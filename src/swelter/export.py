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
from collections.abc import Iterable, Mapping, Sequence
from typing import cast

from .calibrate import CorrectionRegistry
from .models import QC_SUSPICIOUS, RAW, Observation, parse_timestamp
from .qc import Gap

TermsKey = str | tuple[str, str] | tuple[str, str, str]

_CSV_FIELDS = (
    "node_id",
    "timestamp",
    "parameter",
    "value",
    "unit",
    "source",
    "calibration",
    "qc",
    "qc_flags",
    "uncertainty",
    "trustworthy",
    "data_license",
    "data_attribution",
)

DATA_LICENSE_LINE = "CC0-1.0 (observations) · see DATA-LICENSE"

#: The store itself is source-agnostic (native network observations are CC0), so this is the
#: default when a caller doesn't say otherwise. A fetched third-party source (OpenAQ's
#: provider-specific terms; Sensor.Community's ODC-DbCL-1.0; Open-Meteo's CC BY 4.0) keeps its own
#: terms and must pass them explicitly at export time — see the ``LICENSE`` constants in
#: ``sources/*.py``.
DEFAULT_LICENSE = "CC0-1.0"

# Characters that make a spreadsheet treat a cell as a formula. node_id is self-reported by
# untrusted field devices, so a CSV cell starting with one of these is neutralised on export.
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _csv_safe(value: object) -> object:
    """Prefix a risky text cell with a single quote so a spreadsheet treats it as literal text."""
    if isinstance(value, str) and value and value[0] in _FORMULA_PREFIXES:
        return "'" + value
    return value


def to_records(
    observations: Iterable[Observation],
    *,
    terms_by_observation: Mapping[TermsKey, Mapping[str, str]] | None = None,
) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for observation in observations:
        record: dict[str, object] = {
            "node_id": observation.node_id,
            "timestamp": observation.timestamp,
            "parameter": observation.parameter,
            # A non-finite value would serialise as invalid JSON (NaN/Infinity tokens); map it
            # to null. Ingest rejects these, so this is belt-and-suspenders for direct callers.
            "value": observation.value if math.isfinite(observation.value) else None,
            "unit": observation.unit,
            "source": observation.source,
            "calibration": observation.calibration,
            "qc": observation.qc,
            # The suspicious QC verdict(s) on this reading, as an array so it matches the surface
            # cell's `qc_flags` field and travels with the value (ADR 0029, invariant 4). A single
            # observation carries at most one verdict, so this is [] or a one-element list; range
            # and missing are physically unmappable, not suspicious, and never appear here.
            "qc_flags": [observation.qc] if observation.qc in QC_SUSPICIOUS else [],
            "uncertainty": observation.uncertainty,
            # An explicit status so a downloader needn't infer trust from the calibration string.
            "trustworthy": observation.is_trustworthy,
        }
        node_terms = None
        if terms_by_observation is not None:
            node_terms = terms_by_observation.get(
                (observation.node_id, observation.timestamp, observation.source)
            )
            if node_terms is None:
                node_terms = terms_by_observation.get((observation.node_id, observation.timestamp))
            if node_terms is None:
                node_terms = terms_by_observation.get(observation.node_id)
        if node_terms is not None:
            record["data_license"] = node_terms["license"]
            record["data_attribution"] = node_terms["attribution"]
        records.append(record)
    return records


def to_csv(
    observations: Iterable[Observation],
    *,
    license: str | None = None,
    attribution: str | None = None,
    terms_by_observation: Mapping[TermsKey, Mapping[str, str]] | None = None,
) -> str:
    items = list(observations)
    if license is None or not license.strip():
        raise ValueError("export requires an explicit data license")
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=_CSV_FIELDS)
    writer.writeheader()
    for record in to_records(items, terms_by_observation=terms_by_observation):
        row = {
            **record,
            # A CSV cell is a scalar, so the qc_flags array (always a list from to_records) is
            # flattened to a space-joined string ("spike", "flatline", or ""); JSON keeps the array.
            "qc_flags": " ".join(cast("list[str]", record["qc_flags"])),
            # Keep provenance in-band without inventing non-standard comment lines before the
            # header. Repeating it per row makes an extracted subset self-describing and leaves
            # the result readable by ordinary csv.DictReader/pandas consumers.
            "data_license": record.get("data_license", license),
            "data_attribution": record.get("data_attribution", attribution or ""),
        }
        writer.writerow({key: _csv_safe(value) for key, value in row.items()})
    return buffer.getvalue()


def to_json(
    observations: Iterable[Observation],
    *,
    indent: int | None = None,
    license: str | None = None,
    attribution: str | None = None,
    terms_by_observation: Mapping[TermsKey, Mapping[str, str]] | None = None,
) -> str:
    items = list(observations)
    if license is None or not license.strip():
        raise ValueError("export requires an explicit data license")
    payload: dict[str, object] = {"license": license}
    if attribution:
        payload["attribution"] = attribution
    payload["observations"] = to_records(items, terms_by_observation=terms_by_observation)
    return json.dumps(payload, indent=indent, allow_nan=False)


def _thousands(value: int) -> str:
    return f"{value:,}"


def summarize(
    observations: Sequence[Observation],
    *,
    gaps: Sequence[Gap] = (),
    registry: CorrectionRegistry | None = None,
    license: str = DEFAULT_LICENSE,
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
        applied = "; ".join(f"{family} x{count}" for family, count in sorted(families.items()))
        lines.append(f"         calibration applied: {applied}")
    gap_note = ""
    if gaps:
        longest = gaps[0]
        gap_note = f", longest gap {round(longest.seconds / 60)} min ({longest.node_id} offline)"
    lines.append(f"         coverage: {coverage}{gap_note}")
    # The richer native-store line only applies to the CC0 default (it names DATA-LICENSE, which
    # exists for the repo's own observations); a fetched third-party license stands on its own.
    license_line = DATA_LICENSE_LINE if license == DEFAULT_LICENSE else license
    lines.append(f"         data license: {license_line}")
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
