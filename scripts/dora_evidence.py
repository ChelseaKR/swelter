#!/usr/bin/env python3
"""Retain, generate, and verify deterministic DORA evidence from GitHub JSON exports.

**A cancelled run is not one outcome.** A job killed by its own ``timeout-minutes`` concludes
``cancelled``, never ``timed_out`` -- measured on `gtfs-scorecard` run 34162993774, whose job ran
45 minutes to the second against ``timeout-minutes: 45`` and concluded ``cancelled``. That
workflow died that way for eleven consecutive scheduled runs while every sweep read the result as
no signal (#267). Meanwhile every one of this repository's 38 cancelled ``pages.yml`` runs was
evicted out of the pending queue before a runner existed, and counting *those* as deployment
failures would put a false 12.5% on ``change_fail_rate``.

So the repair is not a wider :data:`FAILED_CONCLUSIONS`. It is retaining the evidence that tells
the two apart -- each cancelled run's jobs and their check-run annotations, where GitHub says
"The job has exceeded the maximum execution time of 45m0s" and nowhere else -- and then resolving
every terminal outcome through one table (:data:`RUN_DISPOSITIONS`,
:data:`CANCELLATION_DISPOSITIONS`) that has no silent branch. An outcome nobody has classified
makes the change-failure metrics ``unavailable``; it does not make the denominator smaller.
:func:`failure_mode_coverage` reports how many of the eleven non-success terminal outcomes reach a
decision, so that number is a gate output rather than a claim in a pull request.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ACTIONS = ROOT / "docs" / "audits" / "dora" / "actions.json"
DEFAULT_ISSUES = ROOT / "docs" / "audits" / "dora" / "issues.json"
DEFAULT_SNAPSHOT = ROOT / "docs" / "audits" / "dora" / "snapshot.json"
DEFAULT_MARKDOWN = ROOT / "docs" / "DORA.md"
DEFAULT_WORKFLOW = ROOT / ".github" / "workflows" / "dora.yml"

#: The retained-evidence schema. Bumped 1 -> 2 when a cancelled run gained the ``cancellation``
#: object below: a version 1 document cannot say why one of its runs was cancelled, and a reader
#: that treated the absence as "not a failure" would be making exactly the mistake this schema
#: change exists to stop.
SCHEMA_VERSION = 2

#: Where a completed run lands relative to the change-failure line.
#:
#: ``REFUSED`` is the member that makes this a table rather than a set. Before it existed, every
#: conclusion outside :data:`FAILED_CONCLUSIONS` fell out of *both* the numerator and the
#: denominator of ``change_fail_rate`` without a word, so "this run did not fail" and "this reader
#: does not know what this run did" produced the identical number. A terminal outcome nobody has
#: classified is now a refusal, which is loud, rather than a silent subtraction.
DEPLOYED = "deployed"
FAILED = "failed"
NOT_ATTEMPTED = "not_attempted"
REFUSED = "refused"

#: Every ``conclusion`` GitHub documents for a *completed* workflow run, except ``cancelled``.
#: ``cancelled`` is deliberately absent: it is not one outcome, it is four, and which one it was
#: is decided from retained per-job evidence by :func:`_classify_cancellation`.
#:
#: ``skipped`` and ``stale`` are non-attempts because nothing ran; ``neutral`` is a refusal
#: because it is a legacy checks-API value with no settled meaning for a deployment, and guessing
#: at one would put a number on the metric that nobody chose.
RUN_DISPOSITIONS: dict[str, str] = {
    "success": DEPLOYED,
    "failure": FAILED,
    "timed_out": FAILED,
    "action_required": FAILED,
    "startup_failure": FAILED,
    "skipped": NOT_ATTEMPTED,
    "stale": NOT_ATTEMPTED,
    "neutral": REFUSED,
}

#: Retained conclusions that mean the run failed, kept as a name because `docs/DORA.md` and the
#: tests both talk about it. ``cancelled`` reaches this set only through a classified cancellation.
FAILED_CONCLUSIONS = frozenset(
    conclusion for conclusion, disposition in RUN_DISPOSITIONS.items() if disposition == FAILED
)

#: **A job killed by its own `timeout-minutes` concludes `cancelled`, never `timed_out`.** Measured
#: on `gtfs-scorecard` run 34162993774: the job started 21:24:06Z and completed 22:09:20Z, 45
#: minutes to the second against `timeout-minutes: 45`, and both the job and the run concluded
#: `cancelled`. That workflow had been dying that way for eleven consecutive scheduled runs while
#: every sweep read the result as no signal (#267).
#:
#: The `conclusion` field cannot tell that apart from a concurrency eviction, and neither can the
#: job's own duration without knowing the bound, which the API does not expose. GitHub *does* say
#: it, in the check-run annotation it writes on the killed job, and that is the only place it says
#: it. So the annotation is what this retains and what the classification reads.
_TIMEOUT_KILL_ANNOTATION = re.compile(r"^The job has exceeded the maximum execution time of ")

#: The same measurement's other half. A run superseded while a job was already running carries
#: `Canceling since a higher priority waiting request for ... exists` -- measured on swelter
#: `ci.yml` job 101911103002. That is a scheduling decision about a stale ref, not a deployment
#: failure, and counting it as one would put a false rate on the metric.
_SUPERSEDED_ANNOTATION = re.compile(r"^Canceling since a higher priority waiting request ")

#: Why a run concluded `cancelled`, and what that means for the change-failure line.
#:
#: ``never_started`` is the common case here and the reason the obvious fix -- adding `cancelled`
#: to :data:`FAILED_CONCLUSIONS` -- would have been worse than the blindness it replaced. All 38
#: cancelled `pages.yml` runs in this repository's history returned `total_count: 0` from the jobs
#: endpoint: every one was evicted out of the pending queue before a runner existed. Counting them
#: would have put a false 12.5% on `change_fail_rate`.
CANCELLATION_DISPOSITIONS: dict[str, str] = {
    "timeout_kill": FAILED,
    "superseded": NOT_ATTEMPTED,
    "never_started": NOT_ATTEMPTED,
    "unrecognised": REFUSED,
}

REWORK_TITLE = re.compile(r"^(?:fix(?:\([^)]+\))?[!:]?|FIX-\d+\b)", re.IGNORECASE)

#: The one call that makes `.github/workflows/dora.yml` the DORA workflow. `publication_route`
#: refuses rather than answering over a file it no longer recognises: "this workflow has no way
#: to publish" and "this reader stopped understanding the workflow" produce the same word
#: otherwise, and only one of them is a fact about the repository.
_GENERATE_INVOCATION = "dora_evidence.py generate"

#: Actions whose whole purpose is to put a file back into the repository or onto the site.
#: Names are matched on the `owner/repo` part of `uses:`, before any `@sha`.
_PUBLISHING_ACTIONS = frozenset(
    {
        "peter-evans/create-pull-request",
        "stefanzweifel/git-auto-commit-action",
        "endbug/add-and-commit",
        "ad-m/github-push-action",
        "actions/deploy-pages",
        "actions/upload-pages-artifact",
        "jamesives/github-pages-deploy-action",
    }
)

#: Shell fragments that move a file out of the runner and somewhere a reader can reach it.
_PUBLISHING_COMMANDS = ("git push", "gh pr create", "gh release create", "gh release upload")

#: Permissions a job would need before any of the above could succeed. Read as a *capability*:
#: a workflow granted none of these cannot write the evidence anywhere durable whatever binary
#: it invokes, which is the half of the question a list of spellings cannot close.
_PUBLISHING_SCOPES = ("contents", "pages")

#: Where a reader can find the window the scheduled run computes. This sentence is derived from
#: the workflow rather than written by hand: the one it replaced -- "Scheduled CI will produce
#: the first complete retained snapshot." -- described a step `dora.yml` has never had, and sat
#: on the committed evidence for eight weeks of successful weekly runs (#267).
RETENTION_NOTES: dict[str, str] = {
    "build-artifact": (
        "The scheduled run retains a complete window every week, but no step in "
        ".github/workflows/dora.yml writes it back into this repository, so that window "
        "reaches only a 90-day build artifact and this committed collection stays "
        "incomplete until publication is configured (#267)."
    ),
    "repository": (
        "The scheduled run writes its retained window back into this repository, so a "
        "committed collection that is still incomplete is one no scheduled run has "
        "replaced yet."
    ),
}


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


def _flatten_actions(
    raw: Any, cancellations: Mapping[int, dict[str, Any]] | None = None
) -> list[dict[str, Any]]:
    """Normalize a runs export, attaching the retained cause to every cancelled run.

    ``cancellations`` is not optional in practice: a cancelled run with no entry is an error, not
    a run that gets the benefit of the doubt. That is the whole repair -- the old flattener kept
    `workflow_runs` fields only, so nothing downstream *could* tell a cap-kill from an eviction,
    and the metric resolved the ambiguity by dropping both.
    """
    cancellations = {} if cancellations is None else cancellations
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
            record: dict[str, Any] = {
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
            if record["conclusion"] == "cancelled":
                run_id = record["id"]
                if run_id not in cancellations:
                    raise EvidenceError(
                        f"cancelled run {run_id} has no retained cancellation evidence; a "
                        "cancellation whose cause was not collected cannot be scored"
                    )
                record["cancellation"] = cancellations[run_id]
            records.append(record)
    return sorted(records, key=lambda record: (str(record.get("created_at")), record.get("id", 0)))


def cancelled_run_ids(raw: Any) -> list[int]:
    """Run ids the collector must fetch job and annotation evidence for, newest last.

    Exposed as its own subcommand so the workflow does not have to re-derive the cancelled set in
    shell, where a quoting mistake yields an empty list and an empty list looks like good news.
    """
    pages = raw if isinstance(raw, list) else [raw]
    found: list[int] = []
    for page in pages:
        if not isinstance(page, dict) or not isinstance(page.get("workflow_runs"), list):
            raise EvidenceError(
                "Actions export must be an object or slurped list with workflow_runs"
            )
        for item in page["workflow_runs"]:
            if not isinstance(item, dict):
                raise EvidenceError("Actions workflow_runs entries must be objects")
            if item.get("conclusion") != "cancelled":
                continue
            run_id = item.get("id")
            if not isinstance(run_id, int) or isinstance(run_id, bool):
                raise EvidenceError("a cancelled run has no integer id")
            found.append(run_id)
    return sorted(set(found))


def job_ids(raw: Any) -> list[int]:
    """Job ids in a `/actions/runs/{id}/jobs` export, so the collector can fetch each annotation."""
    return [job["id"] for job in _jobs_export(raw, label="jobs export")]


def _jobs_export(raw: Any, *, label: str) -> list[dict[str, Any]]:
    pages = raw if isinstance(raw, list) else [raw]
    jobs: list[dict[str, Any]] = []
    for page in pages:
        if not isinstance(page, dict) or not isinstance(page.get("jobs"), list):
            raise EvidenceError(f"{label} must be an object or slurped list with jobs")
        for item in page["jobs"]:
            if not isinstance(item, dict) or not isinstance(item.get("id"), int):
                raise EvidenceError(f"{label}: each job must be an object with an integer id")
            jobs.append(item)
    return jobs


def _annotations_export(raw: Any, *, label: str) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        raise EvidenceError(f"{label} must be a list of annotations")
    pages = raw if raw and all(isinstance(page, list) for page in raw) else [raw]
    annotations: list[dict[str, str]] = []
    for page in pages:
        if not isinstance(page, list):
            raise EvidenceError(f"{label}: slurped page must be a list")
        for item in page:
            if not isinstance(item, dict):
                raise EvidenceError(f"{label}: each annotation must be an object")
            level = item.get("annotation_level")
            message = item.get("message")
            if not isinstance(level, str) or not isinstance(message, str):
                raise EvidenceError(
                    f"{label}: each annotation needs a string annotation_level and message"
                )
            annotations.append({"annotation_level": level, "message": message})
    return annotations


def _classify_cancellation(jobs: Sequence[Mapping[str, Any]]) -> str:
    """Name the cause of one cancelled run from its jobs and their check-run annotations.

    Order matters and it runs toward the failure. A run with two jobs, one superseded and one
    killed by its bound, is a run that hit its bound.
    """
    for job in jobs:
        for annotation in job["annotations"]:
            if _TIMEOUT_KILL_ANNOTATION.match(annotation["message"]):
                return "timeout_kill"
    if not any(job["steps"] for job in jobs):
        return "never_started"
    for job in jobs:
        for annotation in job["annotations"]:
            if _SUPERSEDED_ANNOTATION.match(annotation["message"]):
                return "superseded"
    return "unrecognised"


def load_cancellations(directory: Path, run_ids: Sequence[int]) -> dict[int, dict[str, Any]]:
    """Read one `run-<id>.jobs.json` plus one `job-<id>.annotations.json` per job, and classify.

    Fail-closed in both directions. A cancelled run with no jobs file is an error, and so is a
    jobs file for a run that is not in ``run_ids`` -- a stale collection directory reused across
    windows would otherwise classify this window's cancellations from last window's evidence.
    """
    wanted = set(run_ids)
    collected = {
        int(path.name[len("run-") : -len(".jobs.json")])
        for path in sorted(directory.glob("run-*.jobs.json"))
    }
    if collected - wanted:
        extra = ", ".join(str(run_id) for run_id in sorted(collected - wanted))
        raise EvidenceError(
            f"{directory}: holds cancellation evidence for run(s) {extra}, which the actions "
            "export does not report as cancelled; this collection is not from this window"
        )
    cancellations: dict[int, dict[str, Any]] = {}
    for run_id in sorted(wanted):
        jobs_path = directory / f"run-{run_id}.jobs.json"
        if not jobs_path.is_file():
            raise EvidenceError(
                f"{jobs_path}: missing job evidence for cancelled run {run_id}; without it the "
                "cause of the cancellation cannot be named"
            )
        jobs: list[dict[str, Any]] = []
        for job in _jobs_export(_read_json(jobs_path), label=str(jobs_path)):
            annotations_path = directory / f"job-{job['id']}.annotations.json"
            if not annotations_path.is_file():
                raise EvidenceError(
                    f"{annotations_path}: missing annotations for job {job['id']} of cancelled "
                    f"run {run_id}; the timeout-kill signal lives only there"
                )
            steps = job.get("steps")
            jobs.append(
                {
                    "id": job["id"],
                    "name": job.get("name"),
                    "conclusion": job.get("conclusion"),
                    "started_at": job.get("started_at"),
                    "completed_at": job.get("completed_at"),
                    "steps": len(steps) if isinstance(steps, list) else 0,
                    "annotations": _annotations_export(
                        _read_json(annotations_path), label=str(annotations_path)
                    ),
                }
            )
        cancellations[run_id] = {"cause": _classify_cancellation(jobs), "jobs": jobs}
    return cancellations


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
        "schema_version": SCHEMA_VERSION,
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
    actions_raw = _read_json(args.actions_raw)
    cancellations = load_cancellations(args.cancellations_dir, cancelled_run_ids(actions_raw))
    actions = _retained_document(
        kind="github_actions",
        repository=args.repository,
        records=_flatten_actions(actions_raw, cancellations),
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
    if document.get("schema_version") != SCHEMA_VERSION or document.get("kind") != kind:
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
    _validate_cancellation(record, label)


def _validate_cancellation(record: Mapping[str, Any], label: str) -> None:
    """A cancelled run carries a classified cause; nothing else carries one.

    Both halves are load-bearing. Without the first, a version 2 document can still contain the
    unclassifiable cancelled run this schema exists to prevent. Without the second, a
    ``cancellation`` object could be attached to a *successful* run and silently ignored, which is
    how a field stops meaning anything.
    """
    cancellation = record.get("cancellation")
    if record.get("conclusion") != "cancelled":
        if cancellation is not None:
            raise EvidenceError(f"{label}: only a cancelled run carries a cancellation object")
        return
    if not isinstance(cancellation, dict):
        raise EvidenceError(f"{label}: a cancelled run must carry a cancellation object")
    cause = cancellation.get("cause")
    if cause not in CANCELLATION_DISPOSITIONS:
        raise EvidenceError(
            f"{label}: cancellation cause {cause!r} is not one this reader classifies "
            f"({', '.join(sorted(CANCELLATION_DISPOSITIONS))})"
        )
    jobs = cancellation.get("jobs")
    if not isinstance(jobs, list):
        raise EvidenceError(f"{label}: cancellation.jobs must be a list")
    for index, job in enumerate(jobs):
        _validate_cancellation_job(job, f"{label}: cancellation job {index}")


def _validate_cancellation_job(job: Any, label: str) -> None:
    """The three fields the cause was read from, so the classification stays checkable."""
    if not isinstance(job, dict):
        raise EvidenceError(f"{label} must be an object")
    if not isinstance(job.get("id"), int) or isinstance(job.get("id"), bool):
        raise EvidenceError(f"{label} needs an integer id")
    if not isinstance(job.get("steps"), int) or isinstance(job.get("steps"), bool):
        raise EvidenceError(f"{label} needs an integer step count")
    if not isinstance(job.get("annotations"), list):
        raise EvidenceError(f"{label} needs an annotations list")


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


def run_disposition(record: Mapping[str, Any]) -> str:
    """Which side of the change-failure line one completed run falls on.

    Every terminal outcome reaches a decision here, including the ones nobody has thought about:
    an unmapped ``conclusion`` is :data:`REFUSED`, not skipped. That is the difference between a
    denominator a reader can check and one that quietly shrinks.
    """
    conclusion = record.get("conclusion")
    if conclusion == "cancelled":
        cancellation = record.get("cancellation")
        cause = cancellation.get("cause") if isinstance(cancellation, Mapping) else None
        return CANCELLATION_DISPOSITIONS.get(str(cause), REFUSED)
    return RUN_DISPOSITIONS.get(str(conclusion), REFUSED)


def failure_mode_coverage() -> dict[str, int]:
    """How many ways a run can end without deploying, and how many of them reach a decision.

    ``examinable`` counts the distinct non-success terminal outcomes this evidence can *name*
    from what it retains: the seven non-success ``conclusion`` values, plus the four causes a
    ``cancelled`` run resolves into. ``resolved`` counts the ones that reach a definite side of
    the line; ``refused`` counts the ones that stop the metric rather than being dropped from it.

    Before #267 the answer was four of eleven -- the four :data:`FAILED_CONCLUSIONS`. The other
    seven, `cancelled` in all four of its shapes included, fell out of both the numerator and the
    denominator of ``change_fail_rate`` with nothing printed. This function exists so those two
    numbers are an output of the gate rather than a sentence in a pull request.
    """
    dispositions = [
        disposition
        for conclusion, disposition in RUN_DISPOSITIONS.items()
        if conclusion != "success"
    ] + list(CANCELLATION_DISPOSITIONS.values())
    return {
        "examinable": len(dispositions),
        "counted_as_failure": dispositions.count(FAILED),
        "counted_as_non_attempt": dispositions.count(NOT_ATTEMPTED),
        "refused": dispositions.count(REFUSED),
        "resolved": sum(1 for disposition in dispositions if disposition != REFUSED),
    }


def _by_disposition(completed: Sequence[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Place every completed run on exactly one side of the change-failure line.

    Every run lands in a bucket, including the ones nobody classified. That is the property the
    old `[record for record in completed if record["conclusion"] in FAILED_CONCLUSIONS]` did not
    have: it selected, and everything it did not select disappeared without a count.
    """
    buckets: dict[str, list[dict[str, Any]]] = {
        DEPLOYED: [],
        FAILED: [],
        NOT_ATTEMPTED: [],
        REFUSED: [],
    }
    for record in completed:
        buckets[run_disposition(record)].append(record)
    return buckets


