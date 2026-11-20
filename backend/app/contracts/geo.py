from fractions import Fraction
from itertools import combinations, pairwise
from typing import Annotated, Literal, Self

from pydantic import Field, StrictBool, StrictFloat, model_validator

from .common import ContractModel, NonemptyString, NonnegativeFloat, NonnegativeInt, PositiveInt

GeoStatus = Literal["calibrated", "image_roi_only", "unavailable"]
PixelPoint = tuple[StrictFloat, StrictFloat]
Longitude = Annotated[float, Field(strict=True, ge=-180, le=180)]
Latitude = Annotated[float, Field(strict=True, ge=-90, le=90)]
WorldPosition = tuple[Longitude, Latitude]
FrameSize = tuple[PositiveInt, PositiveInt]
ExactPoint = tuple[Fraction, Fraction]


def orientation(a: ExactPoint, b: ExactPoint, c: ExactPoint) -> Fraction:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def segments_intersect(a: ExactPoint, b: ExactPoint, c: ExactPoint, d: ExactPoint) -> bool:
    if any(max(a[i], b[i]) < min(c[i], d[i]) or max(c[i], d[i]) < min(a[i], b[i]) for i in (0, 1)):
        return False
    abc, abd = orientation(a, b, c), orientation(a, b, d)
    cda, cdb = orientation(c, d, a), orientation(c, d, b)
    return min(abc, abd) <= 0 <= max(abc, abd) and min(cda, cdb) <= 0 <= max(cda, cdb)


class Point(ContractModel):
    type: Literal["Point"]
    coordinates: WorldPosition


class Polygon(ContractModel):
    type: Literal["Polygon"]
    coordinates: tuple[Annotated[list[PixelPoint], Field(min_length=4)]]

    @model_validator(mode="after")
    def validate_ring(self) -> Self:
        (ring,) = self.coordinates
        if ring[0] != ring[-1] or len(set(ring[:-1])) != len(ring) - 1:
            raise ValueError("polygon requires a closed ring without repeated exterior vertices")

        # Exact predicates preserve the topology of the supplied coordinates, including tiny world ROIs.
        points = [(Fraction(x), Fraction(y)) for x, y in ring]
        edges = list(pairwise(points))
        area_twice = sum(orientation(points[0], a, b) for a, b in edges)
        if area_twice == 0:
            raise ValueError("polygon ring must have nonzero area")
        for (i, (a, b)), (j, (c, d)) in combinations(enumerate(edges), 2):
            if j == i + 1 or (i == 0 and j == len(edges) - 1):
                continue
            if segments_intersect(a, b, c, d):
                raise ValueError("polygon ring must be simple")
        return self


class GeofenceInput(ContractModel):
    source_id: NonemptyString
    label: NonemptyString
    space_type: Literal["world", "image"]
    enabled: StrictBool
    geometry: Polygon
    frame_size_px: FrameSize | None

    @model_validator(mode="after")
    def validate_space(self) -> Self:
        (ring,) = self.geometry.coordinates
        if not self.label.strip():
            raise ValueError("label must contain text")
        if self.space_type == "world":
            if self.frame_size_px is not None:
                raise ValueError("world polygons require a null frame size")
            if any(not (-180 <= lon <= 180 and -90 <= lat <= 90) for lon, lat in ring):
                raise ValueError("world polygon positions must be longitude and latitude")
        else:
            if self.frame_size_px is None:
                raise ValueError("image polygons require a reference frame size")
            width, height = self.frame_size_px
            if any(not (0 <= x <= width and 0 <= y <= height) for x, y in ring):
                raise ValueError("image polygon positions must fit inside the reference frame")
        return self


class Geofence(GeofenceInput):
    id: NonemptyString


class Calibration(ContractModel):
    id: NonemptyString
    source_id: NonemptyString
    method: Literal["homography"]
    frame_size_px: FrameSize
    pixel_points: Annotated[list[PixelPoint], Field(min_length=4)]
    geo_points: Annotated[list[WorldPosition], Field(min_length=4)]
    reprojection_error_px: NonnegativeFloat
    valid_for_frame_range: tuple[NonnegativeInt, NonnegativeInt] | None

    @model_validator(mode="after")
    def validate_correspondences(self) -> Self:
        if len(self.pixel_points) != len(self.geo_points):
            raise ValueError("each pixel control point requires a matching world point")
        if min(len(set(self.pixel_points)), len(set(self.geo_points))) < 4:
            raise ValueError("at least four distinct control points are required in each space")
        if self.valid_for_frame_range is not None:
            first, last = self.valid_for_frame_range
            if first > last:
                raise ValueError("first frame index must be at or before the last frame index")
        return self
