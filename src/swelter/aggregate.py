"""Spatial/temporal rollups: the gridded heat-island and AQI surfaces the map and API read.

Aggregation snaps each node's reading to its *published* grid cell — never its precise
location — and rolls values up by hour. Neighbourhood-scale exposure is the question, so the grid
is neighbourhood resolution, not a city average.

On top of the per-parameter cells, a derived ``exposure`` layer combines the calibrated heat index
and the PM2.5 AQI into one published level per cell/hour (ADR 0009). It is built only where both
halves exist, inherits their provisional flag, and never blends them into a fabricated number — the
higher of the two concerns, plus a ``compound`` flag when both are elevated.

Trust is preserved through the rollup. For a given cell, hour, and parameter, the mean is taken
over *calibrated, QC-clean* values when any exist; a cell that has only raw QC-clean readings is
still shown, but marked ``provisional`` so the map can render it as not-yet-fact rather than
dropping it. A QC-rejected value is never placed on the map, even provisionally. Each cell carries
its host-assigned ``label`` so the dashboard can name a block instead of an anonymous "Cell N".
PM2.5 cells carry an EPA AQI value and category, computed from the **hourly** mean
(``aqi_window = "hourly-mean"``) by default, plus an alternate ``"nowcast"`` reading per cell when
enough trailing hours exist (see :func:`_nowcast_cells`) — the two never share a bucket's value.

A calibrated cell publishes **two distinct** uncertainty numbers, under distinct names, so no
consumer can silently reinterpret one as the other: ``mean_member_sigma`` is the plain mean of the
per-value 1-sigmas that went into the cell (the old, simpler number), and ``uncertainty`` is the
cell's own standard error — ``sqrt(sum(sigma_i^2)) / n`` — which is what should actually be quoted
as "the cell's uncertainty" when averaging several independent-ish readings. It carries a caveat:
members of one cell often share a calibration fit (same node, same correction), so their errors are
not fully independent, and this SE is a lower bound on the true combined uncertainty, not an exact
one. The derived ``exposure`` cell has no sigma of its own — its mean is an ordinal level, not a
physical quantity — so instead of a fabricated number it carries an ``uncertainty_note`` identifying
which component (heat or air) bounds the published level.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from typing import NamedTuple

from . import hazard_packs
from .config import NetworkConfig
from .models import (
    QC_SUSPICIOUS,
    QC_UNMAPPABLE,
    Observation,
    exposure_bounding_component,
    exposure_level,
    heat_index_category,
    nowcast_concentration,
    parse_timestamp,
    pm25_aqi,
)

#: Parameters that appear on the map/surface (raw-only diagnostic fields are excluded).
SURFACE_PARAMETERS = ("temp_c", "heat_index_c", "wbgt_c", "pm25_ugm3", "pm10_ugm3", "no2_ppb")

#: The derived combined heat-and-air layer. Not an observed parameter — built per cell/hour from
#: the calibrated heat-index and PM2.5 cells, so it inherits their trust (ADR 0009).
EXPOSURE = "exposure"

#: The averaging window behind the published AQI — hourly mean, not the EPA 24-hour/NowCast value.
AQI_WINDOW = "hourly-mean"

#: The EPA NowCast alternate window (see `_nowcast_cells`) — a distinct, never-conflated tag. The
#: 3-hour floor and 12-hour cap it requires live in `models.nowcast_concentration`.
AQI_WINDOW_NOWCAST = "nowcast"


def hour_bucket(timestamp: str) -> str:
    dt = parse_timestamp(timestamp).replace(minute=0, second=0, microsecond=0)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class CellReading:
    """One parameter's rolled-up value for one grid cell in one hour."""

    cell_id: str
    label: str
    lat: float
    lon: float
    parameter: str
    bucket: str
    mean: float
    n: int
    provisional: bool
    # Cell standard error: sqrt(sum(sigma_i^2)) / n over the calibrated members' own 1-sigmas.
    # None when provisional. Treats member sigmas as independent — members of one cell often share
    # a calibration fit, so this is a *lower bound* on the true combined uncertainty, not exact.
    uncertainty: float | None = None
    # The plain mean of the calibrated members' 1-sigmas — distinct from `uncertainty` above on
    # purpose (a statistician reproducing this from exported per-observation sigmas should never
    # have to guess which one they're looking at). None when provisional.
    mean_member_sigma: float | None = None
    aqi: int | None = None
    category: str | None = None
    aqi_window: str | None = None  # pm25_ugm3 only: "hourly-mean" or "nowcast"
    heat_category: str | None = None  # exposure only: NWS heat-index tier name
    air_category: str | None = None  # exposure only: PM2.5 AQI category name
    compound: bool = False  # exposure only: heat AND air both at least mid-tier
    # exposure only: which axis (heat/air/both) bounds the level — see `_exposure_cells`.
    uncertainty_note: str | None = None
    method: str | None = None  # calibration method(s) behind a confirmed value
    reference: str | None = None  # reference monitor(s) the value was calibrated against
    # QC verdicts carried when a cell is built from suspicious (spike/flatline) readings because no
    # cleaner value existed — empty for a trusted or clean-provisional cell (ADR 0029).
    qc_flags: tuple[str, ...] = ()
    nodes: tuple[str, ...] = ()  # the node id(s) published into this cell (for the data download)

    def as_record(self) -> dict[str, object]:
        record: dict[str, object] = {
            "cell_id": self.cell_id,
            "label": self.label,
            "lat": self.lat,
            "lon": self.lon,
            "parameter": self.parameter,
            "bucket": self.bucket,
            "mean": round(self.mean, 3),
            "n": self.n,
            "provisional": self.provisional,
            "uncertainty": None if self.uncertainty is None else round(self.uncertainty, 3),
            "mean_member_sigma": (
                None if self.mean_member_sigma is None else round(self.mean_member_sigma, 3)
            ),
            "aqi": self.aqi,
            "category": self.category,
        }
        if self.nodes:
            record["nodes"] = list(self.nodes)
        if self.method:
            record["method"] = self.method
        if self.reference:
            record["reference"] = self.reference
        # A cell that is provisional *because it is suspicious* carries the QC verdict(s) that
        # flagged it, so a downstream reader can tell it from a merely-uncalibrated cell (ADR 0029,
        # invariant 4). Omitted when empty — a clean cell should not gain a hollow key.
        if self.qc_flags:
            record["qc_flags"] = list(self.qc_flags)
        if self.parameter == "pm25_ugm3":
            record["aqi_window"] = self.aqi_window
        if self.parameter == EXPOSURE:
            record["heat_category"] = self.heat_category
            record["air_category"] = self.air_category
            record["compound"] = self.compound
            record["uncertainty_note"] = self.uncertainty_note
        return record


