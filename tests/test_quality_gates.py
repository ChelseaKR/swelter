"""Behavioral tests for repository-local quality, release, and safety gates."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

ROOT = Path(__file__).resolve().parent.parent
if TYPE_CHECKING:
    from scripts import (
        docs_contract_check,
        hygiene_check,
        i18n_parity,
        log_safety_check,
        reading_level_check,
        standards_pin_check,
        version_check,
        workflow_policy_check,
    )
else:
    sys.path.insert(0, str(ROOT))
    docs_contract_check = importlib.import_module("scripts.docs_contract_check")
    hygiene_check = importlib.import_module("scripts.hygiene_check")
    i18n_parity = importlib.import_module("scripts.i18n_parity")
    log_safety_check = importlib.import_module("scripts.log_safety_check")
    reading_level_check = importlib.import_module("scripts.reading_level_check")
    standards_pin_check = importlib.import_module("scripts.standards_pin_check")
    version_check = importlib.import_module("scripts.version_check")
    workflow_policy_check = importlib.import_module("scripts.workflow_policy_check")


def test_dependency_free_reading_score_orders_plain_before_complex() -> None:
    plain = "Heat is high. Rest in shade and drink water."
    complex = (
        "Meteorological instrumentation necessitates interdisciplinary contextualization "
        "before interpretation."
    )
    assert reading_level_check.flesch_kincaid_grade(plain) < 8
    assert reading_level_check.flesch_kincaid_grade(complex) > 8


def test_documentation_contract_is_current() -> None:
    assert docs_contract_check.main() == 0


def test_syllable_estimator_is_stable_for_common_civic_words() -> None:
    assert reading_level_check._syllables("heat") == 1
    assert reading_level_check._syllables("water") == 2
    assert reading_level_check._syllables("community") >= 3


def test_version_check_uses_current_release_ref(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_REF_TYPE", "tag")
    monkeypatch.setenv("GITHUB_REF_NAME", "v0.1.0")
    assert version_check._release_ref_version() == "0.1.0"


def test_version_check_rejects_non_semver_tag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_REF_TYPE", "tag")
    monkeypatch.setenv("GITHUB_REF_NAME", "latest")
    try:
        version_check._release_ref_version()
    except ValueError as exc:
        assert "not vMAJOR.MINOR.PATCH" in str(exc)
    else:
        raise AssertionError("non-SemVer release tag must fail")


def test_hygiene_requires_issue_link_for_suppression(tmp_path: Path) -> None:
    untracked = tmp_path / "untracked.py"
    # Assemble the marker at runtime so this test file's own git-tracked source does not
    # contain a bare suppression token that would trip the hygiene gate that scans it.
    bare_noqa = "# " + "noqa: F841"
    untracked.write_text(f"value = 1  {bare_noqa}\n", encoding="utf-8")
    assert any("no linked issue" in problem for problem in hygiene_check._scan([untracked]))

    tracked = tmp_path / "tracked.py"
    tracked.write_text("value = 1  # noqa: F841 (#107)\n", encoding="utf-8")
    assert hygiene_check._scan([tracked]) == []


def test_hygiene_ceiling_rejects_a_new_suppression() -> None:
    """Coding and linking a suppression makes it legible, not temporary. Without a count,
    the inventory can grow forever with the gate green — which is why #107's close
    condition was unreachable by running the gate."""
    problems = hygiene_check.check_ceiling(30, ceiling=29)
    assert problems and "ceiling is 29" in problems[0]


def test_hygiene_ceiling_demands_the_win_be_locked_in() -> None:
    """The ratchet only ratchets if going down is also a failure. A ceiling left high after
    a retirement hands the slack straight back to the next PR."""
    problems = hygiene_check.check_ceiling(28, ceiling=29)
    assert problems and "Lower SUPPRESSION_CEILING to 28" in problems[0]


def test_hygiene_ceiling_is_silent_when_exact() -> None:
    assert hygiene_check.check_ceiling(29, ceiling=29) == []


def test_hygiene_counts_markers_not_lines(tmp_path: Path) -> None:
    """Two suppressions on one line are two suppressions. Counting lines would make
    retiring one of them look like no change at all — the exact case this PR hit."""
    source = tmp_path / "two.py"
    # Both markers are assembled at runtime: a literal one here would be counted by the very
    # gate that scans this file, and a test that changes the number it asserts is not a test.
    noqa = "# " + "noqa: E501 (#107)"
    ignore = "nosem" + "grep: some.rule (#107)"
    source.write_text(f"from x import y  # {ignore}  {noqa}\n", encoding="utf-8")
    assert sum(hygiene_check.count_suppressions([source]).values()) == 2


def test_hygiene_ceiling_matches_the_repository() -> None:
    """The committed ceiling is the real number on this branch, not an aspiration."""
    paths = hygiene_check._tracked_files(*hygiene_check.SCAN_DIRS)
    total = sum(hygiene_check.count_suppressions(paths).values())
    assert total == hygiene_check.SUPPRESSION_CEILING


def test_log_safety_rejects_pii_field_and_dynamic_message(tmp_path: Path) -> None:
    source = tmp_path / "unsafe.py"
    source.write_text(
        "import logging\n"
        "logger = logging.getLogger(__name__)\n"
        "message = 'request'\n"
        "logger.info(message, extra={'email': 'person@example.org'})\n",
        encoding="utf-8",
    )
    problems = log_safety_check.scan_python(source)
    assert any("unstructured/interpolated" in problem for problem in problems)
    assert any("forbidden extra field 'email'" in problem for problem in problems)
    assert any("sensitive literal" in problem for problem in problems)


def test_log_safety_accepts_allowlisted_structured_event(tmp_path: Path) -> None:
    source = tmp_path / "safe.py"
    source.write_text(
        "from swelter import obs\n"
        "obs.log_event('server', 'request', method='GET', path='/health', "
        "status=200, node_id='node-1')\n",
        encoding="utf-8",
    )
    assert log_safety_check.scan_python(source) == []


def test_vendored_standards_match_canonical_manifest() -> None:
    assert standards_pin_check.main() == 0


_EXEMPT_SHA = "0057852bfaa89a56745cba8c7296529d2fc39830"
_EXEMPT_KEY = ("pages.yml", "actions/cache", _EXEMPT_SHA, "v4")


def _exempt_workflow(tmp_path: Path) -> Path:
    workflow = tmp_path / "pages.yml"
    workflow.write_text(
        "permissions:\n"
        "  contents: read\n"
        "jobs:\n"
        "  deploy:\n"
        "    steps:\n"
        f"      - uses: actions/cache@{_EXEMPT_SHA} # v4\n"
        f"# actions/cache@{_EXEMPT_SHA} # v4.3.0\n",
        encoding="utf-8",
    )
    return workflow


def test_pages_cache_annotation_exception_is_exactly_bound(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The exemption mechanism is exercised through an injected table rather than through whatever
    # the live table happens to hold. A test that only passes while a particular pin is committed
    # stops testing the mechanism the moment that pin is bumped, which is exactly what happened.
    monkeypatch.setattr(
        workflow_policy_check, "_PROTECTED_VERSION_ANNOTATIONS", {_EXEMPT_KEY: "v4.3.0"}
    )
    workflow = _exempt_workflow(tmp_path)
    assert workflow_policy_check.scan_workflow(workflow) == []

    workflow.write_text(
        workflow.read_text(encoding="utf-8").replace(
            "0057852bfaa89a56745cba8c7296529d2fc39830 # v4\n",
            "1111111111111111111111111111111111111111 # v4\n",
            1,
        ),
        encoding="utf-8",
    )
    assert any(
        "no exact trailing semver" in problem
        for problem in workflow_policy_check.scan_workflow(workflow)
    )


def test_a_version_exemption_that_outlives_its_workflow_line_is_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An exemption is a hole cut in a security gate. When the line it was cut for is bumped
    away, the hole stays, excusing nothing and matched by nothing -- so nobody learns it can be
    closed. That is what the live table did: it was keyed on an `actions/cache` SHA that left
    `pages.yml` at the v4.3.0 -> v6.1.0 bump and stayed in the table afterwards, reachable by
    no `uses:` line in any workflow."""
    monkeypatch.setattr(
        workflow_policy_check, "_PROTECTED_VERSION_ANNOTATIONS", {_EXEMPT_KEY: "v4.3.0"}
    )
    workflow = _exempt_workflow(tmp_path)
    assert workflow_policy_check.stale_exemptions([workflow]) == []

    workflow.write_text(
        workflow.read_text(encoding="utf-8").replace(_EXEMPT_SHA, "b" * 40),
        encoding="utf-8",
    )
    stale = workflow_policy_check.stale_exemptions([workflow])
    assert stale and "matches no uses: line" in stale[0]


