"""The authenticated node write path: an operator-side ingest listener with per-node HMAC.

This is deliberately a **separate process** from :mod:`swelter.server`. The public read server
stays GET-only with no write path to expose; this listener is write-only and lives on the
operator's side of the trust boundary (bind it to localhost or a private interface, never merge
it into the public server). ``swelter ingest-serve`` runs it; ``swelter node-key`` issues keys.

Authentication is a per-node HMAC-SHA256 over ``(node_id, timestamp, body)``:

* the node sends three headers — ``X-Swelter-Node`` (its host-assigned node id, the only
  identifier in the system), ``X-Swelter-Timestamp`` (the ISO-8601 UTC *signing* time, not the
  observation time), and ``X-Swelter-Signature`` (lowercase hex HMAC of the canonical message
  ``node_id + "\\n" + timestamp + "\\n" + sha256_hex(body)``);
* keys live in an operator-local YAML file **outside** ``network.yaml`` and outside the copyable
  store folder, because the published config and the portable archive must never carry a secret;
* a request that fails authentication is refused with ``401`` and the failure lands in
  ``quarantine.jsonl`` with an ``auth:`` reason, so spoofing attempts are evidence, not noise.

Replay protection is the signed timestamp plus the store's idempotency: a request signed outside
the ``skew_s`` window is refused outright, and within the window a replayed request can only
re-insert the identical rows the first delivery wrote (``INSERT OR IGNORE`` on the observation
key), so a captured request never lets an attacker alter or extend the record. Backfill after an
outage still works because nodes sign at *send* time — old readings travel under fresh signatures.

The payload body is the existing wide format :func:`swelter.ingest.explode` already accepts
(flat or ``{"readings": {...}}`` envelope), one JSON object per POST or a JSON array of them,
so the firmware forwarder and an operator's ``curl`` backfill share one door. An authenticated
payload that is malformed is quarantined by the normal ingest path — auth decides *who* may
write, ingest still decides *what* enters the record.
"""

from __future__ import annotations

import contextlib
import hashlib
import hmac
import json
import os
import secrets
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

from . import ingest
from .models import parse_timestamp
from .store import Store

#: Request headers carrying the authentication triple.
NODE_HEADER = "X-Swelter-Node"
TIMESTAMP_HEADER = "X-Swelter-Timestamp"
SIGNATURE_HEADER = "X-Swelter-Signature"

#: The one write route. Matches the firmware's default ``ingest_url`` path.
INGEST_ROUTE = "/v1/observations"

#: Replay window: a signature timestamp further than this from server time is refused.
DEFAULT_SKEW_S = 300.0

#: Cap on the request body — a season of 5-minute wide payloads is a few hundred bytes each,
#: so anything near this size is not a sensor reading.
MAX_BODY_BYTES = 256 * 1024

#: Issued key size (bytes of entropy; stored as hex). 256-bit keys for HMAC-SHA256.
KEY_BYTES = 32

#: Refuse keys shorter than this many bytes when loading — a truncated key is a typo, not a key.
MIN_KEY_BYTES = 16

_KEYFILE_HEADER = """\
# swelter node ingest keys — OPERATOR-LOCAL SECRET. Issued by `swelter node-key`.
# Never commit this file, never add keys to network.yaml, and keep it outside the
# copyable store folder: the published config and the portable archive carry no secrets.
# Key ids are node ids — the only identifier in the system (no person-bearing field).
"""


class KeyfileError(ValueError):
    """The node-keys file is missing, malformed, or holds an unusable key."""


# -- key provisioning and storage (operator-local, outside network.yaml) -------------------------


def load_keys(path: str | Path) -> dict[str, bytes]:
    """Read the operator-local node-keys file into ``{node_id: key_bytes}``.

    Strict on purpose: a malformed keys file is a loud error, never a silently empty key set
    that would refuse every node at 2 a.m. with no explanation.
    """
    target = Path(path)
    try:
        raw = target.read_text(encoding="utf-8")
    except OSError as exc:
        raise KeyfileError(f"cannot read keys file {target}: {exc}") from exc
    doc = yaml.safe_load(raw)
    if doc is None:
        return {}
    if not isinstance(doc, dict) or not isinstance(doc.get("keys"), dict):
        raise KeyfileError(f"keys file {target} must be a mapping with a top-level 'keys:' block")
    keys: dict[str, bytes] = {}
    for node_id, value in doc["keys"].items():
        if not isinstance(node_id, str) or not node_id:
            raise KeyfileError(f"keys file {target}: node id must be a non-empty string")
        if not isinstance(value, str):
            raise KeyfileError(f"keys file {target}: key for {node_id} must be a hex string")
        try:
            key = bytes.fromhex(value)
        except ValueError as exc:
            raise KeyfileError(f"keys file {target}: key for {node_id} is not valid hex") from exc
        if len(key) < MIN_KEY_BYTES:
            raise KeyfileError(
                f"keys file {target}: key for {node_id} is shorter than "
                f"{MIN_KEY_BYTES} bytes — issue a fresh one with `swelter node-key`"
            )
        keys[node_id] = key
    return keys


