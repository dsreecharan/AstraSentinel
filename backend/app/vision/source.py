from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from typing import Protocol, Self

import cv2
import numpy as np
from numpy.typing import NDArray

from app.media import file_sha256, resolve_mp4

from .errors import ReplayError

Image = NDArray[np.uint8]


@dataclass(frozen=True)
class VideoFrame:
    image: Image
    frame_index: int
    video_time_ms: int


class VideoSource(Protocol):
    @property
    def source_fps(self) -> float | None: ...

    def __enter__(self) -> Self: ...
    def __exit__(self, *exc_info: object) -> None: ...
    def read(self) -> VideoFrame | None: ...


class OpenCVVideoSource:
    def __init__(self, media_root: Path, name: Path, expected_sha256: str):
        self._media_root = media_root
        self._name = name
        self._expected_sha256 = expected_sha256
        self._capture: cv2.VideoCapture | None = None
        self.source_fps: float | None = None
        self._declared_frames = 0
        self._index = 0
        self._first_pts: float | None = None
        self._previous_time_ms = 0.0
        self._fps_clock = False

    def __enter__(self) -> Self:
        if self._capture is not None:
            raise RuntimeError("The video source is already open")
        try:
            path = resolve_mp4(self._media_root, self._name)
            digest = file_sha256(path)
        except (OSError, RuntimeError, ValueError) as error:
            raise ReplayError("video_unavailable", "The registered MP4 is missing or outside the media directory") from error
        if digest != self._expected_sha256:
            raise ReplayError("video_changed", "The MP4 checksum differs from the registered source")

        try:
            self._capture = cv2.VideoCapture(str(path), cv2.CAP_FFMPEG)
            if not self._capture.isOpened():
                raise ReplayError("decode_failed", "OpenCV could not open the MP4. Check for a damaged file or unsupported codec.")
            fps = self._capture.get(cv2.CAP_PROP_FPS)
            self.source_fps = fps if isfinite(fps) and fps > 0 else None
            frames = self._capture.get(cv2.CAP_PROP_FRAME_COUNT)
            self._declared_frames = int(frames) if isfinite(frames) and frames > 0 else 0
            self._index = 0
            self._first_pts = None
            self._previous_time_ms = 0.0
            self._fps_clock = False
            return self
        except cv2.error as error:
            self.__exit__()
            raise ReplayError("decode_failed", "OpenCV could not initialize the MP4 decoder") from error
        except ReplayError:
            self.__exit__()
            raise

    def __exit__(self, *exc_info: object) -> None:
        if self._capture is not None:
            self._capture.release()
            self._capture = None

    def read(self) -> VideoFrame | None:
        capture = self._capture
        if capture is None:
            raise RuntimeError("Open the video source before reading frames")
        try:
            ok, image = capture.read()
            if ok and image is not None and image.size:
                frame = VideoFrame(image, self._index, self._timecode(capture.get(cv2.CAP_PROP_POS_MSEC)))
                self._index += 1
                return frame
        except cv2.error as error:
            raise ReplayError("decode_failed", "OpenCV failed while decoding a replay frame") from error
        if self._index == 0 or self._index < self._declared_frames:
            raise ReplayError("decode_failed", "The MP4 could not be decoded through its declared frame count")
        return None

    def _timecode(self, pts_ms: float) -> int:
        if not self._fps_clock and isfinite(pts_ms) and pts_ms >= 0:
            if self._first_pts is None:
                self._first_pts = pts_ms
            relative = pts_ms - self._first_pts
            if self._index == 0 or relative > self._previous_time_ms:
                self._previous_time_ms = relative
                return round(relative)

        if self.source_fps is None:
            raise ReplayError("timebase_unavailable", "The MP4 has no usable frame timestamps or FPS")
        self._fps_clock = True
        self._previous_time_ms = max(self._previous_time_ms, self._index * 1000 / self.source_fps)
        return round(self._previous_time_ms)
