"""Real neighborhood-scale readings from OpenAQ v3 — physical sensors across California (API key).

OpenAQ aggregates thousands of real air-quality stations (community PurpleAir nodes, regulatory
reference monitors, and many other networks). Coverage is uneven: dense in some neighborhoods,
sparse or absent elsewhere, and a statewide pull is capped at a few hundred sites — so this is
real hardware at neighborhood resolution, not block-by-block and not a coarse atmospheric model.

Honesty, as always: these are real physical sensors, but swelter does not calibrate them, so their
readings ingest as RAW and the dashboard shows them **provisional** — the same posture as any
uncalibrated low-cost sensor. The reading is real; the trust is not yet earned by a swelter fit.

Auth: OpenAQ v3 needs a free API key (sign up at https://explore.openaq.org/register), sent as the
``X-API-Key`` header. Pass it via ``--api-key`` or the ``OPENAQ_API_KEY`` environment variable.

The "latest" snapshot is one call per location, so a statewide pull is throttled and capped.

Licensing: OpenAQ aggregates many original providers. Its v3 location records expose each
provider's license and attribution, and its Terms require downstream users to follow those terms;
there is no honest blanket Creative Commons license for a mixed statewide export.
"""

from __future__ import annotations

import contextlib
import math
import time
from dataclasses import replace
from datetime import timedelta
from typing import Any

from ..models import Observation, format_timestamp, heat_index_c, parse_timestamp
from ._http import SourceError, get_json

API = "https://api.openaq.org/v3"
#: OpenAQ's terms defer to each original provider's license. Until the export carries the v3
#: per-location license ledger, this deliberately refuses to assert a blanket CC license.
LICENSE = "Provider-specific terms (see OpenAQ location metadata)"
ATTRIBUTION = (
    "Real readings accessed via OpenAQ; original-provider licenses and attribution vary by "
    "location (docs.openaq.org/about/terms). Uncalibrated, so shown raw / provisional."
)

#: California bounding box (west, south, east, north).
CALIFORNIA_BBOX = (-124.5, 32.5, -114.1, 42.05)

#: OpenAQ parameter name → (swelter parameter, unit).
_PARAM: dict[str, tuple[str, str]] = {
    "pm25": ("pm25_ugm3", "ug/m3"),
    "pm10": ("pm10_ugm3", "ug/m3"),
    "temperature": ("temp_c", "degC"),
    "relativehumidity": ("humidity_pct", "%"),
}


def _get_json(url: str, api_key: str, *, timeout: float = 45.0, retries: int = 4) -> Any:
    """GET + parse JSON with the API-key header via the shared resilient fetch.

    Retries transient failures (timeouts, dropped connections, bad JSON, HTTP 429/408/5xx),
    honoring a 429 ``Retry-After``; raises :class:`SourceError` on exhaustion or a non-retryable
    HTTP status. See :mod:`swelter.sources._http`."""
    return get_json(url, headers={"X-API-Key": api_key}, timeout=timeout, retries=retries)


def _locations(
    bbox: tuple[float, float, float, float],
    api_key: str,
    *,
    max_locations: int,
    per_page: int = 1000,
) -> list[dict[str, Any]]:
    """Page through the locations in the bbox up to ``max_locations``."""
    west, south, east, north = bbox
    out: list[dict[str, Any]] = []
    page = 1
    while len(out) < max_locations:
        url = (
            f"{API}/locations?bbox={west},{south},{east},{north}"
            f"&limit={min(per_page, 1000)}&page={page}"
        )
        try:
            payload = _get_json(url, api_key)
        except SourceError:
            # The first page failing leaves nothing to fetch; a later page failing keeps the
            # locations already paged in. Either way, one bad page must not crash the whole run.
            break
        results = payload.get("results", []) if isinstance(payload, dict) else []
        if not isinstance(results, list) or not results:
            break
        out += [r for r in results if isinstance(r, dict)]
        if len(results) < per_page:
            break
        page += 1
    return out[:max_locations]


def _sensor_parameters(locations: list[dict[str, Any]]) -> dict[int, tuple[str, str]]:
    """Map each sensor id to its (swelter parameter, unit), across all locations."""
    sensor_param: dict[int, tuple[str, str]] = {}
    for loc in locations:
        for sensor in loc.get("sensors") or []:
            if not isinstance(sensor, dict):
                continue
            name = (sensor.get("parameter") or {}).get("name")
            sid = sensor.get("id")
            if name in _PARAM and isinstance(sid, int):
                sensor_param[sid] = _PARAM[name]
    return sensor_param


