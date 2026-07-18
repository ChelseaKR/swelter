"""Portfolio Standards Conformance ledger parser/gate."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scripts import conformance_check
else:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    conformance_check = importlib.import_module("scripts.conformance_check")


def _table(rows: str) -> str:
    return f"""# Project

## Standards Conformance

| Standard | State |
|---|---|
{rows}

## Next
"""


def test_repository_conformance_ledger_has_every_standard_once() -> None:
    rows, errors = conformance_check.parse_ledger(
        conformance_check.README.read_text(encoding="utf-8")
    )
    assert errors == []
    assert conformance_check.validate_ledger(rows) == []


def test_blocking_machine_evidence_cannot_hide_behind_applies(tmp_path: Path) -> None:
    audits = tmp_path / "docs" / "audits"
    audits.mkdir(parents=True)
    (audits / "quality-metrics-gap.json").write_text(
        json.dumps({"release_blocking": True, "tracking_issue": 211}), encoding="utf-8"
    )
    (audits / "release-publishing-gap.json").write_text(
        json.dumps({"release_blocking": True, "tracking_issue": 212}), encoding="utf-8"
    )
    (audits / "release-review-attestations.json").write_text(
        json.dumps(
            {
                "tracking_issue": 213,
                "attestations": [{"id": "ethics", "outcome": "pending"}],
            }
        ),
        encoding="utf-8",
    )
    rows = [
        conformance_check.LedgerRow("Quality & Metrics", "Applies", None),
        conformance_check.LedgerRow("Release & Versioning", "Applies", None),
        conformance_check.LedgerRow("Responsible-Tech Framework", "Applies", None),
    ]
    problems = conformance_check.semantic_evidence_problems(rows, tmp_path)
    assert "Quality & Metrics: ledger gap does not match machine-evidence issue #211" in problems
    assert "Release & Versioning: ledger gap does not match machine-evidence issue #212" in problems
    assert (
        "Responsible-Tech Framework: ledger gap does not match machine-evidence issue #213"
        in problems
    )


def test_parser_accepts_only_the_three_canonical_state_shapes() -> None:
    rows, errors = conformance_check.parse_ledger(
        _table(
            "| Code Quality | Applies |\n"
            "| CI/CD | Applies — gap tracked in "
            "[#105](https://github.com/ChelseaKR/swelter/issues/105) |\n"
            "| AI Evaluation | N/A — no model surface |"
        )
    )
    assert errors == []
    assert [row.issue for row in rows] == [None, 105, None]


def test_parser_rejects_fourth_state_and_mismatched_issue_link() -> None:
    _, errors = conformance_check.parse_ledger(
        _table(
            "| Code Quality | Partial |\n"
            "| CI/CD | Applies — gap tracked in "
            "[#105](https://github.com/ChelseaKR/swelter/issues/106) |\n"
            "| AI Evaluation | N/A |"
        )
    )
    assert len(errors) == 3
    assert any("noncanonical" in error for error in errors)
    assert any("do not match" in error for error in errors)
