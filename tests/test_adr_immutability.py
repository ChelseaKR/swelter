"""Accepted ADRs are append-only; reversals arrive as new superseding records."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

ROOT = Path(__file__).resolve().parent.parent
if TYPE_CHECKING:
    from scripts import adr_immutability_check, docs_contract_check
else:
    sys.path.insert(0, str(ROOT))
    adr_immutability_check = importlib.import_module("scripts.adr_immutability_check")
    docs_contract_check = importlib.import_module("scripts.docs_contract_check")


def _adr(status: str, decision: str = "Keep history.") -> bytes:
    return (
        "# ADR 0001: Test decision\n\n"
        f"- Status: {status}\n"
        "- Date: 2026-07-16\n"
        "- Deciders: Test\n\n"
        "## Context\n\nContext.\n\n"
        f"## Decision\n\n{decision}\n\n"
        "## Consequences\n\nConsequences.\n"
    ).encode()


def _write(repo: Path, relative: str, content: bytes) -> None:
    path = repo / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _git(repo: Path, *args: str) -> None:
    result = adr_immutability_check._run_git(repo, *args)
    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")


def test_accepted_base_adr_must_remain_byte_identical(tmp_path: Path) -> None:
    relative = "docs/adr/0001-test-decision.md"
    historical = _adr("Accepted")
    _write(tmp_path, relative, historical)
    assert adr_immutability_check.immutability_problems(tmp_path, {relative: historical}) == []

    _write(tmp_path, relative, _adr("Accepted", "Rewrite history."))
    problems = adr_immutability_check.immutability_problems(tmp_path, {relative: historical})
    assert len(problems) == 1
    assert "changed" in problems[0]
    assert "superseding ADR" in problems[0]


def test_deleted_accepted_adr_fails(tmp_path: Path) -> None:
    relative = "docs/adr/0001-test-decision.md"
    problems = adr_immutability_check.immutability_problems(tmp_path, {relative: _adr("Accepted")})
    assert len(problems) == 1
    assert "deleted" in problems[0]


def test_new_superseding_adr_is_allowed_when_old_record_is_unchanged(tmp_path: Path) -> None:
    old = "docs/adr/0001-test-decision.md"
    historical = _adr("Accepted")
    _write(tmp_path, old, historical)
    _write(tmp_path, "docs/adr/0002-supersede-test-decision.md", _adr("Accepted", "Replace 0001."))
    assert adr_immutability_check.immutability_problems(tmp_path, {old: historical}) == []


def test_nonaccepted_base_adr_can_change_or_be_removed(tmp_path: Path) -> None:
    relative = "docs/adr/0001-test-decision.md"
    assert (
        adr_immutability_check.immutability_problems(tmp_path, {relative: _adr("Proposed")}) == []
    )


def test_git_base_loader_compares_the_worktree_to_the_selected_commit(tmp_path: Path) -> None:
    _git(tmp_path, "init", "--quiet")
    _git(tmp_path, "config", "user.name", "ADR Test")
    _git(tmp_path, "config", "user.email", "adr-test@example.invalid")
    _git(tmp_path, "config", "commit.gpgsign", "false")
    relative = "docs/adr/0001-test-decision.md"
    historical = _adr("Accepted")
    _write(tmp_path, relative, historical)
    _git(tmp_path, "add", relative)
    _git(tmp_path, "commit", "--quiet", "-m", "accept decision")

    commit = adr_immutability_check._resolve_commit(tmp_path, "HEAD")
    assert commit is not None
    loaded = adr_immutability_check.base_adrs(tmp_path, commit)
    assert loaded == {relative: historical}

    _write(tmp_path, relative, _adr("Accepted", "Rewrite history."))
    assert len(adr_immutability_check.immutability_problems(tmp_path, loaded)) == 1


def test_explicit_argument_and_environment_precede_automatic_base(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commits = {"argument": "a" * 40, "environment": "e" * 40, "origin/main": "m" * 40}
    monkeypatch.setattr(
        adr_immutability_check,
        "_resolve_commit",
        lambda _repo, ref: commits.get(ref),
    )
    env = {adr_immutability_check.BASE_ENV: "environment"}
    explicit = adr_immutability_check.resolve_base(Path("."), explicit="argument", environ=env)
    configured = adr_immutability_check.resolve_base(Path("."), environ=env)
    assert (explicit.label, explicit.source) == ("argument", "--base")
    assert (configured.label, configured.source) == (
        "environment",
        adr_immutability_check.BASE_ENV,
    )


def test_pull_request_event_sha_precedes_base_ref(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    event = tmp_path / "event.json"
    event.write_text(json.dumps({"pull_request": {"base": {"sha": "b" * 40}}}), encoding="utf-8")
    monkeypatch.setattr(
        adr_immutability_check,
        "_resolve_commit",
        lambda _repo, ref: ref if ref == "b" * 40 else None,
    )
    selection = adr_immutability_check.resolve_base(
        tmp_path,
        environ={"GITHUB_EVENT_PATH": str(event), "GITHUB_BASE_REF": "main"},
    )
    assert selection == adr_immutability_check.BaseSelection("b" * 40, "b" * 40, "pull request")


def test_local_fallback_prefers_origin_main_then_head(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        adr_immutability_check,
        "_resolve_commit",
        lambda _repo, ref: {"origin/main": "m" * 40, "HEAD": "h" * 40}.get(ref),
    )
    selection = adr_immutability_check.resolve_base(Path("."), environ={})
    assert selection.label == "origin/main"

    monkeypatch.setattr(
        adr_immutability_check,
        "_resolve_commit",
        lambda _repo, ref: "h" * 40 if ref == "HEAD" else None,
    )
    selection = adr_immutability_check.resolve_base(Path("."), environ={})
    assert selection.label == "HEAD"


def test_documentation_contract_accepts_adr_0024() -> None:
    assert (ROOT / "docs/adr/0024-preserve-source-specific-data-terms.md").is_file()
    assert docs_contract_check._adr_problems() == []
