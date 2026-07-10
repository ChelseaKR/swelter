"""The project planner is complete, privacy-preserving, and safety-biased."""

from __future__ import annotations

import itertools
import json
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "web" / "planner" / "index.html"
SCRIPT = ROOT / "web" / "planner" / "planner.js"
STYLES = ROOT / "web" / "planner" / "planner.css"


class _PlannerParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.html_lang: str | None = None
        self.h1_count = 0
        self.landmarks: set[str] = set()
        self.ids: set[str] = set()
        self.skip_targets: set[str] = set()
        self.radios: dict[str, list[str]] = {}
        self.unlabelled_radios: list[str] = []
        self.disallowed_inputs: list[str] = []
        self.local_scripts: list[str] = []
        self.local_styles: list[str] = []
        self._label_depth = 0
        self._in_model = False
        self._model_parts: list[str] = []

    @property
    def model(self) -> dict[str, Any]:
        return cast(dict[str, Any], json.loads("".join(self._model_parts)))

    def _handle_input(self, values: dict[str, str]) -> None:
        input_type = values.get("type", "text")
        name = values.get("name", "")
        if input_type == "radio":
            self.radios.setdefault(name, []).append(values.get("value", ""))
            if self._label_depth <= 0:
                self.unlabelled_radios.append(name)
        elif input_type not in {"button", "submit", "reset", "hidden"}:
            self.disallowed_inputs.append(input_type)

    def _handle_resource(self, tag: str, values: dict[str, str]) -> None:
        if tag == "script":
            if values.get("id") == "decision-model":
                self._in_model = True
            if values.get("src"):
                self.local_scripts.append(values["src"])
        elif tag == "link" and values.get("rel") == "stylesheet":
            self.local_styles.append(values.get("href", ""))

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key: value or "" for key, value in attrs}
        if values.get("id"):
            self.ids.add(values["id"])
        if tag == "html":
            self.html_lang = values.get("lang")
        elif tag == "h1":
            self.h1_count += 1
        elif tag in {"header", "main", "nav", "footer"}:
            self.landmarks.add(tag)
        elif tag == "label":
            self._label_depth += 1
        elif tag == "a" and values.get("href", "").startswith("#"):
            self.skip_targets.add(values["href"][1:])
        elif tag == "input":
            self._handle_input(values)
        elif tag in {"script", "link"}:
            self._handle_resource(tag, values)

    def handle_endtag(self, tag: str) -> None:
        if tag == "label":
            self._label_depth -= 1
        elif tag == "script" and self._in_model:
            self._in_model = False

    def handle_data(self, data: str) -> None:
        if self._in_model:
            self._model_parts.append(data)


def _page() -> _PlannerParser:
    parser = _PlannerParser()
    parser.feed(INDEX.read_text(encoding="utf-8"))
    return parser


def _term_matches(term: dict[str, Any], answers: dict[str, str]) -> bool:
    return answers[term["field"]] in term["in"]


def _condition_matches(condition: dict[str, Any], answers: dict[str, str]) -> bool:
    if "all" in condition:
        return all(_term_matches(term, answers) for term in condition["all"])
    return any(_term_matches(term, answers) for term in condition["any"])


def _recommend(model: dict[str, Any], answers: dict[str, str]) -> dict[str, Any]:
    for rule in model["rules"]:
        if "when" not in rule or _condition_matches(rule["when"], answers):
            return cast(dict[str, Any], model["outcomes"][rule["outcome"]])
    raise AssertionError("decision table has no default")


def test_planner_is_accessible_and_collects_no_personal_or_location_fields() -> None:
    page = _page()
    required = set(page.model["required"])

    assert page.html_lang == "en"
    assert page.h1_count == 1
    assert {"header", "main", "nav", "footer"} <= page.landmarks
    assert page.skip_targets & page.ids == {"planner"}
    assert set(page.radios) == required
    assert not page.unlabelled_radios
    assert not page.disallowed_inputs
    assert {"name", "email", "address", "location"}.isdisjoint(page.radios)
    assert page.local_scripts == ["planner.js"]
    assert page.local_styles == ["planner.css"]


def test_every_answer_combination_has_a_complete_recommendation() -> None:
    page = _page()
    model = page.model
    fields = model["required"]
    domains = [page.radios[field] for field in fields]
    expected_parts = {"decision", "title", "why", "next_steps", "proof", "red_lines"}

    assert "when" not in model["rules"][-1]
    for values in itertools.product(*domains):
        outcome = _recommend(model, dict(zip(fields, values, strict=True)))
        assert expected_parts <= set(outcome)
        assert all(outcome[part] for part in expected_parts)


def test_safety_gates_override_sensor_enthusiasm() -> None:
    model = _page().model
    ready = {
        "goal": "intervention",
        "evidence": "calibrated_sensors",
        "timeline": "months",
        "stewardship": "team",
        "governance": "policy_approved",
        "calibration": "reference_ready",
    }

    assert _recommend(model, ready)["decision"] == "OPERATE IN STAGES"
    assert _recommend(model, {**ready, "governance": "not_discussed"})["decision"] == (
        "DO NOT DEPLOY"
    )
    assert _recommend(model, {**ready, "stewardship": "none"})["decision"] == "DO NOT DEPLOY"
    assert _recommend(model, {**ready, "timeline": "days"})["decision"] == (
        "DO NOT DEPLOY FOR THIS DECISION"
    )
    raw = {**ready, "evidence": "raw_sensors", "calibration": "none"}
    assert _recommend(model, raw)["decision"] == "DO NOT EXPAND"


def test_planner_has_no_answer_storage_or_network_submission() -> None:
    script = SCRIPT.read_text(encoding="utf-8")
    css = STYLES.read_text(encoding="utf-8")

    for forbidden in ("localStorage", "sessionStorage", "sendBeacon", "XMLHttpRequest", "fetch("):
        assert forbidden not in script
    assert "prefers-reduced-motion" in css
    assert "forced-colors" in css
    assert "focus-visible" in css
    assert "@media print" in css
