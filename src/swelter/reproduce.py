"""``swelter reproduce`` — rebuild a snapshot's surface from its own frozen inputs.

``swelter snapshot`` freezes the immutable raw observations, the correction registry fitted
against them, and the gridded surface. ``swelter verify-archive`` proves the store's rows are
intact and ``swelter restore --verify`` proves an archive round-trips. None of them proves the
published surface can be *re-derived* from its inputs, which is the claim ``docs/citability.md``
makes when it says a researcher can publish against a snapshot, and the claim a reviewer is
relying on when they quote a Danger-day count.

So this module re-runs the pipeline — apply the frozen corrections to the frozen raw, aggregate
the result — and compares the bytes to the frozen ``aggregate.geojson``. Three rules shape it.

**A reproduction that could not be attempted is not a reproduction that succeeded.** The verdict
has four states, not two. ``reproduced`` requires every check in :data:`REQUIRED_CHECKS` to have
*run* and passed. A release that does not record the swelter version, the data-schema version or
the configuration fingerprint the reproduction would need is ``indeterminate`` — reported with
the name of the thing that is missing, and never with the exit status of a success. Older
snapshots, written before the manifest carried those fields, land here by construction.

**The configuration is an input, and it is not in the snapshot.** The surface depends on the
grid resolution, the published node locations, the hazard pack, the calibration windows and the
reference monitors — all of which live in ``network.yaml``, which also holds the precise
coordinates a host may have declined to publish. Freezing it into a release would leak exactly
what hard rule 2 protects, so the snapshot records only a fingerprint (see
:func:`swelter.config.configuration_fingerprint`) and ``reproduce`` refuses, by name, when the
configuration it was handed is not the one the release was built with. That refusal is the
honest answer: without the operator's configuration the surface genuinely cannot be re-derived,
and saying so is better than rebuilding against a different one and reporting the difference as
data rot.

**A different swelter is a different question.** Cross-version reproduction is reported, not
attempted: if the running version is not the version the manifest names, the verdict is
``indeterminate`` and the two versions are printed. Reproducing a 0.1 release under 0.3 and
calling the difference a mismatch would blame the data for a code change.

Everything here is offline, stdlib-only, and free of the wall clock: the receipt is byte-identical
across two runs against an unchanged snapshot, so it can itself be archived and compared.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from . import aggregate as aggregate_module
from . import calibrate
from .config import NetworkConfig, configuration_fingerprint
from .dictionary import DATA_SCHEMA_VERSION
from .models import RAW, Observation
from .snapshot import (
    AGGREGATE_FILENAME,
    CORRECTIONS_FILENAME,
    MANIFEST_FILENAME,
    RAW_OBSERVATIONS_FILENAME,
    _swelter_version,
)
from .store import open_store

__all__ = [
    "EXIT_INDETERMINATE",
    "EXIT_NOT_REPRODUCED",
    "EXIT_REPRODUCED",
    "RECEIPT_SCHEMA_VERSION",
    "REQUIRED_CHECKS",
    "VERDICT_INDETERMINATE",
    "VERDICT_MISMATCH",
    "VERDICT_REFUSED",
    "VERDICT_REPRODUCED",
    "Check",
    "Receipt",
    "ReproduceError",
    "render",
    "reproduce",
    "verdict_for",
]

RECEIPT_SCHEMA_VERSION = "swelter.reproduce/1"

#: The reproduction ran and the rebuilt surface is byte-identical to the frozen one.
VERDICT_REPRODUCED = "reproduced"
#: The reproduction ran and the rebuilt surface differs from the frozen one.
VERDICT_MISMATCH = "mismatch"
#: A required input is missing or unusable, so no reproduction was attempted.
VERDICT_REFUSED = "refused"
#: The release does not record enough about itself to attempt a reproduction at all.
VERDICT_INDETERMINATE = "indeterminate"

CHECK_OK = "PASS"
CHECK_FAIL = "FAIL"
CHECK_NA = "NOT_APPLICABLE"

#: Every check that must have *run* and passed before a release may be called reproduced.
#: Membership is checked by name, so a check that is skipped is absent rather than passing.
REQUIRED_CHECKS: frozenset[str] = frozenset(
    {
        "manifest",
        "swelter_version",
        "data_schema_version",
        "config_fingerprint",
        "frozen_digests",
        "raw_observations",
        "corrections",
        "frozen_surface",
        "surface_identical",
    }
)

#: Exit statuses. ``reproduced`` is the only zero. ``indeterminate`` gets its own non-zero status
#: rather than sharing zero with success: a caller that gates on ``$? -eq 0`` must not be told
#: that a release nobody could check is a release that checked out.
EXIT_REPRODUCED = 0
EXIT_NOT_REPRODUCED = 1
EXIT_INDETERMINATE = 2

_EXIT_BY_VERDICT = {
    VERDICT_REPRODUCED: EXIT_REPRODUCED,
    VERDICT_MISMATCH: EXIT_NOT_REPRODUCED,
    VERDICT_REFUSED: EXIT_NOT_REPRODUCED,
    VERDICT_INDETERMINATE: EXIT_INDETERMINATE,
}


class ReproduceError(Exception):
    """A snapshot that cannot be read at all — not a verdict about its contents."""


@dataclass(frozen=True)
class Check:
    """One question asked of the release, and whether it could be asked at all."""

    name: str
    status: str
    detail: str

    def to_dict(self) -> dict[str, object]:
        return {"name": self.name, "status": self.status, "detail": self.detail}


@dataclass(frozen=True)
class Receipt:
    """What was reproduced, from what, under which versions, and with what result."""

    verdict: str
    snapshot: str
    release_version: str | None
    recorded: dict[str, object]
    running: dict[str, object]
    checks: tuple[Check, ...]
    surface: dict[str, object]
    reasons: tuple[str, ...]

    @property
    def exit_code(self) -> int:
        return _EXIT_BY_VERDICT[self.verdict]

    def check(self, name: str) -> Check | None:
        return next((c for c in self.checks if c.name == name), None)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": RECEIPT_SCHEMA_VERSION,
            "verdict": self.verdict,
            "snapshot": self.snapshot,
            "release_version": self.release_version,
            "recorded": dict(self.recorded),
            "running": dict(self.running),
            "checks": [c.to_dict() for c in self.checks],
            "counts": {
                CHECK_OK: sum(1 for c in self.checks if c.status == CHECK_OK),
                CHECK_FAIL: sum(1 for c in self.checks if c.status == CHECK_FAIL),
                CHECK_NA: sum(1 for c in self.checks if c.status == CHECK_NA),
            },
            "surface": dict(self.surface),
            "reasons": list(self.reasons),
        }

    def to_json(self) -> bytes:
        """Canonical receipt bytes: sorted keys, two-space indent, one trailing newline."""
        return (json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n").encode("utf-8")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_manifest(snapshot_dir: Path) -> dict[str, Any]:
    path = snapshot_dir / MANIFEST_FILENAME
    try:
        doc = json.loads(path.read_bytes().decode("utf-8"))
    except FileNotFoundError as exc:
        raise ReproduceError(f"{path} not found — this is not a swelter snapshot") from exc
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReproduceError(f"{path} is not readable JSON: {exc}") from exc
    if not isinstance(doc, dict):
        raise ReproduceError(f"{path} is not a JSON object")
    return doc


def _observations_from_export(payload: bytes) -> list[Observation]:
    """Parse ``observations-raw.json`` back into observations, refusing anything ambiguous."""
    try:
        doc = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReproduceError(f"{RAW_OBSERVATIONS_FILENAME} is not readable JSON: {exc}") from exc
    if not isinstance(doc, dict) or not isinstance(doc.get("observations"), list):
        raise ReproduceError(f"{RAW_OBSERVATIONS_FILENAME} has no 'observations' array")
    out: list[Observation] = []
    for index, record in enumerate(doc["observations"]):
        if not isinstance(record, dict):
            raise ReproduceError(f"{RAW_OBSERVATIONS_FILENAME}[{index}] is not an object")
        value = record.get("value")
        if not isinstance(value, int | float) or isinstance(value, bool):
            # `export.to_records` writes null for a non-finite value. A row whose measurement is
            # absent cannot be re-derived from, and averaging around it would put a number on the
            # map that no reading supports.
            raise ReproduceError(
                f"{RAW_OBSERVATIONS_FILENAME}[{index}] has no numeric value "
                f"({value!r}); a reading that was never recorded cannot be reproduced"
            )
        try:
            out.append(
                Observation(
                    node_id=str(record["node_id"]),
                    timestamp=str(record["timestamp"]),
                    parameter=str(record["parameter"]),
                    value=float(value),
                    unit=str(record["unit"]),
                    source=str(record.get("source", "native")),
                    calibration=str(record.get("calibration", RAW)),
                    qc=str(record.get("qc", "ok")),
                    uncertainty=(
                        float(u)
                        if isinstance(u := record.get("uncertainty"), int | float)
                        else None
                    ),
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ReproduceError(
                f"{RAW_OBSERVATIONS_FILENAME}[{index}] is not a usable observation: {exc}"
            ) from exc
    return out


def _rebuild_surface_bytes(
    raw: list[Observation], registry: calibrate.CorrectionRegistry, config: NetworkConfig
) -> bytes:
    """Re-run the pipeline exactly as ``swelter rebuild`` does, through a real store.

    Deliberately not an in-memory shortcut. A cell's value is the *mean* of its members, and a
    mean of floats depends on summation order, so a rebuild that fed the aggregator a list in
    some other order could differ in the last bit and be reported as a mismatch. The store's
    ordering is part of the pipeline, so the reproduction uses it.
    """
    with tempfile.TemporaryDirectory(prefix="swelter-reproduce-") as tmp:
        store_dir = Path(tmp) / "store"
        with open_store(store_dir) as store:
            store.write(raw)
            calibrated = [o for o in calibrate.apply(raw, registry) if o.calibration != RAW]
            store.write(calibrated)
            surface = aggregate_module.aggregate(store.all(), config)
    return json.dumps(surface.snapshot_geojson(), indent=2).encode("utf-8")


def first_difference(frozen: bytes, rebuilt: bytes) -> str | None:
    """The JSON path of the first place the two surfaces disagree, or ``None`` if they agree.

    Structural, not textual: it names ``features[12].properties.temp_c`` rather than a byte
    offset, because the point of the receipt is to tell an operator *what* moved. Two surfaces
    that differ only in serialisation are reported at the document root as ``$``, which is the
    truthful answer to "which value moved" when none did.
    """
    try:
        left = json.loads(frozen.decode("utf-8"))
        right = json.loads(rebuilt.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return "$"
    path = _walk_difference(left, right, "$")
    if path is None and frozen != rebuilt:
        return "$"
    return path


def _walk_difference(left: object, right: object, path: str) -> str | None:
    if isinstance(left, dict) and isinstance(right, dict):
        for key in sorted(set(left) | set(right)):
            if key not in left or key not in right:
                return f"{path}.{key}"
            found = _walk_difference(left[key], right[key], f"{path}.{key}")
            if found is not None:
                return found
        return None
    if isinstance(left, list) and isinstance(right, list):
        for index in range(min(len(left), len(right))):
            found = _walk_difference(left[index], right[index], f"{path}[{index}]")
            if found is not None:
                return found
        if len(left) != len(right):
            return f"{path}[{min(len(left), len(right))}]"
        return None
    return None if left == right else path


@dataclass(frozen=True)
class _Stage:
    """One phase of the run: the checks it performed, and the reason it stopped, if it did."""

    checks: tuple[Check, ...]
    verdict: str | None = None
    reason: str | None = None


def _check_recorded_identity(
    doc: dict[str, Any], running_swelter: str, running_fingerprint: str
) -> _Stage:
    """Does the release record enough about itself for a reproduction to mean anything?

    Every failure here is *indeterminate* or *refused*, never a mismatch: a release that does not
    say what built it has not been shown to be wrong, and must not be reported as either right or
    rotten.
    """
    checks: list[Check] = []

    recorded_swelter = doc.get("swelter_version")
    if not isinstance(recorded_swelter, str) or not recorded_swelter:
        checks.append(
            Check("swelter_version", CHECK_FAIL, "the manifest does not record a swelter version")
        )
        return _Stage(
            tuple(checks), VERDICT_INDETERMINATE, "not reproducible: version not recorded"
        )
    if recorded_swelter != running_swelter:
        checks.append(
            Check(
                "swelter_version",
                CHECK_FAIL,
                f"built by swelter {recorded_swelter}, running swelter {running_swelter}",
            )
        )
        return _Stage(
            tuple(checks),
            VERDICT_INDETERMINATE,
            f"not reproducible here: this release was built by swelter {recorded_swelter} and "
            f"swelter {running_swelter} is running; cross-version reproduction is reported, "
            "not attempted",
        )
    checks.append(Check("swelter_version", CHECK_OK, f"swelter {recorded_swelter}"))

    recorded_schema = doc.get("data_schema_version")
    if not isinstance(recorded_schema, int) or isinstance(recorded_schema, bool):
        checks.append(
            Check(
                "data_schema_version",
                CHECK_FAIL,
                "the manifest does not record a data-schema version",
            )
        )
        return _Stage(
            tuple(checks),
            VERDICT_INDETERMINATE,
            "not reproducible: data-schema version not recorded",
        )
    if recorded_schema != DATA_SCHEMA_VERSION:
        checks.append(
            Check(
                "data_schema_version",
                CHECK_FAIL,
                f"built at data schema {recorded_schema}, running data schema "
                f"{DATA_SCHEMA_VERSION}",
            )
        )
        return _Stage(
            tuple(checks),
            VERDICT_INDETERMINATE,
            f"not reproducible here: this release was built at data-schema version "
            f"{recorded_schema} and version {DATA_SCHEMA_VERSION} is running",
        )
    checks.append(Check("data_schema_version", CHECK_OK, f"data schema {recorded_schema}"))

    recorded_fingerprint = doc.get("config_fingerprint")
    if not isinstance(recorded_fingerprint, str) or not recorded_fingerprint:
        checks.append(
            Check(
                "config_fingerprint",
                CHECK_FAIL,
                "the manifest does not record a network-configuration fingerprint",
            )
        )
        return _Stage(
            tuple(checks),
            VERDICT_INDETERMINATE,
            "not reproducible: network configuration not recorded",
        )
    if recorded_fingerprint != running_fingerprint:
        checks.append(
            Check(
                "config_fingerprint",
                CHECK_FAIL,
                f"recorded {recorded_fingerprint[:12]}\u2026, "
                f"supplied {running_fingerprint[:12]}\u2026",
            )
        )
        return _Stage(
            tuple(checks),
            VERDICT_REFUSED,
            "the network configuration supplied is not the one this release was built with; "
            "rebuilding against a different configuration would report a configuration change "
            "as data rot",
        )
    checks.append(
        Check("config_fingerprint", CHECK_OK, f"{recorded_fingerprint[:12]}\u2026 matches")
    )
    return _Stage(tuple(checks))


def _check_frozen_digests(directory: Path, doc: dict[str, Any]) -> Check:
    """Recompute every file the manifest lists and compare it to the digest recorded there.

    Deliberately *not* an early refusal. The reproduction still runs on an altered snapshot,
    because "which value moved" is the question an operator actually has, and answering it needs
    the rebuild. The two findings then compose: a digest failure alone says the frozen bytes were
    edited; a digest failure with a surface difference says which cell that edit reached.

    A manifest with no file entries is a failure, not a vacuous pass: a digest check that covered
    nothing would report clean over a snapshot whose every file had been replaced.
    """
    entries = doc.get("files")
    if not isinstance(entries, list) or not entries:
        return Check("frozen_digests", CHECK_FAIL, "the manifest lists no files to check")
    problems: list[str] = []
    checked = 0
    for entry in entries:
        if not isinstance(entry, dict):
            problems.append("malformed file entry")
            continue
        name, recorded = entry.get("name"), entry.get("sha256")
        if not isinstance(name, str) or not isinstance(recorded, str):
            problems.append("file entry with no name or digest")
            continue
        try:
            actual = _sha256_bytes((directory / name).read_bytes())
        except OSError:
            problems.append(f"{name} is missing")
            continue
        checked += 1
        if actual != recorded:
            problems.append(f"{name} differs from its recorded digest")
    if problems:
        return Check("frozen_digests", CHECK_FAIL, "; ".join(sorted(problems)))
    return Check("frozen_digests", CHECK_OK, f"{checked} file(s) match their recorded digests")


@dataclass(frozen=True)
class _FrozenInputs:
    raw: tuple[Observation, ...]
    registry: calibrate.CorrectionRegistry
    surface_bytes: bytes


def _load_frozen_inputs(directory: Path) -> tuple[_Stage, _FrozenInputs | None]:
    """Read the three frozen inputs a rebuild needs, refusing by name when one is unusable."""
    checks: list[Check] = []

    raw_path = directory / RAW_OBSERVATIONS_FILENAME
    try:
        raw = _observations_from_export(raw_path.read_bytes())
    except FileNotFoundError:
        checks.append(
            Check("raw_observations", CHECK_FAIL, f"{RAW_OBSERVATIONS_FILENAME} is missing")
        )
        return (
            _Stage(
                tuple(checks),
                VERDICT_REFUSED,
                f"{RAW_OBSERVATIONS_FILENAME} is missing; there is nothing to rebuild from",
            ),
            None,
        )
    except (OSError, ReproduceError) as exc:
        checks.append(Check("raw_observations", CHECK_FAIL, str(exc)))
        return _Stage(tuple(checks), VERDICT_REFUSED, str(exc)), None
    if not raw:
        checks.append(Check("raw_observations", CHECK_FAIL, "the release freezes no observations"))
        return (
            _Stage(
                tuple(checks),
                VERDICT_REFUSED,
                "this release freezes no observations; an empty rebuild matches an empty surface "
                "and would prove nothing",
            ),
            None,
        )
    checks.append(Check("raw_observations", CHECK_OK, f"{len(raw)} raw observations"))

    corrections_path = directory / CORRECTIONS_FILENAME
    if not corrections_path.is_file():
        checks.append(Check("corrections", CHECK_FAIL, f"{CORRECTIONS_FILENAME} is missing"))
        return (
            _Stage(
                tuple(checks),
                VERDICT_REFUSED,
                f"{CORRECTIONS_FILENAME} is missing; a surface cannot be re-derived without the "
                "corrections that produced it",
            ),
            None,
        )
    try:
        registry = calibrate.CorrectionRegistry.from_yaml(corrections_path)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        checks.append(
            Check("corrections", CHECK_FAIL, f"{CORRECTIONS_FILENAME} is unusable: {exc}")
        )
        return (
            _Stage(
                tuple(checks),
                VERDICT_REFUSED,
                f"{CORRECTIONS_FILENAME} is unusable: {exc}",
            ),
            None,
        )
    checks.append(Check("corrections", CHECK_OK, f"{len(registry)} correction(s)"))

    frozen_path = directory / AGGREGATE_FILENAME
    try:
        frozen_bytes = frozen_path.read_bytes()
    except OSError:
        checks.append(Check("frozen_surface", CHECK_FAIL, f"{AGGREGATE_FILENAME} is missing"))
        return (
            _Stage(
                tuple(checks),
                VERDICT_REFUSED,
                f"{AGGREGATE_FILENAME} is missing; this release holds no surface to reproduce",
            ),
            None,
        )
    checks.append(Check("frozen_surface", CHECK_OK, f"{len(frozen_bytes)} bytes"))
    return _Stage(tuple(checks)), _FrozenInputs(tuple(raw), registry, frozen_bytes)


def verdict_for(checks: Sequence[Check]) -> tuple[str, list[str]]:
    """The verdict, built from the required checks having RUN and passed.

    Never from the absence of a failure. A check that never ran cannot fail, so a verdict counted
    from failures would call a reproduction that silently skipped a step a success — which is the
    shape of gate this verb exists to refuse. Separated from :func:`reproduce` so the
    did-not-run branch is reachable from a test rather than being decoration that no case
    exercises.
    """
    reasons: list[str] = []
    passed = {c.name for c in checks if c.status == CHECK_OK}
    failed = sorted({c.name for c in checks if c.status == CHECK_FAIL} & REQUIRED_CHECKS)
    # Everything required that did not affirmatively pass and did not affirmatively fail: it
    # never ran, or it ran and reported NOT_APPLICABLE. Both are absences, and neither is
    # evidence. Counted apart from `failed` so "there was nothing to compare" can never be
    # folded into "the comparison came out clean".
    inconclusive = sorted((REQUIRED_CHECKS - passed) - set(failed))
    if inconclusive:
        reasons.append(f"required check(s) neither ran nor passed: {', '.join(inconclusive)}")
        return VERDICT_INDETERMINATE, reasons
    if failed:
        if "frozen_digests" in failed:
            reasons.append(
                "the frozen files do not match the digests the manifest recorded for them"
            )
        return VERDICT_MISMATCH, reasons
    return VERDICT_REPRODUCED, reasons


_EMPTY_SURFACE: dict[str, object] = {
    "frozen_sha256": None,
    "rebuilt_sha256": None,
    "frozen_features": None,
    "rebuilt_features": None,
    "first_difference": None,
}


def reproduce(
    snapshot_dir: Path | str,
    config: NetworkConfig,
    *,
    config_path: str | None = None,
    running_version: str | None = None,
) -> Receipt:
    """Rebuild ``snapshot_dir``'s surface from its frozen inputs and report what happened."""
    directory = Path(snapshot_dir)
    doc = _read_manifest(directory)

    running_swelter = running_version if running_version is not None else _swelter_version()
    running_fingerprint = configuration_fingerprint(config)
    release_version = (
        doc.get("release_version") if isinstance(doc.get("release_version"), str) else None
    )
    recorded: dict[str, object] = {
        "swelter_version": doc.get("swelter_version"),
        "data_schema_version": doc.get("data_schema_version"),
        "config_fingerprint": doc.get("config_fingerprint"),
    }
    running: dict[str, object] = {
        "swelter_version": running_swelter,
        "data_schema_version": DATA_SCHEMA_VERSION,
        "config_fingerprint": running_fingerprint,
        "config_path": config_path,
    }
    checks: list[Check] = [Check("manifest", CHECK_OK, f"{MANIFEST_FILENAME} parsed")]

    def stop(stage: _Stage) -> Receipt:
        reason = stage.reason
        return Receipt(
            verdict=stage.verdict or VERDICT_REFUSED,
            snapshot=str(directory),
            release_version=release_version,
            recorded=recorded,
            running=running,
            checks=tuple(checks),
            surface=dict(_EMPTY_SURFACE),
            reasons=(reason,) if reason else (),
        )

    identity = _check_recorded_identity(doc, running_swelter, running_fingerprint)
    checks.extend(identity.checks)
    if identity.verdict is not None:
        return stop(identity)

    checks.append(_check_frozen_digests(directory, doc))

    inputs_stage, inputs = _load_frozen_inputs(directory)
    checks.extend(inputs_stage.checks)
    if inputs is None:
        return stop(inputs_stage)

    rebuilt_bytes = _rebuild_surface_bytes(list(inputs.raw), inputs.registry, config)
    frozen_bytes = inputs.surface_bytes
    surface: dict[str, object] = {
        "frozen_sha256": _sha256_bytes(frozen_bytes),
        "rebuilt_sha256": _sha256_bytes(rebuilt_bytes),
        "frozen_features": _feature_count(frozen_bytes),
        "rebuilt_features": _feature_count(rebuilt_bytes),
        "first_difference": None,
    }
    reasons: list[str] = []
    if frozen_bytes == rebuilt_bytes:
        checks.append(Check("surface_identical", CHECK_OK, "rebuilt surface is byte-identical"))
    else:
        difference = first_difference(frozen_bytes, rebuilt_bytes)
        surface["first_difference"] = difference
        checks.append(Check("surface_identical", CHECK_FAIL, f"first difference at {difference}"))
        reasons.append(f"the rebuilt surface differs from the frozen one, first at {difference}")

    verdict, verdict_reasons = verdict_for(checks)
    reasons.extend(verdict_reasons)

    return Receipt(
        verdict=verdict,
        snapshot=str(directory),
        release_version=release_version,
        recorded=recorded,
        running=running,
        checks=tuple(checks),
        surface=surface,
        reasons=tuple(reasons),
    )


