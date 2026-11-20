import json
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI

from app.contracts.events import Incident, IncidentCandidate
from app.db.models import RunRow, SourceRow

SOURCE_ID = "source_test_01"
RUN_ID = "run_test_01"
ORIGIN = "http://localhost:5173"
OPERATOR = {"Authorization": "Bearer test-only-token"}
SOCKET_HEADERS = {"Origin": ORIGIN}


def register_test_replay(app: FastAPI) -> None:
    """Insert TEST DATA provenance only into the caller's isolated test database."""
    with app.state.sessions.begin() as session:
        session.add(SourceRow(
            id=SOURCE_ID, title="TEST DATA - synthetic replay", video_path="private-test-path.mp4",
            video_sha256="0" * 64, rights_note="TEST DATA only", attribution="Test fixture",
            license_url=None, geo_mode="unavailable",
        ))
        session.flush()
        now = datetime.now(UTC)
        session.add(RunRow(id=RUN_ID, source_id=SOURCE_ID, mode="replay", status="ended", started_at=now, stopped_at=now))


def test_candidate(key: str, video_time_ms: int = 4000) -> IncidentCandidate:
    fixture = Path(__file__).with_name("fixtures") / "incident.json"
    payload = json.loads(fixture.read_text(encoding="utf-8"))
    context = {key: value for key, value in payload.items() if key in IncidentCandidate.model_fields}
    return IncidentCandidate.model_validate({
        **context, "video_time_ms": video_time_ms, "idempotency_key": f"TEST DATA/{key}",
    })


def publish_test_incident(app: FastAPI, key: str = "zone-crossing") -> Incident:
    """Create a TEST DATA candidate through the production service in an isolated database."""
    return app.state.incidents.publish_incident(test_candidate(key))
