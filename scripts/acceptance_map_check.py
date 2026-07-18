#!/usr/bin/env python3
"""Validate the executable roadmap-to-acceptance-test contract."""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAP_PATH = ROOT / "docs" / "ACCEPTANCE-TEST-MAP.md"
ROADMAP_PATH = ROOT / "docs" / "ROADMAP.md"

MAP_HEADERS = (
    "Feature ID",
    "Feature / roadmap outcome",
    "Measurable acceptance criterion",
    "Automated evidence",
    "Review evidence",
    "ISO/IEC 25010:2023 characteristic(s)",
)
ROADMAP_HEADERS = ("Feature ID", "Shipped roadmap outcome")
ISO_25010_2023 = frozenset(
    {
        "Functional Suitability",
        "Performance Efficiency",
        "Compatibility",
        "Interaction Capability",
        "Reliability",
        "Security",
        "Maintainability",
        "Flexibility",
        "Safety",
    }
)

_FEATURE_ID = re.compile(r"^F-\d{2}$")
_CODE_ANCHOR = re.compile(r"`([^`]+)`")
_PYTHON_TEST = re.compile(r"^(?:tests|firmware/tests)/.+\.py$")
_JAVASCRIPT_TEST = re.compile(r"^web/tests/.+\.js$")


def _cells(line: str) -> list[str] | None:
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return None
    return [cell.strip() for cell in stripped[1:-1].split("|")]


def _table_after_heading(text: str, heading: str) -> tuple[list[str], list[list[str]]]:
    marker = f"## {heading}"
    if marker not in text:
        raise ValueError(f"missing {marker!r}")
    section = text.split(marker, 1)[1].split("\n## ", 1)[0]
    lines = section.splitlines()
    for index, line in enumerate(lines):
        headers = _cells(line)
        if headers is None:
            continue
        if index + 1 >= len(lines):
            break
        divider = _cells(lines[index + 1])
        if divider is None or len(divider) != len(headers):
            continue
        if not all(re.fullmatch(r":?-{3,}:?", cell) for cell in divider):
            continue
        rows: list[list[str]] = []
        for candidate in lines[index + 2 :]:
            cells = _cells(candidate)
            if cells is None:
                if rows:
                    break
                continue
            rows.append(cells)
        return headers, rows
    raise ValueError(f"{marker}: no Markdown table")


