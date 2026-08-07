"""The alerts feed raises only on real danger crossings, stays deterministic, and carries no PII."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from collections.abc import Mapping
from typing import cast

from swelter import aggregate, alerts
from swelter.alerts import DEFAULT_THRESHOLDS, crossing
from swelter.config import NetworkConfig, NodeConfig
from swelter.models import Observation

from .conftest import make_obs

_NODE = NodeConfig(
    node_id="node-01", label="Oak & 4th", lat=38.5816, lon=-121.4944, location="precise"
)
_CONFIG = NetworkConfig(grid_resolution_m=150.0, nodes=(_NODE,))

# A second, distinctly-located node (well outside a 150m grid cell of `_NODE`) for the dead-node
# staleness tests below: one node keeps reporting, one goes dark.
_NODE_CURRENT = NodeConfig(
    node_id="node-02", label="Elm & 9th", lat=38.6100, lon=-121.4600, location="precise"
)
_CONFIG_TWO_NODES = NetworkConfig(grid_resolution_m=150.0, nodes=(_NODE, _NODE_CURRENT))


def _feed(*obs: Observation, thresholds: Mapping[str, float] | None = None) -> alerts.AlertFeed:
    surface = aggregate.aggregate(obs, _CONFIG)
    return alerts.build_feed(
        surface,
        network="demo",
        base_url="https://example.org",
        thresholds=thresholds,
    )


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


def test_dead_node_stale_reading_does_not_raise_an_alert() -> None:
    # Issue #148: node-01's last-ever reading was a Danger-severity heat index three months before
    # node-02's newest hour, then node-01 went dark. `latest_by_cell()` still returns that reading
    # forever (it is genuinely the *latest* one node-01 ever sent) — build_feed must not turn it
    # into a standing alert once a newer bucket exists anywhere on the surface. node-02 is currently
    # reporting a real Danger crossing in that newest bucket, and its alert must still fire.
    surface = aggregate.aggregate(
        [
            make_obs(
                node_id="node-01",
                parameter="heat_index_c",
                value=45.0,
                calibration="v1",
                timestamp="2026-06-01T12:00:00Z",  # three months stale relative to node-02
            ),
            make_obs(
                node_id="node-02",
                parameter="heat_index_c",
                value=41.0,
                calibration="v1",
                timestamp="2026-09-01T12:00:00Z",  # the surface's newest bucket
            ),
        ],
        _CONFIG_TWO_NODES,
    )

    # Confirm the fixture actually reproduces the bug's precondition: node-01's stale reading is a
    # real, genuine Danger crossing (not a low value that would fail to alert for an unrelated
    # reason), so a passing assertion below is not vacuous.
    stale_by_cell = surface.latest_by_cell()
    stale_area_id, stale_reading = next(
        (area_id, by_param["heat_index_c"])
        for area_id, by_param in stale_by_cell.items()
        if by_param.get("heat_index_c") is not None
        and by_param["heat_index_c"].bucket == "2026-06-01T12:00:00Z"
    )
    assert crossing("heat_index_c", stale_reading, DEFAULT_THRESHOLDS) is not None

    feed = alerts.build_feed(surface, network="demo", base_url="https://example.org")

    # The feed's own "updated" is the surface's newest bucket — node-02's hour, not node-01's.
    assert feed.bucket == "2026-09-01T12:00:00Z"
    # Only the currently-reporting node's Danger crossing is published.
    assert len(feed.alerts) == 1
    alert = feed.alerts[0]
    assert alert.area == "Elm & 9th"
    assert alert.bucket == "2026-09-01T12:00:00Z"
    assert alert.severity == "Danger"
    # The dead node's stale cell raised nothing.
    assert stale_area_id not in {a.area_id for a in feed.alerts}
    assert all(a.area != "Oak & 4th" for a in feed.alerts)


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
    root = ET.fromstring(feed.to_atom())  # noqa: S314 -- parsing our own generated feed, not external input (#107)
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
        "headline_es",
        "aqi",
        "nodes",
    }


def test_to_json_advertises_no_account_subscription() -> None:
    feed = _feed(make_obs(parameter="pm25_ugm3", unit="ug/m3", value=40.0, calibration="v1"))
    doc = feed.to_json()
    assert "no account" in cast(str, doc["note"])
    assert cast(dict[str, float], doc["thresholds"])["pm25_aqi"] == 101.0


# -- bilingual (es) surfaces: server-side catalog, parity-gated -------------


def test_as_record_carries_a_spanish_headline() -> None:
    feed = _feed(make_obs(parameter="pm25_ugm3", unit="ug/m3", value=40.0, calibration="v1"))
    record = feed.alerts[0].as_record()
    assert record["headline_es"]
    assert record["headline_es"] != record["headline"]
    assert record["headline_es"] == feed.alerts[0].headline("es")


def test_to_json_labels_the_translation_as_machine() -> None:
    feed = _feed(make_obs(parameter="pm25_ugm3", unit="ug/m3", value=40.0, calibration="v1"))
    doc = feed.to_json()
    assert doc["translation"] == "machine"
    assert doc["note_es"]


def test_to_atom_es_differs_from_en_and_carries_spanish_text() -> None:
    feed = _feed(
        make_obs(parameter="pm25_ugm3", unit="ug/m3", value=40.0, calibration="v1"),
        make_obs(parameter="heat_index_c", value=41.0, calibration="v2"),
    )
    en_atom = feed.to_atom()
    es_atom = feed.to_atom(lang="es")
    assert en_atom != es_atom
    assert 'xml:lang="es"' in es_atom
    root = ET.fromstring(es_atom)  # noqa: S314 -- our own generated feed, not external input (#107)
    ns = "{http://www.w3.org/2005/Atom}"
    assert root.get("{http://www.w3.org/XML/1998/namespace}lang") == "es"
    entries = root.findall(f"{ns}entry")
    assert len(entries) == len(feed.alerts)
    spanish_fragments = ("la calidad del aire", "índice de calor", "exposición combinada")
    for entry in entries:
        title = entry.find(f"{ns}title")
        assert title is not None and title.text
        assert any(fragment in title.text for fragment in spanish_fragments)


def test_to_atom_es_is_labeled_machine_translated() -> None:
    feed = _feed(make_obs(parameter="pm25_ugm3", unit="ug/m3", value=40.0, calibration="v1"))
    es_atom = feed.to_atom(lang="es")
    assert "machine" in es_atom.lower()
    en_atom = feed.to_atom()
    assert "<generator>" not in en_atom  # English is not flagged as a translation of anything


def test_to_atom_links_the_alternate_language() -> None:
    feed = _feed(make_obs(parameter="pm25_ugm3", unit="ug/m3", value=40.0, calibration="v1"))
    root = ET.fromstring(feed.to_atom())  # noqa: S314 -- our own generated feed, not external input (#107)
    ns = "{http://www.w3.org/2005/Atom}"
    alternates = [
        link
        for link in root.findall(f"{ns}link")
        if link.get("rel") == "alternate" and link.get("hreflang") == "es"
    ]
    assert len(alternates) == 1
    assert alternates[0].get("href", "").endswith("alerts.es.xml")
