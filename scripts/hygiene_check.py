#!/usr/bin/env python3
"""Hygiene gates: no bare TODO/FIXME/HACK markers, and every suppression carries a code
(CODE-QUALITY CQ-34/CQ-35).

The 2026-07-05 conformance audit found the repo already clean of bare TODO/FIXME/HACK markers and
every ``# noqa`` / ``# type: ignore`` already coded — but with no CI gate keeping it that way. This
script is that gate.

**Known, disclosed gap (not silently dropped):** CQ-35's fuller text also wants each suppression to
reference a tracking issue. This repo has no issue tracker wired to a committed artifact this script
could check against, and this remediation pass was explicitly barred from creating GitHub issues (a
live write to another system) on the maintainer's behalf. So issue-reference enforcement is **not**
part of this gate yet; it stays a manual-review expectation until an issue-tracking convention is
adopted. Tracked in ``audit-2026-07-05/swelter-REMEDIATION.md`` (P1-9).
"""

from __future__ import annotations

import re
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


def _tracked_files(*dirs: str) -> list[Path]:
    # Fixed argv, no shell, no user input -- a dev-time/CI gate script.
    out = subprocess.run(  # noqa: S603
        ["git", "-C", str(ROOT), "ls-files", "-z", *dirs],  # noqa: S607
        capture_output=True,
        check=True,
        text=True,
    ).stdout
    return [ROOT / p for p in out.split("\0") if p]


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
        rel = path.relative_to(ROOT)
        for lineno, line in enumerate(text.splitlines(), start=1):
            if _BARE_MARKER.search(line):
                problems.append(f"{rel}:{lineno}: bare TODO/FIXME/HACK marker — {line.strip()!r}")
            if _NOQA.search(line):
                problems.append(f"{rel}:{lineno}: '# noqa' with no error code — {line.strip()!r}")
            if _TYPE_IGNORE_BARE.search(line):
                problems.append(
                    f"{rel}:{lineno}: '# type: ignore' with no bracketed code — {line.strip()!r}"
                )
    return problems


def main() -> int:
    paths = _tracked_files(*SCAN_DIRS)
    problems = _scan(paths)

    if problems:
        print(f"  [FAIL] {len(problems)} hygiene issue(s) found")
        for problem in problems:
            print(f"           - {problem}")
        print("hygiene: bare TODO/FIXME/HACK or uncoded noqa/type:ignore found", file=sys.stderr)
        return 1

    print(f"  [PASS] no bare TODO/FIXME/HACK; every noqa/type:ignore is coded ({len(paths)} files)")
    print("hygiene: clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
