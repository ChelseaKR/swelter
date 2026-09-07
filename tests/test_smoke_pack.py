"""The smoke hazard pack: a NowCast window, an event rule, and the absences around both.

Four things are under test, and three of them are ways this could have quietly lied.

1. **Selecting the pack changes nothing for anyone who did not.** A network that names no
   ``hazard_pack`` produces a byte-identical feed to the one it produced before this pack
   existed.
2. **One spiking node is a node, not an event.** The rule counts cells that have each risen
   against their own past, so a single sensor going to 300 with flat neighbours produces no
   event and stays visible and provisional.
3. **A question that could not be asked has not been answered "no".** A surface with no
   comparable earlier hour reports ``evaluated=False``, not ``active=False``, and says so in
   its own sentence in both languages.
4. **A cell with no PM2.5 in the pack's window gets no tier.** Not tier 0, and not a silent
   fallback to the hourly mean the feed did not promise.
"""

from __future__ import annotations

import json

from swelter import aggregate, alerts, hazard_packs, i18n_alerts
from swelter.config import NetworkConfig, NodeConfig
from swelter.models import Observation

from .conftest import make_obs

# Four nodes far enough apart to land in four distinct 150 m cells.
_NODES = (
    NodeConfig(
        node_id="node-01", label="Oak & 4th", lat=38.5816, lon=-121.4944, location="precise"
    ),
    NodeConfig(
        node_id="node-02", label="Elm & 9th", lat=38.6100, lon=-121.4600, location="precise"
    ),
    NodeConfig(
        node_id="node-03", label="Pine & 2nd", lat=38.6400, lon=-121.4300, location="precise"
    ),
    NodeConfig(
        node_id="node-04", label="Ash & 7th", lat=38.6700, lon=-121.4000, location="precise"
    ),
)
_CONFIG = NetworkConfig(grid_resolution_m=150.0, nodes=_NODES)

#: NowCast needs at least three trailing hourly means, so every fixture below supplies four
#: hours: three to build the window and one to be the "earlier" reading the rule compares to.
_HOURS = (
    "2026-09-01T00:00:00Z",
    "2026-09-01T01:00:00Z",
    "2026-09-01T02:00:00Z",
    "2026-09-01T03:00:00Z",
)


def _pm25(node_id: str, hour: str, value: float) -> Observation:
    return make_obs(
        node_id=node_id,
        timestamp=hour,
        parameter="pm25_ugm3",
        unit="ug/m3",
        value=value,
        calibration="v1",
    )


def _series(**by_node: tuple[float, float, float, float]) -> list[Observation]:
    """One four-hour PM2.5 series per node, in ``_HOURS`` order."""
    return [
        _pm25(node_id, hour, value)
        for node_id, values in by_node.items()
        for hour, value in zip(_HOURS, values, strict=True)
    ]


def _feed(
    observations: list[Observation], pack: hazard_packs.HazardPack | None = None
) -> alerts.AlertFeed:
    surface = aggregate.aggregate(observations, _CONFIG)
    return alerts.build_feed(surface, network="demo", base_url="https://example.org", pack=pack)


# ------------------------------------------------------------------------------------------
# The pack is data, and selecting it is the only thing that changes anything.
# ------------------------------------------------------------------------------------------


def test_the_pack_is_registered_and_cites_every_number_it_publishes() -> None:
    pack = hazard_packs.PACKS["smoke"]
    assert pack is hazard_packs.SMOKE_PACK
    assert pack.aqi_window == hazard_packs.AQI_WINDOW_NOWCAST
    for threshold in pack.thresholds:
        assert threshold.citation.url.startswith("https://")
        assert threshold.citation.source
    rule = pack.event_rule
    assert rule is not None
    assert rule.citation.url.startswith("https://")
    # The rule's own numbers are swelter's, and the citation says so rather than attributing
    # them to a standards body that never set them.
    assert "swelter's own" in rule.citation.detail


