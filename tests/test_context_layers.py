"""The context-layer dataset validates strictly, stays descriptive, and keeps its provenance."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from swelter import context_layers

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "data" / "context_layers.geojson"


def _feature(**props: Any) -> dict[str, Any]:
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [-121.5, 38.57]},
        "properties": props,
    }


def _collection(*features: dict[str, Any]) -> dict[str, Any]:
    return {"type": "FeatureCollection", "features": list(features)}


def test_committed_dataset_loads_and_validates() -> None:
    dataset = context_layers.load(DATASET)
    assert len(dataset.cells) >= 1
    assert dataset.license  # the dataset carries its own license, separate from the CC0 readings
    assert dataset.last_verified  # external-fact data must carry a verified date
    assert dataset.source  # provenance is present


def test_committed_dataset_provenance_is_per_feature() -> None:
    dataset = context_layers.load(DATASET)
    for cell in dataset.cells:
        assert cell.source and cell.last_verified, f"{cell.cell_id} lacks provenance"


def test_committed_dataset_cell_ids_are_joinable() -> None:
    dataset = context_layers.load(DATASET)
    by_id = dataset.by_cell_id()
    assert len(by_id) == len(dataset.cells)
    for cell_id, cell in by_id.items():
        assert cell_id == f"{cell.lat:.6f},{cell.lon:.6f}"


def test_parse_rejects_missing_canopy_pct() -> None:
    with pytest.raises(context_layers.ContextLayerError):
        context_layers.parse(_collection(_feature(notes="no measurement")))


def test_parse_rejects_out_of_range_canopy_pct() -> None:
    with pytest.raises(context_layers.ContextLayerError):
        context_layers.parse(_collection(_feature(canopy_pct=142.0)))


def test_parse_rejects_negative_canopy_pct() -> None:
    with pytest.raises(context_layers.ContextLayerError):
        context_layers.parse(_collection(_feature(canopy_pct=-3.0)))


def test_parse_rejects_non_numeric_canopy_pct() -> None:
    with pytest.raises(context_layers.ContextLayerError):
        context_layers.parse(_collection(_feature(canopy_pct="mostly")))


def test_parse_rejects_boolean_canopy_pct() -> None:
    # bool is a subclass of int in Python; make sure it is refused rather than coerced to 0/100.
    with pytest.raises(context_layers.ContextLayerError):
        context_layers.parse(_collection(_feature(canopy_pct=True)))


def test_parse_rejects_out_of_range_coordinate() -> None:
    bad = {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [-999.0, 38.5]},
        "properties": {"canopy_pct": 20.0},
    }
    with pytest.raises(context_layers.ContextLayerError):
        context_layers.parse(_collection(bad))


def test_parse_rejects_non_point_geometry() -> None:
    bad = {
        "type": "Feature",
        "geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 1]]},
        "properties": {"canopy_pct": 20.0},
    }
    with pytest.raises(context_layers.ContextLayerError):
        context_layers.parse(_collection(bad))


@pytest.mark.parametrize("field", ["rank", "score", "vulnerability", "priority", "index", "grade"])
def test_parse_rejects_any_composite_or_ranking_field(field: str) -> None:
    # The whole point of this module: no field can smuggle a swelter-computed score onto the map.
    with pytest.raises(context_layers.ContextLayerError):
        context_layers.parse(_collection(_feature(canopy_pct=20.0, **{field: 1})))


def test_to_geojson_roundtrip_preserves_fields() -> None:
    dataset = context_layers.parse(
        {
            "type": "FeatureCollection",
            "metadata": {"license": "CC-BY-4.0", "source": "test", "last_verified": "2026-07-08"},
            "features": [
                _feature(canopy_pct=27.5, notes="test note", cell_id="38.570000,-121.500000")
            ],
        }
    )
    gj = dataset.to_geojson()
    assert gj["type"] == "FeatureCollection"
    assert gj["metadata"]["license"] == "CC-BY-4.0"  # type: ignore[index]
    feature = gj["features"][0]  # type: ignore[index]
    assert feature["geometry"]["type"] == "Point"
    assert feature["properties"]["canopy_pct"] == 27.5
    # A roundtrip re-parses cleanly (no field leaks past the allowlist).
    context_layers.parse(gj)


def test_cell_id_defaults_from_coordinates_when_absent() -> None:
    dataset = context_layers.parse(_collection(_feature(canopy_pct=10.0)))
    assert dataset.cells[0].cell_id == "38.570000,-121.500000"


def test_empty_dataset_is_valid() -> None:
    gj = context_layers.empty().to_geojson()
    assert gj["features"] == []
    assert gj["metadata"]["count"] == 0  # type: ignore[index]


def test_from_cells_builds_a_set() -> None:
    cell = context_layers.ContextCell(lat=38.57, lon=-121.5, canopy_pct=15.0)
    dataset = context_layers.from_cells([cell])
    assert dataset.cells == (cell,)
