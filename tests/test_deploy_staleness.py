"""The detector that answers "is the observatory a visitor gets the one this repository has?".

Written from both directions, because the failure it replaces was a green gate. A detector that
cannot fire is noise and gets deleted; a detector that reports a number it did not really measure
is worse than none, because the number reads as a measurement and nobody re-derives it.

So the cases below cover the drift it must report AND every way the comparison can be meaningless
-- no deployment at all, a deployment that never succeeded, a commit this clone does not contain, a
history that has diverged, a publisher workflow that is not there. Each of those must end in a
refusal. None of them may end in a comfortable zero.

The cases specific to this repository are the ones about the *two* staleness questions.
``pages.yml`` republishes `main` daily to refresh the readings, so the deployed commit equals
`main` most days
and a commit-distance check alone would read zero forever while a dead cron served week-old
readings under a page that calls them current.
``test_a_dead_daily_refresh_fires_even_when_no_commit_is_waiting`` is that case, and
``test_the_two_verdicts_are_reported_separately`` is what stops the two from being summed into one
number that means neither.
"""

from __future__ import annotations

import importlib
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
SENTINEL_WORKFLOW = ROOT / ".github" / "workflows" / "deploy-staleness.yml"
if TYPE_CHECKING:
    from scripts import deploy_staleness as staleness
else:
    sys.path.insert(0, str(ROOT))
    staleness = importlib.import_module("scripts.deploy_staleness")

NOW = datetime(2026, 9, 13, 12, 0, tzinfo=UTC)
DEPLOY_TIME = "2026-09-13T16:09:43Z"


def _deployment(**over: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": 6423584071,
        "sha": "c" * 40,
        "environment": "github-pages",
        "created_at": DEPLOY_TIME,
    }
    row.update(over)
    return row


def _succeeded(_id: object) -> list[dict[str, str]]:
    return [{"state": "success"}]


def _never_succeeded(_id: object) -> list[dict[str, str]]:
    return [{"state": "failure"}, {"state": "in_progress"}]


# --- what the deployment record is allowed to mean --------------------------


def test_the_newest_successful_deployment_is_the_live_build() -> None:
    record = staleness.newest_successful_deployment([_deployment()], _succeeded)
    assert record.sha == "c" * 40
    assert record.created_at.date().isoformat() == "2026-09-13"
    assert record.deployment_id == 6423584071


def test_the_newest_deployment_wins_over_an_older_one() -> None:
    newer = _deployment(id=2, sha="d" * 40, created_at="2026-09-14T13:32:00Z")
    record = staleness.newest_successful_deployment([_deployment(), newer], _succeeded)
    assert record.sha == "d" * 40


def test_no_deployment_at_all_is_a_refusal_not_a_zero() -> None:
    with pytest.raises(staleness.StalenessUnknown, match="no github-pages deployment"):
        staleness.newest_successful_deployment([], _succeeded)


def test_a_deployment_that_never_succeeded_is_a_refusal() -> None:
    with pytest.raises(staleness.StalenessUnknown, match="successful status"):
        staleness.newest_successful_deployment([_deployment()], _never_succeeded)


def test_a_deploy_still_running_is_not_yet_the_live_build() -> None:
    """The daily cron's own run, caught mid-flight, must not be read as published bytes.

    This workflow deploys every day, so a scheduled run is in progress for part of every hour this
    sentinel might fire in. Counting its deployment row would date the live site to the run that
    has not finished uploading -- reporting the site as fresher than it is, which is the one
    direction of error this file exists to prevent.
    """
    running = _deployment(id=9, sha="e" * 40, created_at="2026-09-14T13:32:00Z")

    def statuses(deployment_id: object) -> list[dict[str, str]]:
        return [{"state": "in_progress"}] if deployment_id == 9 else [{"state": "success"}]

    record = staleness.newest_successful_deployment([_deployment(), running], statuses)
    assert record.sha == "c" * 40


