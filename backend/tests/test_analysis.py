from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.analysis.config import CrowdSettings, FixedCalibration, SourceAnalysis, ZoneSettings
from app.analysis.homography import GroundProjector
from app.analysis.replay import ReplayAnalysis
from app.contracts.geo import Geofence, Point
from app.contracts.tracks import Track, TrackObservation

SHA = "f" * 64
SIZE = (100, 100)
STAMP = datetime(2026, 11, 20, tzinfo=UTC)


def observation(frame, points, *, run="run", t=None):
    tracks = []
    for index, point in enumerate(points):
        track_id, x, y, kind, confidence = point if isinstance(point, tuple) else (index, point, 50, "person", 0.9)
        tracks.append(Track(
            track_id=f"{run}:{track_id}", object_class=kind, detector_confidence=confidence,
            bbox_xyxy=(x - 2, y - 5, x + 2, y), bottom_center_px=(x, y), location=None, horizontal_error_m=None,
        ))
    return TrackObservation(
        schema_version="1.0", run_id=run, source_id="src", frame_index=frame,
        video_time_ms=t if t is not None else frame * 100, captured_at=None, processed_at=STAMP,
        mode="replay", geo_status="unavailable", tracks=tracks,
    )


def fence(*, world=False):
    if world:
        ring = [[78.0005, 17.0], [78.0011, 17.0], [78.0011, 17.002], [78.0005, 17.002], [78.0005, 17.0]]
    else:
        ring = [[40, 20], [80, 20], [80, 80], [40, 80], [40, 20]]
    return Geofence.model_validate({
        "id": "region", "source_id": "src", "label": "Region", "enabled": True,
        "space_type": "world" if world else "image", "frame_size_px": None if world else SIZE,
        "geometry": {"type": "Polygon", "coordinates": [ring]},
    })


def calibration(**overrides):
    return FixedCalibration.model_validate({
        "camera": "fixed", "video_sha256": SHA, "frame_size_px": SIZE,
        "pixel_points": [(0, 0), (100, 0), (100, 100), (0, 100)],
        "geo_points": [(78, 17), (78.001, 17), (78.001, 17.002), (78, 17.002)],
        **overrides,
    })


def test_crowd_counts_distinct_confident_people_and_respects_frame_gaps():
    analysis = ReplayAnalysis("run", SHA, SourceAnalysis(
        crowd=CrowdSettings(threshold_count=1, clear_count=0, consecutive_frames=2, region_id="region"),
    ), (fence(),))
    rejected = [
        (0, 40, 50, "person", 0.9), (0, 41, 50, "person", 0.8),
        (1, 41, 50, "vehicle", 0.9), (2, 41, 50, "person", 0.24), (3, 20, 50, "person", 0.9),
    ]
    assert not analysis.process(observation(0, rejected), SIZE).candidates
    assert not analysis.process(observation(1, [40, 50]), SIZE).candidates
    assert not analysis.process(observation(3, [40, 50]), SIZE).candidates
    result = analysis.process(observation(4, [40, 50]), SIZE)
    alert, = result.candidates
    assert result.observation.geo_status == alert.geo_status == "image_roi_only"
    assert alert.location is None and alert.horizontal_error_m is None
    assert alert.video_time_ms == 400 and alert.rule_details.person_count == 2
    assert alert.rule_details.trigger_frame_index == 4
    assert alert.rule_details.region_id == "region"
    assert not analysis.process(observation(5, [40, 50]), SIZE).candidates


def test_crowd_hysteresis_and_cooldown_only_emit_for_new_crossings():
    analysis = ReplayAnalysis("run", SHA, SourceAnalysis(
        crowd=CrowdSettings(threshold_count=2, clear_count=1, consecutive_frames=1, cooldown_ms=1000),
    ), ())
    def evaluate(frame, count, time):
        return analysis.process(observation(frame, [50] * count, t=time), SIZE).candidates

    first, = evaluate(0, 3, 0)
    assert first.geo_status == "unavailable" and first.location is None
    assert not evaluate(1, 2, 200)
    assert not evaluate(2, 3, 300)
    assert not evaluate(3, 1, 400)
    assert not evaluate(4, 3, 500)
    assert not evaluate(5, 3, 1100)
    assert not evaluate(6, 1, 1200)
    next_candidate, = evaluate(7, 3, 1300)
    assert first.idempotency_key != next_candidate.idempotency_key


