"""The steward console: compose existing signals into a ranked "what needs doing" list.

Everything a 2 a.m. steward needs to decide the next physical action already exists somewhere in
swelter's output — ``qc.health_report`` (offline/degraded nodes), ``qc.coverage_equity``
(calibration coverage gaps), and the correction registry (calibration age). Nobody had composed
them into one ranked, evidence-cited list. This module does exactly that and nothing else: no
new fetching, no new state, pure functions over data the pipeline already produced.

Three signal families feed the plan, each producing :class:`Action` entries:

* **Node liveness.** Offline nodes rank above degraded nodes — a silent node is a bigger service
  gap than a noisy one.
* **Correction age (FIX-03).** A calibration fitted from a co-location window that ended long ago
  is stale evidence; this flags corrections that have expired or are about to.
* **Coverage gaps.** Cells with no calibrated node at all are a co-location-planning queue,
  ordered *only* by how few calibrated nodes they have — never by neighborhood characteristics
  (audit B4/B5; the same refusal ``qc.coverage_equity`` already encodes).

The tool proposes; the collective disposes. Every action names its evidence so a steward — or an
auditor — can check the recommendation against the number that produced it, not just trust it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .calibrate import Correction
from .models import parse_timestamp

#: Priority bands, lowest number ranks first. Offline nodes are the most urgent physical action;
#: coverage-equity co-location planning is real work but never as urgent as a node gone dark.
_PRIORITY_OFFLINE = 0
_PRIORITY_EXPIRED_CORRECTION = 1
_PRIORITY_DEGRADED = 2
_PRIORITY_EXPIRING_CORRECTION = 3
_PRIORITY_COVERAGE_GAP = 4

#: Default fraction of ``correction_max_age_days`` at which a still-valid correction is flagged
#: "expiring soon" — early enough that a steward can schedule a new co-location window before the
#: correction actually goes stale.
_EXPIRING_SOON_FRACTION = 0.85

DISCLAIMER = (
    "The tool proposes; the collective disposes. Descriptive ordering only — never a ranking of "
    "neighborhoods (audit B4/B5)."
)


@dataclass(frozen=True)
class Action:
    """One ranked, evidence-cited item on the steward's "what needs doing" list.

    ``priority`` is the sort key (lower ranks first); ``evidence`` is a JSON-able dict naming the
    source signal and its numbers, so every recommendation can be checked against the data that
    produced it rather than just trusted.
    """

    priority: int
    kind: str
    subject: str
    reason: str
    evidence: dict[str, Any] = field(default_factory=dict)


def _node_actions(health: dict[str, Any]) -> list[Action]:
    actions: list[Action] = []
    latest = health.get("latest")
    for node in health.get("nodes", []):
        status = node.get("status")
        if status not in ("offline", "degraded"):
            continue
        node_id = str(node.get("node_id", ""))
        completeness = node.get("completeness", 1.0)
        flagged_fraction = node.get("flagged_fraction", 0.0)
        last_seen = node.get("last_seen")
        hours_silent: float | None = None
        if latest and last_seen:
            hours_silent = (
                parse_timestamp(latest) - parse_timestamp(last_seen)
            ).total_seconds() / 3600.0

        if status == "offline":
            silence = (
                f"{hours_silent:.1f}h since last seen"
                if hours_silent is not None
                else ("no recent reading")
            )
            actions.append(
                Action(
                    priority=_PRIORITY_OFFLINE,
                    kind="node_offline",
                    subject=node_id,
                    reason=(
                        f"node {node_id} is offline ({silence}); "
                        f"{completeness * 100:.0f}% complete, "
                        f"{flagged_fraction * 100:.0f}% flagged while live"
                    ),
                    evidence={
                        "source": "qc.health_report",
                        "node_id": node_id,
                        "status": status,
                        "last_seen": last_seen,
                        "hours_since_last_seen": (
                            round(hours_silent, 1) if hours_silent is not None else None
                        ),
                        "completeness": completeness,
                        "flagged_fraction": flagged_fraction,
                    },
                )
            )
        else:  # degraded
            silence = (
                f"{hours_silent:.1f}h since last seen"
                if hours_silent is not None
                else ("last seen recently")
            )
            actions.append(
                Action(
                    priority=_PRIORITY_DEGRADED,
                    kind="node_degraded",
                    subject=node_id,
                    reason=(
                        f"node {node_id} is degraded ({silence}); "
                        f"{completeness * 100:.0f}% complete, "
                        f"{flagged_fraction * 100:.0f}% flagged"
                    ),
                    evidence={
                        "source": "qc.health_report",
                        "node_id": node_id,
                        "status": status,
                        "last_seen": last_seen,
                        "hours_since_last_seen": (
                            round(hours_silent, 1) if hours_silent is not None else None
                        ),
                        "completeness": completeness,
                        "flagged_fraction": flagged_fraction,
                    },
                )
            )
    return actions


def _correction_actions(
    corrections: list[Correction], *, latest: str, correction_max_age_days: float
) -> list[Action]:
    actions: list[Action] = []
    latest_dt = parse_timestamp(latest)
    expiring_at = _EXPIRING_SOON_FRACTION * correction_max_age_days
    for correction in corrections:
        if not correction.window_end:
            continue
        age_days = (latest_dt - parse_timestamp(correction.window_end)).total_seconds() / 86400.0
        if age_days > correction_max_age_days:
            overdue = age_days - correction_max_age_days
            actions.append(
                Action(
                    priority=_PRIORITY_EXPIRED_CORRECTION,
                    kind="correction_expired",
                    subject=f"{correction.node_id}/{correction.parameter}",
                    reason=(
                        f"{correction.node_id}/{correction.parameter} correction "
                        f"({correction.version}) is {overdue:.0f} day(s) past its "
                        f"{correction_max_age_days:.0f}-day max age — recalibrate"
                    ),
                    evidence={
                        "source": "calibrate.CorrectionRegistry (FIX-03 correction age)",
                        "node_id": correction.node_id,
                        "parameter": correction.parameter,
                        "version": correction.version,
                        "window_end": correction.window_end,
                        "age_days": round(age_days, 1),
                        "max_age_days": correction_max_age_days,
                        "overdue_days": round(overdue, 1),
                    },
                )
            )
        elif age_days >= expiring_at:
            remaining = correction_max_age_days - age_days
            actions.append(
                Action(
                    priority=_PRIORITY_EXPIRING_CORRECTION,
                    kind="correction_expiring",
                    subject=f"{correction.node_id}/{correction.parameter}",
                    reason=(
                        f"{correction.node_id}/{correction.parameter} correction "
                        f"({correction.version}) expires in "
                        f"{remaining / 7:.1f} week(s) — schedule a new co-location window"
                    ),
                    evidence={
                        "source": "calibrate.CorrectionRegistry (FIX-03 correction age)",
                        "node_id": correction.node_id,
                        "parameter": correction.parameter,
                        "version": correction.version,
                        "window_end": correction.window_end,
                        "age_days": round(age_days, 1),
                        "max_age_days": correction_max_age_days,
                        "days_remaining": round(remaining, 1),
                    },
                )
            )
    return actions


def _coverage_actions(coverage: dict[str, Any]) -> list[Action]:
    cells = [c for c in coverage.get("cells", []) if not c.get("confirmed", True)]
    # Descriptive coverage only: order by ascending calibrated_nodes (a cell with zero calibrated
    # nodes is a more urgent co-location target than one that already has some), never by any
    # neighborhood characteristic — same boundary qc.coverage_equity's own docstring draws.
    cells.sort(key=lambda c: (c.get("calibrated_nodes", 0), c.get("cell_id", "")))
    note = coverage.get("note", "")
    actions: list[Action] = []
    for cell in cells:
        cell_id = str(cell.get("cell_id", ""))
        label = cell.get("label") or cell_id
        actions.append(
            Action(
                priority=_PRIORITY_COVERAGE_GAP,
                kind="coverage_gap",
                subject=cell_id,
                reason=(
                    f"cell {label} has no calibrated node "
                    f"({cell.get('calibrated_nodes', 0)}/{cell.get('nodes', 0)} calibrated) — "
                    "next co-location candidate"
                ),
                evidence={
                    "source": "qc.coverage_equity",
                    "cell_id": cell_id,
                    "label": cell.get("label", ""),
                    "nodes": cell.get("nodes", 0),
                    "calibrated_nodes": cell.get("calibrated_nodes", 0),
                    "raw_nodes": cell.get("raw_nodes", 0),
                    "note": note,
                },
            )
        )
    return actions


def plan(
    health: dict[str, Any],
    coverage: dict[str, Any],
    corrections: list[Correction],
    *,
    latest: str,
    correction_max_age_days: float = 365.0,
) -> dict[str, Any]:
    """Compose health, coverage-equity, and correction-age signals into one ranked plan.

    Nothing here fetches or computes new numbers — ``health`` (:func:`qc.health_report`),
    ``coverage`` (:func:`qc.coverage_equity`), and ``corrections`` (a
    :class:`calibrate.CorrectionRegistry`'s ``.all()``) are all signals the pipeline already
    produces. ``latest`` anchors "how long ago" math (hours offline, correction age) to the same
    reference timestamp the rest of the pipeline uses, so the plan and the health report agree.
    """
    actions: list[Action] = []
    actions.extend(_node_actions(health))
    actions.extend(
        _correction_actions(
            corrections, latest=latest, correction_max_age_days=correction_max_age_days
        )
    )
    actions.extend(_coverage_actions(coverage))

    # Stable sort on priority band only: each generator above already produced its own
    # deterministic order within a band (health.nodes is node_id-sorted, corrections come from a
    # sorted registry, coverage gaps are pre-sorted ascending by calibrated_nodes) — a Python sort
    # is stable, so that intra-band order survives instead of being overridden by a tiebreak key.
    actions.sort(key=lambda a: a.priority)

    return {
        "generated_for": latest,
        "actions": [
            {
                "priority": a.priority,
                "kind": a.kind,
                "subject": a.subject,
                "reason": a.reason,
                "evidence": a.evidence,
            }
            for a in actions
        ],
        "disclaimer": DISCLAIMER,
    }
