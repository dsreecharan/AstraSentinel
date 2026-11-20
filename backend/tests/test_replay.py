from datetime import UTC, datetime
from threading import Event, current_thread

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.contracts.events import ModelProvenance
from app.db.models import RunRow
from app.main import create_app
from app.media import file_sha256
from app.vision.engine import Detection
from app.vision.errors import ReplayError
from app.vision.source import OpenCVVideoSource
from app.vision.worker import OBSERVATION_CAPACITY

from .replay_support import (
    SOURCE_ID, configure_replay, generate_mp4, register_test_mp4, start_test_replay, wait_for_status,
)
from .support import OPERATOR, SOCKET_HEADERS


class FakeVisionEngine:
    """TEST DATA only. The production application factory defaults to Ultralytics."""

    def __init__(self, startup_gate: Event | None = None):
        self.started = Event()
        self.startup_gate = startup_gate
        self.runs: list[str] = []
        self.inference_threads: list[str] = []

    def start_run(self, run_id: str) -> ModelProvenance:
        self.runs.append(run_id)
        self.started.set()
        if self.startup_gate is not None:
            assert self.startup_gate.wait(timeout=5)
        return ModelProvenance(name="yolo26n", weights_sha256="0" * 64, ultralytics_version="TEST DATA", tracker="bytetrack")

    def track(self, image) -> list[Detection]:
        self.inference_threads.append(current_thread().name)
        assert image.shape == (96, 160, 3)
        return [
            Detection("person", (10.0, 30.0, 40.0, 70.0), 0.9, f"{self.runs[-1]}:1"),
            Detection("vehicle", (64.0, 40.0, 110.0, 80.0), 0.8, None),
        ]


@pytest.fixture
def video(tmp_path):
    return generate_mp4(tmp_path / "TEST DATA.mp4")


def test_opencv_source_reads_real_mp4_and_footage_timecodes(video):
    source = OpenCVVideoSource(video.parent, video, file_sha256(video))
    with source:
        assert source.source_fps == pytest.approx(20.0)
        frames = []
        while (frame := source.read()) is not None:
            frames.append(frame)
        assert [frame.frame_index for frame in frames] == list(range(12))
        assert [frame.video_time_ms for frame in frames] == [index * 50 for index in range(12)]
        assert all(frame.image.shape == (96, 160, 3) for frame in frames)
    with pytest.raises(RuntimeError, match="Open the video source"):
        source.read()


def test_opencv_source_reports_early_eof_and_uses_fps_estimate(monkeypatch, video):
    class TestCapture:
        def __init__(self, *_):
            self.frames = 0

        def isOpened(self):
            return True

        def get(self, flag):
            return {cv2.CAP_PROP_FPS: 20, cv2.CAP_PROP_FRAME_COUNT: 3, cv2.CAP_PROP_POS_MSEC: 0}[flag]

        def read(self):
            self.frames += 1
            return self.frames <= 2, np.zeros((96, 160, 3), dtype=np.uint8)

        def release(self):
            pass

    monkeypatch.setattr(cv2, "VideoCapture", TestCapture)
    with OpenCVVideoSource(video.parent, video, file_sha256(video)) as source:
        assert source.read().video_time_ms == 0
        assert source.read().video_time_ms == 50
        with pytest.raises(ReplayError) as error:
            source.read()
        assert error.value.code == "decode_failed"


