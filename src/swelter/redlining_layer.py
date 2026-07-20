"""Historical-redlining overlay: a curated, provenance-bearing, *strictly descriptive* per-cell
dataset of 1930s Home Owners' Loan Corporation (HOLC) "residential security" grades.

Redlining context belongs next to a heat/AQI reading for the same reason canopy does: it helps
explain why exposure lands unequally across a city today, without swelter computing a verdict
about it. This module follows the exact pattern :mod:`swelter.context_layers` set for tree
canopy (ADR 0023) and :mod:`swelter.ac_access_layer` for AC access: **one** descriptive
measurement per grid cell, plus its provenance.

The measurement here is a **historical fact**, not a swelter judgment: the letter grade
(A/B/C/D) a federal agency assigned to a neighborhood in 1935-1940, as digitized by the
`Mapping Inequality <https://dsl.richmond.edu/panorama/redlining/>`_ project (Digital
Scholarship Lab, University of Richmond). ``holc_grade`` is deliberately *not* a "score" or
"rank" the way those words are used in ``context_layers.ALLOWED_PROPERTIES`` — it is an exact,
single external fact (the grade HOLC itself published) carried with its source, the same way
``canopy_pct`` carries a tree-canopy survey's number. Rendering it is a citation, not an opinion:
callers must say what the grade *was*, in the 1930s, per the source — never what it implies
today. See ``docs/adr/0018-exposure-brief-and-equity-context.md`` for the full framing
discussion and the coverage gap (HOLC only mapped select cities, not every place swelter runs).
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

#: The four historical HOLC grades. There is no fifth "not graded" grade — a cell with no HOLC
#: coverage simply has no feature in the dataset, so absence itself is the honest signal.
HOLC_GRADES: Final[tuple[str, ...]] = ("A", "B", "C", "D")

#: The plain-language label HOLC itself used for each grade, for rendering.
HOLC_GRADE_LABELS: Final[dict[str, str]] = {
    "A": "Best",
    "B": "Still Desirable",
    "C": "Definitely Declining",
    "D": "Hazardous",
}

#: The only properties a redlining feature may carry — one historical fact plus provenance, the
#: same closed-allowlist discipline the rest of the context-layer family uses.
ALLOWED_PROPERTIES: Final[frozenset[str]] = frozenset(
    {
        "cell_id",  # the published grid cell this measurement describes (matches aggregate.py)
        "holc_grade",  # the historical HOLC grade for this area: A, B, C, or D
        "notes",  # short public note (e.g. the HOLC area id, survey year)
        "source",  # who published this record
        "source_url",  # where it came from
        "last_verified",  # ISO date this entry was last checked
    }
)

#: Properties a feature cannot be published without.
REQUIRED_PROPERTIES: Final[tuple[str, ...]] = ("holc_grade",)


class RedliningLayerError(ValueError):
    """Raised when the redlining dataset is malformed or carries a disallowed field."""


@dataclass(frozen=True)
class RedliningCell:
    """One grid cell's historical HOLC grade, with its provenance.

    ``holc_grade`` is copied verbatim from the source dataset — swelter neither recomputes nor
    reinterprets it. ``grade_label`` is HOLC's own plain-language name for the grade, derived
    only for readability.
    """

    lat: float
    lon: float
    holc_grade: str
    cell_id: str = ""
    notes: str = ""
    source: str = ""
    source_url: str = ""
    last_verified: str = ""

    @property
    def grade_label(self) -> str:
        return HOLC_GRADE_LABELS[self.holc_grade]

    def as_feature(self) -> dict[str, object]:
        props: dict[str, object] = {"holc_grade": self.holc_grade}
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
class RedliningLayerSet:
    """A validated dataset of per-cell HOLC grades plus its set-level provenance."""

    cells: tuple[RedliningCell, ...]
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

    def by_cell_id(self) -> dict[str, RedliningCell]:
        """``cell_id`` → cell, for joining this layer onto the surface's own cell keys."""
        return {c.cell_id: c for c in self.cells if c.cell_id}


def _holc_grade(value: Any, name: str) -> str:
    if not isinstance(value, str):
        raise RedliningLayerError(f"{name}: holc_grade must be a string")
    grade = value.strip().upper()
    if grade not in HOLC_GRADES:
        raise RedliningLayerError(f"{name}: holc_grade {value!r} must be one of {HOLC_GRADES}")
    return grade


def _coordinate(geometry: Any, name: str) -> tuple[float, float]:
    if not isinstance(geometry, dict) or geometry.get("type") != "Point":
        raise RedliningLayerError(f"{name}: geometry must be a GeoJSON Point")
    coords = geometry.get("coordinates")
    if not isinstance(coords, (list, tuple)) or len(coords) < 2:
        raise RedliningLayerError(f"{name}: Point needs [lon, lat] coordinates")
    lon, lat = float(coords[0]), float(coords[1])
    if not (-180.0 <= lon <= 180.0 and -90.0 <= lat <= 90.0):
        raise RedliningLayerError(f"{name}: coordinate {lat},{lon} is out of range")
    return lat, lon


def parse(doc: dict[str, Any]) -> RedliningLayerSet:
    """Validate an already-parsed FeatureCollection into a :class:`RedliningLayerSet`."""
    if doc.get("type") != "FeatureCollection":
        raise RedliningLayerError("dataset must be a GeoJSON FeatureCollection")
    features = doc.get("features")
    if not isinstance(features, list):
        raise RedliningLayerError("dataset has no features list")
    cells: list[RedliningCell] = []
    for i, feature in enumerate(features):
        if not isinstance(feature, dict):
            raise RedliningLayerError(f"feature {i} is not an object")
        props = feature.get("properties") or {}
        if not isinstance(props, dict):
            raise RedliningLayerError(f"feature {i}: properties must be an object")
        extra = set(props) - ALLOWED_PROPERTIES
        if extra:
            raise RedliningLayerError(
                f"feature {i}: disallowed propert{'y' if len(extra) == 1 else 'ies'} "
                f"{sorted(extra)} — only documented descriptive fields are permitted"
            )
        missing = [p for p in REQUIRED_PROPERTIES if props.get(p) is None]
        if missing:
            raise RedliningLayerError(f"feature {i}: missing required propert(ies) {missing}")
        lat, lon = _coordinate(feature.get("geometry"), f"feature {i}")
        holc_grade = _holc_grade(props.get("holc_grade"), f"feature {i}")
        cell_id = str(props.get("cell_id") or "") or f"{lat:.6f},{lon:.6f}"
        cells.append(
            RedliningCell(
                lat=lat,
                lon=lon,
                holc_grade=holc_grade,
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
    return RedliningLayerSet(
        cells=tuple(cells),
        license=str(meta.get("license") or ""),
        attribution=str(meta.get("attribution") or ""),
        source=str(meta.get("source") or ""),
        last_verified=str(meta.get("last_verified") or ""),
    )


def load(path: str | Path) -> RedliningLayerSet:
    """Load and validate a redlining GeoJSON dataset from disk."""
    raw: Any = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise RedliningLayerError("dataset root must be a JSON object")
    return parse(raw)


def empty() -> RedliningLayerSet:
    """An empty, valid dataset — what a caller gets when no dataset is configured."""
    return RedliningLayerSet(cells=())


def from_cells(cells: Iterable[RedliningCell]) -> RedliningLayerSet:
    return RedliningLayerSet(cells=tuple(cells))
