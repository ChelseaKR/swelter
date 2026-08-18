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
import re
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, TypeGuard
from urllib.parse import urlsplit

from ..models import (
    SOURCE_OPENAQ,
    Observation,
    derive_heat_metrics,
    format_timestamp,
    parse_timestamp,
)
from . import _california_boundary
from ._http import SourceError, get_json

API = "https://api.openaq.org/v3"
#: OpenAQ's terms defer to each original provider's license. Until the export carries the v3
#: per-location license ledger, this deliberately refuses to assert a blanket CC license.
LICENSE = "Provider-specific terms (see OpenAQ location metadata)"
LICENSE_URL = "https://docs.openaq.org/about/terms"
ATTRIBUTION = (
    "Real readings accessed via OpenAQ; original-provider licenses and attribution vary by "
    "location (docs.openaq.org/about/terms). Uncalibrated, so shown raw / provisional."
)
LICENSE_LEDGER_FILENAME = "source-license-ledger.json"
_NODE_ID = re.compile(r"^oaq-(\d+)$")


def _is_positive_id(value: object) -> TypeGuard[int]:
    """OpenAQ IDs are positive integers; JSON booleans must not pass as ``1``/``0``."""
    return type(value) is int and value > 0


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
    include: Callable[[dict[str, Any]], bool] | None = None,
) -> list[dict[str, Any]]:
    """Page through bbox candidates until ``max_locations`` accepted locations are found.

    ``include`` is applied before the cap. This matters for jurisdiction-shaped scopes: locations
    outside the boundary must not consume a slot merely because the upstream API queries a box.
    """
    west, south, east, north = bbox
    limit = min(per_page, 1000)  # OpenAQ's own page-size cap
    out: list[dict[str, Any]] = []
    page = 1
    while len(out) < max_locations:
        url = f"{API}/locations?bbox={west},{south},{east},{north}&limit={limit}&page={page}"
        try:
            payload = _get_json(url, api_key)
        except SourceError:
            # The first page failing leaves nothing to fetch; a later page failing keeps the
            # locations already paged in. Either way, one bad page must not crash the whole run.
            break
        results = payload.get("results", []) if isinstance(payload, dict) else []
        if not isinstance(results, list) or not results:
            break
        candidates = [row for row in results if isinstance(row, dict)]
        out += [row for row in candidates if include is None or include(row)]
        # A short page means the server has no more to give — compare against the *actual*
        # requested page size (`limit`, clamped to OpenAQ's 1000 cap), not the raw `per_page`
        # argument: a caller passing per_page > 1000 would otherwise see every full (1000-row)
        # page read as "short" against the un-clamped per_page and stop after page one.
        if len(results) < limit:
            break
        page += 1
    return out[:max_locations]


def _coordinates(location: dict[str, Any]) -> tuple[float, float] | None:
    """Return a location's finite ``(latitude, longitude)``, or ``None`` when malformed."""
    coordinates = location.get("coordinates")
    if not isinstance(coordinates, dict):
        return None
    try:
        lat = float(coordinates["latitude"])
        lon = float(coordinates["longitude"])
    except (KeyError, TypeError, ValueError):
        return None
    return (lat, lon) if math.isfinite(lat) and math.isfinite(lon) else None


def _in_california(location: dict[str, Any]) -> bool:
    coordinates = _coordinates(location)
    return coordinates is not None and _california_boundary.contains(*coordinates)


def _sensor_parameters(locations: list[dict[str, Any]]) -> dict[int, tuple[str, str]]:
    """Map each sensor id to its (swelter parameter, unit), across all locations."""
    sensor_param: dict[int, tuple[str, str]] = {}
    for loc in locations:
        for sensor in loc.get("sensors") or []:
            if not isinstance(sensor, dict):
                continue
            name = (sensor.get("parameter") or {}).get("name")
            sid = sensor.get("id")
            if name in _PARAM and _is_positive_id(sid):
                sensor_param[sid] = _PARAM[name]
    return sensor_param


