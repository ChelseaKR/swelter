"""Export: CSV and JSON dumps, and the human-readable run summary the CLI prints.

Export is a first-class command, not an afterthought — it is how a community leaves with its
data and stands the network up elsewhere. The formats are deliberately boring: flat CSV and
JSON that a resident, a reporter, or a researcher can open without an account, a key, or this
codebase. Observation provenance (calibration version, QC verdict, uncertainty) travels in
every row, so a value's trustworthiness leaves with it.
"""

from __future__ import annotations

import csv
import io
import json
import math
from collections.abc import Iterable, Sequence

from .calibrate import CorrectionRegistry
from .models import RAW, Observation, parse_timestamp
from .qc import Gap

_CSV_FIELDS = (
    "node_id",
    "timestamp",
    "parameter",
    "value",
    "unit",
    "calibration",
    "qc",
    "uncertainty",
    "trustworthy",
)

DATA_LICENSE_LINE = "CC0-1.0 (observations) · see DATA-LICENSE"

# Characters that make a spreadsheet treat a cell as a formula. node_id is self-reported by
# untrusted field devices, so a CSV cell starting with one of these is neutralised on export.
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _csv_safe(value: object) -> object:
    """Prefix a risky text cell with a single quote so a spreadsheet treats it as literal text."""
    if isinstance(value, str) and value and value[0] in _FORMULA_PREFIXES:
        return "'" + value
    return value


def to_records(observations: Iterable[Observation]) -> list[dict[str, object]]:
    return [
        {
            "node_id": o.node_id,
            "timestamp": o.timestamp,
            "parameter": o.parameter,
            # A non-finite value would serialise as invalid JSON (NaN/Infinity tokens); map it
            # to null. Ingest rejects these, so this is belt-and-suspenders for direct callers.
            "value": o.value if math.isfinite(o.value) else None,
            "unit": o.unit,
            "calibration": o.calibration,
            "qc": o.qc,
            "uncertainty": o.uncertainty,
            # An explicit status so a downloader needn't infer trust from the calibration string.
            "trustworthy": o.is_trustworthy,
        }
        for o in observations
    ]


def to_csv(observations: Iterable[Observation]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=_CSV_FIELDS)
    writer.writeheader()
    for record in to_records(observations):
        writer.writerow({key: _csv_safe(value) for key, value in record.items()})
    return buffer.getvalue()


def to_json(observations: Iterable[Observation], *, indent: int | None = None) -> str:
    payload = {
        "license": "CC0-1.0",
        "observations": to_records(observations),
    }
    return json.dumps(payload, indent=indent, allow_nan=False)


def _thousands(value: int) -> str:
    return f"{value:,}"


def summarize(
    observations: Sequence[Observation],
    *,
    gaps: Sequence[Gap] = (),
    registry: CorrectionRegistry | None = None,
) -> str:
    """Build the multi-line export banner the README shows, from real counts."""
    total = len(observations)
    nodes = sorted({o.node_id for o in observations})
    calibrated_nodes = sorted({o.node_id for o in observations if o.calibration != RAW})
    raw_only = [n for n in nodes if n not in calibrated_nodes]

    versions = {o.calibration for o in observations if o.calibration != RAW}
    timestamps = sorted({o.timestamp for o in observations})
    coverage = f"{timestamps[0]} → {timestamps[-1]}" if timestamps else "no observations"

    lines = [
        f"swelter: {_thousands(total)} observations from {len(nodes)} nodes "
        f"({len(calibrated_nodes)} calibrated, {len(raw_only)} raw-flagged)"
    ]
    if versions:
        # Condense per-node versions (parameter.method.node) to method families with counts.
        families: dict[str, int] = {}
        for version in versions:
            family = version.rsplit(".", 1)[0]
            families[family] = families.get(family, 0) + 1
        applied = "; ".join(f"{family} ×{count}" for family, count in sorted(families.items()))
        lines.append(f"         calibration applied: {applied}")
    gap_note = ""
    if gaps:
        longest = gaps[0]
        gap_note = f", longest gap {round(longest.seconds / 60)} min ({longest.node_id} offline)"
    lines.append(f"         coverage: {coverage}{gap_note}")
    lines.append(f"         data license: {DATA_LICENSE_LINE}")
    return "\n".join(lines)


def filter_observations(
    observations: Iterable[Observation],
    *,
    since: str | None = None,
    until: str | None = None,
    node: str | None = None,
    parameter: str | None = None,
) -> list[Observation]:
    """In-memory filter mirroring the store query, for already-loaded streams."""
    since_dt = parse_timestamp(since) if since else None
    until_dt = parse_timestamp(until) if until else None
    out: list[Observation] = []
    for obs in observations:
        if node is not None and obs.node_id != node:
            continue
        if parameter is not None and obs.parameter != parameter:
            continue
        if since_dt is not None and parse_timestamp(obs.timestamp) < since_dt:
            continue
        if until_dt is not None and parse_timestamp(obs.timestamp) > until_dt:
            continue
        out.append(obs)
    return out
