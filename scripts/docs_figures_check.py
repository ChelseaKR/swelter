#!/usr/bin/env python3
"""Docs-figures gate: CI re-proves the countable claims prose makes about the codebase.

Prose drifts: a test count, a registry size, a route table, a key-parity claim, or a
duplicated paragraph can all go stale the moment the thing they describe changes and nobody
remembers to update the sentence. This script holds a *tiny*, high-signal manifest of such
claims, each paired with the command or file that is its source of truth, and fails when the
prose and the source disagree.

Two of the five rules below check ``CLAUDE.md`` / ``README.md`` — files this repo's tooling
treats as agent-do-not-modify. Those rules are *advisory*: they print ``WARN`` and a TODO for
a human maintainer, but never flip the process exit code, because a merge-blocking check that
this script (or the agent driving it) has no way to fix would just turn CI permanently red.
The other three rules check docs this script's caller *can* fix (``docs/ROADMAP.md``,
``docs/api.md``, ``docs/I18N.md``) and are hard gates — see ``BLOCKING`` on each ``Rule``.

Exit status is 0 when every hard-gated rule passes (advisory rules never affect it) and 1
otherwise, with a per-rule report naming its source of truth.
"""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

import yaml

ROOT = Path(__file__).resolve().parent.parent
CLAUDE_MD = ROOT / "CLAUDE.md"
README_MD = ROOT / "README.md"
ROADMAP_MD = ROOT / "docs" / "ROADMAP.md"
API_MD = ROOT / "docs" / "api.md"
I18N_MD = ROOT / "docs" / "I18N.md"
CORRECTIONS_YAML = ROOT / "data" / "demo" / "corrections.yaml"
SERVER_PY = ROOT / "src" / "swelter" / "server.py"
API_PY = ROOT / "src" / "swelter" / "api.py"
I18N_DIR = ROOT / "web" / "i18n"

#: Node count that generated the *committed* data/demo fixtures. `SWELTER_DEMO_NODES`
#: legitimately floats this figure for a freshly regenerated dataset (`make gen-demo`), but
#: the checked-in `corrections.yaml` this rule reads is a fixed, versioned artifact — it does
#: not change just because a developer's shell has the env var set. That is exactly why
#: docs/ROADMAP.md's claim self-qualifies as "at the default size": it describes the
#: committed file, not a live-regenerated one, so comparing against it is not a floating check.
DEFAULT_DEMO_NODES = 150


@dataclass
class RuleResult:
    name: str
    source_of_truth: str
    ok: bool
    detail: str
    blocking: bool  # False = advisory (known-stale prose in an agent-do-not-modify file)


