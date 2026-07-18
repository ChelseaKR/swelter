"""Focused regression tests for standards, acceptance-map, and DORA evidence gates."""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

ROOT = Path(__file__).resolve().parent.parent
if TYPE_CHECKING:
    from scripts import acceptance_map_check, dora_evidence, standards_pin_check
else:
    sys.path.insert(0, str(ROOT))
    acceptance_map_check = importlib.import_module("scripts.acceptance_map_check")
    dora_evidence = importlib.import_module("scripts.dora_evidence")
    standards_pin_check = importlib.import_module("scripts.standards_pin_check")


def test_standards_currency_fails_at_two_minors_without_weakening_one_minor() -> None:
    assert standards_pin_check._currency_problem("v1.4.2", "v1.4.9") is None
    assert standards_pin_check._currency_problem("v1.3.9", "v1.4.0") is None
    minor_problem = standards_pin_check._currency_problem("v1.2.9", "v1.4.0")
    major_problem = standards_pin_check._currency_problem("v1.9.9", "v2.0.0")
    assert minor_problem is not None and "two minor" in minor_problem
    assert major_problem is not None and "major release" in major_problem


def _acceptance_fixture(root: Path) -> None:
    (root / "docs").mkdir()
    (root / "tests").mkdir()
    (root / "tests" / "test_feature.py").write_text(
        "def test_feature_contract() -> None:\n    pass\n", encoding="utf-8"
    )
    (root / "docs" / "ACCEPTANCE-TEST-MAP.md").write_text(
        "# Map\n\n"
        "## Executable feature map\n\n"
        "| Feature ID | Feature / roadmap outcome | Measurable acceptance criterion | "
        "Automated evidence | Review evidence | ISO/IEC 25010:2023 characteristic(s) |\n"
        "| --- | --- | --- | --- | --- | --- |\n"
        "| F-01 | Shipped outcome | It works | "
        "`tests/test_feature.py::test_feature_contract` | Named review | Reliability |\n",
        encoding="utf-8",
    )
    (root / "docs" / "ROADMAP.md").write_text(
        "# Roadmap\n\n## Shipped feature inventory\n\n"
        "| Feature ID | Shipped roadmap outcome |\n"
        "| --- | --- |\n"
        "| F-01 | Shipped outcome |\n",
        encoding="utf-8",
    )


def test_acceptance_map_resolves_symbols_iso_vocabulary_and_roadmap(tmp_path: Path) -> None:
    _acceptance_fixture(tmp_path)
    assert acceptance_map_check.check(tmp_path) == []

    path = tmp_path / "docs" / "ACCEPTANCE-TEST-MAP.md"
    path.write_text(
        path.read_text(encoding="utf-8")
        .replace("test_feature_contract", "test_missing")
        .replace("Reliability", "Usability"),
        encoding="utf-8",
    )
    problems = acceptance_map_check.check(tmp_path)
    assert any("missing Python test symbol" in problem for problem in problems)
    assert any("invalid ISO 25010:2023 vocabulary" in problem for problem in problems)


def _retained(*, kind: str, records: list[dict[str, Any]], endpoint: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": kind,
        "repository": "example/project",
        "query": {
            "source": "GitHub REST API",
            "endpoint": endpoint,
            "parameters": {"per_page": 100},
            "pagination": "gh api --paginate --slurp",
            "window_start": "2026-01-01T00:00:00Z",
            "window_end": "2026-01-15T00:00:00Z",
        },
        "collection": {"complete": True, "collected_at": "2026-01-15T00:01:00Z"},
        "records": records,
    }


def _run(
    run_id: int,
    *,
    event: str,
    conclusion: str,
    created: str,
    updated: str,
    commit: str | None,
    title: str,
) -> dict[str, Any]:
    return {
        "id": run_id,
        "event": event,
        "status": "completed",
        "conclusion": conclusion,
        "head_sha": f"{run_id:040x}",
        "commit_timestamp": commit,
        "created_at": created,
        "updated_at": updated,
        "display_title": title,
        "url": f"https://example.test/actions/{run_id}",
    }


