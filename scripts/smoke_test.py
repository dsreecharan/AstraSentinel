"""Local acceptance helpers. Fixture records are written only to disposable SQLite."""

import argparse
import json
import os
import secrets
import shutil
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from alembic import command
from alembic.config import Config
from sqlalchemy.orm import sessionmaker

from app.contracts.events import Source
from app.contracts.geo import Geofence
from app.db.models import GeofenceRow
from app.db.session import sqlite_engine
from app.media import file_sha256
from app.seed_source import register_source

AERIAL = ROOT / "data/demo_video/aerial-intersection-validation.mp4"
AERIAL_SHA = "2b08fdd659f337e7ce4898098b09c64a3f49c204854cdfb02beb623ba8ea71b7"
STILL_SHA = "88431cd9653ccd539741b555fb0a46b61558b301d4110412b5bc28b5e3ea6cb5"
ORIGIN = "http://localhost:5173"
CONTROLLED = "controlled-rule-verification"


def migrate(database: Path) -> None:
    engine = sqlite_engine(database)
    try:
        with engine.connect() as connection:
            config = Config(str(BACKEND / "alembic.ini"))
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
    finally:
        engine.dispose()


def require(condition: object, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def fixture() -> None:
    from fastapi.testclient import TestClient

    from tests.support import OPERATOR, SOCKET_HEADERS, publish_test_incident, register_test_replay

    with TemporaryDirectory(prefix="astra-api-smoke-") as folder:
        database = Path(folder) / "TEST DATA.sqlite3"
        os.environ.update(
            ASTRA_DB_PATH=str(database), ASTRA_FRONTEND_ORIGIN=ORIGIN, ASTRA_ANALYSIS_CONFIG="",
            ASTRA_OPERATOR_TOKEN=OPERATOR["Authorization"].removeprefix("Bearer "), ASTRA_OPERATOR_NAME="smoke-operator",
        )
        from app.main import create_app

        migrate(database)
        app = create_app(database)
        register_test_replay(app)
        with TestClient(app) as client, client.websocket_connect("/ws/events", headers=SOCKET_HEADERS) as socket:
            health = client.get("/api/v1/health")
            require(health.status_code == 200 and health.json()["inference_status"] == "not_started",
                    "Health or unloaded inference state failed")
            require(socket.receive_json()["type"] == "ready", "WebSocket did not send ready")
            incident = publish_test_incident(app)
            message = socket.receive_json()
            require(message["type"] == "candidate_incident" and message["data"]["incident_id"] == incident.id,
                    "Candidate WebSocket notification missing")
            route = f"/api/v1/incidents/{incident.id}"
            pending = client.get(route).json()
            require(pending["review_status"] == "pending", "Committed incident is missing from REST")
            require(publish_test_incident(app).id == incident.id, "Candidate was duplicated")
            body = {"decision": "acknowledged", "reason": "TEST DATA local API smoke"}
            unauthorized = client.post(route + "/review", json=body)
            require(unauthorized.status_code == 401 and unauthorized.json()["error"]["code"] == "unauthorized",
                    "An unauthenticated review was accepted")
            reviewed = client.post(route + "/review", json=body, headers=OPERATOR)
            require(reviewed.status_code == 200 and reviewed.json()["reviewer"] == "smoke-operator",
                    "Authenticated review or server-derived actor failed")
            message = socket.receive_json()
            require(message["type"] == "incident_reviewed" and message["data"]["incident_id"] == incident.id,
                    "Review WebSocket notification missing")
            repeated = client.post(route + "/review", json=body, headers=OPERATOR)
            require(repeated.status_code == 409 and repeated.json()["error"]["code"] == "review_conflict",
                    "Repeated review did not produce a conflict")
            audit = client.get(route + "/audit").json()
            require([entry["action"] for entry in audit["items"]] == ["created", "acknowledged"] and
                    audit["items"][1]["reason"] == body["reason"], "Expected exactly one recorded decision with reason")
        with TestClient(create_app(database)) as client, client.websocket_connect("/ws/events", headers=SOCKET_HEADERS) as socket:
            require(socket.receive_json()["type"] == "ready", "Restarted app did not accept WebSocket reconnect")
            require(client.get(route).json() == reviewed.json(), "Incident changed across app restart")
            require(client.get(route + "/audit").json() == audit, "Audit changed across app restart")
    print("PASS TEST DATA health, durable candidate, idempotency, auth, review, audit, app restart and WebSocket reconnect")


def controlled_video(still: Path, output: Path) -> None:
    import cv2
    import numpy as np

    photo = cv2.imdecode(np.frombuffer(still.read_bytes(), dtype=np.uint8), cv2.IMREAD_COLOR)
    require(photo is not None and photo.shape == (512, 512, 3), "Expected the 512 × 512 NASA source still")
    writer = cv2.VideoWriter(str(output), cv2.VideoWriter_fourcc(*"mp4v"), 10.0, (1152, 512))
    try:
        require(writer.isOpened(), "OpenCV could not create the controlled MP4")
        for index in range(45):
            frame = np.zeros((512, 1152, 3), dtype=np.uint8)
            left = 16 + 6 * min(index, 37)
            frame[:, left:left + 512] = photo
            frame[:, 640:] = photo
            writer.write(frame)
    finally:
        writer.release()


def prepare(output: Path, still: Path, weights: Path, *, controlled_only: bool = False) -> None:
    if not controlled_only:
        require(AERIAL.is_file() and file_sha256(AERIAL) == AERIAL_SHA,
                "Supply the verified aerial excerpt listed in data/README.md, or use --controlled-only")
    require(still.is_file() and file_sha256(still) == STILL_SHA, "Supply the pinned astronaut.png listed in docs/SMOKE_TEST.md")
    require(weights.is_file() and weights.suffix.lower() == ".pt", "Supply a trusted local YOLO26n .pt checkpoint")
    output = output.resolve()
    output.mkdir(parents=True)
    media = output / "media"
    media.mkdir()
    controlled = media / "controlled-two-tracks.mp4"
    controlled_video(still, controlled)
    controlled_sha = file_sha256(controlled)
    fence = {
        "source_id": CONTROLLED, "label": "Controlled crossing at x=385",
        "space_type": "image", "enabled": True, "frame_size_px": [1152, 512],
        "geometry": {"type": "Polygon", "coordinates": [[[385, 0], [610, 0], [610, 512], [385, 512], [385, 0]]]},
    }
    database = output / "smoke.sqlite3"
    migrate(database)
    engine = sqlite_engine(database)
    try:
        sessions = sessionmaker(engine)
        if not controlled_only:
            aerial = media / AERIAL.name
            shutil.copyfile(AERIAL, aerial)
            register_source(sessions, Source(
                id="aerial-intersection-validation", title="Aerial intersection - licensed excerpt",
                video_sha256=AERIAL_SHA, rights_note="Local verification excerpt. Pexels license and terms apply.",
                attribution="Matthias Groeneveld via Pexels", license_url="https://www.pexels.com/license/",
                geo_mode="unavailable",
            ), aerial)
        register_source(sessions, Source(
            id=CONTROLLED, title="Controlled fixture - NASA still with two tracks", video_sha256=controlled_sha,
            rights_note="Public-domain NASA still assembled into a controlled MP4. Real person inference on the composite.",
            attribution="NASA via scikit-image astronaut()", geo_mode="unavailable",
            license_url="https://scikit-image.org/docs/0.26.x/api/skimage.data.html#skimage.data.astronaut",
        ), controlled)
        if controlled_only:
            zone = Geofence(id="controlled-crossing", **fence)
            with sessions.begin() as session:
                session.add(GeofenceRow(**zone.model_dump(mode="json")))
    finally:
        engine.dispose()
    rules = output / "rules.json"
    rules.write_text(json.dumps({"sources": {CONTROLLED: {
        "crowd": {"threshold_count": 1, "clear_count": 0, "consecutive_frames": 3},
        "zone": {"consecutive_frames": 3}, "retain_thumbnails": True,
    }}}, indent=2) + "\n", encoding="utf-8")
    env = {
        "ASTRA_DB_PATH": database.as_posix(), "ASTRA_MEDIA_DIR": media.as_posix(),
        "ASTRA_MODEL_WEIGHTS": weights.resolve().as_posix(), "ASTRA_ANALYSIS_CONFIG": rules.as_posix(),
        "ASTRA_FRONTEND_ORIGIN": ORIGIN, "ASTRA_OPERATOR_NAME": "smoke-operator",
        "ASTRA_OPERATOR_TOKEN": secrets.token_urlsafe(32), "YOLO_CONFIG_DIR": (output / "vision-runtime").as_posix(),
    }
    (output / ".env").write_text(
        "".join(f"{name}={json.dumps(value, ensure_ascii=False)}\n" for name, value in env.items()), encoding="utf-8"
    )
    (output / "zone.json").write_text(json.dumps(fence, indent=2) + "\n", encoding="utf-8")
    source_summary = "one registered source, one image ROI" if controlled_only else "two registered sources"
    print(f"PASS {source_summary} and zero seeded incidents. Controlled MP4 SHA-256 {controlled_sha}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)
    sub.add_parser("fixture", help="Check deterministic TEST DATA through the authenticated API.")
    prep = sub.add_parser("prepare", help="Build an isolated environment for the real replay walkthrough.")
    prep.add_argument("--output", type=Path, required=True, help="A new directory for private verification files.")
    prep.add_argument("--still", type=Path, required=True)
    prep.add_argument("--weights", type=Path, default=ROOT / "YOLO26/yolo26n.pt")
    prep.add_argument("--controlled-only", action="store_true", help="Prepare the controlled MP4 and ROI without the private aerial excerpt")
    args = parser.parse_args()
    try:
        if args.mode == "fixture":
            fixture()
        else:
            prepare(args.output, args.still, args.weights, controlled_only=args.controlled_only)
    except (OSError, RuntimeError, ValueError) as error:
        print(f"FAIL {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
