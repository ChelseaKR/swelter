"""The cooling-center dataset validates strictly and keeps its provenance and field allowlist."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest

from swelter import cooling_centers

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "data" / "cooling_centers.geojson"


def _feature(**props: Any) -> dict[str, Any]:
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [-121.5, 38.57]},
        "properties": props,
    }


def _collection(*features: dict[str, Any]) -> dict[str, Any]:
    return {"type": "FeatureCollection", "features": list(features)}


def test_committed_dataset_loads_and_validates() -> None:
    dataset = cooling_centers.load(DATASET)
    assert len(dataset.centers) >= 1
    assert dataset.license  # the dataset carries its own license, separate from the CC0 readings
    assert dataset.last_verified  # external-fact data must carry a verified date
    assert dataset.source  # provenance is present


def test_committed_dataset_provenance_is_per_feature() -> None:
    dataset = cooling_centers.load(DATASET)
    for center in dataset.centers:
        assert center.source and center.last_verified, f"{center.name} lacks provenance"


def test_parse_rejects_missing_name() -> None:
    with pytest.raises(cooling_centers.CoolingCenterError):
        cooling_centers.parse(_collection(_feature(type="library")))


def test_parse_rejects_out_of_range_coordinate() -> None:
    bad = {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [-999.0, 38.5]},
        "properties": {"name": "Nowhere"},
    }
    with pytest.raises(cooling_centers.CoolingCenterError):
        cooling_centers.parse(_collection(bad))


def test_parse_rejects_disallowed_property() -> None:
    # A field outside the public allowlist (here a contact phone) must be refused, not published.
    with pytest.raises(cooling_centers.CoolingCenterError):
        cooling_centers.parse(_collection(_feature(name="Library", phone="555-1234")))


def test_parse_rejects_non_point_geometry() -> None:
    bad = {
        "type": "Feature",
        "geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 1]]},
        "properties": {"name": "Library"},
    }
    with pytest.raises(cooling_centers.CoolingCenterError):
        cooling_centers.parse(_collection(bad))


def test_to_geojson_roundtrip_preserves_fields() -> None:
    dataset = cooling_centers.parse(
        {
            "type": "FeatureCollection",
            "metadata": {"license": "CC-BY-4.0", "source": "test", "last_verified": "2026-06-29"},
            "features": [
                _feature(
                    name="Downtown Library",
                    type="library",
                    accessible=True,
                    air_conditioned=True,
                    hours="10-18",
                )
            ],
        }
    )
    gj = dataset.to_geojson()
    assert gj["type"] == "FeatureCollection"
    assert cast(dict[str, object], gj["metadata"])["license"] == "CC-BY-4.0"
    feature = cast(list[dict[str, Any]], gj["features"])[0]
    assert feature["geometry"]["type"] == "Point"
    assert feature["properties"]["accessible"] is True
    # A roundtrip re-parses cleanly (no field leaks past the allowlist).
    cooling_centers.parse(gj)


def test_empty_dataset_is_valid() -> None:
    gj = cooling_centers.empty().to_geojson()
    assert gj["features"] == []
    assert cast(dict[str, object], gj["metadata"])["count"] == 0


def test_non_bool_accessible_is_rejected() -> None:
    with pytest.raises(cooling_centers.CoolingCenterError):
        cooling_centers.parse(_collection(_feature(name="Library", accessible="yes")))
