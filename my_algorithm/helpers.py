"""Geometry helpers for constraint/obstacle collision checks."""
import math
from aerohacks.core.models import Position2D


def distance(a: Position2D, b: Position2D) -> float:
    return math.hypot(b.x - a.x, b.y - a.y)


def point_in_circle(px: float, py: float, cx: float, cy: float, r: float) -> bool:
    return (px - cx) ** 2 + (py - cy) ** 2 <= r * r


def point_in_polygon(px: float, py: float, vertices) -> bool:
    inside = False
    n = len(vertices)
    if n < 3:
        return False
    j = n - 1
    for i in range(n):
        xi, yi = vertices[i].x, vertices[i].y
        xj, yj = vertices[j].x, vertices[j].y
        if ((yi > py) != (yj > py)) and (px < (xj - xi) * (py - yi) / ((yj - yi) + 1e-12) + xi):
            inside = not inside
        j = i
    return inside


def point_in_region(px: float, py: float, region) -> bool:
    """Check if point (px,py) is inside a region (circle or polygon)."""
    center = getattr(region, "center_pos", None)
    radius = getattr(region, "radius", None)
    if center is not None and radius is not None:
        return point_in_circle(px, py, center.x, center.y, float(radius))
    vertices = getattr(region, "vertices", None)
    if vertices:
        return point_in_polygon(px, py, vertices)
    return False


def point_hits_constraint(px: float, py: float, constraint, alt_layer: int) -> bool:
    """Check if point is inside a constraint at the given altitude layer."""
    layers = getattr(constraint, "alt_layers", None)
    if layers and alt_layer not in layers:
        return False
    region = getattr(constraint, "region", None)
    if region is None:
        return False
    return point_in_region(px, py, region)


def is_point_safe(px: float, py: float, constraints, alt_layer: int) -> bool:
    """Check if a point is free of all constraints at the given altitude."""
    for c in constraints:
        if point_hits_constraint(px, py, c, alt_layer):
            return False
    return True
