"""The redlining dataset validates strictly, stays a historical fact (not a swelter score), and
keeps its provenance."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest

from swelter import redlining_layer

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "data" / "redlining_layer.geojson"


def _feature(**props: Any) -> dict[str, Any]:
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [-121.5, 38.57]},
        "properties": props,
    }


def _collection(*features: dict[str, Any]) -> dict[str, Any]:
    return {"type": "FeatureCollection", "features": list(features)}


def test_committed_dataset_loads_and_validates() -> None:
    dataset = redlining_layer.load(DATASET)
    assert len(dataset.cells) >= 1
    assert dataset.license
    assert dataset.last_verified
    assert dataset.source


def test_committed_dataset_provenance_is_per_feature() -> None:
    dataset = redlining_layer.load(DATASET)
    for cell in dataset.cells:
        assert cell.source and cell.last_verified, f"{cell.cell_id} lacks provenance"
        assert cell.source_url.startswith("https://")


def test_committed_dataset_grades_are_valid() -> None:
    dataset = redlining_layer.load(DATASET)
    for cell in dataset.cells:
        assert cell.holc_grade in redlining_layer.HOLC_GRADES
        assert cell.grade_label  # every valid grade has a plain-language label


def test_committed_dataset_cell_ids_are_joinable() -> None:
    dataset = redlining_layer.load(DATASET)
    by_id = dataset.by_cell_id()
    assert len(by_id) == len(dataset.cells)
    for cell_id, cell in by_id.items():
        assert cell_id == f"{cell.lat:.6f},{cell.lon:.6f}"


def test_parse_rejects_missing_holc_grade() -> None:
    with pytest.raises(redlining_layer.RedliningLayerError):
        redlining_layer.parse(_collection(_feature(notes="no grade")))


@pytest.mark.parametrize("bad_grade", ["E", "F", "1", "AA", ""])
def test_parse_rejects_invalid_holc_grade(bad_grade: str) -> None:
    with pytest.raises(redlining_layer.RedliningLayerError):
        redlining_layer.parse(_collection(_feature(holc_grade=bad_grade)))


def test_parse_accepts_lowercase_grade_and_normalizes() -> None:
    dataset = redlining_layer.parse(_collection(_feature(holc_grade="d")))
    assert dataset.cells[0].holc_grade == "D"
    assert dataset.cells[0].grade_label == "Hazardous"


def test_parse_rejects_non_string_holc_grade() -> None:
    with pytest.raises(redlining_layer.RedliningLayerError):
        redlining_layer.parse(_collection(_feature(holc_grade=4)))


def test_parse_rejects_out_of_range_coordinate() -> None:
    bad = {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [-999.0, 38.5]},
        "properties": {"holc_grade": "B"},
    }
    with pytest.raises(redlining_layer.RedliningLayerError):
        redlining_layer.parse(_collection(bad))


def test_parse_rejects_non_point_geometry() -> None:
    bad = {
        "type": "Feature",
        "geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 1]]},
        "properties": {"holc_grade": "B"},
    }
    with pytest.raises(redlining_layer.RedliningLayerError):
        redlining_layer.parse(_collection(bad))


@pytest.mark.parametrize("field", ["rank", "score", "vulnerability", "priority", "index"])
def test_parse_rejects_any_composite_or_ranking_field(field: str) -> None:
    # holc_grade itself is a historical fact from the source, not a swelter-computed field;
    # a synthetic ranking bolted on top of it is still refused.
    with pytest.raises(redlining_layer.RedliningLayerError):
        redlining_layer.parse(_collection(_feature(holc_grade="C", **{field: 1})))


def test_cell_id_defaults_from_coordinates_when_absent() -> None:
    dataset = redlining_layer.parse(_collection(_feature(holc_grade="A")))
    assert dataset.cells[0].cell_id == "38.570000,-121.500000"


def test_empty_dataset_is_valid() -> None:
    gj = redlining_layer.empty().to_geojson()
    assert gj["features"] == []
    assert cast(dict[str, object], gj["metadata"])["count"] == 0


def test_from_cells_builds_a_set() -> None:
    cell = redlining_layer.RedliningCell(lat=38.57, lon=-121.5, holc_grade="C")
    dataset = redlining_layer.from_cells([cell])
    assert dataset.cells == (cell,)


def test_to_geojson_roundtrip_preserves_fields() -> None:
    dataset = redlining_layer.parse(
        {
            "type": "FeatureCollection",
            "metadata": {
                "license": "CC BY-NC-SA 4.0",
                "source": "test",
                "last_verified": "2026-07-09",
            },
            "features": [
                _feature(holc_grade="D", notes="test note", cell_id="38.570000,-121.500000")
            ],
        }
    )
    gj = dataset.to_geojson()
    feature = cast(list[dict[str, Any]], gj["features"])[0]
    assert feature["properties"]["holc_grade"] == "D"
    redlining_layer.parse(gj)  # roundtrip re-parses cleanly
