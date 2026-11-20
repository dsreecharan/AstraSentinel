from typing import Literal, Self

from pydantic import StrictFloat, model_validator

from .common import Confidence, ContractModel, NonemptyString, NonnegativeFloat, NonnegativeInt, UtcTimestamp
from .geo import GeoStatus, PixelPoint, Point


class Track(ContractModel):
    track_id: NonemptyString
    object_class: Literal["person", "vehicle"]
    detector_confidence: Confidence
    bbox_xyxy: tuple[StrictFloat, StrictFloat, StrictFloat, StrictFloat]
    bottom_center_px: PixelPoint
    location: Point | None
    horizontal_error_m: NonnegativeFloat | None

    @model_validator(mode="after")
    def validate_track(self) -> Self:
        left, top, right, bottom = self.bbox_xyxy
        if left >= right or top >= bottom:
            raise ValueError("bbox_xyxy must have positive width and height")
        if self.location is None and self.horizontal_error_m is not None:
            raise ValueError("horizontal uncertainty requires a world location")
        return self


class TrackObservation(ContractModel):
    schema_version: Literal["1.0"]
    run_id: NonemptyString
    source_id: NonemptyString
    frame_index: NonnegativeInt
    video_time_ms: NonnegativeInt
    captured_at: UtcTimestamp | None
    processed_at: UtcTimestamp
    mode: Literal["replay"]
    geo_status: GeoStatus
    tracks: list[Track]

    @model_validator(mode="after")
    def validate_tracks(self) -> Self:
        prefix = f"{self.run_id}:"
        for track in self.tracks:
            if not track.track_id.startswith(prefix) or track.track_id == prefix:
                raise ValueError("track ID must be scoped to the observation's run")
            if self.geo_status != "calibrated" and track.location is not None:
                raise ValueError("track locations require a calibrated frame")
        return self