def _unresolved_reason(unresolved: Sequence[Mapping[str, Any]]) -> str | None:
    """Why the change-failure metrics refuse, naming every run that caused it."""
    if not unresolved:
        return None
    runs = "; ".join(
        f"run {record['id']} concluded {record['conclusion']!r}"
        + (
            " for a cause this reader does not classify"
            if record["conclusion"] == "cancelled"
            else ""
        )
        for record in unresolved
    )
    return f"{runs}. A terminal outcome nobody has classified is not a run that succeeded."


def _recovery_metric(
    *,
    successful: Sequence[Mapping[str, Any]],
    failures: Sequence[Mapping[str, Any]],
    issues: Mapping[str, Any],
    end: datetime,
    unresolved: Sequence[Mapping[str, Any]],
    unresolved_reason: str | None,
) -> dict[str, Any]:
    """Time from a failed deployment or incident to the next success, or the open events.

    ``failures`` now includes a run killed by its own ``timeout-minutes``, so a capped deploy
    opens a recovery event instead of passing through this function invisibly (#267).
    """
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
    if unresolved_reason is not None:
        refused = _metric_unavailable(unresolved_reason)
        refused["unresolved_runs"] = [record["id"] for record in unresolved]
        return refused
    if open_events:
        return {
            "status": "alert",
            "open_events": open_events,
            "recovered_events": len(recovery_hours),
            "target": "under 24 hours",
        }
    if not recovery_hours:
        return {
            "status": "no_event",
            "open_events": [],
            "recovered_events": 0,
            "target": "under 24 hours",
        }
    maximum = max(recovery_hours)
    return {
        "status": "pass" if maximum < 24 else "alert",
        "open_events": [],
        "recovered_events": len(recovery_hours),
        "p50_hours": round(_percentile(recovery_hours, 0.5) or 0, 4),
        "max_hours": round(maximum, 4),
        "target": "under 24 hours",
    }


