"""Archive integrity: re-check stored row hashes and chain per-day digests for tamper-evidence.

``store.py`` writes a SHA-256 ``content_hash`` per row at write time (audit F4, "immutable and
content-hashed") and nothing ever re-reads it after that — the property is enforced only at
write time, never checked later. This module is the read-time half:

* :func:`verify_rows` recomputes every stored row's hash from its own value-bearing fields and
  reports any row whose stored hash no longer matches — the row was mutated in place, outside the
  append-only write path.
* :func:`daily_digests` folds the whole store into one canonical SHA-256 per UTC day, then chains
  the days head-to-tail (``chain = sha256(prev_chain + date + day_digest)``) so a single mutation
  anywhere in history changes that day's digest *and* every chain value after it — the tamper is
  detectable even if the mutated row itself is never directly re-checked again.
* :func:`write_digests` publishes that chain as ``digests.jsonl`` in the store folder, so a
  journalist (or ``/api/health.json``) can cite the current head without re-hashing anything.

No signing. Key custody is a governance decision (``docs/governance.md``), deliberately deferred
to an ADR rather than improvised here — this makes the archive tamper-*evident*, not tamper-proof.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from .models import parse_timestamp
from .store import SqliteStore, store_paths


@dataclass(frozen=True)
class Mismatch:
    """One stored row whose recomputed content hash disagrees with what was persisted."""

    node_id: str
    timestamp: str
    parameter: str
    calibration: str
    expected: str
    actual: str


def verify_rows(store: SqliteStore) -> list[Mismatch]:
    """Recompute every stored row's content hash and report any that disagree.

    An empty list means the raw archive matches its own recorded hashes bit for bit — the
    row-level half of tamper evidence (:func:`daily_digests` is the chained half). Iterates in
    :meth:`~swelter.store.SqliteStore.iter_rows` order (day, node, parameter, timestamp), so a
    report is reproducible across runs.
    """
    mismatches: list[Mismatch] = []
    for obs, stored_hash in store.iter_rows():
        actual = obs.content_hash()
        if actual != stored_hash:
            mismatches.append(
                Mismatch(
                    node_id=obs.node_id,
                    timestamp=obs.timestamp,
                    parameter=obs.parameter,
                    calibration=obs.calibration,
                    expected=stored_hash,
                    actual=actual,
                )
            )
    return mismatches


@dataclass(frozen=True)
class DayDigest:
    """One UTC day's canonical digest, plus the running chain hash through that day."""

    date: str  # YYYY-MM-DD
    row_count: int
    digest: str
    chain: str


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _canonical(value: object) -> str:
    """Same ``json.dumps(..., separators=(",", ":"))`` convention as ``Observation.content_hash``,
    so canonicalization is deterministic across platforms and Python versions for the same reason
    it is there: no incidental whitespace differences, stable key order for the dict records."""
    return json.dumps(value, separators=(",", ":"))


def daily_digests(store: SqliteStore) -> list[DayDigest]:
    """Group every stored row hash by UTC day and chain the days into one head hash.

    Per day: sort that day's stored ``content_hash`` values (sorting makes the digest independent
    of write/iteration order) and fold them into one canonical SHA-256 (``digest``). Then walk
    days oldest-first, folding each day's digest into a running
    ``chain = sha256(prev_chain + date + digest)``, seeded with the empty string — so the last
    day's ``chain`` is the archive's head: any single-byte change to any row, on any day, changes
    that day's digest and every chain value after it.
    """
    by_day: dict[str, list[str]] = defaultdict(list)
    for obs, stored_hash in store.iter_rows():
        day = parse_timestamp(obs.timestamp).date().isoformat()
        by_day[day].append(stored_hash)

    digests: list[DayDigest] = []
    chain = ""
    for day in sorted(by_day):
        hashes = sorted(by_day[day])
        digest = _sha256(_canonical(hashes))
        chain = _sha256(chain + day + digest)
        digests.append(DayDigest(date=day, row_count=len(hashes), digest=digest, chain=chain))
    return digests


def write_digests(store_dir: str | Path, digests: list[DayDigest]) -> Path:
    """Write ``digests.jsonl`` into the store folder: one line per day, plus a final head record.

    Deterministic ordering (ascending date — the order :func:`daily_digests` already returns), LF
    line endings, a trailing newline: two runs over the same fixture reproduce this file byte for
    byte, which is the guarantee a ``make demo`` replay checks.
    """
    path = store_paths(store_dir)["digests"]
    lines = [
        _canonical({"date": d.date, "row_count": d.row_count, "digest": d.digest, "chain": d.chain})
        for d in digests
    ]
    head = digests[-1].chain if digests else ""
    last_day = digests[-1].date if digests else None
    lines.append(_canonical({"head": head, "days": len(digests), "last_day": last_day}))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def read_head(store_dir: str | Path) -> dict[str, object] | None:
    """Read the head record (the last line) of ``digests.jsonl`` without recomputing anything.

    Backs the cheap ``integrity`` block in :func:`swelter.qc.health_report` — ``/api/health.json``
    should not re-hash the whole store on every request, so it reads whatever
    ``swelter verify-archive --write`` last published instead. Returns ``None`` if no digests file
    has been written yet, or if the file exists but cannot be parsed (never raises: a malformed or
    stale digests file must not take the health endpoint down with it).
    """
    path = store_paths(store_dir)["digests"]
    if not path.is_file():
        return None
    try:
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if not lines:
            return None
        return cast(dict[str, object], json.loads(lines[-1]))
    except (json.JSONDecodeError, OSError):
        return None
