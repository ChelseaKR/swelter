"""Docs-figures gate: the checker itself must catch a deliberate doc/source mismatch.

``scripts/docs_figures_check.py`` re-proves countable claims in prose against their sources of
truth. It is not an installed package (a `scripts/*.py` gate, like `a11y_check.py` and
`i18n_parity.py`), so it is loaded directly from its file path with importlib — the same
technique ``tests/test_firmware_drivers.py`` uses for the firmware driver modules.

These tests exercise each rule's pure extraction/comparison functions against small fixture
doc+source pairs, independent of this repo's own current prose — so a rule change here catches
real regressions in the checker rather than in swelter's docs.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"


def _load_script(name: str) -> ModuleType:
    path = SCRIPTS_DIR / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"_test_{name}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses in the loaded module need this to resolve types
    spec.loader.exec_module(module)
    return module


docs_figures = _load_script("docs_figures_check")


# --- rule 1: test count -----------------------------------------------------------------------


def test_extract_claude_test_count_reads_the_documented_number() -> None:
    text = "test       →  pytest                       (205 tests, all green)\n"
    assert docs_figures.extract_claude_test_count(text) == 205


def test_extract_claude_test_count_missing_line_returns_none() -> None:
    assert docs_figures.extract_claude_test_count("no such claim here") is None


def test_check_test_count_passes_when_claim_matches_reality() -> None:
    text = "test → pytest (205 tests, all green)\n"
    result = docs_figures.check_test_count(text, actual_count=lambda: 205)
    assert result.ok is True
    assert result.blocking is False  # CLAUDE.md is agent-do-not-modify: advisory, never fails CI


def test_check_test_count_detects_a_deliberate_mismatch() -> None:
    """The load-bearing case: a doc fed the *wrong* number must be caught, not silently passed."""
    text = "test → pytest (62 tests, all green)\n"
    result = docs_figures.check_test_count(text, actual_count=lambda: 205)
    assert result.ok is False
    assert "62" in result.detail
    assert "205" in result.detail
    # Advisory: wrong even though it must be reported, this rule cannot fail the process.
    assert result.blocking is False


# --- rule 2: registry (correction) count ------------------------------------------------------


def test_extract_roadmap_correction_count() -> None:
    text = "— 300 corrections across the 100 co-located nodes at the default size."
    assert docs_figures.extract_roadmap_correction_count(text) == 300


def test_check_corrections_count_fails_on_mismatch_and_is_blocking() -> None:
    text = "— 300 corrections across the 100 co-located nodes at the default size."
    result = docs_figures.check_corrections_count(text, actual_count=299)
    assert result.ok is False
    assert result.blocking is True  # docs/ROADMAP.md is editable: this rule hard-gates


def test_check_corrections_count_passes_on_match() -> None:
    text = "— 300 corrections across the 100 co-located nodes at the default size."
    result = docs_figures.check_corrections_count(text, actual_count=300)
    assert result.ok is True


# --- rule 3: route list -------------------------------------------------------------------------


def test_extract_api_md_routes_parses_table_and_strips_query_strings() -> None:
    text = """
## Endpoints at a glance

| Path | Returns |
| --- | --- |
| `/health` | Liveness |
| `/api/surface.json?hours=N` | Records |
| `/LICENSE`, `/DATA-LICENSE` | License files |
| `web/` static | The dashboard |

## Next section
not a table row
"""
    routes = docs_figures.extract_api_md_routes(text)
    assert routes == {"/health", "/api/surface.json", "/LICENSE", "/DATA-LICENSE"}


def test_extract_server_routes_matches_literal_and_versioned_paths() -> None:
    api_source = 'SENSORTHINGS_VERSION = "1.1"\n'
    server_source = """
if path in ("/health", "/healthz"):
    pass
elif path == v:
    pass
elif path == f"{v}/Things":
    pass
elif path == "/export.csv":
    pass
"""
    routes = docs_figures.extract_server_routes(server_source, api_source)
    assert routes == {"/health", "/healthz", "/v1.1", "/v1.1/Things", "/export.csv"}


def test_check_routes_flags_a_route_registered_but_undocumented() -> None:
    api_md = """
## Endpoints at a glance

| Path | Returns |
| --- | --- |
| `/health` | Liveness |
"""
    api_source = 'SENSORTHINGS_VERSION = "1.1"\n'
    server_source = """
if path in ("/health", "/healthz"):
    pass
"""
    result = docs_figures.check_routes(api_md, server_source, api_source)
    assert result.ok is False
    assert result.blocking is True
    assert "/healthz" in result.detail


def test_check_routes_passes_when_doc_and_server_agree() -> None:
    api_md = """
## Endpoints at a glance

| Path | Returns |
| --- | --- |
| `/health` | Liveness |
"""
    api_source = 'SENSORTHINGS_VERSION = "1.1"\n'
    server_source = """
if path == "/health":
    pass
