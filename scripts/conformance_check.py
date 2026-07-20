#!/usr/bin/env python3
"""Validate README's portfolio Standards Conformance ledger.

The table is intentionally a small machine-readable contract: every vendored standard appears
once, states use one of the three canonical shapes, and a linked gap names the same GitHub issue
in its label and URL. In GitHub Actions, public issue state is also checked so a stale/closed gap
cannot silently remain the repository's declared posture.
"""

from __future__ import annotations

import http.client
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
PUBLISHING_GAP = ROOT / "docs" / "audits" / "release-publishing-gap.json"
RELEASE_REVIEWS = ROOT / "docs" / "audits" / "release-review-attestations.json"
QUALITY_GAP = ROOT / "docs" / "audits" / "quality-metrics-gap.json"

REQUIRED_STANDARDS = (
    "Responsible-Tech Framework",
    "Code Quality",
    "Security & Supply-Chain",
    "CI/CD",
    "Observability",
    "Accessibility",
    "Internationalization",
    "AI Evaluation",
    "Documentation",
    "Quality & Metrics",
    "Release & Versioning",
)

_ROW = re.compile(r"^\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|$")
_GAP = re.compile(
    r"^Applies — gap tracked in "
    r"(?:#(?P<plain>\d+)|\[#(?P<label>\d+)\]\(https://github\.com/"
    r"ChelseaKR/swelter/issues/(?P<url>\d+)\))$"
)
_NA = re.compile(r"^N/A — \S.+$")


@dataclass(frozen=True)
class LedgerRow:
    standard: str
    state: str
    issue: int | None


def parse_ledger(text: str) -> tuple[list[LedgerRow], list[str]]:
    """Parse the first Markdown table under ``## Standards Conformance``."""
    errors: list[str] = []
    marker = "## Standards Conformance"
    if marker not in text:
        return [], [f"README.md has no {marker!r} section"]
    section = text.split(marker, 1)[1].split("\n## ", 1)[0]
    rows: list[LedgerRow] = []
    in_table = False
    for line in section.splitlines():
        match = _ROW.match(line)
        if not match:
            if in_table and line.strip():
                break
            continue
        standard, state = (cell.strip() for cell in match.groups())
        if standard == "Standard" or set(standard) <= {"-", ":"}:
            in_table = True
            continue
        in_table = True
        issue: int | None = None
        gap = _GAP.fullmatch(state)
        if state == "Applies":
            pass
        elif gap:
            if gap.group("label") != gap.group("url"):
                errors.append(f"{standard}: issue label and URL do not match")
            issue = int(gap.group("plain") or gap.group("label"))
        elif not _NA.fullmatch(state):
            errors.append(f"{standard}: noncanonical state {state!r}")
        rows.append(LedgerRow(standard, state, issue))
    return rows, errors


def validate_ledger(rows: list[LedgerRow]) -> list[str]:
    errors: list[str] = []
    names = [row.standard for row in rows]
    for name in REQUIRED_STANDARDS:
        count = names.count(name)
        if count != 1:
            errors.append(f"{name}: expected exactly one row, found {count}")
    extras = sorted(set(names) - set(REQUIRED_STANDARDS))
    if extras:
        errors.append(f"unexpected standard row(s): {', '.join(extras)}")
    return errors


def _json_object(path: Path, label: str) -> tuple[dict[str, object] | None, list[str]]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, [f"{label}: cannot read machine evidence ({exc})"]
    if not isinstance(document, dict):
        return None, [f"{label}: machine evidence root is not an object"]
    return document, []


def _row(rows: list[LedgerRow], standard: str) -> LedgerRow | None:
    return next((row for row in rows if row.standard == standard), None)


def _blocking_evidence_problems(
    row: LedgerRow | None, document: dict[str, object], *, standard: str, blocking: bool
) -> list[str]:
    if row is None:
        return []
    issue = document.get("tracking_issue")
    if blocking:
        if not isinstance(issue, int) or issue < 1:
            return [f"{standard}: blocking machine evidence has no dedicated tracking issue"]
        if row.issue != issue:
            return [f"{standard}: ledger gap does not match machine-evidence issue #{issue}"]
    elif row.state != "Applies":
        return [f"{standard}: completed machine evidence still declares a ledger gap"]
    return []


def semantic_evidence_problems(rows: list[LedgerRow], root: Path = ROOT) -> list[str]:
    """Reject an ``Applies`` row when machine evidence says required work is blocking."""
    problems: list[str] = []
    quality, quality_problems = _json_object(
        root / QUALITY_GAP.relative_to(ROOT), "Quality & Metrics"
    )
    problems.extend(quality_problems)
    if quality is not None:
        problems.extend(
            _blocking_evidence_problems(
                _row(rows, "Quality & Metrics"),
                quality,
                standard="Quality & Metrics",
                blocking=quality.get("release_blocking") is True,
            )
        )

    publishing, publishing_problems = _json_object(
        root / PUBLISHING_GAP.relative_to(ROOT), "Release & Versioning"
    )
    problems.extend(publishing_problems)
    if publishing is not None:
        problems.extend(
            _blocking_evidence_problems(
                _row(rows, "Release & Versioning"),
                publishing,
                standard="Release & Versioning",
                blocking=publishing.get("release_blocking") is True,
            )
        )

    reviews, review_problems = _json_object(
        root / RELEASE_REVIEWS.relative_to(ROOT), "Responsible-Tech Framework"
    )
    problems.extend(review_problems)
    if reviews is not None:
        attestations = reviews.get("attestations")
        blocking = not isinstance(attestations, list) or any(
            not isinstance(item, dict) or item.get("outcome") != "pass" for item in attestations
        )
        problems.extend(
            _blocking_evidence_problems(
                _row(rows, "Responsible-Tech Framework"),
                reviews,
                standard="Responsible-Tech Framework",
                blocking=blocking,
            )
        )
    return problems


def _issue_is_open(number: int) -> bool:
    connection = http.client.HTTPSConnection("api.github.com", timeout=20)
    try:
        connection.request(
            "GET",
            f"/repos/ChelseaKR/swelter/issues/{number}",
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "swelter-conformance",
            },
        )
        response = connection.getresponse()
        if response.status != 200:
            raise RuntimeError(f"GitHub returned HTTP {response.status}")
        doc = json.loads(response.read().decode("utf-8"))
    except (OSError, http.client.HTTPException, json.JSONDecodeError) as exc:
        raise RuntimeError(f"could not resolve issue #{number}: {exc}") from exc
    finally:
        connection.close()
    return isinstance(doc, dict) and doc.get("state") == "open" and "pull_request" not in doc


def main() -> int:
    rows, errors = parse_ledger(README.read_text(encoding="utf-8"))
    errors.extend(validate_ledger(rows))
    errors.extend(semantic_evidence_problems(rows))
    check_issues = os.environ.get("GITHUB_ACTIONS") == "true"
    if check_issues and not errors:
        for number in sorted({row.issue for row in rows if row.issue is not None}):
            try:
                is_open = _issue_is_open(number)
            except RuntimeError as exc:
                errors.append(str(exc))
                continue
            if not is_open:
                errors.append(f"gap issue #{number} does not resolve to an open issue")

    if errors:
        print(f"conformance: FAIL ({len(errors)} error(s))", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    checked = " + open issue state" if check_issues else " (issue state checked in CI)"
    print(f"conformance: PASS ({len(rows)} standards{checked})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
