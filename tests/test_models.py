"""The data-model invariants the rest of the system relies on."""

from __future__ import annotations

import math
import re
from dataclasses import FrozenInstanceError

import pytest

from swelter.models import (
    PARAMETERS,
    RAW,
    Observation,
    derive_heat_metrics,
    exposure_bounding_component,
    exposure_level,
    format_timestamp,
    heat_index_c,
    heat_index_category,
    is_within_range,
    nowcast_aqi,
    nowcast_concentration,
    parse_timestamp,
    pm25_aqi,
    wbgt_c,
    wind_chill_c,
    wind_chill_category,
)

from .conftest import make_obs


def test_observation_is_immutable() -> None:
    obs = make_obs()
    with pytest.raises(FrozenInstanceError):
        field = "value"
        setattr(obs, field, 99.0)  # the frozen guard must fire at runtime


def test_content_hash_is_stable_and_value_sensitive() -> None:
    a = make_obs(value=25.0)
    b = make_obs(value=25.0)
    c = make_obs(value=25.1)
    assert a.content_hash() == b.content_hash()
    assert a.content_hash() != c.content_hash()


def test_content_hash_covers_source_identity() -> None:
    native = make_obs(source="native")
    imported = make_obs(source="openmeteo")
    assert native.content_hash() != imported.content_hash()


def test_calibration_state_drives_trust() -> None:
    raw = make_obs()
    assert raw.calibration == RAW
    assert not raw.is_calibrated
    assert not raw.is_trustworthy  # raw is never "trustworthy" for the map

    calibrated = raw.calibrated("temp_c.enclosure-offset.node-01", 24.2, 0.5)
    assert calibrated.is_calibrated
    assert calibrated.is_trustworthy
    assert calibrated.uncertainty == 0.5
    # the original is untouched — provenance is additive, never destructive
    assert raw.value == 25.0


def test_a_calibrated_observation_without_an_uncertainty_is_refused() -> None:
    # Issue #147. A correction is fitted from recorded co-location evidence and always has a
    # `residual_std`, so a calibrated value with no 1-sigma is a broken row, not a zero-uncertainty
    # one. Unenforced, it reached the rollup and was read as a perfect instrument, *shrinking* the
    # published error bar. `calibrate.apply` never wrote one, but nothing stopped an import path or
    # a restored archive from doing so — the boundary they all pass through is this constructor.
    with pytest.raises(ValueError, match="no uncertainty"):
        Observation(
            node_id="node-01",
            timestamp="2026-06-01T00:00:00Z",
            parameter="temp_c",
            value=24.2,
            unit="degC",
            calibration="temp_c.enclosure-offset.node-01",
            uncertainty=None,
        )

    # A raw row with no uncertainty is the normal, legitimate case and stays allowed; a calibrated
    # row with a *measured* zero is a real fit, not an absence, and stays allowed too.
    assert make_obs().uncertainty is None
    assert make_obs(calibration="v1", uncertainty=0.0).uncertainty == 0.0


def test_qc_rejected_is_not_trustworthy_even_if_calibrated() -> None:
    obs = make_obs(calibration="v1", qc="range")
    assert obs.is_calibrated
    assert not obs.is_trustworthy


def test_timestamp_roundtrip_normalises_to_utc_z() -> None:
    assert format_timestamp(parse_timestamp("2026-06-01T12:00:00+02:00")) == "2026-06-01T10:00:00Z"
    assert format_timestamp(parse_timestamp("2026-06-01T00:00:00Z")) == "2026-06-01T00:00:00Z"


@pytest.mark.parametrize(
    ("conc", "category"),
    [
        (0.0, "Good"),
        (5.0, "Good"),
        (20.0, "Moderate"),
        (45.0, "Unhealthy for Sensitive Groups"),
        (90.0, "Unhealthy"),
        (180.0, "Very Unhealthy"),
        (300.0, "Hazardous"),
        (999.0, "Hazardous"),
    ],
)
def test_pm25_aqi_categories(conc: float, category: str) -> None:
    aqi, label = pm25_aqi(conc)
    assert label == category
    assert 0 <= aqi <= 500


def test_heat_index_passthrough_below_threshold() -> None:
    assert heat_index_c(20.0, 50.0) == 20.0  # regression not meaningful when cool
    assert heat_index_c(35.0, 70.0) > 35.0  # humid heat feels hotter


