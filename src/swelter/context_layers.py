"""Context-layer overlay: a curated, provenance-bearing, *strictly descriptive* per-cell dataset.

A heat map tells a resident how hot it is; it does not tell them why the same afternoon lands
differently two blocks apart. Tree canopy is core to that story — the research base this project
follows cites canopy inequity as a driver of unequal heat exposure. This module loads a curated
GeoJSON dataset of one descriptive measurement per grid cell (currently: percent tree-canopy
cover) and hands it to the API and the dashboard, which draws it as a toggleable map overlay next
to the sensor readings — two honest layers a viewer relates, side by side.

This is deliberately *not* a second `cooling_centers.py` clone with different labels: it exists to
enforce one rule the whole "context layer" family must follow. A context layer publishes a single
descriptive measurement (a percentage, a category, a count) with its provenance — never a
swelter-computed score, ranking, or index that blends canopy with anything else. That boundary is
the same one the exposure layer and the coverage-equity refusal already draw elsewhere in this
codebase: swelter shows what a dataset says, not a synthesized verdict about a neighborhood.
``ALLOWED_PROPERTIES`` enforces this at the schema level, not just in prose — there is no field a
future edit could repurpose into a ranking.

The dataset is *public-domain context* data, not sensor data: it is curated and versioned, carries
explicit provenance (a source, a source URL, and a ``last_verified`` date per feature and for the
set), and is licensed in its own metadata — it is **not** part of the CC0 observation stream, and
it is not derived from or blended with any node reading.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

#: The only properties a context-layer feature may carry. ``canopy_pct`` is the sole descriptive
#: measurement this module knows how to publish; there is intentionally no "score", "rank", or
#: "vulnerability" field in this allowlist, so a future edit cannot smuggle a composite index onto
#: the map through this dataset. Adding a new descriptive property is a deliberate, reviewed change
#: to this set, not a silent schema drift.
ALLOWED_PROPERTIES: Final[frozenset[str]] = frozenset(
    {
        "cell_id",  # the published grid cell this measurement describes (matches aggregate.py)
        "canopy_pct",  # percent tree-canopy cover for the cell, 0-100 — the only measurement
        "notes",  # short public note about the measurement (e.g. survey year, method caveat)
        "source",  # who published this record
        "source_url",  # where it came from
        "last_verified",  # ISO date this entry was last checked
    }
)

#: Properties a feature cannot be published without.
REQUIRED_PROPERTIES: Final[tuple[str, ...]] = ("canopy_pct",)


class ContextLayerError(ValueError):
    """Raised when the context-layer dataset is malformed or carries a disallowed field."""


@dataclass(frozen=True)
class ContextCell:
    """One grid cell's descriptive tree-canopy measurement, with its provenance.

    ``canopy_pct`` is a plain percentage read from the source dataset — not a derived score. A
    resident or organizer relates this to the heat surface by reading both layers, the same way
    they would read two labelled columns in a table; swelter never combines them into a single
    computed number.
    """

    lat: float
    lon: float
    canopy_pct: float
    cell_id: str = ""
    notes: str = ""
    source: str = ""
    source_url: str = ""
    last_verified: str = ""

    def as_feature(self) -> dict[str, object]:
        props: dict[str, object] = {"canopy_pct": self.canopy_pct}
        if self.cell_id:
            props["cell_id"] = self.cell_id
        if self.notes:
            props["notes"] = self.notes
        if self.source:
            props["source"] = self.source
        if self.source_url:
            props["source_url"] = self.source_url
        if self.last_verified:
            props["last_verified"] = self.last_verified
        return {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [self.lon, self.lat]},
            "properties": props,
        }


@dataclass(frozen=True)
class ContextLayerSet:
    """A validated dataset of per-cell context measurements plus its set-level provenance."""

    cells: tuple[ContextCell, ...]
    license: str = ""
    attribution: str = ""
    source: str = ""
    last_verified: str = ""

    def to_geojson(self) -> dict[str, object]:
        """The normalized, validated dataset as a GeoJSON FeatureCollection with metadata."""
        return {
            "type": "FeatureCollection",
            "metadata": {
                "license": self.license,
                "attribution": self.attribution,
                "source": self.source,
                "last_verified": self.last_verified,
                "count": len(self.cells),
            },
            "features": [c.as_feature() for c in self.cells],
        }

    def by_cell_id(self) -> dict[str, ContextCell]:
        """``cell_id`` → cell, for joining this layer onto the surface's own cell keys."""
        return {c.cell_id: c for c in self.cells if c.cell_id}


