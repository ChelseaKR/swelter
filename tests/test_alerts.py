"""The alerts feed raises only on real danger crossings, stays deterministic, and carries no PII."""

from __future__ import annotations

import json
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


def _atom_root(document: str) -> ET.Element:
    """Parse one of our own generated Atom feeds.

    The single parse site in this module: `ET.fromstring` needs an S314 suppression (XML parsing),
    and one suppression on a helper every test shares is better than one per call site (#107).
    """
    return ET.fromstring(document)  # noqa: S314 -- our own generated feed, not external input (#107)


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


def _dead_node_surface(dead_value: float) -> aggregate.Surface:
    """node-01 goes dark after one reading of `dead_value`; node-02 keeps reporting, safely."""
    return aggregate.aggregate(
        [
            make_obs(
                node_id="node-01",
                parameter="heat_index_c",
                value=dead_value,
                calibration="v1",
                timestamp="2026-06-01T12:00:00Z",  # the last hour node-01 ever reported
            ),
            make_obs(
                node_id="node-02",
                parameter="heat_index_c",
                value=20.0,  # comfortably below the Danger floor: node-02 raises nothing
                calibration="v1",
                timestamp="2026-09-01T12:00:00Z",  # the surface's newest bucket
            ),
        ],
        _CONFIG_TWO_NODES,
    )


def _stale_for(feed: alerts.AlertFeed, area: str) -> alerts.StaleArea:
    return next(s for s in feed.stale if s.area == area)


def test_dead_node_is_published_as_no_current_reading_not_as_silence() -> None:
    # ADR 0036 / issue #148. Suppressing the dead node's alert (ADR 0035) leaves the feed saying
    # nothing at all about that block, and in an alerts feed "nothing" reads as "all clear". The
    # dark block must be named, with no value and an explicit "swelter cannot tell".
    feed = alerts.build_feed(
        _dead_node_surface(45.0), network="demo", base_url="https://example.org"
    )

    assert feed.alerts == ()  # the stale Danger crossing is not republished as live
    dark = _stale_for(feed, "Oak & 4th")
    assert dark.parameter == "heat_index_c"
    assert dark.last_bucket == "2026-06-01T12:00:00Z"
    assert dark.hours_since_last_reading == 2208  # 92 days, stated rather than rounded away
    assert dark.withdrawn is True  # that last reading did cross Danger: this retracts it

    record = dark.as_record()
    assert record["status"] == "no-current-reading"
    # The absence must not be reported as a value of any kind. No `value`, no `mean`, no `severity`,
    # no `aqi`, no `threshold`: nothing a consumer could read as "the current reading for this
    # block", and specifically not the last known reading standing in for the missing one.
    assert not {"value", "mean", "severity", "aqi", "threshold", "unit"} & set(record)
    assert "45" not in json.dumps(record)

    payload = feed.to_json()
    assert payload["count"] == 0
    assert payload["stale_count"] == 1
    assert cast(list[dict[str, object]], payload["stale"])[0]["withdrawn"] is True
    headline = str(dark.headline())
    assert "no current heat-index reading" in headline
    assert "cannot tell" in headline
    assert "withdrawn, not cleared" in headline


def test_dead_node_that_was_safe_when_it_died_is_still_published_as_unknown() -> None:
    # The worse half of issue #148: a sensor that dies during a cool spell. It never raised an
    # alert, so suppression changes nothing for it — the feed just keeps quiet about that block
    # forever, which reads as a standing all-clear. It has to be published as unknown too, and it
    # must not be marked `withdrawn` (nothing was published to withdraw).
    feed = alerts.build_feed(
        _dead_node_surface(20.0), network="demo", base_url="https://example.org"
    )

    assert feed.alerts == ()
    dark = _stale_for(feed, "Oak & 4th")
    assert dark.withdrawn is False
    assert dark.last_bucket == "2026-06-01T12:00:00Z"
    assert "cannot tell" in dark.headline()
    assert "withdrawn" not in dark.headline()
    # The currently-reporting, genuinely-safe node is *not* in the stale list: quiet-because-safe
    # and quiet-because-unseen stay distinguishable.
    assert [s.area for s in feed.stale] == ["Oak & 4th"]


def test_stale_atom_entry_updates_the_alert_it_supersedes() -> None:
    # An Atom reader keys entries by id and ignores an update stamped older than what it holds. The
    # withdrawal has to land on the same id as the Danger entry the subscriber is already looking
    # at, stamped with the feed's own bucket, or the last word on that block stays "Danger".
    feed = alerts.build_feed(
        _dead_node_surface(45.0), network="demo", base_url="https://example.org"
    )
    dark = _stale_for(feed, "Oak & 4th")
    root = _atom_root(feed.to_atom())
    entries = root.findall("{http://www.w3.org/2005/Atom}entry")
    assert len(entries) == 1
    entry = entries[0]
    assert entry.findtext("{http://www.w3.org/2005/Atom}id") == (
        f"https://example.org/api/alerts.xml#{dark.area_id}|heat_index_c"
    )
    assert entry.findtext("{http://www.w3.org/2005/Atom}updated") == "2026-09-01T12:00:00Z"
    terms = {c.get("term") for c in entry.findall("{http://www.w3.org/2005/Atom}category")}
    assert alerts.STALE_CATEGORY in terms
    title = entry.findtext("{http://www.w3.org/2005/Atom}title") or ""
    assert "no current heat-index reading" in title
    assert "Danger" not in title


def test_one_area_subscription_still_hears_that_its_own_node_went_dark() -> None:
    feed = alerts.build_feed(
        _dead_node_surface(45.0), network="demo", base_url="https://example.org"
    )
    dark = _stale_for(feed, "Oak & 4th")
    scoped = feed.for_area(dark.area_id)
    assert scoped.alerts == ()
    assert [s.area_id for s in scoped.stale] == [dark.area_id]
    assert feed.for_area("nowhere").stale == ()


def test_an_unparseable_bucket_reports_an_unknown_gap_not_a_zero_hour_one() -> None:
    # A gap whose size cannot be computed is reported without a size. Zero would read as "it
    # reported just now", which is the reassuring answer and the wrong one.
    assert alerts._hours_between("not-a-timestamp", "2026-09-01T12:00:00Z") is None
    area = alerts.StaleArea(
        area_id="38.5,-121.5",
        area="Oak & 4th",
        lat=38.5,
        lon=-121.5,
        parameter="pm25_ugm3",
        last_bucket="2026-06-01T12:00:00Z",
        hours_since_last_reading=None,
        withdrawn=False,
    )
    assert area.as_record()["hours_since_last_reading"] is None
    assert "0 h" not in area.headline()
    assert "last reported 2026-06-01T12:00:00Z" in area.headline()


def test_a_fully_current_surface_publishes_no_stale_areas() -> None:
    feed = _feed(make_obs(parameter="pm25_ugm3", unit="ug/m3", value=5.0, calibration="v1"))
    assert feed.stale == ()
    assert feed.to_json()["stale_count"] == 0
    assert "<entry>" not in feed.to_atom()


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
    root = _atom_root(feed.to_atom())
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
    root = _atom_root(es_atom)
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
    root = _atom_root(feed.to_atom())
    ns = "{http://www.w3.org/2005/Atom}"
    alternates = [
        link
        for link in root.findall(f"{ns}link")
        if link.get("rel") == "alternate" and link.get("hreflang") == "es"
    ]
    assert len(alternates) == 1
    assert alternates[0].get("href", "").endswith("alerts.es.xml")