def _snapshot_reading_props(parameter: str, reading: CellReading) -> dict[str, object]:
    """The GeoJSON properties one parameter's latest reading contributes to its cell's feature.

    Split out of :meth:`Surface.snapshot_geojson` so that method stays simple: this owns the
    per-parameter fan-out (value, the two uncertainties, provisional/QC-flag caveats, provenance,
    and the pm25/exposure extras), keyed by ``{parameter}_...`` so several parameters share one
    feature without colliding.
    """
    props: dict[str, object] = {parameter: round(reading.mean, 3)}
    if reading.uncertainty is not None:
        props[f"{parameter}_uncertainty"] = round(reading.uncertainty, 3)
    if reading.mean_member_sigma is not None:
        props[f"{parameter}_mean_member_sigma"] = round(reading.mean_member_sigma, 3)
    props[f"{parameter}_provisional"] = reading.provisional
    if reading.qc_flags:
        props[f"{parameter}_qc_flags"] = list(reading.qc_flags)
    if reading.method:
        props[f"{parameter}_method"] = reading.method
    if reading.reference:
        props[f"{parameter}_reference"] = reading.reference
    if parameter == "pm25_ugm3":
        props["pm25_aqi"] = reading.aqi
        props["aqi_category"] = reading.category
        props["aqi_window"] = reading.aqi_window
    if parameter == EXPOSURE:
        props["exposure_level"] = int(reading.mean)
        props["exposure_category"] = reading.category
        props["exposure_heat"] = reading.heat_category
        props["exposure_air"] = reading.air_category
        props["compound"] = reading.compound
        props["exposure_uncertainty_note"] = reading.uncertainty_note
    return props


