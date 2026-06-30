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


def test_init_scaffolds_a_loadable_network(tmp_path: Path) -> None:
    from swelter.config import load_config

    cfg = tmp_path / "my-network.yaml"
    assert main(["init", "--config", str(cfg), "--name", "Eastside: heat & air"]) == 0
    assert cfg.is_file()
    network = load_config(str(cfg))  # the scaffold parses, and the name survived special characters
    assert network.name == "Eastside: heat & air"
    assert len(network.nodes) == 2
    assert len(network.reference_monitors) == 1


def test_init_refuses_to_overwrite_without_force(tmp_path: Path) -> None:
    cfg = tmp_path / "network.yaml"
    cfg.write_text("name: keep me\n", encoding="utf-8")
    assert main(["init", "--config", str(cfg)]) == 1  # refused
    assert cfg.read_text(encoding="utf-8") == "name: keep me\n"  # untouched
    assert main(["init", "--config", str(cfg), "--force"]) == 0  # --force overwrites
    assert "keep me" not in cfg.read_text(encoding="utf-8")


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


def test_demo_bakes_alerts_and_cooling_into_web(tmp_path: Path) -> None:
    import json

    web = tmp_path / "web"
    web.mkdir()
    rc = main(
        [
            "demo",
            "--data",
            str(ROOT / "data" / "demo"),
            "--store",
            str(tmp_path / "store"),
            "--config",
            str(ROOT / "network.yaml"),
            "--web",
            str(web),
            "--cooling-centers",
            str(ROOT / "data" / "cooling_centers.geojson"),
        ]
    )
    assert rc == 0
    feed = json.loads((web / "alerts.json").read_text(encoding="utf-8"))
    assert "alerts" in feed and "thresholds" in feed
    assert feed["generated"]  # a data-derived timestamp, even on a calm week
    assert (web / "alerts.xml").read_text(encoding="utf-8").startswith("<?xml")
    cooling = json.loads((web / "cooling-centers.geojson").read_text(encoding="utf-8"))
    assert cooling["type"] == "FeatureCollection"
    assert len(cooling["features"]) >= 1


def test_alerts_command_emits_atom(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    store_dir = tmp_path / "store"
    main(
        [
            "demo",
            "--data",
            str(ROOT / "data" / "demo"),
            "--store",
            str(store_dir),
            "--config",
            str(ROOT / "network.yaml"),
            "--web",
            str(tmp_path / "web"),
            "--cooling-centers",
            str(ROOT / "data" / "cooling_centers.geojson"),
        ]
    )
    capsys.readouterr()  # drop the demo's output
    rc = main(
        [
            "alerts",
            "--store",
            str(store_dir),
            "--config",
            str(ROOT / "network.yaml"),
            "--format",
            "atom",
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert out.startswith("<?xml") and "<feed" in out


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
