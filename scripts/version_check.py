#!/usr/bin/env python3
"""Version single-source-of-truth + tag/CHANGELOG parity gate (RELEASE-AND-VERSIONING REL-02/03).

``pyproject.toml`` is the authored version. On a release ref this script checks the *current ref*
against that version and the dated CHANGELOG/CITATION metadata. It never compares with the highest
historical tag: doing so makes ordinary post-release development fail for the wrong reason and can
let an older, higher tag validate an unrelated commit.

Run with ``git fetch --tags`` already done (CI's checkout step should use ``fetch-depth: 0`` or an
explicit tag fetch for this to see anything) — see ``release.yml``'s own tag-fetch step, which
this script's logic mirrors for local/CI use outside the release job itself.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = ROOT / "pyproject.toml"
CHANGELOG = ROOT / "CHANGELOG.md"
CITATION = ROOT / "CITATION.cff"

_TAG = re.compile(r"^v(\d+\.\d+\.\d+)$")


def _pyproject_version() -> str:
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    version = data["project"]["version"]
    if not isinstance(version, str):
        raise TypeError(f"pyproject.toml [project] version is not a string: {version!r}")
    return version


def _head_version_tag() -> str | None:
    """Return the single SemVer tag that points at HEAD, if one exists."""
    # Fixed argv, no shell, no user input -- a dev-time/CI gate script.
    git = shutil.which("git")
    if git is None:
        raise RuntimeError("version gate requires git on PATH")
    out = subprocess.run(  # noqa: S603 (#107)
        [git, "-C", str(ROOT), "tag", "--points-at", "HEAD", "v*"],
        capture_output=True,
        check=True,
        text=True,
    ).stdout
    versions = [m.group(1) for line in out.splitlines() if (m := _TAG.match(line.strip()))]
    if len(versions) > 1:
        raise ValueError(f"HEAD has multiple version tags: {', '.join(sorted(versions))}")
    return versions[0] if versions else None


def _release_ref_version() -> str | None:
    """Resolve the exact release ref supplied by GitHub Actions or the tagged local HEAD."""
    ref_type = os.environ.get("GITHUB_REF_TYPE")
    ref_name = os.environ.get("GITHUB_REF_NAME")
    if ref_type == "tag":
        match = _TAG.fullmatch(ref_name or "")
        if match is None:
            raise ValueError(f"release ref is not vMAJOR.MINOR.PATCH: {ref_name!r}")
        return match.group(1)
    return _head_version_tag()


def _changelog_has_dated_section(version: str) -> bool:
    pattern = re.compile(rf"^## \[{re.escape(version)}\] . \d{{4}}-\d{{2}}-\d{{2}}", re.MULTILINE)
    return pattern.search(CHANGELOG.read_text(encoding="utf-8")) is not None


def _citation_has_version(version: str) -> bool:
    pattern = re.compile(rf"^version:\s*['\"]?{re.escape(version)}['\"]?\s*$", re.MULTILINE)
    return pattern.search(CITATION.read_text(encoding="utf-8")) is not None


def main() -> int:
    pyproject_version = _pyproject_version()
    try:
        tag_version = _release_ref_version()
    except ValueError as exc:
        print(f"  [FAIL] {exc}", file=sys.stderr)
        return 1

    if tag_version is None:
        print(f"  [PASS] HEAD is not a release ref; pyproject.toml declares {pyproject_version}")
        print("version-check: release-ref parity activates on a vMAJOR.MINOR.PATCH ref")
        return 0

    problems: list[str] = []
    if tag_version != pyproject_version:
        problems.append(
            f"latest tag v{tag_version} does not match pyproject.toml version {pyproject_version}"
        )
    if not _changelog_has_dated_section(tag_version):
        problems.append(f"CHANGELOG.md has no dated '## [{tag_version}] - YYYY-MM-DD' section")
    if not _citation_has_version(tag_version):
        problems.append(f"CITATION.cff does not declare version {tag_version}")

    if problems:
        print(
            f"  [FAIL] current ref v{tag_version} / pyproject {pyproject_version} / "
            "release metadata mismatch"
        )
        for problem in problems:
            print(f"           - {problem}")
        print("version-check: tag, pyproject.toml, and CHANGELOG.md must agree", file=sys.stderr)
        return 1

    print(f"  [PASS] current ref v{tag_version} == pyproject/CHANGELOG/CITATION")
    print("version-check: current release ref and metadata agree")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
