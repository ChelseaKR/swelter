"""Real readings from Open-Meteo: Copernicus CAMS air quality + open weather, no API key.

This is the *real-data* path. It pulls genuine hourly air-quality (PM2.5, PM10 from the EU's
Copernicus Atmosphere Monitoring Service) and weather (temperature, relative humidity) for real
neighborhoods, and maps them into swelter ``Observation`` records so the rest of the pipeline — QC,
aggregation, the map/table/list, the API, export — runs unchanged.

Honesty notes, because they matter here:

* These are **real readings for real places**, current and hourly — not the synthetic demo. But the
  source is an atmospheric **model/reanalysis** (CAMS), **not a physical sensor on each corner**,
  and swelter does **not** calibrate it (CAMS data is already produced and QC'd upstream). Every
  value carries ``source = "openmeteo"`` while calibration remains ``raw`` so its provenance
  travels independently and it is never presented as a swelter-calibrated sensor reading.
* The coordinates are real neighborhood centroids; Open-Meteo snaps each to its model grid cell.
* **Hours that have not happened are not ingested.** The same endpoints serve elapsed hours and
  forecast hours in one array, and swelter's "now" is the newest hour present in the store
  (ADR 0035). A forecast hour entering the store therefore becomes the current reading: the map,
  the Now card and the alerts feed all resolve to an hour that has not occurred. That is a
  different kind of wrongness from an uncalibrated reading — the caveats that do travel
  (``provisional``, "Upstream model") say *how the number was produced*, never that *the hour it
  describes has not happened*. So :func:`to_observations` drops every hour after the fetch's
  reference instant (ADR 0039), and a prediction never becomes an observation.

Attribution (required by Open-Meteo / Copernicus, and right to show): "Air-quality data from the
Copernicus Atmosphere Monitoring Service (CAMS) via Open-Meteo; weather from Open-Meteo."
"""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from ..config import LOCATION_PUBLIC_PLACE
from ..models import (
    SOURCE_OPENMETEO,
    Observation,
    format_timestamp,
    heat_index_c,
    parse_timestamp,
    wbgt_c,
)
from ._california_places import CALIFORNIA as _CALIFORNIA_RAW
from ._http import SourceError, get_json

#: Stable source identity carried separately from calibration state.
SOURCE = SOURCE_OPENMETEO
#: Open-Meteo re-publishes Copernicus CAMS under CC BY 4.0 (open-meteo.com/en/license); the
#: underlying Copernicus terms are themselves attribution-only, so this is the binding term.
LICENSE = "CC BY 4.0 (Copernicus CAMS via Open-Meteo)"
LICENSE_URL = "https://open-meteo.com/en/license"
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
    """GET + parse JSON via the shared resilient fetch (timeouts, backoff, HTTP 429/5xx, bad JSON).

    A statewide fetch is many calls; one flaky connection must not sink the whole run and drop the
    live demo to its synthetic fallback. See :mod:`swelter.sources._http`."""
    return get_json(url, timeout=timeout, retries=retries)


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
    now: datetime | None = None,
) -> list[Observation]:
    """Fetch real hourly readings for each place. Coordinates are batched, ``chunk`` places per
    call, so a statewide list of hundreds of places stays a handful of requests (Open-Meteo caps
    how many coordinates one URL may carry). Results stay index-aligned with ``places``.

    ``forecast_days`` stays at 1 because that is how Open-Meteo returns *today's already-elapsed*
    hours; dropping it to 0 would end the window at the close of yesterday and there would be no
    current reading at all. The forecast hours it also returns are discarded by
    :func:`to_observations` against ``now`` (the fetch instant, or an explicit reference for
    tests), so the window stays wide and the store stays a store of observations (ADR 0039)."""
    reference = now or datetime.now(UTC)
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
        except (SourceError, OSError, ValueError) as exc:
            # One chunk failing (after retries) should not lose the whole state — keep the cities
            # that did come back. Pad so air/weather stay index-aligned with `places`.
            print(
                f"swelter: open-meteo chunk {i // chunk} failed ({exc}); skipping", file=sys.stderr
            )
            chunk_air, chunk_weather = [], []
        air += chunk_air if len(chunk_air) == len(group) else [{} for _ in group]
        weather += chunk_weather if len(chunk_weather) == len(group) else [{} for _ in group]
    print(
        "swelter: open-meteo — ingesting hours at or before "
        f"{format_timestamp(reference)}; later hours in the response are forecast, not readings",
        file=sys.stderr,
    )
    return to_observations(places, air, weather, now=reference)


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
            source=SOURCE,
        )
    )


