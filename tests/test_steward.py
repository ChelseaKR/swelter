"""The steward plan: offline nodes first, expired corrections, then coverage gaps — every
action evidence-cited, and never a ranking of neighborhoods."""

from __future__ import annotations

from typing import Any

from swelter import qc, steward
from swelter.calibrate import Correction

from .conftest import make_obs

LATEST = "2026-06-08T00:00:00Z"


def _correction(
    *,
    node_id: str = "node-01",
    parameter: str = "pm25_ugm3",
    window_end: str,
) -> Correction:
    return Correction(
        version=f"{parameter}.epa-humidity.{node_id}",
        node_id=node_id,
        parameter=parameter,
        method="epa-humidity",
        predictors=("raw", "humidity"),
        coefficients=(1.0, 0.0),
        intercept=0.0,
        residual_std=1.0,
        r2=0.9,
        n=10,
        reference="ref-aqs-0001",
        window_start="2026-01-01T00:00:00Z",
        window_end=window_end,
    )


def _health(nodes: list[dict[str, Any]], latest: str = LATEST) -> dict[str, Any]:
    return {"interval_s": 3600.0, "latest": latest, "summary": {}, "nodes": nodes, "gaps": []}


def _coverage(cells: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "summary": {},
        "cells": cells,
        "note": "Descriptive coverage of calibration, not a ranking of neighborhoods.",
    }


def test_offline_node_is_top_priority_action() -> None:
    health = _health(
        [
            {
                "node_id": "node-07",
                "status": "offline",
                "observations": 10,
                "completeness": 0.4,
                "flagged_fraction": 0.1,
                "online": False,
                "last_seen": "2026-06-06T00:00:00Z",
            }
        ]
    )
    result = steward.plan(health, _coverage([]), [], latest=LATEST)
    assert result["actions"], "expected at least one action"
    top = result["actions"][0]
    assert top["kind"] == "node_offline"
    assert top["subject"] == "node-07"
    assert "48.0h" in top["reason"] or "48h" in top["reason"]
    assert top["evidence"]["source"] == "qc.health_report"
    assert top["evidence"]["hours_since_last_seen"] == 48.0


def test_degraded_node_ranked_below_offline() -> None:
    health = _health(
        [
            {
                "node_id": "node-degraded",
                "status": "degraded",
                "observations": 100,
                "completeness": 0.8,
                "flagged_fraction": 0.2,
                "online": True,
                "last_seen": LATEST,
            },
            {
                "node_id": "node-offline",
                "status": "offline",
                "observations": 10,
                "completeness": 0.4,
                "flagged_fraction": 0.1,
                "online": False,
                "last_seen": "2026-06-06T00:00:00Z",
            },
        ]
    )
    result = steward.plan(health, _coverage([]), [], latest=LATEST)
    kinds = [a["kind"] for a in result["actions"]]
    assert kinds.index("node_offline") < kinds.index("node_degraded")


def test_ok_node_produces_no_action() -> None:
    health = _health(
        [
            {
                "node_id": "node-ok",
                "status": "ok",
                "observations": 100,
                "completeness": 1.0,
                "flagged_fraction": 0.0,
                "online": True,
                "last_seen": LATEST,
            }
        ]
    )
    result = steward.plan(health, _coverage([]), [], latest=LATEST)
    assert result["actions"] == []


def test_expired_correction_flagged_overdue() -> None:
    # window_end 400 days before latest, max age 365 → overdue.
    correction = _correction(window_end="2025-05-04T00:00:00Z")
    result = steward.plan(
        _health([]), _coverage([]), [correction], latest=LATEST, correction_max_age_days=365.0
    )
    actions = result["actions"]
    assert len(actions) == 1
    assert actions[0]["kind"] == "correction_expired"
    assert actions[0]["subject"] == "node-01/pm25_ugm3"
    assert actions[0]["evidence"]["source"].startswith("calibrate.CorrectionRegistry")
    assert actions[0]["evidence"]["overdue_days"] > 0


def test_expiring_soon_correction_flagged_before_expiry() -> None:
    # 320 days old: past 0.85 * 365 ≈ 310.25 (the "expiring soon" threshold) but not yet 365.
    correction = _correction(window_end="2025-07-23T00:00:00Z")
    result = steward.plan(
        _health([]), _coverage([]), [correction], latest=LATEST, correction_max_age_days=365.0
    )
    actions = result["actions"]
    assert len(actions) == 1
    assert actions[0]["kind"] == "correction_expiring"
    assert "expires in" in actions[0]["reason"]
    assert actions[0]["evidence"]["days_remaining"] > 0


def test_fresh_correction_produces_no_action() -> None:
    correction = _correction(window_end="2026-06-01T00:00:00Z")  # a week old
    result = steward.plan(
        _health([]), _coverage([]), [correction], latest=LATEST, correction_max_age_days=365.0
    )
    assert result["actions"] == []


def test_provisional_cell_yields_coverage_action_ordered_by_calibrated_count() -> None:
    cells = [
        {
            "cell_id": "c-few",
            "label": "Cedar & 4th",
            "nodes": 2,
            "calibrated_nodes": 1,
            "raw_nodes": 1,
            "confirmed": False,
        },
        {
            "cell_id": "c-none",
            "label": "Oak & 4th",
            "nodes": 1,
            "calibrated_nodes": 0,
            "raw_nodes": 1,
            "confirmed": False,
        },
        {
            "cell_id": "c-confirmed",
            "label": "Elm & 5th",
            "nodes": 1,
            "calibrated_nodes": 1,
            "raw_nodes": 0,
            "confirmed": True,
        },
    ]
    result = steward.plan(_health([]), _coverage(cells), [], latest=LATEST)
    actions = result["actions"]
    assert [a["subject"] for a in actions] == ["c-none", "c-few"]
    assert all(a["kind"] == "coverage_gap" for a in actions)
    # ascending calibrated_nodes: the zero-calibrated cell comes first.
    assert actions[0]["evidence"]["calibrated_nodes"] == 0
    assert actions[1]["evidence"]["calibrated_nodes"] == 1
    # the coverage_equity note travels verbatim into the evidence.
    assert "ranking of neighborhoods" in actions[0]["evidence"]["note"]


def test_empty_store_yields_empty_action_list() -> None:
    result = steward.plan(_health([]), _coverage([]), [], latest=LATEST)
    assert result["actions"] == []
    assert result["generated_for"] == LATEST


def test_disclaimer_and_note_present() -> None:
    result = steward.plan(_health([]), _coverage([]), [], latest=LATEST)
    assert "collective disposes" in result["disclaimer"]
    assert "neighborhoods" in result["disclaimer"]


def test_plan_integrates_with_real_health_and_coverage_report() -> None:
    """End-to-end sanity: real qc.health_report / qc.coverage_equity shapes plug in cleanly."""
    obs = [
        make_obs(node_id="node-01", timestamp="2026-06-01T00:00:00Z", value=25.0),
        make_obs(node_id="node-01", timestamp="2026-06-01T01:00:00Z", value=25.0),
    ]
    node_cells = {"node-01": ("c1", "Cedar & 4th")}
    coverage = qc.coverage_equity(obs, node_cells)
    health = qc.health_report(obs, expected_interval_s=3600.0, coverage=coverage)
    latest = str(health["latest"])
    result = steward.plan(health, coverage, [], latest=latest)
    assert result["generated_for"] == latest
    # node-01 is raw-only here, so its cell is a coverage gap.
    assert any(a["kind"] == "coverage_gap" for a in result["actions"])
