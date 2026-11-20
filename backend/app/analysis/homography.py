from __future__ import annotations

from dataclasses import dataclass
from math import cos, degrees, radians
from typing import TYPE_CHECKING

import cv2
import numpy as np
from numpy.typing import NDArray

from app.contracts.geo import FrameSize, PixelPoint, Point

from .geometry import Area

if TYPE_CHECKING:
    from .config import FixedCalibration

EARTH_RADIUS_M = 6_378_137.0
MAX_CONTROL_RADIUS_M = 2_000
MAX_RMS_PX = 2.0
MAX_CONTROL_ERROR_PX = 4.0
Matrix = NDArray[np.float64]


def normalize(points: Matrix) -> tuple[Matrix, Matrix]:
    center = points.mean(axis=0)
    distance = np.linalg.norm(points - center, axis=1).mean()
    if distance <= 0:
        raise ValueError("control points have no spatial spread")
    scale = np.sqrt(2) / distance
    transform = np.array([[scale, 0, -scale * center[0]], [0, scale, -scale * center[1]], [0, 0, 1]])
    return (points - center) * scale, transform


def homogeneous(points: Matrix, transform: Matrix) -> Matrix:
    return np.column_stack((points, np.ones(len(points)))) @ transform.T


@dataclass(frozen=True)
class GroundProjector:
    frame_size: FrameSize
    valid_range: tuple[int, int] | None
    rms_error_px: float
    _matrix: Matrix
    _hull: Area
    _longitude: float
    _latitude: float
    _east_scale: float

    @classmethod
    def fit(cls, config: FixedCalibration) -> "GroundProjector":
        pixels = np.array(config.pixel_points, dtype=np.float64)
        world = np.array(config.geo_points, dtype=np.float64)
        lon, lat = map(float, world.mean(axis=0))
        if abs(lat) >= 85:
            raise ValueError("local ground plane requires a nonpolar site")
        east_scale = EARTH_RADIUS_M * cos(radians(lat))
        ground = np.radians(world - (lon, lat)) * (east_scale, EARTH_RADIUS_M)
        if np.linalg.norm(ground, axis=1).max() > MAX_CONTROL_RADIUS_M:
            raise ValueError("control points exceed the supported local ground plane")

        p, pixel_norm = normalize(pixels)
        g, ground_norm = normalize(ground)
        x, y = p.T
        u, v = g.T
        ones, zeros = np.ones(len(p)), np.zeros(len(p))
        design = np.column_stack((x, y, ones, zeros, zeros, zeros, -u*x, -u*y, -u))
        other = np.column_stack((zeros, zeros, zeros, x, y, ones, -v*x, -v*y, -v))
        singular = np.linalg.svd(np.vstack((design, other)), compute_uv=False)
        if singular[7] < 1e-4 * singular[0]:
            raise ValueError("control correspondence is degenerate or ill-conditioned")
        matrix, _ = cv2.findHomography(p, g, method=0)
        if matrix is None or not np.isfinite(matrix).all() or np.linalg.cond(matrix) > 1e5:
            raise ValueError("homography is singular or ill-conditioned")
        denominators = homogeneous(p, matrix)[:, 2]
        if not (np.all(denominators > 1e-6) or np.all(denominators < -1e-6)):
            raise ValueError("the homography has a horizon inside the control region")
        transform = np.linalg.inv(ground_norm) @ matrix @ pixel_norm
        reconstructed = homogeneous(ground, np.linalg.inv(transform))
        residuals = np.linalg.norm(reconstructed[:, :2] / reconstructed[:, 2:] - pixels, axis=1)
        rms = float(np.sqrt(np.mean(residuals**2)))
        if not np.isfinite(residuals).all() or rms > MAX_RMS_PX or residuals.max() > MAX_CONTROL_ERROR_PX:
            raise ValueError("control reprojection error exceeds the pixel tolerance")
        indices = cv2.convexHull(pixels.astype(np.float32), returnPoints=False).ravel()
        if len(indices) < 3:
            raise ValueError("calibration has no usable pixel hull")
        ring = [config.pixel_points[index] for index in indices]
        return cls(config.frame_size_px, config.valid_for_frame_range, rms, transform,
                   Area(ring + ring[:1]), lon, lat, east_scale)

    def applies(self, frame_size: FrameSize, index: int) -> bool:
        return frame_size == self.frame_size and (
            self.valid_range is None or self.valid_range[0] <= index <= self.valid_range[1]
        )

    def project(self, pixel: PixelPoint) -> Point | None:
        if not self._hull.covers(pixel):
            return None
        east, north, depth = self._matrix @ (*pixel, 1.0)
        if abs(depth) < 1e-12:
            return None
        lon = self._longitude + degrees(east / depth / self._east_scale)
        lat = self._latitude + degrees(north / depth / EARTH_RADIUS_M)
        if not (-180 <= lon <= 180 and -90 <= lat <= 90):
            return None
        return Point(type="Point", coordinates=(lon, lat))