def _license_catalog(locations: list[dict[str, Any]], api_key: str) -> dict[int, dict[str, Any]]:
    """Resolve every referenced location-license ID to its authoritative license resource."""
    ids: set[int] = set()
    for location in locations:
        licenses = location.get("licenses")
        if not isinstance(licenses, list):
            continue
        for license_ref in licenses:
            if isinstance(license_ref, dict) and _is_positive_id(license_ref.get("id")):
                ids.add(license_ref["id"])

    catalog: dict[int, dict[str, Any]] = {}
    for license_id in sorted(ids):
        payload = _get_json(f"{API}/licenses/{license_id}", api_key)
        results = payload.get("results", []) if isinstance(payload, dict) else []
        detail = results[0] if isinstance(results, list) and results else None
        if (
            not isinstance(detail, dict)
            or not _is_positive_id(detail.get("id"))
            or detail.get("id") != license_id
        ):
            raise SourceError(f"OpenAQ license {license_id} metadata is unavailable")
        if not isinstance(detail.get("name"), str) or not isinstance(detail.get("sourceUrl"), str):
            raise SourceError(f"OpenAQ license {license_id} lacks a name or source URL")
        catalog[license_id] = detail
    return catalog


def build_license_ledger(
    locations: list[dict[str, Any]],
    catalog: dict[int, dict[str, Any]],
    *,
    fetched_at: str | None = None,
) -> dict[str, Any]:
    """Build a per-location OpenAQ license/attribution ledger from v3 metadata."""
    fetched = fetched_at or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    entries: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for location in locations:
        location_id = location.get("id")
        if not _is_positive_id(location_id):
            continue
        location_name = str(location.get("name") or f"Site {location_id}")
        provider_raw = location.get("provider")
        provider = (
            str(provider_raw.get("name"))
            if isinstance(provider_raw, dict) and provider_raw.get("name")
            else ""
        )
        license_refs = location.get("licenses")
        if not isinstance(license_refs, list) or not license_refs:
            excluded.append(
                {
                    "location_id": location_id,
                    "location_name": location_name,
                    "reason": "OpenAQ returned no location license metadata",
                }
            )
            continue
        location_entries = 0
        for license_ref in license_refs:
            if not isinstance(license_ref, dict) or not _is_positive_id(license_ref.get("id")):
                continue
            detail = catalog.get(license_ref["id"])
            if detail is None:
                continue
            attribution_raw = license_ref.get("attribution")
            attribution = (
                str(attribution_raw.get("name"))
                if isinstance(attribution_raw, dict) and attribution_raw.get("name")
                else ""
            )
            attribution_url = (
                str(attribution_raw.get("url"))
                if isinstance(attribution_raw, dict) and attribution_raw.get("url")
                else ""
            )
            unavailable = [
                field
                for field, value in (("provider", provider), ("attribution", attribution))
                if not value
            ]
            entries.append(
                {
                    "location_id": location_id,
                    "license_id": license_ref["id"],
                    "location_name": location_name,
                    "provider": provider,
                    "license_name": str(detail["name"]),
                    "license_url": str(detail["sourceUrl"]),
                    "attribution": attribution,
                    "attribution_url": attribution_url,
                    "valid_from": license_ref.get("dateFrom"),
                    "valid_to": license_ref.get("dateTo"),
                    "upstream_url": f"{API}/locations/{location_id}",
                    "fetched_at": fetched,
                    "unavailable_fields": unavailable,
                }
            )
            location_entries += 1
        if not location_entries:
            excluded.append(
                {
                    "location_id": location_id,
                    "location_name": location_name,
                    "reason": "OpenAQ license references could not be resolved",
                }
            )
    return {
        "schema_version": 1,
        "source": "OpenAQ v3",
        "generated_at": fetched,
        "entries": entries,
        "excluded_locations": excluded,
    }


