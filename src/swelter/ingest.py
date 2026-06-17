"""Intake: parse node payloads, validate, explode to observations, QC, and store — idempotent.

A node reports *wide* — one payload per timestamp carrying every parameter it sampled. Ingest
turns each payload into long-format :class:`~swelter.models.Observation` records, one per
parameter, runs the QC pass, and writes them to the store. Re-running is always safe: the
store key is idempotent, so a node backfilling its store-and-forward buffer after an outage
fills the gap instead of duplicating.

Validation is strict but forgiving in the right direction. A payload missing a node id or a
timestamp, or carrying no recognisable parameter, is *quarantined* (written to
``quarantine.jsonl`` with a reason) rather than ingested — malformed data never silently
enters the record. Unknown extra fields are ignored, so a firmware that adds a sensor does not
break intake.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import qc
from .models import PARAMETERS, RAW, Observation, format_timestamp, parse_timestamp
from .store import Store, WriteResult

_TS_KEYS = ("timestamp", "ts", "time")
_NODE_KEYS = ("node_id", "node", "id")


@dataclass
class IngestResult:
    """What an ingest run did, for the operator and for CI assertions."""

    accepted_payloads: int = 0
    observations_written: int = 0
    duplicates: int = 0
    quarantined: int = 0
    parameters: set[str] = field(default_factory=set)

    @property
    def observations_seen(self) -> int:
        return self.observations_written + self.duplicates


def _first(payload: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in payload and payload[key] not in (None, ""):
            return payload[key]
    return None


def _readings(payload: dict[str, Any]) -> dict[str, Any]:
    """Support both flat payloads and an explicit ``{"readings": {...}}`` envelope."""
    nested = payload.get("readings")
    if isinstance(nested, dict):
        return nested
    return payload


def explode(payload: dict[str, Any]) -> tuple[list[Observation], str | None]:
    """Turn one payload into raw observations, or return a quarantine reason.

    Returns ``(observations, None)`` on success or ``([], reason)`` if the payload is
    unusable. A payload that parses but yields zero known parameters is quarantined too — an
    empty reading is not a measurement.
    """
    node = _first(payload, _NODE_KEYS)
    if not isinstance(node, str) or not node:
        return [], "missing or non-string node_id"
    ts_raw = _first(payload, _TS_KEYS)
    if not isinstance(ts_raw, str):
        return [], "missing or non-string timestamp"
    try:
        timestamp = format_timestamp(parse_timestamp(ts_raw))
    except (ValueError, TypeError):
        return [], f"unparseable timestamp: {ts_raw!r}"

    readings = _readings(payload)
    observations: list[Observation] = []
    for name, param in PARAMETERS.items():
        if name not in readings:
            continue
        value = readings[name]
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            continue
        observations.append(
            Observation(
                node_id=node,
                timestamp=timestamp,
                parameter=name,
                value=float(value),
                unit=param.unit,
                calibration=RAW,
            )
        )
    if not observations:
        return [], "no recognised parameters"
    return observations, None


def ingest(
    payloads: Iterable[dict[str, Any]],
    store: Store,
    *,
    quarantine_path: str | Path | None = None,
    run_qc: bool = True,
) -> IngestResult:
    """Validate, explode, QC, and persist a batch of payloads."""
    result = IngestResult()
    observations: list[Observation] = []
    quarantine: list[dict[str, Any]] = []

    for payload in payloads:
        obs, reason = explode(payload)
        if reason is not None:
            quarantine.append({"reason": reason, "payload": payload})
            result.quarantined += 1
            continue
        result.accepted_payloads += 1
        observations.extend(obs)
        result.parameters.update(o.parameter for o in obs)

    if run_qc:
        observations = qc.apply(observations)

    write: WriteResult = store.write(observations)
    result.observations_written = write.written
    result.duplicates = write.duplicates

    if quarantine_path is not None and quarantine:
        _append_jsonl(quarantine_path, quarantine)

    return result


def read_jsonl(path: str | Path) -> Iterator[dict[str, Any]]:
    """Yield one parsed JSON object per non-blank line."""
    with Path(path).open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    yield obj


def ingest_file(
    path: str | Path,
    store: Store,
    *,
    quarantine_path: str | Path | None = None,
    run_qc: bool = True,
) -> IngestResult:
    """Ingest a JSONL file of node payloads."""
    return ingest(read_jsonl(path), store, quarantine_path=quarantine_path, run_qc=run_qc)


def _append_jsonl(path: str | Path, rows: list[dict[str, Any]]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, separators=(",", ":")) + "\n")