def issue_key(path: str | Path, node_id: str) -> str:
    """Issue (or rotate) the ingest key for one node and persist the keys file.

    Re-issuing for an existing node id **replaces** the key — that is the rotation path; the old
    key stops working the next time the listener loads the file. The file is written owner-only
    (``0600``) because it is the credential that guards the write path. Returns the new key as
    hex for the operator to copy into the node's uncommitted ``config.py``.
    """
    if not node_id or not isinstance(node_id, str):
        raise KeyfileError("node_id must be a non-empty string")
    target = Path(path)
    keys_hex: dict[str, str] = {}
    if target.is_file():
        keys_hex = {node: key.hex() for node, key in load_keys(target).items()}
    new_key = secrets.token_hex(KEY_BYTES)
    keys_hex[node_id] = new_key
    target.parent.mkdir(parents=True, exist_ok=True)
    body = yaml.safe_dump({"keys": dict(sorted(keys_hex.items()))}, sort_keys=False)
    target.write_text(_KEYFILE_HEADER + body, encoding="utf-8")
    os.chmod(target, 0o600)
    return new_key


# -- signing and verification ---------------------------------------------------------------------


def canonical_message(node_id: str, timestamp: str, body: bytes) -> bytes:
    """The exact bytes both sides sign: ``node_id \\n timestamp \\n sha256_hex(body)``.

    Hashing the body keeps the signed string small and unambiguous (no delimiter can occur
    inside a hex digest); the firmware's ``signing.py`` builds the identical message.
    """
    digest = hashlib.sha256(body).hexdigest()
    return f"{node_id}\n{timestamp}\n{digest}".encode()


def sign(key: bytes, node_id: str, timestamp: str, body: bytes) -> str:
    """HMAC-SHA256 signature (lowercase hex) for one ingest request."""
    return hmac.new(key, canonical_message(node_id, timestamp, body), hashlib.sha256).hexdigest()


def verify_request(
    keys: Mapping[str, bytes],
    node_id: str | None,
    timestamp: str | None,
    signature: str | None,
    body: bytes,
    *,
    now: float,
    skew_s: float = DEFAULT_SKEW_S,
) -> str | None:
    """Check one request's authentication triple. Returns a refusal reason, or ``None`` if valid.

    Order matters for what the reason reveals: an unknown node is named before any crypto runs
    (the node id is public — it is in ``network.yaml``), the timestamp window is enforced before
    the signature so a replayed capture is refused cheaply, and signature comparison is
    constant-time (:func:`hmac.compare_digest`).
    """
    if not node_id or not timestamp or not signature:
        return "missing authentication headers"
    key = keys.get(node_id)
    if key is None:
        return f"unknown node {node_id!r}"
    try:
        signed_at = parse_timestamp(timestamp).timestamp()
    except (ValueError, TypeError):
        return "unparseable signature timestamp"
    if abs(now - signed_at) > skew_s:
        return "signature timestamp outside the replay window"
    expected = sign(key, node_id, timestamp, body)
    if not hmac.compare_digest(expected, signature.strip().lower()):
        return "signature mismatch"
    return None


# -- the listener -----------------------------------------------------------------------------------


@dataclass
class IngestServerContext:
    """Everything a write request needs: the store, the node keys, and where refusals land."""

    store: Store
    keys: Mapping[str, bytes]
    quarantine_path: Path | None = None
    skew_s: float = DEFAULT_SKEW_S
    max_body_bytes: int = MAX_BODY_BYTES
    now: Callable[[], float] = time.time  # injectable clock so the replay window is testable