@dataclass(frozen=True)
class Surface:
    """A full set of cell/hour/parameter rollups, renderable as GeoJSON or flat records."""

    interval: str
    cells: tuple[CellReading, ...]

    def to_records(self) -> list[dict[str, object]]:
        return [c.as_record() for c in self.cells]

    def newest_bucket(self) -> str | None:
        """The most recent hour bucket present anywhere in the surface, across every parameter.

        This is the one reference instant "now" means for a data-derived artifact: the same
        ``max(cell.bucket for cell in surface.cells)`` idiom ``cli.py``'s static publish steps
        already use to pick a snapshot's newest hour and a build's `data_hour`, and — because those
        are exactly the records the dashboard loads into ``state.cells`` — the same value the
        browser computes client-side as ``latestBucket()`` (``web/app.js``). Centralizing it here
        means a cell/parameter with no reading in this bucket is unambiguously stale, and every
        surface that reads "now" this way (the map, the alerts feed, the publish manifest) reads the
        same "now". ``None`` only when the surface has no cells at all.
        """
        return max((cell.bucket for cell in self.cells), default=None)

    def latest_by_cell(self) -> dict[str, dict[str, CellReading]]:
        """cell_id → parameter → the most recent hourly reading, for the map snapshot.

        NowCast rows are skipped here on purpose: the map snapshot promises the hourly-mean value
        for `pm25_ugm3` (`aqi_window="hourly-mean"`), and a NowCast reading — tagged
        `aqi_window="nowcast"` — is an alternate, opt-in view (`Surface.to_records`), never a
        silent substitute for it.
        """
        out: dict[str, dict[str, CellReading]] = defaultdict(dict)
        for cell in self.cells:
            if cell.aqi_window == AQI_WINDOW_NOWCAST:
                continue
            current = out[cell.cell_id].get(cell.parameter)
            if current is None or cell.bucket > current.bucket:
                out[cell.cell_id][cell.parameter] = cell
        return out

    def snapshot_geojson(self) -> dict[str, object]:
        """One GeoJSON point per cell, properties carrying each parameter's latest value."""
        features: list[dict[str, object]] = []
        for cell_id, by_param in sorted(self.latest_by_cell().items()):
            any_reading = next(iter(by_param.values()))
            props: dict[str, object] = {
                "cell_id": cell_id,
                "label": any_reading.label,
                "bucket": max(r.bucket for r in by_param.values()),
                "provisional": any(r.provisional for r in by_param.values()),
            }
            if any_reading.nodes:
                props["nodes"] = list(any_reading.nodes)
            for parameter, reading in by_param.items():
                props.update(_snapshot_reading_props(parameter, reading))
            features.append(
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Point",
                        "coordinates": [any_reading.lon, any_reading.lat],
                    },
                    "properties": props,
                }
            )
        return {"type": "FeatureCollection", "features": features}


def _cell_labels(config: NetworkConfig) -> dict[str, str]:
    """cell_id → the host-assigned name(s) of the node(s) published into that cell."""
    labels: dict[str, str] = {}
    for node in config.nodes:
        loc = node.public_location(config.grid_resolution_m)
        if loc is None:
            continue
        cell_id = f"{loc[0]:.6f},{loc[1]:.6f}"
        name = node.label or node.node_id
        labels[cell_id] = f"{labels[cell_id]} / {name}" if cell_id in labels else name
    return labels


def node_cell_map(config: NetworkConfig) -> dict[str, tuple[str, str]]:
    """node_id → (published cell_id, cell label) for every placed node.

    The cell_id and label are exactly the ones the surface publishes — same grid snap, same
    combined label — so a coverage-equity read (``qc.coverage_equity``) lines up cell-for-cell
    with the map. A node the host has not placed (no coordinate) is omitted, because it has no
    published cell to belong to.
    """
    labels = _cell_labels(config)
    out: dict[str, tuple[str, str]] = {}
    for node in config.nodes:
        loc = node.public_location(config.grid_resolution_m)
        if loc is None:
            continue
        cell_id = f"{loc[0]:.6f},{loc[1]:.6f}"
        out[node.node_id] = (cell_id, labels.get(cell_id, ""))
    return out


