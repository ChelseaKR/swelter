"""AC-access overlay: a curated, provenance-bearing, *strictly descriptive* per-cell dataset.

A heat map tells a resident how hot it is; it does not tell them who has the least ability to
get relief indoors. Whether a household has working air conditioning is one of the strongest
predictors of who is hurt by a heat event, and it is not visible in a temperature reading. This
module follows the exact pattern :mod:`swelter.context_layers` set for tree canopy (ADR 0023):
one descriptive measurement per grid cell — the modeled percent of households that may lack
air conditioning — with its provenance, handed to callers (the CLI brief, a future map layer) as
a validated, joinable dataset.

It is a deliberate sibling module, not an extension of ``context_layers.py``: that module's
``ALLOWED_PROPERTIES`` is closed on purpose so a single canopy dataset can never grow a second,
unrelated measurement into an implied composite score. Each context layer in this family owns
its own narrow allowlist instead.

The real, citable source for this measurement is the U.S. Census Bureau's **Local Air
Conditioning Estimates (LACE)** — an experimental, model-based estimate of AC prevalence at the
state/county/census-tract level, built by fusing the American Housing Survey and the American
Community Survey (see ``docs/adr/0018-exposure-brief-and-equity-context.md`` for the
research notes and known gaps). LACE is tract-level, not sensor-cell-level, so a real deployment
joins it by geocoding each published cell to its census tract — that join is out of scope here;
this module only loads and validates the resulting per-cell dataset, the same boundary
``context_layers.py`` draws for canopy.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

#: The only properties an AC-access feature may carry. As with
#: ``context_layers.ALLOWED_PROPERTIES``, there is no "score", "rank", or "vulnerability" field —
#: only the one descriptive measurement plus its provenance, so this dataset can never be read as
#: a swelter-computed ranking.
ALLOWED_PROPERTIES: Final[frozenset[str]] = frozenset(
    {
        "cell_id",  # the published grid cell this measurement describes (matches aggregate.py)
        "no_ac_pct",  # modeled percent of households estimated to lack air conditioning, 0-100
        "notes",  # short public note (e.g. data vintage, modeling caveat)
        "source",  # who published this record
        "source_url",  # where it came from
        "last_verified",  # ISO date this entry was last checked
    }
)

#: Properties a feature cannot be published without.
REQUIRED_PROPERTIES: Final[tuple[str, ...]] = ("no_ac_pct",)


class ACAccessLayerError(ValueError):
    """Raised when the AC-access dataset is malformed or carries a disallowed field."""


@dataclass(frozen=True)
class ACAccessCell:
    """One grid cell's descriptive AC-access measurement, with its provenance.

    ``no_ac_pct`` is a plain modeled percentage read from the source dataset — not a derived
    score, and not a claim about any individual household. A resident or organizer relates this
    to the heat surface by reading both layers side by side, the same honesty boundary
    ``context_layers.ContextCell`` draws for canopy.
    """

    lat: float
    lon: float
    no_ac_pct: float
    cell_id: str = ""
    notes: str = ""
    source: str = ""
    source_url: str = ""
    last_verified: str = ""

    def as_feature(self) -> dict[str, object]:
        props: dict[str, object] = {"no_ac_pct": self.no_ac_pct}
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
class ACAccessLayerSet:
    """A validated dataset of per-cell AC-access measurements plus its set-level provenance."""

    cells: tuple[ACAccessCell, ...]
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

    def by_cell_id(self) -> dict[str, ACAccessCell]:
        """``cell_id`` → cell, for joining this layer onto the surface's own cell keys."""
        return {c.cell_id: c for c in self.cells if c.cell_id}


def _no_ac_pct(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ACAccessLayerError(f"{name}: no_ac_pct must be a number")
    pct = float(value)
    if not (0.0 <= pct <= 100.0):
        raise ACAccessLayerError(f"{name}: no_ac_pct {pct} is out of range 0-100")
    return pct


def _coordinate(geometry: Any, name: str) -> tuple[float, float]:
    if not isinstance(geometry, dict) or geometry.get("type") != "Point":
        raise ACAccessLayerError(f"{name}: geometry must be a GeoJSON Point")
    coords = geometry.get("coordinates")
    if not isinstance(coords, (list, tuple)) or len(coords) < 2:
        raise ACAccessLayerError(f"{name}: Point needs [lon, lat] coordinates")
    lon, lat = float(coords[0]), float(coords[1])
    if not (-180.0 <= lon <= 180.0 and -90.0 <= lat <= 90.0):
        raise ACAccessLayerError(f"{name}: coordinate {lat},{lon} is out of range")
    return lat, lon


def parse(doc: dict[str, Any]) -> ACAccessLayerSet:
    """Validate an already-parsed FeatureCollection into an :class:`ACAccessLayerSet`."""
    if doc.get("type") != "FeatureCollection":
        raise ACAccessLayerError("dataset must be a GeoJSON FeatureCollection")
    features = doc.get("features")
    if not isinstance(features, list):
        raise ACAccessLayerError("dataset has no features list")
    cells: list[ACAccessCell] = []
    for i, feature in enumerate(features):
        if not isinstance(feature, dict):
            raise ACAccessLayerError(f"feature {i} is not an object")
        props = feature.get("properties") or {}
        if not isinstance(props, dict):
            raise ACAccessLayerError(f"feature {i}: properties must be an object")
        extra = set(props) - ALLOWED_PROPERTIES
        if extra:
            raise ACAccessLayerError(
                f"feature {i}: disallowed propert{'y' if len(extra) == 1 else 'ies'} "
                f"{sorted(extra)} — only documented descriptive fields are permitted"
            )
        missing = [p for p in REQUIRED_PROPERTIES if props.get(p) is None]
        if missing:
            raise ACAccessLayerError(f"feature {i}: missing required propert(ies) {missing}")
        lat, lon = _coordinate(feature.get("geometry"), f"feature {i}")
        no_ac_pct = _no_ac_pct(props.get("no_ac_pct"), f"feature {i}")
        cell_id = str(props.get("cell_id") or "") or f"{lat:.6f},{lon:.6f}"
        cells.append(
            ACAccessCell(
                lat=lat,
                lon=lon,
                no_ac_pct=no_ac_pct,
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
    return ACAccessLayerSet(
        cells=tuple(cells),
        license=str(meta.get("license") or ""),
        attribution=str(meta.get("attribution") or ""),
        source=str(meta.get("source") or ""),
        last_verified=str(meta.get("last_verified") or ""),
    )


def load(path: str | Path) -> ACAccessLayerSet:
    """Load and validate an AC-access GeoJSON dataset from disk."""
    raw: Any = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ACAccessLayerError("dataset root must be a JSON object")
    return parse(raw)


def empty() -> ACAccessLayerSet:
    """An empty, valid dataset — what a caller gets when no dataset is configured."""
    return ACAccessLayerSet(cells=())


def from_cells(cells: Iterable[ACAccessCell]) -> ACAccessLayerSet:
    return ACAccessLayerSet(cells=tuple(cells))
