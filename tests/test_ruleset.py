"""The committed branch ruleset names every gate a pull request runs, or says why not.

Branch protection is a repository setting. It can be widened, narrowed, or deleted without a
commit, and the history would not show it, so `.github/rulesets/main.json` is committed as the
evidence the README's CI/CD row is checked against. `ci.yml` already carries a comment on the
`a11y` job warning that its published name is pinned by "the existing repository ruleset" -- a
constraint the code obeyed while nothing in the repository stated it.

The invariant here is deliberately *not* "the committed file still matches the live ruleset". A
public-scope token cannot read `bypass_actors`, and a comparison that silently drops a field it
could not read is a check that passes for the wrong reason -- the failure mode this repository
already names elsewhere as absence rendered as a value. The invariant is the mistake this
repository can actually make: **a job runs on a pull request, goes red, and the pull request
merges anyway**, because nothing ever made it required.

That is not hypothetical. When this file was written, two jobs ran on every pull request and
neither could block one: `web-tests`, which runs the target `docs/ROADMAP.md` names as the AUTO
gate for the web interaction contract and which
[#105](https://github.com/ChelseaKR/swelter/issues/105) already names as a deferred control, and
`scorecard`. They are enumerated in `NOT_REQUIRED` below with a reason each, so the list is
reviewable rather than invisible, and so a *third* one cannot appear without this suite failing.
"""

from __future__ import annotations

import importlib
import itertools
import json
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import yaml

ROOT = Path(__file__).resolve().parent.parent
if TYPE_CHECKING:
    from scripts import workflow_policy_check
else:
    sys.path.insert(0, str(ROOT))
    workflow_policy_check = importlib.import_module("scripts.workflow_policy_check")

RULESET = ROOT / ".github" / "rulesets" / "main.json"
WORKFLOWS = ROOT / ".github" / "workflows"

#: `${{ matrix.language }}` inside a job's `name:`. GitHub substitutes the leg's value there
#: rather than appending it, which is why the live check is `analyze (python)` and not
#: `analyze (${{ matrix.language }}) (python)`.
_MATRIX_REFERENCE = re.compile(r"\$\{\{\s*matrix\.([A-Za-z_][A-Za-z0-9_-]*)\s*\}\}")

#: Jobs that run on a pull request and are deliberately not required to merge. Each entry is a
#: claim someone has to defend at review time; deleting a job from this table without making it
#: required fails `test_every_unrequired_pull_request_job_is_declared`.
NOT_REQUIRED: dict[str, str] = {
    "web-tests": (
        "NOT REQUIRED, and this is the one that should change. It runs `make web-unit` -- the "
        "dashboard unit, schema, i18n, and conformance tests. The ROADMAP metrics ledger names "
        "`make web-test` as the AUTO gate for the web interaction contract, and `make web-test` "
        "is an alias for exactly this target. An AUTO gate that cannot block a merge is a gate in "
        "name only. Issue #105 already lists "
        "'strict required checks including web-tests' among the governance controls deferred from "
        "the July 2026 remediation, so this is a known, owner-held decision rather than a "
        "discovery. It stays as-is here because making a check required is a repository-settings "
        "change, and this repository's own history says that must be a deliberate act rather than "
        "a side effect of a pull request."
    ),
    "scorecard": (
        "OpenSSF Scorecard grades the posture of the whole repository, not the diff, and its own "
        "`if:` declines to analyze pull requests opened from a fork. Requiring it would gate every "
        "merge on a portfolio-wide trend score that the pull request under review may not have "
        "moved, and `publish_results` is off for pull requests anyway, so the pull-request run is "
        "a smoke test of the scanner rather than a verdict on the change. The scheduled Thursday "
        "run is where its result is meant to be read."
    ),
}


def committed_ruleset() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(RULESET.read_text(encoding="utf-8")))


def required_contexts() -> set[str]:
    for rule in committed_ruleset()["rules"]:
        if rule["type"] == "required_status_checks":
            checks = rule["parameters"]["required_status_checks"]
            return {check["context"] for check in checks}
    raise AssertionError("the committed ruleset requires no status checks at all")


def _excludes_pull_requests(clause: str) -> bool:
    """Whether one `||` alternative of a job-level `if:` can never hold on a pull request."""
    if re.search(r"github\.event_name\s*!=\s*['\"]pull_request['\"]", clause):
        return True
    pinned = re.search(r"github\.event_name\s*==\s*['\"]([a-z_]+)['\"]", clause)
    return pinned is not None and pinned.group(1) != "pull_request"


def runs_on_pull_request(condition: object) -> bool:
    """A job runs on a pull request unless *every* alternative in its `if:` rules one out.

    The disjunction matters. `scorecard` guards itself with
    `github.event_name != 'pull_request' || <head repo is this repo>`, which is a fork guard,
    not a pull-request exclusion: the job runs, and reports, on every same-repository pull
    request. A checker that matched `!= 'pull_request'` anywhere in the string would drop it
    silently -- and dropping it is exactly how an unrequired pull-request job stays invisible.
    """
    if condition is None:
        return True
    return not all(_excludes_pull_requests(clause) for clause in str(condition).split("||"))


def _matrix_axes(job: dict[str, Any]) -> dict[str, list[Any]]:
    matrix = (job.get("strategy") or {}).get("matrix") or {}
    if not isinstance(matrix, dict):
        return {}
    return {key: value for key, value in matrix.items() if isinstance(value, list)}


def _substitute(name: str, leg: dict[str, Any]) -> str:
    return _MATRIX_REFERENCE.sub(lambda match: str(leg[match.group(1)]), name)