def test_zone_first_seen_inside_boundary_occlusion_reentry_and_reset():
    settings = SourceAnalysis(zone=ZoneSettings(consecutive_frames=2, cooldown_ms=800, track_expiry_ms=600))
    analysis = ReplayAnalysis("run", SHA, settings, (fence(),))
    frames = [[40], [40], [20], [40], [], [40], [40], [40], [20], [40], [40], [40], [20], [40], [40]]
    results = [analysis.process(observation(i, frame), SIZE).candidates for i, frame in enumerate(frames)]
    assert [i for i, candidates in enumerate(results) if candidates] == [6, 14]
    first, = results[6]
    reentry, = results[14]
    assert first.rule_details.track_id == "run:0" and first.location is None
    assert first.idempotency_key != reentry.idempotency_key

    other = ReplayAnalysis("other", SHA, settings, (fence(),))
    assert not other.process(observation(0, [40], run="other"), SIZE).candidates
    assert not other.process(observation(1, [40], run="other"), SIZE).candidates
    with pytest.raises(ValueError, match="different run"):
        other.process(observation(0, [40]), SIZE)


def test_zone_track_expiration_and_mismatched_resolution():
    analysis = ReplayAnalysis("run", SHA, SourceAnalysis(
        zone=ZoneSettings(consecutive_frames=2, track_expiry_ms=300),
    ), (fence(),))
    assert not analysis.process(observation(0, [20]), SIZE).candidates
    assert not analysis.process(observation(1, [50]), SIZE).candidates
    result = analysis.process(observation(2, [50]), (200, 100))
    assert not result.candidates and result.observation.geo_status == "unavailable"
    assert not analysis.process(observation(3, [50]), SIZE).candidates
    assert not analysis.process(observation(4, [50], t=900), SIZE).candidates
    assert not analysis.process(observation(5, [50], t=1000), SIZE).candidates


def test_homography_uses_lon_lat_and_never_extrapolates():
    projector = GroundProjector.fit(calibration(valid_for_frame_range=(2, 9)))
    assert projector.rms_error_px < 0.01
    assert projector.project((25, 75)).coordinates == pytest.approx((78.00025, 17.0015), abs=1e-8)
    assert projector.project((101, 50)) is None
    assert projector.applies(SIZE, 2) and projector.applies(SIZE, 9)
    assert not projector.applies(SIZE, 10)
    assert not projector.applies((200, 100), 3)


@pytest.mark.parametrize("changes", [
    {"pixel_points": [(0, 25), (25, 25), (50, 25), (75, 25)]},
    {"pixel_points": [(0, 0), (100, 0), (100, 100), (0, 100), (50, 50)],
     "geo_points": [(78, 17), (78.001, 17), (78.001, 17.002), (78, 17.002), (78.0008, 17.0017)]},
])
def test_degenerate_or_inaccurate_homography_rejected(changes):
    with pytest.raises(ValueError, match="degenerate|reprojection"):
        GroundProjector.fit(calibration(**changes))


def test_moving_camera_and_wrong_asset_cannot_use_fixed_calibration():
    with pytest.raises(ValidationError):
        calibration(camera="moving")
    with pytest.raises(ValueError, match="checksum"):
        ReplayAnalysis("run", "a" * 64, SourceAnalysis(calibration=calibration()), ())


def test_world_zone_emits_projected_location_only_during_calibration():
    settings = SourceAnalysis(calibration=calibration(), zone=ZoneSettings(consecutive_frames=1))
    analysis = ReplayAnalysis("run", SHA, settings, (fence(world=True),))
    assert not analysis.process(observation(0, [20]), SIZE).candidates
    alert, = analysis.process(observation(1, [70]), SIZE).candidates
    assert alert.geo_status == "calibrated"
    assert alert.location.coordinates == pytest.approx((78.0007, 17.001), abs=1e-8)
    assert alert.horizontal_error_m is None
    forged = observation(2, [70])
    forged.geo_status = "calibrated"
    forged.tracks[0].location = Point(type="Point", coordinates=(78.001, 17.001))
    uncalibrated = ReplayAnalysis("run", SHA, SourceAnalysis(), (fence(world=True),)).process(forged, SIZE)
    assert uncalibrated.observation.geo_status == "unavailable" and not uncalibrated.candidates
    assert uncalibrated.observation.tracks[0].location is None


def test_pixel_zone_stays_image_space_even_when_a_track_can_be_projected():
    settings = SourceAnalysis(calibration=calibration(), zone=ZoneSettings(consecutive_frames=1))
    analysis = ReplayAnalysis("run", SHA, settings, (fence(),))
    assert not analysis.process(observation(0, [20]), SIZE).candidates
    result = analysis.process(observation(1, [70]), SIZE)
    assert result.observation.geo_status == "calibrated" and result.observation.tracks[0].location is not None
    alert, = result.candidates
    assert alert.geo_status == "image_roi_only"
    assert alert.location is None and alert.horizontal_error_m is None
