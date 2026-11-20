from dataclasses import dataclass
from threading import Lock

import cv2
import numpy as np

from app.contracts.geo import Geofence
from app.media import MAX_THUMBNAIL_BYTES

from .engine import Detection
from .errors import ReplayError
from .source import Image


@dataclass(frozen=True)
class JpegFrame:
    run_id: str
    frame_index: int
    jpeg: bytes


class LatestFrameStore:
    def __init__(self):
        self._lock = Lock()
        self._frame: JpegFrame | None = None

    def replace(self, frame: JpegFrame | None) -> None:
        with self._lock:
            self._frame = frame

    def get(self) -> JpegFrame | None:
        with self._lock:
            return self._frame


def annotate_frame(
    image: Image, detections: list[Detection], image_regions: list[Geofence], candidate_count: int,
) -> Image:
    annotated = image.copy()
    for region in image_regions:
        ring = np.rint(region.geometry.coordinates[0]).astype(np.int32)
        cv2.polylines(annotated, [ring], True, (24, 182, 247), 2)
        x, y = map(int, ring[0])
        cv2.putText(annotated, "IMAGE ROI", (x, max(42, y)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (24, 182, 247), 1)
    for detection in detections:
        left, top, right, bottom = map(round, detection.bbox_xyxy)
        label = detection.object_class
        if detection.track_id is not None:
            label += f" #{detection.track_id.rsplit(':', 1)[-1]}"
        label += f" {detection.detector_confidence:.2f}"
        cv2.rectangle(annotated, (left, top), (right, bottom), (75, 223, 160), 2)
        cv2.putText(annotated, label, (left, max(15, top - 5)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (75, 223, 160), 1)
    cv2.rectangle(annotated, (0, 0), (149, 24), (20, 20, 20), cv2.FILLED)
    cv2.putText(annotated, "REPLAY SOURCE", (6, 17), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (255, 255, 255), 1, cv2.LINE_AA)
    if candidate_count:
        cv2.rectangle(annotated, (0, 48), (290, 71), (20, 20, 20), cv2.FILLED)
        cv2.putText(annotated, f"REVIEW CANDIDATE x{candidate_count}", (6, 65),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.48, (24, 182, 247), 1, cv2.LINE_AA)
    return annotated


def frame_jpeg(annotated: Image) -> bytes:
    ok, jpeg = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 82])
    if not ok:
        raise ReplayError("stream_encode_failed", "Could not encode the annotated replay frame")
    return jpeg.tobytes()


def evidence_thumbnail(annotated: Image) -> bytes | None:
    scale = min(1.0, 640 / max(annotated.shape[:2]))
    try:
        image = cv2.resize(annotated, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA) if scale < 1 else annotated
        ok, jpeg = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 72])
    except cv2.error:
        return None
    return jpeg.tobytes() if ok and jpeg.size <= MAX_THUMBNAIL_BYTES else None
