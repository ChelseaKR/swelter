#!/usr/bin/env python3
"""Enforce immutable, human-auditable GitHub Actions workflow dependencies."""

from __future__ import annotations

import re
import sys
from collections.abc import Iterable
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
# Governance exception #105 preserves a workflow step byte-for-byte when its comment is a legacy
# major-version rather than an exact semver. Each exemption is bound to its workflow, action,
# immutable SHA, and comment, so it can only ever excuse the one line it names.
#
# The table is empty. It held one entry, for
# ``pages.yml``/``actions/cache``/``0057852bfaa89a56745cba8c7296529d2fc39830``/``v4``, and that
# SHA left every workflow when the action was bumped to
# ``55cc8345863c7cc4c66a329aec7e433d2d1c52a9 # v6.1.0`` -- an exact semver, which needs no
# exemption. The entry stayed. A security exemption whose subject no longer exists is invisible:
# it excuses nothing, it can never be reached, and nothing in the gate said so. So
# ``stale_exemptions`` now checks the table against the workflows on every run: an exemption that
# outlives what it excused is a finding, not a leftover.
_PROTECTED_VERSION_ANNOTATIONS: dict[tuple[str, str, str, str], str] = {}
#: Actions that SHA-pinning does not actually pin. These wrappers select the program that does the
#: work through a `version:` input which defaults to "latest", and then run it from a registry --
#: trufflehog runs `ghcr.io/trufflesecurity/trufflehog:${VERSION}`. So the 40-character SHA and its
#: trailing semver comment describe the wrapper while the scanner, its detector set, and therefore
#: what counts as a finding all float. This gate printed "SHA-pinned, exact-versioned" over exactly
#: that state. It is not hypothetical: the same action in id-churn-sentinel went red on 2026-08-09
#: with no commit on that side, because upstream shipped 3.96.0 and the next scheduled run picked
#: it up -- the same release whose Lob detector began matching pytest function names. A floating
#: scanner can invent findings and can equally stop producing one, with nothing to review either
#: way. For these actions the `version:` input must be present and an exact version.
_SCANNER_VERSION_INPUT_ACTIONS = frozenset({"trufflesecurity/trufflehog"})
#: `version:` is a `with:` input, so it sits below `uses:` with intervening keys and comments.
_SCANNER_VERSION_LOOKAHEAD = 30
_SCANNER_VERSION_INPUT = re.compile(r'^\s*version:\s*["\']?v?\d+\.\d+\.\d+["\']?\s*$')


def _step_input_problems(action: str, index: int, lines: list[str]) -> list[str]:
    """Return findings about the `with:` inputs of the step whose `uses:` is at ``index``.

    Split out of ``scan_workflow`` so each per-action input rule can be added without pushing
    that function past the complexity limit -- the limit is the reason to extract a helper, not
    a reason to skip a rule.
    """
    problems: list[str] = []
    if action == "actions/checkout":
        following = "\n".join(lines[index : index + 8])
        if "persist-credentials: false" not in following:
            problems.append(f"line {index}: checkout does not disable persisted credentials")
    if action in _SCANNER_VERSION_INPUT_ACTIONS:
        scanner_inputs = lines[index : index + _SCANNER_VERSION_LOOKAHEAD]
        if not any(_SCANNER_VERSION_INPUT.fullmatch(candidate) for candidate in scanner_inputs):
            problems.append(
                f"line {index}: {action} does not pin its scanner with an exact "
                f"version: input, so the SHA pins only the wrapper"
            )
    return problems


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
            problems.extend(_step_input_problems(action, index, lines))
        if "continue-on-error: true" in line:
            problems.append(f"line {index}: continue-on-error weakens an automatic gate")
        if "|| true" in line:
            problems.append(f"line {index}: error-suppressing '|| true' is prohibited")
    return problems


def stale_exemptions(paths: Iterable[Path]) -> list[str]:
    """Report any version-annotation exemption whose subject is not in a scanned workflow.

    An exemption is a hole deliberately cut in a security gate. Once the line it was cut for is
    gone, the hole is still there, excusing nothing, matched by nothing, and reported by nothing
    -- so nobody learns it can be closed, and a future pin that happened to reproduce the same
    (workflow, action, SHA, comment) tuple would be waved through on a decision nobody made.
    """
    live = {
        (path.name, match.group(1), match.group(2), match.group(3) or "")
        for path in paths
        for match in (_USES.match(line) for line in path.read_text(encoding="utf-8").splitlines())
        if match
    }
    return [
        f"version-annotation exemption for {action}@{reference} "
        f"(# {comment or 'no comment'}) in {name} matches no uses: line; delete it"
        for (name, action, reference, comment) in sorted(_PROTECTED_VERSION_ANNOTATIONS)
        if (name, action, reference, comment) not in live
    ]


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
    findings: list[str] = list(stale_exemptions(paths))
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