def test_dora_snapshot_is_deterministic_and_digest_bound(tmp_path: Path) -> None:
    actions_path = tmp_path / "actions.json"
    issues_path = tmp_path / "issues.json"
    actions = _retained(
        kind="github_actions",
        endpoint="/repos/example/project/actions/workflows/pages.yml/runs",
        records=[
            _run(
                1,
                event="push",
                conclusion="success",
                created="2026-01-02T00:30:00Z",
                updated="2026-01-02T01:00:00Z",
                commit="2026-01-02T00:00:00Z",
                title="feat: ship",
            ),
            _run(
                2,
                event="push",
                conclusion="failure",
                created="2026-01-03T00:00:00Z",
                updated="2026-01-03T01:00:00Z",
                commit="2026-01-03T00:00:00Z",
                title="feat: failed deploy",
            ),
            _run(
                3,
                event="schedule",
                conclusion="success",
                created="2026-01-03T12:00:00Z",
                updated="2026-01-03T13:00:00Z",
                commit=None,
                title="scheduled refresh",
            ),
        ],
    )
    issues = _retained(
        kind="github_issues",
        endpoint="/repos/example/project/issues",
        records=[
            {
                "number": 7,
                "title": "Production incident",
                "state": "closed",
                "created_at": "2026-01-04T00:00:00Z",
                "closed_at": "2026-01-04T02:00:00Z",
                "url": "https://example.test/issues/7",
            }
        ],
    )
    actions_path.write_text(json.dumps(actions, sort_keys=True), encoding="utf-8")
    issues_path.write_text(json.dumps(issues, sort_keys=True), encoding="utf-8")

    snapshot, _, _ = dora_evidence.build_snapshot(actions_path, issues_path)
    assert snapshot["collection_complete"] is True
    assert snapshot["metrics"]["deployment_frequency"]["status"] == "pass"
    assert snapshot["metrics"]["change_lead_time"]["p90_hours"] == 1.0
    assert snapshot["metrics"]["change_fail_rate"]["status"] == "alert"
    assert snapshot["metrics"]["failed_deployment_recovery_time"]["max_hours"] == 12.0
    first_digest = snapshot["inputs"]["combined_sha256"]

    generated = argparse.Namespace(
        actions=actions_path,
        issues=issues_path,
        snapshot=tmp_path / "snapshot.json",
        markdown=tmp_path / "DORA.md",
    )
    dora_evidence.generate(generated)
    dora_evidence.check(generated)

    actions["query"]["parameters"]["per_page"] = 99
    actions_path.write_text(json.dumps(actions, sort_keys=True), encoding="utf-8")
    changed, _, _ = dora_evidence.build_snapshot(actions_path, issues_path)
    assert changed["inputs"]["combined_sha256"] != first_digest
    with pytest.raises(dora_evidence.EvidenceError, match="snapshot differs"):
        dora_evidence.check(generated)


def test_committed_dora_snapshot_and_ledger_match_retained_inputs() -> None:
    assert dora_evidence.main(["check"]) == 0


def test_dora_incomplete_collection_requires_a_reason(tmp_path: Path) -> None:
    actions = _retained(kind="github_actions", endpoint="/actions", records=[])
    issues = _retained(kind="github_issues", endpoint="/issues", records=[])
    actions["collection"] = {"complete": False, "collected_at": "2026-01-15T00:01:00Z"}
    actions_path = tmp_path / "actions.json"
    issues_path = tmp_path / "issues.json"
    actions_path.write_text(json.dumps(actions), encoding="utf-8")
    issues_path.write_text(json.dumps(issues), encoding="utf-8")
    with pytest.raises(dora_evidence.EvidenceError, match="needs a reason"):
        dora_evidence.build_snapshot(actions_path, issues_path)