def test_wbgt_c_is_registered_and_plausible() -> None:
    assert "wbgt_c" in PARAMETERS
    assert PARAMETERS["wbgt_c"].unit == "degC"

    temp_c, humidity_pct = 35.0, 50.0
    tw = (
        temp_c * math.atan(0.151977 * math.sqrt(humidity_pct + 8.313659))
        + math.atan(temp_c + humidity_pct)
        - math.atan(humidity_pct - 1.676331)
        + 0.00391838 * humidity_pct**1.5 * math.atan(0.023101 * humidity_pct)
        - 4.686035
    )
    estimate = wbgt_c(temp_c, humidity_pct)
    # Shade WBGT sits strictly between the natural wet-bulb temperature and the dry-bulb (air)
    # temperature — a weighted blend of the two — and never above the dry-bulb reading.
    assert round(tw, 2) < estimate < temp_c


def test_wbgt_c_nan_propagates() -> None:
    assert math.isnan(wbgt_c(float("nan"), 50.0))
    assert math.isnan(wbgt_c(35.0, float("nan")))


def test_is_within_range_matches_the_published_bounds() -> None:
    assert is_within_range("temp_c", 20.0)
    assert is_within_range("temp_c", -40.0)  # the bounds are inclusive
    assert is_within_range("temp_c", 60.0)
    assert not is_within_range("temp_c", -40.01)
    assert not is_within_range("temp_c", 60.01)
    assert not is_within_range("temp_c", float("nan"))
    assert not is_within_range("humidity_pct", 100.1)
    assert not is_within_range("humidity_pct", -0.1)
    assert is_within_range("not_a_parameter", 1e9)  # no bounds to fail


def test_derive_heat_metrics_derives_from_plausible_inputs() -> None:
    derived = derive_heat_metrics(35.0, 50.0)
    assert derived == {"heat_index_c": heat_index_c(35.0, 50.0), "wbgt_c": wbgt_c(35.0, 50.0)}


@pytest.mark.parametrize(
    ("temp_c", "humidity_pct"),
    [
        (-41.0, 50.0),  # yielded an in-range WBGT of -39.48 and was mapped as a clean reading
        (-40.01, 0.0),  # yielded an in-range WBGT of -27.21
        (-145.72, 100.0),  # the ≈-145 °C fault seen live on Sensor.Community
        (80.0, 10.0),  # a sun-baked enclosure: yielded an in-range WBGT of 53.11
        (60.5, 90.0),  # just past the ceiling: yielded an in-range WBGT of 59.21
        (35.0, 110.0),  # a condensing sensor: yielded an in-range WBGT of 36.16
        (30.0, 200.0),  # yielded an in-range WBGT of 40.26
        (35.0, -1.0),  # negative RH still yielded an in-range heat index of 32.61
    ],
)
def test_no_derived_heat_metric_from_a_rejected_input(temp_c: float, humidity_pct: float) -> None:
    """An input outside its range is ``QC_RANGE`` → ``QC_UNMAPPABLE`` → never placed on a cell
    (ADR 0029). Deriving from it produced a value that landed back *inside* the derived
    parameter's own range, so QC could not tell it from a real reading and the map published a
    broken sensor's arithmetic as a clean, unflagged measurement (ADR 0041). Every case here is
    one that used to leak; none may derive anything now."""
    assert not is_within_range("temp_c", temp_c) or not is_within_range(
        "humidity_pct", humidity_pct
    ), "the fixture must actually be a rejected input, or it proves nothing"
    assert derive_heat_metrics(temp_c, humidity_pct) == {}


def test_derive_heat_metrics_drops_a_derived_value_outside_its_own_range() -> None:
    """In-range inputs can still put a derived value out of range; it is not emitted either."""
    derived = derive_heat_metrics(50.0, 90.0)  # real bounds, but no meaningful heat index
    assert heat_index_c(50.0, 90.0) > PARAMETERS["heat_index_c"].valid_max
    assert "heat_index_c" not in derived
    assert derived["wbgt_c"] == wbgt_c(50.0, 90.0)  # WBGT stays in range, so it survives


def test_derive_heat_metrics_rejects_nonfinite_inputs() -> None:
    assert derive_heat_metrics(float("nan"), 50.0) == {}
    assert derive_heat_metrics(35.0, float("nan")) == {}
    assert derive_heat_metrics(float("inf"), 50.0) == {}