def _complete_metrics(actions: dict[str, Any], issues: dict[str, Any]) -> dict[str, Any]:
    start = _timestamp(actions["query"]["window_start"], "window_start")
    end = _timestamp(actions["query"]["window_end"], "window_end")
    window_days = (end - start).total_seconds() / 86400
    completed = [record for record in actions["records"] if record["status"] == "completed"]
    by_disposition = _by_disposition(completed)
    successful = by_disposition[DEPLOYED]
    failures = by_disposition[FAILED]
    unresolved = by_disposition[REFUSED]
    cancellations = [record for record in completed if record["conclusion"] == "cancelled"]
    cancelled_by_cause = {
        cause: sum(1 for record in cancellations if record["cancellation"]["cause"] == cause)
        for cause in sorted(CANCELLATION_DISPOSITIONS)
    }
    attempts = [*successful, *failures]
    change_deploys = [record for record in successful if record["event"] == "push"]
    unresolved_reason = _unresolved_reason(unresolved)

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
    if unresolved_reason is not None:
        change_fail_rate = _metric_unavailable(unresolved_reason)
        change_fail_rate["unresolved_runs"] = [record["id"] for record in unresolved]
    else:
        change_fail_rate = {
            "status": "no_event"
            if failure_rate is None
            else ("pass" if failure_rate < 0.15 else "alert"),
            "failed_attempts": len(failures),
            "completed_attempts": len(attempts),
            "cancelled_runs": len(cancellations),
            "cancelled_by_cause": cancelled_by_cause,
            "timeout_killed_attempts": cancelled_by_cause["timeout_kill"],
            "rate": None if failure_rate is None else round(failure_rate, 6),
            "target": "under 15%",
        }

    recovery_metric = _recovery_metric(
        successful=successful,
        failures=failures,
        issues=issues,
        end=end,
        unresolved=unresolved,
        unresolved_reason=unresolved_reason,
    )
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


