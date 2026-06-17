"""End-to-end CLI: the demo replay and the export path a community actually runs."""

from __future__ import annotations

from pathlib import Path

import pytest

from swelter.cli import main
from swelter.store import open_store

from .conftest import ROOT


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["version"]) == 0
    assert "swelter" in capsys.readouterr().out


def test_demo_pipeline_calibrates_and_aggregates(tmp_path: Path) -> None:
    store_dir = tmp_path / "store"
    rc = main(
        [
            "demo",
            "--data",
            str(ROOT / "data" / "demo"),
            "--store",
            str(store_dir),
            "--config",
            str(ROOT / "network.yaml"),
        ]
    )
    assert rc == 0
    store = open_store(store_dir)
    try:
        assert store.count() > 0
        assert len(store.read(calibration="raw")) > 0
        calibrated = [o for o in store.all() if o.is_calibrated]
        assert calibrated, "demo should produce calibrated observations"
    finally:
        store.close()
    assert (store_dir / "aggregate.geojson").is_file()


def test_ingest_then_export_csv(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    payloads = tmp_path / "in.jsonl"
    payloads.write_text(
        '{"node_id":"node-01","timestamp":"2026-06-01T00:00:00Z","temp_c":25.0}\n',
        encoding="utf-8",
    )
    store_dir = tmp_path / "store"
    assert main(["ingest", str(payloads), "--store", str(store_dir)]) == 0
    capsys.readouterr()
    assert main(["export", "--store", str(store_dir), "--format", "csv"]) == 0
    out = capsys.readouterr().out
    assert "node_id,timestamp" in out
    assert "node-01" in out
