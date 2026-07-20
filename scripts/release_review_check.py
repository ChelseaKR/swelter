#!/usr/bin/env python3
"""Validate human release attestations and bind them to the exact reviewed source tree."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MANIFEST = ROOT / "docs" / "audits" / "release-review-attestations.json"
REQUIRED_ATTESTATIONS = frozenset(
    {
        "ethics",
        "fairness",
        "privacy",
        "transparency",
        "security",
        "accessibility",
        "spanish-language",
        "owner-release",
    }
)
_SHA256 = re.compile(r"[0-9a-f]{64}")
_VERSION = re.compile(r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)")
_NON_HUMAN = re.compile(r"\b(?:ai|automated|chatgpt|claude|codex|copilot|openai)\b", re.IGNORECASE)


def source_digest(root: Path = ROOT, manifest: Path = DEFAULT_MANIFEST) -> str:
    """Hash every Git-visible source path except the self-referential review manifest."""
    git = shutil.which("git")
    if git is None:
        raise RuntimeError("release-review source binding requires git on PATH")
    result = subprocess.run(  # noqa: S603 (#107)
        [git, "-C", str(root), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        check=True,
        capture_output=True,
    )
    excluded = manifest.resolve()
    digest = hashlib.sha256()
    names = sorted(name for name in result.stdout.split(b"\0") if name)
    for encoded in names:
        relative = Path(encoded.decode("utf-8"))
        path = (root / relative).resolve()
        if path == excluded or not path.is_file():
            continue
        payload = path.read_bytes()
        digest.update(encoded)
        digest.update(b"\0")
        digest.update(str(len(payload)).encode("ascii"))
        digest.update(b"\0")
        digest.update(payload)
        digest.update(b"\0")
    return digest.hexdigest()


def _load(path: Path) -> tuple[dict[str, object] | None, list[str]]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, [f"cannot read release-review manifest: {exc}"]
    if not isinstance(document, dict):
        return None, ["release-review manifest root is not an object"]
    return document, []


def _date_problem(value: object, label: str) -> str | None:
    if not isinstance(value, str):
        return f"{label} is not an ISO calendar date"
    try:
        date.fromisoformat(value)
    except ValueError:
        return f"{label} is not an ISO calendar date"
    return None


def _artifact_problems(item: dict[str, object], label: str, root: Path) -> list[str]:
    artifact = item.get("artifact")
    if not isinstance(artifact, str) or not artifact:
        return [f"{label}.artifact is missing"]
    path = (root / artifact).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError:
        return [f"{label}.artifact escapes the repository"]
    if not path.is_file():
        return [f"{label}.artifact does not exist: {artifact}"]
    return []


def _completed_review_problems(
    item: dict[str, object], label: str, identifier: str | None
) -> list[str]:
    problems: list[str] = []
    reviewer = item.get("reviewer")
    if not isinstance(reviewer, str) or not reviewer.strip() or _NON_HUMAN.search(reviewer):
        problems.append(f"{label}.reviewer must name a human reviewer")
    problem = _date_problem(item.get("reviewed"), f"{label}.reviewed")
    if problem:
        problems.append(problem)
    notes = item.get("notes")
    if not isinstance(notes, str) or len(notes.strip()) < 12:
        problems.append(f"{label}.notes must record the reviewed tasks and disposition")
    if identifier in {"spanish-language", "accessibility"} and item.get("independent") is not True:
        problems.append(f"{label} must record independent=true")
    return problems


def _attestation_problems(
    item: object, *, index: int, root: Path, require_complete: bool
) -> tuple[str | None, list[str]]:
    label = f"attestations[{index}]"
    if not isinstance(item, dict):
        return None, [f"{label} is not an object"]
    problems = _artifact_problems(item, label, root)
    identifier = item.get("id")
    if not isinstance(identifier, str) or identifier not in REQUIRED_ATTESTATIONS:
        problems.append(f"{label}.id is not a required review id")
        identifier = None
    outcome = item.get("outcome")
    if outcome not in {"pending", "pass"}:
        problems.append(f"{label}.outcome must be pending or pass")
    elif outcome == "pending":
        if item.get("reviewer") is not None or item.get("reviewed") is not None:
            problems.append(f"{label} pending review cannot name a reviewer/date")
        if require_complete:
            problems.append(f"{label} is still pending")
    else:
        problems.extend(_completed_review_problems(item, label, identifier))
    return identifier, problems


def _header_problems(document: dict[str, object], expected_version: str | None) -> list[str]:
    problems: list[str] = []
    if document.get("schema_version") != 1:
        problems.append("release-review schema_version must be 1")
    version = document.get("release_version")
    if not isinstance(version, str) or not _VERSION.fullmatch(version):
        problems.append("release-review release_version is not SemVer")
    elif expected_version is not None and version != expected_version:
        problems.append(f"release-review version {version} does not equal {expected_version}")
    issue = document.get("tracking_issue")
    if issue is not None and (not isinstance(issue, int) or issue < 1):
        problems.append("release-review tracking_issue must be null or a positive issue number")
    return problems


def _digest_problems(
    document: dict[str, object], *, path: Path, root: Path, require_complete: bool
) -> list[str]:
    recorded = document.get("reviewed_source_sha256")
    if recorded is not None and (not isinstance(recorded, str) or not _SHA256.fullmatch(recorded)):
        return ["reviewed_source_sha256 must be null or a lowercase SHA-256"]
    if not require_complete:
        return []
    if not isinstance(recorded, str) or not _SHA256.fullmatch(recorded):
        return ["completed release review has no source digest"]
    if recorded != source_digest(root, path):
        return ["reviewed source digest is stale"]
    return []


def validate_manifest(
    path: Path = DEFAULT_MANIFEST,
    *,
    root: Path = ROOT,
    expected_version: str | None = None,
    require_complete: bool = False,
) -> list[str]:
    """Return schema, human-review, and source-binding findings."""
    document, problems = _load(path)
    if document is None:
        return problems
    problems.extend(_header_problems(document, expected_version))

    items = document.get("attestations")
    if not isinstance(items, list):
        return [*problems, "release-review attestations is not an array"]
    seen: list[str] = []
    for index, item in enumerate(items):
        identifier, item_problems = _attestation_problems(
            item, index=index, root=root, require_complete=require_complete
        )
        if identifier is not None:
            seen.append(identifier)
        problems.extend(item_problems)
    if set(seen) != REQUIRED_ATTESTATIONS or len(seen) != len(REQUIRED_ATTESTATIONS):
        problems.append("release-review attestations must contain each required id exactly once")
    problems.extend(
        _digest_problems(document, path=path, root=root, require_complete=require_complete)
    )
    return problems


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    digest = subparsers.add_parser("digest")
    digest.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    validate = subparsers.add_parser("validate")
    validate.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    validate.add_argument("--version")
    validate.add_argument("--require-complete", action="store_true")
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.command == "digest":
        print(source_digest(ROOT, args.manifest))
        return 0
    problems = validate_manifest(
        args.manifest,
        expected_version=args.version,
        require_complete=args.require_complete,
    )
    if problems:
        print(f"release-review: FAIL ({len(problems)} problem(s))", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    state = "complete and source-bound" if args.require_complete else "schema-valid"
    print(f"release-review: {state}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