def _python_symbols(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _javascript_has_test(path: Path, symbol: str) -> bool:
    source = path.read_text(encoding="utf-8")
    escaped = re.escape(symbol)
    return bool(re.search(rf"\b(?:test|it)\(\s*(['\"]){escaped}\1\s*,", source))


def _anchor_path(root: Path, feature_id: str, relative: str) -> tuple[Path | None, str | None]:
    if not relative or relative.startswith(("/", "../")):
        return None, f"{feature_id}: unsafe evidence path {relative!r}"
    path = (root / relative).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError:
        return None, f"{feature_id}: evidence path escapes repository: {relative}"
    if not path.is_file():
        return None, f"{feature_id}: evidence path does not exist: {relative}"
    return path, None


def _test_anchor_problem(
    feature_id: str, anchor: str, relative: str, symbol: str, path: Path
) -> str | None:
    if _PYTHON_TEST.fullmatch(relative):
        if not symbol:
            return f"{feature_id}: Python test anchor needs ::test_symbol: {anchor}"
        if symbol not in _python_symbols(path):
            return f"{feature_id}: missing Python test symbol: {anchor}"
    elif _JAVASCRIPT_TEST.fullmatch(relative):
        if not symbol:
            return f"{feature_id}: JavaScript test anchor needs ::test title: {anchor}"
        if not _javascript_has_test(path, symbol):
            return f"{feature_id}: missing JavaScript test title: {anchor}"
    elif symbol:
        return f"{feature_id}: symbols are only valid on test files: {anchor}"
    return None


def _anchor_problem(root: Path, feature_id: str, anchor: str) -> str | None:
    relative, _, symbol = anchor.partition("::")
    path, path_problem = _anchor_path(root, feature_id, relative)
    if path_problem or path is None:
        return path_problem
    return _test_anchor_problem(feature_id, anchor, relative, symbol, path)


def _anchor_problems(root: Path, feature_id: str, evidence: str) -> list[str]:
    anchors = _CODE_ANCHOR.findall(evidence)
    if not anchors:
        return [f"{feature_id}: automated evidence has no code anchor"]
    return [problem for anchor in anchors if (problem := _anchor_problem(root, feature_id, anchor))]


def _row_content_problems(feature_id: str, number: int, row: list[str]) -> list[str]:
    _, outcome, criterion, evidence, review, characteristics = row
    label = feature_id or f"row {number}"
    problems = [
        f"{label}: empty {field}"
        for field, value in (
            ("outcome", outcome),
            ("criterion", criterion),
            ("automated evidence", evidence),
            ("review evidence", review),
        )
        if not value
    ]
    vocabulary = [item.strip() for item in characteristics.split(";") if item.strip()]
    if not vocabulary:
        problems.append(f"{label}: no ISO 25010:2023 characteristic")
    invalid = sorted(set(vocabulary) - ISO_25010_2023)
    if invalid:
        problems.append(f"{label}: invalid ISO 25010:2023 vocabulary: {', '.join(invalid)}")
    if len(vocabulary) != len(set(vocabulary)):
        problems.append(f"{label}: duplicate ISO characteristic")
    return problems


def _map_features(root: Path, rows: list[list[str]]) -> tuple[dict[str, str], list[str]]:
    features: dict[str, str] = {}
    problems: list[str] = []
    for number, row in enumerate(rows, start=1):
        if len(row) != len(MAP_HEADERS):
            problems.append(
                f"acceptance map row {number}: expected {len(MAP_HEADERS)} cells, got {len(row)}"
            )
            continue
        feature_id, outcome, _, evidence, _, _ = row
        if not _FEATURE_ID.fullmatch(feature_id):
            problems.append(f"acceptance map row {number}: invalid feature ID {feature_id!r}")
        elif feature_id in features:
            problems.append(f"acceptance map row {number}: duplicate feature ID {feature_id}")
        else:
            features[feature_id] = outcome
        problems.extend(_row_content_problems(feature_id, number, row))
        problems.extend(_anchor_problems(root, feature_id or f"row {number}", evidence))
    return features, problems


def _roadmap_features(rows: list[list[str]]) -> tuple[dict[str, str], list[str]]:
    features: dict[str, str] = {}
    problems: list[str] = []
    for number, row in enumerate(rows, start=1):
        if len(row) != len(ROADMAP_HEADERS):
            problems.append(f"roadmap row {number}: expected 2 cells, got {len(row)}")
            continue
        feature_id, outcome = row
        if not _FEATURE_ID.fullmatch(feature_id):
            problems.append(f"roadmap row {number}: invalid feature ID {feature_id!r}")
        elif feature_id in features:
            problems.append(f"roadmap row {number}: duplicate feature ID {feature_id}")
        else:
            features[feature_id] = outcome
    return features, problems


def _coverage_problems(features: dict[str, str], roadmap: dict[str, str]) -> list[str]:
    problems: list[str] = []
    missing = sorted(set(roadmap) - set(features))
    extra = sorted(set(features) - set(roadmap))
    if missing:
        problems.append(f"roadmap features missing acceptance rows: {', '.join(missing)}")
    if extra:
        problems.append(f"acceptance rows absent from shipped roadmap: {', '.join(extra)}")
    problems.extend(
        f"{feature_id}: outcome differs between roadmap and acceptance map "
        f"({roadmap[feature_id]!r} != {features[feature_id]!r})"
        for feature_id in sorted(set(features) & set(roadmap))
        if features[feature_id] != roadmap[feature_id]
    )
    return problems


def check(root: Path = ROOT) -> list[str]:
    """Return every acceptance-map contract violation under *root*."""
    try:
        headers, rows = _table_after_heading(
            (root / "docs" / "ACCEPTANCE-TEST-MAP.md").read_text(encoding="utf-8"),
            "Executable feature map",
        )
    except (OSError, ValueError) as exc:
        return [f"acceptance map: {exc}"]
    if tuple(headers) != MAP_HEADERS:
        return [f"acceptance map: headers must be {MAP_HEADERS!r}, got {tuple(headers)!r}"]
    features, problems = _map_features(root, rows)

    try:
        roadmap_headers, roadmap_rows = _table_after_heading(
            (root / "docs" / "ROADMAP.md").read_text(encoding="utf-8"),
            "Shipped feature inventory",
        )
    except (OSError, ValueError) as exc:
        problems.append(f"roadmap: {exc}")
        return problems
    if tuple(roadmap_headers) != ROADMAP_HEADERS:
        problems.append(
            f"roadmap inventory: headers must be {ROADMAP_HEADERS!r}, "
            f"got {tuple(roadmap_headers)!r}"
        )
        return problems

    roadmap_features, roadmap_problems = _roadmap_features(roadmap_rows)
    problems.extend(roadmap_problems)
    problems.extend(_coverage_problems(features, roadmap_features))
    return problems


def main() -> int:
    problems = check()
    if problems:
        print(f"acceptance-map: FAIL ({len(problems)} problem(s))", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    _, rows = _table_after_heading(MAP_PATH.read_text(encoding="utf-8"), "Executable feature map")
    print(
        "acceptance-map: PASS "
        f"({len(rows)} shipped features; paths, symbols, roadmap, ISO 25010:2023 verified)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
