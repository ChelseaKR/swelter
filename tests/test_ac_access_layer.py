"""The AC-access dataset validates strictly, stays descriptive, and keeps its provenance."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest

from swelter import ac_access_layer

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "data" / "ac_access_layer.geojson"


def _feature(**props: Any) -> dict[str, Any]:
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [-121.5, 38.57]},
        "properties": props,
    }


def _collection(*features: dict[str, Any]) -> dict[str, Any]:
    return {"type": "FeatureCollection", "features": list(features)}


def test_committed_dataset_loads_and_validates() -> None:
    dataset = ac_access_layer.load(DATASET)
    assert len(dataset.cells) >= 1
    assert dataset.license
    assert dataset.last_verified
    assert dataset.source


def test_committed_dataset_provenance_is_per_feature() -> None:
    dataset = ac_access_layer.load(DATASET)
    for cell in dataset.cells:
        assert cell.source and cell.last_verified, f"{cell.cell_id} lacks provenance"
        assert cell.source_url.startswith("https://")


def test_committed_dataset_cell_ids_are_joinable() -> None:
    dataset = ac_access_layer.load(DATASET)
    by_id = dataset.by_cell_id()
    assert len(by_id) == len(dataset.cells)
    for cell_id, cell in by_id.items():
        assert cell_id == f"{cell.lat:.6f},{cell.lon:.6f}"


def test_parse_rejects_missing_no_ac_pct() -> None:
    with pytest.raises(ac_access_layer.ACAccessLayerError):
        ac_access_layer.parse(_collection(_feature(notes="no measurement")))


def test_parse_rejects_out_of_range_no_ac_pct() -> None:
    with pytest.raises(ac_access_layer.ACAccessLayerError):
        ac_access_layer.parse(_collection(_feature(no_ac_pct=142.0)))


def test_parse_rejects_negative_no_ac_pct() -> None:
    with pytest.raises(ac_access_layer.ACAccessLayerError):
        ac_access_layer.parse(_collection(_feature(no_ac_pct=-3.0)))


def test_parse_rejects_non_numeric_no_ac_pct() -> None:
    with pytest.raises(ac_access_layer.ACAccessLayerError):
        ac_access_layer.parse(_collection(_feature(no_ac_pct="mostly")))


def test_parse_rejects_boolean_no_ac_pct() -> None:
    with pytest.raises(ac_access_layer.ACAccessLayerError):
        ac_access_layer.parse(_collection(_feature(no_ac_pct=True)))


def test_parse_rejects_out_of_range_coordinate() -> None:
    bad = {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [-999.0, 38.5]},
        "properties": {"no_ac_pct": 20.0},
    }
    with pytest.raises(ac_access_layer.ACAccessLayerError):
        ac_access_layer.parse(_collection(bad))


def test_parse_rejects_non_point_geometry() -> None:
    bad = {
        "type": "Feature",
        "geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 1]]},
        "properties": {"no_ac_pct": 20.0},
    }
    with pytest.raises(ac_access_layer.ACAccessLayerError):
        ac_access_layer.parse(_collection(bad))


@pytest.mark.parametrize("field", ["rank", "score", "vulnerability", "priority", "index", "grade"])
def test_parse_rejects_any_composite_or_ranking_field(field: str) -> None:
    with pytest.raises(ac_access_layer.ACAccessLayerError):
        ac_access_layer.parse(_collection(_feature(no_ac_pct=20.0, **{field: 1})))


def test_cell_id_defaults_from_coordinates_when_absent() -> None:
    dataset = ac_access_layer.parse(_collection(_feature(no_ac_pct=10.0)))
    assert dataset.cells[0].cell_id == "38.570000,-121.500000"


def test_empty_dataset_is_valid() -> None:
    gj = ac_access_layer.empty().to_geojson()
    assert gj["features"] == []
    assert cast(dict[str, object], gj["metadata"])["count"] == 0


def test_from_cells_builds_a_set() -> None:
    cell = ac_access_layer.ACAccessCell(lat=38.57, lon=-121.5, no_ac_pct=15.0)
    dataset = ac_access_layer.from_cells([cell])
    assert dataset.cells == (cell,)


def test_to_geojson_roundtrip_preserves_fields() -> None:
    dataset = ac_access_layer.parse(
        {
            "type": "FeatureCollection",
            "metadata": {
                "license": "Public domain",
                "source": "test",
                "last_verified": "2026-07-09",
            },
            "features": [
                _feature(no_ac_pct=27.5, notes="test note", cell_id="38.570000,-121.500000")
            ],
        }
    )
    gj = dataset.to_geojson()
    feature = cast(list[dict[str, Any]], gj["features"])[0]
    assert feature["properties"]["no_ac_pct"] == 27.5
    ac_access_layer.parse(gj)  # roundtrip re-parses cleanly
