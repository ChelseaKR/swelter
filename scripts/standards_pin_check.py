#!/usr/bin/env python3
"""Verify the vendored standards offline and, in CI, against their real upstream tag."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from collections.abc import Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
STANDARDS = ROOT / "docs" / "standards"
VERSION_FILE = STANDARDS / ".standards-version"
MANIFEST = STANDARDS / ".standards-manifest.sha256"

UPSTREAM_REPOSITORY = "ChelseaKR/portfolio-standards"
UPSTREAM_GIT = f"https://github.com/{UPSTREAM_REPOSITORY}.git"
RELEASES_API = f"https://api.github.com/repos/{UPSTREAM_REPOSITORY}/releases?per_page=100"

_HASH_LINE = re.compile(r"^([0-9a-f]{64})  ([A-Z0-9][A-Za-z0-9.-]+\.md)$")
_SEMVER_TAG = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")


def _governed_standard_name(name: str) -> bool:
    return name == "README.md" or name.endswith(("-STANDARD.md", "-FRAMEWORK.md"))


def _version() -> str:
    match = re.search(r"^standards_version=(v\d+\.\d+\.\d+)$", VERSION_FILE.read_text(), re.M)
    if match is None:
        raise ValueError(".standards-version has no standards_version=vMAJOR.MINOR.PATCH line")
    return match.group(1)


def _manifest() -> tuple[str, dict[str, str]]:
    commit = ""
    expected: dict[str, str] = {}
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        if line.startswith("# Canonical peeled commit: "):
            commit = line.removeprefix("# Canonical peeled commit: ").strip()
            continue
        if not line or line.startswith("#"):
            continue
        match = _HASH_LINE.fullmatch(line)
        if match is None:
            raise ValueError(f"invalid standards manifest line: {line!r}")
        digest, name = match.groups()
        if name in expected:
            raise ValueError(f"duplicate standards manifest entry: {name}")
        expected[name] = digest
    if not _COMMIT.fullmatch(commit):
        raise ValueError("standards manifest has no valid canonical peeled commit")
    if not expected:
        raise ValueError("standards manifest has no files")
    return commit, expected


def verify_offline() -> tuple[str, str, dict[str, str]]:
    """Validate the committed, dependency-free local integrity layer."""
    version = _version()
    commit, expected = _manifest()
    actual_files = {path.name for path in STANDARDS.glob("*.md")}
    if actual_files != set(expected):
        missing = sorted(set(expected) - actual_files)
        extra = sorted(actual_files - set(expected))
        raise ValueError(f"standards file set drift; missing={missing}, extra={extra}")

    mismatches = []
    for name, wanted in sorted(expected.items()):
        actual = hashlib.sha256((STANDARDS / name).read_bytes()).hexdigest()
        if actual != wanted:
            mismatches.append(f"{name}: expected {wanted}, got {actual}")
    if mismatches:
        raise ValueError("vendored standard drift: " + "; ".join(mismatches))
    return version, commit, expected


def _run_git(arguments: list[str], *, cwd: Path) -> str:
    git = shutil.which("git")
    if git is None:
        raise RuntimeError("git executable is unavailable")
    result = subprocess.run(  # noqa: S603 (#107)
        [git, *arguments],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip() or "unknown git error"
        raise RuntimeError(f"git {' '.join(arguments)} failed: {detail}")
    return result.stdout.strip()


def _released_tags() -> list[str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "swelter-standards-pin",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(RELEASES_API, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 (#107)
            payload: Any = json.load(response)
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"could not read canonical GitHub releases: {exc}") from exc
    if not isinstance(payload, list):
        raise RuntimeError("canonical GitHub releases response is not a list")
    tags: list[str] = []
    for release in payload:
        if not isinstance(release, dict) or release.get("draft") or release.get("prerelease"):
            continue
        tag = release.get("tag_name")
        if isinstance(tag, str) and _SEMVER_TAG.fullmatch(tag):
            tags.append(tag)
    if not tags:
        raise RuntimeError("canonical repository has no stable SemVer releases")
    return tags


def _semver_key(tag: str) -> tuple[int, int, int]:
    match = _SEMVER_TAG.fullmatch(tag)
    if match is None:
        raise ValueError(f"not a SemVer tag: {tag}")
    major, minor, patch = (int(group) for group in match.groups())
    return major, minor, patch


def _currency_problem(pinned: str, latest: str) -> str | None:
    pinned_version = _semver_key(pinned)
    latest_version = _semver_key(latest)
    if pinned_version > latest_version:
        return f"pinned {pinned} is newer than latest stable upstream release {latest}"
    if pinned_version[0] < latest_version[0]:
        return f"pinned {pinned} is a major release behind latest {latest}"
    if latest_version[1] - pinned_version[1] >= 2:
        return f"pinned {pinned} is at least two minor releases behind latest {latest}"
    return None


def verify_upstream(version: str, commit: str, expected: dict[str, str]) -> str:
    """Fetch the exact upstream release and compare its tag target and blobs."""
    releases = _released_tags()
    if version not in releases:
        raise ValueError(f"{version} is not a stable GitHub release of {UPSTREAM_REPOSITORY}")
    latest = max(releases, key=_semver_key)
    if problem := _currency_problem(version, latest):
        raise ValueError(problem)

    with tempfile.TemporaryDirectory(prefix="swelter-standards-") as temporary:
        checkout = Path(temporary)
        git = shutil.which("git")
        if git is None:
            raise RuntimeError("git executable is unavailable")
        _run_git(["init", "--quiet"], cwd=checkout)
        _run_git(["remote", "add", "origin", UPSTREAM_GIT], cwd=checkout)
        _run_git(
            [
                "fetch",
                "--quiet",
                "--depth=1",
                "origin",
                f"refs/tags/{version}:refs/tags/{version}",
            ],
            cwd=checkout,
        )
        resolved = _run_git(["rev-parse", f"refs/tags/{version}^{{commit}}"], cwd=checkout)
        if resolved != commit:
            raise ValueError(
                f"upstream {version} resolves to {resolved}, manifest records {commit}"
            )
        upstream_names = {
            name
            for name in _run_git(["ls-tree", "--name-only", resolved], cwd=checkout).splitlines()
            if _governed_standard_name(name)
        }
        if upstream_names != set(expected):
            missing = sorted(upstream_names - set(expected))
            extra = sorted(set(expected) - upstream_names)
            raise ValueError(
                f"manifest does not cover the upstream governed file set; missing={missing}, "
                f"extra={extra}"
            )
        mismatches: list[str] = []
        for name, wanted in sorted(expected.items()):
            blob = subprocess.run(  # noqa: S603 (#107)
                [git, "show", f"{resolved}:{name}"],
                cwd=checkout,
                check=False,
                capture_output=True,
                timeout=30,
            )
            if blob.returncode:
                mismatches.append(f"{name}: absent from upstream tag")
                continue
            actual = hashlib.sha256(blob.stdout).hexdigest()
            if actual != wanted:
                mismatches.append(f"{name}: upstream {actual}, manifest {wanted}")
        if mismatches:
            raise ValueError("upstream standard drift: " + "; ".join(mismatches))
    return latest


def main(argv: Sequence[str] = ()) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--upstream",
        action="store_true",
        help="also authenticate the pin against the canonical GitHub release and tag",
    )
    args = parser.parse_args(list(argv))
    try:
        version, commit, expected = verify_offline()
        if args.upstream:
            latest = verify_upstream(version, commit, expected)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"standards-pin: FAIL: {exc}", file=sys.stderr)
        return 1

    print(f"  [PASS] {len(expected)} standards byte-match {version} ({commit[:12]})")
    if args.upstream:
        pinned_key = _semver_key(version)
        latest_key = _semver_key(latest)
        currency = (
            "current release"
            if latest == version
            else f"within the currency window relative to {latest}"
        )
        print(f"  [PASS] upstream release/tag/blob authenticity verified; pin is {currency}")
        if latest_key[1] - pinned_key[1] == 1:
            print(f"  [WARN] standards pin {version} is one minor behind {latest}", file=sys.stderr)
    else:
        print("  [PASS] offline manifest integrity verified (upstream authentication runs in CI)")
    print("standards-pin: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
