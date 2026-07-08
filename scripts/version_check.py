#!/usr/bin/env python3
"""Version single-source-of-truth + tag/CHANGELOG parity gate (RELEASE-AND-VERSIONING REL-02/03).

``src/swelter/__init__.py`` no longer hand-writes ``__version__``; it reads it back from the
installed package's metadata, so ``pyproject.toml``'s ``[project] version`` is the one place the
number is authored. This script is the second half: when a ``v*`` tag exists, it asserts that the
*latest* tag, ``pyproject.toml``, and ``CHANGELOG.md`` all agree.

Pre-1.0 today, swelter has not yet pushed a ``v*`` tag (``git tag -l`` and ``git ls-remote --tags``
are both empty even though ``CHANGELOG.md`` documents a ``0.1.0`` entry) — so this gate currently
passes by delegation, the same posture ``i18n_cldr_pin_check.py`` documents for G12. The moment a
tag is pushed, the check becomes real: a mismatch between the tag, the declared package version,
and the CHANGELOG's dated section for that version fails the build rather than shipping quietly
wrong metadata.

Run with ``git fetch --tags`` already done (CI's checkout step should use ``fetch-depth: 0`` or an
explicit tag fetch for this to see anything) — see ``release.yml``'s own tag-fetch step, which
this script's logic mirrors for local/CI use outside the release job itself.
"""

from __future__ import annotations

import re
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = ROOT / "pyproject.toml"
CHANGELOG = ROOT / "CHANGELOG.md"

_TAG = re.compile(r"^v(\d+\.\d+\.\d+)$")


def _pyproject_version() -> str:
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    version = data["project"]["version"]
    if not isinstance(version, str):
        raise TypeError(f"pyproject.toml [project] version is not a string: {version!r}")
    return version


def _latest_version_tag() -> str | None:
    """The highest ``vX.Y.Z`` tag reachable from this clone, or None if there isn't one yet."""
    # Fixed argv, no shell, no user input -- a dev-time/CI gate script.
    out = subprocess.run(  # noqa: S603
        ["git", "-C", str(ROOT), "tag", "-l", "v*"],  # noqa: S607
        capture_output=True,
        check=True,
        text=True,
    ).stdout
    versions = [m.group(1) for line in out.splitlines() if (m := _TAG.match(line.strip()))]
    if not versions:
        return None
    return max(versions, key=lambda v: tuple(int(p) for p in v.split(".")))


def _changelog_has_dated_section(version: str) -> bool:
    pattern = re.compile(rf"^## \[{re.escape(version)}\] . \d{{4}}-\d{{2}}-\d{{2}}", re.MULTILINE)
    return pattern.search(CHANGELOG.read_text(encoding="utf-8")) is not None


def main() -> int:
    pyproject_version = _pyproject_version()
    tag_version = _latest_version_tag()

    if tag_version is None:
        print(f"  [PASS] no v* tag yet (pre-release); pyproject.toml declares {pyproject_version}")
        print("version-check: N/A-until-tagged (REL-03 parity activates on the first v* tag)")
        return 0

    problems: list[str] = []
    if tag_version != pyproject_version:
        problems.append(
            f"latest tag v{tag_version} does not match pyproject.toml version {pyproject_version}"
        )
    if not _changelog_has_dated_section(tag_version):
        problems.append(f"CHANGELOG.md has no dated '## [{tag_version}] - YYYY-MM-DD' section")

    if problems:
        print(f"  [FAIL] tag v{tag_version} / pyproject {pyproject_version} / CHANGELOG mismatch")
        for problem in problems:
            print(f"           - {problem}")
        print("version-check: tag, pyproject.toml, and CHANGELOG.md must agree", file=sys.stderr)
        return 1

    print(f"  [PASS] tag v{tag_version} == pyproject.toml == a dated CHANGELOG section")
    print("version-check: tag/pyproject/CHANGELOG agree")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
