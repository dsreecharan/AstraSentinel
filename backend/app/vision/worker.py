import json
import logging
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import Event, Lock, Thread
from time import monotonic

import cv2
import numpy as np
from sqlalchemy.exc import SQLAlchemyError

from app.analysis.config import AnalysisSettings, SourceAnalysis
from app.analysis.replay import ReplayAnalysis
from app.contracts.events import ErrorDetail, Run
from app.contracts.tracks import Track, TrackObservation
from app.db.runs import TERMINAL_STATUSES, ReplayAsset, RunStore
from app.errors import ServiceError
from app.services.events import EventBroker, event_message
from app.services.incidents import IncidentService

from .engine import Detection, VisionEngine
from .errors import ReplayError
from .frames import JpegFrame, LatestFrameStore, annotate_frame, evidence_thumbnail, frame_jpeg
from .source import OpenCVVideoSource, VideoFrame

logger = logging.getLogger(__name__)
server_log = logging.getLogger("uvicorn.error")
OBSERVATION_CAPACITY = 8


@dataclass
class ActiveReplay:
    run: Run
    asset: ReplayAsset
    stop: Event
    accepted_at: float
    thread: Thread | None = None


def observation_for(run: Run, frame: VideoFrame, detections: list[Detection]) -> TrackObservation:
    tracks = []
    for detection in detections:
        if detection.track_id is None:
            continue
        left, _, right, bottom = detection.bbox_xyxy
        tracks.append(Track(
            track_id=detection.track_id, object_class=detection.object_class,
            detector_confidence=detection.detector_confidence, bbox_xyxy=detection.bbox_xyxy,
            bottom_center_px=((left + right) / 2, bottom), location=None, horizontal_error_m=None,
        ))
    return TrackObservation(
        schema_version="1.0", run_id=run.id, source_id=run.source_id,
        frame_index=frame.frame_index, video_time_ms=frame.video_time_ms,
        captured_at=None, processed_at=datetime.now(UTC), mode="replay",
        geo_status="unavailable", tracks=tracks,
    )


