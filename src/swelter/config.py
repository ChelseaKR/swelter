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

import difflib
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

DEFAULT_GRID_M = 150.0
_METRES_PER_DEGREE_LAT = 111_320.0

#: The only keys `network.yaml` may have at the top level. Anything else is almost always a typo
#: (`language:` for `languages:`) or a stale field copied from another template —
#: `config_concerns`/`swelter doctor` rejects it loudly instead of silently ignoring it.
_KNOWN_TOP_LEVEL_KEYS: frozenset[str] = frozenset(
    {
        "name",
        "grid_resolution_m",
        "languages",
        "nodes",
        "reference_monitors",
        "calibration_windows",
        "alert_thresholds",
    }
)
_KNOWN_LOCATIONS: frozenset[str] = frozenset({"coarse", "precise"})

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


def _as_str(value: Any, default: str = "") -> str:
    return str(value) if value is not None else default


def _as_float(value: Any) -> float | None:
    return None if value is None else float(value)


def load_config(path: str | Path) -> NetworkConfig:
    """Load and validate ``network.yaml`` into a typed :class:`NetworkConfig`."""
    return load_config_doc(path)[0]


def load_config_doc(path: str | Path) -> tuple[NetworkConfig, dict[str, Any]]:
    """Load ``network.yaml`` and also return the raw parsed mapping.

    ``parse_config`` drops anything it does not recognize (an unknown top-level key, a typo'd
    ``alert_thresholds`` entry), so a validator that wants to catch those mistakes needs the
    document *before* that happens. Callers that only need the typed config should use
    :func:`load_config`; ``swelter doctor`` and anything printing :func:`config_concerns` wants
    both.
    """
    raw: Any = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    doc = raw if isinstance(raw, dict) else {}
    return parse_config(doc), doc


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


def _did_you_mean(key: str, candidates: frozenset[str]) -> str:
    """A short ` (did you mean 'x'?)` hint, or `""` when nothing is close enough to suggest."""
    match = difflib.get_close_matches(key, sorted(candidates), n=1, cutoff=0.6)
    return f" (did you mean {match[0]!r}?)" if match else ""


def config_concerns(config: NetworkConfig, doc: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Validate a loaded config against the raw document it came from.

    Returns ``(errors, warnings)``. Errors name a mistake that would silently corrupt data or
    safety behaviour (a duplicate node id merging two sensors into one cell identity, an
    `alert_thresholds` typo that reverts a danger floor to the default without saying so) —
    ``swelter doctor`` exits nonzero when there are any. Warnings name something a host probably
    did not intend but that swelter can fail-safe around (a stray `location:` value falls back to
    `coarse`, an unresolved calibration reference just does not calibrate) — printed, never
    blocking. Every message names the offending item and the fix in plain language; ``doc`` is the
    raw parsed mapping (before ``parse_config`` drops anything it does not recognize), because
    that is the only place an unknown or misspelled key is still visible.
    """
    from . import alerts  # deferred: alerts -> aggregate -> config would otherwise cycle

    errors: list[str] = []
    warnings: list[str] = []
    _unknown_key_concerns(doc, errors)
    _node_id_concerns(config, errors)
    _threshold_concerns(config, frozenset(alerts.DEFAULT_THRESHOLDS), errors)
    _node_field_concerns(config, errors, warnings)
    _window_concerns(config, warnings)
    return errors, warnings


def _unknown_key_concerns(doc: dict[str, Any], errors: list[str]) -> None:
    for key in doc:
        if key not in _KNOWN_TOP_LEVEL_KEYS:
            hint = _did_you_mean(str(key), _KNOWN_TOP_LEVEL_KEYS)
            errors.append(
                f"network.yaml: unknown top-level key {key!r}{hint} — remove it or fix the typo "
                f"(recognized keys: {', '.join(sorted(_KNOWN_TOP_LEVEL_KEYS))})"
            )


def _node_id_concerns(config: NetworkConfig, errors: list[str]) -> None:
    seen_ids: dict[str, int] = {}
    for node in config.nodes:
        if not node.node_id:
            errors.append(
                "nodes: a node has an empty or missing node_id — every node needs a unique, "
                "non-empty node_id (this is what identifies it everywhere downstream)"
            )
            continue
        seen_ids[node.node_id] = seen_ids.get(node.node_id, 0) + 1
    for node_id, count in seen_ids.items():
        if count > 1:
            errors.append(
                f"nodes: node_id {node_id!r} is reused by {count} nodes — give each node a "
                f"unique node_id, or their readings will merge into one cell identity"
            )


def _threshold_concerns(
    config: NetworkConfig, valid_threshold_keys: frozenset[str], errors: list[str]
) -> None:
    for key in config.alert_thresholds:
        if key not in valid_threshold_keys:
            hint = _did_you_mean(key, valid_threshold_keys)
            errors.append(
                f"alert_thresholds: unknown key {key!r}{hint} — it is ignored at runtime and the "
                f"default danger floor stays in effect; recognized keys: "
                f"{', '.join(sorted(valid_threshold_keys))}"
            )


def _node_field_concerns(config: NetworkConfig, errors: list[str], warnings: list[str]) -> None:
    for node in config.nodes:
        label = node.node_id or "<missing node_id>"
        if node.lat is not None and not (-90.0 <= node.lat <= 90.0):
            errors.append(
                f"{label}: lat {node.lat} is out of range (-90..90) — check for a typo or a "
                f"swapped lat/lon"
            )
        if node.lon is not None and not (-180.0 <= node.lon <= 180.0):
            errors.append(
                f"{label}: lon {node.lon} is out of range (-180..180) — check for a typo or a "
                f"swapped lat/lon"
            )
        if node.location not in _KNOWN_LOCATIONS:
            warnings.append(
                f"{label}: location {node.location!r} is not 'coarse' or 'precise' — treating it "
                f"as 'coarse' (fail-safe); set 'location: precise' if the host opted into an "
                f"exact coordinate"
            )


def _window_concerns(config: NetworkConfig, warnings: list[str]) -> None:
    node_ids = {n.node_id for n in config.nodes if n.node_id}
    monitor_ids = {m.monitor_id for m in config.reference_monitors if m.monitor_id}
    for window in config.calibration_windows:
        if window.node_id not in node_ids:
            warnings.append(
                f"calibration_windows: node_id {window.node_id!r} is not a registered node — add "
                f"it under nodes: or fix the typo (this window will not calibrate anything)"
            )
        if window.reference not in monitor_ids:
            warnings.append(
                f"calibration_windows: reference {window.reference!r} is not a registered "
                f"reference monitor — add it under reference_monitors: or fix the typo"
            )
