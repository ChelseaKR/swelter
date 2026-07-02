"""Per-node request signing for the node -> ingest write path.

The operator-side listener (``swelter ingest-serve``) authenticates every POST with an
HMAC-SHA256 over ``(node_id, timestamp, body)`` under a per-node key issued by
``swelter node-key``. This module produces the matching three headers on the node.

MicroPython does not ship an ``hmac`` module, so HMAC is implemented here from the SHA-256
primitive per RFC 2104 — ``hashlib.sha256`` exists on both runtimes, so the same file runs on
the board and on desktop CPython for review and tests (the server-side test suite asserts this
implementation and ``swelter.ingest_server.sign`` produce identical signatures).

Two properties worth naming:

* The signed timestamp is the **signing** time, not the observation time. A node backfilling
  its store-and-forward buffer after an outage therefore signs old readings with a fresh
  timestamp and they pass the listener's replay window; the observations themselves keep their
  original timestamps.
* The key is a secret the collective issued for this node. It lives only in the node's
  uncommitted ``config.py`` (as ``ingest_key``) and the operator's local keys file — never in
  ``network.yaml``, never in the repo. The node id stays the only identifier that leaves the node.
"""

try:
    import hashlib
except ImportError:  # pragma: no cover - MicroPython name
    import uhashlib as hashlib

try:
    import binascii
except ImportError:  # pragma: no cover - MicroPython name
    import ubinascii as binascii

# The authentication headers the listener expects (mirrors swelter.ingest_server).
NODE_HEADER = "X-Swelter-Node"
TIMESTAMP_HEADER = "X-Swelter-Timestamp"
SIGNATURE_HEADER = "X-Swelter-Signature"

_BLOCK_SIZE = 64  # SHA-256 block size in bytes (the RFC 2104 HMAC block)


def _sha256(data):
    return hashlib.sha256(data).digest()


def _hex(data):
    return binascii.hexlify(data).decode()


def hmac_sha256_hex(key, message):
    """RFC 2104 HMAC-SHA256 of ``message`` under ``key`` (both bytes), as lowercase hex."""
    if len(key) > _BLOCK_SIZE:
        key = _sha256(key)
    key = key + b"\x00" * (_BLOCK_SIZE - len(key))
    inner = bytes(b ^ 0x36 for b in key)
    outer = bytes(b ^ 0x5C for b in key)
    return _hex(_sha256(outer + _sha256(inner + message)))


def sign(key_hex, node_id, timestamp, body):
    """Signature for one ingest request; ``body`` is the exact str/bytes that will be POSTed.

    The canonical message is ``node_id + "\\n" + timestamp + "\\n" + sha256_hex(body)`` — the
    body travels as its digest so the signed string is small and delimiter-safe.
    """
    if isinstance(body, str):
        body = body.encode("utf-8")
    digest = _hex(_sha256(body))
    message = ("%s\n%s\n%s" % (node_id, timestamp, digest)).encode("utf-8")
    return hmac_sha256_hex(binascii.unhexlify(key_hex), message)


def headers(key_hex, node_id, body, timestamp=None):
    """The three authentication headers for one POST of ``body``.

    ``timestamp`` defaults to the current UTC clock — correct on the node once ``sync_clock()``
    has disciplined the RTC; injectable for tests.
    """
    ts = timestamp if timestamp is not None else utc_timestamp()
    return {
        NODE_HEADER: node_id,
        TIMESTAMP_HEADER: ts,
        SIGNATURE_HEADER: sign(key_hex, node_id, ts, body),
    }


def utc_timestamp(now=None):
    """The current UTC instant as canonical ISO-8601 ``YYYY-MM-DDTHH:MM:SSZ``."""
    import time

    parts = time.gmtime(now) if now is not None else time.gmtime()
    return "%04d-%02d-%02dT%02d:%02d:%02dZ" % (
        parts[0],
        parts[1],
        parts[2],
        parts[3],
        parts[4],
        parts[5],
    )
