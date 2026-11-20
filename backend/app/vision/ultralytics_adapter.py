import os
from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from time import perf_counter_ns
from typing import Literal

from app.contracts.events import ModelProvenance
from app.media import file_sha256

from .engine import Detection
from .errors import ReplayError
from .source import Image

ObjectClass = Literal["person", "vehicle"]
DEVICE = "cpu"
IMAGE_SIZE = 640
TRACKER_CONFIG = "bytetrack.yaml"
CLASS_NAMES: dict[str, ObjectClass] = {
    "person": "person",
    "bicycle": "vehicle",
    "car": "vehicle",
    "motorcycle": "vehicle",
    "bus": "vehicle",
    "truck": "vehicle",
}


@dataclass(frozen=True)
class VisionTimings:
    inference_ms: float
    tracking_ms: float


class UltralyticsAdapter:
    def __init__(self, weights: Path):
        self._weights = weights
        self._model = None
        self._provenance: ModelProvenance | None = None
        self._class_ids: dict[int, ObjectClass] = {}
        self._run_id: str | None = None

    def _load(self) -> None:
        if not self._weights.is_file() or self._weights.suffix.lower() != ".pt":
            raise ReplayError("model_unavailable", "Configure a trusted local YOLO26n .pt weights file")

        # The pinned Ultralytics package reads these switches at import time.
        os.environ["YOLO_OFFLINE"] = "true"
        os.environ["YOLO_AUTOINSTALL"] = "false"
        try:
            from ultralytics import YOLO, __version__

            digest = file_sha256(self._weights)
            model = YOLO(str(self._weights), task="detect")
            yaml = model.model.yaml
            architecture = Path(yaml.get("yaml_file", "")).stem
            if architecture != "yolo26n" and (architecture, yaml.get("scale")) != ("yolo26", "n"):
                raise ValueError("unexpected checkpoint architecture")
            if model.task != "detect" or not {"person", "car"} <= set(model.names.values()):
                raise ValueError("checkpoint lacks the required detection classes")
            self._class_ids = {
                index: CLASS_NAMES[name] for index, name in model.names.items() if name in CLASS_NAMES
            }
            self._provenance = ModelProvenance(
                name="yolo26n", weights_sha256=digest, ultralytics_version=__version__, tracker="bytetrack"
            )
            self._model = model
        except ImportError as error:
            raise ReplayError("model_unavailable", "The optional Ultralytics vision dependencies are unavailable") from error
        except Exception as error:
            raise ReplayError("model_unavailable", "Could not load the configured YOLO26n detection checkpoint") from error

    def start_run(self, run_id: str) -> ModelProvenance:
        if self._model is None:
            self._load()
        try:
            for tracker in getattr(self._model.predictor, "trackers", ()):
                tracker.reset()
        except Exception as error:
            raise ReplayError("tracker_failed", "Could not reset ByteTrack for a new replay") from error
        self._run_id = run_id
        assert self._provenance is not None
        return self._provenance

    def track(self, image: Image) -> list[Detection]:
        detections, _ = self._track(image)
        return detections

    def track_timed(self, image: Image) -> tuple[list[Detection], VisionTimings]:
        """Profile batch-one forward time and the actual ByteTrack update on a warmed adapter."""
        from unittest.mock import patch

        trackers = getattr(getattr(self._model, "predictor", None), "trackers", ())
        if len(trackers) != 1:
            raise RuntimeError("Run at least one warm-up frame before timing ByteTrack")
        tracker = trackers[0]
        original_update = tracker.update
        samples_ms: list[float] = []

        def timed_update(*args, **kwargs):
            started = perf_counter_ns()
            result = original_update(*args, **kwargs)
            samples_ms.append((perf_counter_ns() - started) / 1_000_000)
            return result

        with patch.object(tracker, "update", timed_update):
            detections, speed = self._track(image)
        inference_ms = speed.get("inference")
        if len(samples_ms) != 1 or inference_ms is None or not isfinite(inference_ms) or inference_ms < 0:
            raise RuntimeError("The installed vision runtime did not provide one valid batch-one timing")
        return detections, VisionTimings(inference_ms, samples_ms[0])

    def _track(self, image: Image) -> tuple[list[Detection], dict[str, float | None]]:
        if self._run_id is None or self._model is None:
            raise RuntimeError("Start a replay before tracking")
        try:
            results = self._model.track(
                source=image, persist=True, tracker=TRACKER_CONFIG, classes=list(self._class_ids),
                device=DEVICE, imgsz=IMAGE_SIZE, batch=1, verbose=False, save=False,
            )
            trackers = self._model.predictor.trackers
            if len(trackers) != 1 or trackers[0].args.tracker_type != "bytetrack":
                raise RuntimeError("the single ByteTrack tracker was not initialized")

            boxes = results[0].boxes.cpu().numpy()
            identifiers = boxes.id if boxes.id is not None else [None] * len(boxes)
            detections = []
            for xyxy, score, category, local_id in zip(boxes.xyxy, boxes.conf, boxes.cls, identifiers, strict=True):
                left, top, right, bottom = map(float, xyxy)
                if left >= right or top >= bottom:
                    continue
                detections.append(Detection(
                    object_class=self._class_ids[int(category)], bbox_xyxy=(left, top, right, bottom),
                    detector_confidence=float(score),
                    track_id=f"{self._run_id}:{int(local_id)}" if local_id is not None else None,
                ))
            return detections, results[0].speed
        except Exception as error:
            raise ReplayError("tracker_failed", "YOLO26n inference or ByteTrack failed on a replay frame") from error
