from pathlib import Path
from time import monotonic, sleep

import cv2
import numpy as np
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.contracts.events import Source
from app.media import file_sha256
from app.seed_source import register_source

from .support import OPERATOR

SOURCE_ID = "vision-test"


def generate_mp4(path: Path, frames: int = 12, fps: float = 20.0) -> Path:
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (160, 96))
    if not writer.isOpened():
        raise AssertionError("OpenCV could not encode the synthetic MP4 fixture")
    try:
        for index in range(frames):
            image = np.full((96, 160, 3), 32, dtype=np.uint8)
            cv2.rectangle(image, (10 + index, 30), (40 + index, 70), (215, 215, 215), cv2.FILLED)
            writer.write(image)
    finally:
        writer.release()
    return path


def register_test_mp4(app: FastAPI, path: Path) -> None:
    source = Source(
        id=SOURCE_ID, title="TEST DATA - replay verification", video_sha256=file_sha256(path),
        rights_note="Offline test use only", attribution="Test fixture",
        license_url=None, geo_mode="unavailable",
    )
    register_source(app.state.sessions, source, path)


def configure_replay(monkeypatch, media: Path) -> None:
    monkeypatch.setenv("ASTRA_MEDIA_DIR", str(media))
    monkeypatch.setenv("ASTRA_FRONTEND_ORIGIN", "http://localhost:5173")
    monkeypatch.setenv("ASTRA_OPERATOR_TOKEN", "test-only-token")


def start_test_replay(client: TestClient) -> str:
    response = client.post("/api/v1/runs/start", headers=OPERATOR, json={"source_id": SOURCE_ID, "mode": "replay"})
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["status"] == "starting"
    return body["id"]


def wait_for_status(client: TestClient, *statuses: str, timeout: float = 5.0) -> dict:
    deadline = monotonic() + timeout
    while monotonic() < deadline:
        response = client.get("/api/v1/runs/status")
        assert response.status_code == 200, response.text
        latest = response.json()["run"]
        if latest is not None and latest["status"] in statuses:
            return latest
        sleep(0.02)
    raise AssertionError(f"Replay did not reach {statuses}: {response.text}")
