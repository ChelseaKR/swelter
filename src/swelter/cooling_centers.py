"""Cooling-center overlay: a curated, provenance-bearing dataset of public places to cool down.

A heat map tells a resident where it is dangerous; it should also tell them where to go. Cooling
centers — libraries, community centers, senior centers, cooled public buildings — are exactly the
kind of civic data that belongs beside the readings. This module loads a curated GeoJSON dataset,
validates it, and hands it to the API and the dashboard, which draws it as a toggleable map overlay
with a parity list (ADR 0011).

The dataset is *public-facility* data, not sensor data: it is curated and versioned, carries
explicit provenance (a source, a source URL, and a ``last_verified`` date per feature and for the
set), and is licensed in its own metadata — it is **not** part of the CC0 observation stream.
Validation is strict about two things: every feature must have a name and a valid coordinate, and
the schema only admits the documented public fields, so a future edit cannot smuggle a private
contact or a person's name into what the map publishes.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

#: The only properties a cooling-center feature may carry. Everything published here is public
#: facility information; the allowlist keeps a private phone, a contact name, or a personal note
#: from ever reaching the map through this dataset.
ALLOWED_PROPERTIES: Final[frozenset[str]] = frozenset(
    {
        "name",  # the facility's public name
        "type",  # library | community-center | senior-center | cooling-center | public
        "address",  # public street address of the facility (not a residence)
        "hours",  # human-readable opening hours
        "accessible",  # wheelchair-accessible (bool)
        "air_conditioned",  # actively cooled (bool)
        "notes",  # short public note (e.g. "water available")
        "source",  # who published this record
        "source_url",  # where it came from
        "last_verified",  # ISO date this entry was last checked
    }
)

#: Properties a feature cannot be published without.
REQUIRED_PROPERTIES: Final[tuple[str, ...]] = ("name",)


class CoolingCenterError(ValueError):
    """Raised when the cooling-center dataset is malformed or carries a disallowed field."""


@dataclass(frozen=True)
class CoolingCenter:
    """One public place to cool down, with its provenance."""

    name: str
    lat: float
    lon: float
    type: str = "public"
    address: str = ""
    hours: str = ""
    accessible: bool | None = None
    air_conditioned: bool | None = None
    notes: str = ""
    source: str = ""
    source_url: str = ""
    last_verified: str = ""

    def as_feature(self) -> dict[str, object]:
        props: dict[str, object] = {"name": self.name, "type": self.type}
        if self.address:
            props["address"] = self.address
        if self.hours:
            props["hours"] = self.hours
        if self.accessible is not None:
            props["accessible"] = self.accessible
        if self.air_conditioned is not None:
            props["air_conditioned"] = self.air_conditioned
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
class CoolingCenterSet:
    """A validated dataset of cooling centers plus its set-level provenance metadata."""

    centers: tuple[CoolingCenter, ...]
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
                "count": len(self.centers),
            },
            "features": [c.as_feature() for c in self.centers],
        }


def _as_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    raise CoolingCenterError(f"expected a boolean, got {value!r}")


def _coordinate(geometry: Any, name: str) -> tuple[float, float]:
    if not isinstance(geometry, dict) or geometry.get("type") != "Point":
        raise CoolingCenterError(f"{name}: geometry must be a GeoJSON Point")
    coords = geometry.get("coordinates")
    if not isinstance(coords, (list, tuple)) or len(coords) < 2:
        raise CoolingCenterError(f"{name}: Point needs [lon, lat] coordinates")
    lon, lat = float(coords[0]), float(coords[1])
    if not (-180.0 <= lon <= 180.0 and -90.0 <= lat <= 90.0):
        raise CoolingCenterError(f"{name}: coordinate {lat},{lon} is out of range")
    return lat, lon


def parse(doc: dict[str, Any]) -> CoolingCenterSet:
    """Validate an already-parsed FeatureCollection into a :class:`CoolingCenterSet`."""
    if doc.get("type") != "FeatureCollection":
        raise CoolingCenterError("dataset must be a GeoJSON FeatureCollection")
    features = doc.get("features")
    if not isinstance(features, list):
        raise CoolingCenterError("dataset has no features list")
    centers: list[CoolingCenter] = []
    for i, feature in enumerate(features):
        if not isinstance(feature, dict):
            raise CoolingCenterError(f"feature {i} is not an object")
        props = feature.get("properties") or {}
        if not isinstance(props, dict):
            raise CoolingCenterError(f"feature {i}: properties must be an object")
        extra = set(props) - ALLOWED_PROPERTIES
        if extra:
            raise CoolingCenterError(
                f"feature {i}: disallowed propert{'y' if len(extra) == 1 else 'ies'} "
                f"{sorted(extra)} — only documented public fields are permitted"
            )
        name = str(props.get("name") or "").strip()
        if not name:
            raise CoolingCenterError(f"feature {i}: a cooling center must have a name")
        lat, lon = _coordinate(feature.get("geometry"), f"feature {i} ({name})")
        centers.append(
            CoolingCenter(
                name=name,
                lat=lat,
                lon=lon,
                type=str(props.get("type") or "public"),
                address=str(props.get("address") or ""),
                hours=str(props.get("hours") or ""),
                accessible=_as_bool(props.get("accessible")),
                air_conditioned=_as_bool(props.get("air_conditioned")),
                notes=str(props.get("notes") or ""),
                source=str(props.get("source") or ""),
                source_url=str(props.get("source_url") or ""),
                last_verified=str(props.get("last_verified") or ""),
            )
        )
    meta = doc.get("metadata") or {}
    if not isinstance(meta, dict):
        meta = {}
    return CoolingCenterSet(
        centers=tuple(centers),
        license=str(meta.get("license") or ""),
        attribution=str(meta.get("attribution") or ""),
        source=str(meta.get("source") or ""),
        last_verified=str(meta.get("last_verified") or ""),
    )


def load(path: str | Path) -> CoolingCenterSet:
    """Load and validate a cooling-center GeoJSON dataset from disk."""
    raw: Any = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise CoolingCenterError("dataset root must be a JSON object")
    return parse(raw)


def empty() -> CoolingCenterSet:
    """An empty, valid dataset — what the API serves when no dataset is configured."""
    return CoolingCenterSet(centers=())


def from_features(features: Iterable[CoolingCenter]) -> CoolingCenterSet:
    return CoolingCenterSet(centers=tuple(features))
