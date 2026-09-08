"""Portfolio Standards Conformance ledger parser/gate."""

from __future__ import annotations

import http.client
import importlib
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

import pytest
import yaml

if TYPE_CHECKING:
    from scripts import conformance_check
else:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    conformance_check = importlib.import_module("scripts.conformance_check")


def _table(rows: str) -> str:
    return f"""# Project

## Standards Conformance

| Standard | State |
|---|---|
{rows}

## Next
"""


def test_repository_conformance_ledger_has_every_standard_once() -> None:
    rows, errors = conformance_check.parse_ledger(
        conformance_check.README.read_text(encoding="utf-8")
    )
    assert errors == []
    assert conformance_check.validate_ledger(rows) == []


def test_blocking_machine_evidence_cannot_hide_behind_applies(tmp_path: Path) -> None:
    audits = tmp_path / "docs" / "audits"
    audits.mkdir(parents=True)
    (audits / "quality-metrics-gap.json").write_text(
        json.dumps({"release_blocking": True, "tracking_issue": 211}), encoding="utf-8"
    )
    (audits / "release-publishing-gap.json").write_text(
        json.dumps({"release_blocking": True, "tracking_issue": 212}), encoding="utf-8"
    )
    (audits / "release-review-attestations.json").write_text(
        json.dumps(
            {
                "tracking_issue": 213,
                "attestations": [{"id": "ethics", "outcome": "pending"}],
            }
        ),
        encoding="utf-8",
    )
    rows = [
        conformance_check.LedgerRow("Quality & Metrics", "Applies", None),
        conformance_check.LedgerRow("Release & Versioning", "Applies", None),
        conformance_check.LedgerRow("Responsible-Tech Framework", "Applies", None),
    ]
    problems = conformance_check.semantic_evidence_problems(rows, tmp_path)
    assert "Quality & Metrics: ledger gap does not match machine-evidence issue #211" in problems
    assert "Release & Versioning: ledger gap does not match machine-evidence issue #212" in problems
    assert (
        "Responsible-Tech Framework: ledger gap does not match machine-evidence issue #213"
        in problems
    )


def test_parser_accepts_only_the_three_canonical_state_shapes() -> None:
    rows, errors = conformance_check.parse_ledger(
        _table(
            "| Code Quality | Applies |\n"
            "| CI/CD | Applies — gap tracked in "
            "[#105](https://github.com/ChelseaKR/swelter/issues/105) |\n"
            "| AI Evaluation | N/A — no model surface |"
        )
    )
    assert errors == []
    assert [row.issue for row in rows] == [None, 105, None]


def test_parser_rejects_fourth_state_and_mismatched_issue_link() -> None:
    _, errors = conformance_check.parse_ledger(
        _table(
            "| Code Quality | Partial |\n"
            "| CI/CD | Applies — gap tracked in "
            "[#105](https://github.com/ChelseaKR/swelter/issues/106) |\n"
            "| AI Evaluation | N/A |"
        )
    )
    assert len(errors) == 3
    assert any("noncanonical" in error for error in errors)
    assert any("do not match" in error for error in errors)


class _StubResponse:
    """Enough of :class:`http.client.HTTPResponse` for the issue lookup."""

    def __init__(self, status: int, body: str = "", headers: dict[str, str] | None = None) -> None:
        self.status = status
        self._body = body.encode("utf-8")
        self._headers = headers or {}

    def read(self) -> bytes:
        return self._body

    def getheader(self, name: str, default: str | None = None) -> str | None:
        return self._headers.get(name.lower(), default)


class _StubConnection:
    """Records the headers the gate sends and replays one canned response."""

    sent_headers: ClassVar[dict[str, str]] = {}

    def __init__(self, response: _StubResponse) -> None:
        self._response = response

    def request(self, method: str, url: str, headers: dict[str, str] | None = None) -> None:
        type(self).sent_headers = dict(headers or {})

    def getresponse(self) -> _StubResponse:
        return self._response

    def close(self) -> None:
        return None


def _with_response(
    monkeypatch: pytest.MonkeyPatch, response: _StubResponse
) -> type[_StubConnection]:
    _StubConnection.sent_headers = {}

    def _factory(*_args: Any, **_kwargs: Any) -> _StubConnection:
        return _StubConnection(response)

    monkeypatch.setattr(http.client, "HTTPSConnection", _factory)
    return _StubConnection