def test_a_failed_newer_deployment_does_not_hide_the_successful_older_one() -> None:
    """A failed republish leaves the previous build serving; that is the live one."""
    failed = _deployment(id=9, sha="e" * 40, created_at="2026-09-14T13:32:00Z")

    def statuses(deployment_id: object) -> list[dict[str, str]]:
        return [{"state": "failure"}] if deployment_id == 9 else [{"state": "success"}]

    record = staleness.newest_successful_deployment([_deployment(), failed], statuses)
    assert record.sha == "c" * 40


def test_a_row_without_a_commit_id_is_not_a_deployment() -> None:
    with pytest.raises(staleness.StalenessUnknown, match="no github-pages deployment"):
        staleness.newest_successful_deployment([_deployment(sha="not-a-sha")], _succeeded)


# --- which files change what a visitor receives -----------------------------


@pytest.mark.parametrize(
    "path",
    [
        "web/index.html",
        "web/app.js",
        "web/styles.css",
        "web/sw.js",
        "web/i18n/es.json",
        "web/basemap.geojson",
        "web/planner/planner.js",
        "src/swelter/cli.py",
        "src/swelter/aggregate.py",
        "scripts/pages_seo.py",
        "scripts/stamp_pages_version.py",
        "scripts/build_demo_contract.py",
        ".github/workflows/pages.yml",
        "network.yaml",
        "data/demo/observations.jsonl",
    ],
)
def test_the_publishers_inputs_ship_to_visitors(path: str) -> None:
    assert staleness.ships_to_visitors(path)


@pytest.mark.parametrize(
    "path",
    [
        "tests/test_deploy_staleness.py",
        "docs/adr/0053-a-season-is-a-property-of-the-data-not-of-the-run.md",
        "firmware/src/main.py",
        "infra/cdk/app.py",
        "scripts/hygiene_check.py",
        "data/cooling_centers.geojson",
        "README.md",
        "uv.lock",
    ],
)
def test_everything_else_does_not(path: str) -> None:
    assert not staleness.ships_to_visitors(path)


@pytest.mark.parametrize(
    "path",
    [
        "web/package.json",
        "web/package-lock.json",
        "web/tests/build-i18n-runtime.cjs",
    ],
)
def test_the_vendored_runtimes_build_inputs_ship_to_visitors(path: str) -> None:
    """The non-obvious members of the set, and the ones a shorter list would drop.

    ``pages.yml`` runs ``npm --prefix web ci --omit=dev``, whose ``postinstall`` builds
    ``web/vendor/messageformat/`` out of the locked dependency and then deletes ``node_modules``.
    The runtime a visitor's browser executes is generated at deploy time from these three files
    (ADR 0026), so a clock blind to them would call the site current while the shipped
    message-formatting runtime changed underneath it.
    """
    assert staleness.ships_to_visitors(path)


@pytest.mark.parametrize("path", sorted(staleness.REPUBLISHED_AT_DEPLOY))
def test_what_the_deploy_rewrites_is_not_a_pending_change(path: str) -> None:
    """``swelter publish`` overwrites these from the store on every deploy, so a commit that

    changes only them changes no published byte. Counting them would fire on every refresh of the
    committed demo artifacts -- a false alarm on the most routine change this repository makes.
    """
    assert not staleness.ships_to_visitors(path)


def test_every_rewritten_file_is_inside_the_directory_it_excepts() -> None:
    """An exception that matches no path in the set excuses nothing and hides that it does not."""
    assert all(path.startswith("web/") for path in staleness.REPUBLISHED_AT_DEPLOY)


# --- the refresh cadence the publisher declares for itself -------------------


def test_the_committed_publisher_declares_a_daily_refresh() -> None:
    """Read out of ``pages.yml`` rather than restated here, so the two cannot drift apart."""
    refresh = staleness.declared_refresh(staleness.publisher_workflow_text(ROOT))

    assert refresh is not None
    assert refresh.period_days == 1
    assert refresh.threshold_days == 1 + staleness.REFRESH_GRACE_DAYS


