"""Hazard packs: heat stays the default (unchanged), a network enables cold by config alone, and
every pack's danger floors are cited, versioned data (EXP-13 / ADR 0031)."""

from __future__ import annotations

import math

import pytest

from swelter import aggregate, alerts, hazard_packs
from swelter.config import NetworkConfig, NodeConfig, config_concerns, parse_config
from swelter.models import PARAMETERS, Observation, wind_chill_c, wind_chill_category

from .conftest import make_obs

_NODE = NodeConfig(
    node_id="node-01", label="Oak & 4th", lat=38.5816, lon=-121.4944, location="precise"
)
_HEAT_CONFIG = NetworkConfig(grid_resolution_m=150.0, nodes=(_NODE,))
_COLD_CONFIG = NetworkConfig(grid_resolution_m=150.0, nodes=(_NODE,), hazard_pack="cold")


def _feed(config: NetworkConfig, *obs: Observation) -> alerts.AlertFeed:
    """Build a feed exactly the way the CLI/server do: surface from config, pack from config."""
    surface = aggregate.aggregate(obs, config)
    return alerts.build_feed(
        surface,
        network="demo",
        base_url="https://example.org",
        thresholds=config.alert_thresholds or None,
        pack=hazard_packs.resolve_pack(config.hazard_pack),
    )


# -- the abstraction: heat is the default and is unchanged -----------------------------------


def test_heat_is_the_default_pack() -> None:
    for pack_id in (None, "", "heat"):
        assert hazard_packs.resolve_pack(pack_id) is hazard_packs.HEAT_PACK
    # An unknown id fails safe to heat (the hard error lives in config_concerns, not here).
    assert hazard_packs.resolve_pack("blizzard") is hazard_packs.HEAT_PACK


def test_heat_pack_floors_are_the_original_documented_values() -> None:
    # The whole point of "no behaviour change when unspecified": these are the exact floors the
    # feed always used, and the alerts module still exposes them under DEFAULT_THRESHOLDS.
    assert hazard_packs.HEAT_PACK.default_floors() == {
        "pm25_aqi": 101.0,
        "heat_index_c": 39.4,
        "exposure": 3.0,
    }
    assert dict(alerts.DEFAULT_THRESHOLDS) == hazard_packs.HEAT_PACK.default_floors()


def test_every_threshold_and_guidance_carries_a_public_citation() -> None:
    # Caveats travel (invariant 4): a floor with no source is just an opinion.
    for pack in hazard_packs.PACKS.values():
        assert pack.thresholds, f"{pack.pack_id} has no thresholds"
        cited = [t.citation for t in pack.thresholds] + list(pack.guidance)
        for citation in cited:
            assert citation.source and citation.detail
            assert citation.url.startswith("https://")
            assert citation.last_verified.count("-") == 2  # ISO YYYY-MM-DD


# -- the cold pack: what it watches ----------------------------------------------------------


def test_cold_pack_watches_wind_chill_and_keeps_air_quality() -> None:
    cold = hazard_packs.COLD_PACK
    assert cold.alerting_parameters() == ("pm25_ugm3", "wind_chill_c")
    assert "wind_chill_c" in cold.surface_parameters()
    assert cold.threshold_keys() == {"pm25_aqi", "wind_chill_c"}
    # Air quality is not seasonal: the same EPA floor is watched by both packs.
    assert cold.default_floors()["pm25_aqi"] == hazard_packs.HEAT_PACK.default_floors()["pm25_aqi"]


# -- the cold pack: wired through alerts, enabled by config alone -----------------------------


def test_config_alone_enables_a_cold_wind_chill_alert() -> None:
    # A directly-reported wind chill below the NWS 30-minute frostbite boundary, on a network whose
    # only cold-specific setting is `hazard_pack: cold`. aggregate must roll wind_chill_c up and
    # build_feed must check it — both driven purely off the config.
    feed = _feed(_COLD_CONFIG, make_obs(parameter="wind_chill_c", value=-30.0, calibration="v1"))
    assert len(feed.alerts) == 1
    alert = feed.alerts[0]
    assert alert.parameter == "wind_chill_c"
    assert alert.severity == "Frostbite in 30 min"
    assert alert.threshold == -28.3
    assert alert.unit == "degC"
    assert alert.area == "Oak & 4th"


def test_wind_chill_above_the_floor_is_quiet() -> None:
    # -20 °C is cold, but warmer than the -28.3 °C frostbite floor: colder is worse, so no alert.
    feed = _feed(_COLD_CONFIG, make_obs(parameter="wind_chill_c", value=-20.0, calibration="v1"))
    assert feed.alerts == ()


