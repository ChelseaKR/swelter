"""``swelter diff`` — what changed between two surfaces, snapshots or health reports, and why.

``verify-archive`` proves nothing was tampered with. Nothing proved what legitimately changed.
A steward or a journalist holding two ``sample-surface.json`` files from different days could
only eyeball two GeoJSONs, and an organiser who says "the block got worse this week" had no way
to show whether the *number* moved or the *calibration* did — which are different claims about
the same cell, and only one of them is about the weather.

So every difference here is attributed to exactly one kind, drawn from a closed vocabulary
(:data:`CHANGE_KINDS`), and the vocabulary is deliberately the shape of ``nearmiss``'s
``tools/diff_datasets.py``: two sibling projects that both answer "why is this number different
from last week's" should not answer it in two different languages.

Three rules this module will not bend.

**Absence is never a delta.** A cell missing on one side is reported as ``absent_to_present``
or ``present_to_absent``, carrying only the side that exists. No arithmetic is performed
against a missing value and no ``delta`` key is emitted anywhere, so there is no field in this
output that a reader could mistake for "it went to zero" (ADR 0037).

**An unrecorded version is not a matching version.** If either input records no schema version,
the comparison does not silently proceed as though the two agreed: the header says the version
was not recorded on that side and was therefore *not compared*. Only two versions that are both
recorded and different are a refusal (`--allow-schema-skew` to proceed anyway).

**Two readings are only compared when they describe the same instant.** The default alignment
pairs readings by ``(cell, parameter, bucket)``. `--align latest` compares each side's most
recent reading per cell and parameter instead — the "did this block get worse" question — and
every record it produces carries both buckets, because a change between two different instants
must say which two.

Deterministic: no clock, no network, stdlib only. The same two inputs always produce the same
bytes.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

__all__ = [
    "CHANGE_KINDS",
    "DIFF_SCHEMA_VERSION",
    "Change",
    "DiffError",
    "InputSide",
    "build_report",
    "classify_field",
    "load_side",
    "render_markdown",
    "render_text",
]

DIFF_SCHEMA_VERSION = "1.0"

CHANGE_VALUE = "value_change"
CHANGE_CALIBRATION = "calibration_version"
CHANGE_QC = "qc_state"
CHANGE_RIGHTS = "source_or_rights_change"
CHANGE_APPEARED = "absent_to_present"
CHANGE_DISAPPEARED = "present_to_absent"
CHANGE_SCHEMA = "schema_version_change"

#: The closed attribution vocabulary. A consumer may branch exhaustively on ``kind``.
CHANGE_KINDS: tuple[str, ...] = (
    CHANGE_VALUE,
    CHANGE_CALIBRATION,
    CHANGE_QC,
    CHANGE_RIGHTS,
    CHANGE_APPEARED,
    CHANGE_DISAPPEARED,
    CHANGE_SCHEMA,
)

KIND_SURFACE = "surface"
KIND_SNAPSHOT = "snapshot"
KIND_HEALTH = "health"


class DiffError(Exception):
    """The two inputs cannot be compared, and saying so is the only honest result."""


# ---- attribution --------------------------------------------------------------------------
#
# Which kind a differing field is attributed to. Exact names first, then suffixes, because the
# surface fans a parameter out across `{parameter}_provisional`, `{parameter}_method` and so on.

_CALIBRATION_FIELDS = frozenset({"method", "reference", "version", "calibration", "model"})
_CALIBRATION_SUFFIXES = ("_method", "_reference", "_calibration_version")
_QC_FIELDS = frozenset({"provisional", "qc_flags", "flagged_fraction", "status", "online"})
_QC_SUFFIXES = ("_provisional", "_qc_flags")
_RIGHTS_FIELDS = frozenset(
    {
        "attribution",
        "rights",
        "source",
        "license",
        "data_source",
        "data_license",
        "data_attribution",
        "doi",
        "links",
        "rel",
        "href",
    }
)
_SCHEMA_FIELDS = frozenset({"schema_version", "swelter_version", "data_schema_version"})


def classify_field(field: str) -> str:
    """Attribute one differing field to exactly one change kind.

    The fallthrough is :data:`CHANGE_VALUE` and that is deliberate rather than lazy: a field
    this function has never heard of is a *number or label that moved*, which is the least
    specific and least alarming claim available. Attributing an unknown field to a calibration
    or a rights change would put a specific explanation behind something nothing explained.
    """
    leaf = field.rsplit(".", 1)[-1]
    if leaf in _SCHEMA_FIELDS:
        return CHANGE_SCHEMA
    if leaf in _CALIBRATION_FIELDS or leaf.endswith(_CALIBRATION_SUFFIXES):
        return CHANGE_CALIBRATION
    if leaf in _QC_FIELDS or leaf.endswith(_QC_SUFFIXES):
        return CHANGE_QC
    if leaf in _RIGHTS_FIELDS:
        return CHANGE_RIGHTS
    return CHANGE_VALUE


# ---- the records --------------------------------------------------------------------------


@dataclass(frozen=True)
class Change:
    """One difference, attributed to one kind.

    ``from_value``/``to_value`` are :data:`_ABSENT` on the side where the thing does not exist.
    Nothing here is ever a delta: see the module docstring.
    """

    kind: str
    subject: str
    subject_id: str
    field: str
    from_value: Any = None
    to_value: Any = None
    context: Mapping[str, Any] | None = None

    @property
    def sort_key(self) -> tuple[str, str, str, str]:
        return (self.subject, self.subject_id, self.field, self.kind)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "kind": self.kind,
            "subject": self.subject,
            "subject_id": self.subject_id,
            "field": self.field,
        }
        if self.from_value is not _ABSENT:
            payload["from"] = self.from_value
        if self.to_value is not _ABSENT:
            payload["to"] = self.to_value
        if self.context:
            payload["context"] = dict(self.context)
        return payload


class _Absent:
    """A sentinel for "this side does not have it", distinct from a recorded ``null``.

    ``None`` is a real published value in this project — ``uncertainty: null`` means "no error
    bar, and here is why" (ADR 0035). Using it to also mean "not present" would collapse the
    one distinction this diff exists to keep.
    """

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return "<absent>"


_ABSENT = _Absent()


@dataclass(frozen=True)
class InputSide:
    """One loaded input: what kind it is, what it says about itself, and its content."""

    path: Path
    kind: str
    document: Mapping[str, Any]
    source: str | None
    rights: Mapping[str, Any] | None
    schema_version: str | None


# ---- loading ------------------------------------------------------------------------------


def load_side(path: Path) -> InputSide:
    """Load a surface JSON, a snapshot directory, or a health report, and say which it is."""
    if path.is_dir():
        manifest_path = path / "MANIFEST.json"
        if not manifest_path.is_file():
            raise DiffError(
                f"{path} is a directory with no MANIFEST.json — it is not a swelter snapshot"
            )
        manifest = _read_json(manifest_path)
        return InputSide(
            path=path,
            kind=KIND_SNAPSHOT,
            document=manifest,
            source=_as_str(manifest.get("data_source")),
            rights={
                "license": manifest.get("data_license"),
                "attribution": manifest.get("data_attribution"),
                "doi": manifest.get("doi"),
            },
            schema_version=_as_str(manifest.get("swelter_version")),
        )

    if not path.is_file():
        raise DiffError(f"{path} does not exist")

    document = _read_json(path)
    if "cells" in document:
        rights = document.get("rights")
        rights_map = rights if isinstance(rights, dict) else None
        return InputSide(
            path=path,
            kind=KIND_SURFACE,
            document=document,
            source=_as_str((rights_map or {}).get("source")),
            rights=rights_map,
            schema_version=_as_str((rights_map or {}).get("schema_version")),
        )
    if "nodes" in document:
        return InputSide(
            path=path,
            kind=KIND_HEALTH,
            document=document,
            source=None,
            rights=None,
            schema_version=_as_str(document.get("schema_version")),
        )
    raise DiffError(
        f"{path} is neither a surface (no `cells`) nor a health report (no `nodes`). "
        f"`swelter diff` compares two surfaces, two snapshot directories, or two health reports."
    )


def _read_json(path: Path) -> dict[str, Any]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DiffError(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(loaded, dict):
        raise DiffError(f"{path} is not a JSON object")
    return loaded


def _as_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


# ---- the comparison -----------------------------------------------------------------------


def build_report(
    a: InputSide, b: InputSide, *, align: str = "bucket", allow_schema_skew: bool = False
) -> dict[str, Any]:
    """Compare two loaded sides. Raises :class:`DiffError` rather than guessing."""
    if a.kind != b.kind:
        raise DiffError(
            f"cannot compare a {a.kind} with a {b.kind}: {a.path} and {b.path} are different "
            f"kinds of artifact"
        )
    if align not in {"bucket", "latest"}:
        raise DiffError(f"unknown alignment {align!r}: expected 'bucket' or 'latest'")

    schema = _schema_block(a, b, allow_schema_skew=allow_schema_skew)

    if a.kind == KIND_SURFACE:
        changes = _surface_changes(a.document, b.document, align=align)
    elif a.kind == KIND_HEALTH:
        changes = _health_changes(a.document, b.document)
    else:
        changes = _snapshot_changes(a, b)

    changes.extend(_rights_changes(a, b))
    if schema["comparable"] and schema["a"] != schema["b"]:
        changes.append(
            Change(
                kind=CHANGE_SCHEMA,
                subject="document",
                subject_id=str(a.path.name),
                field="schema_version",
                from_value=schema["a"],
                to_value=schema["b"],
            )
        )

    ordered = sorted(changes, key=lambda change: change.sort_key)
    summary = {kind: sum(1 for c in ordered if c.kind == kind) for kind in CHANGE_KINDS}
    return {
        "schema_version": DIFF_SCHEMA_VERSION,
        "input_kind": a.kind,
        "alignment": align,
        "a": _side_header(a),
        "b": _side_header(b),
        "schema_version_comparison": schema,
        "summary": summary,
        "changes": [change.to_dict() for change in ordered],
    }


def _side_header(side: InputSide) -> dict[str, Any]:
    return {
        "path": str(side.path),
        "source": side.source,
        "rights": dict(side.rights) if side.rights else None,
        "schema_version": side.schema_version,
    }


def _schema_block(a: InputSide, b: InputSide, *, allow_schema_skew: bool) -> dict[str, Any]:
    """Say what was compared, and refuse a recorded mismatch.

    The `unrecorded` case is the one worth being careful about: an artifact that carries no
    version has not told us it matches, and reporting a comparison that did not happen is the
    same defect as reporting a reading that was never taken.
    """
    unrecorded = [label for label, side in (("a", a), ("b", b)) if side.schema_version is None]
    if unrecorded:
        return {
            "a": a.schema_version,
            "b": b.schema_version,
            "comparable": False,
            "note": (
                f"schema version is not recorded on side(s) {', '.join(unrecorded)}, so the two "
                f"versions were NOT compared. This is not a finding that they agree."
            ),
        }
    if a.schema_version != b.schema_version and not allow_schema_skew:
        raise DiffError(
            f"schema versions differ: {a.schema_version!r} ({a.path}) vs "
            f"{b.schema_version!r} ({b.path}). Pass --allow-schema-skew to compare anyway; the "
            f"fields on either side may not mean the same thing."
        )
    return {"a": a.schema_version, "b": b.schema_version, "comparable": True, "note": ""}


def _rights_changes(a: InputSide, b: InputSide) -> list[Change]:
    changes: list[Change] = []
    if a.source != b.source:
        changes.append(
            Change(
                kind=CHANGE_RIGHTS,
                subject="document",
                subject_id=str(a.path.name),
                field="source",
                from_value=a.source,
                to_value=b.source,
            )
        )
    changes.extend(
        _mapping_changes(
            a.rights or {},
            b.rights or {},
            subject="document",
            subject_id=str(a.path.name),
            prefix="rights",
            skip={"schema_version"},
        )
    )
    return changes


def _mapping_changes(
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    *,
    subject: str,
    subject_id: str,
    prefix: str = "",
    skip: frozenset[str] | set[str] = frozenset(),
    context: Mapping[str, Any] | None = None,
) -> list[Change]:
    """Field-by-field, with a present/absent field reported as presence, never as a value."""
    changes: list[Change] = []
    for key in sorted(set(before) | set(after)):
        if key in skip:
            continue
        field = f"{prefix}.{key}" if prefix else key
        old = before.get(key, _ABSENT)
        new = after.get(key, _ABSENT)
        if old is _ABSENT and new is _ABSENT:  # pragma: no cover - impossible by construction
            continue
        if old is _ABSENT:
            changes.append(
                Change(CHANGE_APPEARED, subject, subject_id, field, _ABSENT, new, context)
            )
            continue
        if new is _ABSENT:
            changes.append(
                Change(CHANGE_DISAPPEARED, subject, subject_id, field, old, _ABSENT, context)
            )
            continue
        if old != new:
            changes.append(
                Change(classify_field(field), subject, subject_id, field, old, new, context)
            )
    return changes


# ---- surfaces -----------------------------------------------------------------------------

#: What identifies one published reading. `aqi_window` is in here, and it has to be: the
#: surface publishes TWO `pm25_ugm3` records for the same cell and the same bucket — an
#: `hourly-mean` one that carries an error bar and a `nowcast` one that explains why it does
#: not. Keying on `(cell, parameter, bucket)` alone silently coalesces them, so half of every
#: PM2.5 comparison would be made against the wrong record and the other half would vanish.
#: 1050 records in the committed `web/sample-surface.json` collapse to 900 under the shorter
#: key. A diff that quietly loses a reading is worse than no diff.
_READING_KEY_FIELDS = ("cell_id", "parameter", "bucket", "aqi_window")


def _surface_changes(
    before: Mapping[str, Any], after: Mapping[str, Any], *, align: str
) -> list[Change]:
    old_cells = _readings(before)
    new_cells = _readings(after)
    if align == "latest":
        old_cells = _latest_per_cell(old_cells)
        new_cells = _latest_per_cell(new_cells)

    changes: list[Change] = []
    for key in sorted(set(old_cells) | set(new_cells)):
        old = old_cells.get(key)
        new = new_cells.get(key)
        subject_id = "|".join(key)
        if old is None:
            changes.append(
                Change(CHANGE_APPEARED, "cell", subject_id, "reading", _ABSENT, _label(new))
            )
            continue
        if new is None:
            changes.append(
                Change(CHANGE_DISAPPEARED, "cell", subject_id, "reading", _label(old), _ABSENT)
            )
            continue
        context = None
        if align == "latest" and old.get("bucket") != new.get("bucket"):
            # A comparison across two different instants must say which two, on every record it
            # produces — otherwise "34.8, was 31.2" reads as one place at one time.
            context = {"from_bucket": old.get("bucket"), "to_bucket": new.get("bucket")}
        changes.extend(
            _mapping_changes(
                old,
                new,
                subject="cell",
                subject_id=subject_id,
                skip={"bucket"} if align == "latest" else frozenset(),
                context=context,
            )
        )
    return changes


def _readings(document: Mapping[str, Any]) -> dict[tuple[str, ...], dict[str, Any]]:
    readings: dict[tuple[str, ...], dict[str, Any]] = {}
    cells = document.get("cells")
    if not isinstance(cells, list):
        raise DiffError("surface has no `cells` array")
    for cell in cells:
        if not isinstance(cell, dict):
            raise DiffError("surface `cells` contains a non-object entry")
        key = tuple(str(cell.get(name, "")) for name in _READING_KEY_FIELDS)
        if key in readings:
            # Refuse rather than overwrite. Coalescing two published readings into one would
            # make every comparison against that key a comparison against whichever record
            # happened to be last in the file — a wrong answer that looks like a right one.
            raise DiffError(
                f"surface publishes two readings with the same identity "
                f"{dict(zip(_READING_KEY_FIELDS, key, strict=True))}; `swelter diff` cannot "
                f"tell them apart and will not guess which one to compare"
            )
        readings[key] = cell
    return readings


def _latest_per_cell(
    readings: Mapping[tuple[str, ...], dict[str, Any]],
) -> dict[tuple[str, ...], dict[str, Any]]:
    latest: dict[tuple[str, ...], dict[str, Any]] = {}
    for key, cell in readings.items():
        cell_key = (key[0], key[1], key[3])
        current = latest.get(cell_key)
        if current is None or str(cell.get("bucket", "")) > str(current.get("bucket", "")):
            latest[cell_key] = cell
    return latest


def _label(cell: Mapping[str, Any] | None) -> Any:
    if cell is None:  # pragma: no cover - guarded by the caller
        return None
    return {name: cell.get(name) for name in ("label", "parameter", "bucket", "mean", "n")}


# ---- health reports -----------------------------------------------------------------------


def _health_changes(before: Mapping[str, Any], after: Mapping[str, Any]) -> list[Change]:
    old_nodes = _by_id(before.get("nodes"), "node_id", "health report `nodes`")
    new_nodes = _by_id(after.get("nodes"), "node_id", "health report `nodes`")
    changes: list[Change] = []
    for node_id in sorted(set(old_nodes) | set(new_nodes)):
        old = old_nodes.get(node_id)
        new = new_nodes.get(node_id)
        if old is None:
            changes.append(Change(CHANGE_APPEARED, "node", node_id, "node", _ABSENT, new))
            continue
        if new is None:
            changes.append(Change(CHANGE_DISAPPEARED, "node", node_id, "node", old, _ABSENT))
            continue
        changes.extend(_mapping_changes(old, new, subject="node", subject_id=node_id))

    old_cal = _calibration_entries(before)
    new_cal = _calibration_entries(after)
    for key in sorted(set(old_cal) | set(new_cal)):
        old_entry = old_cal.get(key)
        new_entry = new_cal.get(key)
        if old_entry is None:
            changes.append(
                Change(CHANGE_APPEARED, "correction", key, "correction", _ABSENT, new_entry)
            )
            continue
        if new_entry is None:
            changes.append(
                Change(CHANGE_DISAPPEARED, "correction", key, "correction", old_entry, _ABSENT)
            )
            continue
        changes.extend(_mapping_changes(old_entry, new_entry, subject="correction", subject_id=key))
    return changes


def _by_id(rows: object, key: str, where: str) -> dict[str, dict[str, Any]]:
    if rows is None:
        return {}
    if not isinstance(rows, list):
        raise DiffError(f"{where} must be a list")
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise DiffError(f"{where} contains a non-object entry")
        out[str(row.get(key, ""))] = row
    return out


def _calibration_entries(document: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """The per-node correction rows a health report carries, keyed by node and parameter."""
    block = document.get("calibration")
    if not isinstance(block, dict):
        return {}
    rows = block.get("corrections") or block.get("nodes")
    if not isinstance(rows, list):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        out[f"{row.get('node_id', '')}/{row.get('parameter', '')}"] = row
    return out


# ---- snapshots ----------------------------------------------------------------------------

_MANIFEST_SCALARS = (
    "release_version",
    "created_at",
    "record_count",
    "observation_window",
    "notes",
)


def _snapshot_changes(a: InputSide, b: InputSide) -> list[Change]:
    changes = _mapping_changes(
        {k: v for k, v in a.document.items() if k in _MANIFEST_SCALARS},
        {k: v for k, v in b.document.items() if k in _MANIFEST_SCALARS},
        subject="document",
        subject_id="MANIFEST.json",
    )

    old_files = _by_id(a.document.get("files"), "name", "MANIFEST `files`")
    new_files = _by_id(b.document.get("files"), "name", "MANIFEST `files`")
    for name in sorted(set(old_files) | set(new_files)):
        old = old_files.get(name)
        new = new_files.get(name)
        if old is None:
            changes.append(Change(CHANGE_APPEARED, "file", name, "file", _ABSENT, new))
            continue
        if new is None:
            changes.append(Change(CHANGE_DISAPPEARED, "file", name, "file", old, _ABSENT))
            continue
        changes.extend(
            _mapping_changes(
                {k: old.get(k) for k in ("sha256", "bytes")},
                {k: new.get(k) for k in ("sha256", "bytes")},
                subject="file",
                subject_id=name,
            )
        )

    changes.extend(_aggregate_changes(a.path, b.path))
    return changes


def _aggregate_changes(a_dir: Path, b_dir: Path) -> list[Change]:
    """Per-cell differences in the frozen ``aggregate.geojson``, if both snapshots carry one."""
    old_path = a_dir / "aggregate.geojson"
    new_path = b_dir / "aggregate.geojson"
    if not old_path.is_file() or not new_path.is_file():
        # Reported by the MANIFEST file comparison above as an appearance/disappearance. Nothing
        # is invented here for a file that is not on both sides.
        return []
    old_features = _features(_read_json(old_path))
    new_features = _features(_read_json(new_path))
    changes: list[Change] = []
    for cell_id in sorted(set(old_features) | set(new_features)):
        old = old_features.get(cell_id)
        new = new_features.get(cell_id)
        if old is None:
            changes.append(Change(CHANGE_APPEARED, "cell", cell_id, "cell", _ABSENT, _label(new)))
            continue
        if new is None:
            changes.append(
                Change(CHANGE_DISAPPEARED, "cell", cell_id, "cell", _label(old), _ABSENT)
            )
            continue
        changes.extend(_mapping_changes(old, new, subject="cell", subject_id=cell_id))
    return changes


def _features(document: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    features = document.get("features")
    if not isinstance(features, list):
        raise DiffError("aggregate.geojson has no `features` array")
    out: dict[str, dict[str, Any]] = {}
    for feature in features:
        if not isinstance(feature, dict):
            continue
        props = feature.get("properties")
        if not isinstance(props, dict):
            continue
        out[str(props.get("cell_id", ""))] = props
    return out


# ---- rendering ----------------------------------------------------------------------------


def _header_lines(report: Mapping[str, Any]) -> list[str]:
    a = report["a"]
    b = report["b"]
    schema = report["schema_version_comparison"]
    lines = [
        f"comparing two {report['input_kind']}s, aligned by {report['alignment']}",
        f"  a: {a['path']}",
        f"  b: {b['path']}",
        f"  source:  {a['source']!r} -> {b['source']!r}",
        f"  schema:  {a['schema_version']!r} -> {b['schema_version']!r}",
    ]
    if schema["note"]:
        lines.append(f"  NOTE: {schema['note']}")
    return lines


def render_text(report: Mapping[str, Any]) -> str:
    lines = _header_lines(report)
    changes: Sequence[Mapping[str, Any]] = report["changes"]
    lines.append("")
    if not changes:
        lines.append("no changes")
        return "\n".join(lines) + "\n"
    for kind, count in report["summary"].items():
        if count:
            lines.append(f"  {kind:<20} {count}")
    lines.append("")
    for change in changes:
        detail = _detail(change)
        lines.append(
            f"  [{change['kind']}] {change['subject']} {change['subject_id']} "
            f"{change['field']}: {detail}"
        )
    return "\n".join(lines) + "\n"


def render_markdown(report: Mapping[str, Any]) -> str:
    lines = ["# swelter diff", ""]
    lines.extend(f"- {line.strip()}" for line in _header_lines(report))
    lines.extend(["", "## Summary", ""])
    lines.append("| kind | count |")
    lines.append("| --- | --- |")
    for kind, count in report["summary"].items():
        lines.append(f"| `{kind}` | {count} |")
    lines.extend(["", "## Changes", ""])
    changes: Sequence[Mapping[str, Any]] = report["changes"]
    if not changes:
        lines.append("No changes.")
        return "\n".join(lines) + "\n"
    lines.append("| kind | subject | id | field | change |")
    lines.append("| --- | --- | --- | --- | --- |")
    for change in changes:
        lines.append(
            f"| `{change['kind']}` | {change['subject']} | `{change['subject_id']}` | "
            f"`{change['field']}` | {_detail(change)} |"
        )
    return "\n".join(lines) + "\n"


def _detail(change: Mapping[str, Any]) -> str:
    """Say what moved — and, where one side does not exist, say *that*, never a number."""
    has_from = "from" in change
    has_to = "to" in change
    if has_from and not has_to:
        return f"{_short(change['from'])} -> absent"
    if has_to and not has_from:
        return f"absent -> {_short(change['to'])}"
    detail = f"{_short(change.get('from'))} -> {_short(change.get('to'))}"
    context = change.get("context")
    if context:
        detail += f" (at {context.get('from_bucket')} -> {context.get('to_bucket')})"
    return detail


def _short(value: Any) -> str:
    if isinstance(value, dict | list):
        return json.dumps(value, sort_keys=True, separators=(",", ":"))
    return json.dumps(value)
