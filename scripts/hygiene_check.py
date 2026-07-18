#!/usr/bin/env python3
"""Hygiene gates: no bare TODO/FIXME/HACK markers; every suppression is coded and issue-linked
(CODE-QUALITY CQ-34/CQ-35).

Suppressions use a precise diagnostic and a ``(#NN)`` or GitHub issue URL. One shared retirement
issue may cover a coherent sweep, but blanket or untracked suppressions fail this gate.
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
    problems = _scan(paths)

    if problems:
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
    print("hygiene: clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