def _feature_count(payload: bytes) -> int | None:
    try:
        doc = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    features = doc.get("features") if isinstance(doc, dict) else None
    return len(features) if isinstance(features, list) else None


_VERDICT_HEADLINE = {
    VERDICT_REPRODUCED: "reproduced — the frozen surface re-derives byte-for-byte from its inputs",
    VERDICT_MISMATCH: "NOT reproduced — the rebuilt surface differs from the frozen one",
    VERDICT_REFUSED: "NOT reproduced — a required input is missing or does not belong to it",
    VERDICT_INDETERMINATE: "INDETERMINATE — this release cannot be checked, which is not a pass",
}


def render(receipt: Receipt) -> list[str]:
    """The human-readable receipt, one line at a time."""
    lines = [
        f"swelter reproduce: {receipt.snapshot}",
        f"  verdict: {_VERDICT_HEADLINE[receipt.verdict]}",
    ]
    if receipt.release_version:
        lines.append(f"  release: {receipt.release_version}")
    for check in receipt.checks:
        lines.append(f"  [{check.status}] {check.name}: {check.detail}")
    statuses = [c.status for c in receipt.checks]
    lines.append(
        f"  checks: {statuses.count(CHECK_OK)} passed, {statuses.count(CHECK_FAIL)} failed, "
        f"{statuses.count(CHECK_NA)} not applicable"
    )
    for reason in receipt.reasons:
        lines.append(f"  ⚠ {reason}")
    return lines
