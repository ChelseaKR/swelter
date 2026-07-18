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
    untracked.write_text("value = 1  # noqa: F841\n", encoding="utf-8")
    assert any("no linked issue" in problem for problem in hygiene_check._scan([untracked]))

    tracked = tmp_path / "tracked.py"
    tracked.write_text("value = 1  # noqa: F841 (#107)\n", encoding="utf-8")
    assert hygiene_check._scan([tracked]) == []


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


def test_pages_cache_annotation_exception_is_exactly_bound(tmp_path: Path) -> None:
    workflow = tmp_path / "pages.yml"
    workflow.write_text(
        "permissions:\n"
        "  contents: read\n"
        "jobs:\n"
        "  deploy:\n"
        "    steps:\n"
        "      - uses: actions/cache@0057852bfaa89a56745cba8c7296529d2fc39830 # v4\n"
        "# actions/cache@0057852bfaa89a56745cba8c7296529d2fc39830 # v4.3.0\n",
        encoding="utf-8",
    )
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
