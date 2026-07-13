"""The OpenAQ real-sensor adapter: the pure mapping from /latest results to observations.

The live fetch needs an API key and a network, so it is not unit-tested; these tests exercise the
deterministic mapping with hand-built OpenAQ-v3-shaped payloads — including the honesty-critical bit
that real-but-uncalibrated sensors stay RAW (→ provisional).
"""

from __future__ import annotations

from typing import Any

import pytest

from swelter.models import RAW, Observation
from swelter.sources import _california_boundary as california_boundary
from swelter.sources import openaq
from swelter.sources._geometry import contains_point, decode_multipolygon


def _row(sid: int, value: float, when: str = "2026-06-17T23:00:00Z") -> dict[str, Any]:
    return {"sensorsId": sid, "value": value, "datetime": {"utc": when}}


SENSOR_PARAM = {
    1: ("pm25_ugm3", "ug/m3"),
    2: ("temp_c", "degC"),
    3: ("humidity_pct", "%"),
}


def test_parse_latest_maps_and_stays_raw() -> None:
    obs = openaq.parse_latest("oaq-7", [_row(1, 12.3), _row(2, 28.0), _row(3, 40.0)], SENSOR_PARAM)
    params = {o.parameter for o in obs}
    # + derived heat index and estimated WBGT
    assert params == {"pm25_ugm3", "temp_c", "humidity_pct", "heat_index_c", "wbgt_c"}
    assert all(o.calibration == RAW for o in obs)  # real, but not swelter-calibrated → provisional
    assert all(o.node_id == "oaq-7" for o in obs)
    assert all(o.timestamp.endswith("Z") for o in obs)
    pm = next(o for o in obs if o.parameter == "pm25_ugm3")
    assert pm.value == 12.3 and pm.unit == "ug/m3"


def test_parse_latest_skips_unknown_or_null() -> None:
    rows = [
        _row(99, 5.0),  # sensor not in the parameter map
        {"sensorsId": 1, "value": None, "datetime": {"utc": "2026-06-17T23:00:00Z"}},  # null value
        {"sensorsId": 1, "value": 9.0},  # no datetime
    ]
    assert openaq.parse_latest("oaq-1", rows, SENSOR_PARAM) == []


def test_sensor_parameters_indexes_by_sensor_id() -> None:
    locations = [
        {
            "id": 5,
            "sensors": [
                {"id": 10, "parameter": {"name": "pm25", "units": "ug/m3"}},
                {"id": 11, "parameter": {"name": "co", "units": "ppm"}},  # not a swelter parameter
            ],
        }
    ]
    sp = openaq._sensor_parameters(locations)
    assert sp == {10: ("pm25_ugm3", "ug/m3")}  # co dropped, pm25 mapped


def test_network_doc_marks_uncalibrated_coarse_and_california_only() -> None:
    doc = openaq.network_doc(
        "California",
        {
            "oaq-5": ("Downtown LA", 34.05, -118.24),
            "oaq-6": ("Yuma", 32.6927, -114.6277),
        },
    )
    node = doc["nodes"][0]
    assert [candidate["node_id"] for candidate in doc["nodes"]] == ["oaq-5"]
    assert node["location"] == "coarse"  # upstream publication is not swelter host consent
    assert doc["calibration_windows"] == []  # real, but not swelter-calibrated
    assert doc["geographic_scope"]["id"] == "US-CA"
    assert "OpenAQ" in doc["name"]


@pytest.mark.parametrize(
    ("name", "lat", "lon", "expected"),
    [
        ("Sacramento", 38.5816, -121.4944, True),
        ("South Lake Tahoe", 38.9399, -119.9772, True),
        ("Avalon on Santa Catalina Island", 33.3428, -118.3278, True),
        ("Yuma, Arizona", 32.6927, -114.6277, False),
        ("Sparks, Nevada", 39.5349, -119.7527, False),
        ("Brookings, Oregon", 42.0526, -124.2839, False),
    ],
)
def test_california_boundary_rejects_bbox_spillover(
    name: str, lat: float, lon: float, expected: bool
) -> None:
    assert california_boundary.contains(lat, lon) is expected, name


