"""Aggregation rolls up to the published grid and preserves the calibrated/provisional line."""

from __future__ import annotations

import json
import math
from typing import Any

import pytest

from swelter import aggregate
from swelter.config import CalibrationWindow, NetworkConfig, NodeConfig, ReferenceMonitor

from .conftest import make_obs

_NODE = NodeConfig(node_id="node-01", lat=38.5816, lon=-121.4944, location="precise")
_CONFIG = NetworkConfig(grid_resolution_m=150.0, nodes=(_NODE,))


def test_raw_only_cell_is_provisional_and_has_aqi() -> None:
    surface = aggregate.aggregate(
        [make_obs(parameter="pm25_ugm3", unit="ug/m3", value=12.0)], _CONFIG
    )
    assert len(surface.cells) == 1
    cell = surface.cells[0]
    assert cell.provisional is True
    assert cell.aqi is not None
    assert cell.category is not None


def test_calibrated_cell_is_not_provisional() -> None:
    surface = aggregate.aggregate(
        [make_obs(parameter="pm25_ugm3", unit="ug/m3", value=12.0, calibration="v1")], _CONFIG
    )
    assert surface.cells[0].provisional is False


def test_unplaced_node_is_excluded() -> None:
    config = NetworkConfig(nodes=(NodeConfig(node_id="node-01"),))
    surface = aggregate.aggregate(
        [make_obs(parameter="pm25_ugm3", unit="ug/m3", value=10.0, calibration="v1")], config
    )
    assert surface.cells == ()


def _exposure(surface: aggregate.Surface) -> list[aggregate.CellReading]:
    return [c for c in surface.cells if c.parameter == aggregate.EXPOSURE]


def test_exposure_needs_both_heat_and_air() -> None:
    # Only PM2.5 present → no exposure cell (the compound claim needs both axes).
    surface = aggregate.aggregate(
        [make_obs(parameter="pm25_ugm3", unit="ug/m3", value=12.0, calibration="v1")], _CONFIG
    )
    assert _exposure(surface) == []


def test_exposure_combines_calibrated_heat_and_air() -> None:
    surface = aggregate.aggregate(
        [
            make_obs(parameter="heat_index_c", value=35.0, calibration="v1"),  # Extreme Caution
            make_obs(
                parameter="pm25_ugm3", unit="ug/m3", value=40.0, calibration="v2"
            ),  # USG (level 2)
        ],
        _CONFIG,
    )
    exposure = _exposure(surface)
    assert len(exposure) == 1
    cell = exposure[0]
    assert cell.provisional is False
    assert cell.category == "Elevated"
    assert cell.compound is True
    assert cell.heat_category == "Extreme Caution"
    assert cell.air_category == "Unhealthy for Sensitive Groups"
    record = cell.as_record()
    assert record["compound"] is True
    assert record["air_category"] == "Unhealthy for Sensitive Groups"


def test_exposure_is_provisional_if_either_component_is() -> None:
    surface = aggregate.aggregate(
        [
            make_obs(parameter="heat_index_c", value=35.0),  # raw → provisional
            make_obs(parameter="pm25_ugm3", unit="ug/m3", value=40.0, calibration="v2"),
        ],
        _CONFIG,
    )
    exposure = _exposure(surface)
    assert len(exposure) == 1
    assert exposure[0].provisional is True


def test_confirmed_cell_carries_calibration_provenance() -> None:
    config = NetworkConfig(
        grid_resolution_m=150.0,
        nodes=(_NODE,),
        reference_monitors=(ReferenceMonitor(monitor_id="ref-aqs-0010", label="Regulatory AQS"),),
        calibration_windows=(CalibrationWindow("node-01", "ref-aqs-0010", "pm25_ugm3", "s", "e"),),
    )
    surface = aggregate.aggregate(
        [
            make_obs(
                parameter="pm25_ugm3",
                unit="ug/m3",
                value=12.0,
                calibration="pm25_ugm3.epa-humidity.node-01",
                uncertainty=0.9,
            )
        ],
        config,
    )
    pm = next(c for c in surface.cells if c.parameter == "pm25_ugm3")
    assert pm.provisional is False
    assert pm.method == "epa-humidity"
    assert pm.reference == "Regulatory AQS"
    assert pm.nodes == ("node-01",)
    record = pm.as_record()
    assert record["method"] == "epa-humidity"
    assert record["reference"] == "Regulatory AQS"
    assert record["nodes"] == ["node-01"]


