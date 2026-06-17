"""Flash-backed store-and-forward buffer: never lose a reading to a dropped connection.

Every sample is appended to a buffer on flash *before* the node tries to send it. A node that
loses connectivity keeps sampling and keeps appending; when it reconnects, :meth:`flush` walks the
buffer oldest-first and forwards each payload, dropping it from the buffer only once the transport
confirms the send. An outage therefore becomes a backfilled gap, not a hole in the record.

Idempotency is the load-bearing property. Each payload carries ``node_id``, ``timestamp``, and its
parameter values; the ingest store key is ``(node_id, timestamp, parameter, calibration)`` with an
``INSERT OR IGNORE`` write, so re-sending a payload the server already stored is a no-op. That means
a flush interrupted mid-batch can safely re-send the whole batch on the next attempt without
duplicating — the firmware never has to track exactly-once delivery itself.

The buffer is a JSON-lines file: one payload per line, appended at the tail, consumed from the head.
On flash that survives reboots, so a node that resets mid-outage still has its backlog. Persistence
is deferred and guarded so this module imports and runs on desktop CPython for review and tests.
"""

from __future__ import annotations

try:  # MicroPython and CPython both provide json; import at module load is safe on both.
    import json
except Exception:  # pragma: no cover - json is always present
    json = None  # type: ignore[assignment]


class TransportError(Exception):
    """A forward attempt failed (no connectivity, endpoint error). The payload stays buffered."""


class StoreAndForward:
    """Append readings to flash and flush them to a transport on reconnect.

    Parameters
    ----------
    path:
        Buffer file path on flash, e.g. ``"buffer.jsonl"``.
    transport:
        An object with ``send(payload) -> None`` that raises :class:`TransportError` when it cannot
        deliver. The MQTT and HTTP forwarders in ``main.py`` implement this.
    max_records:
        Cap on buffered payloads. When the buffer is full the **oldest** record is dropped to make
        room, so the node keeps the most recent readings during a long outage rather than refusing
        to sample. A dropped record is gone; sizing this for the worst expected outage is a build
        decision documented in the assembly guide.
    """

    def __init__(self, path, transport=None, max_records=20000):
        self.path = path
        self.transport = transport
        self.max_records = int(max_records)
        # Cached buffer size so append() can early-out without rereading the whole file each
        # time. One scan at startup, then kept in sync on append / flush / trim.
        self._count = self.pending()

    # -- buffering -----------------------------------------------------------------------------

    def append(self, payload):
        """Persist one wide payload to the tail of the buffer before any send is attempted."""
        if payload is None:
            return
        self._enforce_cap()
        line = json.dumps(payload)
        with self._open(self.path, "a") as handle:
            handle.write(line + "\n")
        self._count += 1

    def pending(self):
        """Number of payloads currently buffered."""
        return sum(1 for _ in self._read_lines())

    # -- flushing ------------------------------------------------------------------------------

    def flush(self, limit=None):
        """Forward buffered payloads oldest-first; keep only those not yet confirmed sent.

        Walks the buffer from the head. Each payload is sent through the transport; a payload the
        transport confirms is dropped, a payload that raises :class:`TransportError` is kept along
        with everything after it (preserving order), and flushing stops at the first failure so the
        node does not hammer a dead link. Because payloads are idempotent on the server, a payload
        that was delivered but whose confirmation was lost is harmless to re-send next flush.

        Returns the number of payloads confirmed delivered this call (corrupt lines dropped from
        the buffer are not counted).
        """
        if self.transport is None:
            raise TransportError("no transport configured")

        records = list(self._read_lines())
        if not records:
            return 0

        sent = 0
        remaining = []
        stopped = False
        for raw in records:
            if stopped:
                remaining.append(raw)
                continue
            if limit is not None and sent >= limit:
                remaining.append(raw)
                continue
            payload = self._parse(raw)
            if payload is None:
                # A corrupt line is dropped rather than blocking the backlog behind it forever.
                continue
            try:
                self.transport.send(payload)
            except TransportError:
                remaining.append(raw)
                stopped = True
                continue
            sent += 1

        self._rewrite(remaining)
        self._count = len(remaining)
        return sent

    # -- persistence (guarded so the module is import-safe on CPython) --------------------------

    def _enforce_cap(self):
        # Amortised O(1): only when the cached count reaches the cap do we read + rewrite, and
        # then we trim a whole batch (~10%) at once, so the costly flash rewrite is rare even
        # through a long outage instead of happening on every single append once full.
        if self.max_records <= 0 or self._count < self.max_records:
            return
        records = list(self._read_lines())
        keep = max(0, int(self.max_records * 0.9) - 1)
        records = records[-keep:] if keep else []
        self._rewrite(records)
        self._count = len(records)

    def _read_lines(self):
        try:
            handle = self._open(self.path, "r")
        except OSError:
            return
        try:
            for line in handle:
                line = line.strip()
                if line:
                    yield line
        finally:
            handle.close()

    def _rewrite(self, lines):
        """Replace the buffer with ``lines``. Truncates to empty when ``lines`` is empty."""
        with self._open(self.path, "w") as handle:
            for line in lines:
                handle.write(line + "\n")

    @staticmethod
    def _parse(raw):
        try:
            obj = json.loads(raw)
        except Exception:
            return None
        if isinstance(obj, dict) and obj.get("node_id") and obj.get("timestamp"):
            return obj
        return None

    @staticmethod
    def _open(path, mode):
        # Plain built-in open works on both MicroPython and CPython for the node's flash filesystem.
        return open(path, mode)