def test_a_publisher_with_no_schedule_arms_no_age_verdict() -> None:
    """A push-only publisher promises nothing about freshness; holding it to one would be this

    check inventing a policy the repository never adopted.
    """
    assert staleness.declared_refresh("on:\n  push:\n    branches: [main]\n") is None


@pytest.mark.parametrize(
    ("expression", "days"),
    [
        ("30 13 * * *", 1),
        ("17 6 * * 1", 7),
        ("17 6 * * 1,4", 3),
        ("30 13 1 * *", None),
        ("30 13 * *", None),
        ("30 13 * * */2", None),
    ],
)
def test_a_cadence_it_will_not_guess_is_reported_as_unknown(
    expression: str, days: int | None
) -> None:
    assert staleness.cron_period_days(expression) == days


def test_a_missing_publisher_workflow_is_a_refusal(tmp_path: Path) -> None:
    """Not a missing optional input: without that workflow the publishing model assumed here is

    wrong, and every number would be measuring something other than the published site.
    """
    with pytest.raises(staleness.StalenessUnknown, match="publisher workflow"):
        staleness.publisher_workflow_text(tmp_path)


# --- the comparison against main, and every way it can be meaningless -------


@pytest.fixture
def clone(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "clone"
    root.mkdir()
    monkeypatch.setattr(staleness, "REPO_ROOT", root)
    _git("init", "-b", "main")
    _git("config", "user.email", "sentinel@example.test")
    _git("config", "user.name", "sentinel")
    return root


def _git(*args: str) -> str:
    """Drive the fixture repository through the module's own runner, monkeypatched at REPO_ROOT.

    Reusing it rather than calling ``subprocess`` again keeps this suite from adding a second
    fixed-argv ``S603`` suppression to the inventory #107 is ratcheting down, and it means a broken
    runner fails the setup loudly instead of silently building no history at all.
    """
    result = staleness._run_git(*args)
    assert result.returncode == 0, f"git {' '.join(args)} failed: {result.stderr}"
    return result.stdout.strip()


def _commit(root: Path, path: str, body: str = "x") -> str:
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")
    _git("add", path)
    _git("commit", "-m", f"touch {path}")
    return _git("rev-parse", "HEAD")


def _record(sha: str, created_at: datetime) -> staleness.DeployRecord:
    return staleness.DeployRecord(deployment_id=1, sha=sha, created_at=created_at)


DAILY = staleness.RefreshContract(period_days=1)


def test_it_counts_the_commits_and_names_the_visitor_visible_ones(clone: Path) -> None:
    deployed = _commit(clone, "README.md")
    _commit(clone, "tests/test_x.py")
    _commit(clone, "src/swelter/aggregate.py")
    _commit(clone, "web/index.html")

    drift = staleness.measure(_record(deployed, NOW - timedelta(days=63)), "HEAD", NOW)

    assert drift.commits == 3
    assert drift.visitor_commits == 2
    assert drift.days == 63
    assert drift.code_overdue


def test_age_alone_is_not_code_overdue(clone: Path) -> None:
    """A site nobody has republished because nothing it publishes changed is correct, not stale.

    Reporting on age alone would make this fire on every repository that is simply finished.
    """
    deployed = _commit(clone, "README.md")
    _commit(clone, "docs/adr/0054-something.md")

    drift = staleness.measure(_record(deployed, NOW - timedelta(days=200)), "HEAD", NOW)

    assert drift.commits == 1
    assert drift.visitor_commits == 0
    assert not drift.code_overdue


def test_inside_the_threshold_is_not_overdue(clone: Path) -> None:
    deployed = _commit(clone, "README.md")
    _commit(clone, "web/app.js")

    drift = staleness.measure(_record(deployed, NOW - timedelta(days=3)), "HEAD", NOW)

    assert drift.visitor_commits == 1
    assert not drift.code_overdue


def test_nothing_since_the_deploy_is_up_to_date(clone: Path) -> None:
    deployed = _commit(clone, "web/index.html")

    drift = staleness.measure(
        _record(deployed, NOW - timedelta(hours=4)), "HEAD", NOW, refresh=DAILY
    )

    assert drift.commits == 0
    assert drift.visitor_commits == 0
    assert not drift.overdue
    assert "Code up to date" in staleness.render(drift)


def test_a_commit_this_clone_does_not_have_is_a_refusal(clone: Path) -> None:
    """The shallow-checkout case, which is the one that reports zero silently.

    ``git log <absent>..HEAD`` on a shallow clone lists nothing, so the site reads as current. This
    is why the sentinel workflow checks out with ``fetch-depth: 0``, and why the refusal exists
    rather than trusting that it did.
    """
    _commit(clone, "README.md")

    with pytest.raises(staleness.StalenessUnknown, match="not in this clone"):
        staleness.measure(_record("a" * 40, NOW - timedelta(days=63)), "HEAD", NOW)


def test_a_diverged_history_is_a_refusal(clone: Path) -> None:
    _commit(clone, "README.md")
    _git("checkout", "-b", "other")
    orphan = _commit(clone, "orphan.txt")
    _git("checkout", "main")

    with pytest.raises(staleness.StalenessUnknown, match="not an ancestor"):
        staleness.measure(_record(orphan, NOW - timedelta(days=63)), "HEAD", NOW)


def test_a_malformed_deployed_sha_is_a_refusal(clone: Path) -> None:
    _commit(clone, "README.md")

    with pytest.raises(staleness.StalenessUnknown, match="not a commit id"):
        staleness.measure(_record("nope", NOW), "HEAD", NOW)


# --- the two staleness questions, kept apart --------------------------------


def test_a_dead_daily_refresh_fires_even_when_no_commit_is_waiting(clone: Path) -> None:
    """The failure this repository can actually have, and the one a commit-distance check misses.

    ``pages.yml`` republishes `main` every day to refresh the readings, so the deployed commit is
    `main`'s head almost always and ``visitor_commits`` reads zero almost always. If the cron stops
    landing and no visitor-visible commit happens to arrive, commit distance stays at zero forever
    while the site serves week-old readings under a page that calls them current. Age is the only
    signal that moves, and it moves only because the workflow itself declares a daily cadence.
    """
    deployed = _commit(clone, "web/index.html")

    drift = staleness.measure(
        _record(deployed, NOW - timedelta(days=9)), "HEAD", NOW, refresh=DAILY
    )

    assert drift.visitor_commits == 0
    assert not drift.code_overdue
    assert drift.refresh_overdue
    assert drift.overdue


def test_a_refresh_inside_its_own_grace_is_not_overdue(clone: Path) -> None:
    """One missed cron run and the retry after it is not an incident; a stopped cron is."""
    deployed = _commit(clone, "web/index.html")

    drift = staleness.measure(
        _record(deployed, NOW - timedelta(days=2)), "HEAD", NOW, refresh=DAILY
    )

    assert not drift.refresh_overdue


def test_without_a_declared_cadence_age_never_fires(clone: Path) -> None:
    """The disarm. A publisher that makes no refresh promise is not held to one."""
    deployed = _commit(clone, "web/index.html")

    drift = staleness.measure(_record(deployed, NOW - timedelta(days=200)), "HEAD", NOW)

    assert drift.refresh is None
    assert not drift.refresh_overdue
    assert not drift.overdue
    assert "declares no schedule" in staleness.render(drift)


def test_the_two_verdicts_are_reported_separately(clone: Path) -> None:
    """Neither question may be answered with the other one's number.

    A single `overdue` flag would let a stale-readings finding read as a stale-code finding, and
    the two have different causes and different fixes: one is a publisher that stopped running,
    the other is a merge that never reached a reader.
    """
    deployed = _commit(clone, "README.md")
    _commit(clone, "web/app.js")

    drift = staleness.measure(
        _record(deployed, NOW - timedelta(days=30)), "HEAD", NOW, refresh=DAILY
    )
    payload = staleness.as_json(drift)

    assert payload["code_overdue"] is True
    assert payload["refresh_overdue"] is True
    assert payload["refresh_period_days"] == 1
    report = staleness.render(drift)
    assert "OVERDUE (code)" in report
    assert "OVERDUE (refresh)" in report


# --- the report, and the exit code ------------------------------------------


def test_the_report_states_the_measurement_before_its_verdict(clone: Path) -> None:
    deployed = _commit(clone, "README.md")
    _commit(clone, "web/index.html")
    drift = staleness.measure(_record(deployed, NOW - timedelta(days=63)), "HEAD", NOW)

    report = staleness.render(drift)

    assert deployed[:9] in report
    assert "63 days ago" in report
    assert report.index("Behind by") < report.index("OVERDUE (code)")


def test_the_report_names_the_question_it_did_not_answer(clone: Path) -> None:
    """The conflation guard, in the text a reader actually sees.

    A deployment that succeeded, restored a cached store and fell back to a coarser source
    publishes fresh bytes full of old readings. Nothing available here can see that, and a report
    that said "fresh" without saying so would be the exact error this file refuses.
    """
    deployed = _commit(clone, "web/index.html")
    drift = staleness.measure(
        _record(deployed, NOW - timedelta(hours=2)), "HEAD", NOW, refresh=DAILY
    )

    assert "Not measured: how old the readings" in staleness.render(drift)


def test_the_json_carries_every_number_the_report_states(clone: Path) -> None:
    deployed = _commit(clone, "README.md")
    _commit(clone, "web/index.html")
    drift = staleness.measure(_record(deployed, NOW - timedelta(days=63)), "HEAD", NOW)

    payload = staleness.as_json(drift)

    assert payload["deployed_sha"] == deployed
    assert payload["days"] == 63
    assert payload["commits"] == 1
    assert payload["visitor_commits"] == 1
    assert payload["overdue"] is True


def test_the_cli_refuses_with_a_nonzero_exit_when_it_cannot_measure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Exit 2, not 0 with a reassuring report. The sentinel workflow turns a measurement into an

    issue and a refusal into a red run, so this exit code is the whole difference between "the site
    is fine" and "nobody can tell".
    """
    payload = tmp_path / "deployments.json"
    payload.write_text('{"deployments": [], "statuses": {}}', encoding="utf-8")

    code = staleness.main(["--deployments-json", str(payload)])

    assert code == 2
    assert "cannot measure" in capsys.readouterr().err


# --- the sentinel's own blast radius ----------------------------------------


def test_the_sentinel_holds_no_publishing_credential() -> None:
    """It reports on publishing; it must never be able to publish.

    Asserted against the **parsed** workflow, never against its text. The file's own header comment
    says in so many words that it holds no ``pages: write`` and no ``id-token: write``, so a check
    that grepped for those strings would find them in the disclaimer and could be made to pass --
    or fail -- by a sentence nobody executes. ``yaml.safe_load`` drops comments by construction,
    which is a stronger guarantee than remembering to strip them.
    """
    workflow = yaml.safe_load(SENTINEL_WORKFLOW.read_text(encoding="utf-8"))

    assert workflow["permissions"] == {}
    assert workflow["jobs"]["report"]["permissions"] == {
        "contents": "read",
        "deployments": "read",
        "issues": "write",
    }


def test_the_sentinel_cannot_be_triggered_by_a_push_or_a_pull_request() -> None:
    """Weekly and on demand. A publisher-adjacent job on `push` is how a reporting tool starts

    being part of the deploy path, and a `pull_request` trigger would put an unrequired job on
    every merge (see tests/test_ruleset.py for what that costs).
    """
    workflow = yaml.safe_load(SENTINEL_WORKFLOW.read_text(encoding="utf-8"))
    triggers = workflow.get(True) or workflow.get("on")

    assert set(triggers) == {"schedule", "workflow_dispatch"}
