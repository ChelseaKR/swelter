#!/usr/bin/env python3
"""Stamp a static Pages route with an exact, machine-readable deployment identity."""

from __future__ import annotations

import argparse
import html
import json
import re
from datetime import datetime
from pathlib import Path

_COMMIT = re.compile(r"[0-9a-f]{40}")
_REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
_META = re.compile(r'<meta\s+name="swelter-build-commit"\s+content="[^"]*"\s*/?>', re.IGNORECASE)


def _validate_timestamp(value: str) -> None:
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("source timestamp must be ISO 8601") from exc


def version_document(
    *, commit: str, ref: str, repository: str, run_id: str, source_timestamp: str
) -> dict[str, object]:
    """Return the stable public deployment-identity document."""
    if not _COMMIT.fullmatch(commit):
        raise ValueError("commit must be a lowercase 40-character SHA-1")
    if not ref.startswith("refs/"):
        raise ValueError("ref must be a full refs/... name")
    if not _REPOSITORY.fullmatch(repository):
        raise ValueError("repository must be owner/name")
    if not run_id.isdecimal() or int(run_id) < 1:
        raise ValueError("run id must be a positive integer")
    _validate_timestamp(source_timestamp)
    return {
        "schema_version": 1,
        "repository": repository,
        "commit": commit,
        "ref": ref,
        "workflow_run_id": int(run_id),
        "source_timestamp": source_timestamp,
    }


def stamp_route(
    web_dir: Path,
    *,
    commit: str,
    ref: str,
    repository: str,
    run_id: str,
    source_timestamp: str,
) -> None:
    """Write ``version.json`` and the equivalent build-commit meta tag."""
    index = web_dir / "index.html"
    if not index.is_file():
        raise FileNotFoundError(f"route has no index.html: {web_dir}")
    document = version_document(
        commit=commit,
        ref=ref,
        repository=repository,
        run_id=run_id,
        source_timestamp=source_timestamp,
    )
    (web_dir / "version.json").write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    markup = index.read_text(encoding="utf-8")
    tag = f'<meta name="swelter-build-commit" content="{html.escape(commit, quote=True)}">'
    if _META.search(markup):
        markup = _META.sub(tag, markup, count=1)
    elif "</head>" in markup:
        markup = markup.replace("</head>", f"  {tag}\n</head>", 1)
    else:
        raise ValueError(f"route index has no </head>: {index}")
    index.write_text(markup, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--web-dir", required=True, type=Path)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--ref", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--source-timestamp", required=True)
    args = parser.parse_args()
    try:
        stamp_route(
            args.web_dir,
            commit=args.commit,
            ref=args.ref,
            repository=args.repository,
            run_id=args.run_id,
            source_timestamp=args.source_timestamp,
        )
    except (OSError, ValueError) as exc:
        parser.exit(status=2, message=f"{parser.prog}: error: {exc}\n")
    print(f"pages-version: stamped {args.web_dir}/version.json at {args.commit}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
