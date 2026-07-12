"""The OpenAQ real-sensor adapter: the pure mapping from /latest results to observations.

The live fetch needs an API key and a network, so it is not unit-tested; these tests exercise the
deterministic mapping with hand-built OpenAQ-v3-shaped payloads — including the honesty-critical bit
that real-but-uncalibrated sensors stay RAW (→ provisional).
"""

from __future__ import annotations

from typing import Any

from swelter.models import RAW, Observation
from swelter.sources import openaq


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


def test_network_doc_marks_uncalibrated() -> None:
    doc = openaq.network_doc("California", {"oaq-5": ("Downtown LA", 34.05, -118.24)})
    node = doc["nodes"][0]
    assert node["location"] == "precise"  # real sensor coordinates
    assert doc["calibration_windows"] == []  # real, but not swelter-calibrated
    assert "OpenAQ" in doc["name"]


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
