#!/usr/bin/env python3
"""Is the observatory a visitor gets at chelseakr.github.io/swelter/ the one this repository has?

Nothing in this repository has ever asked. There is no ``live-integrity.yml`` here and no
scheduled job that reaches the published URL, so every statement this repository makes about the
live site is a statement about `main` wearing the live site's name. Two repositories in this
portfolio have already been caught out by exactly that gap: `afterward` merged canonical tags
across 9,046 pages that never reached a reader, and `evals.chelseakr.com` served a 2026-07-12
build for 63 days with every gate green.

Two different things can be stale here, and they fail for different reasons
-------------------------------------------------------------------------
This site is not a static render of a commit. ``pages.yml`` fires on push to `main`,
on dispatch, **and on a daily ``30 13 * * *`` cron** whose own comment says "refresh the real
readings daily". Each run fetches live observations (OpenAQ, else Copernicus CAMS, else the
committed synthetic fixture), bakes them with ``swelter publish``, and uploads the result. So a
published artifact is a *pair*: the repository's code at some commit, and readings fetched at some
instant. Either half can go stale on its own.

1. **Code staleness.** The deployed commit falls behind `main`, so a visitor receives an older
   renderer, an older page, an older set of strings, an older service worker.
2. **Reading staleness.** The deployed commit is exactly `main`, and the readings inside it are
   days old anyway -- because the daily cron stopped landing, or because a run restored a cached
   store and fell through to a coarser source.

**This module measures publication, not readings.** It reports two numbers, and it is worth being
exact about what each one can and cannot see:

* ``visitor_commits`` / ``commits`` -- how far the published build's *commit* is behind `main`,
  counting only commits that touched something a visitor receives. This is question (1), answered
  exactly.
* ``days`` -- how long ago the newest **successful** ``github-pages`` deployment published. Since
  ``pages.yml`` declares a daily refresh, a gap here means the declared refresh is not landing,
  which is the *cause* of question (2). It is not a measurement of the readings themselves.

What this deliberately does **not** measure is the reading-freshness question directly. A
deployment that succeeded, restored a five-day-old cached store, and fell back from OpenAQ to CAMS
publishes fresh bytes containing old readings, and every signal available here reports it as
current. The numbers that would settle it -- ``publish-manifest.json``'s ``data_hour``, the
surface's newest bucket -- exist only inside the served artifact, and reading them means fetching
the live site, which is a different tool with different failure modes (and a different set of
credentials, which this workflow deliberately has none of). Saying "the site is fresh" on the
strength of a deployment timestamp would be exactly the conflation this file is supposed to refuse,
so the report states which question it answered and names the one it did not.

The publishing model this assumes
---------------------------------
**GitHub Pages built by a workflow from source.** ``gh api repos/ChelseaKR/swelter/pages`` reports
``build_type: workflow``, branch `main`, path `/`. Nothing in this repository commits a built site,
so there is no published subtree to compare and deployed-SHA-versus-head is the right question --
the deployed commit's source tree, plus that run's fetched readings, produced the bytes.

Why the deployment record and not the run history
-------------------------------------------------
A deployment row exists because bytes were published, and it names the commit they were built
from. ``pages.yml``'s run list does not carry that guarantee: this workflow can finish having
published a *fallback* artifact, and a cancelled or skipped run is indistinguishable from a fresh
one at the granularity a run list offers. Worse, in this repository the run history would
systematically flatter the site -- the daily cron reaches a runner every day whether or not the
fetch, the build contract, or the crawl gate succeeded. A ``github-pages`` deployment whose newest
status is ``success`` is the only artefact here that says bytes actually landed.

Note what the daily cron does to the *first* number. Because the cron builds whatever `main` points
at, the deployed commit equals `main`'s head most days, and ``visitor_commits`` reads zero. That is
not the check being useless; it is the check agreeing with a publisher that is working. The moment
the cron stops landing, both numbers start moving -- and if no visitor-visible commit happens to
land in that window, ``days`` is the only one that moves at all. That is precisely the failure the
brief for this work named as "nothing reports it", and it is why age is a verdict here when the
repository's own workflow declares a refresh cadence, and disarmed when it does not.

The rule this file follows: a detector that cannot tell must refuse, never report a comfortable
zero. Every unmeasurable case below raises :class:`StalenessUnknown` rather than returning a number
that would read as a measurement (ADR 0048 -- a check that could not run is not a check that
passed).

Standard library only, and it imports nothing from ``src/swelter``, so the sentinel runs on a bare
``python3`` with no dependency resolution and cannot be broken by one.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_REPO = "ChelseaKR/swelter"

#: The Pages environment a deployment has to belong to. The repository carries other environments;
#: only this one is the published observatory.
PAGES_ENVIRONMENT = "github-pages"

#: The publisher. Its `schedule:` block is the repository's own statement about how often the live
#: readings are meant to be refreshed, and this file reads that statement rather than restating it.
PAGES_WORKFLOW = Path(".github/workflows/pages.yml")

#: How long an unpublished visitor-visible commit may wait before this reports.
DEFAULT_MAX_AGE_DAYS = 14

#: Slack on top of the publisher's declared refresh period before a missed refresh is reported.
#: Two days, so a single failed cron run plus the retry that follows it is not an incident, while
#: a cron that has stopped landing altogether is.
REFRESH_GRACE_DAYS = 2

#: Paths whose change alters what a visitor receives.
#:
#: ``actions/upload-pages-artifact`` uploads ``web/`` wholesale, so the base of the set is that
#: directory: every page, stylesheet, module, icon, catalog, service worker, basemap and the
#: ``/planner/`` route ship verbatim. ``web/package.json``, ``web/package-lock.json`` and
#: ``web/tests/build-i18n-runtime.cjs`` are in the set for a less obvious reason -- ``pages.yml``
#: runs ``npm --prefix web ci --omit=dev`` whose ``postinstall`` generates
#: ``web/vendor/messageformat/`` from the locked dependency and then deletes ``node_modules``. The
#: vendored runtime a visitor executes is built from those files at deploy time (ADR 0026), so a
#: change to them is a change to the site.
#:
#: Beyond ``web/``: ``src/swelter/`` is the publisher itself (``swelter fetch`` and
#: ``swelter publish`` bake the whole artifact -- surfaces, slices, health, alerts, export.csv,
#: the license files and the manifest, per ADR 0020); the three ``scripts/`` entries are the
#: deploy-time steps that write into the artifact after it (route metadata and sitemap, the
#: demo-source contract, the deployed-identity stamp); ``pages.yml`` is on the list because the
#: build recipe *is* that file -- it chooses the source, sets the license and attribution, composes
#: ``/sensors/`` and rewrites each service worker's cache release; and ``network.yaml`` plus
#: ``data/demo/`` shape the artifact on the synthetic fallback branch.
#:
#: Everything else changes `main` constantly without changing a published byte -- ``tests/``, the
#: ADRs, ``firmware/``, ``infra/``, the other gate scripts, ``docs/`` -- and counting them would
#: make the number meaningless well before it made it alarming.
SITE_SOURCE_PREFIXES = (
    "web/",
    "src/swelter/",
    "scripts/pages_seo.py",
    "scripts/stamp_pages_version.py",
    "scripts/build_demo_contract.py",
    ".github/workflows/pages.yml",
    "network.yaml",
    "data/demo/",
)

#: The exception inside ``web/``: every file ``swelter publish`` (and the workflow's own cleanup)
#: deterministically rewrites or removes at deploy time. ``cli.PUBLISH_FILES`` plus the manifest it
#: writes, plus the illustrative cooling centers the workflow deletes before upload. A commit that
#: changes only these changes nothing a visitor receives, because the deploy overwrites them from
#: the store before the artifact is uploaded; counting them would cry wolf on every refresh of the
#: committed demo artifacts.
REPUBLISHED_AT_DEPLOY = frozenset(
    {
        "web/sample-surface.json",
        "web/demo.json",
        "web/sample-health.json",
        "web/alerts.json",
        "web/alerts.xml",
        "web/alerts.es.xml",
        "web/cooling-centers.geojson",
        "web/surface-24h.json",
        "web/surface-7d.json",
        "web/export.csv",
        "web/source-metadata.json",
        "web/source-license-ledger.json",
        "web/DATA-LICENSE",
        "web/LICENSE",
        "web/publish-manifest.json",
    }
)

_SHA = re.compile(r"^[0-9a-f]{40}$")

#: `- cron: "30 13 * * *"  # refresh the real readings daily`, quoted or not, comment or not.
_CRON = re.compile(r"""(?m)^\s*-\s*cron:\s*["']?([^"'#\n]+?)["']?\s*(?:#.*)?$""")

#: A day-of-week field this reader is willing to count days from: `1`, `1,4`, `MON`.
_DAY_OF_WEEK_LIST = re.compile(r"^[0-9A-Za-z]+(?:,[0-9A-Za-z]+)*$")


class StalenessUnknown(Exception):
    """The comparison could not be made, so no number is reported.

    Raised in preference to returning zero anywhere the inputs do not support a measurement. The
    caller turns this into a red run: a sentinel that cannot tell is a broken sentinel, and it has
    to look broken rather than report that everything is fine.
    """


@dataclass(frozen=True)
class DeployRecord:
    """The published build: which commit it came from, and when it went out."""

    deployment_id: int
    sha: str
    created_at: datetime


@dataclass(frozen=True)
class RefreshContract:
    """The publisher's own declared refresh cadence, read out of its ``schedule:`` block.

    This is what makes an age-based verdict legitimate here rather than a clock firing on a site
    that is simply finished. ``pages.yml`` says it republishes daily to keep the readings current;
    a build older than that promise plus a grace period is the promise not being kept. Delete the
    cron and this contract disappears with it, and the age verdict disarms itself -- the check can
    only ever hold the repository to something the repository says.
    """

    period_days: int
    grace_days: int = REFRESH_GRACE_DAYS

    @property
    def threshold_days(self) -> int:
        return self.period_days + self.grace_days


@dataclass(frozen=True)
class Drift:
    """How far the published build is behind, on both of the questions that have an answer here."""

    deployed: DeployRecord
    head: str
    days: int
    commits: int
    visitor_commits: int
    max_age_days: int
    refresh: RefreshContract | None

    @property
    def code_overdue(self) -> bool:
        """Question 1: is the *commit* a visitor is served behind `main`?

        Age alone is not this signal. A site that has not been republished for a month because
        nothing it publishes has changed is correct, not stale.
        """
        return self.visitor_commits > 0 and self.days > self.max_age_days

    @property
    def refresh_overdue(self) -> bool:
        """Question 2's cause: has the publisher's own declared refresh stopped landing?

        Armed only by a ``schedule:`` block in ``pages.yml``. This says nothing about how old the
        readings inside the last successful publish are -- only that no new publish has happened
        within the cadence this repository declares for itself.
        """
        return self.refresh is not None and self.days > self.refresh.threshold_days

    @property
    def overdue(self) -> bool:
        return self.code_overdue or self.refresh_overdue


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def newest_successful_deployment(
    deployments: Iterable[Mapping[str, Any]],
    statuses_for: Any,
) -> DeployRecord:
    """The most recent `github-pages` deployment that actually published.

    ``statuses_for`` is called with a deployment id and returns that deployment's statuses. A
    deployment row is a *request* to publish; its statuses are what say whether bytes landed. A
    deployment whose newest status is ``failure``, ``error`` or ``in_progress`` never became a
    site, and treating its commit as the live one would report the site as fresher than it is --
    the precise direction of error this whole file exists to prevent.
    """
    candidates = [
        d
        for d in deployments
        if d.get("environment") in (None, PAGES_ENVIRONMENT) and _SHA.match(str(d.get("sha", "")))
    ]
    if not candidates:
        raise StalenessUnknown(
            "no github-pages deployment in this repository's history: there is no published "
            "build to compare main against"
        )
    candidates.sort(key=lambda d: _parse_timestamp(str(d["created_at"])), reverse=True)

    for deployment in candidates:
        states = [str(s.get("state", "")) for s in statuses_for(deployment["id"])]
        if states and states[0] == "success":
            return DeployRecord(
                deployment_id=int(deployment["id"]),
                sha=str(deployment["sha"]),
                created_at=_parse_timestamp(str(deployment["created_at"])),
            )

    raise StalenessUnknown(
        f"none of the {len(candidates)} github-pages deployment(s) reports a successful status: "
        "nothing here proves any build was ever published"
    )


def ships_to_visitors(path: str) -> bool:
    """Does changing this file change what the published observatory shows?"""
    if path in REPUBLISHED_AT_DEPLOY:
        return False
    return any(
        path.startswith(prefix) if prefix.endswith("/") else path == prefix
        for prefix in SITE_SOURCE_PREFIXES
    )


def cron_period_days(expression: str) -> int | None:
    """Days between runs of one cron expression, or ``None`` when this reader will not guess.

    Deliberately narrow. It recognises the two shapes a publisher in this portfolio actually
    declares -- every day, and on named weekdays -- and returns ``None`` for anything else rather
    than inventing a cadence. An unrecognised schedule disarms the age verdict and says so; a
    guessed one would produce a threshold nobody chose.
    """
    fields = expression.split()
    if len(fields) != 5:
        return None
    day_of_month, day_of_week = fields[2], fields[4]
    if day_of_month != "*":
        return None
    if day_of_week == "*":
        return 1
    if _DAY_OF_WEEK_LIST.fullmatch(day_of_week):
        return max(1, 7 // (day_of_week.count(",") + 1))
    return None


def declared_refresh(workflow_text: str) -> RefreshContract | None:
    """The publisher's refresh cadence as it declares it, or ``None`` when it declares none.

    Returning ``None`` is a real answer, not a failure: a publisher that only fires on push makes
    no promise about reading freshness, and holding it to one would be this check inventing a
    policy the repository never adopted.
    """
    periods = [
        days
        for match in _CRON.finditer(workflow_text)
        if (days := cron_period_days(match.group(1)))
    ]
    if not periods:
        return None
    return RefreshContract(period_days=min(periods))


def publisher_workflow_text(root: Path = REPO_ROOT) -> str:
    """Read ``pages.yml``, refusing if it is absent.

    Its absence is not a missing optional input. This whole file assumes Pages is built from source
    by that workflow; if it is gone, the model is wrong and every number below would be measuring
    something else.
    """
    path = root / PAGES_WORKFLOW
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise StalenessUnknown(
            f"cannot read the publisher workflow at {PAGES_WORKFLOW}: {exc}. This sentinel assumes "
            "Pages is built from source by that workflow, so without it nothing here is measuring "
            "the published site"
        ) from exc


def _executable(name: str) -> str:
    resolved = shutil.which(name)
    if resolved is None:
        raise StalenessUnknown(f"{name} is not on PATH, so the measurement cannot be made at all")
    return resolved


def _capture(argv: Sequence[str]) -> subprocess.CompletedProcess[str]:
    # Absolute executable, fixed subcommands, argv-only invocation, and no shell -- the same
    # permanent pattern as the other gate scripts in this directory.
    return subprocess.run(  # noqa: S603 (#107)
        list(argv),
        capture_output=True,
        text=True,
        check=False,
    )


def _run_git(*args: str) -> subprocess.CompletedProcess[str]:
    return _capture([_executable("git"), "-C", str(REPO_ROOT), *args])


def _git(*args: str) -> str:
    result = _run_git(*args)
    if result.returncode != 0:
        raise StalenessUnknown(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def _has_commit(sha: str) -> bool:
    """Whether this clone contains the commit, without raising on absence.

    ``git cat-file`` exits non-zero for a commit that is simply not here, which is the ordinary
    shallow-clone case and not a git failure. Routing it through ``_git`` would report it as one,
    and the refusal the caller raises -- the one that names the shallow checkout and says why a
    zero would be wrong -- would never be reached.
    """
    return _run_git("cat-file", "-e", f"{sha}^{{commit}}").returncode == 0


def require_comparable(deployed_sha: str, head: str) -> None:
    """Refuse unless this clone can actually place the deployed commit on `main`.

    Both failures below report zero drift if they are not caught, and both are ordinary. A shallow
    checkout simply does not contain an older commit, so ``git log <deployed>..HEAD`` lists nothing
    and the site reads as up to date -- which is why the sentinel workflow checks out with
    ``fetch-depth: 0`` and why this refuses rather than trusting that it did. A force-push or a
    rebase leaves the deployed commit off `main` entirely, where "commits since" is not a question
    with an answer.
    """
    if not _SHA.match(deployed_sha):
        raise StalenessUnknown(f"deployed commit {deployed_sha!r} is not a commit id")
    if not _has_commit(deployed_sha):
        raise StalenessUnknown(
            f"deployed commit {deployed_sha[:9]} is not in this clone: the checkout is shallow, "
            "and a comparison against a history that does not reach the published build would "
            "report no drift at all"
        )
    merge_base = _git("merge-base", deployed_sha, head)
    if merge_base != _git("rev-parse", deployed_sha):
        raise StalenessUnknown(
            f"deployed commit {deployed_sha[:9]} is not an ancestor of {head}: the history has "
            "diverged and 'commits since the deploy' has no answer"
        )


def commits_between(deployed_sha: str, head: str) -> list[tuple[str, list[str]]]:
    """Each commit after the deployed one, with the paths it touched."""
    raw = _git("log", "--format=%x00%H", "--name-only", f"{deployed_sha}..{head}")
    commits: list[tuple[str, list[str]]] = []
    for block in raw.split("\x00"):
        lines = [line for line in block.strip("\n").splitlines() if line.strip()]
        if lines:
            commits.append((lines[0], lines[1:]))
    return commits


def measure(
    deployed: DeployRecord,
    head: str,
    now: datetime,
    max_age_days: int = DEFAULT_MAX_AGE_DAYS,
    refresh: RefreshContract | None = None,
) -> Drift:
    """Place the published build against `main`, or refuse."""
    head_sha = _git("rev-parse", head)
    require_comparable(deployed.sha, head_sha)
    commits = commits_between(deployed.sha, head_sha)
    visitor = [commit for commit in commits if any(ships_to_visitors(p) for p in commit[1])]
    return Drift(
        deployed=deployed,
        head=head_sha,
        days=(now - deployed.created_at).days,
        commits=len(commits),
        visitor_commits=len(visitor),
        max_age_days=max_age_days,
        refresh=refresh,
    )


def _code_verdict(drift: Drift) -> str:
    if drift.code_overdue:
        return (
            f"OVERDUE (code): {drift.visitor_commits} visitor-visible commit(s) have waited "
            f"{drift.days} days, past the {drift.max_age_days}-day threshold. The live site is not "
            "what this repository says it is."
        )
    if drift.visitor_commits:
        return (
            f"Waiting (code): {drift.visitor_commits} visitor-visible commit(s), {drift.days} "
            f"days, within the {drift.max_age_days}-day threshold."
        )
    return "Code up to date: nothing a visitor receives has changed since the live build."


def _refresh_verdict(drift: Drift) -> str:
    if drift.refresh is None:
        return (
            "Refresh cadence: pages.yml declares no schedule, so there is no refresh promise to "
            "hold it to and the age verdict is disarmed."
        )
    cadence = f"every {drift.refresh.period_days} day(s)"
    if drift.refresh_overdue:
        return (
            f"OVERDUE (refresh): pages.yml declares a republish {cadence}, and the newest "
            f"successful deployment is {drift.days} days old -- past {drift.refresh.period_days} "
            f"+ {drift.refresh.grace_days} days of grace. The declared refresh is not landing, so "
            "the readings a visitor sees are at least that old."
        )
    return (
        f"Refresh landing: pages.yml declares a republish {cadence} and the newest successful "
        f"deployment is {drift.days} days old."
    )


def render(drift: Drift) -> str:
    """The report. States the measurement before its verdict, and names what it did not measure."""
    return "\n".join(
        [
            f"Published build:  {drift.deployed.sha[:9]}  "
            f"({drift.deployed.created_at.date().isoformat()}, "
            f"deployment {drift.deployed.deployment_id})",
            f"main:             {drift.head[:9]}",
            f"Behind by:        {drift.commits} commits, {drift.visitor_commits} of them changing "
            "what a visitor receives",
            f"Last published:   {drift.days} days ago",
            "",
            _code_verdict(drift),
            _refresh_verdict(drift),
            "",
            "Not measured: how old the readings inside the published artifact are. A run that "
            "restored a cached store or fell back to a coarser source still publishes "
            "successfully, and only the served artifact's own data_hour could say otherwise.",
        ]
    )


def as_json(drift: Drift) -> dict[str, Any]:
    return {
        "deployed_sha": drift.deployed.sha,
        "deployed_at": drift.deployed.created_at.isoformat(),
        "deployment_id": drift.deployed.deployment_id,
        "head": drift.head,
        "days": drift.days,
        "commits": drift.commits,
        "visitor_commits": drift.visitor_commits,
        "refresh_period_days": None if drift.refresh is None else drift.refresh.period_days,
        "code_overdue": drift.code_overdue,
        "refresh_overdue": drift.refresh_overdue,
        "overdue": drift.overdue,
    }


def _gh(path: str) -> Any:
    """Read the API through ``gh``, which the runner already authenticates."""
    result = _capture([_executable("gh"), "api", path])
    if result.returncode != 0:
        raise StalenessUnknown(f"gh api {path} failed: {result.stderr.strip()}")
    return json.loads(result.stdout)


def _readers(args: argparse.Namespace) -> tuple[list[Mapping[str, Any]], Any]:
    """The deployment list and a statuses lookup, from the API or from a file for offline use."""
    if args.deployments_json:
        payload = json.loads(Path(args.deployments_json).read_text(encoding="utf-8"))
        statuses = payload["statuses"]
        return payload["deployments"], lambda did: statuses.get(str(did), [])
    deployments = _gh(f"repos/{args.repo}/deployments?environment={PAGES_ENVIRONMENT}&per_page=20")
    return deployments, lambda did: _gh(f"repos/{args.repo}/deployments/{did}/statuses?per_page=10")


def _write_github_output(drift: Drift | None, error: str | None) -> None:
    path = os.environ.get("GITHUB_OUTPUT")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as handle:
        if drift is None:
            handle.write("measured=false\n")
            handle.write(f"error={error or 'unknown'}\n")
            return
        handle.write("measured=true\n")
        handle.write(f"overdue={str(drift.overdue).lower()}\n")
        handle.write(f"code_overdue={str(drift.code_overdue).lower()}\n")
        handle.write(f"refresh_overdue={str(drift.refresh_overdue).lower()}\n")
        handle.write(f"days={drift.days}\n")
        handle.write(f"commits={drift.commits}\n")
        handle.write(f"visitor_commits={drift.visitor_commits}\n")
        handle.write(f"deployed_sha={drift.deployed.sha}\n")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--head", default="origin/main")
    parser.add_argument("--max-age-days", type=int, default=DEFAULT_MAX_AGE_DAYS)
    parser.add_argument("--json", action="store_true", help="emit the measurement as JSON")
    parser.add_argument(
        "--deployments-json",
        type=Path,
        help="read deployments from a file instead of the API (offline use and tests)",
    )
    args = parser.parse_args(argv)

    try:
        deployments, statuses_for = _readers(args)
        refresh = declared_refresh(publisher_workflow_text())
        deployed = newest_successful_deployment(deployments, statuses_for)
        drift = measure(deployed, args.head, datetime.now(UTC), args.max_age_days, refresh)
    except StalenessUnknown as exc:
        print(f"cannot measure deploy staleness: {exc}", file=sys.stderr)
        _write_github_output(None, str(exc))
        return 2

    print(json.dumps(as_json(drift), indent=2) if args.json else render(drift))
    _write_github_output(drift, None)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
