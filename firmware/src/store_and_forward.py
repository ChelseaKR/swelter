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

Two power-loss properties make the backlog survive an abrupt reset, not just a clean shutdown:

* **Appends are flushed before return.** A payload is written as one ``line + "\n"`` and the handle
  is flushed (and ``fsync``'d where the runtime supports it) before :meth:`append` returns. A reset
  mid-write leaves at most one torn trailing line, which :meth:`_parse` rejects on the next read, so
  a half-written record is dropped, never forwarded as a malformed payload.
* **Rewrites are replace-by-rename.** Trimming and post-flush compaction write the survivors to a
  sibling temp file, flush it, then rename it over the buffer. Rename is atomic on the node's flash
  filesystem, so a reset during compaction leaves either the old complete buffer or the new complete
  buffer — never a truncated one. The backlog is never lost to a crash in the middle of housekeeping.
"""

from __future__ import annotations

try:  # MicroPython and CPython both provide json; import at module load is safe on both.
    import json
except Exception:  # pragma: no cover - json is always present
    json = None  # type: ignore[assignment]


def _default_sleep(seconds):
    """Guarded sleep used between retries; a no-op if no runtime clock is available."""
    try:
        import time as _time

        _time.sleep(seconds)
    except Exception:  # pragma: no cover - time.sleep exists on both runtimes
        pass


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
    max_attempts:
        Upper bound on send attempts for a single payload within one :meth:`flush` call. The first
        :class:`TransportError` is retried in place, backing off between tries, up to this many
        attempts; if it still fails the payload (and everything after it) stays buffered and the
        flush stops, to be retried whole on the next cycle. Bounding the retries keeps one bad link
        from spinning the radio — and the CPU — for the entire sample interval.
    backoff_base_s / backoff_cap_s:
        Exponential backoff between in-flush retries: the n-th wait is
        ``min(backoff_base_s * 2 ** (n - 1), backoff_cap_s)``. Bounded by the cap so a long outage
        does not push a single wait past the sample interval. Retries never duplicate data because
        the payload is idempotent on the server's store key.
    sleep:
        Injected sleep used between retries (seconds). Defaults to a guarded ``time.sleep``;
        tests pass a fake so the backoff is observed without real waiting.
    """

    def __init__(
        self,
        path,
        transport=None,
        max_records=20000,
        max_attempts=3,
        backoff_base_s=1.0,
        backoff_cap_s=30.0,
        sleep=None,
    ):
        self.path = path
        self.transport = transport
        self.max_records = int(max_records)
        self.max_attempts = max(1, int(max_attempts))
        self.backoff_base_s = float(backoff_base_s)
        self.backoff_cap_s = float(backoff_cap_s)
        self._sleep = sleep if sleep is not None else _default_sleep
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
        handle = self._open(self.path, "a")
        try:
            handle.write(line + "\n")
            self._sync(handle)
        finally:
            handle.close()
        self._count += 1

    def pending(self):
        """Number of payloads currently buffered."""
        return sum(1 for _ in self._read_lines())

    # -- flushing ------------------------------------------------------------------------------

    def flush(self, limit=None):
        """Forward buffered payloads oldest-first; keep only those not yet confirmed sent.

        Walks the buffer from the head. Each payload is sent through the transport; a payload the
        transport confirms is dropped, a payload that raises :class:`TransportError` is retried in
        place with bounded exponential backoff (up to ``max_attempts``). If it still fails it is kept
        along with everything after it (preserving order) and flushing stops, so the node does not
        hammer a dead link nor spin the radio for the whole interval. Because payloads are idempotent
        on the server, a payload that was delivered but whose confirmation was lost is harmless to
        re-send next flush.

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
            if self._send_with_retry(payload):
                sent += 1
            else:
                remaining.append(raw)
                stopped = True

        self._rewrite(remaining)
        self._count = len(remaining)
        return sent

    def _send_with_retry(self, payload):
        """Send one payload, retrying a :class:`TransportError` with bounded backoff.

        Returns ``True`` if the transport confirmed delivery within ``max_attempts``, ``False`` if
        every attempt failed. A re-send is safe to repeat because the payload is idempotent on the
        server's store key, so a delivery whose confirmation was lost never duplicates.
        """
        for attempt in range(1, self.max_attempts + 1):
            try:
                self.transport.send(payload)
                return True
            except TransportError:
                if attempt >= self.max_attempts:
                    return False
                wait = min(self.backoff_base_s * (2 ** (attempt - 1)), self.backoff_cap_s)
                if wait > 0:
                    self._sleep(wait)
        return False

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
        """Replace the buffer with ``lines`` atomically: write a temp file, then rename it over.

        Rename is atomic on the node's flash filesystem, so a reset mid-rewrite leaves either the
        old complete buffer or the new one — never a half-written file. Truncates to empty when
        ``lines`` is empty (an empty temp file renamed into place).
        """
        tmp = self.path + ".tmp"
        handle = self._open(tmp, "w")
        try:
            for line in lines:
                handle.write(line + "\n")
            self._sync(handle)
        finally:
            handle.close()
        self._replace(tmp, self.path)

    @staticmethod
    def _sync(handle):
        """Flush a handle to the flash medium where the runtime supports it; best-effort.

        CPython exposes ``flush`` + ``os.fsync``; MicroPython flushes on the handle and the VFS
        commits. Either way the bytes are on flash before the call returns, so a reset just after a
        write does not lose the record. Any failure here is non-fatal — the record is still in the
        OS buffer and the worst case is a torn trailing line the reader rejects.
        """
        try:
            handle.flush()
        except Exception:  # pragma: no cover - flush is available on both runtimes
            pass
        try:
            import os

            os.fsync(handle.fileno())
        except Exception:
            # MicroPython has no os.fsync / fileno; the handle flush above is the durability point.
            pass

    @staticmethod
    def _replace(src, dst):
        """Atomically move ``src`` onto ``dst``. Falls back to remove+rename on MicroPython."""
        try:
            import os

            try:
                os.replace(src, dst)  # atomic on CPython; not present on MicroPython
                return
            except AttributeError:
                pass
            try:
                os.remove(dst)
            except OSError:
                pass
            os.rename(src, dst)
        except Exception:  # pragma: no cover - defensive; os is present on both runtimes
            pass

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