class VideoWorker:
    def __init__(
        self, runs: RunStore, broker: EventBroker, media_root: Path, vision_factory: Callable[[], VisionEngine],
        analysis: AnalysisSettings, incidents: IncidentService,
    ):
        self._runs = runs
        self._broker = broker
        self._media_root = media_root
        self._vision_factory = vision_factory
        self._analysis = analysis
        self._incidents = incidents
        self._vision: VisionEngine | None = None
        self._active: ActiveReplay | None = None
        self._lock = Lock()
        self._inference_status = "not_started"
        self._storage_failed = False
        self._closing = False
        self.frames = LatestFrameStore()
        self._observations: deque[TrackObservation] = deque(maxlen=OBSERVATION_CAPACITY)

    @property
    def inference_status(self):
        with self._lock:
            return self._inference_status

    def startup(self, recover: bool) -> None:
        with self._lock:
            self._closing = False
            if recover:
                self._recover_interrupted()

    def _recover_interrupted(self) -> None:
        for run in self._runs.recover_interrupted():
            self._announce(run)
        self._storage_failed = False

    def _announce(self, run: Run) -> None:
        self._broker.notify(event_message("run_status", run_id=run.id, source_id=run.source_id, status=run.status))

    def start(self, source_id: str) -> Run:
        with self._lock:
            if self._active is not None:
                raise ServiceError(409, "run_active", "A replay already owns the worker")
            if self._closing:
                raise ServiceError(503, "storage_unavailable", "The replay service is shutting down")
            if self._storage_failed:
                self._recover_interrupted()
            run, asset = self._runs.create(source_id)
            replay = ActiveReplay(run=run, asset=asset, stop=Event(), accepted_at=monotonic())
            replay.thread = Thread(target=self._run, args=(replay,), name="astra-video-worker")
            self._observations.clear()
            self.frames.replace(None)
            self._active = replay
            self._announce(run)
            try:
                replay.thread.start()
            except RuntimeError:
                self._active = None
                self._storage_failed = True
                failed = self._runs.transition(run.id, "error", error=ErrorDetail(
                    code="worker_failed", message="The replay worker could not start"
                ))
                self._storage_failed = False
                self._announce(failed)
            return run

    def stop(self, run_id: str) -> Run:
        with self._lock:
            if self._storage_failed:
                self._recover_interrupted()
            run = self._runs.get(run_id)
            if run.status in TERMINAL_STATUSES or run.status == "stopping":
                return run
            replay = self._active
            if replay is None or replay.run.id != run_id:
                raise ServiceError(503, "storage_unavailable", "The active replay could not be resolved")
            return self._request_stop(replay)

    def _request_stop(self, replay: ActiveReplay) -> Run:
        replay.stop.set()
        self.frames.replace(None)
        run = self._runs.transition(replay.run.id, "stopping")
        self._announce(run)
        return run

    def status(self) -> Run | None:
        with self._lock:
            if self._storage_failed:
                self._recover_interrupted()
            return self._runs.latest()

    def drain_observations(self) -> list[TrackObservation]:
        with self._lock:
            observations = list(self._observations)
            self._observations.clear()
            return observations

    def shutdown(self) -> None:
        with self._lock:
            self._closing = True
            replay = self._active
            if replay is not None and not replay.stop.is_set():
                try:
                    self._request_stop(replay)
                except SQLAlchemyError:
                    replay.stop.set()
                    logger.error("Could not save the replay stop request during shutdown")
        if replay is not None and replay.thread is not None:
            replay.thread.join()
        with self._lock:
            self._vision = None
            self.frames.replace(None)
            self._observations.clear()

    def _run(self, replay: ActiveReplay) -> None:
        failure = None
        try:
            if not replay.stop.is_set():
                self._replay(replay)
        except ReplayError as error:
            failure = ErrorDetail(code=error.code, message=str(error))
        except SQLAlchemyError:
            failure = ErrorDetail(code="storage_unavailable", message="Could not persist replay data")
        except Exception:
            logger.error("The replay worker failed unexpectedly")
            failure = ErrorDetail(code="worker_failed", message="The replay worker could not process a frame")
        finally:
            self._finish(replay, failure)

    def _replay(self, replay: ActiveReplay) -> None:
        asset = replay.asset
        settings = self._analysis.sources.get(replay.run.source_id) or SourceAnalysis()
        try:
            analysis = ReplayAnalysis(replay.run.id, asset.sha256, settings, asset.geofences)
        except (ValueError, cv2.error, np.linalg.LinAlgError) as error:
            raise ReplayError("analysis_config_invalid", "Check the source's rule, geofence and calibration settings") from error
        if analysis.projector:
            logger.info("Fixed-scene control-point reprojection RMS: %.3f px", analysis.projector.rms_error_px)
        with OpenCVVideoSource(self._media_root, asset.path, asset.sha256) as source:
            if replay.stop.is_set():
                return
            read_start = monotonic()
            frame = source.read()
            decode_seconds = monotonic() - read_start
            if replay.stop.is_set():
                return
            with self._lock:
                self._inference_status = "loading"
            if self._vision is None:
                self._vision = self._vision_factory()
            model = self._vision.start_run(replay.run.id)

            anchor = monotonic()
            last_time_ms = 0
            frames = 0
            processing_seconds = 0.0
            first_frame_ms = 0.0
            while frame is not None:
                if replay.stop.wait(max(0, anchor + frame.video_time_ms / 1000 - monotonic())):
                    return
                processing_start = monotonic()
                detections = self._vision.track(frame.image)
                if replay.stop.is_set():
                    return
                height, width = frame.image.shape[:2]
                result = analysis.process(observation_for(replay.run, frame, detections), (width, height))
                annotated = annotate_frame(frame.image, detections, result.image_regions, len(result.candidates))
                jpeg = frame_jpeg(annotated)
                thumbnail = evidence_thumbnail(annotated) if result.candidates and analysis.retain_thumbnails else None
                with self._lock:
                    if replay.stop.is_set():
                        return
                    if frame.frame_index == 0:
                        self._announce(self._runs.transition(replay.run.id, "running", model=model))
                        self._inference_status = "ready"
                    for candidate in result.candidates:
                        self._incidents.publish_incident(candidate, thumbnail)
                    self._observations.append(result.observation)
                    self.frames.replace(JpegFrame(replay.run.id, frame.frame_index, jpeg))
                published_at = monotonic()
                processing_seconds += decode_seconds + published_at - processing_start
                if frames == 0:
                    first_frame_ms = (published_at - replay.accepted_at) * 1000
                frames += 1
                last_time_ms = frame.video_time_ms
                read_start = monotonic()
                frame = source.read()
                decode_seconds = monotonic() - read_start
            if source.source_fps is not None:
                if replay.stop.wait(max(0, anchor + last_time_ms / 1000 + 1 / source.source_fps - monotonic())):
                    return
            if frames and processing_seconds > 0:
                server_log.info("replay_metrics %s", json.dumps({
                    "run_id": replay.run.id, "source_id": replay.run.source_id,
                    "frames_published": frames, "source_fps": source.source_fps, "processing_seconds": round(processing_seconds, 6),
                    "processing_fps": round(frames / processing_seconds, 3),
                    "accepted_to_first_jpeg_ms": round(first_frame_ms, 3),
                    "post_setup_wall_seconds": round(monotonic() - anchor, 6),
                }))

    def _finish(self, replay: ActiveReplay, failure: ErrorDetail | None) -> None:
        with self._lock:
            self.frames.replace(None)
            if failure is not None and failure.code in {"model_unavailable", "tracker_failed"}:
                self._inference_status = "error"
            elif self._inference_status == "loading":
                self._inference_status = "not_started"

            try:
                if replay.stop.is_set():
                    run = self._runs.transition(replay.run.id, "stopped")
                elif failure is not None:
                    run = self._runs.transition(replay.run.id, "error", error=failure)
                else:
                    run = self._runs.transition(replay.run.id, "ended")
                self._announce(run)
            except SQLAlchemyError:
                self._storage_failed = True
                logger.error("Could not save the terminal replay state")
            finally:
                self._active = None
