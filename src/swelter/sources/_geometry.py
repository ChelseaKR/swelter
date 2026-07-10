"""Small, dependency-free GeoJSON polygon predicates used by source adapters.

Coordinates follow GeoJSON order: longitude first, latitude second. Polygon boundary points are
included. For holes, the hole interior is excluded while the hole's boundary remains part of the
polygon boundary.
"""

from __future__ import annotations

import math
from enum import IntEnum

type Position = tuple[float, float]
type Ring = tuple[Position, ...]
type Polygon = tuple[Ring, ...]
type MultiPolygon = tuple[Polygon, ...]

_EPSILON = 1e-10


class _RingLocation(IntEnum):
    OUTSIDE = 0
    INSIDE = 1
    BOUNDARY = 2


def _position(value: object) -> Position:
    if not isinstance(value, list) or len(value) < 2:
        raise ValueError("GeoJSON position must contain longitude and latitude")
    lon, lat = value[0], value[1]
    if (
        isinstance(lon, bool)
        or isinstance(lat, bool)
        or not isinstance(lon, (int, float))
        or not isinstance(lat, (int, float))
    ):
        raise ValueError("GeoJSON longitude and latitude must be numbers")
    point = (float(lon), float(lat))
    if not all(math.isfinite(coordinate) for coordinate in point):
        raise ValueError("GeoJSON coordinates must be finite")
    return point


def _ring(value: object) -> Ring:
    if not isinstance(value, list):
        raise ValueError("GeoJSON linear ring must be an array")
    ring = tuple(_position(point) for point in value)
    if len(ring) < 4 or ring[0] != ring[-1]:
        raise ValueError("GeoJSON linear ring must be closed and contain at least four positions")
    return ring


def _polygon(value: object) -> Polygon:
    if not isinstance(value, list) or not value:
        raise ValueError("GeoJSON polygon must contain an exterior ring")
    return tuple(_ring(ring) for ring in value)


def decode_multipolygon(value: object) -> MultiPolygon:
    """Validate and decode a GeoJSON MultiPolygon geometry into immutable tuples."""
    if not isinstance(value, dict) or value.get("type") != "MultiPolygon":
        raise ValueError("expected a GeoJSON MultiPolygon geometry")
    coordinates = value.get("coordinates")
    if not isinstance(coordinates, list) or not coordinates:
        raise ValueError("GeoJSON MultiPolygon must contain at least one polygon")
    return tuple(_polygon(polygon) for polygon in coordinates)


def _on_segment(point: Position, start: Position, end: Position) -> bool:
    px, py = point
    ax, ay = start
    bx, by = end
    dx, dy = bx - ax, by - ay
    cross = (px - ax) * dy - (py - ay) * dx
    scale = max(1.0, abs(dx), abs(dy))
    if abs(cross) > _EPSILON * scale:
        return False
    return (
        min(ax, bx) - _EPSILON <= px <= max(ax, bx) + _EPSILON
        and min(ay, by) - _EPSILON <= py <= max(ay, by) + _EPSILON
    )


def _classify_ring(point: Position, ring: Ring) -> _RingLocation:
    inside = False
    previous = ring[-1]
    px, py = point
    for current in ring:
        if _on_segment(point, previous, current):
            return _RingLocation.BOUNDARY
        ax, ay = previous
        bx, by = current
        if (ay > py) != (by > py):
            crossing_x = ax + (py - ay) * (bx - ax) / (by - ay)
            if px < crossing_x:
                inside = not inside
        previous = current
    return _RingLocation.INSIDE if inside else _RingLocation.OUTSIDE


def _contains_polygon(point: Position, polygon: Polygon) -> bool:
    exterior = _classify_ring(point, polygon[0])
    if exterior == _RingLocation.BOUNDARY:
        return True
    if exterior == _RingLocation.OUTSIDE:
        return False
    for hole in polygon[1:]:
        hole_location = _classify_ring(point, hole)
        if hole_location == _RingLocation.BOUNDARY:
            return True
        if hole_location == _RingLocation.INSIDE:
            return False
    return True


def contains_point(geometry: MultiPolygon, longitude: float, latitude: float) -> bool:
    """Return whether a finite point is inside or on the boundary of a MultiPolygon."""
    if not math.isfinite(longitude) or not math.isfinite(latitude):
        return False
    point = (longitude, latitude)
    return any(_contains_polygon(point, polygon) for polygon in geometry)