def _make_handler(ctx: IngestServerContext) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "swelter-ingest/0.1"
        timeout = 30.0  # one stalled writer must not hold the listener forever

        def log_message(self, *_: object) -> None:  # refusals go to quarantine, not stdout
            return

        def do_GET(self) -> None:  # noqa: N802 (http.server API)
            # Liveness only. Everything readable lives on the public read server; keeping this
            # surface write-only is the trust boundary, not a missing feature.
            path = urlparse(self.path).path.rstrip("/") or "/"
            if path in ("/health", "/healthz"):
                self._json(200, {"status": "ok", "nodes": len(ctx.keys)})
            else:
                self._error(405, "the ingest listener is write-only; read via `swelter serve`")

        def do_POST(self) -> None:  # noqa: N802
            try:
                self._post()
            except BrokenPipeError:  # client went away mid-response
                return
            except Exception:  # never drop the connection with no response
                self._error(500, "internal error")

        do_PUT = do_DELETE = do_PATCH = do_POST

        # -- the one write route -------------------------------------------------

        def _post(self) -> None:
            path = urlparse(self.path).path.rstrip("/") or "/"
            if path != INGEST_ROUTE:
                self._error(404, "not found")
                return
            if self.command != "POST":
                self._error(405, f"use POST {INGEST_ROUTE}")
                return
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = -1
            if length <= 0:
                self._error(411, "a JSON body with Content-Length is required")
                return
            if length > ctx.max_body_bytes:
                self._error(413, f"body exceeds {ctx.max_body_bytes} bytes")
                return
            body = self.rfile.read(length)
            node = self.headers.get(NODE_HEADER)

            reason = verify_request(
                ctx.keys,
                node,
                self.headers.get(TIMESTAMP_HEADER),
                self.headers.get(SIGNATURE_HEADER),
                body,
                now=ctx.now(),
                skew_s=ctx.skew_s,
            )
            if reason is not None:
                self._refuse(401, f"auth: {reason}", node, body)
                return

            try:
                parsed: Any = json.loads(body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                self._refuse(400, "unparseable JSON body from authenticated node", node, body)
                return

            payloads = parsed if isinstance(parsed, list) else [parsed]
            batch: list[dict[str, Any]] = []
            for item in payloads:
                if not isinstance(item, dict):
                    batch.append(
                        {
                            "__parse_error__": "payload is not a JSON object",
                            "__raw__": json.dumps(item),
                        }
                    )
                    continue
                claimed = ingest._first(item, ingest._NODE_KEYS)
                if claimed is not None and claimed != node:
                    # A valid key only ever writes as its own node. Refuse the whole request:
                    # a batch that impersonates another node is suspect end to end.
                    self._refuse(
                        401,
                        f"auth: payload node_id {claimed!r} does not match authenticated "
                        f"node {node!r}",
                        node,
                        body,
                    )
                    return
                batch.append(item)

            result = ingest.ingest(batch, ctx.store, quarantine_path=ctx.quarantine_path)
            self._json(
                200,
                {
                    "status": "ok",
                    "node": node,
                    "accepted_payloads": result.accepted_payloads,
                    "written": result.observations_written,
                    "duplicates": result.duplicates,
                    "quarantined": result.quarantined,
                },
            )

        # -- helpers ---------------------------------------------------------------

        def _refuse(self, code: int, reason: str, node: str | None, body: bytes) -> None:
            """Refuse a request and leave the evidence in quarantine.jsonl.

            Auth failures are the spoofing attempts the security audit cares about, so they are
            recorded with the same mechanism as malformed payloads — a reason and the (bounded)
            offending bytes — never silently dropped.
            """
            if ctx.quarantine_path is not None:
                record = {
                    "reason": reason,
                    "node_id": node,
                    "payload": body[:2048].decode("utf-8", "replace"),
                }
                ingest._append_jsonl(ctx.quarantine_path, [record])
            self._error(code, reason)

        def _error(self, code: int, message: str) -> None:
            with contextlib.suppress(Exception):  # headers may already be on the wire
                self._json(code, {"error": message, "status": code})

        def _json(self, code: int, payload: object) -> None:
            data = json.dumps(payload).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")  # a write path is never cacheable
            self.end_headers()
            self.wfile.write(data)

    return Handler


def make_server(ctx: IngestServerContext, host: str, port: int) -> HTTPServer:
    """Build (but do not start) the ingest listener.

    Single-threaded like the read server (one SQLite writer, serialised requests), and expected
    to bind localhost or a private interface — the public internet talks to ``swelter serve``,
    nodes talk to this.
    """
    return HTTPServer((host, port), _make_handler(ctx))


def serve(ctx: IngestServerContext, host: str = "127.0.0.1", port: int = 8100) -> None:
    """Run the ingest listener until interrupted."""
    httpd = make_server(ctx, host, port)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
