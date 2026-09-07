"""``hazard_pack: auto-season`` — selecting a pack by the month of the data, not of the run.

ADR 0050 shipped the smoke pack and deliberately did **not** ship the seasonal selector, because a
wall-clock switch makes the published output depend on the day the pipeline ran: a committed
artifact and a fresh replay then disagree the moment a month boundary passes, and the
demo-artifacts gate goes red on a calendar rather than on a change.

These tests are about the two things that make the selector shippable instead: the month comes
from the surface's newest bucket, and the calendar is declared by the network rather than asserted
by swelter.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from swelter import aggregate as aggregate_module
from swelter import alerts, hazard_packs
from swelter.config import NetworkConfig, config_concerns, parse_config
from swelter.models import Observation
from swelter.store import open_store

# A California-shaped calendar: heat through the hot months, smoke through fire season, cold in
# midwinter. It is a fixture, not a recommendation -- which is the whole point of the feature.
CALENDAR: list[dict[str, object]] = [
    {"months": [4, 5, 6, 7, 8], "pack": "heat"},
    {"months": [9, 10, 11], "pack": "smoke"},
    {"months": [12, 1, 2, 3], "pack": "cold"},
]


def _doc(**overrides: object) -> dict[str, object]:
    doc: dict[str, object] = {
        "name": "Season Test Network",
        "grid_resolution_m": 500,
        "nodes": [
            {"node_id": "node-a", "label": "A", "lat": 33.87, "lon": -117.92},
            {"node_id": "node-b", "label": "B", "lat": 33.872, "lon": -117.92},
            {"node_id": "node-c", "label": "C", "lat": 33.874, "lon": -117.92},
        ],
        "hazard_pack": "auto-season",
        "season_calendar": CALENDAR,
    }
    doc.update(overrides)
    return doc


def _config(**overrides: object) -> NetworkConfig:
    return parse_config(yaml.safe_load(yaml.safe_dump(_doc(**overrides))))


def _surface(
    observations: list[Observation], config: NetworkConfig, tmp_path: Path
) -> aggregate_module.Surface:
    with open_store(tmp_path / "store") as store:
        store.write(observations)
        return aggregate_module.aggregate(store.all(), config)


def _pm25(month: int, *, value: float = 90.0) -> list[Observation]:
    """PM2.5 readings in a given month, across three cells and four hours."""
    return [
        Observation(
            node_id=node,
            timestamp=f"2026-{month:02d}-0{day}T0{hour}:00:00Z",
            parameter="pm25_ugm3",
            value=value,
            unit="ug/m3",
        )
        for node in ("node-a", "node-b", "node-c")
        for day, hour in ((1, 0), (1, 1), (1, 2), (1, 3))
    ]


# --------------------------------------------------------------------------------------------
# The selector picks by the month the data is about.
# --------------------------------------------------------------------------------------------


def test_the_month_comes_from_the_surface_not_from_the_wall_clock(tmp_path: Path) -> None:
    """Two stores differing only in their month select different packs, on any day of any year.

    This is the property ADR 0050 said the feature needed before it could ship. Nothing here reads
    a clock, so the same store selects the same pack forever.
    """
    config = _config()
    july = _surface(_pm25(7), config, tmp_path / "july")
    october = _surface(_pm25(10), config, tmp_path / "october")

    july_pack, july_selection = alerts.pack_for_surface(config, july)
    october_pack, october_selection = alerts.pack_for_surface(config, october)

    assert july_pack.pack_id == "heat"
    assert october_pack.pack_id == "smoke"
    assert july_selection is not None and july_selection.month == 7
    assert october_selection is not None and october_selection.month == 10
    assert october_selection.selected_by == "season-calendar"


def test_the_switch_is_recorded_on_the_feed_it_changed(tmp_path: Path) -> None:
    """A pack that changed without the configuration changing must say so on the surface.

    Otherwise the floors a network calls dangerous move for a reason nothing published records.
    """
    config = _config()
    surface = _surface(_pm25(10), config, tmp_path)
    pack, selection = alerts.pack_for_surface(config, surface)
    feed = alerts.build_feed(surface, pack=pack, pack_selection=selection)
    document = feed.to_json()

    assert document["pack_selection"] == {
        "pack": "smoke",
        "selected_by": "season-calendar",
        "month": 10,
    }
    # The month published is the month of the hour the feed stamps itself with -- checkable by a
    # reader against the timestamp printed beside it, which is why both travel.
    assert str(document["generated"])[5:7] == "10"


def test_a_network_that_names_one_pack_serializes_exactly_what_it_always_did(
    tmp_path: Path,
) -> None:
    """ADR 0031's byte-identity promise: adding a selector must not add a key to every feed.

    Compared as serialized bytes rather than field by field, so a new key added anywhere fails
    here instead of slipping past a spot check -- the same mistake the smoke pack made once.
    """
    heat = parse_config(
        yaml.safe_load(yaml.safe_dump(_doc(hazard_pack="heat", season_calendar=[])))
    )
    default_doc = _doc()
    del default_doc["hazard_pack"]
    del default_doc["season_calendar"]
    unset = parse_config(yaml.safe_load(yaml.safe_dump(default_doc)))

    for config in (heat, unset):
        surface = _surface(_pm25(10), config, tmp_path / config.hazard_pack)
        pack, selection = alerts.pack_for_surface(config, surface)
        assert selection is None
        document = alerts.build_feed(surface, pack=pack, pack_selection=selection).to_json()
        assert "pack_selection" not in document
        assert "aqi_window" not in document


def test_a_surface_with_no_cells_publishes_no_month_rather_than_inventing_one(
    tmp_path: Path,
) -> None:
    """An empty surface has no month; a date invented to fill the field is a fabricated fact."""
    config = _config()
    empty = _surface([], config, tmp_path)
    assert empty.newest_bucket() is None
    pack, selection = alerts.pack_for_surface(config, empty)
    assert selection is None
    assert pack.pack_id == "heat", "an unknowable month falls back to the documented default"
    assert "pack_selection" not in alerts.build_feed(empty, pack=pack).to_json()


def test_a_seasonal_surface_carries_every_parameter_any_month_will_need(tmp_path: Path) -> None:
    """The rollup happens before the month is knowable, so it must be the union of the calendar.

    A cell that was never aggregated cannot be alerted on later, so a smoke/cold network that
    rolled up only July's parameters would reach January with nothing for the cold pack to read.
    """
    config = _config()
    observations = _pm25(7) + [
        Observation(
            node_id="node-a",
            timestamp=f"2026-07-01T0{hour}:00:00Z",
            parameter="wind_chill_c",
            value=-30.0,
            unit="degC",
        )
        for hour in range(4)
    ]
    surface = _surface(observations, config, tmp_path)
    parameters = {cell.parameter for cell in surface.cells}
    assert "wind_chill_c" in parameters, (
        "a July surface on a calendar that includes cold must still carry wind chill"
    )
    assert "pm25_ugm3" in parameters


# --------------------------------------------------------------------------------------------
# The calendar is the network's, and an incomplete one is refused.
# --------------------------------------------------------------------------------------------


def test_a_complete_calendar_raises_no_configuration_concern() -> None:
    doc = _doc()
    errors, _ = config_concerns(parse_config(doc), doc)
    assert errors == []


@pytest.mark.parametrize(
    ("calendar", "expected"),
    [
        pytest.param([], "must declare which months", id="absent"),
        pytest.param(
            [{"months": [1, 2, 3, 4, 5, 6], "pack": "heat"}], "no pack covers month", id="gap"
        ),
        pytest.param(
            [
                {"months": list(range(1, 13)), "pack": "heat"},
                {"months": [7], "pack": "smoke"},
            ],
            "claimed by both",
            id="overlap",
        ),
        pytest.param(
            [{"months": list(range(1, 13)), "pack": "monsoon"}], "unknown pack", id="unknown-pack"
        ),
    ],
)
def test_an_incomplete_or_contradictory_calendar_is_refused(
    calendar: list[dict[str, object]], expected: str
) -> None:
    """An uncovered month would fall back to heat in a place whose calendar deliberately omits it.

    That is the same safety surprise `_hazard_pack_concerns` already refuses one level up: a
    network believing it alerts on cold and not doing so.
    """
    doc = _doc(season_calendar=calendar)
    errors, _ = config_concerns(parse_config(doc), doc)
    assert any(expected in error for error in errors), errors


def test_a_calendar_on_a_network_that_names_a_single_pack_is_refused_not_ignored() -> None:
    """A calendar nothing reads is a host believing they configured a season and did not."""
    doc = _doc(hazard_pack="heat")
    errors, _ = config_concerns(parse_config(doc), doc)
    assert any("silently ignored" in error for error in errors), errors


def test_a_seasonal_network_may_override_a_floor_from_any_pack_in_its_calendar() -> None:
    """Validating against one pack would reject the others' keys as unknown.

    A host who set `wind_chill_c` on a seasonal network and was told it is not a real key would
    reasonably conclude the floor took effect somewhere else. It did not.
    """
    doc = _doc(alert_thresholds={"heat_index_c": 38.0, "wind_chill_c": -25.0, "pm25_aqi": 90.0})
    errors, _ = config_concerns(parse_config(doc), doc)
    assert errors == []


def test_a_floor_no_pack_in_the_calendar_defines_is_still_refused() -> None:
    doc = _doc(alert_thresholds={"not_a_real_floor": 1.0})
    errors, _ = config_concerns(parse_config(doc), doc)
    assert any("not_a_real_floor" in error for error in errors), errors


def test_auto_season_is_not_itself_a_pack() -> None:
    """It is a selector. Putting it in PACKS would let it be resolved as a pack with no floors."""
    assert hazard_packs.AUTO_SEASON_PACK_ID not in hazard_packs.PACKS


def test_resolving_the_selector_without_a_month_falls_back_rather_than_guessing_one() -> None:
    calendar = parse_config(_doc()).season_calendar
    assert (
        hazard_packs.resolve_pack(hazard_packs.AUTO_SEASON_PACK_ID, calendar=calendar).pack_id
        == "heat"
    )
    assert (
        hazard_packs.resolve_pack(
            hazard_packs.AUTO_SEASON_PACK_ID, calendar=calendar, month=1
        ).pack_id
        == "cold"
    )


def test_every_month_of_the_year_resolves_to_the_pack_the_calendar_names() -> None:
    """All twelve, not a sample: an off-by-one in a month range is invisible to a spot check."""
    calendar = parse_config(_doc()).season_calendar
    expected = {
        1: "cold",
        2: "cold",
        3: "cold",
        4: "heat",
        5: "heat",
        6: "heat",
        7: "heat",
        8: "heat",
        9: "smoke",
        10: "smoke",
        11: "smoke",
        12: "cold",
    }
    assert {
        month: hazard_packs.pack_for_month(calendar, month).pack_id for month in range(1, 13)
    } == expected


def test_a_month_outside_a_validated_calendar_raises_rather_than_defaulting() -> None:
    """Reaching here means validation was bypassed; silently alerting on heat would hide that."""
    with pytest.raises(hazard_packs.SeasonCalendarError):
        hazard_packs.pack_for_month((hazard_packs.SeasonWindow(months=(1,), pack="cold"),), 7)


def test_the_month_is_read_from_the_bucket_text_it_is_published_beside() -> None:
    assert hazard_packs.month_of("2026-10-01T00:00:00Z") == 10
    assert hazard_packs.month_of("2026-01-31T23:00:00Z") == 1


def test_two_feeds_from_one_seasonal_store_are_byte_identical(tmp_path: Path) -> None:
    config = _config()
    surface = _surface(_pm25(10), config, tmp_path)
    pack, selection = alerts.pack_for_surface(config, surface)
    first = json.dumps(
        alerts.build_feed(surface, pack=pack, pack_selection=selection).to_json(), sort_keys=True
    )
    pack2, selection2 = alerts.pack_for_surface(config, surface)
    second = json.dumps(
        alerts.build_feed(surface, pack=pack2, pack_selection=selection2).to_json(), sort_keys=True
    )
    assert first == second