def test_provisional_wind_chill_alerts_but_is_flagged() -> None:
    feed = _feed(_COLD_CONFIG, make_obs(parameter="wind_chill_c", value=-30.0))  # raw
    assert len(feed.alerts) == 1
    assert feed.alerts[0].provisional is True


def test_cold_alert_headline_is_bilingual() -> None:
    feed = _feed(_COLD_CONFIG, make_obs(parameter="wind_chill_c", value=-30.0, calibration="v1"))
    alert = feed.alerts[0]
    en = alert.headline("en")
    es = alert.headline("es")
    assert "wind chill" in en and "-30" in en
    assert "sensación térmica" in es
    assert es != en


# -- the heat pack is untouched by the cold parameter ----------------------------------------


def test_heat_network_does_not_alert_on_wind_chill() -> None:
    # Same freezing reading, default (heat) network: the heat pack does not watch wind chill, so it
    # raises nothing — enabling a pack is what turns a hazard on, never the mere presence of data.
    feed = _feed(_HEAT_CONFIG, make_obs(parameter="wind_chill_c", value=-40.0, calibration="v1"))
    assert feed.alerts == ()


def test_heat_network_still_raises_heat_alerts() -> None:
    feed = _feed(_HEAT_CONFIG, make_obs(parameter="heat_index_c", value=41.0, calibration="v1"))
    assert len(feed.alerts) == 1
    assert feed.alerts[0].severity == "Danger"


# -- the wind-chill parameter itself ---------------------------------------------------------


def test_wind_chill_is_a_registered_parameter_with_cold_bounds() -> None:
    param = PARAMETERS["wind_chill_c"]
    assert param.unit == "degC"
    assert param.valid_min == -100.0  # colder than any other parameter's floor
    assert param.valid_max == 60.0


def test_wind_chill_formula_and_passthrough() -> None:
    # NWS/Environment-Canada metric wind chill: -10 °C air, 30 km/h wind → about -19.5 °C.
    assert wind_chill_c(-10.0, 30.0) == pytest.approx(-19.52, abs=0.01)
    # Not defined above 10 °C or in near-calm air → the air temperature passes through unchanged.
    assert wind_chill_c(15.0, 30.0) == 15.0
    assert wind_chill_c(-10.0, 3.0) == -10.0
    # A missing input yields a missing derived reading, not an exception.
    assert math.isnan(wind_chill_c(math.nan, 30.0))


def test_wind_chill_category_crosses_downward() -> None:
    assert wind_chill_category(-30.0) == (1, "Frostbite in 30 min")
    assert wind_chill_category(-28.3) == (1, "Frostbite in 30 min")  # at the floor is a crossing
    assert wind_chill_category(-20.0) == (0, "None")
    with pytest.raises(ValueError, match="NaN"):
        wind_chill_category(math.nan)


# -- config validation: enabling a pack, and overriding its floors ----------------------------


def test_unknown_hazard_pack_is_a_hard_error() -> None:
    config = parse_config({"hazard_pack": "warm"})
    errors, _ = config_concerns(config, {"hazard_pack": "warm"})
    assert any("unknown pack 'warm'" in e for e in errors)


def test_cold_network_accepts_its_own_threshold_key_and_rejects_heat_keys() -> None:
    # On a cold network, wind_chill_c is a valid override and heat_index_c is not (and vice versa),
    # because override keys are checked against the *active* pack's floors.
    ok_doc = {"hazard_pack": "cold", "alert_thresholds": {"wind_chill_c": -25.0}}
    ok_errors, _ = config_concerns(parse_config(ok_doc), ok_doc)
    assert not any("alert_thresholds" in e for e in ok_errors)

    bad_doc = {"hazard_pack": "cold", "alert_thresholds": {"heat_index_c": 39.4}}
    bad_errors, _ = config_concerns(parse_config(bad_doc), bad_doc)
    assert any("unknown key 'heat_index_c'" in e for e in bad_errors)


def test_cold_override_lowers_the_wind_chill_floor() -> None:
    # A collective can make the cold alert fire sooner (a warmer wind chill) via alert_thresholds.
    config = NetworkConfig(
        grid_resolution_m=150.0,
        nodes=(_NODE,),
        hazard_pack="cold",
        alert_thresholds={"wind_chill_c": -20.0},
    )
    feed = _feed(config, make_obs(parameter="wind_chill_c", value=-22.0, calibration="v1"))
    assert len(feed.alerts) == 1
    assert feed.alerts[0].threshold == -20.0