"""
    result = docs_figures.check_routes(api_md, server_source, api_source)
    assert result.ok is True


# --- rule 5: duplicate-paragraph lint ---------------------------------------------------------


def test_find_duplicate_paragraphs_detects_a_repeated_bullet() -> None:
    text = (
        "Intro paragraph that is long enough to matter for the minimum length threshold here.\n\n"
        "- `swelter fetch --source sensor-community` — real physical low-cost sensors from the\n"
        "  community network, ingested raw and shown provisional until calibrated.\n"
        "- `swelter fetch --source sensor-community` — real physical low-cost sensors from the\n"
        "  community network, ingested raw and shown provisional until calibrated.\n"
    )
    dupes = docs_figures.find_duplicate_paragraphs(text)
    assert len(dupes) == 1
    assert "sensor-community" in dupes[0]


def test_find_duplicate_paragraphs_no_false_positive_on_distinct_bullets() -> None:
    text = (
        "- first bullet with genuinely distinct long-enough content to pass the length floor\n"
        "- second bullet with different and also long-enough content to pass the length floor\n"
    )
    assert docs_figures.find_duplicate_paragraphs(text) == []


def test_check_readme_duplicate_paragraphs_is_advisory() -> None:
    text = "- one two three four five six seven eight nine ten eleven twelve thirteen fourteen\n"
    result = docs_figures.check_readme_duplicate_paragraphs(text)
    assert result.ok is True
    assert result.blocking is False


# --- end-to-end smoke: the real repo's blocking rules pass today ------------------------------


def test_run_all_reports_six_rules_and_blocking_rules_pass_on_this_repo() -> None:
    results = docs_figures.run_all(docs_figures.ROOT)
    assert len(results) == 6
    blocking_failures = [r for r in results if r.blocking and not r.ok]
    assert not blocking_failures, blocking_failures


def test_no_test_count_claim_is_compliance_not_a_permanent_warning() -> None:
    """CLAUDE.md's own rule is "never put a test count in prose unless a check regenerates it",
    and the count this rule was written for was deleted under that rule. The rule then warned
    ``could not find a '(N tests, all green)' line`` on every run, forever, for a state that is
    correct. An advisory channel that is always amber reports nothing, because nobody reads it.
    """
    result = docs_figures.check_test_count("no count claimed anywhere", actual_count=lambda: 205)
    assert result.ok is True
    assert result.blocking is False
    assert "no hard-coded test count" in result.detail


def test_the_pytest_collection_runs_only_when_there_is_a_claim_to_compare() -> None:
    """The `pytest --collect-only` subprocess used to run on every `make verify` and have its
    result discarded, because the claim it was collected to compare against no longer exists."""
    calls = []

    def counter() -> int:
        calls.append(1)
        return 205

    docs_figures.check_test_count("no count claimed anywhere", actual_count=counter)
    assert calls == []

    docs_figures.check_test_count("(205 tests, all green)", actual_count=counter)
    assert calls == [1]


def test_this_repository_makes_no_hard_coded_test_count_claim() -> None:
    """If CLAUDE.md ever regains a count, the rule above starts comparing it again."""
    claude = (docs_figures.ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    assert docs_figures.extract_claude_test_count(claude) is None


# --- rule 6: paper test count -----------------------------------------------------------------


def test_extract_paper_test_count_reads_the_documented_number() -> None:
    text = "checks, and a 257-test suite with\na 90% branch-coverage floor.\n"
    assert docs_figures.extract_paper_test_count(text) == 257


def test_extract_paper_test_count_missing_claim_returns_none() -> None:
    assert docs_figures.extract_paper_test_count("the full test suite with a floor") is None


def test_check_paper_test_count_detects_a_deliberate_mismatch_and_blocks() -> None:
    """The load-bearing case, and the one that actually shipped: paper.md said "a 257-test
    suite" while the collected count was roughly four times that, and no gate read paper/."""
    result = docs_figures.check_paper_test_count("a 257-test suite", actual_count=lambda: 1040)
    assert result.ok is False
    assert "257" in result.detail
    assert "1040" in result.detail
    # Blocking: the paper is maintainer prose, not agent-do-not-modify, so this fails CI.
    assert result.blocking is True


def test_check_paper_test_count_passes_when_claim_matches_reality() -> None:
    result = docs_figures.check_paper_test_count("a 205-test suite", actual_count=lambda: 205)
    assert result.ok is True
    assert result.blocking is True


def test_paper_without_a_count_is_compliance_and_collects_nothing() -> None:
    """Absence of the claim passes without running the collection subprocess, like rule 1."""
    calls: list[int] = []

    def counter() -> int:
        calls.append(1)
        return 205

    result = docs_figures.check_paper_test_count("no count claimed", actual_count=counter)
    assert result.ok is True
    assert result.blocking is True
    assert calls == []

    docs_figures.check_paper_test_count("a 205-test suite", actual_count=counter)
    assert calls == [1]


def test_the_paper_makes_no_hard_coded_test_count_claim() -> None:
    """If paper/paper.md ever regains a count, rule 6 starts comparing it against pytest."""
    paper = (docs_figures.ROOT / "paper" / "paper.md").read_text(encoding="utf-8")
    assert docs_figures.extract_paper_test_count(paper) is None
