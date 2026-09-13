"""An artifact upload retains every path it names, including hidden ones (#266).

`ci.yml`'s `a11y-advisory` job uploaded `web/.lighthouseci` as its performance evidence. That is a
hidden directory, and `actions/upload-artifact` excludes hidden files unless
`include-hidden-files: true` is set, so none of the Lighthouse reports the step named was ever
retained: 0 of 135 unexpired `a11y-evidence-*` artifacts contained one, measured 2026-09-13.
`if-no-files-found: warn` could not notice, because the step's other two paths always matched.

A retention step that keeps a subset of what it names reads, in the workflow file, exactly like one
that keeps everything. So the rule is checked for every upload step in every workflow, not only the
one that was caught.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = ROOT / ".github" / "workflows"
UPLOAD_ACTION = "actions/upload-artifact"


def _upload_steps() -> list[tuple[str, str, dict[str, Any]]]:
    steps: list[tuple[str, str, dict[str, Any]]] = []
    paths = sorted([*WORKFLOWS.glob("*.yml"), *WORKFLOWS.glob("*.yaml")])
    assert paths, "no workflows found: a rule checked over nothing proves nothing"
    for path in paths:
        document: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
        jobs = document.get("jobs") if isinstance(document, dict) else None
        for job_id, job in (jobs or {}).items():
            for step in (job or {}).get("steps") or []:
                uses = step.get("uses")
                if isinstance(uses, str) and uses.split("@", 1)[0] == UPLOAD_ACTION:
                    inputs = step.get("with") or {}
                    steps.append((path.name, str(step.get("name", job_id)), inputs))
    return steps


def _hidden_paths(inputs: dict[str, Any]) -> list[str]:
    """Upload patterns with a dot-named component. Exclusions (`!…`) need no hidden-file opt-in."""
    lines = [line.strip() for line in str(inputs.get("path", "")).splitlines()]
    return [
        line
        for line in lines
        if line
        and not line.startswith("!")
        and any(part.startswith(".") and part not in {".", ".."} for part in Path(line).parts)
    ]


def test_an_upload_that_names_a_hidden_path_includes_hidden_files() -> None:
    offenders = [
        f"{workflow}: step {name!r} names {hidden} without include-hidden-files: true"
        for workflow, name, inputs in _upload_steps()
        if (hidden := _hidden_paths(inputs)) and inputs.get("include-hidden-files") is not True
    ]
    assert offenders == []


def test_the_rule_is_exercised_by_the_step_that_was_caught() -> None:
    """Guard against the rule passing over an empty set, e.g. if upload steps stop being found."""
    exercised = [
        (workflow, name) for workflow, name, inputs in _upload_steps() if _hidden_paths(inputs)
    ]
    assert ("ci.yml", "Retain browser accessibility and performance evidence") in exercised


def test_hidden_path_detection() -> None:
    assert _hidden_paths({"path": "web/test-results\nweb/.lighthouseci\n"}) == ["web/.lighthouseci"]
    assert _hidden_paths({"path": "dist/dora"}) == []
    assert _hidden_paths({"path": "./dist\n!web/.cache"}) == []
