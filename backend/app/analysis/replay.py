from dataclasses import dataclass

from app.contracts.events import IncidentCandidate
from app.contracts.geo import FrameSize, Geofence
from app.contracts.tracks import TrackObservation

from .config import SourceAnalysis
from .rules import CrowdThresholdRule, Region, ZoneEntryRule


@dataclass(frozen=True)
class AnalysisResult:
    observation: TrackObservation
    candidates: list[IncidentCandidate]
    image_regions: list[Geofence]


class ReplayAnalysis:
    def __init__(self, run_id: str, sha256: str, settings: SourceAnalysis, fences: tuple[Geofence, ...]):
        self._run_id = run_id
        self.retain_thumbnails = settings.retain_thumbnails
        self._regions = {fence.id: Region(fence) for fence in fences if fence.enabled}
        self._zone_rules = [ZoneEntryRule(settings.zone, region) for region in self._regions.values()]
        self._crowd = None
        if settings.crowd:
            region_id = settings.crowd.region_id
            region = self._regions.get(region_id) if region_id is not None else None
            if region_id is not None and (region is None or region.fence.space_type != "image"):
                raise ValueError("crowd region must be an enabled image geofence for this source")
            self._crowd = CrowdThresholdRule(settings.crowd, region)
        if settings.calibration and settings.calibration.video_sha256 != sha256:
            raise ValueError("calibration checksum does not match the registered footage")
        self.projector = settings.projector

    def process(self, observation: TrackObservation, size: FrameSize) -> AnalysisResult:
        if observation.run_id != self._run_id:
            raise ValueError("rule state belongs to a different run")
        image_regions = [
            region.fence for region in self._regions.values()
            if region.fence.space_type == "image" and region.fence.frame_size_px == size
        ]
        projector = self.projector if self.projector and self.projector.applies(size, observation.frame_index) else None
        geo_status = "calibrated" if projector else ("image_roi_only" if image_regions else "unavailable")
        observation = observation.model_copy(update={
            "geo_status": geo_status,
            "tracks": [track.model_copy(update={
                "location": projector.project(track.bottom_center_px) if projector else None,
                "horizontal_error_m": None,
            }) for track in observation.tracks],
        })

        candidates = []
        if self._crowd:
            candidate = self._crowd.evaluate(observation, size)
            if candidate is not None:
                candidates.append(candidate)
        for rule in self._zone_rules:
            candidates.extend(rule.evaluate(observation, size))
        return AnalysisResult(observation, candidates, image_regions)