def test_replay_runs_to_eof_and_serves_annotated_mjpeg(database, monkeypatch, video):
    configure_replay(monkeypatch, video.parent)
    engine = FakeVisionEngine()
    factory_calls = []

    def make_engine():
        factory_calls.append(True)
        return engine

    api = create_app(database, vision_factory=make_engine)
    register_test_mp4(api, video)
    with TestClient(api) as client:
        assert client.get("/api/v1/runs/status").json() == {"run": None}
        assert client.get("/api/v1/stream/annotated.mjpg").status_code == 503
        with client.websocket_connect("/ws/events", headers=SOCKET_HEADERS) as ws:
            assert ws.receive_json()["type"] == "ready"
            run_id = start_test_replay(client)
            assert ws.receive_json()["data"] == {"run_id": run_id, "source_id": SOURCE_ID, "status": "starting"}
            assert ws.receive_json()["data"]["status"] == "running"
            response = client.get("/api/v1/stream/annotated.mjpg", params={"run": run_id}, headers=SOCKET_HEADERS)
            assert response.status_code == 200, response.text
            assert response.headers["content-type"] == "multipart/x-mixed-replace; boundary=frame"
            assert response.headers["cache-control"] == "no-store"
            assert response.headers["cross-origin-resource-policy"] == "same-origin"
            assert response.headers["access-control-allow-origin"] == SOCKET_HEADERS["Origin"]
            header, first_jpeg = response.content.split(b"\r\n\r\n", 1)
            assert header.startswith(b"--frame\r\nContent-Type: image/jpeg")
            jpeg_length = int(header.rsplit(b" ", 1)[-1])
            preview = cv2.imdecode(np.frombuffer(first_jpeg[:jpeg_length], dtype=np.uint8), cv2.IMREAD_COLOR)
            assert preview.shape == (96, 160, 3)
            assert response.content.endswith(b"--frame--\r\n")
            assert ws.receive_json()["data"]["status"] == "ended"

        ended = wait_for_status(client, "ended")
        assert ended["id"] == run_id and ended["stopped_at"] is not None
        assert ended["model"]["tracker"] == "bytetrack"
        assert client.get("/api/v1/health").json()["inference_status"] == "ready"
        assert client.get("/api/v1/stream/annotated.mjpg").json()["error"]["code"] == "frame_unavailable"
        observations = api.state.video.drain_observations()
        assert [item.frame_index for item in observations] == list(range(12 - OBSERVATION_CAPACITY, 12))
        assert [item.video_time_ms for item in observations] == [item.frame_index * 50 for item in observations]
        assert all(item.tracks[0].track_id == f"{run_id}:1" and len(item.tracks) == 1 for item in observations)
        assert all(item.captured_at is None and item.geo_status == "unavailable" for item in observations)

        second_id = start_test_replay(client)
        assert wait_for_status(client, "running")["id"] == second_id
        stale_frame = client.get("/api/v1/stream/annotated.mjpg", params={"run": run_id})
        assert stale_frame.status_code == 503 and stale_frame.json()["error"]["code"] == "frame_unavailable"
        assert wait_for_status(client, "ended")["id"] == second_id
        assert {item.tracks[0].track_id for item in api.state.video.drain_observations()} == {f"{second_id}:1"}
        assert factory_calls == [True]
        assert engine.runs == [run_id, second_id]
        assert set(engine.inference_threads) == {"astra-video-worker"}


def test_stop_during_loading_releases_worker_without_emitting_stale_frames(database, monkeypatch, video):
    configure_replay(monkeypatch, video.parent)
    gate = Event()
    engine = FakeVisionEngine(gate)
    api = create_app(database, vision_factory=lambda: engine)
    register_test_mp4(api, video)
    with TestClient(api) as client:
        run_id = start_test_replay(client)
        try:
            assert engine.started.wait(timeout=3)
            assert client.get("/api/v1/health").json()["inference_status"] == "loading"
            conflict = client.post("/api/v1/runs/start", json={"source_id": SOURCE_ID, "mode": "replay"}, headers=OPERATOR)
            assert conflict.status_code == 409 and conflict.json()["error"]["code"] == "run_active"
            assert client.get("/api/v1/stream/annotated.mjpg").status_code == 503
            for _ in range(2):
                response = client.post("/api/v1/runs/stop", headers=OPERATOR, json={"run_id": run_id})
                assert response.status_code == 202 and response.json()["status"] == "stopping"
        finally:
            gate.set()
        stopped = wait_for_status(client, "stopped")
        assert stopped["stopped_at"] is not None and not api.state.video.drain_observations()
        assert client.post("/api/v1/runs/stop", headers=OPERATOR, json={"run_id": run_id}).status_code == 200
        assert client.get("/api/v1/stream/annotated.mjpg").status_code == 503
        assert not engine.inference_threads
    with TestClient(create_app(database)) as restarted:
        assert restarted.get("/api/v1/runs/status").json()["run"] == stopped


