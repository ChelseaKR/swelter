"""Spatial/temporal rollups: the gridded heat-island and AQI surfaces the map and API read.

Aggregation snaps each node's reading to its *published* grid cell — never its precise
location — and rolls values up by hour. Block-scale exposure is the question, so the grid is
neighbourhood resolution, not a city average.

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

from .config import NetworkConfig
from .models import QC_REJECTED, Observation, parse_timestamp, pm25_aqi

#: Parameters that appear on the map/surface (raw-only diagnostic fields are excluded).
SURFACE_PARAMETERS = ("temp_c", "heat_index_c", "pm25_ugm3", "pm10_ugm3", "no2_ppb")

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
        if self.parameter == "pm25_ugm3":
            record["aqi_window"] = AQI_WINDOW
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
            for parameter, reading in by_param.items():
                props[parameter] = round(reading.mean, 3)
                if reading.uncertainty is not None:
                    props[f"{parameter}_uncertainty"] = round(reading.uncertainty, 3)
                props[f"{parameter}_provisional"] = reading.provisional
                if parameter == "pm25_ugm3":
                    props["pm25_aqi"] = reading.aqi
                    props["aqi_category"] = reading.category
                    props["aqi_window"] = AQI_WINDOW
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

    trusted_vals: dict[tuple[str, str, str], list[float]] = defaultdict(list)
    trusted_unc: dict[tuple[str, str, str], list[float]] = defaultdict(list)
    provisional_vals: dict[tuple[str, str, str], list[float]] = defaultdict(list)
    coords: dict[str, tuple[float, float]] = {}

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
        coords[cell_id] = (lat, lon)
        key = (cell_id, hour_bucket(obs.timestamp), obs.parameter)
        if obs.is_trustworthy:
            trusted_vals[key].append(obs.value)
            trusted_unc[key].append(obs.uncertainty if obs.uncertainty is not None else 0.0)
        else:
            provisional_vals[key].append(obs.value)

    cells: list[CellReading] = []
    for key in sorted(set(trusted_vals) | set(provisional_vals)):
        cell_id, bucket, parameter = key
        lat, lon = coords[cell_id]
        trustworthy = trusted_vals.get(key, [])
        if trustworthy:
            values = trustworthy
            provisional = False
            uncs = trusted_unc[key]
            uncertainty: float | None = (sum(uncs) / len(uncs)) if any(uncs) else None
        else:
            values = provisional_vals[key]
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
            )
        )
    return Surface(interval="hour", cells=tuple(cells))
