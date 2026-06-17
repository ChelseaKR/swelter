"""Real readings from Open-Meteo: Copernicus CAMS air quality + open weather, no API key.

This is the *real-data* path. It pulls genuine hourly air-quality (PM2.5, PM10 from the EU's
Copernicus Atmosphere Monitoring Service) and weather (temperature, relative humidity) for real
neighborhoods, and maps them into swelter ``Observation`` records so the rest of the pipeline — QC,
aggregation, the map/table/list, the API, export — runs unchanged.

Honesty notes, because they matter here:

* These are **real readings for real places**, current and hourly — not the synthetic demo. But the
  source is an atmospheric **model/reanalysis** (CAMS), **not a physical sensor on each corner**,
  and swelter does **not** calibrate it (CAMS data is already produced and QC'd upstream). Every
  value carries ``calibration = "copernicus-cams"`` so its provenance travels with it and it is
  never presented as a swelter-calibrated low-cost-sensor reading.
* The coordinates are real neighborhood centroids; Open-Meteo snaps each to its model grid cell.

Attribution (required by Open-Meteo / Copernicus, and right to show): "Air-quality data from the
Copernicus Atmosphere Monitoring Service (CAMS) via Open-Meteo; weather from Open-Meteo."
"""

from __future__ import annotations

import json
import math
import sys
import time
import urllib.request
from dataclasses import dataclass
from typing import Any

from ..models import Observation, format_timestamp, heat_index_c, parse_timestamp
from ._california_places import CALIFORNIA as _CALIFORNIA_RAW

#: Provenance tag carried in the calibration field of every reading from this source.
SOURCE = "copernicus-cams"
ATTRIBUTION = (
    "Real hourly readings for California cities from the Copernicus Atmosphere Monitoring "
    "Service (CAMS) via Open-Meteo — atmospheric model data, not physical sensors, "
    "and not swelter-calibrated."
)

AIR_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"


@dataclass(frozen=True)
class Neighborhood:
    """A real place: a name and a real centroid coordinate."""

    name: str
    lat: float
    lon: float

    @property
    def node_id(self) -> str:
        return self.name.lower().replace(" ", "-").replace("/", "-")


#: Every California place from the validated data module, wrapped as Neighborhoods. Public city
#: centroids (no homes, no people); point-in-polygon checked against US Census county boundaries.
CALIFORNIA: tuple[Neighborhood, ...] = tuple(
    Neighborhood(name, lat, lon) for name, lat, lon in _CALIFORNIA_RAW
)


def _get_json(url: str, *, timeout: float = 30.0, retries: int = 4) -> Any:
    """GET + parse JSON, retrying transient network failures (timeouts, SSL handshake drops) with
    exponential backoff. A statewide fetch is many calls; one flaky connection must not sink the
    whole run and drop the live demo to its synthetic fallback."""
    last: Exception | None = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310 (fixed host)
                return json.loads(response.read().decode("utf-8"))
        except (OSError, ValueError) as exc:  # URLError, timeout, SSL, truncated body all subclass
            last = exc
            if attempt < retries - 1:
                time.sleep(min(8.0, 2.0**attempt))
    assert last is not None
    raise last


def _as_list(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [p for p in payload if isinstance(p, dict)]
    if isinstance(payload, dict):
        return [payload]
    return []


def _coords(places: tuple[Neighborhood, ...]) -> tuple[str, str]:
    return (",".join(f"{p.lat}" for p in places), ",".join(f"{p.lon}" for p in places))


def fetch(
    places: tuple[Neighborhood, ...] = CALIFORNIA,
    *,
    past_days: int = 2,
    forecast_days: int = 1,
    chunk: int = 100,
) -> list[Observation]:
    """Fetch real hourly readings for each place. Coordinates are batched, ``chunk`` places per
    call, so a statewide list of hundreds of places stays a handful of requests (Open-Meteo caps
    how many coordinates one URL may carry). Results stay index-aligned with ``places``."""
    window = f"&past_days={past_days}&forecast_days={forecast_days}"
    air: list[dict[str, Any]] = []
    weather: list[dict[str, Any]] = []
    for i in range(0, len(places), chunk):
        group = places[i : i + chunk]
        lats, lons = _coords(group)
        try:
            chunk_air = _as_list(
                _get_json(f"{AIR_URL}?latitude={lats}&longitude={lons}&hourly=pm2_5,pm10{window}")
            )
            chunk_weather = _as_list(
                _get_json(
                    f"{WEATHER_URL}?latitude={lats}&longitude={lons}"
                    f"&hourly=temperature_2m,relative_humidity_2m{window}"
                )
            )
        except (OSError, ValueError) as exc:
            # One chunk failing (after retries) should not lose the whole state — keep the cities
            # that did come back. Pad so air/weather stay index-aligned with `places`.
            print(
                f"swelter: open-meteo chunk {i // chunk} failed ({exc}); skipping", file=sys.stderr
            )
            chunk_air, chunk_weather = [], []
        air += chunk_air if len(chunk_air) == len(group) else [{} for _ in group]
        weather += chunk_weather if len(chunk_weather) == len(group) else [{} for _ in group]
    return to_observations(places, air, weather)


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
    out.append(
        Observation(
            node_id=node_id,
            timestamp=ts,
            parameter=parameter,
            value=round(numeric, 2),
            unit=unit,
            calibration=SOURCE,
        )
    )


def to_observations(
    places: tuple[Neighborhood, ...],
    air: list[dict[str, Any]],
    weather: list[dict[str, Any]],
) -> list[Observation]:
    """Map Open-Meteo hourly arrays to swelter observations (pure — no network)."""
    out: list[Observation] = []
    for i, place in enumerate(places):
        a = air[i].get("hourly", {}) if i < len(air) else {}
        w = weather[i].get("hourly", {}) if i < len(weather) else {}
        times = a.get("time") or w.get("time") or []
        pm25, pm10 = a.get("pm2_5", []), a.get("pm10", [])
        temp, humid = w.get("temperature_2m", []), w.get("relative_humidity_2m", [])
        for j, raw_t in enumerate(times):
            ts = format_timestamp(parse_timestamp(str(raw_t)))
            t = temp[j] if j < len(temp) else None
            h = humid[j] if j < len(humid) else None
            _emit(out, place.node_id, ts, "temp_c", t, "degC")
            _emit(out, place.node_id, ts, "humidity_pct", h, "%")
            _emit(out, place.node_id, ts, "pm25_ugm3", pm25[j] if j < len(pm25) else None, "ug/m3")
            _emit(out, place.node_id, ts, "pm10_ugm3", pm10[j] if j < len(pm10) else None, "ug/m3")
            if t is not None and h is not None:
                with_hi = heat_index_c(float(t), float(h))
                _emit(out, place.node_id, ts, "heat_index_c", with_hi, "degC")
    return out


def network_doc(
    places: tuple[Neighborhood, ...] = CALIFORNIA,
    *,
    name: str = "swelter — California (real open data)",
    languages: tuple[str, ...] = ("en", "es"),
) -> dict[str, Any]:
    """A ``network.yaml`` document for the real places (precise public centroids)."""
    return {
        "name": name,
        "grid_resolution_m": 150,
        "languages": list(languages),
        "reference_monitors": [],
        "nodes": [
            {
                "node_id": p.node_id,
                "label": p.name,
                "lat": p.lat,
                "lon": p.lon,
                "location": "precise",  # public city/place centroids, not private homes
            }
            for p in places
        ],
        "calibration_windows": [],  # this source is not swelter-calibrated
    }
