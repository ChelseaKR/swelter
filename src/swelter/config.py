"""Network configuration: nodes, calibration windows, grid resolution, languages.

Configuration is committed YAML, not code and not an admin console (``network.yaml`` in the
repo root is the worked example). A community stands up its own instance by editing one
file: registering its nodes and reference monitors, choosing a grid resolution, and listing
the languages its dashboard ships. Pointing swelter at a different city is a config change
with a diff and a review, not a fork.

Two privacy rules are enforced *here*, before any value reaches the map:

* A node's published location is snapped to a coarse grid (``grid_precision_m``, default
  ~150 m) unless the host explicitly opts into ``location: precise``. ``public_location``
  is the only coordinate the rest of the system is allowed to read.
* The precise coordinate is never required — a node with no location at all still ingests,
  it simply does not appear on the map until a host places it.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

DEFAULT_GRID_M = 150.0
_METRES_PER_DEGREE_LAT = 111_320.0

# Node labels are PUBLISHED (map, table, API, exports), so they must name a place, not a person or
# an address (hard rule #1). These heuristics catch the obvious leaks — a street address, apartment
# unit, an email, a phone — so a host is warned before such a label ever goes out. Cross-street and
# place names ("Cedar & 4th", "Oak Park Commons") do not match.
_LABEL_PII_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(
            r"\b\d{1,5}\s+\w+(\s+\w+)*\s+"
            r"(st|street|ave|avenue|rd|road|blvd|boulevard|ln|lane|dr|drive|ct|court|"
            r"way|pl|place|terrace|ter|hwy|highway)\b\.?",
            re.IGNORECASE,
        ),
        "looks like a street address",
    ),
    (
        re.compile(r"\b(apt|apartment|unit|suite|ste)\b\.?\s*\S+", re.IGNORECASE),
        "looks like a unit number",
    ),
    (re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+"), "contains an email address"),
    (re.compile(r"\b\d{3}[.\-\s]\d{3}[.\-\s]\d{4}\b"), "contains a phone number"),
)


@dataclass(frozen=True)
class NodeConfig:
    """A sensor node as the hosting collective registered it."""

    node_id: str
    label: str = ""
    lat: float | None = None
    lon: float | None = None
    location: str = "coarse"  # "coarse" (snap to grid) or "precise" (host opted in)
    # governance-log entry recording host consent for a precise location (governance.md §4)
    consent_ref: str = ""

    def public_location(self, grid_m: float) -> tuple[float, float] | None:
        """The coordinate swelter is allowed to publish for this node.

        ``None`` when the host has not placed the node. ``precise`` returns the exact
        coordinate the host opted to disclose; otherwise the value is snapped to the grid so
        hosting a sensor cannot reveal where a person lives.
        """
        if self.lat is None or self.lon is None:
            return None
        if self.location == "precise":
            return (self.lat, self.lon)
        return snap_to_grid(self.lat, self.lon, grid_m)


@dataclass(frozen=True)
class ReferenceMonitor:
    """A reference-grade monitor a node is co-located against to fit its correction."""

    monitor_id: str
    label: str = ""
    source: str = ""  # e.g. "US EPA AQS site 06-067-0010"


@dataclass(frozen=True)
class CalibrationWindow:
    """A co-location training window: which node sat beside which reference, and when."""

    node_id: str
    reference: str
    parameter: str
    start: str
    end: str


@dataclass(frozen=True)
class TwinWindow:
    """A co-located sensor-twin window: two low-cost nodes sitting side by side, and when.

    Unlike :class:`CalibrationWindow`, neither node is a reference monitor — this is a
    precision check (do the twins agree with each other?), not an accuracy check (does either
    twin agree with truth?). See ``qc.twin_agreement`` and ``docs/calibration.md``.
    """

    node_a: str
    node_b: str
    parameter: str
    start: str
    end: str


@dataclass(frozen=True)
class NetworkConfig:
    """The whole network as one reviewable document."""

    name: str = "swelter network"
    grid_resolution_m: float = DEFAULT_GRID_M
    languages: tuple[str, ...] = ("en",)
    nodes: tuple[NodeConfig, ...] = ()
    reference_monitors: tuple[ReferenceMonitor, ...] = ()
    calibration_windows: tuple[CalibrationWindow, ...] = field(default_factory=tuple)
    #: Co-located twin windows for the cross-checked precision tier (QC metadata only — see
    #: ``qc.twin_agreement``). Empty means no twin pairs are configured; nothing changes.
    twin_windows: tuple[TwinWindow, ...] = field(default_factory=tuple)
    #: Per-network danger floors for the alerts feed (keys: ``pm25_aqi``, ``heat_index_c``,
    #: ``exposure``). Empty means "use the documented public-health defaults" (see ``alerts.py``).
    alert_thresholds: dict[str, float] = field(default_factory=dict)

    def node(self, node_id: str) -> NodeConfig | None:
        return next((n for n in self.nodes if n.node_id == node_id), None)

    def public_locations(self) -> dict[str, tuple[float, float]]:
        """node_id → published (lat, lon), for every node the host has placed."""
        out: dict[str, tuple[float, float]] = {}
        for node in self.nodes:
            loc = node.public_location(self.grid_resolution_m)
            if loc is not None:
                out[node.node_id] = loc
        return out


def snap_to_grid(lat: float, lon: float, grid_m: float) -> tuple[float, float]:
    """Snap a coordinate to the centre of a ``grid_m``-sided cell.

    Longitude cell size widens with latitude so cells stay roughly square on the ground.
    Returns the cell centre, which is what gets published.
    """
    lat_step = grid_m / _METRES_PER_DEGREE_LAT
    lon_metres_per_degree = _METRES_PER_DEGREE_LAT * math.cos(math.radians(lat)) or 1e-9
    lon_step = grid_m / lon_metres_per_degree
    snapped_lat = (math.floor(lat / lat_step) + 0.5) * lat_step
    snapped_lon = (math.floor(lon / lon_step) + 0.5) * lon_step
    return (round(snapped_lat, 6), round(snapped_lon, 6))


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Ground distance in metres between two coordinates (haversine formula).

    Used to show a host how far the published (possibly grid-snapped) coordinate sits from
    their sensor's exact location — see ``swelter node-preview``.
    """
    earth_radius_m = _METRES_PER_DEGREE_LAT * 180.0 / math.pi
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * earth_radius_m * math.asin(math.sqrt(a))


