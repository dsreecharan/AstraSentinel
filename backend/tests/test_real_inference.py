import os
from collections import Counter
from importlib.util import find_spec
from pathlib import Path
from time import monotonic, sleep

import pytest
from fastapi.testclient import TestClient

from app.config import local_path
from app.main import create_app
from app.media import file_sha256

from .replay_support import configure_replay, register_test_mp4, start_test_replay


@pytest.mark.real_inference
def test_real_yolo26n_bytetrack_replays_local_mp4(database, monkeypatch):
    weights = local_path("ASTRA_MODEL_WEIGHTS", "data/weights/yolo26n.pt")
    if not weights.is_file():
        pytest.skip("Local YOLO26n weights absent. Set ASTRA_MODEL_WEIGHTS to a trusted yolo26n.pt file.")
    video_path = os.getenv("ASTRA_INFERENCE_SMOKE_MP4")
    if not video_path or not Path(video_path).is_file():
        pytest.skip("Set ASTRA_INFERENCE_SMOKE_MP4 to a short permissioned local MP4 with visible people or vehicles.")
    if find_spec("ultralytics") is None:
        pytest.skip("Install the locked vision extra to run actual YOLO26n and ByteTrack.")

    video = Path(video_path).resolve()
    configure_replay(monkeypatch, video.parent)
    api = create_app(database)
    register_test_mp4(api, video)
    with TestClient(api) as client:
        for _ in range(2):
            run_id = start_test_replay(client)
            samples = []
            previous = None
            persistent = False
            total_frames = 0
            deadline = monotonic() + 45
            while monotonic() < deadline:
                current = client.get("/api/v1/runs/status").json()["run"]
                for item in api.state.video.drain_observations():
                    ids = {track.track_id for track in item.tracks}
                    assert all(track_id.startswith(f"{run_id}:") for track_id in ids)
                    if previous is not None and previous[0] + 1 == item.frame_index and previous[1] & ids:
                        persistent = True
                    previous = (item.frame_index, ids)
                    total_frames += 1
                    if len(samples) < 6:
                        counts = Counter(track.object_class for track in item.tracks)
                        samples.append((item.frame_index, item.video_time_ms, dict(sorted(counts.items()))))
                if current["status"] in {"ended", "error"}:
                    break
                sleep(0.025)
            assert current["id"] == run_id and current["status"] == "ended", current
            assert current["model"]["weights_sha256"] == file_sha256(weights)
            assert current["model"]["tracker"] == "bytetrack"
            assert persistent, f"No persistent ByteTrack ID on consecutive frames. Sample counts: {samples}"
            print(
                f"Real YOLO26n + ByteTrack replay reached EOS. Observed {total_frames} frames. "
                f"(frame, ms, tracked objects by class): {samples}"
            )
