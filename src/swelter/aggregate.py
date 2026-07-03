"""Spatial/temporal rollups: the gridded heat-island and AQI surfaces the map and API read.

Aggregation snaps each node's reading to its *published* grid cell — never its precise
location — and rolls values up by hour. Neighbourhood-scale exposure is the question, so the grid
is neighbourhood resolution, not a city average.

On top of the per-parameter cells, a derived ``exposure`` layer combines the calibrated heat index
and the PM2.5 AQI into one published level per cell/hour (ADR 0009). It is built only where both
halves exist, inherits their provisional flag, and never blends them into a fabricated number — the
higher of the two concerns, plus a ``compound`` flag when both are elevated.

Trust is preserved through the rollup. For a given cell, hour, and parameter, the mean is taken
over *calibrated, QC-clean* values when any exist (and carries their mean 1-sigma uncertainty); a
cell that has only raw QC-clean readings is still shown, but marked ``provisional`` so the map can
render it as not-yet-fact rather than dropping it. A QC-rejected value is never placed on the map,
even provisionally. Each cell carries its host-assigned ``label`` so the dashboard can name a block
instead of an anonymous "Cell N". PM2.5 cells carry an EPA AQI value and category, computed from the
**hourly** mean (``aqi_window = "hourly-mean"``), not a 24-hour NowCast.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from typing import NamedTuple

from .config import NetworkConfig
from .models import (
    QC_REJECTED,
    Observation,
    exposure_level,
    heat_index_category,
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
    uncertainty: float | None = None  # mean 1-sigma of the calibrated values; None when provisional
    aqi: int | None = None
    category: str | None = None
    heat_category: str | None = None  # exposure only: NWS heat-index tier name
    air_category: str | None = None  # exposure only: PM2.5 AQI category name
    compound: bool = False  # exposure only: heat AND air both at least mid-tier
    method: str | None = None  # calibration method(s) behind a confirmed value
    reference: str | None = None  # reference monitor(s) the value was calibrated against
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
            "aqi": self.aqi,
            "category": self.category,
        }
        if self.nodes:
            record["nodes"] = list(self.nodes)
        if self.method:
            record["method"] = self.method
        if self.reference:
            record["reference"] = self.reference
        if self.parameter == "pm25_ugm3":
            record["aqi_window"] = AQI_WINDOW
        if self.parameter == EXPOSURE:
            record["heat_category"] = self.heat_category
            record["air_category"] = self.air_category
            record["compound"] = self.compound
        return record


@dataclass(frozen=True)
class Surface:
    """A full set of cell/hour/parameter rollups, renderable as GeoJSON or flat records."""

    interval: str
    cells: tuple[CellReading, ...]

    def to_records(self) -> list[dict[str, object]]:
        return [c.as_record() for c in self.cells]

    def latest_by_cell(self) -> dict[str, dict[str, CellReading]]:
        """cell_id → parameter → the most recent hourly reading, for the map snapshot."""
        out: dict[str, dict[str, CellReading]] = defaultdict(dict)
        for cell in self.cells:
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
                props[parameter] = round(reading.mean, 3)
                if reading.uncertainty is not None:
                    props[f"{parameter}_uncertainty"] = round(reading.uncertainty, 3)
                props[f"{parameter}_provisional"] = reading.provisional
                if reading.method:
                    props[f"{parameter}_method"] = reading.method
                if reading.reference:
                    props[f"{parameter}_reference"] = reading.reference
                if parameter == "pm25_ugm3":
                    props["pm25_aqi"] = reading.aqi
                    props["aqi_category"] = reading.category
                    props["aqi_window"] = AQI_WINDOW
                if parameter == EXPOSURE:
                    props["exposure_level"] = int(reading.mean)
                    props["exposure_category"] = reading.category
                    props["exposure_heat"] = reading.heat_category
                    props["exposure_air"] = reading.air_category
                    props["compound"] = reading.compound
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
    )
    for obs in observations:
        if obs.parameter not in wanted:
            continue
        loc = locations.get(obs.node_id)
        if loc is None:
            continue
        if obs.qc in QC_REJECTED:
            continue  # never place a QC-rejected value on the map, even as provisional
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
        else:
            b.provisional_vals[key].append(obs.value)
    return b


def _build_cells(b: _Buckets, labels: dict[str, str]) -> list[CellReading]:
    """Reduce the bucketed accumulators to one :class:`CellReading` per (cell, hour, parameter)."""
    cells: list[CellReading] = []
    for key in sorted(set(b.trusted_vals) | set(b.provisional_vals)):
        cell_id, bucket, parameter = key
        lat, lon = b.coords[cell_id]
        trustworthy = b.trusted_vals.get(key, [])
        method: str | None = None
        reference: str | None = None
        if trustworthy:
            values = trustworthy
            provisional = False
            uncs = b.trusted_unc[key]
            uncertainty: float | None = (sum(uncs) / len(uncs)) if any(uncs) else None
            method = " / ".join(sorted(b.trusted_methods[key])) or None
            reference = " / ".join(sorted(b.trusted_refs[key])) or None
        else:
            values = b.provisional_vals[key]
            provisional = True
            uncertainty = None
        mean = sum(values) / len(values)
        aqi: int | None = None
        category: str | None = None
        if parameter == "pm25_ugm3":
            aqi, category = pm25_aqi(mean)
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
                aqi=aqi,
                category=category,
                method=method,
                reference=reference,
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
    """Roll observations up to (cell, hour, parameter) means, preferring calibrated values."""
    locations = config.public_locations()
    labels = _cell_labels(config)
    wanted = set(parameters)
    # Provenance lookups for the "show your work" trust view: which reference each node/parameter
    # was calibrated against, and that monitor's human label.
    ref_by_node_param = {(w.node_id, w.parameter): w.reference for w in config.calibration_windows}
    monitor_label = {m.monitor_id: (m.label or m.monitor_id) for m in config.reference_monitors}

    buckets = _bucket_observations(
        observations, locations, wanted, ref_by_node_param, monitor_label
    )
    cells = _build_cells(buckets, labels)
    cells.extend(_exposure_cells(cells))
    cells.sort(key=lambda c: (c.cell_id, c.bucket, c.parameter))
    return Surface(interval="hour", cells=tuple(cells))


def _exposure_cells(cells: list[CellReading]) -> list[CellReading]:
    """Derive the combined heat-and-air exposure layer for every cell/hour that has both halves.

    Built only where a calibrated-or-provisional heat-index cell *and* a PM2.5 cell exist for the
    same cell and hour, so the compound claim is never made from a single axis. The exposure cell
    is provisional whenever either component is, and carries no fabricated value — its ``mean`` is
    the ordinal level used for sorting; the human signal is in ``category`` and the components.
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
                aqi=None,
                category=name,
                heat_category=heat_index_category(heat.mean)[1],
                air_category=air.category,
                compound=compound,
                nodes=heat.nodes,
            )
        )
    return out