def test_the_live_version_exemption_table_has_no_stale_entries() -> None:
    """The committed table, against the committed workflows. This is the assertion that would
    have failed while the retired `actions/cache` entry was still there."""
    assert workflow_policy_check.stale_exemptions(workflow_policy_check.workflow_files()) == []


def test_log_safety_gate_refuses_to_pass_when_it_scans_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Same defect class as `test_workflow_policy_gate_refuses_to_pass_on_no_workflows` and
    `test_reading_level_gate_refuses_to_pass_when_it_scores_nothing`, in the gate with the
    highest stake: this one's PASS line is "production log calls are structured and PII-safe".
    Its corpus is `git ls-files '*.py'` filtered by SCAN_DIRS, so renaming `src/` or a git call
    that returns nothing emptied it silently and the gate printed the same sentence."""
    monkeypatch.setattr(log_safety_check, "_tracked_python", list)
    assert log_safety_check.main() == 1


def test_log_safety_gate_names_every_production_directory_it_missed() -> None:
    grouped: dict[str, list[Path]] = {name: [] for name in log_safety_check.SCAN_DIRS}
    problems = log_safety_check.corpus_problems(grouped)
    assert len(problems) == len(log_safety_check.SCAN_DIRS)
    assert all("empty corpus" in problem for problem in problems)


def test_log_safety_gate_still_covers_every_production_directory() -> None:
    """The guard is only worth anything if the real corpus satisfies it: every configured scan
    directory must actually contribute files today."""
    grouped = log_safety_check.scan_targets(log_safety_check._tracked_python())
    assert log_safety_check.corpus_problems(grouped) == []
    assert all(grouped[name] for name in log_safety_check.SCAN_DIRS)


def test_two_empty_catalogs_are_not_at_parity() -> None:
    """`_check_catalog`'s three set comparisons are all satisfied by two empty catalogs, so an
    emptied or truncated `en.json` read as "EN/ES at key parity (0 keys)". Parity over nothing
    is not parity, and this gate is the floor the accessibility gate assumes."""
    assert i18n_parity._check_catalog("empty", {}, {}) == 1
    assert i18n_parity._check_catalog("real", {"a": "A"}, {"a": "A"}) == 0


def test_workflow_policy_gate_scans_yaml_workflows_too(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # GitHub runs `.yaml` workflows exactly as it runs `.yml` ones. The gate globbed `*.yml`
    # alone, so a workflow committed as `.yaml` was invisible to it — unpinned actions, `|| true`,
    # `continue-on-error: true` and a credential-persisting checkout all passed — while the gate
    # still printed that *every* action is SHA-pinned and fail-closed.
    (tmp_path / "pinned.yml").write_text(
        "permissions:\n  contents: read\njobs: {}\n", encoding="utf-8"
    )
    (tmp_path / "unpinned.yaml").write_text(
        "permissions:\n"
        "  contents: read\n"
        "jobs:\n"
        "  build:\n"
        "    steps:\n"
        "      - uses: actions/checkout@v4\n"
        "      - run: ./flaky.sh || true\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(workflow_policy_check, "WORKFLOWS", tmp_path)

    assert workflow_policy_check.main() == 1
    assert [path.name for path in workflow_policy_check.workflow_files(tmp_path)] == [
        "pinned.yml",
        "unpinned.yaml",
    ]


def test_workflow_policy_gate_refuses_to_pass_on_no_workflows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A gate whose output is a universal claim must not make one about an empty set: scanning
    # nothing is not the same as finding nothing wrong.
    monkeypatch.setattr(workflow_policy_check, "WORKFLOWS", tmp_path)
    assert workflow_policy_check.main() == 1


def test_reading_level_gate_refuses_to_pass_when_it_scores_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Same defect, other gate: the corpus is whatever survives `_scorable_strings`, and a catalog
    # of nothing but short labels used to print "[PASS] all 0 scored strings are at or below
    # grade 8". A reading-level gate that scored no prose has not held the reading level.
    catalog = tmp_path / "en.json"
    catalog.write_text('{"units": "Units", "language": "Language"}', encoding="utf-8")
    monkeypatch.setattr(reading_level_check, "EN_CATALOG", catalog)

    assert reading_level_check._scorable_strings({"units": "Units"}) == {}
    assert reading_level_check.main() == 1
