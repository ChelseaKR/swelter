"""Tests for the authenticated ingest listener and per-node HMAC authentication."""

import json
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import yaml

from swelter import ingest_server
from swelter.models import parse_timestamp
from swelter.store import SqliteStore


@pytest.fixture
def keys_file(tmp_path: Path) -> Path:
    """Create a temporary keys file for testing."""
    return tmp_path / "node-keys.yaml"


@pytest.fixture
def store_path(tmp_path: Path) -> Path:
    """Create a temporary store path (database file path)."""
    return tmp_path / "observations.db"


@pytest.fixture
def store_dir(tmp_path: Path) -> Path:
    """Create a temporary store directory for quarantine files."""
    store_path = tmp_path / "store"
    store_path.mkdir(parents=True, exist_ok=True)
    return store_path


class TestKeyProvisioning:
    """Test key issuance, loading, and rotation."""

    def test_issue_key_creates_file(self, keys_file: Path) -> None:
        """Issuing a key creates the keys file if it doesn't exist."""
        assert not keys_file.exists()
        key = ingest_server.issue_key(keys_file, "node-1")
        assert keys_file.is_file()
        assert len(key) == 64  # 32 bytes as hex
        assert all(c in "0123456789abcdef" for c in key)

    def test_issue_key_file_permissions(self, keys_file: Path) -> None:
        """The keys file is created with owner-only permissions (0600)."""
        ingest_server.issue_key(keys_file, "node-1")
        mode = keys_file.stat().st_mode & 0o777
        assert mode == 0o600

    def test_issue_key_rotation(self, keys_file: Path) -> None:
        """Re-issuing a key for an existing node rotates (replaces) it."""
        key1 = ingest_server.issue_key(keys_file, "node-1")
        key2 = ingest_server.issue_key(keys_file, "node-1")
        assert key1 != key2
        keys = ingest_server.load_keys(keys_file)
        assert keys["node-1"].hex() == key2

    def test_issue_multiple_nodes(self, keys_file: Path) -> None:
        """Multiple nodes can have keys in the same file."""
        key1 = ingest_server.issue_key(keys_file, "node-1")
        key2 = ingest_server.issue_key(keys_file, "node-2")
        assert key1 != key2
        keys = ingest_server.load_keys(keys_file)
        assert len(keys) == 2
        assert keys["node-1"].hex() == key1
        assert keys["node-2"].hex() == key2

    def test_load_keys_nonexistent_file(self) -> None:
        """Loading a nonexistent keys file raises KeyfileError."""
        with pytest.raises(ingest_server.KeyfileError):
            ingest_server.load_keys("/nonexistent/path/keys.yaml")

    def test_load_keys_malformed_yaml(self, keys_file: Path) -> None:
        """Loading a malformed YAML file raises an error (KeyfileError or yaml.error)."""
        keys_file.write_text("{ invalid yaml }[")
        with pytest.raises((ingest_server.KeyfileError, yaml.YAMLError)):
            ingest_server.load_keys(keys_file)

    def test_load_keys_missing_keys_block(self, keys_file: Path) -> None:
        """Loading a YAML without 'keys:' block raises KeyfileError."""
        keys_file.write_text("not_keys:\n  node-1: abc123\n")
        with pytest.raises(ingest_server.KeyfileError):
            ingest_server.load_keys(keys_file)

    def test_load_keys_invalid_hex(self, keys_file: Path) -> None:
        """Loading a key with invalid hex raises KeyfileError."""
        keys_file.write_text("keys:\n  node-1: not_hex!!!\n")
        with pytest.raises(ingest_server.KeyfileError):
            ingest_server.load_keys(keys_file)

    def test_load_keys_key_too_short(self, keys_file: Path) -> None:
        """Loading a key shorter than MIN_KEY_BYTES raises KeyfileError."""
        keys_file.write_text("keys:\n  node-1: 0123456789\n")  # 5 bytes
        with pytest.raises(ingest_server.KeyfileError):
            ingest_server.load_keys(keys_file)

    def test_load_empty_keys_file(self, keys_file: Path) -> None:
        """Loading an empty or null YAML returns an empty dict."""
        keys_file.write_text("")
        assert ingest_server.load_keys(keys_file) == {}