class _Buckets(NamedTuple):
    """Per-(cell, hour, parameter) accumulators built by :func:`_bucket_observations`."""

    trusted_vals: dict[tuple[str, str, str], list[float]]
    trusted_unc: dict[tuple[str, str, str], list[float]]
    trusted_methods: dict[tuple[str, str, str], set[str]]
    trusted_refs: dict[tuple[str, str, str], set[str]]
    provisional_vals: dict[tuple[str, str, str], list[float]]
    coords: dict[str, tuple[float, float]]
    cell_nodes: dict[str, set[str]]
    # Suspicious (spike/flatline) readings and the verdict(s) that flagged them. Kept in their own
    # lane so a spike never pulls a clean mean; surfaced only when they are the sole evidence for a
    # cell/hour, provisional and flagged (ADR 0029).
    suspicious_vals: dict[tuple[str, str, str], list[float]]
    suspicious_flags: dict[tuple[str, str, str], set[str]]


def _bucket_observations(
    observations: Iterable[Observation],
    locations: dict[str, tuple[float, float]],
    wanted: set[str],
    ref_by_node_param: dict[tuple[str, str], str],
    monitor_label: dict[str, str],
) -> _Buckets:
    """Sort observations into per-(cell, hour, parameter) trusted/provisional accumulators."""
    b = _Buckets(
        defaultdict(list),
        defaultdict(list),
        defaultdict(set),
        defaultdict(set),
        defaultdict(list),
        {},
        defaultdict(set),
        defaultdict(list),
        defaultdict(set),
    )
    for obs in observations:
        if obs.parameter not in wanted:
            continue
        loc = locations.get(obs.node_id)
        if loc is None:
            continue
        if obs.qc in QC_UNMAPPABLE:
            continue  # impossible or absent value — never placed, even provisionally (ADR 0029)
        lat, lon = loc
        cell_id = f"{lat:.6f},{lon:.6f}"
        b.coords[cell_id] = (lat, lon)
        b.cell_nodes[cell_id].add(obs.node_id)
        key = (cell_id, hour_bucket(obs.timestamp), obs.parameter)
        if obs.is_trustworthy:
            b.trusted_vals[key].append(obs.value)
            b.trusted_unc[key].append(obs.uncertainty if obs.uncertainty is not None else 0.0)
            parts = obs.calibration.split(".")  # "{parameter}.{method}.{node_id}"
            if len(parts) >= 2:
                b.trusted_methods[key].add(parts[1])
            ref = ref_by_node_param.get((obs.node_id, obs.parameter))
            if ref:
                b.trusted_refs[key].add(monitor_label.get(ref, ref))
        elif obs.qc in QC_SUSPICIOUS:
            # Own lane so a spike never pulls a clean mean; surfaced only when it is the sole
            # evidence for the cell/hour (ADR 0029).
            b.suspicious_vals[key].append(obs.value)
            b.suspicious_flags[key].add(obs.qc)
        else:
            b.provisional_vals[key].append(obs.value)
    return b


