from fractions import Fraction
from itertools import pairwise

from app.contracts.geo import ExactPoint, PixelPoint, orientation


class Area:
    def __init__(self, closed_ring: list[PixelPoint]):
        self._edges = tuple(pairwise((Fraction(x), Fraction(y)) for x, y in closed_ring))

    def covers(self, point: PixelPoint) -> bool:
        x, y = point
        exact: ExactPoint = (Fraction(x), Fraction(y))
        inside = False
        for a, b in self._edges:
            side = orientation(a, b, exact)
            if side == 0 and min(a[0], b[0]) <= x <= max(a[0], b[0]) and min(a[1], b[1]) <= y <= max(a[1], b[1]):
                return True
            if (a[1] > y) != (b[1] > y) and (side > 0) == (b[1] > a[1]):
                inside = not inside
        return inside
