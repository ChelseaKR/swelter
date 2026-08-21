#!/usr/bin/env python3
"""Report mutation results and bind a dated baseline to its exact inputs."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import tomllib
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
MUTMUT_VERSION = "3.7.0"
DEFAULT_MODULES = ("calibrate", "models", "qc")
SOURCE_FILES = tuple(Path("src/swelter") / f"{module}.py" for module in DEFAULT_MODULES)
TEST_FILES = (
    Path("tests/test_calibrate.py"),
    Path("tests/test_calibrate_branches.py"),
    Path("tests/test_models.py"),
    Path("tests/test_qc.py"),
)
STATUS_BY_EXIT_CODE: dict[int | None, str] = {
    None: "not_checked",
    0: "survived",
    1: "killed",
    2: "interrupted",
    3: "killed",
    5: "no_tests",
    24: "timeout",
    33: "no_tests",
    34: "skipped",
    35: "suspicious",
    36: "timeout",
    37: "type_error",
    152: "timeout",
    255: "timeout",
    -9: "segfault",
    -11: "segfault",
    -24: "timeout",
}
INCOMPLETE_STATUSES = frozenset(
    {"interrupted", "not_checked", "segfault", "skipped", "timeout", "type_error", "unknown"}
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def sha256_path(path: Path) -> str:
    """Return a streaming SHA-256 digest."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def collect(mutants: Path, modules: tuple[str, ...]) -> tuple[Counter[str], list[dict[str, str]]]:
    """Collect mutmut statuses without treating timeouts or skips as kills."""
    counts: Counter[str] = Counter()
    non_killed: list[dict[str, str]] = []
    for module in modules:
        metadata = mutants / "src" / "swelter" / f"{module}.py.meta"
        if not metadata.is_file():
            raise FileNotFoundError(f"mutmut metadata missing for {module}: {metadata}")
        document = json.loads(metadata.read_text(encoding="utf-8"))
        results = document.get("exit_code_by_key")
        if not isinstance(results, dict) or not results:
            raise ValueError(f"{metadata} has no non-empty exit_code_by_key object")
        for mutant, exit_code in results.items():
            if exit_code is not None and not isinstance(exit_code, int):
                raise ValueError(f"{metadata}: invalid exit code for {mutant}")
            status = STATUS_BY_EXIT_CODE.get(exit_code, "unknown")
            counts[status] += 1
            if status != "killed":
                non_killed.append({"id": str(mutant), "status": status})
    return counts, sorted(non_killed, key=lambda item: item["id"])


def mutation_score(counts: Counter[str]) -> float:
    """Return killed / all generated mutants; only actual kills enter the numerator."""
    total = sum(counts.values())
    return 100.0 * counts["killed"] / total if total else 0.0


def incomplete_statuses(counts: Counter[str]) -> list[str]:
    """Return execution states that make a mutation result non-final."""
    return sorted(status for status in INCOMPLETE_STATUSES if counts[status])


def report(
    counts: Counter[str], non_killed: list[dict[str, str]], modules: tuple[str, ...]
) -> dict[str, object]:
    incomplete = incomplete_statuses(counts)
    return {
        "schema_version": 2,
        "tool": {"name": "mutmut", "version": MUTMUT_VERSION},
        "modules": list(modules),
        "score": round(mutation_score(counts), 2),
        "score_definition": "killed / all generated mutants",
        "complete": not incomplete,
        "incomplete_statuses": incomplete,
        "counts": dict(sorted(counts.items())),
        "non_killed_mutants": non_killed,
    }


def markdown(document: dict[str, object], threshold: float) -> str:
    counts = document["counts"]
    non_killed = document["non_killed_mutants"]
    score = document["score"]
    complete = document["complete"]
    if not isinstance(counts, dict) or not isinstance(non_killed, list):
        raise ValueError("mutation report has invalid counts or non_killed_mutants")
    if not isinstance(score, int | float) or not isinstance(complete, bool):
        raise ValueError("mutation report has an invalid score or completeness state")
    lines = [
        "# Core safety mutation report",
        "",
        f"Mutation score: **{score:.2f}%** (required: **{threshold:.2f}%**).",
        "",
        "The score is killed mutants divided by every generated mutant. Timeouts, skipped or",
        "unchecked mutants never count as killed, and any incomplete state fails the gate.",
        "",
        f"Execution complete: **{'yes' if complete else 'no'}**.",
        "",
        "| Status | Count |",
        "|---|---:|",
    ]
    lines.extend(f"| {status} | {count} |" for status, count in sorted(counts.items()))
    lines.extend(["", "## Non-killed mutants", ""])
    for item in non_killed:
        if not isinstance(item, dict):
            raise ValueError("mutation report contains an invalid non-killed mutant")
        lines.append(f"- `{item.get('id')}` — {item.get('status')}")
    if not non_killed:
        lines.append("None.")
    return "\n".join(lines) + "\n"


