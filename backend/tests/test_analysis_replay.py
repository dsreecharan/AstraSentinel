import json

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.contracts.events import ModelProvenance
from app.main import create_app
from app.media import MAX_THUMBNAIL_BYTES
from app.vision.engine import Detection

from .replay_support import (
    SOURCE_ID, configure_replay, generate_mp4, register_test_mp4, start_test_replay, wait_for_status,
)
from .support import OPERATOR, SOCKET_HEADERS


class ControlledReplay:
    def start_run(self, run_id):
        self.run_id = run_id
        self.index = 0
        return ModelProvenance(name="yolo26n", weights_sha256="0" * 64, ultralytics_version="TEST DATA", tracker="bytetrack")

    def track(self, _image):
        x = 20 if self.index < 2 else 90
        self.index += 1
        return [Detection("person", (x - 3, 40, x + 3, 70), 0.9, f"{self.run_id}:1")]


@pytest.mark.parametrize("retain", [True, False])
def test_worker_publishes_one_image_roi_candidate_with_opt_in_evidence(database, monkeypatch, tmp_path, retain):
    video = generate_mp4(tmp_path / "controlled.mp4")
    config = tmp_path / "rules.json"
    config.write_text(json.dumps({"sources": {SOURCE_ID: {
        "zone": {"consecutive_frames": 2, "cooldown_ms": 0}, "retain_thumbnails": retain,
    }}}))
    configure_replay(monkeypatch, video.parent)
    monkeypatch.setenv("ASTRA_ANALYSIS_CONFIG", str(config))
    api = create_app(database, vision_factory=ControlledReplay)
    register_test_mp4(api, video)
    with TestClient(api) as client:
        created = client.post("/api/v1/geofences", headers=OPERATOR, json={
            "source_id": SOURCE_ID, "label": "Right side", "space_type": "image", "enabled": True,
            "frame_size_px": [160, 96], "geometry": {
                "type": "Polygon", "coordinates": [[[80, 30], [150, 30], [150, 90], [80, 90], [80, 30]]],
            },
        })
        assert created.status_code == 201, created.text
        with client.websocket_connect("/ws/events", headers=SOCKET_HEADERS) as ws:
            assert ws.receive_json()["type"] == "ready"
            run_id = start_test_replay(client)
            assert [ws.receive_json()["data"]["status"] for _ in range(2)] == ["starting", "running"]
            event = ws.receive_json()
            assert event["type"] == "candidate_incident"
            incident = client.get(f"/api/v1/incidents/{event['data']['incident_id']}").json()
            assert incident["run_id"] == run_id and incident["source_id"] == SOURCE_ID
            assert incident["geo_status"] == "image_roi_only" and incident["location"] is None
            assert incident["review_status"] == "pending" and incident["video_time_ms"] == 150
            assert incident["rule_details"]["trigger_frame_index"] == 3
            assert incident["rule_details"]["zone_id"] == created.json()["id"]
            thumbnail_path = f"/api/v1/incidents/{incident['id']}/thumbnail"
            evidence = client.get(thumbnail_path, headers=SOCKET_HEADERS)
            if retain:
                assert incident["evidence_url"] == thumbnail_path
                assert evidence.status_code == 200 and evidence.headers["content-type"] == "image/jpeg"
                assert evidence.headers["Cache-Control"] == "no-store"
                assert 0 < len(evidence.content) <= MAX_THUMBNAIL_BYTES
                image = cv2.imdecode(np.frombuffer(evidence.content, dtype=np.uint8), cv2.IMREAD_COLOR)
                assert image.shape == (96, 160, 3)
            else:
                assert incident["evidence_url"] is None and evidence.status_code == 404
                assert evidence.json()["error"]["code"] == "evidence_unavailable"
            assert ws.receive_json()["data"]["status"] == "ended"
        assert wait_for_status(client, "ended")["id"] == run_id
        assert client.get("/api/v1/incidents").json()["total"] == 1
        assert len(client.get(f"/api/v1/incidents/{incident['id']}/audit").json()["items"]) == 1