def _build_cells(b: _Buckets, labels: dict[str, str]) -> list[CellReading]:
    """Reduce the bucketed accumulators to one :class:`CellReading` per (cell, hour, parameter)."""
    cells: list[CellReading] = []
    for key in sorted(set(b.trusted_vals) | set(b.provisional_vals) | set(b.suspicious_vals)):
        cell_id, bucket, parameter = key
        lat, lon = b.coords[cell_id]
        trustworthy = b.trusted_vals.get(key, [])
        clean_provisional = b.provisional_vals.get(key, [])
        method: str | None = None
        reference: str | None = None
        qc_flags: tuple[str, ...] = ()
        if trustworthy:
            values = trustworthy
            provisional = False
            uncs = b.trusted_unc[key]
            has_unc = any(uncs)
            # (a) the plain mean of the members' own 1-sigmas — the old, simpler number.
            mean_member_sigma: float | None = (sum(uncs) / len(uncs)) if has_unc else None
            # (b) the cell's own standard error, combining independent per-value sigmas as
            # sqrt(sum(sigma_i^2)) / n (see the module docstring for the within-cell-correlation
            # caveat: this treats members as independent, which co-located/same-fit members
            # aren't fully, so it is a lower bound on the true combined uncertainty).
            uncertainty: float | None = (
                (math.sqrt(sum(u * u for u in uncs)) / len(uncs)) if has_unc else None
            )
            method = " / ".join(sorted(b.trusted_methods[key])) or None
            reference = " / ".join(sorted(b.trusted_refs[key])) or None
        elif clean_provisional:
            # Uncalibrated but not flagged: provisional, no numeric uncertainty, no QC flag.
            values = clean_provisional
            provisional = True
            uncertainty = None
            mean_member_sigma = None
        else:
            # Only suspicious readings remain: show them so the cell is not blank during an event,
            # provisional and carrying the QC verdict(s) that flagged them (ADR 0029).
            values = b.suspicious_vals[key]
            provisional = True
            uncertainty = None
            mean_member_sigma = None
            qc_flags = tuple(sorted(b.suspicious_flags.get(key, set())))
        mean = sum(values) / len(values)
        aqi: int | None = None
        category: str | None = None
        aqi_window: str | None = None
        if parameter == "pm25_ugm3":
            aqi, category = pm25_aqi(mean)
            aqi_window = AQI_WINDOW
        cells.append(
            CellReading(
                cell_id=cell_id,
                label=labels.get(cell_id, ""),
                lat=lat,
                lon=lon,
                parameter=parameter,
                bucket=bucket,
                mean=mean,
                n=len(values),
                provisional=provisional,
                uncertainty=uncertainty,
                mean_member_sigma=mean_member_sigma,
                aqi=aqi,
                category=category,
                aqi_window=aqi_window,
                method=method,
                reference=reference,
                qc_flags=qc_flags,
                nodes=tuple(sorted(b.cell_nodes[cell_id])),
            )
        )
    return cells


def aggregate(
    observations: Iterable[Observation],
    config: NetworkConfig,
    *,
    parameters: tuple[str, ...] = SURFACE_PARAMETERS,
) -> Surface:
    """Roll observations up to (cell, hour, parameter) means, preferring calibrated values.

    Beyond the requested ``parameters`` (the map surface by default), the network's hazard pack can
    add the observed parameters it needs to alert on — e.g. the cold pack pulls ``wind_chill_c``
    into the rollup so ``alerts`` can see it. The heat pack adds nothing already in the surface, so
    a heat network's output is byte-for-byte unchanged (ADR 0031).
    """
    locations = config.public_locations()
    labels = _cell_labels(config)
    pack = hazard_packs.resolve_pack(config.hazard_pack)
    wanted = set(parameters) | set(pack.surface_parameters())
    # Provenance lookups for the "show your work" trust view: which reference each node/parameter
    # was calibrated against, and that monitor's human label.
    ref_by_node_param = {(w.node_id, w.parameter): w.reference for w in config.calibration_windows}
    monitor_label = {m.monitor_id: (m.label or m.monitor_id) for m in config.reference_monitors}

    buckets = _bucket_observations(
        observations, locations, wanted, ref_by_node_param, monitor_label
    )
    cells = _build_cells(buckets, labels)
    cells.extend(_exposure_cells(cells))
    cells.extend(_nowcast_cells(cells))
    cells.sort(key=lambda c: (c.cell_id, c.bucket, c.parameter))
    return Surface(interval="hour", cells=tuple(cells))


def _exposure_uncertainty_note(heat: CellReading, air: CellReading, air_category: str) -> str:
    """The exposure cell's uncertainty statement: which axis bounds the published level.

    ``exposure.mean`` is an ordinal (the higher of two concern tiers), not a physical quantity, so
    it has no sigma of its own — fabricating one would misrepresent it. Instead this names the
    bounding component and points at *that* component's real signal (its category, and its own
    uncertainty or provisional status) so a reader can go verify it directly. ``air_category`` is
    passed in
    (rather than read off ``air.category``) because the caller has already established it is not
    ``None`` before building an exposure cell at all.
    """
    component = exposure_bounding_component(heat.mean, air_category)
    if component == "both":
        return (
            f"tied — heat ({heat_index_category(heat.mean)[1]}) and air ({air_category}) "
            "both bound this level; see each component's own uncertainty"
        )
    bound = heat if component == "heat" else air
    category = heat_index_category(heat.mean)[1] if component == "heat" else air_category
    if bound.uncertainty is not None:
        detail = f"cell standard error {bound.uncertainty:.3f}"
    elif bound.provisional:
        detail = "provisional, no numeric uncertainty"
    else:
        detail = "no numeric uncertainty"
    return f"bounded by {component}: {category} ({detail})"


