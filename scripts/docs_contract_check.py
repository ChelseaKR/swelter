#!/usr/bin/env python3
"""Mechanical documentation contract: required set, ADR shape, live links, and currency stamps."""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import unquote

import yaml

ROOT = Path(__file__).resolve().parent.parent

REQUIRED_FILES = (
    "README.md",
    "CHANGELOG.md",
    "CITATION.cff",
    "SECURITY.md",
    "CONTRIBUTING.md",
    "DEFINITION_OF_DONE.md",
    "docs/ROADMAP.md",
    "docs/RESPONSIBLE-TECH-AUDITS.md",
    "docs/ARCHITECTURE.md",
    "docs/DORA.md",
    "docs/ACCEPTANCE-TEST-MAP.md",
    "docs/STANDARDS-PIN.md",
    "docs/runbooks/operations.md",
    "docs/adr/0000-record-architecture-decisions.md",
    "docs/adr/template.md",
)

CURRENCY_DOCS = (
    "SECURITY.md",
    "CONTRIBUTING.md",
    "docs/ROADMAP.md",
    "docs/RESPONSIBLE-TECH-AUDITS.md",
    "docs/ARCHITECTURE.md",
    "docs/I18N.md",
    "docs/DORA.md",
    "docs/ACCEPTANCE-TEST-MAP.md",
    "docs/STANDARDS-PIN.md",
    "docs/audits/accessibility-report.md",
    "docs/audits/privacy-dpia.md",
    "docs/audits/methodology.md",
    "docs/audits/fairness-review.md",
    "docs/audits/ethics-consequence-scan.md",
    "docs/audits/threat-model.md",
    "docs/audits/residual-risk-register.md",
    "docs/audits/data-flow.md",
)

_LINK = re.compile(r"(?<!!)\[[^\]]+\]\((<[^>]+>|[^)\s]+)(?:\s+['\"][^'\"]+['\"])?\)")
_ADR_NAME = re.compile(r"^(\d{4})-[a-z0-9]+(?:-[a-z0-9]+)*\.md$")
_STATUS = re.compile(
    r"\*\*Status:\*\*\s+(Spec|Scaffolded|In build \(M\d+\)|Beta|Production|Maintained|Archived)\b"
)


def _markdown_files() -> list[Path]:
    roots = [ROOT / name for name in ("README.md", "CONTRIBUTING.md", "SECURITY.md")]
    roots.extend((ROOT / "docs").rglob("*.md"))
    standards = (ROOT / "docs" / "standards").resolve()
    return sorted(
        path for path in roots if path.is_file() and standards not in path.resolve().parents
    )


def _link_problems(path: Path) -> list[str]:
    problems: list[str] = []
    text = path.read_text(encoding="utf-8")
    for raw in _LINK.findall(text):
        target = raw[1:-1] if raw.startswith("<") and raw.endswith(">") else raw
        if target.startswith(("https://", "http://", "mailto:", "#")):
            continue
        relative = unquote(target.split("#", 1)[0].split("?", 1)[0])
        if not relative:
            continue
        resolved = (path.parent / relative).resolve()
        try:
            resolved.relative_to(ROOT.resolve())
        except ValueError:
            problems.append(f"{path.relative_to(ROOT)}: link escapes repository: {target}")
            continue
        if not resolved.exists():
            problems.append(f"{path.relative_to(ROOT)}: missing link target: {target}")
    return problems


