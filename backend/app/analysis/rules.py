import json
from dataclasses import dataclass, field

from app.contracts.events import CrowdRuleDetails, IncidentCandidate, ZoneRuleDetails
from app.contracts.geo import FrameSize, Geofence
from app.contracts.tracks import Track, TrackObservation

from .config import CrowdSettings, ZoneSettings
from .geometry import Area


@dataclass
class Streak:
    first: int = -1
    last: int = -2
    count: int = 0

    def clear(self) -> None:
        self.count = 0

    def add(self, frame_index: int) -> None:
        if self.count == 0 or frame_index != self.last + 1:
            self.first = frame_index
            self.count = 0
        self.count += 1
        self.last = frame_index


class Region:
    def __init__(self, fence: Geofence):
        self.fence = fence
        self.area = Area(fence.geometry.coordinates[0])

    def active(self, observation: TrackObservation, size: FrameSize) -> bool:
        if self.fence.space_type == "image":
            return self.fence.frame_size_px == size
        return observation.geo_status == "calibrated"

    def contains(self, track: Track) -> bool | None:
        if self.fence.space_type == "image":
            return self.area.covers(track.bottom_center_px)
        return self.area.covers(track.location.coordinates) if track.location else None


def candidate_key(run_id: str, rule: str, region: str | None, track_id: str | None, first_frame: int) -> str:
    return json.dumps([run_id, rule, region, track_id, first_frame], separators=(",", ":"))


class CrowdThresholdRule:
    def __init__(self, settings: CrowdSettings, region: Region | None = None):
        self.settings = settings
        self.region = region
        self._pending = Streak()
        self._latched = False
        self._next_allowed = 0

    def evaluate(self, obs: TrackObservation, size: FrameSize) -> IncidentCandidate | None:
        settings = self.settings
        if self.region and not self.region.active(obs, size):
            self._pending.clear()
            return None
        count = len({
            track.track_id for track in obs.tracks
            if track.object_class == "person" and track.detector_confidence >= settings.min_detector_confidence
            and (self.region is None or self.region.contains(track))
        })
        if count <= settings.threshold_count:
            self._pending.clear()
            if count <= settings.clear_count:
                self._latched = False
            return None
        if self._latched:
            return None
        self._pending.add(obs.frame_index)
        if self._pending.count < settings.consecutive_frames:
            return None
        self._latched = True
        if obs.video_time_ms < self._next_allowed:
            return None
        self._next_allowed = obs.video_time_ms + settings.cooldown_ms
        return IncidentCandidate(
            run_id=obs.run_id, source_id=obs.source_id, event_type="crowd_threshold",
            rule_name="crowd_count_above_threshold", video_time_ms=obs.video_time_ms,
            observed_at=obs.captured_at, location=None, horizontal_error_m=None,
            geo_status="image_roi_only" if self.region else "unavailable",
            idempotency_key=candidate_key(
                obs.run_id, "crowd_threshold", settings.region_id, None, self._pending.first
            ),
            rule_details=CrowdRuleDetails(
                trigger_frame_index=obs.frame_index, consecutive_frames=self._pending.count,
                cooldown_ms=settings.cooldown_ms, person_count=count, threshold_count=settings.threshold_count,
                clear_count=settings.clear_count, min_detector_confidence=settings.min_detector_confidence,
                region_id=settings.region_id,
            ),
        )


@dataclass
class EntryState:
    inside: bool | None = None
    last_seen: int = 0
    next_allowed: int = 0
    pending: Streak = field(default_factory=Streak)


class ZoneEntryRule:
    def __init__(self, settings: ZoneSettings, region: Region):
        self.settings = settings
        self.region = region
        self._state: dict[str, EntryState] = {}

    def evaluate(self, obs: TrackObservation, size: FrameSize) -> list[IncidentCandidate]:
        now = obs.video_time_ms
        for track_id, state in tuple(self._state.items()):
            if now - state.last_seen > self.settings.track_expiry_ms:
                if now >= state.next_allowed:
                    del self._state[track_id]
                else:
                    state.inside = None
                    state.pending.clear()
        if not self.region.active(obs, size):
            return []
        candidates = []
        tracks = {track.track_id: track for track in obs.tracks if track.object_class == "person"}
        for track in tracks.values():
            inside = self.region.contains(track)
            if inside is None:
                continue
            candidate = self._observe(obs, track, inside)
            if candidate is not None:
                candidates.append(candidate)
        return candidates

    def _observe(self, obs: TrackObservation, track: Track, inside: bool) -> IncidentCandidate | None:
        state = self._state.setdefault(track.track_id, EntryState())
        state.last_seen = obs.video_time_ms
        if not inside or state.inside is None:
            # A track first seen inside has no observed entry transition.
            state.inside = inside
            state.pending.clear()
            return None
        if state.inside:
            return None
        state.pending.add(obs.frame_index)
        if state.pending.count < self.settings.consecutive_frames:
            return None
        state.inside = True
        if obs.video_time_ms < state.next_allowed:
            return None
        state.next_allowed = obs.video_time_ms + self.settings.cooldown_ms
        fence = self.region.fence
        world = fence.space_type == "world"
        return IncidentCandidate(
            run_id=obs.run_id, source_id=obs.source_id, event_type="zone_intrusion",
            rule_name="restricted_zone_entry", video_time_ms=obs.video_time_ms, observed_at=obs.captured_at,
            location=track.location if world else None, horizontal_error_m=None,
            geo_status="calibrated" if world else "image_roi_only",
            idempotency_key=candidate_key(
                obs.run_id, "zone_intrusion", fence.id, track.track_id, state.pending.first
            ),
            rule_details=ZoneRuleDetails(
                trigger_frame_index=obs.frame_index, zone_id=fence.id, track_id=track.track_id,
                consecutive_frames=state.pending.count, cooldown_ms=self.settings.cooldown_ms,
            ),
        )
