from dataclasses import dataclass
from typing import Literal, Protocol

from app.contracts.events import ModelProvenance

from .source import Image

Box = tuple[float, float, float, float]


@dataclass(frozen=True)
class Detection:
    object_class: Literal["person", "vehicle"]
    bbox_xyxy: Box
    detector_confidence: float
    track_id: str | None


class VisionEngine(Protocol):
    def start_run(self, run_id: str) -> ModelProvenance: ...
    def track(self, image: Image) -> list[Detection]: ...