def test_an_api_refusal_is_reported_as_a_check_that_did_not_happen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A 403 must not arrive in the same words as "this gap issue is closed".

    This is the defect the authenticated request exists to stop recurring: unauthenticated
    api.github.com is capped at 60/hour per runner IP pool, so this gate failed on other
    repositories' traffic and told the reader the repository's declared posture was stale when in
    fact nothing had been checked.
    """
    _with_response(monkeypatch, _StubResponse(403, headers={"x-ratelimit-remaining": "0"}))
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    with pytest.raises(conformance_check.IssueUnreadable) as caught:
        conformance_check._issue_is_open(238)

    message = str(caught.value)
    assert "could not check gap issue #238" in message
    assert "HTTP 403" in message
    assert "rate limit is exhausted" in message
    assert "this is not a finding that it is closed" in message
    # The wording the gate uses for a *measured* stale gap must not appear here.
    assert "does not resolve to an open issue" not in message


def test_a_transport_failure_is_also_unreadable_not_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A refused connection carries no status code and must take the same honest path."""

    def _factory(*_args: Any, **_kwargs: Any) -> _StubConnection:
        raise OSError("[Errno 111] Connection refused")

    monkeypatch.setattr(http.client, "HTTPSConnection", _factory)
    with pytest.raises(conformance_check.IssueUnreadable) as caught:
        conformance_check._issue_is_open(105)
    assert "could not check gap issue #105" in str(caught.value)


def test_a_closed_issue_is_still_a_finding(monkeypatch: pytest.MonkeyPatch) -> None:
    """The other half: when GitHub *does* answer, a closed gap is a real, reportable stale claim.

    Without this the previous test is satisfied by a gate that never reports anything at all.
    """
    _with_response(monkeypatch, _StubResponse(200, json.dumps({"state": "closed"})))
    assert conformance_check._issue_is_open(105) is False
    _with_response(monkeypatch, _StubResponse(200, json.dumps({"state": "open"})))
    assert conformance_check._issue_is_open(105) is True


def test_a_pull_request_number_does_not_count_as_an_open_gap_issue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _with_response(
        monkeypatch,
        _StubResponse(200, json.dumps({"state": "open", "pull_request": {"url": "..."}})),
    )
    assert conformance_check._issue_is_open(261) is False


def test_the_lookup_authenticates_when_a_token_is_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The whole point of the fix: the request must actually carry the token."""
    stub = _with_response(monkeypatch, _StubResponse(200, json.dumps({"state": "open"})))
    monkeypatch.setenv("GITHUB_TOKEN", "ghs-not-a-real-token")
    conformance_check._issue_is_open(105)
    assert stub.sent_headers["Authorization"] == "Bearer ghs-not-a-real-token"


def test_the_lookup_sends_no_empty_authorization_header_without_a_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`Authorization: Bearer ` is a malformed credential, and GitHub answers 401 to it.

    Absent means absent: an unauthenticated request is rate-limited but valid, and that is the
    honest degraded state. Sending an empty bearer would turn a 60/hour cap into an outright
    refusal on every run.
    """
    stub = _with_response(monkeypatch, _StubResponse(200, json.dumps({"state": "open"})))
    monkeypatch.setenv("GITHUB_TOKEN", "   ")
    conformance_check._issue_is_open(105)
    assert "Authorization" not in stub.sent_headers


def test_the_ci_job_grants_the_scope_and_the_token_the_issue_check_needs() -> None:
    """The script half is useless without the workflow half, and nothing else would notice.

    `make conformance` runs inside `make verify-core`; a job-level `permissions:` block replaces
    the workflow-level one, so `contents: read` has to be restated alongside `issues: read`. This
    reads the parsed workflow rather than grepping it: `grep` on this machine is ugrep, which
    treats `${{ }}` as an interval quantifier and reports a missing guard on a file that has one.
    """
    workflow = yaml.safe_load(
        (Path(conformance_check.ROOT) / ".github" / "workflows" / "ci.yml").read_text(
            encoding="utf-8"
        )
    )
    checks = workflow["jobs"]["checks"]
    assert checks["permissions"] == {"contents": "read", "issues": "read"}
    steps = [step for step in checks["steps"] if step.get("run") == "make verify-core"]
    assert len(steps) == 1, "the gate step moved; this assertion is no longer about anything"
    expression = steps[0]["env"]["GITHUB_TOKEN"]
    assert "secrets.GITHUB_TOKEN" in expression, expression
    assert expression.startswith("${{"), expression
