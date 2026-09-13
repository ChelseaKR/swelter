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
        "schema_version": dora_evidence.SCHEMA_VERSION,
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
    cancellation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    record = {
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
    if cancellation is not None:
        record["cancellation"] = cancellation
    return record


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
        dora_workflow=dora_evidence.DEFAULT_WORKFLOW,
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


def test_an_empty_acceptance_map_is_not_full_coverage(tmp_path: Path) -> None:
    """Every per-row rule is satisfied vacuously by a table with no rows, and one-to-one
    coverage of an empty inventory by an empty map is trivially true. So a map emptied by a bad
    edit printed ``PASS (0 shipped features; paths, symbols, roadmap, ISO 25010:2023
    verified)`` -- a gate that resolved no path, no symbol and no characteristic, reporting that
    it had verified all of them."""
    _acceptance_fixture(tmp_path)
    assert acceptance_map_check.check(tmp_path) == []

    header = (
        "# Map\n\n## Executable feature map\n\n"
        "| Feature ID | Feature / roadmap outcome | Measurable acceptance criterion | "
        "Automated evidence | Review evidence | ISO/IEC 25010:2023 characteristic(s) |\n"
        "| --- | --- | --- | --- | --- | --- |\n"
    )
    (tmp_path / "docs" / "ACCEPTANCE-TEST-MAP.md").write_text(header, encoding="utf-8")
    (tmp_path / "docs" / "ROADMAP.md").write_text(
        "# Roadmap\n\n## Shipped feature inventory\n\n"
        "| Feature ID | Shipped roadmap outcome |\n| --- | --- |\n",
        encoding="utf-8",
    )
    problems = acceptance_map_check.check(tmp_path)
    assert any("executable feature map has no rows" in problem for problem in problems)
    assert any("shipped feature inventory has no rows" in problem for problem in problems)


def test_the_dora_gate_states_how_much_evidence_it_actually_checked() -> None:
    """``dora-evidence: PASS (check)`` was printed identically for a full retained window and for
    the committed state, which has zero records, zero computed metrics, and an incomplete
    collection -- so ``_complete_metrics``, where every DORA threshold in the script lives, is
    never entered. That emptiness is real, disclosed and tracked in #109; what was wrong is that
    a reader could not tell the two runs apart from the gate's own output."""
    snapshot = {
        "collection_complete": False,
        "metrics": {"deployment_frequency": {"status": "unavailable"}},
    }
    summary = dora_evidence.coverage_summary(snapshot, {"records": []}, {"records": []})
    assert "0 deployment run(s)" in summary
    assert "0/1 metric(s) computed" in summary
    assert "collection INCOMPLETE" in summary

    full = {"collection_complete": True, "metrics": {"deployment_frequency": {"status": "pass"}}}
    summary = dora_evidence.coverage_summary(full, {"records": [{}, {}]}, {"records": [{}]})
    assert "2 deployment run(s), 1 incident(s), 1/1 metric(s) computed" in summary
    assert summary.endswith("collection complete")


def test_the_committed_dora_gate_reports_its_own_coverage() -> None:
    detail = dora_evidence.check(
        argparse.Namespace(
            actions=dora_evidence.DEFAULT_ACTIONS,
            issues=dora_evidence.DEFAULT_ISSUES,
            snapshot=dora_evidence.DEFAULT_SNAPSHOT,
            markdown=dora_evidence.DEFAULT_MARKDOWN,
            dora_workflow=dora_evidence.DEFAULT_WORKFLOW,
        )
    )
    assert "metric(s) computed" in detail and "deployment run(s)" in detail
    assert "scheduled window reaches build-artifact" in detail


_WORKFLOW_WITH_NO_PUBLICATION_ROUTE = """
name: DORA evidence
on:
  schedule:
    - cron: "17 13 * * 1"
permissions:
  contents: read
  actions: read
jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@0000000000000000000000000000000000000000
      - name: Generate
        run: python scripts/dora_evidence.py generate --out-dir dist/dora
      - uses: actions/upload-artifact@0000000000000000000000000000000000000000
"""


def _workflow(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "dora.yml"
    path.write_text(body, encoding="utf-8")
    return path


def test_the_committed_evidence_says_where_the_scheduled_window_can_actually_be_read() -> None:
    """The live defect, asserted against the unmodified tree.

    ``docs/audits/dora/*.json`` said ``Scheduled CI will produce the first complete retained
    snapshot`` from 2026-07-17 until this test landed. ``dora.yml`` has run weekly and
    successfully since 2026-07-20 and has never had a step that writes anything back into the
    repository -- so the sentence described a mechanism the workflow does not contain, on the
    one artifact whose whole job is to say what is and is not known (#267).
    """
    route = dora_evidence.publication_route(dora_evidence.DEFAULT_WORKFLOW)
    assert route == "build-artifact"
    for path in (dora_evidence.DEFAULT_ACTIONS, dora_evidence.DEFAULT_ISSUES):
        document = json.loads(path.read_text(encoding="utf-8"))
        collection = document["collection"]
        assert collection["complete"] is False, path
        assert collection["reason"].endswith(dora_evidence.RETENTION_NOTES[route]), path


def test_a_publication_route_of_any_kind_changes_the_sentence_the_evidence_must_carry(
    tmp_path: Path,
) -> None:
    """Three independent routes, and the capability one is the half a spelling list cannot close.

    A job granted ``contents: write`` can commit the snapshot whatever binary it invokes, so the
    permission alone is enough to make ``build-artifact`` a false claim; the two action/command
    routes catch a step holding a token from somewhere else.
    """
    assert (
        dora_evidence.publication_route(_workflow(tmp_path, _WORKFLOW_WITH_NO_PUBLICATION_ROUTE))
        == "build-artifact"
    )

    granted = _WORKFLOW_WITH_NO_PUBLICATION_ROUTE.replace("contents: read", "contents: write")
    assert dora_evidence.publication_route(_workflow(tmp_path, granted)) == "repository"

    pages = _WORKFLOW_WITH_NO_PUBLICATION_ROUTE.replace(
        "      - uses: actions/upload-artifact@0000000000000000000000000000000000000000",
        "      - uses: peter-evans/create-pull-request@1111111111111111111111111111111111111111",
    )
    assert dora_evidence.publication_route(_workflow(tmp_path, pages)) == "repository"

    pushed = _WORKFLOW_WITH_NO_PUBLICATION_ROUTE.replace(
        "        run: python scripts/dora_evidence.py generate --out-dir dist/dora",
        "        run: |\n"
        "          python scripts/dora_evidence.py generate --out-dir docs/audits/dora\n"
        "          git   push  origin main\n",
    )
    assert dora_evidence.publication_route(_workflow(tmp_path, pushed)) == "repository"


def test_a_workflow_the_reader_no_longer_recognises_is_refused_not_called_artifact_only(
    tmp_path: Path,
) -> None:
    """``build-artifact`` is the answer a reader returns when it understands the file and finds
    no route, and it is also what a reader that has stopped parsing returns. Four floors keep
    the two apart, because only one of them is a fact about this repository."""
    missing = tmp_path / "absent.yml"
    with pytest.raises(dora_evidence.EvidenceError, match="cannot read"):
        dora_evidence.publication_route(missing)

    with pytest.raises(dora_evidence.EvidenceError, match="not a mapping"):
        dora_evidence.publication_route(_workflow(tmp_path, "- just\n- a list\n"))

    with pytest.raises(dora_evidence.EvidenceError, match="no jobs"):
        dora_evidence.publication_route(_workflow(tmp_path, "name: DORA evidence\njobs: {}\n"))

    renamed = _WORKFLOW_WITH_NO_PUBLICATION_ROUTE.replace(
        "python scripts/dora_evidence.py generate", "python scripts/other_thing.py build"
    )
    with pytest.raises(dora_evidence.EvidenceError, match="this is not the workflow"):
        dora_evidence.publication_route(_workflow(tmp_path, renamed))


def test_an_incomplete_reason_that_predates_the_workflow_is_refused_and_a_complete_one_is_not(
    tmp_path: Path,
) -> None:
    """The refusal needs the case it must let through beside it: a *complete* collection is not
    asked where its window can be read, because it is already here."""
    workflow = _workflow(tmp_path, _WORKFLOW_WITH_NO_PUBLICATION_ROUTE)
    retired = "Scheduled CI will produce the first complete retained snapshot."

    stale = _retained(kind="github_actions", endpoint="/actions", records=[])
    stale["collection"] = {
        "complete": False,
        "collected_at": "2026-01-15T00:01:00Z",
        "reason": retired,
    }
    complete = _retained(kind="github_issues", endpoint="/issues", records=[])
    with pytest.raises(dora_evidence.EvidenceError, match="does not end with the sentence"):
        dora_evidence._validate_retention_note(
            {"github_actions": stale, "github_issues": complete}, workflow
        )

    stale["collection"]["reason"] = (
        "Something happened. " + dora_evidence.RETENTION_NOTES["build-artifact"]
    )
    assert (
        dora_evidence._validate_retention_note(
            {"github_actions": stale, "github_issues": complete}, workflow
        )
        == "build-artifact"
    )

    complete_only = _retained(kind="github_actions", endpoint="/actions", records=[])
    assert (
        dora_evidence._validate_retention_note(
            {"github_actions": complete_only, "github_issues": complete}, workflow
        )
        is None
    )


# --- #267: a cancelled run is four outcomes, and the DORA failure set must tell them apart ----
#
# Every annotation string below is the exact text GitHub wrote, copied from a real run:
# `gtfs-scorecard` run 34162993774 / job 101868453025 for the timeout kill, and swelter `ci.yml`
# job 101911103002 for the supersede. A test that invented the wording would pass forever while
# the classifier missed the message it will actually meet.
TIMEOUT_KILL_MESSAGE = "The job has exceeded the maximum execution time of 45m0s"
SUPERSEDE_MESSAGE = (
    "Canceling since a higher priority waiting request for CI-refs/pull/265/merge-pr exists"
)
OPERATION_CANCELED_MESSAGE = "The operation was canceled."


def _cancellation(cause: str, *, steps: int = 8, messages: tuple[str, ...] = ()) -> dict[str, Any]:
    return {
        "cause": cause,
        "jobs": [
            {
                "id": 101868453025,
                "name": "monitor",
                "conclusion": "cancelled",
                "started_at": "2026-01-05T21:24:06Z",
                "completed_at": "2026-01-05T22:09:20Z",
                "steps": steps,
                "annotations": [
                    {"annotation_level": "failure", "message": message} for message in messages
                ],
            }
        ]
        if steps or messages
        else [],
    }


def _metrics_over(records: list[dict[str, Any]], tmp_path: Path) -> dict[str, Any]:
    actions_path = tmp_path / "actions.json"
    issues_path = tmp_path / "issues.json"
    actions_path.write_text(
        json.dumps(
            _retained(
                kind="github_actions",
                endpoint="/repos/example/project/actions/workflows/pages.yml/runs",
                records=records,
            ),
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    issues_path.write_text(
        json.dumps(
            _retained(kind="github_issues", endpoint="/repos/example/project/issues", records=[]),
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    snapshot, _, _ = dora_evidence.build_snapshot(actions_path, issues_path)
    metrics: dict[str, Any] = snapshot["metrics"]
    return metrics


def _deploy_and_cancellation(cancellation: dict[str, Any]) -> list[dict[str, Any]]:
    return [
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
            event="schedule",
            conclusion="cancelled",
            created="2026-01-05T21:24:04Z",
            updated="2026-01-05T22:09:21Z",
            commit=None,
            title="scheduled refresh",
            cancellation=cancellation,
        ),
    ]


def test_dora_counts_a_job_killed_by_its_own_timeout_as_a_failed_deployment() -> None:
    """The defect in #267, at its narrowest.

    A job killed by its own ``timeout-minutes`` concludes ``cancelled``, never ``timed_out``, so
    it fell out of the numerator *and* the denominator of ``change_fail_rate`` and opened no
    recovery event. `gtfs-scorecard` died that way for eleven consecutive scheduled runs while
    every sweep read the result as no signal.
    """
    killed = _cancellation(
        "timeout_kill", messages=(TIMEOUT_KILL_MESSAGE, OPERATION_CANCELED_MESSAGE)
    )
    assert dora_evidence._classify_cancellation(killed["jobs"]) == "timeout_kill", (
        "the classifier must recognise the exact sentence GitHub writes"
    )
    assert (
        dora_evidence.run_disposition({"conclusion": "cancelled", "cancellation": killed})
        == dora_evidence.FAILED
    )


def test_dora_change_fail_rate_counts_a_timeout_kill_and_opens_its_recovery(
    tmp_path: Path,
) -> None:
    metrics = _metrics_over(
        _deploy_and_cancellation(_cancellation("timeout_kill", messages=(TIMEOUT_KILL_MESSAGE,))),
        tmp_path,
    )
    rate = metrics["change_fail_rate"]
    assert rate["failed_attempts"] == 1
    assert rate["completed_attempts"] == 2, "a capped deploy is an attempt, not a non-event"
    assert rate["timeout_killed_attempts"] == 1
    assert rate["rate"] == 0.5
    assert metrics["failed_deployment_recovery_time"]["open_events"] == ["workflow run 2"]


def test_dora_does_not_count_a_cancellation_that_never_reached_a_runner(tmp_path: Path) -> None:
    """Adding ``cancelled`` to the failure set would have been worse than the blindness.

    All 38 cancelled ``pages.yml`` runs in this repository's history returned ``total_count: 0``
    from the jobs endpoint -- evicted out of the pending queue before a runner existed. Counting
    them would put a false 12.5% on a metric whose target is 15%.
    """
    metrics = _metrics_over(
        _deploy_and_cancellation(_cancellation("never_started", steps=0)), tmp_path
    )
    rate = metrics["change_fail_rate"]
    assert rate["failed_attempts"] == 0
    assert rate["completed_attempts"] == 1
    assert rate["cancelled_by_cause"]["never_started"] == 1
    assert metrics["failed_deployment_recovery_time"]["status"] == "no_event"


def test_dora_does_not_count_a_run_superseded_while_a_job_was_running(tmp_path: Path) -> None:
    assert (
        dora_evidence._classify_cancellation(
            _cancellation("superseded", messages=(SUPERSEDE_MESSAGE,))["jobs"]
        )
        == "superseded"
    )
    metrics = _metrics_over(
        _deploy_and_cancellation(_cancellation("superseded", messages=(SUPERSEDE_MESSAGE,))),
        tmp_path,
    )
    assert metrics["change_fail_rate"]["failed_attempts"] == 0
    assert metrics["change_fail_rate"]["cancelled_by_cause"]["superseded"] == 1


def test_dora_refuses_a_cancellation_whose_cause_it_cannot_name(tmp_path: Path) -> None:
    """ "We could not tell" must not arrive at the reader spelled "it did not fail"."""
    unrecognised = _cancellation("unrecognised", messages=(OPERATION_CANCELED_MESSAGE,))
    assert dora_evidence._classify_cancellation(unrecognised["jobs"]) == "unrecognised"
    metrics = _metrics_over(_deploy_and_cancellation(unrecognised), tmp_path)
    for name in ("change_fail_rate", "failed_deployment_recovery_time"):
        assert metrics[name]["status"] == "unavailable", name
        assert metrics[name]["unresolved_runs"] == [2], name
        assert "does not classify" in metrics[name]["reason"], name
    assert metrics["deployment_frequency"]["status"] == "pass", (
        "an unclassifiable cancellation says nothing about how often this repository deployed"
    )


def test_dora_refuses_a_terminal_outcome_that_is_in_no_disposition_table(tmp_path: Path) -> None:
    """The same hole one level up: an unmapped ``conclusion`` used to vanish from both totals."""
    records = [
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
            3,
            event="push",
            conclusion="neutral",
            created="2026-01-06T00:00:00Z",
            updated="2026-01-06T00:05:00Z",
            commit="2026-01-06T00:00:00Z",
            title="feat: something new",
        ),
    ]
    metrics = _metrics_over(records, tmp_path)
    assert metrics["change_fail_rate"]["status"] == "unavailable"
    assert metrics["change_fail_rate"]["unresolved_runs"] == [3]
    assert dora_evidence.run_disposition({"conclusion": "a_value_github_has_not_invented_yet"}) == (
        dora_evidence.REFUSED
    )


def test_dora_failure_mode_coverage_is_an_output_of_the_gate() -> None:
    """Two numbers, computed rather than asserted in prose.

    Before #267 four of the eleven non-success terminal outcomes reached a decision: the four
    members of ``FAILED_CONCLUSIONS``. The other seven -- ``skipped``, ``stale``, ``neutral`` and
    ``cancelled`` in all four of its shapes -- were dropped from both the numerator and the
    denominator with nothing printed.
    """
    coverage = dora_evidence.failure_mode_coverage()
    assert coverage["examinable"] == 11
    assert coverage["resolved"] + coverage["refused"] == coverage["examinable"]
    assert coverage["counted_as_failure"] == 5
    assert coverage["counted_as_non_attempt"] == 4
    assert coverage["refused"] == 2
    assert len(dora_evidence.FAILED_CONCLUSIONS) == 4, (
        "the four this gate could already see; the fifth failure mode is a classified cancellation"
    )
    # Every conclusion GitHub documents for a completed workflow run reaches the table, and
    # `cancelled` is the one that reaches it through the retained cause rather than by name.
    documented = {
        "success",
        "failure",
        "neutral",
        "cancelled",
        "skipped",
        "timed_out",
        "action_required",
        "startup_failure",
        "stale",
    }
    unmapped = documented - set(dora_evidence.RUN_DISPOSITIONS) - {"cancelled"}
    assert unmapped == set(), f"unmapped terminal outcome(s): {sorted(unmapped)}"


def test_dora_snapshot_summary_reports_the_two_failure_mode_numbers() -> None:
    summary = dora_evidence.coverage_summary(
        {"metrics": {}, "collection_complete": True}, {"records": []}, {"records": []}
    )
    assert "11/11 non-success terminal outcome(s) reach a decision" in summary


def _raw_actions(conclusion: str, run_id: int = 2) -> dict[str, Any]:
    return {
        "total_count": 1,
        "workflow_runs": [
            {
                "id": run_id,
                "event": "schedule",
                "status": "completed",
                "conclusion": conclusion,
                "head_sha": f"{run_id:040x}",
                "created_at": "2026-01-05T21:24:04Z",
                "updated_at": "2026-01-05T22:09:21Z",
                "display_title": "scheduled refresh",
                "html_url": f"https://example.test/actions/{run_id}",
                "head_commit": {"timestamp": None, "message": "scheduled refresh"},
            }
        ],
    }


def _retain_args(tmp_path: Path, raw: dict[str, Any]) -> argparse.Namespace:
    (tmp_path / "actions-raw.json").write_text(json.dumps([raw]), encoding="utf-8")
    (tmp_path / "issues-raw.json").write_text(json.dumps([[]]), encoding="utf-8")
    (tmp_path / "cancelled").mkdir(exist_ok=True)
    return argparse.Namespace(
        actions_raw=tmp_path / "actions-raw.json",
        issues_raw=tmp_path / "issues-raw.json",
        cancellations_dir=tmp_path / "cancelled",
        repository="example/project",
        workflow="pages.yml",
        window_start="2026-01-01T00:00:00Z",
        window_end="2026-01-15T00:00:00Z",
        collected_at="2026-01-15T00:01:00Z",
        out_dir=tmp_path / "out",
    )


def test_dora_retention_refuses_a_cancelled_run_whose_cause_was_not_collected(
    tmp_path: Path,
) -> None:
    """The half that makes the rest of this trustworthy.

    If a fetch fails in the collector, the cheap outcome is a retained window in which a cancelled
    run simply has no cause -- and a reader that defaults a missing cause to "not a failure" has
    rebuilt the blindness with more code. So retention stops.
    """
    args = _retain_args(tmp_path, _raw_actions("cancelled"))
    with pytest.raises(dora_evidence.EvidenceError, match="missing job evidence"):
        dora_evidence.retain(args)


def test_dora_retention_refuses_a_job_with_no_retained_annotations(tmp_path: Path) -> None:
    args = _retain_args(tmp_path, _raw_actions("cancelled"))
    (args.cancellations_dir / "run-2.jobs.json").write_text(
        json.dumps([{"total_count": 1, "jobs": [{"id": 99, "name": "build", "steps": []}]}]),
        encoding="utf-8",
    )
    with pytest.raises(dora_evidence.EvidenceError, match="missing annotations for job 99"):
        dora_evidence.retain(args)


def test_dora_retention_refuses_cancellation_evidence_from_another_window(tmp_path: Path) -> None:
    """A collection directory reused across windows would classify this window from the last."""
    args = _retain_args(tmp_path, _raw_actions("success"))
    (args.cancellations_dir / "run-7.jobs.json").write_text(
        json.dumps([{"total_count": 0, "jobs": []}]), encoding="utf-8"
    )
    with pytest.raises(dora_evidence.EvidenceError, match="not from this window"):
        dora_evidence.retain(args)


def test_dora_retention_classifies_and_attaches_the_cause(tmp_path: Path) -> None:
    args = _retain_args(tmp_path, _raw_actions("cancelled"))
    (args.cancellations_dir / "run-2.jobs.json").write_text(
        json.dumps(
            [
                {
                    "total_count": 1,
                    "jobs": [
                        {
                            "id": 99,
                            "name": "build-and-deploy",
                            "conclusion": "cancelled",
                            "started_at": "2026-01-05T21:24:06Z",
                            "completed_at": "2026-01-05T22:09:20Z",
                            "steps": [{"number": index} for index in range(8)],
                        }
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )
    (args.cancellations_dir / "job-99.annotations.json").write_text(
        json.dumps([[{"annotation_level": "failure", "message": TIMEOUT_KILL_MESSAGE}]]),
        encoding="utf-8",
    )
    dora_evidence.retain(args)
    retained = json.loads((args.out_dir / "actions.json").read_text(encoding="utf-8"))
    assert retained["schema_version"] == 2, "a v1 document cannot say why a run was cancelled"
    cancellation = retained["records"][0]["cancellation"]
    assert cancellation["cause"] == "timeout_kill"
    assert cancellation["jobs"][0]["steps"] == 8, (
        "the step count is retained because a job that never got a runner reports zero of them"
    )


def test_dora_refuses_a_cancellation_object_on_a_run_that_was_not_cancelled() -> None:
    seen: set[int] = set()
    record = _run(
        1,
        event="push",
        conclusion="success",
        created="2026-01-02T00:30:00Z",
        updated="2026-01-02T01:00:00Z",
        commit="2026-01-02T00:00:00Z",
        title="feat: ship",
        cancellation=_cancellation("timeout_kill", messages=(TIMEOUT_KILL_MESSAGE,)),
    )
    with pytest.raises(dora_evidence.EvidenceError, match="only a cancelled run"):
        dora_evidence._validate_action_record(record, 0, seen)


def test_dora_cancelled_run_ids_and_job_ids_drive_the_collector() -> None:
    """The workflow's two loops read these, so an empty list here is a silently empty collection."""
    raw = [_raw_actions("cancelled", run_id=11), _raw_actions("success", run_id=12)]
    assert dora_evidence.cancelled_run_ids(raw) == [11]
    jobs_export = [{"total_count": 2, "jobs": [{"id": 5}, {"id": 6}]}]
    assert dora_evidence.job_ids(jobs_export) == [5, 6]


def test_dora_flattening_refuses_a_cancelled_run_with_no_cause_of_its_own() -> None:
    """The second guard, tested where the first one cannot mask it.

    ``retain`` refuses through ``load_cancellations`` before the flattener is reached, so a
    negative control planted in the flattener passed the whole suite. Both guards are wanted --
    the collector's, and the flattener's, which protects any caller that assembles the
    cancellation map some other way -- and a guard no test can fail is not a guard.
    """
    raw = [_raw_actions("cancelled", run_id=42)]
    with pytest.raises(dora_evidence.EvidenceError, match="run 42 has no retained cancellation"):
        dora_evidence._flatten_actions(raw, {})
    attached = dora_evidence._flatten_actions(
        raw, {42: _cancellation("timeout_kill", messages=(TIMEOUT_KILL_MESSAGE,))}
    )
    assert attached[0]["cancellation"]["cause"] == "timeout_kill"


def test_dora_schema_refuses_a_cancelled_record_carrying_no_cause() -> None:
    """The schema half, which guards evidence this process did not produce.

    ``retain`` cannot emit such a record, so no test through ``retain`` can fail if the schema
    rule is deleted -- a negative control proved exactly that. But ``check`` also validates
    evidence read off disk: a hand-edited `docs/audits/dora/actions.json`, or a 90-day artifact
    retained before schema 2, would otherwise arrive with cancelled runs and no cause and be
    scored as if none of them had failed.
    """
    seen: set[int] = set()
    record = _run(
        2,
        event="schedule",
        conclusion="cancelled",
        created="2026-01-05T21:24:04Z",
        updated="2026-01-05T22:09:21Z",
        commit=None,
        title="scheduled refresh",
    )
    assert "cancellation" not in record
    with pytest.raises(dora_evidence.EvidenceError, match="must carry a cancellation object"):
        dora_evidence._validate_action_record(record, 0, seen)
    record["cancellation"] = {"cause": "not_a_cause_this_reader_knows", "jobs": []}
    with pytest.raises(dora_evidence.EvidenceError, match="is not one this reader classifies"):
        dora_evidence._validate_action_record(record, 0, set())