def test_the_duplicated_window_names_equal_the_ones_aggregate_publishes() -> None:
    """`hazard_packs` deliberately imports nothing from `aggregate`, so the two copies of these
    strings can drift. They may not."""
    assert hazard_packs.AQI_WINDOW_HOURLY_MEAN == aggregate.AQI_WINDOW
    assert hazard_packs.AQI_WINDOW_NOWCAST == aggregate.AQI_WINDOW_NOWCAST


def test_a_network_that_names_no_pack_is_byte_identical_to_before() -> None:
    """The abstraction's own promise: adding a pack changes nothing for anyone who did not
    select it. Compared as serialized bytes, not field by field, so a new key added to the feed
    would fail here rather than slip through a spot check."""
    observations = _series(**{"node-01": (5.0, 6.0, 7.0, 8.0)})
    default = _feed(observations)
    heat = _feed(observations, hazard_packs.HEAT_PACK)
    assert json.dumps(default.to_json(), sort_keys=True) == json.dumps(
        heat.to_json(), sort_keys=True
    )
    assert default.event is None
    assert default.aqi_window == aggregate.AQI_WINDOW


def test_the_heat_feed_carries_no_event_key_at_all() -> None:
    """Absent means "this pack looks for no events"; `{"active": false}` means "checked, and no".
    Collapsing the two would let a heat feed's silence read as an all-clear about smoke."""
    payload = _feed(_series(**{"node-01": (5.0, 6.0, 7.0, 8.0)})).to_json()
    assert "event" not in payload
    assert "event_headline" not in payload
    # And no `aqi_window` either: this feed reads the window it always read, so it serializes
    # the bytes it always serialized. `scripts/demo_artifact_check.py` is what caught the first
    # version of this, which added the key to every feed.
    assert "aqi_window" not in payload


# ------------------------------------------------------------------------------------------
# The window is selected, never preferred.
# ------------------------------------------------------------------------------------------


def test_the_smoke_pack_alerts_on_the_nowcast_window_and_says_so() -> None:
    feed = _feed(_series(**{"node-01": (10.0, 20.0, 60.0, 90.0)}), hazard_packs.SMOKE_PACK)
    assert feed.aqi_window == aggregate.AQI_WINDOW_NOWCAST
    assert feed.to_json()["aqi_window"] == aggregate.AQI_WINDOW_NOWCAST
    assert len(feed.alerts) == 1
    # NowCast weights recent hours, so it sits above the flat four-hour mean of this series.
    hourly = _feed(_series(**{"node-01": (10.0, 20.0, 60.0, 90.0)}), hazard_packs.HEAT_PACK)
    assert feed.alerts[0].value != hourly.alerts[0].value


def test_a_cell_without_a_nowcast_reading_gets_no_tier_rather_than_the_other_window() -> None:
    """Two trailing hours is below NowCast's three-hour floor, so `nowcast_concentration`
    returns `None` and there is no NowCast row for this cell at all. The smoke feed must then
    say nothing about it, not quietly publish the hourly mean under a feed that named NowCast.
    """
    short = [
        _pm25("node-01", _HOURS[2], 300.0),
        _pm25("node-01", _HOURS[3], 320.0),
    ]
    surface = aggregate.aggregate(short, _CONFIG)
    assert not [c for c in surface.cells if c.aqi_window == aggregate.AQI_WINDOW_NOWCAST]

    feed = _feed(short, hazard_packs.SMOKE_PACK)
    assert feed.alerts == ()
    assert feed.stale == ()
    # And the hourly-mean feed does see it, which is what makes the line above a selection
    # rather than an empty surface.
    assert len(_feed(short, hazard_packs.HEAT_PACK).alerts) == 1


def test_a_cell_with_no_pm25_at_all_gets_no_tier_and_not_tier_zero() -> None:
    temperature_only = [
        make_obs(node_id="node-01", timestamp=hour, parameter="temp_c", value=21.0)
        for hour in _HOURS
    ]
    feed = _feed(temperature_only, hazard_packs.SMOKE_PACK)
    assert feed.alerts == ()
    payload = feed.to_json()
    assert payload["count"] == 0
    published = payload["alerts"]
    assert isinstance(published, list)
    assert published == []


# ------------------------------------------------------------------------------------------
# The event rule: one node is a node.
# ------------------------------------------------------------------------------------------