class TestSigningAndVerification:
    """Test HMAC signing and verification."""

    def test_canonical_message(self) -> None:
        """The canonical message format is consistent."""
        node_id = "node-1"
        timestamp = "2026-07-01T12:00:00Z"
        body = b"test payload"
        msg = ingest_server.canonical_message(node_id, timestamp, body)
        # Should be node_id\ntimestamp\nsha256_hex(body)
        assert msg.startswith(b"node-1\n2026-07-01T12:00:00Z\n")
        # The digest part should be hex
        parts = msg.decode().split("\n")
        assert len(parts) == 3
        assert all(c in "0123456789abcdef" for c in parts[2])

    def test_sign_consistency(self) -> None:
        """Signing the same message twice produces the same signature."""
        key = bytes.fromhex("0123456789abcdef" * 4)  # 16 bytes
        node_id = "node-1"
        timestamp = "2026-07-01T12:00:00Z"
        body = b"test payload"
        sig1 = ingest_server.sign(key, node_id, timestamp, body)
        sig2 = ingest_server.sign(key, node_id, timestamp, body)
        assert sig1 == sig2

    def test_verify_valid_request(self) -> None:
        """A valid request passes verification."""
        key = bytes.fromhex("0123456789abcdef" * 4)
        node_id = "node-1"
        timestamp = "2026-07-01T12:00:00Z"
        body = b"test payload"
        signature = ingest_server.sign(key, node_id, timestamp, body)
        keys = {node_id: key}
        now = parse_timestamp(timestamp).timestamp()
        reason = ingest_server.verify_request(
            keys, node_id, timestamp, signature, body, now=now, skew_s=300
        )
        assert reason is None

    def test_verify_missing_headers(self) -> None:
        """Missing any authentication header causes verification to fail."""
        keys = {"node-1": bytes.fromhex("0123456789abcdef" * 4)}
        body = b"test"
        now = time.time()
        # Missing node_id
        reason = ingest_server.verify_request(
            keys, None, "2026-07-01T12:00:00Z", "sig", body, now=now
        )
        assert "missing" in reason.lower()

    def test_verify_unknown_node(self) -> None:
        """An unknown node is refused."""
        keys = {"node-1": bytes.fromhex("0123456789abcdef" * 4)}
        body = b"test"
        now = time.time()
        reason = ingest_server.verify_request(
            keys, "unknown-node", "2026-07-01T12:00:00Z", "sig", body, now=now
        )
        assert "unknown" in reason.lower()

    def test_verify_replay_too_old(self) -> None:
        """A signature timestamp outside the skew window is refused."""
        key = bytes.fromhex("0123456789abcdef" * 4)
        node_id = "node-1"
        timestamp = "2026-07-01T12:00:00Z"
        body = b"test"
        signature = ingest_server.sign(key, node_id, timestamp, body)
        keys = {node_id: key}
        # Claim it's 400 seconds later (outside 300s window)
        ts_base = parse_timestamp(timestamp).timestamp()
        now = ts_base + 400.0
        reason = ingest_server.verify_request(
            keys, node_id, timestamp, signature, body, now=now, skew_s=300
        )
        assert "replay window" in reason.lower()

    def test_verify_replay_too_new(self) -> None:
        """A signature timestamp in the future outside the skew window is refused."""
        key = bytes.fromhex("0123456789abcdef" * 4)
        node_id = "node-1"
        timestamp = "2026-07-01T13:00:00Z"
        body = b"test"
        signature = ingest_server.sign(key, node_id, timestamp, body)
        keys = {node_id: key}
        # Claim it's 400 seconds earlier (outside 300s window)
        ts_base = parse_timestamp("2026-07-01T12:00:00Z").timestamp()
        now = ts_base
        reason = ingest_server.verify_request(
            keys, node_id, timestamp, signature, body, now=now, skew_s=300
        )
        assert "replay window" in reason.lower()

    def test_verify_signature_mismatch(self) -> None:
        """A mismatched signature is refused."""
        key = bytes.fromhex("0123456789abcdef" * 4)
        node_id = "node-1"
        timestamp = "2026-07-01T12:00:00Z"
        body = b"test"
        bad_signature = "0" * 64
        keys = {node_id: key}
        now = parse_timestamp(timestamp).timestamp()
        reason = ingest_server.verify_request(
            keys, node_id, timestamp, bad_signature, body, now=now, skew_s=300
        )
        assert "signature mismatch" in reason.lower()

    def test_verify_altered_body(self) -> None:
        """Altering the body after signing causes verification to fail."""
        key = bytes.fromhex("0123456789abcdef" * 4)
        node_id = "node-1"
        timestamp = "2026-07-01T12:00:00Z"
        body = b"original payload"
        signature = ingest_server.sign(key, node_id, timestamp, body)
        keys = {node_id: key}
        now = parse_timestamp(timestamp).timestamp()
        # Try to verify with altered body
        reason = ingest_server.verify_request(
            keys, node_id, timestamp, signature, b"altered payload", now=now, skew_s=300
        )
        assert "signature mismatch" in reason.lower()


