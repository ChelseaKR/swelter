#!/usr/bin/env python3
"""G1 UTF-8 encoding gate — a merge-blocking i18n check (INTERNATIONALIZATION-STANDARD §4).

Every tracked *text* file must be ``utf-8`` or ``us-ascii``. A stray Latin-1 or UTF-16 file is a
mojibake bug waiting to ship: the moment it carries an accented Spanish character it renders as
garbage for exactly the readers this project owes both languages. The standard's mechanism is
``git ls-files -z | xargs -0 file --mime-encoding`` asserting ``utf-8``/``us-ascii``; this script
is that check, made portable, deterministic, and self-reporting.

It asks git for the tracked set (so untracked scratch files and ignored caches are never in scope),
runs ``file`` in brief mime-encoding mode over them, and fails listing any offender. Binary files
(images, fonts) legitimately report ``binary`` and are skipped — the gate is about *text*.

Pure standard library plus the ``git`` and ``file`` tools that CI and the dev host already have.
Exit status is 0 when every text file is UTF-8/ASCII and 1 otherwise.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: A text file must report one of these; anything else (iso-8859-1, utf-16, unknown-8bit) fails.
ALLOWED = {"utf-8", "us-ascii"}
#: ``file`` reports this for non-text files (images, fonts); they are out of scope for a text gate.
BINARY = "binary"


def _tracked_files() -> list[str]:
    """Return every path tracked by git, NUL-delimited so filenames with spaces survive."""
    # Fixed argv, no shell, no user input -- a dev-time/CI gate script, not a network-facing path.
    git = shutil.which("git")
    if git is None:
        raise RuntimeError("i18n encoding gate requires git on PATH")
    out = subprocess.run(  # noqa: S603 (#107)
        [git, "-C", str(ROOT), "ls-files", "-z"],
        capture_output=True,
        check=True,
        text=True,
    ).stdout
    # A pre-commit working tree can contain tracked deletions. They are absent from the candidate
    # artifact and `file` would otherwise report a misleading "cannot open" encoding failure.
    return [p for p in out.split("\0") if p and (ROOT / p).is_file()]


def _encodings(paths: list[str]) -> list[str]:
    """Return the mime-encoding of each path, one per input, in order (brief mode, no filename)."""
    # `paths` are git-tracked repo paths from `_tracked_files()`, not external input.
    file_command = shutil.which("file")
    if file_command is None:
        raise RuntimeError("i18n encoding gate requires file on PATH")
    out = subprocess.run(  # noqa: S603 (#107)
        [file_command, "-b", "--mime-encoding", "--", *paths],
        cwd=ROOT,
        capture_output=True,
        check=True,
        text=True,
    ).stdout
    return out.splitlines()


def main() -> int:
    paths = _tracked_files()
    if not paths:
        print("i18n-encoding: no tracked files found", file=sys.stderr)
        return 1

    encodings = _encodings(paths)
    if len(encodings) != len(paths):
        print(
            f"i18n-encoding: file reported {len(encodings)} results for {len(paths)} files",
            file=sys.stderr,
        )
        return 1

    offenders: list[tuple[str, str]] = []
    checked = 0
    for path, enc in zip(paths, encodings, strict=True):
        enc = enc.strip()
        if enc == BINARY:
            continue  # not a text file — out of scope for the UTF-8 gate
        checked += 1
        if enc not in ALLOWED:
            offenders.append((path, enc))

    ok = not offenders
    marker = "PASS" if ok else "FAIL"
    print(f"  [{marker}] every tracked text file is utf-8/us-ascii ({len(offenders)} not)")
    for path, enc in sorted(offenders):
        print(f"           - {path}: {enc}")

    if offenders:
        print(f"i18n-encoding: {len(offenders)} non-UTF-8 text file(s)", file=sys.stderr)
        return 1
    print(f"i18n-encoding: {checked} text files are UTF-8/ASCII ({len(paths)} tracked)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