def test_one_spiking_node_with_flat_neighbours_declares_no_event() -> None:
    """The rule's whole reason for counting cells. The spiking node still alerts and stays
    visible and provisional; what it does not get to do is declare a network-wide event."""
    feed = _feed(
        _series(
            **{
                "node-01": (8.0, 9.0, 10.0, 300.0),
                "node-02": (8.0, 9.0, 9.0, 9.0),
                "node-03": (8.0, 8.0, 9.0, 9.0),
                "node-04": (9.0, 9.0, 8.0, 9.0),
            }
        ),
        hazard_packs.SMOKE_PACK,
    )
    event = feed.event
    assert event is not None
    assert event.evaluated is True
    assert event.active is False
    assert event.qualifying_cells == 1
    assert event.minimum_cells == 3

    # The node is still there, still alerting, and still labelled as uncalibrated-or-not.
    assert [a.area_id for a in feed.alerts]
    assert all(isinstance(a.provisional, bool) for a in feed.alerts)


def test_a_sustained_multi_cell_rise_declares_an_event_and_names_the_window() -> None:
    feed = _feed(
        _series(
            **{
                "node-01": (8.0, 40.0, 120.0, 180.0),
                "node-02": (9.0, 45.0, 130.0, 190.0),
                "node-03": (7.0, 38.0, 125.0, 175.0),
                "node-04": (8.0, 9.0, 9.0, 9.0),
            }
        ),
        hazard_packs.SMOKE_PACK,
    )
    event = feed.event
    assert event is not None
    assert event.evaluated is True
    assert event.active is True
    assert event.qualifying_cells == 3
    assert event.aqi_window == aggregate.AQI_WINDOW
    assert event.parameter == "pm25_ugm3"
    assert len(event.areas) == 3
    assert list(event.areas) == sorted(event.areas)
    assert event.bucket == _HOURS[-1]


def test_a_high_but_flat_airshed_is_not_an_event() -> None:
    """An absolute floor alone would put a chronically poor airshed permanently "in an event",
    which tells a resident nothing. The rise is what makes it an episode."""
    feed = _feed(
        _series(
            **{
                "node-01": (150.0, 150.0, 150.0, 150.0),
                "node-02": (150.0, 150.0, 150.0, 150.0),
                "node-03": (150.0, 150.0, 150.0, 150.0),
            }
        ),
        hazard_packs.SMOKE_PACK,
    )
    assert feed.event is not None
    assert feed.event.evaluated is True
    assert feed.event.active is False
    assert feed.event.qualifying_cells == 0
    # And every cell is still alerting on its own, which is the point of keeping them separate.
    assert len(feed.alerts) == 3


# ------------------------------------------------------------------------------------------
# Absence, in the two places it could have been rendered as a value.
# ------------------------------------------------------------------------------------------


def test_a_surface_with_no_comparable_earlier_hour_is_not_evaluated_rather_than_negative() -> None:
    """The failure this repository keeps finding: a question that could not be asked, answered
    "no". Three consecutive hours give a NowCast row only at the newest, so there is nothing
    three hours back to compare it against."""
    three_hours = [
        _pm25("node-01", hour, value)
        for hour, value in zip(_HOURS[:3], (10.0, 100.0, 300.0), strict=True)
    ]
    feed = _feed(three_hours, hazard_packs.SMOKE_PACK)
    event = feed.event
    assert event is not None
    assert event.evaluated is False
    assert event.active is False
    assert event.qualifying_cells == 0
    assert "no rise could be measured" in event.reason


def test_an_unevaluated_event_gets_its_own_sentence_in_both_languages() -> None:
    """ "Not determined" and "no event" must not share a sentence, because only one of them is
    reassuring."""
    three_hours = [
        _pm25("node-01", hour, value)
        for hour, value in zip(_HOURS[:3], (10.0, 100.0, 300.0), strict=True)
    ]
    event = _feed(three_hours, hazard_packs.SMOKE_PACK).event
    assert event is not None
    english = i18n_alerts.event_headline(event, "en")
    spanish = i18n_alerts.event_headline(event, "es")
    assert "not determined" in english
    assert "no determinado" in spanish
    assert "No smoke event" not in english


