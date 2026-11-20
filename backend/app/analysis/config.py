from functools import cached_property
from pathlib import Path
from typing import Annotated, Literal, Self

import cv2
import numpy as np
from pydantic import Field, StrictBool, model_validator

from app.contracts.common import Confidence, ContractModel, NonemptyString, NonnegativeInt, PositiveInt, Sha256
from app.contracts.geo import FrameSize, PixelPoint, WorldPosition

from .homography import GroundProjector


class CrowdSettings(ContractModel):
    threshold_count: PositiveInt
    clear_count: NonnegativeInt
    consecutive_frames: PositiveInt = 3
    min_detector_confidence: Confidence = 0.25
    cooldown_ms: NonnegativeInt = 5000
    region_id: NonemptyString | None = None

    @model_validator(mode="after")
    def validate_hysteresis(self) -> Self:
        if self.clear_count >= self.threshold_count:
            raise ValueError("clear_count must be below threshold_count")
        return self


class ZoneSettings(ContractModel):
    consecutive_frames: PositiveInt = 3
    cooldown_ms: NonnegativeInt = 5000
    track_expiry_ms: PositiveInt = 2000


class FixedCalibration(ContractModel):
    camera: Literal["fixed"]
    video_sha256: Sha256
    frame_size_px: FrameSize
    pixel_points: Annotated[list[PixelPoint], Field(min_length=4)]
    geo_points: Annotated[list[WorldPosition], Field(min_length=4)]
    valid_for_frame_range: tuple[NonnegativeInt, NonnegativeInt] | None = None

    @model_validator(mode="after")
    def validate_controls(self) -> Self:
        width, height = self.frame_size_px
        if any(not (0 <= x <= width and 0 <= y <= height) for x, y in self.pixel_points):
            raise ValueError("pixel control points must fit the reference frame")
        if len(self.pixel_points) != len(self.geo_points):
            raise ValueError("pixel and geographic control points must be paired")
        if len(set(self.pixel_points)) != len(self.pixel_points) or len(set(self.geo_points)) != len(self.geo_points):
            raise ValueError("control points must be distinct in both coordinate spaces")
        if self.valid_for_frame_range and self.valid_for_frame_range[0] > self.valid_for_frame_range[1]:
            raise ValueError("calibration frame range is reversed")
        return self


class SourceAnalysis(ContractModel):
    crowd: CrowdSettings | None = None
    zone: ZoneSettings = Field(default_factory=ZoneSettings)
    calibration: FixedCalibration | None = None
    retain_thumbnails: StrictBool = False

    @cached_property
    def projector(self) -> GroundProjector | None:
        return GroundProjector.fit(self.calibration) if self.calibration else None


class AnalysisSettings(ContractModel):
    sources: dict[NonemptyString, SourceAnalysis] = Field(default_factory=dict)

    @classmethod
    def read(cls, path: Path) -> Self:
        settings = cls.model_validate_json(path.read_bytes())
        for source_id, source in settings.sources.items():
            try:
                _ = source.projector
            except (ValueError, cv2.error, np.linalg.LinAlgError) as error:
                raise ValueError(f"Invalid fixed-scene calibration for source {source_id}: {error}") from None
        return settings
