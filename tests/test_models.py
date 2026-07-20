"""The data-model invariants the rest of the system relies on."""

from __future__ import annotations

import math
from dataclasses import FrozenInstanceError

import pytest

from swelter.models import (
    PARAMETERS,
    RAW,
    exposure_bounding_component,
    exposure_level,
    format_timestamp,
    heat_index_c,
    heat_index_category,
    nowcast_aqi,
    nowcast_concentration,
    parse_timestamp,
    pm25_aqi,
    wbgt_c,
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