@pytest.mark.parametrize("humidity_pct", [0.0, 1.0, 1.99])
def test_a_dead_probe_humidity_is_outside_the_published_range(humidity_pct: float) -> None:
    """A capacitive probe whose readout fails lands on its scale floor. Measured live on
    2026-08-19, every Sensor.Community humidity reading at or below 5 %RH was exactly ``0.0``
    (BME280, 1) or exactly ``1.0`` (DHT22, 25), with nothing between ``1.0`` and the lowest real
    reading of 7.0 %RH. Both sentinels used to sit *inside* ``[0.0, 100.0]``, so nothing flagged
    them (ADR 0043)."""
    assert not is_within_range("humidity_pct", humidity_pct)


@pytest.mark.parametrize(("temp_c", "humidity_pct"), [(46.2, 1.0), (35.0, 0.0), (30.3, 1.0)])
def test_no_derived_heat_metric_from_a_dead_humidity_probe(
    temp_c: float, humidity_pct: float
) -> None:
    """The whole point of the floor: no estimated WBGT reaches the map from a dead probe.

    Each pair is a real (temperature, humidity) reading taken from the live feed on 2026-08-19.
    The published estimated WBGT was 6 to 14 degC **below** the same temperature at a plausible
    humidity — always toward "safe", on a heat-safety surface (ADR 0043)."""
    assert is_within_range("temp_c", temp_c), "the temperature must be the plausible half"
    assert wbgt_c(temp_c, humidity_pct) < wbgt_c(temp_c, 55.0) - 5.0, (
        "the fixture must actually under-report by a wide margin, or it proves nothing"
    )
    assert derive_heat_metrics(temp_c, humidity_pct) == {}


def test_the_humidity_floor_admits_genuinely_very_dry_readings() -> None:
    """The floor clears the sentinels without deleting real dry air.

    Model output over desert California really does reach single-digit %RH: on 2026-08-19 the
    published store held 1,121 humidity rows at or below 7 %RH, decaying smoothly (458 at 7,
    322 at 6, 213 at 5, 103 at 4, 21 at 3, 3 at 2, 1 at 1). A floor set to the *lowest sampled*
    value rather than to the sentinels would have thrown all of those away (ADR 0043)."""
    assert PARAMETERS["humidity_pct"].valid_min == 2.0
    for genuinely_dry in (2.0, 3.0, 4.0, 5.0, 7.0):  # the bound is inclusive, like every other
        assert is_within_range("humidity_pct", genuinely_dry)
        assert derive_heat_metrics(35.0, genuinely_dry) != {}


def test_heat_index_category_bands() -> None:
    assert heat_index_category(20.0) == (0, "None")  # below the Caution floor
    assert heat_index_category(28.0) == (1, "Caution")
    assert heat_index_category(35.0) == (2, "Extreme Caution")
    assert heat_index_category(45.0) == (3, "Danger")
    assert heat_index_category(52.0) == (4, "Extreme Danger")


def test_exposure_takes_the_higher_concern() -> None:
    # Air drives it: cool but Unhealthy air → level 3 "High", heat tier too low for compound.
    assert exposure_level(20.0, "Unhealthy") == (3, "High", False)
    # Heat drives it: Danger heat but Good air → level 3 "High", air too low for compound.
    assert exposure_level(45.0, "Good") == (3, "High", False)


def test_exposure_flags_compound_when_both_elevated() -> None:
    # Extreme Caution heat (2) AND Unhealthy-for-Sensitive air (2): both mid-tier → compound.
    level, name, compound = exposure_level(35.0, "Unhealthy for Sensitive Groups")
    assert (level, name) == (2, "Elevated")
    assert compound is True


def test_exposure_bounding_component_names_the_dominant_axis() -> None:
    assert exposure_bounding_component(20.0, "Unhealthy") == "air"  # air drives, per the test above
    assert exposure_bounding_component(45.0, "Good") == "heat"  # heat drives, per the test above
    # Extreme Caution heat (2) tied with Unhealthy-for-Sensitive air (2): neither alone bounds it.
    assert exposure_bounding_component(35.0, "Unhealthy for Sensitive Groups") == "both"


