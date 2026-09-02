"""Demo-artifact gate: the checker itself must catch a drifted committed artifact.

``scripts/demo_artifact_check.py`` replays the committed demo and byte-compares every
generated file that is git-tracked under ``web/``. It exists because the committed
``web/sample-surface.json`` silently kept pre-#142 heat-index error bars on eleven
single-member cells: the schema contract held, so no gate noticed a committed artifact
diverging from the computation it stands in for. These tests exercise the comparison
logic against small fixture trees, independent of this repo's own current artifacts,
and one repo-level test runs the real gate end to end so the sentinel artifact and the
replay wiring cannot rot.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"


def _load_script(name: str) -> ModuleType:
    path = SCRIPTS_DIR / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"_test_{name}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


demo_artifacts = _load_script("demo_artifact_check")


def _tree(root: Path, files: dict[str, str]) -> None:
    for rel, content in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def test_identical_tracked_files_compare_clean(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    gen = tmp_path / "gen"
    _tree(root, {"web/sample-surface.json": '{"cells": 1}'})
    _tree(gen, {"sample-surface.json": '{"cells": 1}'})
    compared, drifted = demo_artifacts.compare_generated(root, gen, {"web/sample-surface.json"})
    assert compared == ["web/sample-surface.json"]
    assert drifted == []


def test_a_single_changed_byte_is_reported_as_drift(tmp_path: Path) -> None:
    """The load-bearing case, and the one that actually shipped: same schema-valid shape,
    one numeric value differing from what the pipeline computes."""
    root = tmp_path / "repo"
    gen = tmp_path / "gen"
    _tree(root, {"web/sample-surface.json": '{"uncertainty": 0.942}'})
    _tree(gen, {"sample-surface.json": '{"uncertainty": 1.54}'})
    compared, drifted = demo_artifacts.compare_generated(root, gen, {"web/sample-surface.json"})
    assert compared == ["web/sample-surface.json"]
    assert drifted == ["web/sample-surface.json"]


def test_a_generated_file_missing_from_the_repo_is_drift_not_a_skip(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    gen = tmp_path / "gen"
    root.mkdir()
    _tree(gen, {"alerts.json": "[]"})
    compared, drifted = demo_artifacts.compare_generated(root, gen, {"web/alerts.json"})
    assert compared == ["web/alerts.json"]
    assert drifted == ["web/alerts.json"]


def test_untracked_scratch_output_is_not_compared(tmp_path: Path) -> None:
    """The replay writes more than the committed set (store files, licenses); only files
    git tracks under web/ are claims the repository makes, so only those are compared."""
    root = tmp_path / "repo"
    gen = tmp_path / "gen"
    _tree(root, {"web/sample-surface.json": "{}"})
    _tree(gen, {"sample-surface.json": "{}", "DATA-LICENSE": "CC0-1.0"})
    compared, drifted = demo_artifacts.compare_generated(root, gen, {"web/sample-surface.json"})
    assert compared == ["web/sample-surface.json"]
    assert drifted == []


def test_nothing_tracked_means_nothing_compared_which_main_refuses(tmp_path: Path) -> None:
    """An empty comparison set must surface as emptiness for main() to refuse, never as a
    quiet pass: a gate that compares nothing is the failure class this gate exists for."""
    root = tmp_path / "repo"
    gen = tmp_path / "gen"
    root.mkdir()
    _tree(gen, {"sample-surface.json": "{}"})
    compared, drifted = demo_artifacts.compare_generated(root, gen, set())
    assert compared == []
    assert drifted == []


def test_the_gate_passes_on_this_repository_and_names_the_sentinel(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """End to end over the real committed artifacts: the replay runs, the comparison set
    includes web/sample-surface.json, and every committed artifact matches. If this fails
    after a pipeline change, regenerate with `uv run swelter demo` and commit the diff."""
    exit_code = demo_artifacts.main()
    out = capsys.readouterr().out
    assert exit_code == 0, out
    assert "web/sample-surface.json" in out