@pytest.mark.parametrize("stop_via_api", [True, False])
def test_stop_while_running_and_lifespan_shutdown(database, monkeypatch, tmp_path, stop_via_api):
    video = generate_mp4(tmp_path / "longer.mp4", frames=40, fps=5)
    configure_replay(monkeypatch, video.parent)
    api = create_app(database, vision_factory=FakeVisionEngine)
    register_test_mp4(api, video)
    with TestClient(api) as client:
        run_id = start_test_replay(client)
        assert wait_for_status(client, "running")["id"] == run_id
        if stop_via_api:
            response = client.post("/api/v1/runs/stop", headers=OPERATOR, json={"run_id": run_id})
            assert response.status_code == 202 and response.json()["status"] == "stopping"
            assert client.get("/api/v1/stream/annotated.mjpg").status_code == 503
            assert wait_for_status(client, "stopped")["id"] == run_id
            assert client.get("/api/v1/stream/annotated.mjpg").status_code == 503
    with TestClient(create_app(database)) as restarted:
        assert restarted.get("/api/v1/runs/status").json()["run"]["status"] == "stopped"


def test_restart_marks_interrupted_run_and_requires_operator_for_writes(database, monkeypatch, video):
    configure_replay(monkeypatch, video.parent)
    api = create_app(database, vision_factory=FakeVisionEngine)
    register_test_mp4(api, video)
    with api.state.sessions.begin() as session:
        session.add(RunRow(id="interrupted", source_id=SOURCE_ID, mode="replay", status="starting", started_at=datetime.now(UTC)))
    with TestClient(api) as client:
        status = client.get("/api/v1/runs/status").json()["run"]
        assert status["id"] == "interrupted" and status["error"]["code"] == "run_interrupted"
        for path, params in [("start", {"source_id": SOURCE_ID, "mode": "replay"}), ("stop", {"run_id": "interrupted"})]:
            response = client.post(f"/api/v1/runs/{path}", json=params)
            assert response.status_code == 401


@pytest.mark.parametrize(("scenario", "code"), [
    ("corrupt", "decode_failed"), ("outside", "video_unavailable"), ("changed", "video_changed"),
    ("missing_video", "video_unavailable"), ("missing_model", "model_unavailable"),
])
def test_failed_replay_is_explicit_and_never_streams_synthetic_results(database, monkeypatch, video, scenario, code):
    media_root = video.parent
    if scenario == "corrupt":
        video.write_bytes(b"TEST DATA: deliberately invalid MP4")
    if scenario == "outside":
        media_root = video.parent / "allowlisted"
        media_root.mkdir()
    configure_replay(monkeypatch, media_root)
    monkeypatch.setenv("ASTRA_MODEL_WEIGHTS", str(video.parent / "missing" / "yolo26n.pt"))
    api = create_app(database)
    register_test_mp4(api, video)
    if scenario == "changed":
        video.write_bytes(b"TEST DATA: replaced after registration")
    if scenario == "missing_video":
        video.unlink()
    with TestClient(api) as client:
        start_test_replay(client)
        failed = wait_for_status(client, "error")
        assert failed["error"]["code"] == code
        assert str(video.parent) not in failed["error"]["message"]
        assert failed["model"] is None and failed["stopped_at"] is not None
        assert client.get("/api/v1/stream/annotated.mjpg").status_code == 503
        assert not api.state.video.drain_observations()