def test_provisional_cell_has_no_provenance_keys() -> None:
    surface = aggregate.aggregate(
        [make_obs(parameter="pm25_ugm3", unit="ug/m3", value=12.0)], _CONFIG
    )
    record = surface.cells[0].as_record()
    assert "method" not in record and "reference" not in record


def test_snapshot_geojson_shape() -> None:
    surface = aggregate.aggregate(
        [
            make_obs(parameter="pm25_ugm3", unit="ug/m3", value=12.0, calibration="v1"),
            make_obs(parameter="temp_c", value=31.0, calibration="v2"),
        ],
        _CONFIG,
    )
    geojson: Any = json.loads(json.dumps(surface.snapshot_geojson()))
    assert geojson["type"] == "FeatureCollection"
    feature = geojson["features"][0]
    assert feature["geometry"]["type"] == "Point"
    assert "pm25_ugm3" in feature["properties"]
    assert "pm25_aqi" in feature["properties"]


# --- FIX-04: cell standard error vs mean-member-sigma ------------------------------------------


def test_cell_standard_error_is_reproducible_from_member_sigmas() -> None:
    """A statistician handed the per-observation sigmas should be able to reproduce the cell's
    published `uncertainty` (the cell standard error) *and* tell it apart from `mean_member_sigma`
    (the old, simpler mean-of-sigmas number) — the two must never be interchangeable."""
    sigmas = [0.9, 1.2, 0.5]
    values = [10.0, 12.0, 11.0]
    surface = aggregate.aggregate(
        [
            make_obs(parameter="pm25_ugm3", unit="ug/m3", value=v, calibration="v1", uncertainty=s)
            for v, s in zip(values, sigmas, strict=True)
        ],
        _CONFIG,
    )
    cell = surface.cells[0]
    expected_mean_member_sigma = sum(sigmas) / len(sigmas)
    expected_cell_se = math.sqrt(sum(s * s for s in sigmas)) / len(sigmas)

    assert cell.mean_member_sigma == pytest.approx(expected_mean_member_sigma)
    assert cell.uncertainty == pytest.approx(expected_cell_se)
    assert cell.uncertainty != pytest.approx(cell.mean_member_sigma)  # distinct, never conflated

    record = cell.as_record()
    assert record["mean_member_sigma"] == round(expected_mean_member_sigma, 3)
    assert record["uncertainty"] == round(expected_cell_se, 3)


def test_provisional_cell_has_no_sigma_of_either_kind() -> None:
    surface = aggregate.aggregate(
        [make_obs(parameter="pm25_ugm3", unit="ug/m3", value=12.0)], _CONFIG
    )
    cell = surface.cells[0]
    assert cell.uncertainty is None
    assert cell.mean_member_sigma is None


# --- FIX-04: exposure cells carry a component-bounded uncertainty statement ---------------------


def test_exposure_note_names_both_when_heat_and_air_tie() -> None:
    surface = aggregate.aggregate(
        [
            make_obs(parameter="heat_index_c", value=35.0, calibration="v1"),  # Extreme Caution
            make_obs(parameter="pm25_ugm3", unit="ug/m3", value=40.0, calibration="v2"),  # USG
        ],
        _CONFIG,
    )
    cell = _exposure(surface)[0]
    assert cell.uncertainty is None  # exposure never fabricates a σ
    assert cell.uncertainty_note is not None
    assert "heat" in cell.uncertainty_note
    assert "air" in cell.uncertainty_note
    assert cell.as_record()["uncertainty_note"] == cell.uncertainty_note