_LEDGER_FIELDS = frozenset(
    {"schema_version", "source", "generated_at", "entries", "excluded_locations"}
)
_ENTRY_FIELDS = frozenset(
    {
        "location_id",
        "license_id",
        "location_name",
        "provider",
        "license_name",
        "license_url",
        "attribution",
        "attribution_url",
        "valid_from",
        "valid_to",
        "upstream_url",
        "fetched_at",
        "unavailable_fields",
    }
)
_EXCLUDED_FIELDS = frozenset({"location_id", "location_name", "reason"})
_UNAVAILABLE_FIELDS = frozenset({"provider", "attribution"})


def _normalized_text(value: object, *, required: bool) -> str:
    if not isinstance(value, str) or value != value.strip():
        raise ValueError("OpenAQ ledger text must be a normalized string")
    if required and not value:
        raise ValueError("OpenAQ ledger text must not be empty")
    if any(ord(character) < 32 for character in value):
        raise ValueError("OpenAQ ledger text must not contain control characters")
    return value


def _normalized_timestamp(value: object) -> str:
    text = _normalized_text(value, required=True)
    try:
        parsed = datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError as exc:
        raise ValueError("OpenAQ ledger timestamp must be canonical UTC ISO-8601") from exc
    if format_timestamp(parsed) != text:
        raise ValueError("OpenAQ ledger timestamp must be canonical UTC ISO-8601")
    return text


def _normalized_date(value: object) -> str | None:
    if value is None:
        return None
    text = _normalized_text(value, required=True)
    try:
        parsed = date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError("OpenAQ license validity must be an ISO-8601 date") from exc
    if parsed.isoformat() != text:
        raise ValueError("OpenAQ license validity must be a normalized ISO-8601 date")
    return text