def to_observations(
    places: tuple[Neighborhood, ...],
    air: list[dict[str, Any]],
    weather: list[dict[str, Any]],
    *,
    now: datetime | None = None,
) -> list[Observation]:
    """Map Open-Meteo hourly arrays to swelter observations (no network).

    An hour later than ``now`` is a **forecast**, not a reading, and is not emitted (ADR 0039).
    Open-Meteo returns elapsed and forecast hours in one array with nothing in the payload marking
    which is which, and swelter's ``Observation`` has no field that could carry the distinction —
    so the boundary is here, where the response is still a response and not yet a record. ``now``
    defaults to the wall clock precisely because a caller who forgets it must get the safe
    behaviour: an explicit reference instant is for tests and for reproducing a past fetch, never
    an opt-in to clipping.

    The clip is a comparison against a real instant, not a rule about the data, so it is the one
    wall-clock read in this pipeline. Everything downstream stays clock-free: "now" is still the
    newest bucket present (ADR 0035), which is now guaranteed to be an hour that has happened.
    """
    reference = now or datetime.now(UTC)
    out: list[Observation] = []
    for i, place in enumerate(places):
        a = air[i].get("hourly", {}) if i < len(air) else {}
        w = weather[i].get("hourly", {}) if i < len(weather) else {}
        times = a.get("time") or w.get("time") or []
        pm25, pm10 = a.get("pm2_5", []), a.get("pm10", [])
        temp, humid = w.get("temperature_2m", []), w.get("relative_humidity_2m", [])
        for j, raw_t in enumerate(times):
            parsed = parse_timestamp(str(raw_t))
            if parsed > reference:
                continue  # an hour that has not happened is a prediction, not an observation
            ts = format_timestamp(parsed)
            t = temp[j] if j < len(temp) else None
            h = humid[j] if j < len(humid) else None
            _emit(out, place.node_id, ts, "temp_c", t, "degC")
            _emit(out, place.node_id, ts, "humidity_pct", h, "%")
            _emit(out, place.node_id, ts, "pm25_ugm3", pm25[j] if j < len(pm25) else None, "ug/m3")
            _emit(out, place.node_id, ts, "pm10_ugm3", pm10[j] if j < len(pm10) else None, "ug/m3")
            if t is not None and h is not None:
                with_hi = heat_index_c(float(t), float(h))
                _emit(out, place.node_id, ts, "heat_index_c", with_hi, "degC")
                with_wbgt = wbgt_c(float(t), float(h))
                _emit(out, place.node_id, ts, "wbgt_c", with_wbgt, "degC")
    return out


def network_doc(
    places: tuple[Neighborhood, ...] = CALIFORNIA,
    *,
    name: str = "swelter — California (real open data)",
    languages: tuple[str, ...] = ("en", "es"),
) -> dict[str, Any]:
    """A ``network.yaml`` document for the real places (exact public centroids, no hosts).

    Every node is ``location: public-place``: the coordinate is exact and published as-is, and
    there is no host behind it whose consent could be recorded. These were ``precise`` until issue
    #166, which made ``config.consent_concerns`` warn once per place per route on every deploy —
    several hundred warnings that named nobody who could act on them, drowning the one warning that
    would matter (ADR 0040).
    """
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
                # Public city/place centroids, not private homes: exact, and hostless.
                "location": LOCATION_PUBLIC_PLACE,
            }
            for p in places
        ],
        "calibration_windows": [],  # this source is not swelter-calibrated
    }