def _exposure_cells(cells: list[CellReading]) -> list[CellReading]:
    """Derive the combined heat-and-air exposure layer for every cell/hour that has both halves.

    Built only where a calibrated-or-provisional heat-index cell *and* a PM2.5 cell exist for the
    same cell and hour, so the compound claim is never made from a single axis. The exposure cell
    is provisional whenever either component is, and carries no fabricated sigma — its ``mean`` is
    the ordinal level used for sorting; the human signal is in ``category``, the components, and
    ``uncertainty_note`` (which axis bounds the level — see `_exposure_uncertainty_note`).
    """
    by_cell_bucket: dict[tuple[str, str], dict[str, CellReading]] = defaultdict(dict)
    for cell in cells:
        by_cell_bucket[(cell.cell_id, cell.bucket)][cell.parameter] = cell
    out: list[CellReading] = []
    for (cell_id, bucket), params in by_cell_bucket.items():
        heat = params.get("heat_index_c")
        air = params.get("pm25_ugm3")
        if heat is None or air is None or air.category is None:
            continue
        level, name, compound = exposure_level(heat.mean, air.category)
        out.append(
            CellReading(
                cell_id=cell_id,
                label=heat.label,
                lat=heat.lat,
                lon=heat.lon,
                parameter=EXPOSURE,
                bucket=bucket,
                mean=float(level),
                n=min(heat.n, air.n),
                provisional=heat.provisional or air.provisional,
                uncertainty=None,
                mean_member_sigma=None,
                aqi=None,
                category=name,
                heat_category=heat_index_category(heat.mean)[1],
                air_category=air.category,
                compound=compound,
                uncertainty_note=_exposure_uncertainty_note(heat, air, air.category),
                # The derived level inherits its components' QC flags, so a compound cell built on a
                # suspicious heat or air reading stays visibly flagged (ADR 0029, invariant 4).
                qc_flags=tuple(sorted(set(heat.qc_flags) | set(air.qc_flags))),
                nodes=heat.nodes,
            )
        )
    return out


def _nowcast_cells(cells: list[CellReading]) -> list[CellReading]:
    """EPA NowCast PM2.5 reading per cell, from the trailing hourly means already rolled up.

    NowCast reacts faster to changing PM2.5 than a flat hourly mean — the EPA/AirNow "right now"
    air-quality number. Built once per cell, at its most recent PM2.5 bucket, from up to the 12
    preceding hourly means (most-recent-first); skipped when fewer than 3 are available
    (:func:`swelter.models.nowcast_concentration` returns ``None``). Tagged
    ``aqi_window="nowcast"`` — a distinct *alternate* reading, not a replacement: the hourly-mean
    cell for the same bucket is untouched, and `Surface.latest_by_cell` deliberately skips NowCast
    rows so the map snapshot never shows one in place of the promised hourly mean.
    """
    by_cell: dict[str, list[CellReading]] = defaultdict(list)
    for cell in cells:
        if cell.parameter == "pm25_ugm3" and cell.aqi_window != AQI_WINDOW_NOWCAST:
            by_cell[cell.cell_id].append(cell)
    out: list[CellReading] = []
    for readings in by_cell.values():
        window = sorted(readings, key=lambda c: c.bucket, reverse=True)[:12]
        nowcast = nowcast_concentration([c.mean for c in window])
        if nowcast is None:
            continue
        aqi, category = pm25_aqi(nowcast)
        latest = window[0]
        out.append(
            CellReading(
                cell_id=latest.cell_id,
                label=latest.label,
                lat=latest.lat,
                lon=latest.lon,
                parameter="pm25_ugm3",
                bucket=latest.bucket,
                mean=nowcast,
                n=len(window),
                provisional=any(c.provisional for c in window),
                uncertainty=None,
                mean_member_sigma=None,
                aqi=aqi,
                category=category,
                aqi_window=AQI_WINDOW_NOWCAST,
                # NowCast is built from the trailing hourly means, so it inherits every QC flag
                # those component hours carried — a flagged hour never drops out (ADR 0029).
                qc_flags=tuple(sorted({flag for c in window for flag in c.qc_flags})),
                nodes=latest.nodes,
            )
        )
    return out