def test_the_event_record_is_published_whether_or_not_an_event_is_running() -> None:
    payload = _feed(
        _series(**{"node-01": (8.0, 9.0, 10.0, 11.0)}), hazard_packs.SMOKE_PACK
    ).to_json()
    record = payload["event"]
    assert isinstance(record, dict)
    assert record["active"] is False
    assert record["minimum_cells"] == 3
    assert record["reason"]
    assert payload["event_headline"]
    assert payload["event_headline_es"]


def test_a_running_event_says_so_in_both_languages() -> None:
    feed = _feed(
        _series(
            **{
                "node-01": (8.0, 40.0, 120.0, 180.0),
                "node-02": (9.0, 45.0, 130.0, 190.0),
                "node-03": (7.0, 38.0, 125.0, 175.0),
            }
        ),
        hazard_packs.SMOKE_PACK,
    )
    event = feed.event
    assert event is not None
    assert "Smoke event in progress" in i18n_alerts.event_headline(event, "en")
    assert "Evento de humo en curso" in i18n_alerts.event_headline(event, "es")


def test_an_area_that_stops_reporting_during_an_event_publishes_absence() -> None:
    """A node that goes quiet mid-episode must not keep broadcasting its last tier, and must not
    vanish either: it is published as a stale record with no value."""
    observations = _series(
        **{
            "node-01": (8.0, 40.0, 120.0, 180.0),
            "node-02": (9.0, 45.0, 130.0, 190.0),
            "node-03": (7.0, 38.0, 125.0, 175.0),
        }
    )
    # node-04 reported for the first three hours and then went dark.
    observations += [
        _pm25("node-04", hour, value)
        for hour, value in zip(_HOURS[:3], (10.0, 60.0, 160.0), strict=True)
    ]
    feed = _feed(observations, hazard_packs.SMOKE_PACK)

    stale_areas = {s.area_id for s in feed.stale}
    alerting = {a.area_id for a in feed.alerts}
    assert stale_areas
    assert not (stale_areas & alerting), "a dark node cannot be both stale and alerting"
    for record in feed.stale:
        assert "value" not in record.as_record()
    assert feed.event is not None and feed.event.active is True


def test_the_single_area_view_keeps_the_event() -> None:
    """A resident subscribed to one block is still in the smoke. The event is network-wide by
    construction, so narrowing the feed must not narrow it away into an all-clear."""
    feed = _feed(
        _series(
            **{
                "node-01": (8.0, 40.0, 120.0, 180.0),
                "node-02": (9.0, 45.0, 130.0, 190.0),
                "node-03": (7.0, 38.0, 125.0, 175.0),
            }
        ),
        hazard_packs.SMOKE_PACK,
    )
    assert feed.event is not None
    narrowed = feed.for_area(feed.alerts[0].area_id)
    assert narrowed.event == feed.event
    assert narrowed.aqi_window == feed.aqi_window


# ------------------------------------------------------------------------------------------
# Determinism.
# ------------------------------------------------------------------------------------------


def test_the_verdict_is_derived_from_the_data_and_not_the_clock() -> None:
    observations = _series(
        **{
            "node-01": (8.0, 40.0, 120.0, 180.0),
            "node-02": (9.0, 45.0, 130.0, 190.0),
            "node-03": (7.0, 38.0, 125.0, 175.0),
        }
    )
    first = _feed(observations, hazard_packs.SMOKE_PACK).to_json()
    second = _feed(observations, hazard_packs.SMOKE_PACK).to_json()
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_an_unparseable_bucket_reports_not_evaluated_rather_than_a_rise_of_zero() -> None:
    """`_shift_hours` returns `None` on a bucket it cannot read. Returning the same hour instead
    would compare each cell against itself and publish a rise of zero as a measurement."""
    assert alerts._shift_hours("not-a-timestamp", -3) is None
    assert alerts._shift_hours("2026-09-01T03:00:00Z", -3) == "2026-09-01T00:00:00Z"
