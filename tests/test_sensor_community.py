"""The Sensor.Community real-sensor adapter: the pure mapping from API rows to observations.

The live area fetch is not unit-tested (flaky, hits a live network); these tests exercise the
deterministic mapping with hand-built Sensor.Community-shaped payloads — including the things that
matter for honesty: readings stay RAW (uncalibrated community sensors → provisional), and a sensor
that reports twice collapses to its latest measurement.
"""

from __future__ import annotations

from swelter.models import RAW
from swelter.sources import sensor_community


def _row(
    sid: int, ts: str, *, p2: str, p1: str, temp: str, humid: str, sensor_type: str = ""
) -> dict[str, object]:
    sensor: dict[str, object] = {"id": sid}
    if sensor_type:
        sensor["sensor_type"] = {"name": sensor_type}
    return {
        "sensor": sensor,
        "timestamp": ts,
        "location": {"latitude": "48.7758", "longitude": "9.1829"},
        "sensordatavalues": [
            {"value_type": "P2", "value": p2},
            {"value_type": "P1", "value": p1},
            {"value_type": "temperature", "value": temp},
            {"value_type": "humidity", "value": humid},
        ],
    }


def test_parse_maps_values_as_raw() -> None:
    obs, nodes = sensor_community.parse_measurements(
        [_row(123, "2026-06-17 23:00:00", p2="12.3", p1="20.0", temp="28.1", humid="40.0")]
    )
    assert nodes == {"sc-123": ("Sensor 123", 48.7758, 9.1829, "")}
    assert {o.parameter for o in obs} == {
        "pm25_ugm3",
        "pm10_ugm3",
        "temp_c",
        "humidity_pct",
        "heat_index_c",
        "wbgt_c",
    }
    # Honesty: community low-cost sensors are uncalibrated, so every value stays RAW (provisional).
    assert all(o.calibration == RAW for o in obs)
    assert all(o.timestamp.endswith("Z") for o in obs)  # "2026-... ..." normalised to canonical UTC
    pm = next(o for o in obs if o.parameter == "pm25_ugm3")
    assert pm.value == 12.3 and pm.unit == "ug/m3"


def test_parse_drops_sds011_over_range_sentinel() -> None:
    # An SDS011 reporting its 999.9 saturation sentinel must not surface as a real reading.
    obs, _ = sensor_community.parse_measurements(
        [_row(5, "2026-06-17 23:00:00", p2="999.9", p1="999.9", temp="25.0", humid="40.0")]
    )
    params = {o.parameter for o in obs}
    assert "pm25_ugm3" not in params and "pm10_ugm3" not in params  # sentinels dropped
    assert "temp_c" in params  # the genuine temperature reading is kept


def test_parse_derives_no_heat_metric_from_a_faulted_probe() -> None:
    """A faulted DHT/BME on this network reports ≈-145 °C. That temperature is rejected as
    impossible and never mapped (ADR 0029) — so the heat index and estimated WBGT computed from
    it must not be published either, even though they can land inside their own valid ranges and
    pass QC as clean (ADR 0041)."""
    obs, _ = sensor_community.parse_measurements(
        [_row(9, "2026-06-17 23:00:00", p2="8.0", p1="12.0", temp="-145.72", humid="100.0")]
    )
    params = {o.parameter for o in obs}
    assert "heat_index_c" not in params and "wbgt_c" not in params
    # The raw readings themselves still travel; QC labels them, it does not delete them.
    assert "temp_c" in params and "humidity_pct" in params
    assert "pm25_ugm3" in params  # a faulted probe does not discredit the PM sensor beside it


def test_parse_derives_no_heat_metric_from_a_condensing_humidity_reading() -> None:
    """>100 %RH is what a condensing low-cost sensor reports, not weather."""
    obs, _ = sensor_community.parse_measurements(
        [_row(11, "2026-06-17 23:00:00", p2="8.0", p1="12.0", temp="35.0", humid="110.0")]
    )
    params = {o.parameter for o in obs}
    assert "heat_index_c" not in params and "wbgt_c" not in params
    assert "temp_c" in params and "humidity_pct" in params


def test_parse_keeps_latest_per_sensor() -> None:
    rows = [
        _row(7, "2026-06-17 22:00:00", p2="50.0", p1="60.0", temp="20.0", humid="30.0"),
        _row(7, "2026-06-17 23:00:00", p2="11.0", p1="12.0", temp="21.0", humid="31.0"),
    ]
    obs, nodes = sensor_community.parse_measurements(rows)
    assert set(nodes) == {"sc-7"}  # one node, not two
    pm = next(o for o in obs if o.parameter == "pm25_ugm3")
    assert pm.value == 11.0  # the later reading wins
    assert pm.timestamp == "2026-06-17T23:00:00Z"


def test_parse_skips_rows_without_coords_or_sensor() -> None:
    rows: list[object] = [
        {"sensor": {"id": 1}, "timestamp": "2026-06-17 23:00:00"},  # no location
        {
            "timestamp": "2026-06-17 23:00:00",
            "location": {"latitude": "1", "longitude": "2"},
        },  # no sensor
        "not-a-dict",
    ]
    obs, nodes = sensor_community.parse_measurements(rows)
    assert obs == [] and nodes == {}


def test_network_doc_marks_uncalibrated() -> None:
    doc = sensor_community.network_doc("Stuttgart", {"sc-9": ("Sensor 9", 48.0, 9.0, "")})
    assert doc["nodes"][0]["location"] == "precise"  # real sensor coordinates
    assert doc["calibration_windows"] == []  # community sensors here are uncalibrated
    assert "Sensor.Community" in doc["name"]
    assert "sensor_model" not in doc["nodes"][0]  # unknown model omitted, not published as ""


def test_parse_preserves_known_sensor_model() -> None:
    # The adapter must not discard the sensor type it already knows (SDS011/SPS30/...): it maps
    # onto the node's sensor_model so a later calibration can select the right correction family.
    obs, nodes = sensor_community.parse_measurements(
        [
            _row(
                42,
                "2026-06-17 23:00:00",
                p2="12.3",
                p1="20.0",
                temp="28.1",
                humid="40.0",
                sensor_type="SDS011",
            )
        ]
    )
    assert nodes == {"sc-42": ("Sensor 42", 48.7758, 9.1829, "SDS011")}
    assert obs  # readings still map normally


def test_network_doc_carries_known_sensor_model() -> None:
    doc = sensor_community.network_doc("Stuttgart", {"sc-42": ("Sensor 42", 48.0, 9.0, "SDS011")})
    assert doc["nodes"][0]["sensor_model"] == "SDS011"
    assert doc["calibration_windows"] == []  # still uncalibrated — a model is not a calibration
