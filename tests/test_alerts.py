"""The alerts feed raises only on real danger crossings, stays deterministic, and carries no PII."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from swelter import aggregate, alerts
from swelter.config import NetworkConfig, NodeConfig

from .conftest import make_obs

_NODE = NodeConfig(
    node_id="node-01", label="Oak & 4th", lat=38.5816, lon=-121.4944, location="precise"
)
_CONFIG = NetworkConfig(grid_resolution_m=150.0, nodes=(_NODE,))


def _feed(*obs: object, **kw: object) -> alerts.AlertFeed:
    surface = aggregate.aggregate(list(obs), _CONFIG)  # type: ignore[arg-type]
    return alerts.build_feed(surface, network="demo", base_url="https://example.org", **kw)  # type: ignore[arg-type]


def test_clean_air_raises_no_alert() -> None:
    feed = _feed(make_obs(parameter="pm25_ugm3", unit="ug/m3", value=5.0, calibration="v1"))
    assert feed.alerts == ()
    assert feed.to_json()["count"] == 0


def test_pm25_over_aqi_101_raises_alert() -> None:
    # 40 ug/m3 → AQI ~112, "Unhealthy for Sensitive Groups" → past the 101 floor.
    feed = _feed(make_obs(parameter="pm25_ugm3", unit="ug/m3", value=40.0, calibration="v1"))
    assert len(feed.alerts) == 1
    alert = feed.alerts[0]
    assert alert.parameter == "pm25_ugm3"
    assert alert.area == "Oak & 4th"
    assert alert.aqi is not None and alert.aqi >= 101
    assert alert.provisional is False
    assert "Oak & 4th" in alert.headline()


def test_heat_index_danger_raises_alert() -> None:
    feed = _feed(make_obs(parameter="heat_index_c", value=41.0, calibration="v1"))
    assert len(feed.alerts) == 1
    assert feed.alerts[0].severity == "Danger"


def test_heat_index_below_danger_is_quiet() -> None:
    # 35 °C heat index is "Extreme Caution" — concerning, but below the published Danger floor.
    feed = _feed(make_obs(parameter="heat_index_c", value=35.0, calibration="v1"))
    assert feed.alerts == ()


def test_provisional_reading_alerts_but_is_flagged() -> None:
    feed = _feed(make_obs(parameter="pm25_ugm3", unit="ug/m3", value=60.0))  # raw → provisional
    assert len(feed.alerts) == 1
    assert feed.alerts[0].provisional is True
    assert "provisional" in feed.alerts[0].headline()


def test_compound_cell_can_raise_multiple_alerts() -> None:
    feed = _feed(
        make_obs(parameter="pm25_ugm3", unit="ug/m3", value=60.0, calibration="v1"),
        make_obs(parameter="heat_index_c", value=41.0, calibration="v2"),
    )
    params = sorted(a.parameter for a in feed.alerts)
    assert params == ["exposure", "heat_index_c", "pm25_ugm3"]


def test_custom_threshold_can_lower_the_floor() -> None:
    obs = make_obs(parameter="heat_index_c", value=33.0, calibration="v1")  # below default Danger
    assert _feed(obs).alerts == ()
    feed = _feed(obs, thresholds={"heat_index_c": 32.0})
    assert len(feed.alerts) == 1


def test_feed_timestamp_is_data_derived_not_wallclock() -> None:
    # The feed's "generated" is the latest surface bucket, so the artifact is reproducible.
    feed = _feed(
        make_obs(
            parameter="pm25_ugm3",
            unit="ug/m3",
            value=40.0,
            calibration="v1",
            timestamp="2026-06-01T05:00:00Z",
        )
    )
    assert feed.bucket == "2026-06-01T05:00:00Z"
    assert feed.to_json()["generated"] == "2026-06-01T05:00:00Z"


def test_empty_feed_still_carries_latest_bucket() -> None:
    # A calm hour (clean air, no crossings) still reports the surface's latest bucket.
    feed = _feed(
        make_obs(
            parameter="pm25_ugm3",
            unit="ug/m3",
            value=4.0,
            calibration="v1",
            timestamp="2026-06-02T03:00:00Z",
        )
    )
    assert feed.alerts == ()
    assert feed.bucket == "2026-06-02T03:00:00Z"


def test_for_area_narrows_to_one_cell() -> None:
    feed = _feed(make_obs(parameter="pm25_ugm3", unit="ug/m3", value=40.0, calibration="v1"))
    area_id = feed.alerts[0].area_id
    assert len(feed.for_area(area_id).alerts) == 1
    assert feed.for_area("nowhere").alerts == ()


def test_atom_is_valid_xml_with_one_entry_per_alert() -> None:
    feed = _feed(
        make_obs(parameter="pm25_ugm3", unit="ug/m3", value=60.0, calibration="v1"),
        make_obs(parameter="heat_index_c", value=41.0, calibration="v2"),
    )
    root = ET.fromstring(feed.to_atom())  # noqa: S314 -- parsing our own generated feed, not external input
    ns = "{http://www.w3.org/2005/Atom}"
    entries = root.findall(f"{ns}entry")
    assert len(entries) == len(feed.alerts)
    assert root.find(f"{ns}updated") is not None


def test_alert_record_carries_only_public_fields() -> None:
    feed = _feed(make_obs(parameter="pm25_ugm3", unit="ug/m3", value=40.0, calibration="v1"))
    record = feed.alerts[0].as_record()
    # No person-shaped keys: the record names a block and a reading, never an individual or device.
    forbidden = {"email", "phone", "name_contact", "mac", "address", "device_id", "subscriber"}
    assert forbidden.isdisjoint(record)
    assert set(record) <= {
        "id",
        "area_id",
        "area",
        "lat",
        "lon",
        "parameter",
        "bucket",
        "value",
        "unit",
        "severity",
        "threshold",
        "provisional",
        "headline",
        "aqi",
        "nodes",
    }


def test_to_json_advertises_no_account_subscription() -> None:
    feed = _feed(make_obs(parameter="pm25_ugm3", unit="ug/m3", value=40.0, calibration="v1"))
    doc = feed.to_json()
    assert "no account" in doc["note"]  # type: ignore[operator]
    assert doc["thresholds"]["pm25_aqi"] == 101.0  # type: ignore[index]
