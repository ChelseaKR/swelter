"""The data-model invariants the rest of the system relies on."""

from __future__ import annotations

import math
from dataclasses import FrozenInstanceError

import pytest

from swelter.models import (
    PARAMETERS,
    RAW,
    exposure_level,
    format_timestamp,
    heat_index_c,
    heat_index_category,
    parse_timestamp,
    pm25_aqi,
    wbgt_c,
)

from .conftest import make_obs


def test_observation_is_immutable() -> None:
    obs = make_obs()
    with pytest.raises(FrozenInstanceError):
        obs.value = 99.0  # type: ignore[misc]  # the frozen guard must fire at runtime


def test_content_hash_is_stable_and_value_sensitive() -> None:
    a = make_obs(value=25.0)
    b = make_obs(value=25.0)
    c = make_obs(value=25.1)
    assert a.content_hash() == b.content_hash()
    assert a.content_hash() != c.content_hash()


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
