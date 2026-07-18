"""Small, explicit localhost HTTP client for real-listener integration tests.

The production adapters deliberately use ``urllib`` for HTTPS sources. Tests that exercise a
server bound in-process should not need a broad ``urllib`` security waiver: this helper accepts
only loopback HTTP URLs and uses :mod:`http.client` directly.
"""

from __future__ import annotations

import http.client
from dataclasses import dataclass
from urllib.parse import urlsplit


@dataclass(frozen=True)
class LocalResponse:
    status: int
    headers: dict[str, str]
    body: bytes


def request_local(
    url: str,
    *,
    method: str = "GET",
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 5,
) -> LocalResponse:
    """Request an in-process loopback server and return its complete response."""
    parts = urlsplit(url)
    if parts.scheme != "http" or parts.hostname not in {"127.0.0.1", "localhost"}:
        raise ValueError(f"test HTTP client only accepts loopback HTTP URLs, got {url!r}")
    if parts.port is None:
        raise ValueError(f"test HTTP client requires an explicit port, got {url!r}")
    target = parts.path or "/"
    if parts.query:
        target = f"{target}?{parts.query}"
    connection = http.client.HTTPConnection(parts.hostname, parts.port, timeout=timeout)
    try:
        connection.request(method, target, body=body, headers=headers or {})
        response = connection.getresponse()
        response_body = response.read()
        return LocalResponse(
            status=response.status,
            headers={name: value for name, value in response.getheaders()},
            body=response_body,
        )
    finally:
        connection.close()
