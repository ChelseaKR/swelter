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

import http.client
import json
import time
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit

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


class _HTTPStatusError(OSError):
    """An upstream returned a non-success status, with headers retained for retry policy."""

    def __init__(self, code: int, headers: Mapping[str, str]) -> None:
        super().__init__(f"HTTP {code}")
        self.code = code
        self.headers = headers


def _retry_after_seconds(exc: _HTTPStatusError, *, cap: float = _MAX_RETRY_AFTER_S) -> float:
    """Honor a 429/503 ``Retry-After`` header (delta-seconds form), capped; else 0."""
    raw = exc.headers.get("Retry-After") if exc.headers is not None else None
    if not raw:
        return 0.0
    try:
        return max(0.0, min(cap, float(raw)))
    except (TypeError, ValueError):
        return 0.0  # HTTP-date form is rare here; fall back to plain backoff


def _request_json(url: str, headers: Mapping[str, str], timeout: float) -> Any:
    """Fetch one JSON document from an absolute HTTPS URL.

    Source adapters construct these URLs internally, but this boundary still validates the
    transport and host before opening a socket. Using ``http.client`` makes the HTTPS-only policy
    explicit instead of relying on a broad dynamic-URL waiver around ``urllib``.
    """
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
        raise ValueError(f"source URL must be absolute HTTPS without userinfo: {url!r}")
    target = parts.path or "/"
    if parts.query:
        target = f"{target}?{parts.query}"
    connection = http.client.HTTPSConnection(parts.hostname, parts.port, timeout=timeout)
    try:
        connection.request("GET", target, headers=dict(headers))
        response = connection.getresponse()
        body = response.read()
        response_headers = {name: value for name, value in response.getheaders()}
        if not 200 <= response.status < 300:
            raise _HTTPStatusError(response.status, response_headers)
        return json.loads(body.decode("utf-8"))
    finally:
        connection.close()


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
    last: Exception | None = None
    attempts = max(1, retries)
    for attempt in range(attempts):
        wait = min(max_backoff_s, 2.0**attempt)
        try:
            return _request_json(url, headers or {}, timeout)
        except _HTTPStatusError as exc:
            last = exc
            if exc.code not in _RETRYABLE_STATUS:
                raise SourceError(f"{url} returned HTTP {exc.code}") from exc
            wait = max(wait, _retry_after_seconds(exc))
        except (OSError, ValueError, http.client.HTTPException) as exc:
            # URLError, timeout, SSL/reset, truncated body, and bad JSON all land here.
            last = exc
        if attempt < attempts - 1:
            time.sleep(wait)
    raise SourceError(f"{url} failed after {attempts} attempts") from last