def _as_str(value: Any, default: str = "") -> str:
    return str(value) if value is not None else default


def _as_float(value: Any) -> float | None:
    return None if value is None else float(value)


def load_config(path: str | Path) -> NetworkConfig:
    """Load and validate ``network.yaml`` into a typed :class:`NetworkConfig`."""
    raw: Any = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return parse_config(raw if isinstance(raw, dict) else {})


def parse_config(doc: dict[str, Any]) -> NetworkConfig:
    """Build a :class:`NetworkConfig` from an already-parsed mapping."""
    nodes = tuple(
        NodeConfig(
            node_id=_as_str(n.get("node_id") or n.get("id")),
            label=_as_str(n.get("label")),
            lat=_as_float(n.get("lat")),
            lon=_as_float(n.get("lon")),
            location=_as_str(n.get("location"), "coarse"),
            consent_ref=_as_str(n.get("consent_ref")),
        )
        for n in doc.get("nodes", []) or []
    )
    monitors = tuple(
        ReferenceMonitor(
            monitor_id=_as_str(m.get("monitor_id") or m.get("id")),
            label=_as_str(m.get("label")),
            source=_as_str(m.get("source")),
        )
        for m in doc.get("reference_monitors", []) or []
    )
    windows = tuple(
        CalibrationWindow(
            node_id=_as_str(w.get("node_id")),
            reference=_as_str(w.get("reference")),
            parameter=_as_str(w.get("parameter")),
            start=_as_str(w.get("start")),
            end=_as_str(w.get("end")),
        )
        for w in doc.get("calibration_windows", []) or []
    )
    twin_windows = tuple(
        TwinWindow(
            node_a=_as_str(t.get("node_a")),
            node_b=_as_str(t.get("node_b")),
            parameter=_as_str(t.get("parameter")),
            start=_as_str(t.get("start")),
            end=_as_str(t.get("end")),
        )
        for t in doc.get("twin_windows", []) or []
    )
    languages = tuple(str(lang) for lang in doc.get("languages", ["en"]) or ["en"])
    thresholds = {
        str(k): float(v) for k, v in (doc.get("alert_thresholds") or {}).items() if v is not None
    }
    return NetworkConfig(
        name=_as_str(doc.get("name"), "swelter network"),
        grid_resolution_m=float(doc.get("grid_resolution_m", DEFAULT_GRID_M)),
        languages=languages,
        nodes=nodes,
        reference_monitors=monitors,
        calibration_windows=windows,
        twin_windows=twin_windows,
        alert_thresholds=thresholds,
    )


def label_concerns(config: NetworkConfig) -> list[str]:
    """Warn about node labels that look like they encode a person or an address.

    Labels are published, so a street address, unit, email, or phone in one would leak exactly what
    the coarse-grid rule protects against (hard rule #1). Heuristic and conservative — it warns, it
    does not block — so a host can fix a label before it goes out; the CLI prints these on load.
    """
    out: list[str] = []
    for node in config.nodes:
        for field_name, value in (("node_id", node.node_id), ("label", node.label or "")):
            for pattern, why in _LABEL_PII_PATTERNS:
                if pattern.search(value):
                    out.append(
                        f"{node.node_id}: {field_name} {value!r} {why} — node ids and labels are "
                        f"public; use a place name, not an address (hard rule #1)"
                    )
                    break
            else:
                continue
            break
    return out


def consent_concerns(config: NetworkConfig) -> list[str]:
    """Warn about precise nodes with no recorded host consent.

    Disclosing a precise location is a decision only the host of that node may make, and
    governance.md §4 requires it be written down as a dated entry in the governance log. This
    does not gate ``public_location`` — a node missing ``consent_ref`` still publishes its precise
    coordinate — it only warns, so a host or steward can go record the consent that governance
    already requires; the CLI prints these on load.
    """
    out: list[str] = []
    for node in config.nodes:
        if node.location == "precise" and not node.consent_ref.strip():
            out.append(
                f"{node.node_id}: location is 'precise' but no consent_ref recorded — a precise "
                f"location requires a dated governance-log consent entry (governance.md §4)"
            )
    return out
