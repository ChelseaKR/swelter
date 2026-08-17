#!/usr/bin/env python3
"""Enforce immutable, human-auditable GitHub Actions workflow dependencies."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = ROOT / ".github" / "workflows"
#: Both suffixes GitHub Actions accepts for a workflow definition. This gate used to glob `*.yml`
#: alone, so a workflow committed as `.yaml` was invisible to it: unpinned actions, `|| true`,
#: `continue-on-error: true`, a missing `permissions:` block and a credential-persisting checkout
#: all passed, while the gate still printed that *every* action is SHA-pinned and fail-closed. A
#: gate that makes a claim about a set has to enumerate the whole set.
WORKFLOW_SUFFIXES = ("*.yml", "*.yaml")
_USES = re.compile(r"^\s*(?:-\s*)?uses:\s*([^\s@]+)@([^\s#]+)(?:\s+#\s*(\S+))?\s*$")
_SHA = re.compile(r"^[0-9a-f]{40}$")
_SEMVER = re.compile(r"^v\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$")
# Governance exception #105 preserves the existing Pages cache step byte-for-byte. The exemption
# is deliberately bound to its workflow, action, immutable SHA, and legacy major-version comment.
_PROTECTED_VERSION_ANNOTATIONS = {
    (
        "pages.yml",
        "actions/cache",
        "0057852bfaa89a56745cba8c7296529d2fc39830",
        "v4",
    ): "v4.3.0",
}


def scan_workflow(path: Path) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    problems: list[str] = []
    if not any(line.startswith("permissions:") for line in lines):
        problems.append("has no top-level permissions declaration")
    for index, line in enumerate(lines, start=1):
        match = _USES.match(line)
        if match:
            action, reference, comment = match.groups()
            if not _SHA.fullmatch(reference):
                problems.append(f"line {index}: {action} is not pinned to a 40-character SHA")
            protected_version = _PROTECTED_VERSION_ANNOTATIONS.get(
                (path.name, action, reference, comment or "")
            )
            protected_annotation = f"{action}@{reference} # {protected_version}"
            version_is_documented = (comment is not None and bool(_SEMVER.fullmatch(comment))) or (
                protected_version is not None
                and any(protected_annotation in candidate for candidate in lines)
            )
            if not version_is_documented:
                problems.append(f"line {index}: {action} has no exact trailing semver comment")
            if action == "actions/checkout":
                following = "\n".join(lines[index : index + 8])
                if "persist-credentials: false" not in following:
                    problems.append(
                        f"line {index}: checkout does not disable persisted credentials"
                    )
        if "continue-on-error: true" in line:
            problems.append(f"line {index}: continue-on-error weakens an automatic gate")
        if "|| true" in line:
            problems.append(f"line {index}: error-suppressing '|| true' is prohibited")
    return problems


def workflow_files(directory: Path = WORKFLOWS) -> list[Path]:
    """Every workflow definition GitHub would run, in a stable order."""
    return sorted(path for suffix in WORKFLOW_SUFFIXES for path in directory.glob(suffix))


def _display(path: Path) -> str:
    """Repository-relative where possible; the full path when the scan root is elsewhere."""
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def main() -> int:
    paths = workflow_files(WORKFLOWS)
    if not paths:
        # Scanning nothing is not the same as finding nothing wrong. This gate's output is a
        # universal claim, and it must not make one about an empty set.
        print(f"  [FAIL] no workflow definitions found under {WORKFLOWS}")
        print("workflow-policy: the gate scanned nothing, so it proved nothing", file=sys.stderr)
        return 1
    findings: list[str] = []
    for path in paths:
        findings.extend(f"{_display(path)}: {problem}" for problem in scan_workflow(path))
    if findings:
        for finding in findings:
            print(f"  [FAIL] {finding}")
        return 1
    print(
        f"workflow-policy: all {len(paths)} workflow(s) are SHA-pinned, exact-versioned, "
        "and fail-closed"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