def test_exposure_note_names_air_with_numeric_uncertainty_when_air_bounds() -> None:
    surface = aggregate.aggregate(
        [
            make_obs(parameter="heat_index_c", value=20.0, calibration="v1"),  # None tier, 0
            make_obs(
                parameter="pm25_ugm3", unit="ug/m3", value=90.0, calibration="v2", uncertainty=0.9
            ),  # Unhealthy, level 3 -> bounds
        ],
        _CONFIG,
    )
    cell = _exposure(surface)[0]
    assert cell.uncertainty_note is not None
    assert cell.uncertainty_note.startswith("bounded by air")
    assert "Unhealthy" in cell.uncertainty_note
    assert "cell standard error" in cell.uncertainty_note


def test_exposure_note_names_heat_confirmed_without_numeric_uncertainty() -> None:
    surface = aggregate.aggregate(
        [
            make_obs(parameter="heat_index_c", value=45.0, calibration="v1"),  # Danger, level 3
            make_obs(parameter="pm25_ugm3", unit="ug/m3", value=5.0, calibration="v2"),  # Good, 0
        ],
        _CONFIG,
    )
    cell = _exposure(surface)[0]
    assert cell.uncertainty_note is not None
    assert cell.uncertainty_note.startswith("bounded by heat")
    assert "no numeric uncertainty" in cell.uncertainty_note
    assert "provisional" not in cell.uncertainty_note  # confirmed, just has no σ to report


def test_exposure_note_names_heat_when_provisional_heat_bounds() -> None:
    surface = aggregate.aggregate(
        [
            make_obs(parameter="heat_index_c", value=45.0),  # raw -> provisional, Danger, level 3
            make_obs(parameter="pm25_ugm3", unit="ug/m3", value=5.0),  # Good, level 0
        ],
        _CONFIG,
    )
    cell = _exposure(surface)[0]
    assert cell.uncertainty_note is not None
    assert cell.uncertainty_note.startswith("bounded by heat")
    assert "provisional" in cell.uncertainty_note


# --- FIX-04: EPA NowCast as a distinct aqi_window variant ---------------------------------------


def test_nowcast_reading_is_added_with_at_least_three_hours() -> None:
    obs = [
        make_obs(
            parameter="pm25_ugm3",
            unit="ug/m3",
            timestamp=f"2026-06-01T0{h}:00:00Z",
            value=v,
            calibration="v1",
        )
        for h, v in enumerate([8.0, 10.0, 12.0])
    ]
    surface = aggregate.aggregate(obs, _CONFIG)
    pm25_cells = [c for c in surface.cells if c.parameter == "pm25_ugm3"]
    hourly = [c for c in pm25_cells if c.aqi_window == "hourly-mean"]
    nowcast = [c for c in pm25_cells if c.aqi_window == "nowcast"]
    assert len(hourly) == 3
    assert len(nowcast) == 1


def test_hourly_mean_and_nowcast_never_share_an_aqi_window_tag() -> None:
    obs = [
        make_obs(
            parameter="pm25_ugm3",
            unit="ug/m3",
            timestamp=f"2026-06-01T0{h}:00:00Z",
            value=v,
            calibration="v1",
        )
        for h, v in enumerate([8.0, 10.0, 12.0])
    ]
    surface = aggregate.aggregate(obs, _CONFIG)
    pm25_cells = [c for c in surface.cells if c.parameter == "pm25_ugm3"]
    # every pm25 cell carries exactly one of the two tags, and the set never blends them into one
    assert {c.aqi_window for c in pm25_cells} == {"hourly-mean", "nowcast"}
    for cell in pm25_cells:
        record = cell.as_record()
        assert record["aqi_window"] in ("hourly-mean", "nowcast")

    # the map snapshot promises the hourly mean, never the NowCast value, for the same cell/param
    latest = surface.latest_by_cell()
    cell_id = pm25_cells[0].cell_id
    assert latest[cell_id]["pm25_ugm3"].aqi_window == "hourly-mean"


def test_nowcast_absent_with_fewer_than_three_hours() -> None:
    surface = aggregate.aggregate(
        [make_obs(parameter="pm25_ugm3", unit="ug/m3", value=12.0, calibration="v1")], _CONFIG
    )
    pm25_cells = [c for c in surface.cells if c.parameter == "pm25_ugm3"]
    assert len(pm25_cells) == 1
    assert pm25_cells[0].aqi_window == "hourly-mean"