def test_nowcast_aqi_none_below_three_hours() -> None:
    assert nowcast_aqi([]) is None
    assert nowcast_aqi([10.0]) is None
    assert nowcast_aqi([10.0, 12.0]) is None
    assert nowcast_concentration([10.0, 12.0]) is None


def test_nowcast_aqi_hand_computed_example() -> None:
    # Most-recent-first hourly means 12, 10, 8 ug/m3. min/max = 8/12 = 0.6667 (above the 0.5
    # floor), so weight w = 0.6667. NowCast = (12*w^0 + 10*w^1 + 8*w^2) / (w^0 + w^1 + w^2)
    #   = (12 + 6.6667 + 3.5556) / (1 + 0.6667 + 0.4444) = 22.2222 / 2.1111 ≈ 10.526 ug/m3,
    # which lands in the EPA "Moderate" band (9.1-35.4 ug/m3 -> AQI 51-100) at AQI 54.
    window = [12.0, 10.0, 8.0]
    conc = nowcast_concentration(window)
    assert conc is not None
    assert conc == pytest.approx(10.526315789473683)

    result = nowcast_aqi(window)
    assert result is not None
    aqi, category = result
    assert (aqi, category) == (54, "Moderate")
    # nowcast_aqi is exactly nowcast_concentration + pm25_aqi's own breakpoint table/truncation —
    # never a separately-drifting lookup.
    assert result == pm25_aqi(conc)


def test_nowcast_concentration_uses_at_most_the_trailing_twelve_hours() -> None:
    # A 13th (oldest) hour with an outlier value must not move the result at all.
    window = [10.0] * 12
    outlier_appended = [*window, 1000.0]
    assert nowcast_concentration(window) == nowcast_concentration(outlier_appended)


# -- wind chill: the reference implementation for a node that reports it -----------------------
#
# `wind_chill_c` and `wind_chill_category` had no unit test in this module at all: every mutant
# mutmut generated for them reported `no_tests`, so the published NWS coefficients, the domain
# boundary, and the frostbite band were unprotected by the core-safety gate.


def test_wind_chill_c_reproduces_the_published_nws_index() -> None:
    # NWS/Environment Canada 2001 North American revision, metric form:
    #   WCT = 13.12 + 0.6215*T - 11.37*V^0.16 + 0.3965*T*V^0.16   (T in degC, V in km/h)
    # Hand-checked against that formula, so a drifted coefficient or a flipped operator moves
    # these numbers rather than passing silently.
    # https://www.weather.gov/safety/cold-wind-chill-chart
    assert wind_chill_c(0.0, 32.0) == -6.68
    assert wind_chill_c(-10.0, 20.0) == -17.86
    assert wind_chill_c(-20.0, 50.0) == -35.4


def test_wind_chill_c_applies_exactly_on_its_documented_domain_edges() -> None:
    # The index is defined for temp_c <= 10 and wind_kph > 4.8; both edges belong to the index,
    # and the first step outside either one is the passthrough.
    assert wind_chill_c(10.0, 40.0) == 5.97  # exactly at the warm ceiling: still wind chill
    assert wind_chill_c(-5.0, 4.9) == -7.21  # just over the calm floor: still wind chill
    assert wind_chill_c(10.1, 40.0) == 10.1  # too warm for the index
    assert wind_chill_c(-5.0, 4.8) == -5.0  # calm enough that wind chill is not meaningful
    assert wind_chill_c(-5.0, 0.0) == -5.0


def test_wind_chill_c_rounds_both_branches_to_two_decimals() -> None:
    # Two decimals is the published resolution on both sides of the domain test; a passthrough
    # that echoed the input unrounded would leak more precision than the index claims.
    assert wind_chill_c(11.234, 40.0) == 11.23
    assert wind_chill_c(-3.126, 4.0) == -3.13


def test_wind_chill_c_nan_propagates_rather_than_raising() -> None:
    # A missing reading is a missing derived reading — the same convention `wbgt_c` uses.
    assert math.isnan(wind_chill_c(float("nan"), 20.0))
    assert math.isnan(wind_chill_c(-5.0, float("nan")))


def test_wind_chill_category_bands() -> None:
    # Colder is worse, so a reading crosses a band by falling at or below its ceiling. The NWS
    # chart publishes exactly one numeric frostbite boundary (-19 degF / -28.3 degC).
    assert wind_chill_category(0.0) == (0, "None")
    assert wind_chill_category(-28.2) == (0, "None")
    assert wind_chill_category(-28.3) == (1, "Frostbite in 30 min")  # the ceiling is in the band
    assert wind_chill_category(-45.0) == (1, "Frostbite in 30 min")


