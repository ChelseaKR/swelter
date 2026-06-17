"""Spatial/temporal rollups: the gridded heat-island and AQI surfaces the map and API read.

Aggregation snaps each node's reading to its *published* grid cell — never its precise
location — and rolls values up by hour. Block-scale exposure is the question, so the grid is
neighbourhood resolution, not a city average.

Trust is preserved through the rollup. For a given cell, hour, and parameter, the mean is
taken over *calibrated, QC-clean* values when any exist; a cell that has only raw or flagged
readings is still shown, but marked ``provisional`` so the map can render it as not-yet-fact
rather than dropping it. PM2.5 cells carry their EPA AQI value and category.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

from .config import NetworkConfig
from .models import Observation, parse_timestamp, pm25_aqi

#: Parameters that appear on the map/surface (raw-only diagnostic fields are excluded).
SURFACE_PARAMETERS = ("temp_c", "heat_index_c", "pm25_ugm3", "pm10_ugm3", "no2_ppb")


def hour_bucket(timestamp: str) -> str:
    dt = parse_timestamp(timestamp).replace(minute=0, second=0, microsecond=0)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class CellReading:
    """One parameter's rolled-up value for one grid cell in one hour."""

    cell_id: str
    lat: float
    lon: float
    parameter: str
    bucket: str
    mean: float
    n: int
    provisional: bool
    aqi: int | None = None
    category: str | None = None

    def as_record(self) -> dict[str, object]:
        return {
            "cell_id": self.cell_id,
            "lat": self.lat,
            "lon": self.lon,
            "parameter": self.parameter,
            "bucket": self.bucket,
            "mean": round(self.mean, 3),
            "n": self.n,
            "provisional": self.provisional,
            "aqi": self.aqi,
            "category": self.category,
        }


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
                "bucket": max(r.bucket for r in by_param.values()),
                "provisional": any(r.provisional for r in by_param.values()),
            }
            for parameter, reading in by_param.items():
                props[parameter] = round(reading.mean, 3)
                if parameter == "pm25_ugm3":
                    props["pm25_aqi"] = reading.aqi
                    props["aqi_category"] = reading.category
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


def aggregate(
    observations: Iterable[Observation],
    config: NetworkConfig,
    *,
    parameters: tuple[str, ...] = SURFACE_PARAMETERS,
) -> Surface:
    """Roll observations up to (cell, hour, parameter) means, preferring calibrated values."""
    locations = config.public_locations()
    wanted = set(parameters)

    # bucketed[(cell_id, bucket, parameter)] = (trustworthy_values, all_values, lat, lon)
    trusted: dict[tuple[str, str, str], list[float]] = defaultdict(list)
    everything: dict[tuple[str, str, str], list[float]] = defaultdict(list)
    coords: dict[str, tuple[float, float]] = {}

    for obs in observations:
        if obs.parameter not in wanted:
            continue
        loc = locations.get(obs.node_id)
        if loc is None:
            continue
        lat, lon = loc
        cell_id = f"{lat:.6f},{lon:.6f}"
        coords[cell_id] = (lat, lon)
        key = (cell_id, hour_bucket(obs.timestamp), obs.parameter)
        everything[key].append(obs.value)
        if obs.is_trustworthy:
            trusted[key].append(obs.value)

    cells: list[CellReading] = []
    for key in sorted(everything):
        cell_id, bucket, parameter = key
        lat, lon = coords[cell_id]
        trustworthy = trusted.get(key, [])
        if trustworthy:
            values, provisional = trustworthy, False
        else:
            values, provisional = everything[key], True
        mean = sum(values) / len(values)
        aqi: int | None = None
        category: str | None = None
        if parameter == "pm25_ugm3":
            aqi, category = pm25_aqi(mean)
        cells.append(
            CellReading(
                cell_id=cell_id,
                lat=lat,
                lon=lon,
                parameter=parameter,
                bucket=bucket,
                mean=mean,
                n=len(values),
                provisional=provisional,
                aqi=aqi,
                category=category,
            )
        )
    return Surface(interval="hour", cells=tuple(cells))