def test_multipolygon_holes_and_boundaries() -> None:
    geometry = decode_multipolygon(
        {
            "type": "MultiPolygon",
            "coordinates": [
                [
                    [[0, 0], [4, 0], [4, 4], [0, 4], [0, 0]],
                    [[2, 2], [3, 2], [3, 3], [2, 3], [2, 2]],
                ],
                [[[10, 10], [11, 10], [11, 11], [10, 11], [10, 10]]],
            ],
        }
    )
    assert contains_point(geometry, 1.0, 1.0)  # first polygon interior
    assert not contains_point(geometry, 2.5, 2.5)  # hole interior is excluded
    assert contains_point(geometry, 2.0, 2.5)  # hole boundary belongs to the polygon boundary
    assert contains_point(geometry, 0.0, 1.0)  # exterior boundary is included
    assert contains_point(geometry, 10.5, 10.5)  # second polygon is included
    assert not contains_point(geometry, 8.0, 8.0)
    assert not contains_point(geometry, float("nan"), 1.0)


@pytest.mark.parametrize(
    "geometry",
    [
        None,
        {"type": "Polygon", "coordinates": []},
        {"type": "MultiPolygon", "coordinates": []},
        {"type": "MultiPolygon", "coordinates": [[]]},
        {"type": "MultiPolygon", "coordinates": [[None]]},
        {"type": "MultiPolygon", "coordinates": [[[[0]]]]},
        {
            "type": "MultiPolygon",
            "coordinates": [[[[0, 0], [1, 0], [1, 1], [0, 1]]]],
        },
        {
            "type": "MultiPolygon",
            "coordinates": [[[[True, 0], [1, 0], [1, 1], [True, 0]]]],
        },
        {
            "type": "MultiPolygon",
            "coordinates": [[[[float("inf"), 0], [1, 0], [1, 1], [float("inf"), 0]]]],
        },
    ],
)
def test_multipolygon_decoder_rejects_malformed_geometry(geometry: object) -> None:
    with pytest.raises(ValueError):
        decode_multipolygon(geometry)


def test_california_boundary_rejects_non_finite_coordinates() -> None:
    assert not california_boundary.contains(float("nan"), -121.49)
    assert not california_boundary.contains(38.58, float("inf"))


def test_california_boundary_includes_points_on_its_actual_edge() -> None:
    lon, lat = california_boundary._boundary()[0][0][0]
    assert california_boundary.contains(lat, lon)


@pytest.mark.parametrize(
    "location",
    [
        {},
        {"coordinates": []},
        {"coordinates": {"latitude": 38.5}},
        {"coordinates": {"latitude": "invalid", "longitude": -121.5}},
        {"coordinates": {"latitude": float("nan"), "longitude": -121.5}},
    ],
)
def test_openaq_coordinates_reject_malformed_or_non_finite(location: dict[str, Any]) -> None:
    assert openaq._coordinates(location) is None


def _pm(node: str, ts: str, value: float) -> Observation:
    return Observation(node_id=node, timestamp=ts, parameter="pm25_ugm3", value=value, unit="ug/m3")


def test_to_snapshot_collapses_to_one_hour_and_drops_stale() -> None:
    # /latest readings arrive on each sensor's own clock; the snapshot collapses the live ones to
    # one hour (so the whole network shows at once) and drops anything staler than the window.
    obs = [
        _pm("oaq-1", "2026-06-17T21:50:00Z", 10.0),
        _pm("oaq-2", "2026-06-17T21:05:00Z", 20.0),
        _pm("oaq-3", "2026-06-17T10:00:00Z", 99.0),  # >6h older than newest → dropped
    ]
    snap = openaq._to_snapshot(obs)
    assert {o.timestamp for o in snap} == {"2026-06-17T21:00:00Z"}  # all on the newest hour
    assert {o.node_id for o in snap} == {"oaq-1", "oaq-2"}  # the stale site is gone