def _adr_problems() -> list[str]:
    problems: list[str] = []
    adr_dir = ROOT / "docs" / "adr"
    numbered = [path for path in adr_dir.glob("*.md") if _ADR_NAME.fullmatch(path.name)]
    numbers = sorted(int(path.name[:4]) for path in numbered)
    if numbers != list(range(0, max(numbers, default=-1) + 1)):
        problems.append(f"docs/adr: numbering is not contiguous: {numbers}")
    required_headings = ("## Context", "## Decision", "## Consequences")
    metadata = {
        "Status": re.compile(r"^- (?:\*\*)?Status:(?:\*\*)?\s+\S", re.MULTILINE),
        "Date": re.compile(r"^- (?:\*\*)?Date:(?:\*\*)?\s+\S", re.MULTILINE),
        "Deciders": re.compile(r"^- (?:\*\*)?Deciders:(?:\*\*)?\s+\S", re.MULTILINE),
    }
    allowed_status = re.compile(
        r"^- (?:\*\*)?Status:(?:\*\*)? "
        r"(Proposed|Accepted|Deprecated|Superseded by \d{4})$",
        re.MULTILINE,
    )
    for path in numbered:
        text = path.read_text(encoding="utf-8")
        missing = [field for field, pattern in metadata.items() if not pattern.search(text)]
        missing.extend(heading for heading in required_headings if heading not in text)
        if missing:
            problems.append(f"{path.relative_to(ROOT)}: missing {', '.join(missing)}")
        if not allowed_status.search(text):
            problems.append(f"{path.relative_to(ROOT)}: invalid ADR status")
    return problems


def _currency_problems() -> list[str]:
    problems: list[str] = []
    for name in CURRENCY_DOCS:
        path = ROOT / name
        if not path.is_file():
            problems.append(f"{name}: required current artifact is missing")
            continue
        text = path.read_text(encoding="utf-8")
        if not re.search(r"(?:Last verified:|Evidence date:)\s*20\d{2}-\d{2}-\d{2}", text):
            problems.append(f"{name}: no dated Last verified/Evidence date stamp")
        if "Recheck cadence:" not in text:
            problems.append(f"{name}: no Recheck cadence")
    return problems


def _citation_problems() -> list[str]:
    problems: list[str] = []
    try:
        citation = yaml.safe_load((ROOT / "CITATION.cff").read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        problems.append(f"CITATION.cff: invalid YAML ({exc})")
        citation = {}
    if not isinstance(citation, dict):
        return ["CITATION.cff: top level must be a mapping"]
    for key in ("cff-version", "title", "authors", "version", "license"):
        if not citation.get(key):
            problems.append(f"CITATION.cff: missing {key}")
    if os.environ.get("GITHUB_REF_TYPE") == "tag" and not citation.get("date-released"):
        problems.append("CITATION.cff: tagged release has no date-released")
    return problems


def _zenodo_problems() -> list[str]:
    try:
        zenodo = json.loads((ROOT / ".zenodo.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f".zenodo.json: invalid or missing ({exc})"]
    description = str(zenodo.get("description", "")) if isinstance(zenodo, dict) else ""
    if "source-specific" not in description or "CC0" not in description:
        return [".zenodo.json: data licensing is not source-specific"]
    return []


def _root_contract_problems() -> list[str]:
    problems = [
        f"{name}: required file is missing"
        for name in REQUIRED_FILES
        if not (ROOT / name).is_file()
    ]
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    if not _STATUS.search(readme):
        problems.append("README.md: missing an allowed explicit Status")
    contributing = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    lower_contributing = contributing.lower()
    required_contributing = {
        "make verify": "make verify",
        "Standards Conformance": "standards conformance",
        "DCO/sign-off rule": "developer certificate of origin",
        "signed-off commit command": "git commit -s",
    }
    for label, required in required_contributing.items():
        if required not in lower_contributing:
            problems.append(f"CONTRIBUTING.md: missing {label!r}")
    problems.extend(_citation_problems())
    problems.extend(_zenodo_problems())
    return problems


def main() -> int:
    problems = _root_contract_problems() + _adr_problems() + _currency_problems()
    for path in _markdown_files():
        problems.extend(_link_problems(path))
    for path in (
        ROOT / "src" / "swelter" / "ac_access_layer.py",
        ROOT / "src" / "swelter" / "redlining_layer.py",
        *sorted((ROOT / "data").glob("*.geojson")),
        ROOT / "web" / "cooling-centers.geojson",
    ):
        if path.is_file() and "docs/decisions/" in path.read_text(encoding="utf-8"):
            problems.append(f"{path.relative_to(ROOT)}: live provenance points at legacy ADR log")

    if problems:
        print(f"docs-contract: FAIL ({len(problems)} problem(s))", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    print("docs-contract: PASS (required set, ADRs, currency, links, citation, provenance)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
