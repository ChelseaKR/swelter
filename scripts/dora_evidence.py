#!/usr/bin/env python3
"""Retain, generate, and verify deterministic DORA evidence from GitHub JSON exports."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ACTIONS = ROOT / "docs" / "audits" / "dora" / "actions.json"
DEFAULT_ISSUES = ROOT / "docs" / "audits" / "dora" / "issues.json"
DEFAULT_SNAPSHOT = ROOT / "docs" / "audits" / "dora" / "snapshot.json"
DEFAULT_MARKDOWN = ROOT / "docs" / "DORA.md"

FAILED_CONCLUSIONS = frozenset({"failure", "timed_out", "action_required", "startup_failure"})
REWORK_TITLE = re.compile(r"^(?:fix(?:\([^)]+\))?[!:]?|FIX-\d+\b)", re.IGNORECASE)


class EvidenceError(ValueError):
    """Raised when retained evidence does not satisfy the fail-closed schema."""


def _timestamp(value: Any, label: str) -> datetime:
    if not isinstance(value, str):
        raise EvidenceError(f"{label} must be an RFC 3339 string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EvidenceError(f"{label} is not an RFC 3339 timestamp: {value!r}") from exc
    if parsed.tzinfo is None:
        raise EvidenceError(f"{label} must include a UTC offset")
    return parsed.astimezone(UTC)


def _canonical_json(document: Any) -> bytes:
    return (json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode()


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvidenceError(f"{path}: invalid or missing JSON ({exc})") from exc


def _write_json(path: Path, document: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_canonical_json(document))


def _flatten_actions(raw: Any) -> list[dict[str, Any]]:
    pages = raw if isinstance(raw, list) else [raw]
    records: list[dict[str, Any]] = []
    for page in pages:
        if not isinstance(page, dict) or not isinstance(page.get("workflow_runs"), list):
            raise EvidenceError(
                "Actions export must be an object or slurped list with workflow_runs"
            )
        for item in page["workflow_runs"]:
            if not isinstance(item, dict):
                raise EvidenceError("Actions workflow_runs entries must be objects")
            head_commit = item.get("head_commit")
            commit_timestamp = (
                head_commit.get("timestamp") if isinstance(head_commit, dict) else None
            )
            commit_message = head_commit.get("message") if isinstance(head_commit, dict) else None
            title = item.get("display_title")
            if not isinstance(title, str) and isinstance(commit_message, str):
                title = commit_message.splitlines()[0]
            records.append(
                {
                    "id": item.get("id"),
                    "event": item.get("event"),
                    "status": item.get("status"),
                    "conclusion": item.get("conclusion"),
                    "head_sha": item.get("head_sha"),
                    "commit_timestamp": commit_timestamp,
                    "created_at": item.get("created_at"),
                    "updated_at": item.get("updated_at"),
                    "display_title": title,
                    "url": item.get("html_url"),
                }
            )
    return sorted(records, key=lambda record: (str(record.get("created_at")), record.get("id", 0)))


def _flatten_issues(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        raise EvidenceError("Issues export must be a list or a slurped list of pages")
    pages = raw if raw and all(isinstance(page, list) for page in raw) else [raw]
    records: list[dict[str, Any]] = []
    for page in pages:
        if not isinstance(page, list):
            raise EvidenceError("Issues slurped page must be a list")
        for item in page:
            if not isinstance(item, dict):
                raise EvidenceError("Issues entries must be objects")
            if "pull_request" in item:
                continue
            records.append(
                {
                    "number": item.get("number"),
                    "title": item.get("title"),
                    "state": item.get("state"),
                    "created_at": item.get("created_at"),
                    "closed_at": item.get("closed_at"),
                    "url": item.get("html_url"),
                }
            )
    return sorted(
        records, key=lambda record: (str(record.get("created_at")), record.get("number", 0))
    )


def _issues_overlapping_window(
    records: list[dict[str, Any]], window_start: str, window_end: str
) -> list[dict[str, Any]]:
    start = _timestamp(window_start, "window start")
    end = _timestamp(window_end, "window end")
    retained: list[dict[str, Any]] = []
    for record in records:
        opened = _timestamp(record.get("created_at"), "incident created_at")
        closed_value = record.get("closed_at")
        closed = None if closed_value is None else _timestamp(closed_value, "incident closed_at")
        if opened <= end and (closed is None or closed >= start):
            retained.append(record)
    return retained


def _retained_document(
    *,
    kind: str,
    repository: str,
    records: list[dict[str, Any]],
    endpoint: str,
    parameters: dict[str, Any],
    window_start: str,
    window_end: str,
    collected_at: str,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": kind,
        "repository": repository,
        "query": {
            "source": "GitHub REST API",
            "endpoint": endpoint,
            "parameters": parameters,
            "pagination": "gh api --paginate --slurp",
            "window_start": window_start,
            "window_end": window_end,
        },
        "collection": {"complete": True, "collected_at": collected_at},
        "records": records,
    }


def retain(args: argparse.Namespace) -> None:
    start = _timestamp(args.window_start, "window start")
    end = _timestamp(args.window_end, "window end")
    collected = _timestamp(args.collected_at, "collection time")
    if start >= end:
        raise EvidenceError("window start must precede window end")
    if collected < end:
        raise EvidenceError("collection time must be at or after window end")
    actions = _retained_document(
        kind="github_actions",
        repository=args.repository,
        records=_flatten_actions(_read_json(args.actions_raw)),
        endpoint=f"/repos/{args.repository}/actions/workflows/{args.workflow}/runs",
        parameters={
            "created": f"{args.window_start}..{args.window_end}",
            "per_page": 100,
        },
        window_start=args.window_start,
        window_end=args.window_end,
        collected_at=args.collected_at,
    )
    issues = _retained_document(
        kind="github_issues",
        repository=args.repository,
        records=_issues_overlapping_window(
            _flatten_issues(_read_json(args.issues_raw)), args.window_start, args.window_end
        ),
        endpoint=f"/repos/{args.repository}/issues",
        parameters={
            "labels": "incident",
            "state": "all",
            "per_page": 100,
        },
        window_start=args.window_start,
        window_end=args.window_end,
        collected_at=args.collected_at,
    )
    _write_json(args.out_dir / "actions.json", actions)
    _write_json(args.out_dir / "issues.json", issues)


def _validate_query(query: Any, kind: str) -> None:
    if not isinstance(query, dict):
        raise EvidenceError(f"{kind}: query metadata must be an object")
    for field in ("source", "endpoint", "parameters", "pagination", "window_start", "window_end"):
        if field not in query:
            raise EvidenceError(f"{kind}: query metadata missing {field}")
    start = _timestamp(query["window_start"], f"{kind} window_start")
    end = _timestamp(query["window_end"], f"{kind} window_end")
    if start >= end:
        raise EvidenceError(f"{kind}: window start must precede window end")


def _validate_collection(collection: Any, kind: str) -> None:
    if not isinstance(collection, dict) or not isinstance(collection.get("complete"), bool):
        raise EvidenceError(f"{kind}: collection.complete must be boolean")
    _timestamp(collection.get("collected_at"), f"{kind} collected_at")
    if not collection["complete"] and not collection.get("reason"):
        raise EvidenceError(f"{kind}: incomplete collection needs a reason")


def _validate_input(document: Any, kind: str) -> dict[str, Any]:
    if not isinstance(document, dict):
        raise EvidenceError(f"{kind}: top level must be an object")
    if document.get("schema_version") != 1 or document.get("kind") != kind:
        raise EvidenceError(f"{kind}: unsupported schema_version or kind")
    if not isinstance(document.get("repository"), str) or not document["repository"]:
        raise EvidenceError(f"{kind}: repository must be non-empty")
    _validate_query(document.get("query"), kind)
    _validate_collection(document.get("collection"), kind)
    records = document.get("records")
    if not isinstance(records, list):
        raise EvidenceError(f"{kind}: records must be a list")
    return document


def _validate_action_times(record: dict[str, Any], label: str) -> None:
    created = _timestamp(record.get("created_at"), f"{label} created_at")
    updated = _timestamp(record.get("updated_at"), f"{label} updated_at")
    if updated < created:
        raise EvidenceError(f"{label}: updated_at precedes created_at")
    if record.get("commit_timestamp") is not None:
        committed = _timestamp(record["commit_timestamp"], f"{label} commit_timestamp")
        if committed > updated:
            raise EvidenceError(f"{label}: commit_timestamp follows run completion")


def _validate_action_record(record: Any, index: int, seen: set[int]) -> None:
    label = f"github_actions record {index}"
    if not isinstance(record, dict):
        raise EvidenceError(f"{label}: must be an object")
    if not isinstance(record.get("id"), int) or isinstance(record.get("id"), bool):
        raise EvidenceError(f"{label}: id must be an integer")
    if record["id"] in seen:
        raise EvidenceError(f"{label}: duplicate id {record['id']}")
    seen.add(record["id"])
    for field in ("event", "status", "head_sha", "display_title", "url"):
        if not isinstance(record.get(field), str):
            raise EvidenceError(f"{label}: {field} must be a string")
    _validate_action_times(record, label)
    if record.get("conclusion") is not None and not isinstance(record["conclusion"], str):
        raise EvidenceError(f"{label}: conclusion must be string or null")


def _validate_issue_record(record: Any, index: int, seen: set[int]) -> None:
    label = f"github_issues record {index}"
    if not isinstance(record, dict):
        raise EvidenceError(f"{label}: must be an object")
    if not isinstance(record.get("number"), int) or isinstance(record.get("number"), bool):
        raise EvidenceError(f"{label}: number must be an integer")
    if record["number"] in seen:
        raise EvidenceError(f"{label}: duplicate number {record['number']}")
    seen.add(record["number"])
    for field in ("title", "state", "created_at", "url"):
        if not isinstance(record.get(field), str):
            raise EvidenceError(f"{label}: {field} must be a string")
    _timestamp(record["created_at"], f"{label} created_at")
    if record.get("closed_at") is not None:
        closed = _timestamp(record["closed_at"], f"{label} closed_at")
        opened = _timestamp(record["created_at"], f"{label} created_at")
        if closed < opened:
            raise EvidenceError(f"{label}: closed_at precedes created_at")


def _validate_window_coverage(actions: dict[str, Any], issues: dict[str, Any]) -> None:
    start = _timestamp(actions["query"]["window_start"], "window_start")
    end = _timestamp(actions["query"]["window_end"], "window_end")
    for record in actions["records"]:
        created = _timestamp(record["created_at"], "Actions created_at")
        if not start <= created <= end:
            raise EvidenceError(f"Actions run {record['id']} falls outside the declared window")
    for record in issues["records"]:
        opened = _timestamp(record["created_at"], "incident created_at")
        closed_value = record.get("closed_at")
        closed = None if closed_value is None else _timestamp(closed_value, "incident closed_at")
        if opened > end or (closed is not None and closed < start):
            raise EvidenceError(
                f"incident #{record['number']} does not overlap the declared window"
            )


def _validate_records(actions: dict[str, Any], issues: dict[str, Any]) -> None:
    action_ids: set[int] = set()
    for index, record in enumerate(actions["records"]):
        _validate_action_record(record, index, action_ids)

    issue_numbers: set[int] = set()
    for index, record in enumerate(issues["records"]):
        _validate_issue_record(record, index, issue_numbers)


def _load_inputs(actions_path: Path, issues_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    actions = _validate_input(_read_json(actions_path), "github_actions")
    issues = _validate_input(_read_json(issues_path), "github_issues")
    if actions["repository"] != issues["repository"]:
        raise EvidenceError("Actions and issues evidence name different repositories")
    for field in ("window_start", "window_end"):
        if actions["query"][field] != issues["query"][field]:
            raise EvidenceError(f"Actions and issues {field} differ")
    _validate_records(actions, issues)
    _validate_window_coverage(actions, issues)
    return actions, issues


def _percentile(values: list[float], proportion: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * proportion
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return ordered[low]
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def _metric_unavailable(reason: str) -> dict[str, Any]:
    return {"status": "unavailable", "reason": reason}


def _complete_metrics(actions: dict[str, Any], issues: dict[str, Any]) -> dict[str, Any]:
    start = _timestamp(actions["query"]["window_start"], "window_start")
    end = _timestamp(actions["query"]["window_end"], "window_end")
    window_days = (end - start).total_seconds() / 86400
    completed = [record for record in actions["records"] if record["status"] == "completed"]
    successful = [record for record in completed if record["conclusion"] == "success"]
    failures = [record for record in completed if record["conclusion"] in FAILED_CONCLUSIONS]
    cancellations = [record for record in completed if record["conclusion"] == "cancelled"]
    attempts = [*successful, *failures]
    change_deploys = [record for record in successful if record["event"] == "push"]

    deployment_frequency = {
        "status": "pass" if successful and window_days / len(successful) <= 14 else "alert",
        "successful_deployments": len(successful),
        "change_triggered": len(change_deploys),
        "scheduled": sum(record["event"] == "schedule" for record in successful),
        "window_days": round(window_days, 4),
        "deployments_per_week": round(len(successful) * 7 / window_days, 4),
        "target": "at least one successful deployment per 14 days",
    }

    lead_hours = [
        (
            _timestamp(record["updated_at"], "run updated_at")
            - _timestamp(record["commit_timestamp"], "commit timestamp")
        ).total_seconds()
        / 3600
        for record in change_deploys
        if record.get("commit_timestamp") is not None
    ]
    if len(lead_hours) != len(change_deploys):
        change_lead_time = _metric_unavailable(
            f"{len(change_deploys) - len(lead_hours)} successful push run(s) lacked a "
            "retained commit timestamp"
        )
        change_lead_time["sample_size"] = len(lead_hours)
    elif not lead_hours:
        change_lead_time = {"status": "no_event", "sample_size": 0, "target": "P90 under 24 hours"}
    else:
        p50 = _percentile(lead_hours, 0.5)
        p90 = _percentile(lead_hours, 0.9)
        if p50 is None or p90 is None:
            raise EvidenceError("lead-time percentile calculation unexpectedly had no samples")
        change_lead_time = {
            "status": "pass" if p90 < 24 else "alert",
            "sample_size": len(lead_hours),
            "p50_hours": round(p50, 4),
            "p90_hours": round(p90, 4),
            "target": "P90 under 24 hours",
        }

    failure_rate = len(failures) / len(attempts) if attempts else None
    change_fail_rate = {
        "status": "no_event"
        if failure_rate is None
        else ("pass" if failure_rate < 0.15 else "alert"),
        "failed_attempts": len(failures),
        "completed_attempts": len(attempts),
        "cancelled_runs": len(cancellations),
        "rate": None if failure_rate is None else round(failure_rate, 6),
        "target": "under 15%",
    }

    recovery_hours: list[float] = []
    open_events: list[str] = []
    success_times = sorted(
        _timestamp(record["updated_at"], "run updated_at") for record in successful
    )
    for record in failures:
        failed_at = _timestamp(record["updated_at"], "failed run updated_at")
        recovery = next((candidate for candidate in success_times if candidate > failed_at), None)
        if recovery is None:
            open_events.append(f"workflow run {record['id']}")
        else:
            recovery_hours.append((recovery - failed_at).total_seconds() / 3600)
    for issue in issues["records"]:
        opened = _timestamp(issue["created_at"], "incident created_at")
        closed_value = issue.get("closed_at")
        closed = None if closed_value is None else _timestamp(closed_value, "incident closed_at")
        if closed is None or closed > end:
            open_events.append(f"incident #{issue['number']}")
        else:
            recovery_hours.append((closed - opened).total_seconds() / 3600)
    if open_events:
        recovery_metric = {
            "status": "alert",
            "open_events": open_events,
            "recovered_events": len(recovery_hours),
            "target": "under 24 hours",
        }
    elif recovery_hours:
        maximum = max(recovery_hours)
        recovery_metric = {
            "status": "pass" if maximum < 24 else "alert",
            "open_events": [],
            "recovered_events": len(recovery_hours),
            "p50_hours": round(_percentile(recovery_hours, 0.5) or 0, 4),
            "max_hours": round(maximum, 4),
            "target": "under 24 hours",
        }
    else:
        recovery_metric = {
            "status": "no_event",
            "open_events": [],
            "recovered_events": 0,
            "target": "under 24 hours",
        }

    rework = [record for record in change_deploys if REWORK_TITLE.search(record["display_title"])]
    rework_rate = len(rework) / len(change_deploys) if change_deploys else None
    deployment_rework_rate = {
        "status": "no_event"
        if rework_rate is None
        else ("pass" if rework_rate < 0.10 else "alert"),
        "proxy_matches": len(rework),
        "change_deployments": len(change_deploys),
        "rate": None if rework_rate is None else round(rework_rate, 6),
        "target": "under 10%",
        "proxy": (
            "successful push title begins fix, fix(...), or FIX-NN; human classification "
            "remains required"
        ),
    }
    return {
        "deployment_frequency": deployment_frequency,
        "change_lead_time": change_lead_time,
        "change_fail_rate": change_fail_rate,
        "failed_deployment_recovery_time": recovery_metric,
        "deployment_rework_rate": deployment_rework_rate,
    }


def build_snapshot(
    actions_path: Path, issues_path: Path
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    actions, issues = _load_inputs(actions_path, issues_path)
    actions_digest = hashlib.sha256(actions_path.read_bytes()).hexdigest()
    issues_digest = hashlib.sha256(issues_path.read_bytes()).hexdigest()
    combined_digest = hashlib.sha256(f"{actions_digest}\n{issues_digest}\n".encode()).hexdigest()
    complete = bool(actions["collection"]["complete"] and issues["collection"]["complete"])
    if complete:
        metrics = _complete_metrics(actions, issues)
    else:
        reasons = [
            document["collection"]["reason"]
            for document in (actions, issues)
            if not document["collection"]["complete"]
        ]
        reason = " ".join(dict.fromkeys(reasons))
        metrics = {
            name: _metric_unavailable(reason)
            for name in (
                "deployment_frequency",
                "change_lead_time",
                "change_fail_rate",
                "failed_deployment_recovery_time",
                "deployment_rework_rate",
            )
        }
    collected = max(actions["collection"]["collected_at"], issues["collection"]["collected_at"])
    snapshot = {
        "schema_version": 1,
        "repository": actions["repository"],
        "window": {
            "start": actions["query"]["window_start"],
            "end": actions["query"]["window_end"],
        },
        "generated_at": collected,
        "collection_complete": complete,
        "inputs": {
            "actions_sha256": actions_digest,
            "issues_sha256": issues_digest,
            "combined_sha256": combined_digest,
        },
        "queries": {"actions": actions["query"], "issues": issues["query"]},
        "metrics": metrics,
    }
    return snapshot, actions, issues


def _percent(value: Any) -> str:
    return "N/A" if value is None else f"{float(value) * 100:.1f}%"


def _metric_baseline(name: str, metric: dict[str, Any]) -> str:
    status = metric["status"]
    if status == "unavailable":
        return "Unavailable — retained inputs are incomplete"
    if name == "deployment_frequency":
        return (
            f"{metric['successful_deployments']} successful deploys "
            f"({metric['deployments_per_week']:.2f}/week)"
        )
    if name == "change_lead_time":
        if status == "no_event":
            return "No successful push deployment in the window"
        return f"P50 {metric['p50_hours']:.2f} h; P90 {metric['p90_hours']:.2f} h"
    if name == "change_fail_rate":
        return (
            f"{metric['failed_attempts']} of {metric['completed_attempts']} completed attempts "
            f"({_percent(metric['rate'])}); {metric['cancelled_runs']} cancelled reported "
            "separately"
        )
    if name == "failed_deployment_recovery_time":
        if status == "no_event":
            return "No failed deployment or incident event in the window"
        if metric.get("open_events"):
            return "Open: " + ", ".join(metric["open_events"])
        return f"P50 {metric['p50_hours']:.2f} h; max {metric['max_hours']:.2f} h"
    if name == "deployment_rework_rate":
        return (
            f"{metric['proxy_matches']} of {metric['change_deployments']} change deploys "
            f"({_percent(metric['rate'])}) matched the title proxy"
        )
    raise EvidenceError(f"unknown metric {name}")


def render_markdown(
    snapshot: dict[str, Any], actions: dict[str, Any], issues: dict[str, Any]
) -> str:
    labels = {
        "deployment_frequency": ("Deployment frequency", "At least weekly; alert after 14 days"),
        "change_lead_time": ("Change lead time", "P90 under 1 day"),
        "change_fail_rate": ("Change fail rate", "Under 15%"),
        "failed_deployment_recovery_time": ("Failed-deployment recovery time", "Under 1 day"),
        "deployment_rework_rate": ("Deployment rework rate", "Under 10%"),
    }
    start = snapshot["window"]["start"]
    end = snapshot["window"]["end"]
    digest = snapshot["inputs"]["combined_sha256"]
    lines = [
        "# DORA delivery-health ledger",
        "",
        "This ledger uses the five-metric 2024 DORA model required by the pinned",
        "[`QUALITY-AND-METRICS-STANDARD`](standards/QUALITY-AND-METRICS-STANDARD.md). It is",
        "generated from retained GitHub Actions and incident-issue JSON, not from memory or",
        "hand-maintained deployment counts.",
        "",
        f"Owner: maintainer. Evidence window: {start} through {end}.",
        f"Combined input SHA-256: `{digest}`.",
        "",
    ]
    if not snapshot["collection_complete"]:
        reason = next(
            document["collection"]["reason"]
            for document in (actions, issues)
            if not document["collection"]["complete"]
        )
        lines.extend(
            [
                "> **Evidence incomplete — no performance tier is claimed.** " + reason,
                "> Scheduled CI now collects complete row-level evidence; a maintainer must review",
                "> commit a complete dated snapshot before replacing this fail-closed baseline.",
                "",
            ]
        )
    lines.extend(
        [
            "| Metric | Portfolio target | Baseline | Result |",
            "| --- | --- | --- | --- |",
        ]
    )
    for name, (label, target) in labels.items():
        metric = snapshot["metrics"][name]
        baseline = _metric_baseline(name, metric)
        result = metric["status"].title()
        lines.append(f"| {label} | {target} | {baseline} | {result} |")
    lines.extend(
        [
            "",
            "## Reproduce and verify",
            "",
            "The retained inputs include the API endpoint, parameters, window, pagination method,",
            "collection completeness, and timestamp. The snapshot embeds each input digest plus a",
            "digest. Any record or query-metadata edit therefore changes the snapshot.",
            "",
            "```console",
            "python scripts/dora_evidence.py check",
            "```",
            "",
            "Scheduled `.github/workflows/dora.yml` queries Pages runs and `incident` issues.",
            "It normalizes the fields needed for the five metrics, generates and verifies the",
            "snapshot, and retains all four evidence files as a CI artifact. Cancelled runs are",
            "reported apart from completed deployment attempts. Rework remains a disclosed title",
            "proxy until human quarterly classification is retained alongside it.",
            "",
            f"Last verified: {snapshot['generated_at'][:10]}. Recheck cadence: weekly in CI,",
            "quarterly for the committed snapshot, and after an incident or event-model change.",
            "",
        ]
    )
    return "\n".join(lines)


def generate(args: argparse.Namespace) -> None:
    snapshot, actions, issues = build_snapshot(args.actions, args.issues)
    _write_json(args.snapshot, snapshot)
    args.markdown.parent.mkdir(parents=True, exist_ok=True)
    args.markdown.write_text(render_markdown(snapshot, actions, issues), encoding="utf-8")


def check(args: argparse.Namespace) -> None:
    expected, actions, issues = build_snapshot(args.actions, args.issues)
    actual = _read_json(args.snapshot)
    if actual != expected:
        raise EvidenceError(
            f"{args.snapshot}: snapshot differs from retained inputs; regenerate it"
        )
    expected_markdown = render_markdown(expected, actions, issues)
    try:
        actual_markdown = args.markdown.read_text(encoding="utf-8")
    except OSError as exc:
        raise EvidenceError(f"{args.markdown}: missing generated ledger ({exc})") from exc
    if actual_markdown != expected_markdown:
        raise EvidenceError(f"{args.markdown}: ledger differs from retained inputs; regenerate it")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    retain_parser = subparsers.add_parser("retain", help="normalize raw gh api JSON exports")
    retain_parser.add_argument("--actions-raw", type=Path, required=True)
    retain_parser.add_argument("--issues-raw", type=Path, required=True)
    retain_parser.add_argument("--repository", required=True)
    retain_parser.add_argument("--workflow", default="pages.yml")
    retain_parser.add_argument("--window-start", required=True)
    retain_parser.add_argument("--window-end", required=True)
    retain_parser.add_argument("--collected-at", required=True)
    retain_parser.add_argument("--out-dir", type=Path, required=True)

    for command in ("generate", "check"):
        command_parser = subparsers.add_parser(command)
        command_parser.add_argument("--actions", type=Path, default=DEFAULT_ACTIONS)
        command_parser.add_argument("--issues", type=Path, default=DEFAULT_ISSUES)
        command_parser.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
        command_parser.add_argument("--markdown", type=Path, default=DEFAULT_MARKDOWN)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "retain":
            retain(args)
        elif args.command == "generate":
            generate(args)
        else:
            check(args)
    except EvidenceError as exc:
        print(f"dora-evidence: FAIL: {exc}", file=sys.stderr)
        return 1
    print(f"dora-evidence: PASS ({args.command})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
