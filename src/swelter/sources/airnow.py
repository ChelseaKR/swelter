"""Regulatory reference readings from US EPA AirNow / AQS — the calibration truth side (API key).

swelter calibrates a low-cost node by regressing its raw readings onto a co-located reference-grade
monitor. That reference series used to be hand-built into a co-location file. This adapter pulls the
*reference* side directly: hourly regulatory PM2.5 from the US EPA AirNow program, which
redistributes AQS reference-monitor data. Overlapping timestamps then become co-location training
pairs automatically (see :mod:`swelter.colocate`, ``swelter colocate``, and ADR 0032).

What this is, honestly:

* This is the **reference truth**, not a swelter node. Its readings never enter the node observation
  store and are never shown as a swelter-calibrated sensor value. They exist only to be paired
  against a node's raw readings so a correction can be *fit*; the monitor's public AQS site id
  travels into ``Correction.reference`` as the provenance of that fit.
* Regulatory monitors are public record, so this carries no host- or person-shaped fields — only a
  public AQS site id, a UTC timestamp, and a concentration. Station and agency names in the upstream
  rows are ignored.

Auth: AirNow issues a free API key (request one at https://docs.airnowapi.org/). It is supplied at
runtime via ``--api-key`` or ``AIRNOW_API_KEY`` and is **never** written into the store, a public
artifact, or an error message — the fetch redacts the key from any failure text, because a key in a
URL is a credential (SECURITY.md).

Scope note: the tested, offline contract of this module is :func:`parse_series` — the pure mapping
from AirNow ``aq/data`` rows to :class:`ReferenceReading`. The live :func:`fetch` request wiring
(endpoint, query window, key handling) is an operator responsibility to confirm against current
AirNow documentation and is deliberately not exercised by the test suite.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from ..models import format_timestamp, parse_timestamp
from ._http import SourceError, get_json

#: Provenance label for this reference source. It is intentionally absent from
#: ``models.KNOWN_SOURCES``: a reference reading never becomes a stored node ``Observation``.
SOURCE = "airnow"

#: AirNow redistributes US federal reference-monitor data. US Government works are public domain
#: (17 U.S.C. §105); AirNow's data-exchange terms additionally require attribution and forbid
#: implying EPA endorsement. Those terms are retained here, not relabelled under swelter's CC0.
LICENSE = "US Government public-domain data (17 U.S.C. §105); AirNow attribution terms retained"
LICENSE_URL = "https://docs.airnowapi.org/"
ATTRIBUTION = (
    "Regulatory reference PM2.5 from the US EPA AirNow program (AQS reference monitors), used as "
    "co-location truth to fit swelter corrections — not a swelter sensor, not swelter-calibrated."
)

#: AirNow data API. This reference implementation targets its hourly-observation ``aq/data`` shape.
API = "https://www.airnowapi.org/aq/data/"

#: The swelter parameter this adapter provides and the AirNow parameter name it maps from.
PARAMETER = "pm25_ugm3"
UNIT = "ug/m3"
_AIRNOW_PM25 = "PM2.5"


@dataclass(frozen=True)
class ReferenceReading:
    """One reference-grade reading: the co-location truth a node's raw value is regressed onto.

    ``monitor_id`` is the public AQS site id (e.g. ``060670010``); it carries no host- or
    person-shaped information and travels into ``Correction.reference`` as fit provenance.
    """

    monitor_id: str
    parameter: str
    timestamp: str
    value: float
    unit: str = UNIT


def _redact(text: str, secret: str) -> str:
    """Blank an API key wherever it appears in a message, so a failure never leaks it."""
    return text.replace(secret, "***") if secret else text


def _get_json(url: str, api_key: str, *, timeout: float = 45.0, retries: int = 4) -> Any:
    """GET + parse JSON via the shared resilient fetch, redacting the key from any failure text.

    The key rides in the ``aq/data`` query string as AirNow requires; :mod:`swelter.sources._http`
    embeds the failing URL in its ``SourceError`` message, so this wrapper re-raises with the key
    blanked and drops the URL-bearing cause — the SECURITY.md rule against printing
    credential-bearing URLs."""
    try:
        return get_json(url, timeout=timeout, retries=retries)
    except SourceError as exc:
        raise SourceError(_redact(str(exc), api_key)) from None


def _airnow_hour(raw: str) -> str:
    """Normalize an AirNow UTC stamp to a canonical ISO-8601 ``...Z`` timestamp.

    AirNow emits hour-resolution UTC as ``YYYY-MM-DDTHH`` (no minutes); pad it before parsing so the
    reference reading lands on the exact hour a node sample is paired against.
    """
    text = raw.strip().rstrip("Z")
    if len(text) == 13 and text[10] == "T":  # "YYYY-MM-DDTHH" hour-only form
        text = f"{text}:00:00"
    return format_timestamp(parse_timestamp(text))


def parse_series(payload: Any, *, parameter: str = PARAMETER) -> list[ReferenceReading]:
    """Map AirNow ``aq/data`` rows to reference readings (pure — no network).

    Keeps only rows for the requested parameter (PM2.5), each carrying its public AQS site id
    (``FullAQSCode``). A row missing an id, timestamp, or finite value — or carrying AirNow's
    ``-999`` missing marker (any negative concentration) — is skipped rather than guessed at: a
    reference truth must be trustworthy or absent, and a sentinel paired into a fit would poison it.
    """
    rows = payload if isinstance(payload, list) else []
    out: list[ReferenceReading] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("Parameter", "")).strip().upper() != _AIRNOW_PM25:
            continue
        monitor_id = str(row.get("FullAQSCode", "")).strip()
        stamp = row.get("UTC")
        value = row.get("Value")
        if not monitor_id or not stamp or value is None:
            continue
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(numeric) or numeric < 0:
            continue
        out.append(
            ReferenceReading(
                monitor_id=monitor_id,
                parameter=parameter,
                timestamp=_airnow_hour(str(stamp)),
                value=round(numeric, 2),
            )
        )
    return out


def fetch(
    monitor_id: str,
    api_key: str,
    *,
    start: str,
    end: str,
    bbox: tuple[float, float, float, float],
    parameter: str = PARAMETER,
) -> list[ReferenceReading]:
    """Fetch the reference PM2.5 series for a monitoring site over ``[start, end]`` (live; keyed).

    Not exercised by the test suite (it would hit a live, keyed service); the tested contract is
    the pure :func:`parse_series` mapping. ``start``/``end`` are AirNow ``YYYY-MM-DDTHH`` UTC
    strings and ``bbox`` (west, south, east, north) narrows the query to the monitor's vicinity.
    The returned series is filtered to ``monitor_id`` so only that site's readings become pairs.
    """
    west, south, east, north = bbox
    url = (
        f"{API}?startDate={start}&endDate={end}&parameters=PM25"
        f"&BBOX={west},{south},{east},{north}"
        f"&dataType=C&format=application/json&verbose=1&monitorType=2&API_KEY={api_key}"
    )
    payload = _get_json(url, api_key)
    readings = parse_series(payload, parameter=parameter)
    return [r for r in readings if r.monitor_id == monitor_id]