def _normalized_https_url(value: object, *, required: bool) -> str:
    text = _normalized_text(value, required=required)
    if not text and not required:
        return ""
    try:
        parsed = urlsplit(text)
        hostname = parsed.hostname
        _port = parsed.port  # validate a supplied port rather than leaving a latent ValueError
    except ValueError as exc:
        raise ValueError("OpenAQ ledger URL is malformed") from exc
    if (
        parsed.scheme != "https"
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ValueError("OpenAQ ledger URLs must be absolute credential-free HTTPS URLs")
    return text


@dataclass(frozen=True)
class _NormalizedEntry:
    location_id: int
    license_id: int
    location_name: str
    provider: str
    license_name: str
    license_url: str
    attribution: str
    attribution_url: str
    valid_from: str | None
    valid_to: str | None
    upstream_url: str
    fetched_at: str
    unavailable_fields: tuple[str, ...]

    @property
    def identity(self) -> tuple[object, ...]:
        return (
            self.location_id,
            self.license_id,
            self.license_name,
            self.license_url,
            self.valid_from,
            self.valid_to,
            self.provider,
            self.attribution,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "location_id": self.location_id,
            "license_id": self.license_id,
            "location_name": self.location_name,
            "provider": self.provider,
            "license_name": self.license_name,
            "license_url": self.license_url,
            "attribution": self.attribution,
            "attribution_url": self.attribution_url,
            "valid_from": self.valid_from,
            "valid_to": self.valid_to,
            "upstream_url": self.upstream_url,
            "fetched_at": self.fetched_at,
            "unavailable_fields": list(self.unavailable_fields),
        }


@dataclass(frozen=True)
class _NormalizedExclusion:
    location_id: int
    location_name: str
    reason: str

    @property
    def identity(self) -> tuple[int, str, str]:
        return (self.location_id, self.location_name, self.reason)

    def to_dict(self) -> dict[str, object]:
        return {
            "location_id": self.location_id,
            "location_name": self.location_name,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class _NormalizedLedger:
    generated_at: str
    entries: tuple[_NormalizedEntry, ...]
    excluded_locations: tuple[_NormalizedExclusion, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "source": "OpenAQ v3",
            "generated_at": self.generated_at,
            "entries": [entry.to_dict() for entry in self.entries],
            "excluded_locations": [item.to_dict() for item in self.excluded_locations],
        }


def _normalize_entry(raw: dict[str, Any]) -> _NormalizedEntry:
    if set(raw) != _ENTRY_FIELDS:
        raise ValueError("OpenAQ ledger entry has an unexpected shape")
    location_id = raw["location_id"]
    license_id = raw["license_id"]
    if not _is_positive_id(location_id) or not _is_positive_id(license_id):
        raise ValueError("OpenAQ ledger IDs must be positive non-boolean integers")

    provider = _normalized_text(raw["provider"], required=False)
    attribution = _normalized_text(raw["attribution"], required=False)
    unavailable_raw = raw["unavailable_fields"]
    if not isinstance(unavailable_raw, list) or not all(
        isinstance(field, str) for field in unavailable_raw
    ):
        raise ValueError("OpenAQ unavailable_fields must be a string array")
    unavailable = tuple(sorted(unavailable_raw))
    if len(unavailable) != len(set(unavailable)) or not set(unavailable) <= _UNAVAILABLE_FIELDS:
        raise ValueError("OpenAQ unavailable_fields contains duplicates or unknown names")
    expected_unavailable = {
        field
        for field, value in (("provider", provider), ("attribution", attribution))
        if not value
    }
    if set(unavailable) != expected_unavailable or not (provider or attribution):
        raise ValueError("OpenAQ provider/attribution availability evidence is inconsistent")

    valid_from = _normalized_date(raw["valid_from"])
    valid_to = _normalized_date(raw["valid_to"])
    if (
        valid_from is not None
        and valid_to is not None
        and date.fromisoformat(valid_from) > date.fromisoformat(valid_to)
    ):
        raise ValueError("OpenAQ license validity starts after it ends")

    return _NormalizedEntry(
        location_id=location_id,
        license_id=license_id,
        location_name=_normalized_text(raw["location_name"], required=True),
        provider=provider,
        license_name=_normalized_text(raw["license_name"], required=True),
        license_url=_normalized_https_url(raw["license_url"], required=True),
        attribution=attribution,
        attribution_url=_normalized_https_url(raw["attribution_url"], required=False),
        valid_from=valid_from,
        valid_to=valid_to,
        upstream_url=_normalized_https_url(raw["upstream_url"], required=True),
        fetched_at=_normalized_timestamp(raw["fetched_at"]),
        unavailable_fields=unavailable,
    )


def _normalize_exclusion(raw: dict[str, Any]) -> _NormalizedExclusion:
    if set(raw) != _EXCLUDED_FIELDS or not _is_positive_id(raw.get("location_id")):
        raise ValueError("OpenAQ excluded location has an unexpected shape or invalid ID")
    return _NormalizedExclusion(
        location_id=raw["location_id"],
        location_name=_normalized_text(raw["location_name"], required=True),
        reason=_normalized_text(raw["reason"], required=True),
    )


def _normalized_ledger(ledger: object) -> _NormalizedLedger | None:
    try:
        if not isinstance(ledger, dict) or set(ledger) != _LEDGER_FIELDS:
            return None
        schema_version = ledger["schema_version"]
        if (
            type(schema_version) is not int
            or schema_version != 1
            or ledger["source"] != "OpenAQ v3"
        ):
            return None
        generated_at = _normalized_timestamp(ledger["generated_at"])
        entries_raw = ledger["entries"]
        exclusions_raw = ledger["excluded_locations"]
        if not isinstance(entries_raw, list) or not entries_raw:
            return None
        if not isinstance(exclusions_raw, list):
            return None
        if not all(isinstance(item, dict) for item in [*entries_raw, *exclusions_raw]):
            return None
        entries = tuple(_normalize_entry(item) for item in entries_raw)
        exclusions = tuple(_normalize_exclusion(item) for item in exclusions_raw)
    except (KeyError, TypeError, ValueError):
        return None

    identities = [entry.identity for entry in entries]
    exclusion_identities = [item.identity for item in exclusions]
    if len(identities) != len(set(identities)) or len(exclusion_identities) != len(
        set(exclusion_identities)
    ):
        return None
    generated = datetime.strptime(generated_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    if any(
        datetime.strptime(entry.fetched_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC) > generated
        for entry in entries
    ):
        return None
    return _NormalizedLedger(generated_at, entries, exclusions)


def _validity_boundary(value: object, *, end: bool) -> datetime | None:
    normalized = _normalized_date(value)
    if normalized is None:
        return None
    parsed = date.fromisoformat(normalized)
    boundary = datetime(parsed.year, parsed.month, parsed.day, tzinfo=UTC)
    return boundary + timedelta(days=1) if end else boundary


def _entry_covers(entry: dict[str, Any], observation: Observation) -> bool:
    try:
        timestamp = parse_timestamp(observation.timestamp)
        start = _validity_boundary(entry.get("valid_from"), end=False)
        end = _validity_boundary(entry.get("valid_to"), end=True)
    except (TypeError, ValueError):
        return False
    return (start is None or timestamp >= start) and (end is None or timestamp < end)


def _ledger_entries(ledger: object) -> list[dict[str, Any]] | None:
    normalized = _normalized_ledger(ledger)
    return None if normalized is None else [entry.to_dict() for entry in normalized.entries]


def _observations_have_terms(
    observations: Iterable[Observation], entries_by_location: dict[int, list[dict[str, Any]]]
) -> bool:
    for observation in observations:
        match = _NODE_ID.fullmatch(observation.node_id)
        if match is None:
            return False
        candidates = entries_by_location.get(int(match.group(1)), [])
        if not any(_entry_covers(entry, observation) for entry in candidates):
            return False
    return True


def validate_license_ledger(ledger: object, *, observations: Iterable[Observation] = ()) -> bool:
    """Return whether a ledger is complete for the OpenAQ observations being released."""
    normalized = _normalized_ledger(ledger)
    if normalized is None:
        return False
    entries_by_location: dict[int, list[dict[str, Any]]] = {}
    for normalized_entry in normalized.entries:
        entry = normalized_entry.to_dict()
        entries_by_location.setdefault(entry["location_id"], []).append(entry)
    return _observations_have_terms(observations, entries_by_location)


def license_terms_by_observation(
    ledger: object, observations: Iterable[Observation]
) -> dict[tuple[str, str, str], dict[str, str]]:
    """Resolve the exact provider terms covering each exported observation timestamp."""
    items = list(observations)
    entries = _ledger_entries(ledger)
    if entries is None or not validate_license_ledger(ledger, observations=items):
        raise ValueError("OpenAQ ledger does not cover every observation")
    entries_by_location: dict[int, list[dict[str, Any]]] = {}
    for entry in entries:
        entries_by_location.setdefault(entry["location_id"], []).append(entry)

    resolved: dict[tuple[str, str, str], dict[str, str]] = {}
    for observation in items:
        match = _NODE_ID.fullmatch(observation.node_id)
        if match is None:  # validate_license_ledger already rejects this; keep the boundary local.
            raise ValueError(f"invalid OpenAQ node identity: {observation.node_id}")
        covering = [
            entry
            for entry in entries_by_location[int(match.group(1))]
            if _entry_covers(entry, observation)
        ]
        licenses = sorted(
            {f"{entry['license_name']} ({entry['license_url']})" for entry in covering}
        )
        attributions = sorted(
            {
                str(entry.get("attribution") or entry.get("provider"))
                for entry in covering
                if entry.get("attribution") or entry.get("provider")
            }
        )
        resolved[(observation.node_id, observation.timestamp, observation.source)] = {
            "license": "; ".join(licenses),
            "attribution": "; ".join(attributions),
        }
    return resolved


def merge_license_ledgers(previous: object, current: object) -> dict[str, Any]:
    """Union two strictly valid ledgers without dropping historical terms."""
    previous_normalized = _normalized_ledger(previous)
    current_normalized = _normalized_ledger(current)
    if previous_normalized is None or current_normalized is None:
        raise ValueError("cannot accumulate an invalid OpenAQ source-license ledger")

    merged_entries: dict[tuple[object, ...], _NormalizedEntry] = {}
    for entry in [*previous_normalized.entries, *current_normalized.entries]:
        identity = entry.identity
        prior = merged_entries.get(identity)
        if prior is None or entry.fetched_at >= prior.fetched_at:
            merged_entries[identity] = entry

    exclusions = {
        item.identity: item
        for item in [
            *previous_normalized.excluded_locations,
            *current_normalized.excluded_locations,
        ]
    }
    merged = {
        "schema_version": 1,
        "source": "OpenAQ v3",
        "generated_at": current_normalized.generated_at,
        "entries": sorted(
            (entry.to_dict() for entry in merged_entries.values()),
            key=lambda entry: (
                entry["location_id"],
                str(entry.get("valid_from") or ""),
                str(entry.get("valid_to") or ""),
                entry["license_id"],
                entry["license_name"],
            ),
        ),
        "excluded_locations": [exclusions[key].to_dict() for key in sorted(exclusions)],
    }
    if not validate_license_ledger(merged):
        raise ValueError("merged OpenAQ source-license ledger is invalid")
    return merged


def parse_latest(
    location_id: int, results: list[Any], sensor_param: dict[int, tuple[str, str]]
) -> list[Observation]:
    """Map one location's `/latest` rows, rejecting records bound to any other location."""
    if not _is_positive_id(location_id):
        return []
    node_id = f"oaq-{location_id}"
    out: list[Observation] = []
    seen: dict[str, tuple[float, str]] = {}
    for row in results:
        if not isinstance(row, dict):
            continue
        row_location_id = row.get("locationsId")
        if not _is_positive_id(row_location_id) or row_location_id != location_id:
            continue
        sid = row.get("sensorsId", row.get("sensorId"))
        param_unit = sensor_param.get(sid) if _is_positive_id(sid) else None
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
                source=SOURCE_OPENAQ,
            )
        )
        seen[parameter] = (numeric, ts)
    out.extend(_derived_heat_observations(node_id, seen))
    return out


def _derived_heat_observations(
    node_id: str, seen: dict[str, tuple[float, str]]
) -> list[Observation]:
    """Heat index and estimated shade WBGT for one location, when its inputs support them.

    Derived only from in-range inputs, so a reading the pipeline rejects as impossible cannot
    re-enter the map wearing a derived parameter's name (ADR 0041).
    """
    if "temp_c" not in seen or "humidity_pct" not in seen:
        return []
    (temp, ts), (humid, _) = seen["temp_c"], seen["humidity_pct"]
    derived: list[Observation] = []
    with contextlib.suppress(TypeError, ValueError):
        derived = [
            Observation(
                node_id=node_id,
                timestamp=ts,
                parameter=parameter,
                value=round(value, 2),
                unit="degC",
                source=SOURCE_OPENAQ,
            )
            for parameter, value in derive_heat_metrics(temp, humid).items()
        ]
    return derived


def fetch(
    api_key: str,
    *,
    bbox: tuple[float, float, float, float] = CALIFORNIA_BBOX,
    max_locations: int = 200,
    throttle_s: float = 1.1,
    license_ledger: dict[str, Any] | None = None,
) -> tuple[list[Observation], dict[str, tuple[str, float, float]]]:
    """Fetch each California sensor location in the bbox (one ``/latest`` call per site).

    OpenAQ accepts a rectangle, not a state polygon. Every bbox candidate is therefore checked
    against the packaged U.S. Census California boundary before it counts toward ``max_locations``
    or triggers a per-site request. The check is repeated here defensively so a replacement location
    provider cannot bypass the jurisdiction boundary. A single failing location is skipped.
    """
    locations = _locations(bbox, api_key, max_locations=max_locations, include=_in_california)
    locations = [location for location in locations if _in_california(location)]
    catalog = _license_catalog(locations, api_key)
    ledger = build_license_ledger(locations, catalog)
    eligible_location_ids = {
        entry["location_id"] for entry in ledger["entries"] if isinstance(entry, dict)
    }
    locations = [location for location in locations if location.get("id") in eligible_location_ids]
    sensor_param = _sensor_parameters(locations)
    out: list[Observation] = []
    nodes: dict[str, tuple[str, float, float]] = {}
    for loc in locations:
        lid = loc.get("id")
        coordinates = _coordinates(loc)
        if coordinates is None:
            continue
        lat, lon = coordinates
        if not _is_positive_id(lid):
            continue
        location_id = int(lid)
        try:
            payload = _get_json(f"{API}/locations/{location_id}/latest", api_key)
        except (SourceError, OSError, ValueError):
            continue  # skip this site; one flaky location must not sink the run
        results = payload.get("results", []) if isinstance(payload, dict) else []
        if throttle_s:
            time.sleep(throttle_s)
        node_id = f"oaq-{location_id}"
        emitted = parse_latest(
            location_id, results if isinstance(results, list) else [], sensor_param
        )
        if emitted:
            out += emitted
            nodes[node_id] = (str(loc.get("name") or f"Site {lid}"), lat, lon)
    out = _to_snapshot(out)
    live = {o.node_id for o in out}
    nodes = {nid: meta for nid, meta in nodes.items() if nid in live}
    ledger["entries"] = [
        entry for entry in ledger["entries"] if f"oaq-{entry['location_id']}" in live
    ]
    if out and not validate_license_ledger(ledger, observations=out):
        raise SourceError("OpenAQ readings have no publishable per-location license ledger")
    if license_ledger is not None:
        license_ledger.clear()
        license_ledger.update(ledger)
    return out, nodes


def _to_snapshot(observations: list[Observation], *, window_h: float = 6.0) -> list[Observation]:
    """Drop stale ``/latest`` rows without rewriting the provider's measurement timestamps.

    The visualization may choose a display window, but stored/exported facts keep their observed
    time. Re-stamping rows can cross a provider-license validity boundary and would destroy temporal
    provenance.
    """
    if not observations:
        return observations
    times = [parse_timestamp(o.timestamp) for o in observations]
    newest = max(times)
    cutoff = newest - timedelta(hours=window_h)
    return [o for o, timestamp in zip(observations, times, strict=True) if timestamp >= cutoff]


def network_doc(
    name: str,
    nodes: dict[str, tuple[str, float, float]],
    languages: tuple[str, ...] = ("en", "es"),
) -> dict[str, Any]:
    """A California-scoped ``network.yaml`` document for discovered OpenAQ sensors.

    Vendor coordinates are used for the jurisdiction test, then published through swelter's normal
    coarse-grid path. An upstream public coordinate is not treated as host consent to republish a
    precise porch-level location.
    """
    return {
        "name": f"swelter — {name} (real sensors, OpenAQ)",
        "grid_resolution_m": 150,
        "languages": list(languages),
        "geographic_scope": {
            "id": "US-CA",
            "boundary": _california_boundary.SCOPE_ID,
        },
        "reference_monitors": [],
        "nodes": [
            {"node_id": nid, "label": label, "lat": lat, "lon": lon, "location": "coarse"}
            for nid, (label, lat, lon) in sorted(nodes.items())
            if _california_boundary.contains(lat, lon)
        ],
        "calibration_windows": [],  # real sensors, but not swelter-calibrated (raw/provisional)
    }