def _unavailable_baseline(metric: Mapping[str, Any]) -> str:
    """Which unavailability this is: no retained window, or a run nobody could score.

    They are different findings with different owners, and the ledger used to print the first
    sentence over both.
    """
    unresolved = metric.get("unresolved_runs")
    if unresolved:
        return (
            f"Unavailable — {len(unresolved)} completed run(s) ended in a terminal outcome "
            "this reader does not classify"
        )
    return "Unavailable — retained inputs are incomplete"


def _metric_baseline(name: str, metric: dict[str, Any]) -> str:
    status = metric["status"]
    if status == "unavailable":
        return _unavailable_baseline(metric)
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
        causes = metric["cancelled_by_cause"]
        return (
            f"{metric['failed_attempts']} of {metric['completed_attempts']} completed attempts "
            f"({_percent(metric['rate'])}), including {causes['timeout_kill']} killed by its own "
            f"timeout; {causes['never_started'] + causes['superseded']} of "
            f"{metric['cancelled_runs']} cancelled run(s) were not deployment attempts"
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
                "> A maintainer must review a complete dated snapshot and commit it before this",
                "> fail-closed baseline is replaced. The sentence above says where the scheduled",
                "> run's own window can be read; it is checked against the workflow file.",
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
            "snapshot, and retains all four evidence files as a CI artifact. A cancelled run is",
            "resolved from its own jobs and their check-run annotations: one killed by its",
            "`timeout-minutes` bound is a failed deployment attempt, one whose jobs never started",
            "or was superseded is no attempt at all, and one whose cause this reader cannot name",
            "makes the change-failure metrics unavailable rather than smaller. Rework remains a",
            "disclosed title proxy until human quarterly classification is retained alongside it.",
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


def coverage_summary(
    snapshot: Mapping[str, Any],
    actions: Mapping[str, Any],
    issues: Mapping[str, Any],
    route: str | None = None,
) -> str:
    """Say what this run actually verified, so a vacuous PASS cannot read like a full one.

    The committed evidence currently declares ``collection.complete: false`` with zero retained
    records, so every metric resolves to ``unavailable`` and ``_complete_metrics`` -- where every
    DORA threshold in this file lives -- is never entered. That state is real, disclosed, and
    tracked in #109; what was wrong is that the gate printed the identical bare ``PASS (check)``
    for it as it would for a full window. A green line that cannot be told apart from a green
    line over nothing is not evidence. This makes the emptiness part of the output.
    """
    metrics = snapshot.get("metrics")
    metrics = metrics if isinstance(metrics, dict) else {}
    computed = sum(
        1
        for metric in metrics.values()
        if isinstance(metric, dict) and metric.get("status") != "unavailable"
    )
    state = "complete" if snapshot.get("collection_complete") else "INCOMPLETE"
    where = "" if route is None else f", scheduled window reaches {route}"
    coverage = failure_mode_coverage()
    modes = (
        f"{coverage['resolved'] + coverage['refused']}/{coverage['examinable']} non-success "
        f"terminal outcome(s) reach a decision ({coverage['counted_as_failure']} scored as change "
        f"failures, {coverage['counted_as_non_attempt']} as non-attempts, {coverage['refused']} "
        "refused)"
    )
    return (
        f"{len(actions['records'])} deployment run(s), {len(issues['records'])} incident(s), "
        f"{computed}/{len(metrics)} metric(s) computed, {modes}, collection {state}{where}"
    )


def _permission_scopes(value: Any) -> set[str]:
    """The scopes a `permissions:` block grants at write level, as a set of scope names.

    GitHub accepts three shapes and two of them are strings: `write-all`, `read-all`, and a
    mapping of scope to level. `read-all` and an absent block both grant nothing writable.
    """
    if value == "write-all":
        return set(_PUBLISHING_SCOPES)
    if not isinstance(value, dict):
        return set()
    return {scope for scope, level in value.items() if isinstance(level, str) and level == "write"}


def _workflow_document(workflow: Path) -> tuple[str, dict[str, Any]]:
    """Read a workflow file and refuse anything :func:`publication_route` cannot answer over."""
    try:
        text = workflow.read_text(encoding="utf-8")
        document = yaml.safe_load(text)
    except (OSError, yaml.YAMLError) as exc:
        raise EvidenceError(f"{workflow}: cannot read the DORA workflow ({exc})") from exc
    if not isinstance(document, dict):
        raise EvidenceError(f"{workflow}: the DORA workflow is not a mapping")
    jobs = document.get("jobs")
    if not isinstance(jobs, dict) or not jobs:
        raise EvidenceError(f"{workflow}: the DORA workflow declares no jobs")
    return text, document


def _step_publishes(step: Mapping[str, Any]) -> bool:
    """True when one step could move a generated file somewhere a reader can reach it."""
    uses = step.get("uses")
    if isinstance(uses, str) and uses.split("@", 1)[0].strip().lower() in _PUBLISHING_ACTIONS:
        return True
    run = step.get("run")
    if isinstance(run, str):
        collapsed = " ".join(run.lower().split())
        return any(command in collapsed for command in _PUBLISHING_COMMANDS)
    return False


def publication_route(workflow: Path) -> str:
    """Where a snapshot generated by ``workflow`` can be read: ``repository`` or ``build-artifact``.

    ``build-artifact`` is the narrower answer and is only returned when *nothing* in the file
    can move a generated file out of the runner:

    * no job grants ``contents: write`` or ``pages: write`` -- the capability half, which closes
      whatever binary a step invokes; and
    * no step uses a publishing action or runs a publishing command -- the spelling half, which
      catches a step holding a token from somewhere else.

    Either half alone flips the answer to ``repository``, because the sentence this decides is
    an assertion that publication does *not* happen, and the cheap mistake to make is to keep
    asserting it after a route appears.

    Two floors, because a reader that has stopped understanding the file returns exactly what a
    workflow with no publication route returns:

    * the file must parse into a mapping with at least one job holding at least one step;
    * it must still contain :data:`_GENERATE_INVOCATION`, the call that makes it this workflow.
    """
    text, document = _workflow_document(workflow)
    jobs = document["jobs"]
    workflow_scopes = _permission_scopes(document.get("permissions"))
    steps_read = 0
    route = "build-artifact"
    for job in jobs.values():
        if not isinstance(job, dict):
            raise EvidenceError(f"{workflow}: a job is not a mapping")
        scopes = _permission_scopes(job["permissions"]) if "permissions" in job else workflow_scopes
        if scopes & set(_PUBLISHING_SCOPES):
            route = "repository"
        steps = job.get("steps")
        if not isinstance(steps, list):
            raise EvidenceError(f"{workflow}: job {job.get('name', '?')!r} declares no steps")
        for step in steps:
            if not isinstance(step, dict):
                raise EvidenceError(f"{workflow}: a step is not a mapping")
            steps_read += 1
            if _step_publishes(step):
                route = "repository"
    if steps_read == 0:
        raise EvidenceError(f"{workflow}: the DORA workflow declares no steps")
    if _GENERATE_INVOCATION not in text:
        raise EvidenceError(
            f"{workflow}: no {_GENERATE_INVOCATION!r} call — this is not the workflow whose "
            "publication route the committed evidence describes"
        )
    return route


def _validate_retention_note(
    documents: Mapping[str, Mapping[str, Any]], workflow: Path
) -> str | None:
    """Hold an incomplete collection's stated reason to the workflow that would complete it.

    The committed evidence says why it is incomplete, and the second half of that sentence is a
    claim about a mechanism -- the kind of claim that goes false without anything changing in
    the file that carries it. So it is not written by hand: :func:`publication_route` reads
    ``dora.yml`` and :data:`RETENTION_NOTES` supplies the sentence, and the reason has to end
    with it. Adding a publishing step to the workflow therefore fails this check until the
    sentence is updated, and so does deleting one.

    Returns the route it resolved, or ``None`` when every collection is complete and the
    question does not arise.
    """
    incomplete = {
        kind: document
        for kind, document in documents.items()
        if not document["collection"]["complete"]
    }
    if not incomplete:
        return None
    route = publication_route(workflow)
    expected = RETENTION_NOTES[route]
    for kind, document in incomplete.items():
        reason = str(document["collection"].get("reason", ""))
        if not reason.endswith(expected):
            raise EvidenceError(
                f"{kind}: the incomplete-collection reason does not end with the sentence "
                f"{workflow.name} supports (route {route!r}). Expected it to end with: "
                f"{expected!r}"
            )
    return route


def check(args: argparse.Namespace) -> str:
    expected, actions, issues = build_snapshot(args.actions, args.issues)
    route = _validate_retention_note(
        {"github_actions": actions, "github_issues": issues}, args.dora_workflow
    )
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
    return coverage_summary(expected, actions, issues, route)


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
    retain_parser.add_argument(
        "--cancellations-dir",
        type=Path,
        required=True,
        help=(
            "directory holding run-<id>.jobs.json and job-<id>.annotations.json for every "
            "cancelled run in the actions export; required, because a cancelled run whose cause "
            "was not collected must stop the retention rather than be scored as a non-failure"
        ),
    )

    plan_parser = subparsers.add_parser(
        "cancelled-runs", help="print the run ids needing cancellation evidence, one per line"
    )
    plan_parser.add_argument("--actions-raw", type=Path, required=True)

    jobs_parser = subparsers.add_parser(
        "cancelled-jobs", help="print the job ids in one runs/<id>/jobs export, one per line"
    )
    jobs_parser.add_argument("--jobs", type=Path, required=True)

    for command in ("generate", "check"):
        command_parser = subparsers.add_parser(command)
        command_parser.add_argument("--actions", type=Path, default=DEFAULT_ACTIONS)
        command_parser.add_argument("--issues", type=Path, default=DEFAULT_ISSUES)
        command_parser.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
        command_parser.add_argument("--markdown", type=Path, default=DEFAULT_MARKDOWN)
        command_parser.add_argument("--dora-workflow", type=Path, default=DEFAULT_WORKFLOW)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    detail = ""
    try:
        if args.command == "retain":
            retain(args)
        elif args.command == "cancelled-runs":
            for run_id in cancelled_run_ids(_read_json(args.actions_raw)):
                print(run_id)
            return 0
        elif args.command == "cancelled-jobs":
            for job_id in job_ids(_read_json(args.jobs)):
                print(job_id)
            return 0
        elif args.command == "generate":
            generate(args)
        else:
            detail = f"; {check(args)}"
    except EvidenceError as exc:
        print(f"dora-evidence: FAIL: {exc}", file=sys.stderr)
        return 1
    print(f"dora-evidence: PASS ({args.command}{detail})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
