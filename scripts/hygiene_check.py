#!/usr/bin/env python3
"""Hygiene gates: no bare TODO/FIXME/HACK markers; every suppression is coded and issue-linked
(CODE-QUALITY CQ-34/CQ-35); and the number of tracked suppressions never grows.

Suppressions use a precise diagnostic and a ``(#NN)`` or GitHub issue URL. One shared retirement
issue may cover a coherent sweep, but blanket or untracked suppressions fail this gate.

THE RATCHET. Coding and linking a suppression makes it *legible*; it does nothing to make it
*temporary*. Every suppression in this repository was already coded and linked, so the gate was
green while the inventory could grow without limit — and #107, whose close condition is "the
hygiene gate reports no tracked suppressions", could never be reached by running the gate,
because the gate did not count.

So it counts now, against a committed ceiling:

* **Above** ``SUPPRESSION_CEILING`` fails. Adding a suppression is allowed, but it costs a
  deliberate edit to this file that a reviewer sees, instead of arriving as one quiet comment
  in a large diff.
* **Below** it also fails, asking you to lower the ceiling. That is the ratchet: retiring a
  suppression and leaving the ceiling up would hand the slack straight back.

The ceiling is a number, not a judgement about which suppressions are correct. Several here are
permanent and right — ``S603`` on a fixed-argv subprocess call does not become wrong with age.
Ratcheting the count is what makes the *direction* enforceable while that argument stays open.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: Directories worth scanning for hygiene; excludes vendored/generated/data trees.
SCAN_DIRS = ("src", "tests", "scripts", "web", "firmware/src", "firmware/tests")

#: A bare marker with no ticket/context is the thing this gate exists to catch. Deliberately does
#: not fire on words like "TODOne" or inside this script's own docstring examples above.
_BARE_MARKER = re.compile(r"\b(TODO|FIXME|HACK)\b(?!\()")

_NOQA = re.compile(r"#\s*noqa\b(?!\s*:)")
_TYPE_IGNORE_BARE = re.compile(r"#\s*type:\s*ignore\s*(?!\[)")
_ISSUE_REFERENCE = re.compile(
    r"\(#\d+\)|https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/issues/\d+"
)

#: Any of the three suppression forms this repo tracks, for counting.
_SUPPRESSION = re.compile(r"#\s*noqa\b|#\s*type:\s*ignore\b|nosemgrep:")

#: The exact number of tracked suppressions on `main` today. Lower it whenever you retire one;
#: raising it is a deliberate, reviewable edit. Retirement is tracked on #107.
#: 26 -> 28: two fixed-argv `S603` subprocess calls in scripts/demo_artifact_check.py
#: (git ls-files, and the demo replay the gate re-runs), the same permanent pattern as
#: the other gate scripts.
#: 28 -> 27: `do_GET`'s `C901` retired. Its twenty-arm `if/elif` route dispatch is a table
#: (`server._GET_ROUTES`), which is one branch instead of twenty. Genuinely retired debt, not
#: a rule-level exception waived away.
SUPPRESSION_CEILING = 27


def _tracked_files(*dirs: str) -> list[Path]:
    # Fixed argv, no shell, no user input -- a dev-time/CI gate script.
    git = shutil.which("git")
    if git is None:
        raise RuntimeError("hygiene gate requires git on PATH")
    out = subprocess.run(  # noqa: S603 (#107)
        [git, "-C", str(ROOT), "ls-files", "-z", *dirs],
        capture_output=True,
        check=True,
        text=True,
    ).stdout
    return [ROOT / p for p in out.split("\0") if p]


def count_suppressions(paths: list[Path]) -> dict[str, int]:
    """Tracked suppressions per file, for the ratchet and for the #107 inventory."""
    counts: dict[str, int] = {}
    for path in paths:
        if path.name == Path(__file__).name:
            continue  # this file's own patterns would count itself
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        rel = str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)
        # Count MARKERS, not lines. Two suppressions on one line is two suppressions;
        # counting lines would let a retirement look like no change at all.
        found = sum(len(_SUPPRESSION.findall(line)) for line in text.splitlines())
        if found:
            counts[rel] = found
    return counts


def check_ceiling(total: int, ceiling: int = SUPPRESSION_CEILING) -> list[str]:
    """The ratchet. Returns the problems, so `main` can report them like any other."""
    if total > ceiling:
        return [
            f"{total} tracked suppression(s), ceiling is {ceiling}. A new suppression is a "
            "decision, not a detail: if it is right, raise SUPPRESSION_CEILING in "
            "scripts/hygiene_check.py in this PR and say why in the description (#107).",
        ]
    if total < ceiling:
        return [
            f"{total} tracked suppression(s), ceiling is still {ceiling}. Lower "
            "SUPPRESSION_CEILING to {0} to lock the retirement in — a ceiling left high "
            "hands the slack straight back (#107).".format(total),
        ]
    return []


def _scan(paths: list[Path]) -> list[str]:
    problems: list[str] = []
    for path in paths:
        if path.name == Path(__file__).name:
            continue  # this file's own docstring/patterns above would false-positive on itself
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue  # binary/unreadable; the i18n encoding gate covers text-encoding separately
        # Tests and downstream callers may supply an explicit file outside the
        # checkout. Keep diagnostics useful without weakening the repository
        # scan performed by ``main``.
        rel = path.relative_to(ROOT) if path.is_relative_to(ROOT) else path
        for lineno, line in enumerate(text.splitlines(), start=1):
            if _BARE_MARKER.search(line):
                problems.append(f"{rel}:{lineno}: bare TODO/FIXME/HACK marker — {line.strip()!r}")
            if _NOQA.search(line):
                problems.append(f"{rel}:{lineno}: '# noqa' with no error code — {line.strip()!r}")
            if _TYPE_IGNORE_BARE.search(line):
                problems.append(
                    f"{rel}:{lineno}: '# type: ignore' with no bracketed code — {line.strip()!r}"
                )
            if ("# noqa" in line or "# type: ignore" in line or "nosemgrep:" in line) and not (
                _ISSUE_REFERENCE.search(line)
            ):
                problems.append(
                    f"{rel}:{lineno}: suppression has no linked issue — {line.strip()!r}"
                )
    return problems


def main() -> int:
    paths = _tracked_files(*SCAN_DIRS)
    counts = count_suppressions(paths)
    total = sum(counts.values())
    problems = _scan(paths) + check_ceiling(total)

    if problems:
        print("  tracked suppressions by file (the #107 inventory):")
        for rel, found in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
            print(f"           {found:>3}  {rel}")
        print(f"  [FAIL] {len(problems)} hygiene issue(s) found")
        for problem in problems:
            print(f"           - {problem}")
        print(
            "hygiene: bare TODO/FIXME/HACK or uncoded/unissued suppression found",
            file=sys.stderr,
        )
        return 1

    print(
        "  [PASS] no bare TODO/FIXME/HACK; every suppression is coded and issue-linked "
        f"({len(paths)} files)"
    )
    print(f"  [PASS] {total} tracked suppression(s), at the committed ceiling; never above it")
    print("hygiene: clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
