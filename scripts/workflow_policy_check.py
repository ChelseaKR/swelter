#!/usr/bin/env python3
"""Enforce immutable, human-auditable GitHub Actions workflow dependencies."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = ROOT / ".github" / "workflows"
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


def main() -> int:
    findings: list[str] = []
    for path in sorted(WORKFLOWS.glob("*.yml")):
        findings.extend(f"{path.relative_to(ROOT)}: {problem}" for problem in scan_workflow(path))
    if findings:
        for finding in findings:
            print(f"  [FAIL] {finding}")
        return 1
    print("workflow-policy: every Action is SHA-pinned, exact-versioned, and fail-closed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
