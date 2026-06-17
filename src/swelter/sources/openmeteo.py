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
import urllib.request
from dataclasses import dataclass
from typing import Any

from ..models import Observation, format_timestamp, heat_index_c, parse_timestamp

#: Provenance tag carried in the calibration field of every reading from this source.
SOURCE = "copernicus-cams"

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


#: Real Sacramento-area neighborhoods (approximate real centroids). The names and places are real.
SACRAMENTO: tuple[Neighborhood, ...] = (
    Neighborhood("Downtown", 38.5816, -121.4944),
    Neighborhood("Midtown", 38.5700, -121.4750),
    Neighborhood("East Sacramento", 38.5680, -121.4520),
    Neighborhood("Oak Park", 38.5470, -121.4630),
    Neighborhood("Curtis Park", 38.5450, -121.4760),
    Neighborhood("Land Park", 38.5380, -121.4980),
    Neighborhood("Tahoe Park", 38.5440, -121.4400),
    Neighborhood("Elmhurst", 38.5560, -121.4470),
    Neighborhood("Fruitridge Manor", 38.5260, -121.4640),
    Neighborhood("Meadowview", 38.4900, -121.4870),
    Neighborhood("South Land Park", 38.5100, -121.5070),
    Neighborhood("Pocket-Greenhaven", 38.4870, -121.5350),
    Neighborhood("North Natomas", 38.6500, -121.5050),
    Neighborhood("South Natomas", 38.6200, -121.5180),
    Neighborhood("Del Paso Heights", 38.6470, -121.4480),
    Neighborhood("Hagginwood", 38.6280, -121.4520),
    Neighborhood("Arden-Arcade", 38.6000, -121.3900),
    Neighborhood("Carmichael", 38.6260, -121.3290),
    Neighborhood("Rancho Cordova", 38.5890, -121.3030),
    Neighborhood("Colonial Heights", 38.5360, -121.4430),
    Neighborhood("Valley Hi", 38.4500, -121.4400),
    Neighborhood("Parkway", 38.4830, -121.4500),
    Neighborhood("College-Glen", 38.5560, -121.3950),
    Neighborhood("Rosemont", 38.5520, -121.3620),
    Neighborhood("West Sacramento", 38.5800, -121.5300),
    Neighborhood("Davis", 38.5449, -121.7405),
    Neighborhood("North Sacramento", 38.6200, -121.4500),
    Neighborhood("Gardenland", 38.6150, -121.5050),
    Neighborhood("Robla", 38.6650, -121.4450),
    Neighborhood("Florin", 38.4900, -121.4300),
    Neighborhood("Mangan Park", 38.5300, -121.4750),
    Neighborhood("Glen Elder", 38.5400, -121.4350),
)


def _get_json(url: str, *, timeout: float = 30.0) -> Any:
    with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310 (fixed open-meteo host)
        return json.loads(response.read().decode("utf-8"))


def _as_list(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [p for p in payload if isinstance(p, dict)]
    if isinstance(payload, dict):
        return [payload]
    return []


def _coords(places: tuple[Neighborhood, ...]) -> tuple[str, str]:
    return (",".join(f"{p.lat}" for p in places), ",".join(f"{p.lon}" for p in places))


def fetch(
    places: tuple[Neighborhood, ...] = SACRAMENTO,
    *,
    past_days: int = 2,
    forecast_days: int = 1,
) -> list[Observation]:
    """Fetch real hourly readings for each place (one batched call per endpoint)."""
    lats, lons = _coords(places)
    window = f"&past_days={past_days}&forecast_days={forecast_days}"
    air = _as_list(
        _get_json(f"{AIR_URL}?latitude={lats}&longitude={lons}&hourly=pm2_5,pm10{window}")
    )
    weather = _as_list(
        _get_json(
            f"{WEATHER_URL}?latitude={lats}&longitude={lons}"
            f"&hourly=temperature_2m,relative_humidity_2m{window}"
        )
    )
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
    places: tuple[Neighborhood, ...], languages: tuple[str, ...] = ("en", "es")
) -> dict[str, Any]:
    """A ``network.yaml`` document for the real neighborhoods (precise public centroids)."""
    return {
        "name": "swelter — Sacramento (real open data)",
        "grid_resolution_m": 150,
        "languages": list(languages),
        "reference_monitors": [],
        "nodes": [
            {
                "node_id": p.node_id,
                "label": p.name,
                "lat": p.lat,
                "lon": p.lon,
                "location": "precise",  # public neighborhood centroids, not private homes
            }
            for p in places
        ],
        "calibration_windows": [],  # this source is not swelter-calibrated
    }
