#!/usr/bin/env python3
"""Prevent an accepted architecture decision from being rewritten or deleted.

The selected Git base is the historical record. Every numbered ADR whose *base* content says
``Status: Accepted`` must remain byte-for-byte present in the working tree. A reversal therefore
lands as a new ADR that names what it supersedes; it never edits history to make the old decision
look as if it had not been made.

Base selection, in precedence order:

1. ``--base REF``;
2. ``ADR_IMMUTABILITY_BASE=REF``;
3. a pull-request base SHA/ref from GitHub Actions metadata;
4. local ``origin/main``;
5. local ``HEAD`` (protects accepted ADRs from uncommitted rewrites).

CI must fetch the selected base's history. An explicit or PR base that cannot be resolved fails
closed with a useful diagnostic instead of silently comparing against a different commit.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE_ENV = "ADR_IMMUTABILITY_BASE"

_ADR_PATH = re.compile(r"^docs/adr/\d{4}-[a-z0-9]+(?:-[a-z0-9]+)*\.md$")
_ACCEPTED = re.compile(
    rb"^- (?:\*\*)?Status:(?:\*\*)?[ \t]+Accepted[ \t]*$",
    re.MULTILINE,
)


class ADRImmutabilityError(RuntimeError):
    """The gate could not establish or inspect its comparison base."""


@dataclass(frozen=True)
class BaseSelection:
    commit: str
    label: str
    source: str


def _run_git(repo: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    git = shutil.which("git")
    if git is None:
        raise ADRImmutabilityError("ADR immutability gate requires git on PATH")
    # Absolute executable, fixed subcommands, argv-only invocation, and no shell. Refs are passed
    # after ``--end-of-options`` when resolved so they cannot become command options.
    return subprocess.run(  # noqa: S603 (#107)
        [git, "-C", str(repo), *args],
        capture_output=True,
        check=False,
    )


def _resolve_commit(repo: Path, ref: str) -> str | None:
    if not ref.strip():
        return None
    result = _run_git(
        repo,
        "rev-parse",
        "--verify",
        "--quiet",
        "--end-of-options",
        f"{ref}^{{commit}}",
    )
    if result.returncode != 0:
        return None
    commit = result.stdout.decode("ascii", errors="strict").strip()
    return commit or None


def _event_base_sha(environ: Mapping[str, str]) -> str | None:
    event_path = environ.get("GITHUB_EVENT_PATH", "").strip()
    if not event_path:
        return None
    try:
        event = json.loads(Path(event_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ADRImmutabilityError(
            f"cannot read GitHub event metadata {event_path}: {exc}"
        ) from exc
    if not isinstance(event, dict):
        return None
    pull_request = event.get("pull_request")
    if not isinstance(pull_request, dict):
        return None
    base = pull_request.get("base")
    if not isinstance(base, dict):
        return None
    sha = base.get("sha")
    return sha.strip() if isinstance(sha, str) and sha.strip() else None


def _require_ref(repo: Path, ref: str, source: str) -> BaseSelection:
    commit = _resolve_commit(repo, ref)
    if commit is None:
        raise ADRImmutabilityError(
            f"{source} base {ref!r} is unavailable; fetch full history for the comparison base"
        )
    return BaseSelection(commit=commit, label=ref, source=source)


def resolve_base(
    repo: Path = ROOT,
    *,
    explicit: str | None = None,
    environ: Mapping[str, str] | None = None,
) -> BaseSelection:
    """Resolve the immutable-history base without silently weakening an explicit/PR choice."""
    env = os.environ if environ is None else environ
    if explicit is not None:
        return _require_ref(repo, explicit, "--base")

    configured = env.get(BASE_ENV, "").strip()
    if configured:
        return _require_ref(repo, configured, BASE_ENV)

    github_base_sha = env.get("GITHUB_BASE_SHA", "").strip() or _event_base_sha(env)
    if github_base_sha:
        return _require_ref(repo, github_base_sha, "pull request")

    github_base_ref = env.get("GITHUB_BASE_REF", "").strip()
    if github_base_ref:
        for candidate in (f"origin/{github_base_ref}", github_base_ref):
            commit = _resolve_commit(repo, candidate)
            if commit is not None:
                return BaseSelection(commit, candidate, "pull request")
        raise ADRImmutabilityError(
            f"pull-request base {github_base_ref!r} is unavailable; fetch full history and its "
            "remote base ref"
        )

    origin_main = _resolve_commit(repo, "origin/main")
    if origin_main is not None:
        return BaseSelection(origin_main, "origin/main", "local fallback")
    return _require_ref(repo, "HEAD", "local fallback")


def base_adrs(repo: Path, commit: str) -> dict[str, bytes]:
    """Return numbered ADR blobs from ``commit`` keyed by repository-relative path."""
    listing = _run_git(
        repo,
        "ls-tree",
        "-r",
        "--name-only",
        "-z",
        commit,
        "--",
        "docs/adr",
    )
    if listing.returncode != 0:
        detail = listing.stderr.decode("utf-8", errors="replace").strip()
        raise ADRImmutabilityError(f"cannot list ADRs at base {commit}: {detail}")
    paths = [
        raw.decode("utf-8", errors="strict")
        for raw in listing.stdout.split(b"\0")
        if raw and _ADR_PATH.fullmatch(raw.decode("utf-8", errors="strict"))
    ]
    blobs: dict[str, bytes] = {}
    for path in paths:
        blob = _run_git(repo, "cat-file", "blob", f"{commit}:{path}")
        if blob.returncode != 0:
            detail = blob.stderr.decode("utf-8", errors="replace").strip()
            raise ADRImmutabilityError(f"cannot read {path} at base {commit}: {detail}")
        blobs[path] = blob.stdout
    return blobs


def immutability_problems(repo: Path, historical_adrs: Mapping[str, bytes]) -> list[str]:
    """Report changed/deleted ADRs that were Accepted in ``historical_adrs``."""
    problems: list[str] = []
    for relative, historical in sorted(historical_adrs.items()):
        if not _ADR_PATH.fullmatch(relative) or _ACCEPTED.search(historical) is None:
            continue
        current_path = repo / relative
        if not current_path.is_file():
            problems.append(
                f"{relative}: deleted, but the base ADR is Accepted; add a new superseding ADR"
            )
            continue
        if current_path.read_bytes() != historical:
            problems.append(
                f"{relative}: changed, but the base ADR is Accepted; restore it and add a new "
                "superseding ADR"
            )
    return problems


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base",
        metavar="REF",
        help=f"Git ref to compare against (overrides {BASE_ENV} and automatic base selection)",
    )
    return parser


def main(argv: list[str] | None = None, *, repo: Path = ROOT) -> int:
    args = _parser().parse_args(argv)
    try:
        selection = resolve_base(repo, explicit=args.base)
        historical = base_adrs(repo, selection.commit)
        problems = immutability_problems(repo, historical)
    except ADRImmutabilityError as exc:
        print(f"adr-immutability: FAIL ({exc})", file=sys.stderr)
        return 1

    accepted_count = sum(_ACCEPTED.search(content) is not None for content in historical.values())
    if problems:
        print(f"adr-immutability: FAIL ({len(problems)} immutable ADR change(s))", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    print(
        f"adr-immutability: PASS ({accepted_count} Accepted base ADR(s) unchanged; "
        f"base {selection.label} via {selection.source})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
