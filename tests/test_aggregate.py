"""Aggregation rolls up to the published grid and preserves the calibrated/provisional line."""

from __future__ import annotations

import json
from typing import Any

from swelter import aggregate
from swelter.config import NetworkConfig, NodeConfig

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
