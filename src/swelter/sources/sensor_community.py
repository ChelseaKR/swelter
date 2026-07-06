"""Real readings from Sensor.Community — a grassroots network of community low-cost air sensors.

Sensor.Community (formerly Luftdaten) is thousands of community-built, community-owned low-cost
sensors (SDS011/SPS30 for particulates; DHT/BME for temperature and humidity). This is precisely
the kind of network swelter is *for*: real, low-cost, community-owned — and **uncalibrated**. So
swelter ingests these as RAW and the dashboard shows them **provisional**, the honest posture for a
sensor that drifts and reads high in humidity. That is not a hedge; it is the whole point — these
are the readings the project says a reference monitor should correct before they are trusted.

The keyless "area" filter returns each sensor's *latest* reading (last ~5 minutes), so this is a
current snapshot, not a time series. Coverage is dense in Europe (the network's origin) and sparse
in the US. No API key.

Attribution: "Readings from the Sensor.Community network (https://sensor.community), CC BY-SA 4.0."
"""

from __future__ import annotations

import contextlib
import math
from dataclasses import dataclass
from typing import Any

from ..models import Observation, format_timestamp, heat_index_c, parse_timestamp
from ._http import get_json

AREA_URL = "https://data.sensor.community/airrohr/v1/filter/area="
ATTRIBUTION = (
    "Real readings from the Sensor.Community network of community low-cost sensors "
    "(sensor.community, CC BY-SA 4.0) — uncalibrated, so shown raw / provisional."
)

# Sensor.Community value_type → (swelter parameter, unit). P2 = PM2.5, P1 = PM10.
_MAP: dict[str, tuple[str, str]] = {
    "P2": ("pm25_ugm3", "ug/m3"),
    "P1": ("pm10_ugm3", "ug/m3"),
    "temperature": ("temp_c", "degC"),
    "humidity": ("humidity_pct", "%"),
}

# The SDS011 — the most common Sensor.Community PM sensor — clamps to 999.9 ug/m3 when it saturates
# or faults. That sentinel is not a reading: real PM2.5 never reaches it (the EPA scale caps at
# 500.4), and keeping it would paint a broken sensor as "Hazardous". So drop PM at/above this.
_PM_OVER_RANGE = 999.0


@dataclass(frozen=True)
class Area:
    """A circular query area: a name and a centre, with a radius in kilometres."""

    name: str
    lat: float
    lon: float
    radius_km: float = 30.0


#: A dense default — Stuttgart, the network's origin, has hundreds of live community sensors.
STUTTGART = Area("Stuttgart", 48.7758, 9.1829, 30.0)


def _get_json(url: str, *, timeout: float = 30.0, retries: int = 4) -> Any:
    """GET + parse JSON via the shared resilient fetch (timeouts, backoff, HTTP 429/5xx, bad JSON).

    Raises :class:`swelter.sources._http.SourceError` on exhaustion. See
    :mod:`swelter.sources._http`."""
    return get_json(url, timeout=timeout, retries=retries)


def _emit(
    out: list[Observation], node_id: str, ts: str, parameter: str, value: Any, unit: str
) -> None:
    if value is None:
        return
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return
    if not math.isfinite(numeric):
        return
    # RAW: these are uncalibrated community sensors. QC and the map will mark them provisional.
    out.append(
        Observation(
            node_id=node_id, timestamp=ts, parameter=parameter, value=round(numeric, 2), unit=unit
        )
    )


def fetch(area: Area = STUTTGART) -> tuple[list[Observation], dict[str, tuple[str, float, float]]]:
    """Fetch each sensor's latest reading in the area. Returns (observations, node metadata)."""
    rows = _get_json(f"{AREA_URL}{area.lat},{area.lon},{area.radius_km}")
    return parse_measurements(rows if isinstance(rows, list) else [])


def _latest_by_sensor(rows: list[Any]) -> dict[int, dict[str, Any]]:
    """A sensor can appear in several rows; keep only its latest measurement."""
    latest: dict[int, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        sensor = row.get("sensor") or {}
        sid = sensor.get("id")
        ts = row.get("timestamp")
        if sid is None or not ts:
            continue
        if sid not in latest or str(ts) > str(latest[sid].get("timestamp", "")):
            latest[sid] = row
    return latest


def _emit_sensor_readings(
    sid: int,
    row: dict[str, Any],
    out: list[Observation],
    nodes: dict[str, tuple[str, float, float]],
) -> None:
    """Parse one sensor's latest row into raw observations, appended to ``out``/``nodes``."""
    loc = row.get("location") or {}
    try:
        lat, lon = float(loc["latitude"]), float(loc["longitude"])
    except (KeyError, TypeError, ValueError):
        return
    node_id = f"sc-{sid}"
    nodes[node_id] = (f"Sensor {sid}", lat, lon)
    ts = format_timestamp(parse_timestamp(str(row["timestamp"]).replace(" ", "T")))
    values: dict[str, Any] = {}
    for value in row.get("sensordatavalues") or []:
        if isinstance(value, dict) and value.get("value_type") in _MAP:
            values[value["value_type"]] = value.get("value")
    for pm in ("P2", "P1"):  # drop the SDS011 over-range/fault sentinel before it reaches QC
        with contextlib.suppress(TypeError, ValueError):
            if values.get(pm) is not None and float(values[pm]) >= _PM_OVER_RANGE:
                values[pm] = None
    for vtype, (parameter, unit) in _MAP.items():
        _emit(out, node_id, ts, parameter, values.get(vtype), unit)
    temp, humid = values.get("temperature"), values.get("humidity")
    if temp is not None and humid is not None:
        with contextlib.suppress(TypeError, ValueError):
            hi = heat_index_c(float(temp), float(humid))
            _emit(out, node_id, ts, "heat_index_c", hi, "degC")


def parse_measurements(
    rows: list[Any],
) -> tuple[list[Observation], dict[str, tuple[str, float, float]]]:
    """Map Sensor.Community measurements to raw observations + node metadata (pure — no network)."""
    latest = _latest_by_sensor(rows)
    out: list[Observation] = []
    nodes: dict[str, tuple[str, float, float]] = {}
    for sid, row in latest.items():
        _emit_sensor_readings(sid, row, out, nodes)
    return out, nodes


def network_doc(
    name: str,
    nodes: dict[str, tuple[str, float, float]],
    languages: tuple[str, ...] = ("en", "es"),
) -> dict[str, Any]:
    """A ``network.yaml`` document for the discovered community sensors (precise real locations)."""
    return {
        "name": f"swelter — {name} (real community sensors, Sensor.Community)",
        "grid_resolution_m": 150,
        "languages": list(languages),
        "reference_monitors": [],
        "nodes": [
            {"node_id": nid, "label": label, "lat": lat, "lon": lon, "location": "precise"}
            for nid, (label, lat, lon) in sorted(nodes.items())
        ],
        "calibration_windows": [],  # community sensors here are uncalibrated (raw/provisional)
    }