class TestFirmwareSigningCompat:
    """Test that firmware signing (from firmware/src/signing.py) matches server signing."""

    def test_firmware_signing_module_compatibility(self) -> None:
        """The firmware signing.py produces signatures identical to ingest_server.sign."""
        # Import the firmware signing module
        import sys
        from pathlib import Path

        firmware_path = Path(__file__).parent.parent / "firmware" / "src"
        sys.path.insert(0, str(firmware_path))
        try:
            import signing as fw_signing

            # Test data
            key_hex = "0123456789abcdef" * 4
            node_id = "node-1"
            timestamp = "2026-07-01T12:00:00Z"
            body = b'{"readings":{"pm25_ugm3":23.5}}'

            # Get signatures from both sides
            fw_sig = fw_signing.sign(key_hex, node_id, timestamp, body)
            key_bytes = bytes.fromhex(key_hex)
            server_sig = ingest_server.sign(key_bytes, node_id, timestamp, body)

            assert fw_sig == server_sig
        finally:
            sys.path.pop(0)

    def test_firmware_headers_generation(self) -> None:
        """The firmware headers() function generates correct auth headers."""
        import sys
        from pathlib import Path

        firmware_path = Path(__file__).parent.parent / "firmware" / "src"
        sys.path.insert(0, str(firmware_path))
        try:
            import signing as fw_signing

            key_hex = "0123456789abcdef" * 4
            node_id = "node-1"
            body = b'{"readings":{"pm25_ugm3":23.5}}'

            # Generate headers with a fixed timestamp
            fixed_ts = "2026-07-01T12:00:00Z"
            headers = fw_signing.headers(key_hex, node_id, body, timestamp=fixed_ts)

            # Verify structure
            assert fw_signing.NODE_HEADER in headers
            assert fw_signing.TIMESTAMP_HEADER in headers
            assert fw_signing.SIGNATURE_HEADER in headers
            assert headers[fw_signing.NODE_HEADER] == node_id
            assert headers[fw_signing.TIMESTAMP_HEADER] == fixed_ts

            # Verify signature is valid
            key_bytes = bytes.fromhex(key_hex)
            server_sig = ingest_server.sign(key_bytes, node_id, fixed_ts, body)
            assert headers[fw_signing.SIGNATURE_HEADER] == server_sig
        finally:
            sys.path.pop(0)


class TestIngestServerConstruction:
    """Object-construction sanity checks — no socket involved.

    Real network-facing coverage (a live listener, actual HTTP requests) lives in
    :class:`TestIngestServerHandlerIntegration` below.
    """

    def test_ingest_server_context_creation(
        self, store_path: Path, store_dir: Path, keys_file: Path
    ) -> None:
        """Create an IngestServerContext."""
        store = SqliteStore(store_path)
        try:
            ingest_server.issue_key(keys_file, "node-1")
            keys = ingest_server.load_keys(keys_file)
            ctx = ingest_server.IngestServerContext(
                store=store,
                keys=keys,
                quarantine_path=store_dir / "quarantine.jsonl",
                skew_s=300,
            )
            assert ctx.store is store
            assert "node-1" in ctx.keys
            assert len(ctx.keys["node-1"]) == 32  # 256-bit key
        finally:
            store.close()

    def test_make_server(self, store_path: Path, store_dir: Path, keys_file: Path) -> None:
        """Create an ingest server."""
        store = SqliteStore(store_path)
        try:
            ingest_server.issue_key(keys_file, "node-1")
            keys = ingest_server.load_keys(keys_file)
            ctx = ingest_server.IngestServerContext(
                store=store,
                keys=keys,
                quarantine_path=store_dir / "quarantine.jsonl",
            )
            server = ingest_server.make_server(ctx, "127.0.0.1", 0)
            assert server is not None
            server.server_close()
        finally:
            store.close()