def test_wind_chill_category_rejects_nan() -> None:
    # A missing reading must not pose as a measurement, the same way `pm25_aqi` refuses NaN.
    with pytest.raises(ValueError, match="wind chill is NaN"):
        wind_chill_category(float("nan"))


# -- boundaries the published tables actually turn on ------------------------------------------


def test_pm25_aqi_breakpoints_are_inclusive_at_both_ends() -> None:
    # The EPA table has deliberate gaps between bands (9.0 then 9.1), so both ends of every
    # breakpoint belong to their band. A half-open comparison would drop a value into the gap
    # and fall through to the "Hazardous" clamp at the bottom of the function.
    assert pm25_aqi(9.0) == (50, "Good")
    assert pm25_aqi(9.1) == (51, "Moderate")
    assert pm25_aqi(35.4) == (100, "Moderate")
    assert pm25_aqi(35.5) == (101, "Unhealthy for Sensitive Groups")
    assert pm25_aqi(325.4) == (500, "Hazardous")
    assert pm25_aqi(325.5) == (500, "Hazardous")  # above the top band, clamped


def test_pm25_aqi_clamps_at_and_below_zero_but_not_above_it() -> None:
    assert pm25_aqi(0.0) == (0, "Good")
    assert pm25_aqi(-1.0) == (0, "Good")
    # 0.05 truncates to 0.0 and still runs the table rather than short-circuiting on the clamp,
    # so the clamp really is "at or below zero" and not "below one".
    assert pm25_aqi(0.05) == (0, "Good")
    assert pm25_aqi(1.0) == (6, "Good")


def test_pm25_aqi_rejects_nan_by_name() -> None:
    with pytest.raises(ValueError, match=re.escape("PM2.5 concentration is NaN")):
        pm25_aqi(float("nan"))


def test_heat_index_category_floors_are_inclusive() -> None:
    # The band floors are the published NWS values converted from degF; a reading exactly on a
    # floor is inside that band, not the one below it.
    assert heat_index_category(26.7) == (1, "Caution")
    assert heat_index_category(32.2) == (2, "Extreme Caution")
    assert heat_index_category(39.4) == (3, "Danger")
    assert heat_index_category(51.1) == (4, "Extreme Danger")


def test_heat_index_category_rejects_nan_by_name() -> None:
    with pytest.raises(ValueError, match="heat index is NaN"):
        heat_index_category(float("nan"))


def test_heat_index_passthrough_rounds_to_two_decimals() -> None:
    # Below the regression floor heat index *is* the air temperature, at the same two-decimal
    # resolution the regression branch reports.
    assert heat_index_c(20.126, 50.0) == 20.13


def test_exposure_bounding_component_needs_a_strictly_higher_axis() -> None:
    # Caution heat (1) against Good air (0): heat is strictly higher, so heat bounds it. A tie
    # reads "both" (covered above) — this pins that the comparison is strict in the other
    # direction too, so "heat" is never reported for a level heat did not actually set.
    assert exposure_bounding_component(28.0, "Good") == "heat"
    assert exposure_bounding_component(20.0, "Moderate") == "air"


def test_unknown_aqi_category_contributes_no_air_concern() -> None:
    # An unrecognised category must read as no elevated air concern, never as a mid-tier one:
    # a mislabelled band would otherwise silently raise the published exposure level.
    assert exposure_level(20.0, "not-a-published-category") == (0, "Minimal", False)
    assert exposure_bounding_component(28.0, "not-a-published-category") == "heat"


def test_nowcast_concentration_of_an_all_zero_window_is_zero() -> None:
    # c_max == 0 has no range ratio to take, so the weight falls back to 1.0 (a flat average)
    # rather than dividing by zero.
    assert nowcast_concentration([0.0, 0.0, 0.0]) == 0.0


def test_parse_timestamp_assumes_utc_for_a_naive_reading() -> None:
    # A node that omits the offset is read as UTC rather than as the reader's local clock, so
    # the same payload parses identically wherever the pipeline runs.
    assert format_timestamp(parse_timestamp("2026-06-01T12:00:00")) == "2026-06-01T12:00:00Z"