def _canonical_sha256(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def _project_configuration(root: Path) -> dict[str, Any]:
    with (root / "pyproject.toml").open("rb") as handle:
        document = tomllib.load(handle)
    configuration = document.get("tool", {}).get("mutmut")
    if not isinstance(configuration, dict):
        raise ValueError("pyproject.toml has no [tool.mutmut] table")
    return configuration


def _locked_tool(root: Path) -> dict[str, Any]:
    with (root / "uv.lock").open("rb") as handle:
        document = tomllib.load(handle)
    packages = document.get("package")
    if not isinstance(packages, list):
        raise ValueError("uv.lock has no package array")
    matches = [package for package in packages if package.get("name") == "mutmut"]
    if len(matches) != 1 or matches[0].get("version") != MUTMUT_VERSION:
        raise ValueError(f"uv.lock must contain exactly mutmut {MUTMUT_VERSION}")
    package = matches[0]
    locked = {
        "name": package.get("name"),
        "version": package.get("version"),
        "source": package.get("source"),
        "sdist": package.get("sdist"),
        "wheels": package.get("wheels"),
    }
    artifact_hashes = [
        artifact.get("hash", "").removeprefix("sha256:")
        for artifact in [locked.get("sdist"), *(locked.get("wheels") or [])]
        if isinstance(artifact, dict)
    ]
    if not artifact_hashes or any(not _SHA256.fullmatch(value) for value in artifact_hashes):
        raise ValueError("mutmut lock entry has missing or invalid artifact hashes")
    return locked


def _file_hashes(root: Path, paths: tuple[Path, ...]) -> dict[str, str]:
    result: dict[str, str] = {}
    for relative in paths:
        path = root / relative
        if not path.is_file():
            raise FileNotFoundError(path)
        result[relative.as_posix()] = sha256_path(path)
    return result


def build_baseline(
    result: dict[str, object], evidence_date: str, threshold: float, root: Path = ROOT
) -> dict[str, object]:
    """Bind a mutation result to the exact source, tests, config, and locked tool."""
    date.fromisoformat(evidence_date)
    if result.get("schema_version") != 2 or result.get("modules") != list(DEFAULT_MODULES):
        raise ValueError("mutation report does not cover the configured core modules")
    tool = result.get("tool")
    if tool != {"name": "mutmut", "version": MUTMUT_VERSION}:
        raise ValueError(f"mutation report was not produced by mutmut {MUTMUT_VERSION}")
    return {
        "schema_version": 1,
        "evidence_date": evidence_date,
        "minimum_score": threshold,
        "source_sha256": _file_hashes(root, SOURCE_FILES),
        "tests_sha256": _file_hashes(root, TEST_FILES),
        "configuration_sha256": _canonical_sha256(_project_configuration(root)),
        "tool_lock_sha256": _canonical_sha256(_locked_tool(root)),
        "result": result,
    }


def _baseline_header_findings(document: dict[str, object]) -> list[str]:
    findings: list[str] = []
    if document.get("schema_version") != 1:
        findings.append("baseline schema_version must be 1")
    try:
        evidence_date = document.get("evidence_date")
        if not isinstance(evidence_date, str):
            raise ValueError
        date.fromisoformat(evidence_date)
    except ValueError:
        findings.append("evidence_date must be an ISO calendar date")
    threshold = document.get("minimum_score")
    if not isinstance(threshold, int | float) or not 0 <= threshold <= 100:
        findings.append("minimum_score must be between 0 and 100")
    return findings


def _baseline_input_findings(document: dict[str, object], root: Path) -> list[str]:
    findings: list[str] = []
    expected_fields: dict[str, object] = {}
    try:
        expected_fields = {
            "source_sha256": _file_hashes(root, SOURCE_FILES),
            "tests_sha256": _file_hashes(root, TEST_FILES),
            "configuration_sha256": _canonical_sha256(_project_configuration(root)),
            "tool_lock_sha256": _canonical_sha256(_locked_tool(root)),
        }
    except (FileNotFoundError, OSError, TypeError, ValueError, tomllib.TOMLDecodeError) as exc:
        findings.append(f"cannot calculate current mutation inputs: {exc}")
    for field, expected in expected_fields.items():
        if document.get(field) != expected:
            findings.append(f"{field} is stale")
    return findings


def _mutation_count_findings(result: dict[str, object]) -> list[str]:
    findings: list[str] = []
    counts = result.get("counts")
    if not isinstance(counts, dict) or any(
        not isinstance(status, str) or not isinstance(count, int) or count < 0
        for status, count in counts.items()
    ):
        return ["result has invalid mutation counts"]
    total = sum(counts.values())
    if total == 0:
        return ["result has no generated mutants"]
    expected_score = round(100.0 * counts.get("killed", 0) / total, 2)
    if result.get("score") != expected_score:
        findings.append("result score is inconsistent with killed / all generated mutants")
    non_killed = result.get("non_killed_mutants")
    if not isinstance(non_killed, list) or len(non_killed) != total - counts.get("killed", 0):
        findings.append("result non-killed mutant inventory is incomplete")
    expected_incomplete = sorted(status for status in INCOMPLETE_STATUSES if counts.get(status, 0))
    if result.get("incomplete_statuses") != expected_incomplete:
        findings.append("result incomplete-status inventory is inconsistent")
    return findings


def _baseline_result_findings(document: dict[str, object]) -> list[str]:
    findings: list[str] = []
    threshold = document.get("minimum_score")
    result = document.get("result")
    if not isinstance(result, dict):
        return ["result is missing"]
    if result.get("tool") != {"name": "mutmut", "version": MUTMUT_VERSION}:
        findings.append(f"result tool must be mutmut {MUTMUT_VERSION}")
    if result.get("modules") != list(DEFAULT_MODULES):
        findings.append("result modules do not match the configured core modules")
    if result.get("score_definition") != "killed / all generated mutants":
        findings.append("result uses an unsupported mutation-score definition")
    if result.get("complete") is not True or result.get("incomplete_statuses") != []:
        findings.append("result contains incomplete mutation states")
    score = result.get("score")
    if isinstance(threshold, int | float) and (
        not isinstance(score, int | float) or score < threshold
    ):
        findings.append("result is below the committed minimum score")
    findings.extend(_mutation_count_findings(result))
    return findings


def verify_baseline(document: object, root: Path = ROOT) -> list[str]:
    """Return findings when a committed mutation baseline is stale or non-passing."""
    if not isinstance(document, dict):
        return ["baseline root is not an object"]
    return [
        *_baseline_header_findings(document),
        *_baseline_input_findings(document, root),
        *_baseline_result_findings(document),
    ]


def baseline_markdown(document: dict[str, object]) -> str:
    result = document.get("result")
    if not isinstance(result, dict):
        raise ValueError("baseline has no result")
    score = result.get("score")
    threshold = document.get("minimum_score")
    counts = result.get("counts")
    if not isinstance(score, int | float) or not isinstance(threshold, int | float):
        raise ValueError("baseline has no numeric score or threshold")
    if not isinstance(counts, dict):
        raise ValueError("baseline has no counts")
    lines = [
        "# Core safety mutation baseline",
        "",
        f"Evidence date: {document.get('evidence_date')}.",
        f"Tool: mutmut {MUTMUT_VERSION} (exactly locked in `uv.lock`).",
        "",
        f"Score: **{score:.2f}%** killed / all generated mutants; floor: **{threshold:.2f}%**.",
        "",
        "| Status | Count |",
        "|---|---:|",
    ]
    lines.extend(f"| {status} | {count} |" for status, count in sorted(counts.items()))
    lines.extend(
        [
            "",
            "The JSON evidence beside this file binds the result to SHA-256 hashes of every",
            "mutated source file and selected test, the canonical mutmut configuration, and the",
            "exact mutmut lock entry. `make mutation-baseline-check` fails when any input changes.",
        ]
    )
    return "\n".join(lines) + "\n"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    summarize = subparsers.add_parser("report")
    summarize.add_argument("--mutants", type=Path, default=Path("mutants"))
    summarize.add_argument("--module", action="append", dest="modules")
    summarize.add_argument("--json", type=Path, required=True)
    summarize.add_argument("--markdown", type=Path, required=True)
    summarize.add_argument("--minimum-score", type=float, default=80.0)
    baseline = subparsers.add_parser("baseline")
    baseline.add_argument("--report", type=Path, required=True)
    baseline.add_argument("--evidence-date", required=True)
    baseline.add_argument("--json", type=Path, required=True)
    baseline.add_argument("--markdown", type=Path, required=True)
    baseline.add_argument("--minimum-score", type=float, default=80.0)
    verify = subparsers.add_parser("verify-baseline")
    verify.add_argument("--baseline", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "report":
        modules = tuple(args.modules or DEFAULT_MODULES)
        counts, non_killed = collect(args.mutants, modules)
        document = report(counts, non_killed, modules)
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        args.markdown.write_text(markdown(document, args.minimum_score), encoding="utf-8")
        score = mutation_score(counts)
        print(f"mutation: {score:.2f}% ({counts['killed']} killed / {sum(counts.values())} total)")
        if incomplete_statuses(counts):
            print("mutation: incomplete states: " + ", ".join(incomplete_statuses(counts)))
            return 1
        return 0 if score >= args.minimum_score else 1
    if args.command == "baseline":
        result = json.loads(args.report.read_text(encoding="utf-8"))
        document = build_baseline(result, args.evidence_date, args.minimum_score)
        findings = verify_baseline(document)
        if findings:
            for finding in findings:
                print(f"  [FAIL] {finding}")
            return 1
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        args.markdown.write_text(baseline_markdown(document), encoding="utf-8")
        print(f"mutation-baseline: wrote passing evidence to {args.json}")
        return 0
    if args.command == "verify-baseline":
        try:
            document = json.loads(args.baseline.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"  [FAIL] cannot read mutation baseline: {exc}")
            return 1
        findings = verify_baseline(document)
        if findings:
            for finding in findings:
                print(f"  [FAIL] {finding}")
            return 1
        print("mutation-baseline: committed evidence is current and passing")
        return 0
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
