#!/usr/bin/env python3
"""Fail on unstructured production logs or PII/credential-shaped structured fields."""

from __future__ import annotations

import ast
import re
import shutil
import subprocess
from collections.abc import Iterable, Mapping
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCAN_DIRS = ("src", "scripts", "infra")
_LOG_METHODS = frozenset({"debug", "info", "warning", "error", "exception", "critical"})
_FORBIDDEN_NAMES = (
    "ip",
    "addr",
    "email",
    "phone",
    "name",
    "lat",
    "lon",
    "password",
    "token",
    "secret",
    "api_key",
    "ssn",
    "dob",
)
_SENSITIVE_LITERAL = re.compile(
    r"(?:\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b|[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}|"
    r"(?:bearer|password|token|secret|api[_-]?key)[=: ]+\S+)",
    re.IGNORECASE,
)


def _tracked_python() -> list[Path]:
    git = shutil.which("git")
    if git is None:
        raise RuntimeError("log-safety gate requires git on PATH")
    # The executable is resolved to an absolute path and every argument is fixed by this gate;
    # no shell or caller-controlled command data crosses the subprocess boundary.
    result = subprocess.run(  # noqa: S603 (#107)
        [git, "-C", str(ROOT), "ls-files", "-z", "*.py"],
        check=True,
        capture_output=True,
        text=True,
    )
    return [ROOT / name for name in result.stdout.split("\0") if name]


def _call_name(call: ast.Call) -> str:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return ""


def _is_logger_call(call: ast.Call) -> bool:
    # Treat every conventional logging method as a logger boundary. Restricting this to variables
    # literally named ``logger`` lets aliases and member loggers bypass the policy.
    return isinstance(call.func, ast.Attribute) and call.func.attr in _LOG_METHODS


def _forbidden_field(name: str) -> bool:
    lowered = name.lower()
    return name != "node_id" and any(part in lowered for part in _FORBIDDEN_NAMES)


def _literal_problem(node: ast.AST) -> bool:
    return any(
        isinstance(child, ast.Constant)
        and isinstance(child.value, str)
        and bool(_SENSITIVE_LITERAL.search(child.value))
        for child in ast.walk(node)
    )


def _scan_keyword(keyword: ast.keyword, *, is_event: bool, lineno: int) -> list[str]:
    """Return safety findings for one structured logging keyword."""
    problems: list[str] = []
    if keyword.arg is None:
        return [f"line {lineno}: dynamic **fields bypass static log review"]
    if is_event and _forbidden_field(keyword.arg):
        problems.append(f"line {lineno}: forbidden structured field {keyword.arg!r}")
    if _literal_problem(keyword.value):
        problems.append(f"line {lineno}: sensitive literal in field {keyword.arg!r}")
    if keyword.arg == "extra" and isinstance(keyword.value, ast.Dict):
        for key in keyword.value.keys:
            if (
                isinstance(key, ast.Constant)
                and isinstance(key.value, str)
                and _forbidden_field(key.value)
            ):
                problems.append(f"line {lineno}: forbidden extra field {key.value!r}")
    return problems


def _scan_call(node: ast.Call) -> list[str]:
    """Return safety findings for one known logging/event call."""
    problems: list[str] = []
    if _is_logger_call(node) and node.args and not isinstance(node.args[0], ast.Constant):
        problems.append(f"line {node.lineno}: unstructured/interpolated logger message")
    for arg in node.args:
        if _literal_problem(arg):
            problems.append(f"line {node.lineno}: sensitive literal in log message")
    is_event = _call_name(node) == "log_event"
    for keyword in node.keywords:
        problems.extend(_scan_keyword(keyword, is_event=is_event, lineno=node.lineno))
    return problems


def scan_python(path: Path) -> list[str]:
    """Return log-safety problems in one Python file."""
    if path == ROOT / "src" / "swelter" / "obs.py":
        return []  # central scrubber is covered by behavioral tests
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError) as exc:
        return [f"cannot parse: {exc}"]
    problems: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if _call_name(node) != "log_event" and not _is_logger_call(node):
            continue
        problems.extend(_scan_call(node))
    return problems


def scan_targets(paths: Iterable[Path]) -> dict[str, list[Path]]:
    """Group tracked Python files by the production directory this gate covers.

    ``firmware/src`` groups under ``src`` because that is the directory name the existing
    membership test matches. This is a report of the corpus actually scanned, not a new
    selection rule: the same files are scanned as before.
    """
    grouped: dict[str, list[Path]] = {name: [] for name in SCAN_DIRS}
    for path in paths:
        parts = path.relative_to(ROOT).parts
        for name in SCAN_DIRS:
            if name in parts:
                grouped[name].append(path)
                break
    return grouped


def corpus_problems(grouped: Mapping[str, list[Path]]) -> list[str]:
    """Refuse to pass on an empty corpus.

    This gate's PASS line is a universal claim: *production log calls are structured and
    PII-safe*. A universal claim about an empty set is not evidence of anything. The corpus is
    whatever ``git ls-files '*.py'`` returns, filtered by :data:`SCAN_DIRS` -- so renaming
    ``src/``, moving the production packages, or a git invocation that returns nothing all
    shrink it silently, and the gate printed the same sentence either way. Compare
    ``workflow_policy_check`` and ``reading_level_check``, which already refuse the empty set.
    """
    return [
        f"{name}/: no tracked Python file reached the log-safety scan. This gate's PASS line is "
        "a claim about production logging; it must not be made about an empty corpus."
        for name in SCAN_DIRS
        if not grouped.get(name)
    ]


def main() -> int:
    grouped = scan_targets(_tracked_python())
    all_problems: list[str] = corpus_problems(grouped)
    scanned = 0
    for name in SCAN_DIRS:
        for path in grouped[name]:
            scanned += 1
            for problem in scan_python(path):
                all_problems.append(f"{path.relative_to(ROOT)}: {problem}")
    if all_problems:
        print(f"  [FAIL] {len(all_problems)} unsafe logging construct(s)")
        for problem in all_problems:
            print(f"           - {problem}")
        return 1
    covered = ", ".join(f"{name}={len(grouped[name])}" for name in SCAN_DIRS)
    print(f"  [PASS] production log calls are structured and PII-safe ({covered})")
    print(f"log-safety: {scanned} tracked production Python file(s) scanned")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