def parse_latest(
    node_id: str, results: list[Any], sensor_param: dict[int, tuple[str, str]]
) -> list[Observation]:
    """Map a location's /latest results to raw observations (pure — no network)."""
    out: list[Observation] = []
    seen: dict[str, tuple[float, str]] = {}
    for row in results:
        if not isinstance(row, dict):
            continue
        sid = row.get("sensorsId", row.get("sensorId"))
        param_unit = sensor_param.get(sid) if isinstance(sid, int) else None
        if not param_unit:
            continue
        parameter, unit = param_unit
        value = row.get("value")
        when = (row.get("datetime") or {}).get("utc") or (row.get("date") or {}).get("utc")
        if value is None or not when:
            continue
        try:
            ts = format_timestamp(parse_timestamp(str(when)))
            numeric = float(value)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(numeric):
            continue
        # RAW: real sensor, but not swelter-calibrated → the map shows it provisional.
        out.append(
            Observation(
                node_id=node_id,
                timestamp=ts,
                parameter=parameter,
                value=round(numeric, 2),
                unit=unit,
            )
        )
        seen[parameter] = (numeric, ts)
    if "temp_c" in seen and "humidity_pct" in seen:
        (temp, ts), (humid, _) = seen["temp_c"], seen["humidity_pct"]
        with contextlib.suppress(TypeError, ValueError):
            hi = heat_index_c(temp, humid)
            out.append(
                Observation(
                    node_id=node_id,
                    timestamp=ts,
                    parameter="heat_index_c",
                    value=round(hi, 2),
                    unit="degC",
                )
            )
    return out


def fetch(
    api_key: str,
    *,
    bbox: tuple[float, float, float, float] = CALIFORNIA_BBOX,
    max_locations: int = 200,
    throttle_s: float = 1.1,
) -> tuple[list[Observation], dict[str, tuple[str, float, float]]]:
    """Fetch the latest reading for each real sensor location in the bbox (one /latest call each).

    Throttled to respect the free-tier rate limit and capped at ``max_locations`` so a statewide
    pull is bounded. Returns (observations, node metadata). A single failing location is skipped.
    """
    locations = _locations(bbox, api_key, max_locations=max_locations)
    sensor_param = _sensor_parameters(locations)
    out: list[Observation] = []
    nodes: dict[str, tuple[str, float, float]] = {}
    for loc in locations:
        coords = loc.get("coordinates") or {}
        lid = loc.get("id")
        try:
            lat, lon = float(coords["latitude"]), float(coords["longitude"])
        except (KeyError, TypeError, ValueError):
            continue
        if not isinstance(lid, int):
            continue
        try:
            payload = _get_json(f"{API}/locations/{lid}/latest", api_key)
        except (SourceError, OSError, ValueError):
            continue  # skip this site; one flaky location must not sink the run
        results = payload.get("results", []) if isinstance(payload, dict) else []
        if throttle_s:
            time.sleep(throttle_s)
        node_id = f"oaq-{lid}"
        emitted = parse_latest(node_id, results if isinstance(results, list) else [], sensor_param)
        if emitted:
            out += emitted
            nodes[node_id] = (str(loc.get("name") or f"Site {lid}"), lat, lon)
    out = _to_snapshot(out)
    live = {o.node_id for o in out}
    nodes = {nid: meta for nid, meta in nodes.items() if nid in live}
    return out, nodes


def _to_snapshot(observations: list[Observation], *, window_h: float = 6.0) -> list[Observation]:
    """Collapse "latest" readings to a single most-recent hour. Each sensor reports on its own
    clock, so otherwise they scatter across hourly buckets and any single hour looks sparse.
    /latest is a snapshot, so present it as one: drop readings staler than ``window_h`` before the
    newest, and stamp the rest at the newest hour — the live network at once, like an AQI map."""
    if not observations:
        return observations
    times = [parse_timestamp(o.timestamp) for o in observations]
    newest = max(times)
    cutoff = newest - timedelta(hours=window_h)
    snap = format_timestamp(newest.replace(minute=0, second=0, microsecond=0))
    return [
        replace(o, timestamp=snap) for o, t in zip(observations, times, strict=True) if t >= cutoff
    ]


def network_doc(
    name: str,
    nodes: dict[str, tuple[str, float, float]],
    languages: tuple[str, ...] = ("en", "es"),
) -> dict[str, Any]:
    """A ``network.yaml`` document for the discovered OpenAQ sensors (precise real locations)."""
    return {
        "name": f"swelter — {name} (real sensors, OpenAQ)",
        "grid_resolution_m": 150,
        "languages": list(languages),
        "reference_monitors": [],
        "nodes": [
            {"node_id": nid, "label": label, "lat": lat, "lon": lon, "location": "precise"}
            for nid, (label, lat, lon) in sorted(nodes.items())
        ],
        "calibration_windows": [],  # real sensors, but not swelter-calibrated (raw/provisional)
    }