def _load_sibling_module(name: str) -> ModuleType:
    """Load another scripts/*.py module by file path, regardless of how *this* file was run."""
    path = Path(__file__).resolve().with_name(f"{name}.py")
    spec = importlib.util.spec_from_file_location(f"_docs_figures_{name}", path)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise ImportError(f"could not load sibling module {name} from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # required for the sibling's own dataclasses/typing to resolve
    spec.loader.exec_module(module)
    return module


# --- Rule 1: test count (CLAUDE.md vs. `pytest --collect-only`) -----------------------------

_CLAUDE_TEST_COUNT_RE = re.compile(r"\((\d+)\s+tests,\s*all green\)")


def extract_claude_test_count(text: str) -> int | None:
    """Extract the N in CLAUDE.md's `test → pytest (N tests, all green)` line."""
    match = _CLAUDE_TEST_COUNT_RE.search(text)
    return int(match.group(1)) if match else None


def collected_test_count(root: Path) -> int:
    """The actual number of tests pytest would collect — the source of truth for rule 1."""
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    total = 0
    matched_any = False
    for line in proc.stdout.splitlines():
        m = re.match(r"^tests/\S+\.py:\s*(\d+)$", line)
        if m:
            matched_any = True
            total += int(m.group(1))
    if matched_any:
        return total
    # Fallback for pytest versions that print a trailing "N tests collected in Xs" summary
    # instead of the per-file tally above.
    m = re.search(r"(\d+) tests? collected", proc.stdout)
    if m:
        return int(m.group(1))
    raise RuntimeError(f"could not parse test count from pytest --collect-only -q:\n{proc.stdout}")


def check_test_count(claude_text: str, actual_count: int) -> RuleResult:
    claimed = extract_claude_test_count(claude_text)
    source = "`pytest --collect-only -q` (actual collected test count)"
    if claimed is None:
        return RuleResult(
            "test-count",
            source,
            False,
            "CLAUDE.md: could not find a '(N tests, all green)' line",
            blocking=False,
        )
    ok = claimed == actual_count
    detail = f"CLAUDE.md claims {claimed} tests; {source.split(' (')[0]} finds {actual_count}"
    if not ok:
        detail += " — TODO(maintainer): reconcile CLAUDE.md's test count (agent-do-not-modify)"
    return RuleResult("test-count", source, ok, detail, blocking=False)


# --- Rule 2: correction registry count (docs/ROADMAP.md vs. data/demo/corrections.yaml) -----

_ROADMAP_CORRECTIONS_RE = re.compile(r"(\d+) corrections across the (\d+) co-located nodes")


def extract_roadmap_correction_count(text: str) -> int | None:
    """Extract the N in ROADMAP.md's '— N corrections across the M co-located nodes' claim."""
    match = _ROADMAP_CORRECTIONS_RE.search(text)
    return int(match.group(1)) if match else None


def load_corrections_count(path: Path) -> int:
    """Entry count in the committed correction registry — the source of truth for rule 2."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    corrections = data.get("corrections", []) if isinstance(data, dict) else []
    return len(corrections)


def check_corrections_count(roadmap_text: str, actual_count: int) -> RuleResult:
    claimed = extract_roadmap_correction_count(roadmap_text)
    source = (
        f"`data/demo/corrections.yaml` entry count "
        f"(committed file, {DEFAULT_DEMO_NODES}-node default)"
    )
    if claimed is None:
        return RuleResult(
            "registry-count",
            source,
            False,
            "docs/ROADMAP.md: could not find a 'N corrections across the M co-located nodes' claim",
            blocking=True,
        )
    ok = claimed == actual_count
    detail = f"docs/ROADMAP.md claims {claimed} corrections; corrections.yaml has {actual_count}"
    return RuleResult("registry-count", source, ok, detail, blocking=True)


# --- Rule 3: /api route list (docs/api.md vs. src/swelter/server.py registrations) ----------

_TABLE_ROW_RE = re.compile(r"^\|\s*(.+?)\s*\|.*\|\s*$", re.MULTILINE)
_BACKTICK_RE = re.compile(r"`([^`]+)`")
_SENSORTHINGS_VERSION_RE = re.compile(r'SENSORTHINGS_VERSION\s*=\s*"([^"]+)"')
_ROUTE_TUPLE_RE = re.compile(r"path in \(([^)]*)\)")
_ROUTE_LITERAL_RE = re.compile(r'path == "([^"]+)"')
_ROUTE_V_BASE_RE = re.compile(r"path == v:")
_ROUTE_V_SUFFIX_RE = re.compile(r'path == f"\{v\}(/[A-Za-z]+)"')
_QUOTED_RE = re.compile(r'"([^"]+)"')


def extract_api_md_routes(text: str) -> set[str]:
    """Parse the '## Endpoints at a glance' table's Path column into a set of route paths."""
    if "## Endpoints at a glance" not in text:
        return set()
    section = text.split("## Endpoints at a glance", 1)[1].split("\n## ", 1)[0]
    routes: set[str] = set()
    for row in _TABLE_ROW_RE.findall(section):
        if row.startswith("---"):
            continue
        first_cell = row.split("|", 1)[0]
        for backticked in _BACKTICK_RE.findall(first_cell):
            path = backticked.split("?", 1)[0]  # strip query strings, e.g. ?hours=N
            if path.startswith("/"):
                routes.add(path.rstrip("/") or "/")
    return routes


def extract_server_routes(server_source: str, api_source: str) -> set[str]:
    """Parse do_GET's route dispatch in server.py into the same shape as extract_api_md_routes."""
    version_match = _SENSORTHINGS_VERSION_RE.search(api_source)
    if version_match is None:
        raise RuntimeError("could not find SENSORTHINGS_VERSION in src/swelter/api.py")
    v = f"/v{version_match.group(1)}"

    routes: set[str] = set()
    for tuple_body in _ROUTE_TUPLE_RE.findall(server_source):
        routes.update(_QUOTED_RE.findall(tuple_body))
    routes.update(_ROUTE_LITERAL_RE.findall(server_source))
    if _ROUTE_V_BASE_RE.search(server_source):
        routes.add(v)
    for suffix in _ROUTE_V_SUFFIX_RE.findall(server_source):
        routes.add(f"{v}{suffix}")
    return routes


def check_routes(api_md_text: str, server_source: str, api_source: str) -> RuleResult:
    source = "src/swelter/server.py's do_GET dispatch (registered routes)"
    documented = extract_api_md_routes(api_md_text)
    registered = extract_server_routes(server_source, api_source)
    missing_from_docs = sorted(registered - documented)
    missing_from_server = sorted(documented - registered)
    ok = not missing_from_docs and not missing_from_server
    parts = [f"docs/api.md documents {len(documented)} routes, server registers {len(registered)}"]
    if missing_from_docs:
        parts.append(f"registered but undocumented: {missing_from_docs}")
    if missing_from_server:
        parts.append(f"documented but not registered: {missing_from_server}")
    return RuleResult("route-list", source, ok, "; ".join(parts), blocking=True)


# --- Rule 4: i18n key-parity claim (docs/I18N.md's G6 row vs. web/i18n catalogs) ------------


def check_i18n_parity(root: Path) -> RuleResult:
    """Re-prove docs/I18N.md's G6 claim ('keys(en) == keys(es), no empty ES values') by
    reusing scripts/i18n_parity.py's own flatten/compare logic against the actual catalogs."""
    parity = _load_sibling_module("i18n_parity")
    source = "web/i18n/en.json + web/i18n/es.json via scripts/i18n_parity.py"
    en = parity._load(parity.EN)
    es = parity._load(parity.ES)
    missing_in_es = sorted(set(en) - set(es))
    missing_in_en = sorted(set(es) - set(en))
    empty_es = sorted(k for k, v in es.items() if k in en and isinstance(v, str) and not v.strip())
    ok = not (missing_in_es or missing_in_en or empty_es)
    detail = (
        f"docs/I18N.md G6 claims keys(en) == keys(es); en has {len(en)} keys, es has {len(es)} "
        f"keys, {len(missing_in_es)} missing-in-es, {len(missing_in_en)} missing-in-en, "
        f"{len(empty_es)} empty-in-es"
    )
    return RuleResult("i18n-key-parity", source, ok, detail, blocking=True)


# --- Rule 5: duplicate-paragraph lint (README.md) --------------------------------------------

_WHITESPACE_RE = re.compile(r"\s+")
_BULLET_START_RE = re.compile(r"^-\s+")


def _split_into_units(text: str) -> list[str]:
    """Split text into paragraph-like units: blank-line-delimited blocks, further split at each
    top-level markdown bullet (`- ...`) so a duplicated *list item* — not just a duplicated
    free-standing paragraph — is its own comparable unit (continuation lines stay attached)."""
    units: list[str] = []
    for block in text.split("\n\n"):
        current: list[str] = []
        for line in block.split("\n"):
            if _BULLET_START_RE.match(line) and current:
                units.append("\n".join(current))
                current = [line]
            else:
                current.append(line)
        if current:
            units.append("\n".join(current))
    return units


def find_duplicate_paragraphs(text: str, min_len: int = 40) -> list[str]:
    """Normalize whitespace per unit and flag any unit (of meaningful length) that appears more
    than once — the class of copy-paste doc bug this repo has shipped before."""
    normalized = [_WHITESPACE_RE.sub(" ", u).strip() for u in _split_into_units(text)]
    seen: dict[str, int] = {}
    for p in normalized:
        if len(p) < min_len:
            continue
        seen[p] = seen.get(p, 0) + 1
    return sorted(p for p, count in seen.items() if count > 1)


def check_readme_duplicate_paragraphs(readme_text: str) -> RuleResult:
    source = "README.md itself (self-consistency; no external source of truth)"
    dupes = find_duplicate_paragraphs(readme_text)
    ok = not dupes
    if ok:
        detail = "no paragraph appears twice"
    else:
        preview = dupes[0][:80] + ("…" if len(dupes[0]) > 80 else "")
        detail = (
            f"{len(dupes)} duplicated paragraph(s), e.g. {preview!r} — "
            "TODO(maintainer): de-duplicate README.md (agent-do-not-modify)"
        )
    return RuleResult("readme-duplicate-paragraph", source, ok, detail, blocking=False)


def run_all(root: Path = ROOT) -> list[RuleResult]:
    results: list[RuleResult] = []

    claude_text = CLAUDE_MD.read_text(encoding="utf-8") if CLAUDE_MD.is_file() else ""
    results.append(check_test_count(claude_text, collected_test_count(root)))

    roadmap_text = ROADMAP_MD.read_text(encoding="utf-8") if ROADMAP_MD.is_file() else ""
    results.append(check_corrections_count(roadmap_text, load_corrections_count(CORRECTIONS_YAML)))

    api_md_text = API_MD.read_text(encoding="utf-8") if API_MD.is_file() else ""
    server_source = SERVER_PY.read_text(encoding="utf-8")
    api_source = API_PY.read_text(encoding="utf-8")
    results.append(check_routes(api_md_text, server_source, api_source))

    results.append(check_i18n_parity(root))

    readme_text = README_MD.read_text(encoding="utf-8") if README_MD.is_file() else ""
    results.append(check_readme_duplicate_paragraphs(readme_text))

    return results


def main() -> int:
    results = run_all(ROOT)
    failed_blocking = 0
    for r in results:
        if r.ok:
            marker = "PASS"
        elif r.blocking:
            marker = "FAIL"
            failed_blocking += 1
        else:
            marker = "WARN"
        print(f"  [{marker}] {r.name}: {r.detail}")
        print(f"           source of truth: {r.source_of_truth}")

    total_blocking = sum(1 for r in results if r.blocking)
    passed_blocking = sum(1 for r in results if r.blocking and r.ok)
    advisory = [r for r in results if not r.blocking]
    print(
        f"docs-figures: {passed_blocking}/{total_blocking} blocking checks passed "
        f"({sum(1 for r in advisory if r.ok)}/{len(advisory)} advisory checks passed)"
    )
    return 0 if failed_blocking == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