def _expand(name: str, axes: dict[str, list[Any]]) -> set[str]:
    """Render a job's check names the way GitHub does, one per matrix leg."""
    if not axes:
        return {name}
    references_matrix = bool(_MATRIX_REFERENCE.search(name))
    names: set[str] = set()
    for combination in itertools.product(*axes.values()):
        if references_matrix:
            names.add(_substitute(name, dict(zip(axes.keys(), combination, strict=True))))
        else:
            names.add(f"{name} ({', '.join(str(value) for value in combination)})")
    return names


def _workflow_files() -> list[Path]:
    """Every file GitHub Actions would treat as a workflow, per the existing gate's own list.

    `scripts/workflow_policy_check.py:13-18` records this repository already making the other
    mistake: that gate globbed `*.yml` alone, so a workflow committed as `.yaml` was invisible to
    it while it still claimed to have checked every one. A gate that makes a claim about a set has
    to enumerate the whole set, and here an unseen workflow is an unseen unrequired job. Its
    `WORKFLOW_SUFFIXES` is reused rather than restated so the two gates cannot come to disagree
    about what a workflow is.
    """
    suffixes: tuple[str, ...] = workflow_policy_check.WORKFLOW_SUFFIXES
    return sorted(path for suffix in suffixes for path in WORKFLOWS.glob(suffix))


def pull_request_check_names() -> set[str]:
    """Every check name a pull request in this repository can produce, matrix legs expanded."""
    names: set[str] = set()
    for path in _workflow_files():
        workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert isinstance(workflow, dict), f"{path.name} is not a workflow mapping"
        triggers = workflow.get(True) or workflow.get("on") or {}
        if not isinstance(triggers, dict) or "pull_request" not in triggers:
            continue
        jobs = workflow.get("jobs") or {}
        assert isinstance(jobs, dict), f"{path.name} declares no jobs mapping"
        for job_id, job in jobs.items():
            if not runs_on_pull_request(job.get("if")):
                continue
            names |= _expand(str(job.get("name", job_id)), _matrix_axes(job))
    return names


def test_every_unrequired_pull_request_job_is_declared() -> None:
    """A job that runs on a pull request either blocks the merge or is named in NOT_REQUIRED."""
    undeclared = pull_request_check_names() - required_contexts() - set(NOT_REQUIRED)
    assert not undeclared, (
        "these jobs run on a pull request, are not required by the committed ruleset, and are not "
        f"declared in NOT_REQUIRED, so each can go red and still merge: {sorted(undeclared)}"
    )


def test_no_required_check_names_a_job_that_cannot_report() -> None:
    """A required context nothing produces never turns green, so it blocks every merge forever."""
    stale = required_contexts() - pull_request_check_names()
    assert not stale, (
        "the committed ruleset requires status checks that no pull-request job produces, which "
        f"would wedge every merge: {sorted(stale)}"
    )


def test_the_exemption_list_does_not_outlive_its_jobs() -> None:
    """An exemption for a job no pull request runs any more excuses nothing and hides that."""
    gone = set(NOT_REQUIRED) - pull_request_check_names()
    assert not gone, f"NOT_REQUIRED excuses jobs no pull request runs: {sorted(gone)}"


def test_no_job_is_both_required_and_excused() -> None:
    """A job cannot be both required and exempt; one of the two statements is then false."""
    both = set(NOT_REQUIRED) & required_contexts()
    assert not both, f"required by the ruleset AND excused in NOT_REQUIRED: {sorted(both)}"


def test_every_exemption_carries_a_written_reason() -> None:
    assert all(reason.strip() for reason in NOT_REQUIRED.values()), (
        "an exemption with an empty reason is an undeclared exemption wearing a table row"
    )


def test_the_ruleset_still_refuses_deletion_and_force_push() -> None:
    types = {rule["type"] for rule in committed_ruleset()["rules"]}
    assert {"deletion", "non_fast_forward"} <= types


def test_the_ruleset_is_active_on_main() -> None:
    ruleset = committed_ruleset()
    assert ruleset["enforcement"] == "active"
    assert "refs/heads/main" in ruleset["conditions"]["ref_name"]["include"]


def test_the_bypass_actors_are_stated_rather_than_omitted() -> None:
    """The admin bypass is real. A file that omits it is a file that lies politely."""
    assert "bypass_actors" in committed_ruleset(), (
        "bypass_actors is absent from the committed ruleset; an omitted bypass reads as no "
        "bypass, which is a stronger claim than this repository can make"
    )


def test_the_fork_guard_shape_is_read_as_running_on_pull_requests() -> None:
    """Lock in the disjunction reading, since getting it wrong would hide a real finding."""
    fork_guard = (
        "github.event_name != 'pull_request' || "
        "github.event.pull_request.head.repo.full_name == github.repository"
    )
    assert runs_on_pull_request(fork_guard)
    assert not runs_on_pull_request("github.event_name == 'push'")
    assert not runs_on_pull_request("github.event_name != 'pull_request'")
    assert runs_on_pull_request(None)


def test_both_workflow_suffixes_are_scanned() -> None:
    """A workflow committed as `.yaml` must not be an invisible source of unrequired jobs."""
    assert _workflow_files(), "no workflows were found at all, so every assertion above is vacuous"
    assert {path.name for path in _workflow_files()} >= {"ci.yml", "codeql.yml", "scorecard.yml"}
    assert set(workflow_policy_check.WORKFLOW_SUFFIXES) == {"*.yml", "*.yaml"}


def test_matrix_legs_are_named_the_way_github_names_them() -> None:
    """`analyze (python)` must not read as missing because the ruleset spells out the leg."""
    assert _expand("analyze (${{ matrix.language }})", {"language": ["python", "actions"]}) == {
        "analyze (python)",
        "analyze (actions)",
    }
    assert _expand("test", {"python": ["3.12", "3.13"]}) == {"test (3.12)", "test (3.13)"}
