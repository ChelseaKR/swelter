"""The data-model invariants the rest of the system relies on."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from swelter.models import (
    RAW,
    format_timestamp,
    heat_index_c,
    parse_timestamp,
    pm25_aqi,
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