def _canopy_pct(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ContextLayerError(f"{name}: canopy_pct must be a number")
    pct = float(value)
    if not (0.0 <= pct <= 100.0):
        raise ContextLayerError(f"{name}: canopy_pct {pct} is out of range 0-100")
    return pct


def _coordinate(geometry: Any, name: str) -> tuple[float, float]:
    if not isinstance(geometry, dict) or geometry.get("type") != "Point":
        raise ContextLayerError(f"{name}: geometry must be a GeoJSON Point")
    coords = geometry.get("coordinates")
    if not isinstance(coords, (list, tuple)) or len(coords) < 2:
        raise ContextLayerError(f"{name}: Point needs [lon, lat] coordinates")
    lon, lat = float(coords[0]), float(coords[1])
    if not (-180.0 <= lon <= 180.0 and -90.0 <= lat <= 90.0):
        raise ContextLayerError(f"{name}: coordinate {lat},{lon} is out of range")
    return lat, lon


def parse(doc: dict[str, Any]) -> ContextLayerSet:
    """Validate an already-parsed FeatureCollection into a :class:`ContextLayerSet`."""
    if doc.get("type") != "FeatureCollection":
        raise ContextLayerError("dataset must be a GeoJSON FeatureCollection")
    features = doc.get("features")
    if not isinstance(features, list):
        raise ContextLayerError("dataset has no features list")
    cells: list[ContextCell] = []
    for i, feature in enumerate(features):
        if not isinstance(feature, dict):
            raise ContextLayerError(f"feature {i} is not an object")
        props = feature.get("properties") or {}
        if not isinstance(props, dict):
            raise ContextLayerError(f"feature {i}: properties must be an object")
        extra = set(props) - ALLOWED_PROPERTIES
        if extra:
            raise ContextLayerError(
                f"feature {i}: disallowed propert{'y' if len(extra) == 1 else 'ies'} "
                f"{sorted(extra)} — only documented descriptive fields are permitted"
            )
        missing = [p for p in REQUIRED_PROPERTIES if props.get(p) is None]
        if missing:
            raise ContextLayerError(f"feature {i}: missing required propert(ies) {missing}")
        lat, lon = _coordinate(feature.get("geometry"), f"feature {i}")
        canopy_pct = _canopy_pct(props.get("canopy_pct"), f"feature {i}")
        cell_id = str(props.get("cell_id") or "") or f"{lat:.6f},{lon:.6f}"
        cells.append(
            ContextCell(
                lat=lat,
                lon=lon,
                canopy_pct=canopy_pct,
                cell_id=cell_id,
                notes=str(props.get("notes") or ""),
                source=str(props.get("source") or ""),
                source_url=str(props.get("source_url") or ""),
                last_verified=str(props.get("last_verified") or ""),
            )
        )
    meta = doc.get("metadata") or {}
    if not isinstance(meta, dict):
        meta = {}
    return ContextLayerSet(
        cells=tuple(cells),
        license=str(meta.get("license") or ""),
        attribution=str(meta.get("attribution") or ""),
        source=str(meta.get("source") or ""),
        last_verified=str(meta.get("last_verified") or ""),
    )


def load(path: str | Path) -> ContextLayerSet:
    """Load and validate a context-layer GeoJSON dataset from disk."""
    raw: Any = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ContextLayerError("dataset root must be a JSON object")
    return parse(raw)


def empty() -> ContextLayerSet:
    """An empty, valid dataset — what the API serves when no dataset is configured."""
    return ContextLayerSet(cells=())


def from_cells(cells: Iterable[ContextCell]) -> ContextLayerSet:
    return ContextLayerSet(cells=tuple(cells))
