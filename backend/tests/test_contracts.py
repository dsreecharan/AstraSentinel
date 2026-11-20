import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.contracts.events import Incident
from app.contracts.tracks import TrackObservation

FIXTURES = Path(__file__).with_name("fixtures")


def test_observation_round_trips_footage_time_and_absent_geo():
    payload = json.loads((FIXTURES / "track_observation.json").read_text(encoding="utf-8"))

    observation = TrackObservation.model_validate(payload)

    assert observation.video_time_ms == 4000
    assert observation.captured_at is None
    assert observation.geo_status == "image_roi_only"
    assert observation.model_dump(mode="json") == payload


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("video_time_ms", -1),
        ("video_time_ms", "4000"),
        ("captured_at", "2026-11-20T13:05:00+05:30"),
    ],
)
def test_observation_rejects_invalid_time_fields(field: str, value: int | str):
    payload = json.loads((FIXTURES / "track_observation.json").read_text(encoding="utf-8"))
    payload[field] = value

    with pytest.raises(ValidationError):
        TrackObservation.model_validate(payload)


def test_observation_rejects_world_location_in_image_space():
    payload = json.loads((FIXTURES / "track_observation.json").read_text(encoding="utf-8"))
    payload["tracks"][0]["location"] = {"type": "Point", "coordinates": [78.4, 17.4]}

    with pytest.raises(ValidationError, match="locations require a calibrated frame"):
        TrackObservation.model_validate(payload)


def test_incident_preserves_pending_review_and_absent_geo():
    payload = json.loads((FIXTURES / "incident.json").read_text(encoding="utf-8"))

    incident = Incident.model_validate(payload)

    assert incident.review_status == "pending"
    assert incident.observed_at is None
    assert incident.geo_status == "image_roi_only"
    assert incident.model_dump(mode="json") == payload