# -- real listener, real HTTP requests --------------------------------------------------------
#
# Everything above (and TestSigningAndVerification) exercises verify_request() directly — the
# pure crypto function. That is necessary but not sufficient: it never proves the *handler*
# (src/swelter/ingest_server.py's `_post()`) does the right thing with a real socket, real
# headers, and a real response code. The fixture below starts the actual server returned by
# `make_server()` on a background thread and every test in this section talks to it over
# real HTTP, exactly as a node (or an operator's curl backfill) would.

#: A fixed signing instant so tests are deterministic regardless of wall-clock time — the
#: fixture below wires this in as `IngestServerContext.now`, which is the injectable clock the
#: module docstring calls out as "so the replay window is testable".
FIXED_TIMESTAMP = "2026-07-01T12:00:00Z"
FIXED_NOW = parse_timestamp(FIXED_TIMESTAMP).timestamp()


def _post(url: str, body: bytes, headers: dict[str, str]) -> tuple[int, dict[str, Any]]:
    """POST over a real socket and return (status, parsed-JSON-body) whether it's a 2xx or not."""
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=5) as response:  # noqa: S310 (localhost)
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def _quarantine_records(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


@pytest.fixture
def running_server(store_path: Path, store_dir: Path, keys_file: Path):  # type: ignore[no-untyped-def]
    """A real ingest listener, bound to 127.0.0.1 on an OS-assigned port, on a daemon thread.

    Two nodes (``node-1``, ``node-2``) are pre-provisioned so impersonation-style tests have a
    second real, registered node to claim.
    """
    store = SqliteStore(store_path)
    quarantine_path = store_dir / "quarantine.jsonl"
    ingest_server.issue_key(keys_file, "node-1")
    ingest_server.issue_key(keys_file, "node-2")
    keys = ingest_server.load_keys(keys_file)  # {node_id: key_bytes} — what `sign()` needs
    ctx = ingest_server.IngestServerContext(
        store=store,
        keys=keys,
        quarantine_path=quarantine_path,
        skew_s=300,
        now=lambda: FIXED_NOW,  # deterministic: matches FIXED_TIMESTAMP above
    )
    httpd = ingest_server.make_server(ctx, "127.0.0.1", 0)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield SimpleNamespace(
            url=f"http://127.0.0.1:{port}{ingest_server.INGEST_ROUTE}",
            store=store,
            quarantine_path=quarantine_path,
            keys=keys,
        )
    finally:
        httpd.shutdown()
        httpd.server_close()
        store.close()


class TestIngestServerHandlerIntegration:
    """Real HTTP requests against a real running listener — the coverage gap this closes.

    Each test drives ``do_POST`` / ``_post()`` end to end over a socket, not `verify_request()`
    in isolation, and checks the observable side effects (store rows, quarantine.jsonl) that a
    unit-level call to `verify_request()` can never confirm.
    """

    def test_valid_signature_is_written_and_returns_200(
        self, running_server: SimpleNamespace
    ) -> None:
        node_id = "node-1"
        body = json.dumps(
            {
                "node_id": node_id,
                "timestamp": "2026-07-01T11:55:00Z",
                "readings": {"pm25_ugm3": 23.5},
            }
        ).encode()
        signature = ingest_server.sign(running_server.keys[node_id], node_id, FIXED_TIMESTAMP, body)

        status, payload = _post(
            running_server.url,
            body,
            {
                ingest_server.NODE_HEADER: node_id,
                ingest_server.TIMESTAMP_HEADER: FIXED_TIMESTAMP,
                ingest_server.SIGNATURE_HEADER: signature,
                "Content-Type": "application/json",
            },
        )

        assert status == 200
        assert payload["status"] == "ok"
        assert payload["written"] == 1

        # The row actually landed in the store — queried back over the real Store API, not
        # inferred from the response body.
        rows = running_server.store.read(node_id=node_id, parameter="pm25_ugm3")
        assert len(rows) == 1
        assert rows[0].value == 23.5
        assert running_server.quarantine_path.is_file() is False  # nothing refused, nothing logged

    def test_missing_signature_headers_returns_401_and_quarantines(
        self, running_server: SimpleNamespace
    ) -> None:
        node_id = "node-1"
        body = json.dumps(
            {
                "node_id": node_id,
                "timestamp": "2026-07-01T11:55:00Z",
                "readings": {"pm25_ugm3": 9.0},
            }
        ).encode()

        # No X-Swelter-Timestamp / X-Swelter-Signature headers at all.
        status, payload = _post(
            running_server.url,
            body,
            {ingest_server.NODE_HEADER: node_id, "Content-Type": "application/json"},
        )

        assert status == 401
        assert "missing" in payload["error"].lower()
        assert running_server.store.count() == 0  # never written

        records = _quarantine_records(running_server.quarantine_path)
        assert records, "a refused request must leave evidence in quarantine.jsonl"
        assert records[-1]["reason"].startswith("auth: missing")
        assert records[-1]["node_id"] == node_id

    def test_bad_signature_returns_401_and_quarantines(
        self, running_server: SimpleNamespace
    ) -> None:
        node_id = "node-1"
        body = json.dumps(
            {
                "node_id": node_id,
                "timestamp": "2026-07-01T11:55:00Z",
                "readings": {"pm25_ugm3": 9.0},
            }
        ).encode()

        status, payload = _post(
            running_server.url,
            body,
            {
                ingest_server.NODE_HEADER: node_id,
                ingest_server.TIMESTAMP_HEADER: FIXED_TIMESTAMP,
                ingest_server.SIGNATURE_HEADER: "0" * 64,  # well-formed hex, wrong signature
                "Content-Type": "application/json",
            },
        )

        assert status == 401
        assert "signature mismatch" in payload["error"].lower()
        assert running_server.store.count() == 0

        records = _quarantine_records(running_server.quarantine_path)
        assert records[-1]["reason"] == "auth: signature mismatch"
        assert records[-1]["node_id"] == node_id

    def test_impersonation_rejected_by_the_handlers_impersonation_branch(
        self, running_server: SimpleNamespace
    ) -> None:
        """node-1 signs correctly (crypto passes) but the payload claims to be node-2.

        This is the scenario the docstring of the old (removed) `test_impersonation_detected`
        claimed to cover but never did — that test only re-confirmed `verify_request()` accepts
        a validly-signed request. `verify_request()` doesn't even see the payload body's
        node_id; the impersonation check is a handler-level guard in `_post()` (the
        `claimed != node` block) applied *after* auth passes. This test drives that branch for
        real, over the real listener.
        """
        node_id = "node-1"
        body = json.dumps(
            {
                "node_id": "node-2",  # impersonation: signed by node-1, claims to be node-2
                "timestamp": "2026-07-01T11:55:00Z",
                "readings": {"pm25_ugm3": 9.0},
            }
        ).encode()
        signature = ingest_server.sign(running_server.keys[node_id], node_id, FIXED_TIMESTAMP, body)

        status, payload = _post(
            running_server.url,
            body,
            {
                ingest_server.NODE_HEADER: node_id,  # authenticated as node-1
                ingest_server.TIMESTAMP_HEADER: FIXED_TIMESTAMP,
                ingest_server.SIGNATURE_HEADER: signature,  # a genuinely valid node-1 signature
                "Content-Type": "application/json",
            },
        )

        assert status == 401
        assert "does not match authenticated" in payload["error"]
        assert (
            running_server.store.count() == 0
        )  # the impersonated row never lands, for either node

        records = _quarantine_records(running_server.quarantine_path)
        assert "payload node_id" in records[-1]["reason"]
        assert records[-1]["node_id"] == node_id

    def test_unknown_node_well_formed_signature_returns_401(
        self, running_server: SimpleNamespace
    ) -> None:
        """A node id that is not registered at all — refused before any crypto compare runs."""
        node_id = "ghost-node"
        body = json.dumps(
            {
                "node_id": node_id,
                "timestamp": "2026-07-01T11:55:00Z",
                "readings": {"pm25_ugm3": 9.0},
            }
        ).encode()
        # A well-formed HMAC, just computed with a key nobody registered — proves the "unknown
        # node" refusal isn't just a signature-mismatch in disguise.
        bogus_key = bytes(32)
        signature = ingest_server.sign(bogus_key, node_id, FIXED_TIMESTAMP, body)

        status, payload = _post(
            running_server.url,
            body,
            {
                ingest_server.NODE_HEADER: node_id,
                ingest_server.TIMESTAMP_HEADER: FIXED_TIMESTAMP,
                ingest_server.SIGNATURE_HEADER: signature,
                "Content-Type": "application/json",
            },
        )

        assert status == 401
        assert "unknown node" in payload["error"].lower()
        assert running_server.store.count() == 0

        records = _quarantine_records(running_server.quarantine_path)
        assert "unknown node" in records[-1]["reason"]
