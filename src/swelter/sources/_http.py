"""Shared HTTP fetch + retry for the real-data source adapters (no third-party deps).

The three live sources (OpenAQ, Open-Meteo, Sensor.Community) all do the same fragile thing: a
GET over the public internet that has to survive a flaky connection, a rate-limit, or a momentarily
broken response without sinking the whole run and dropping the live demo to its synthetic fallback.
This module is that one resilient GET, so the adapters share one tested retry policy rather than
three drifting copies.

Policy, deliberately conservative for an untended daily refresh:

* a real timeout on every request (``timeout``);
* bounded retries with exponential backoff (``2**attempt`` capped at ``max_backoff_s``);
* HTTP 429 / 408 and 5xx are transient -> retried; a 429's ``Retry-After`` is honored (capped);
* other 4xx (404, 401, 403...) are caller errors -> raised immediately, no wasted retries;
* network errors (timeout, SSL drop, reset, truncated body) and malformed JSON are retried;
* on exhaustion a single :class:`SourceError` is raised carrying the last cause -- one clean,
  non-crashing failure type the caller can catch, instead of a grab-bag of OSError/ValueError.

Nothing here touches data semantics, the calibrated-vs-raw posture, or any hard rule: it only
governs *how* bytes are fetched, never what an observation means.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any

#: HTTP statuses worth retrying: rate-limit, request-timeout, and server-side faults.
_RETRYABLE_STATUS = frozenset({408, 429, 500, 502, 503, 504})

#: Hard cap on any single honored ``Retry-After`` so a hostile/large value cannot stall the run.
_MAX_RETRY_AFTER_S = 30.0


class SourceError(OSError):
    """A live source could not be fetched after retries (network, rate-limit, or bad response).

    Subclasses :class:`OSError` so any caller that already guards a fetch with ``except OSError``
    (as the CLI's fetch paths historically did) keeps catching it, while new code can name it
    explicitly for one clean message instead of a grab-bag of OSError/ValueError. The triggering
    exception is preserved as ``__cause__``.
    """


def _retry_after_seconds(exc: urllib.error.HTTPError, *, cap: float = _MAX_RETRY_AFTER_S) -> float:
    """Honor a 429/503 ``Retry-After`` header (delta-seconds form), capped; else 0."""
    raw = exc.headers.get("Retry-After") if exc.headers is not None else None
    if not raw:
        return 0.0
    try:
        return max(0.0, min(cap, float(raw)))
    except (TypeError, ValueError):
        return 0.0  # HTTP-date form is rare here; fall back to plain backoff


def get_json(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: float = 30.0,
    retries: int = 4,
    max_backoff_s: float = 8.0,
) -> Any:
    """GET ``url`` and parse JSON, retrying transient failures with exponential backoff.

    Retries timeouts, connection drops, malformed JSON, and retryable HTTP statuses (429/408/5xx),
    honoring a 429/503 ``Retry-After`` when present. Non-retryable HTTP errors (e.g. 404, 401) are
    raised immediately. On exhaustion (or an immediate non-retryable error) raises
    :class:`SourceError` with the underlying exception as ``__cause__``.
    """
    # `url` always comes from this module's own adapters (OpenAQ/Open-Meteo/Sensor.Community),
    # which build fixed https:// endpoints -- never an arbitrary caller-supplied scheme.
    request = urllib.request.Request(url, headers=headers or {})  # noqa: S310
    last: Exception | None = None
    attempts = max(1, retries)
    for attempt in range(attempts):
        wait = min(max_backoff_s, 2.0**attempt)
        try:
            # `url` is always a fixed https:// endpoint built by this module's own callers
            # (OpenAQ/Open-Meteo/Sensor.Community), never attacker-controlled -- same
            # justification as the `Request` construction above (S310).
            # nosemgrep: dynamic-urllib-use-detected
            with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            last = exc
            if exc.code not in _RETRYABLE_STATUS:
                raise SourceError(f"{url} returned HTTP {exc.code}") from exc
            wait = max(wait, _retry_after_seconds(exc))
        except (OSError, ValueError) as exc:
            # URLError, timeout, SSL/reset, truncated body, and bad JSON all land here.
            last = exc
        if attempt < attempts - 1:
            time.sleep(wait)
    raise SourceError(f"{url} failed after {attempts} attempts") from last
