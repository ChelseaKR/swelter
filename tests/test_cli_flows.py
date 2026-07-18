"""CLI surface coverage: the real command flows a collective runs, plus the error and
exit-code paths that keep a misuse from looking like success.

These exercise ``swelter`` end to end through ``cli.main`` — argument parsing, subcommand
routing, the calibrate→rebuild-from-raw invariant (hard rule #3), the no-PII label warning
(hard rule #1), and the ``fetch`` source routing — without touching the network. The two
``serve`` entry points are driven with a stubbed ``serve`` so the context-construction and
store-lifecycle paths run without binding a socket.
"""

from __future__ import annotations

import csv
import json
import sqlite3
from collections.abc import Iterable
from pathlib import Path

import pytest

from swelter import aggregate, snapshot
from swelter.cli import _merge_network_doc, _write_web_sample, main
from swelter.config import load_config
from swelter.models import (
    RAW,
    SOURCE_NATIVE,
    SOURCE_OPENAQ,
    SOURCE_OPENMETEO,
    SOURCE_SENSOR_COMMUNITY,
    Observation,
)
from swelter.server import ServerContext
from swelter.sources import openaq, openmeteo, sensor_community
from swelter.sources._http import SourceError
from swelter.store import SqliteStore, WriteResult, open_store, store_paths

from .conftest import DEMO, ROOT, make_obs

NETWORK = str(ROOT / "network.yaml")
COOLING = str(ROOT / "data" / "cooling_centers.geojson")


def _demo_into(store_dir: Path, web: Path) -> None:
    """Replay the recorded demo week into a fresh store + web dir (the pipeline keystone)."""
    rc = main(
        [
            "demo",
            "--data",
            str(DEMO),
            "--store",
            str(store_dir),
            "--config",
            NETWORK,
            "--web",
            str(web),
            "--cooling-centers",
            COOLING,
        ]
    )
    assert rc == 0


@pytest.fixture(scope="module")
def demo_store(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A populated store (raw + calibrated + registry) shared by the read-only command tests."""
    base = tmp_path_factory.mktemp("demo")
    _demo_into(base / "store", base / "web")
    return base / "store"


# -- qc ----------------------------------------------------------------------


def test_qc_text_reports_health_and_coverage(
    demo_store: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = main(["qc", "--store", str(demo_store), "--config", NETWORK])
    assert rc == 0
    err = capsys.readouterr().err
    assert "nodes" in err
    # The coverage-equity line surfaces calibrated-vs-raw counts (audit B3), not a ranking.
    assert "calibrated" in err and "confirmed" in err


def test_qc_json_is_machine_readable(demo_store: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["qc", "--store", str(demo_store), "--config", NETWORK, "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert {"nodes", "gaps", "coverage_equity"} <= payload.keys()
    assert payload["nodes"], "demo network has nodes"
    summary = payload["coverage_equity"]["summary"]
    assert summary["calibrated_nodes"] <= summary["nodes"]


def test_qc_on_empty_store_says_so(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["qc", "--store", str(tmp_path / "empty"), "--config", NETWORK])
    assert rc == 0
    assert "store is empty" in capsys.readouterr().err


# -- status (steward plan, EXP-05) --------------------------------------------


def test_status_plan_text_reports_ranked_actions(
    demo_store: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = main(["status", "--plan", "--store", str(demo_store), "--config", NETWORK])
    assert rc == 0
    err = capsys.readouterr().err
    assert "steward plan" in err
    assert "collective disposes" in err  # the audit B4/B5 disclaimer always prints


def test_status_plan_json_is_machine_readable(
    demo_store: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = main(["status", "--plan", "--json", "--store", str(demo_store), "--config", NETWORK])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert {"generated_for", "actions", "disclaimer"} <= payload.keys()
    assert payload["actions"], "demo network has offline/degraded nodes and coverage gaps"
    for action in payload["actions"]:
        assert action["evidence"], "every action names its evidence source"
    # priorities are non-decreasing: offline/expired-correction bands sort before coverage gaps.
    priorities = [a["priority"] for a in payload["actions"]]
    assert priorities == sorted(priorities)


def test_status_on_empty_store_says_so(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["status", "--plan", "--store", str(tmp_path / "empty"), "--config", NETWORK])
    assert rc == 0
    assert "store is empty" in capsys.readouterr().err


def test_status_on_empty_store_json_is_still_valid(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = main(
        ["status", "--plan", "--json", "--store", str(tmp_path / "empty"), "--config", NETWORK]
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["actions"] == []
    assert "collective disposes" in payload["disclaimer"]


def test_status_with_no_registry_file_treats_corrections_as_empty(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A store with raw data but no committed corrections.yaml still produces a plan (guard)."""
    store_dir = tmp_path / "store"
    _demo_into(store_dir, tmp_path / "web")
    store_paths(store_dir)["registry"].unlink(missing_ok=True)
    rc = main(["status", "--plan", "--json", "--store", str(store_dir), "--config", NETWORK])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert not any(a["kind"].startswith("correction_") for a in payload["actions"])


# -- config loading (PII + missing) ------------------------------------------


def test_load_config_warns_on_pii_label(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A label that looks like a street address is published, so the CLI warns (hard rule #1)."""
    cfg = tmp_path / "pii.yaml"
    cfg.write_text(
        "name: Test\n"
        "grid_resolution_m: 150\n"
        "languages: [en]\n"
        "reference_monitors: []\n"
        "nodes:\n"
        "- node_id: node-01\n"
        "  label: 123 Main Street\n"
        "  lat: 38.5\n"
        "  lon: -121.5\n"
        "  location: coarse\n"
        "calibration_windows: []\n",
        encoding="utf-8",
    )
    rc = main(["qc", "--store", str(tmp_path / "store"), "--config", str(cfg)])
    assert rc == 0
    assert "looks like a street address" in capsys.readouterr().err


def test_missing_config_falls_back_to_empty_network(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "surface.geojson"
    rc = main(
        [
            "aggregate",
            "--store",
            str(tmp_path / "store"),
            "--config",
            str(tmp_path / "nope.yaml"),
            "--out",
            str(out),
        ]
    )
    assert rc == 0
    assert "not found; using an empty network" in capsys.readouterr().err


# -- ingest / export ---------------------------------------------------------


def test_ingest_missing_input_returns_1(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["ingest", str(tmp_path / "absent.jsonl"), "--store", str(tmp_path / "store")])
    assert rc == 1
    assert "not found" in capsys.readouterr().err


def test_export_json_is_cc0_licensed(demo_store: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["export", "--store", str(demo_store), "--format", "json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    # Hard rule #4: observations stay open and portable.
    assert payload["license"] == "CC0-1.0"
    assert payload["observations"], "demo store has observations to export"


def test_export_filters_by_parameter(demo_store: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["export", "--store", str(demo_store), "--format", "csv", "--parameter", "pm25_ugm3"])
    assert rc == 0
    body = capsys.readouterr().out
    rows = [line for line in body.splitlines() if line and not line.startswith("node_id,")]
    assert rows, "at least one pm25 row"
    assert all(",pm25_ugm3," in row for row in rows)


# -- aggregate ---------------------------------------------------------------


def test_aggregate_writes_geojson_surface(
    demo_store: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "surface.geojson"
    rc = main(["aggregate", "--store", str(demo_store), "--config", NETWORK, "--out", str(out)])
    assert rc == 0
    fc = json.loads(out.read_text(encoding="utf-8"))
    assert fc["type"] == "FeatureCollection"
    assert fc["features"], "demo surface has cells"


# -- alerts ------------------------------------------------------------------


def test_alerts_json_and_web_baking(
    demo_store: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    web = tmp_path / "web"
    web.mkdir()
    rc = main(
        [
            "alerts",
            "--store",
            str(demo_store),
            "--config",
            NETWORK,
            "--format",
            "json",
            "--web",
            str(web),
        ]
    )
    assert rc == 0
    stdout = capsys.readouterr().out
    feed = json.loads(stdout)
    assert "alerts" in feed and "thresholds" in feed
    baked_feed = json.loads((web / "alerts.json").read_text(encoding="utf-8"))
    assert baked_feed["rights"]["links"] == [{"rel": "license", "href": "DATA-LICENSE"}]
    atom = (web / "alerts.xml").read_text(encoding="utf-8")
    assert atom.startswith("<?xml")
    assert '<link rel="license" href="DATA-LICENSE"/>' in atom
    es_atom = (web / "alerts.es.xml").read_text(encoding="utf-8")
    assert es_atom.startswith("<?xml")
    assert 'xml:lang="es"' in es_atom


# -- brief (E1 / F5: Danger-day count + sourced canopy/AC-access/redlining context) ------------

CANOPY = str(ROOT / "data" / "context_layers.geojson")
AC_ACCESS = str(ROOT / "data" / "ac_access_layer.geojson")
REDLINING = str(ROOT / "data" / "redlining_layer.geojson")
_BRIEF_AREA = "38.567867,-121.515433"  # node-01's published cell; has canopy/AC/redlining sample


def test_brief_text_for_one_area_includes_sourced_context(
    demo_store: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = main(
        [
            "brief",
            "--store",
            str(demo_store),
            "--config",
            NETWORK,
            "--area",
            _BRIEF_AREA,
            "--canopy",
            CANOPY,
            "--ac-access",
            AC_ACCESS,
            "--redlining",
            REDLINING,
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "Danger range" in out and "day(s) measured" in out
    assert "Tree-canopy coverage" in out and "USDA" not in out  # demo dataset, not the real source
    assert "may lack air conditioning" in out
    assert "grade" in out and "Home Owners' Loan Corporation" in out


def test_brief_json_is_machine_readable_and_sourced(
    demo_store: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = main(
        [
            "brief",
            "--store",
            str(demo_store),
            "--config",
            NETWORK,
            "--area",
            _BRIEF_AREA,
            "--format",
            "json",
            "--canopy",
            CANOPY,
            "--ac-access",
            AC_ACCESS,
            "--redlining",
            REDLINING,
        ]
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    brief = payload[_BRIEF_AREA]
    assert brief["danger"]["parameter"] == "heat_index_c"
    assert brief["danger"]["severity"] == "Danger"
    assert brief["canopy"]["source_url"]
    assert brief["ac_access"]["source_url"]
    assert brief["redlining"]["holc_grade"] in ("A", "B", "C", "D")


def test_brief_without_context_datasets_still_builds_the_danger_line(
    demo_store: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = main(
        [
            "brief",
            "--store",
            str(demo_store),
            "--config",
            NETWORK,
            "--area",
            _BRIEF_AREA,
            "--canopy",
            str(tmp_path / "no-canopy.geojson"),
            "--ac-access",
            str(tmp_path / "no-ac.geojson"),
            "--redlining",
            str(tmp_path / "no-redlining.geojson"),
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "Danger range" in out
    assert "Tree-canopy" not in out
    assert "air conditioning" not in out
    assert "Home Owners' Loan Corporation" not in out


def test_brief_unknown_area_returns_1(demo_store: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(
        ["brief", "--store", str(demo_store), "--config", NETWORK, "--area", "0.000000,0.000000"]
    )
    assert rc == 1
    assert "no brief for area" in capsys.readouterr().err


def test_brief_pm25_parameter_selects_the_aqi_floor(
    demo_store: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = main(
        [
            "brief",
            "--store",
            str(demo_store),
            "--config",
            NETWORK,
            "--area",
            _BRIEF_AREA,
            "--parameter",
            "pm25_ugm3",
            "--format",
            "json",
        ]
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload[_BRIEF_AREA]["danger"]["parameter"] == "pm25_ugm3"
    assert payload[_BRIEF_AREA]["danger"]["floor"] == 101.0


# -- calibrate / rebuild (hard rule #3: rebuild from immutable raw) -----------


def test_calibrate_missing_colocation_returns_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = main(
        [
            "calibrate",
            "--store",
            str(tmp_path / "store"),
            "--colocation",
            str(tmp_path / "absent.jsonl"),
        ]
    )
    assert rc == 1
    assert "not found" in capsys.readouterr().err


def test_calibrate_fit_only_writes_registry_but_no_calibrated(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store_dir = tmp_path / "store"
    # Seed the store with raw demo readings so a non-fit-only run would have something to apply.
    assert main(["ingest", str(DEMO / "observations.jsonl"), "--store", str(store_dir)]) == 0
    rc = main(
        [
            "calibrate",
            "--store",
            str(store_dir),
            "--colocation",
            str(DEMO / "colocation.jsonl"),
            "--fit-only",
        ]
    )
    assert rc == 0
    assert (store_dir / "corrections.yaml").is_file()
    store = open_store(store_dir)
    try:
        assert all(o.calibration == RAW for o in store.all()), "fit-only must not apply"
    finally:
        store.close()


def test_calibrate_then_apply_produces_calibrated(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store_dir = tmp_path / "store"
    assert main(["ingest", str(DEMO / "observations.jsonl"), "--store", str(store_dir)]) == 0
    rc = main(
        [
            "calibrate",
            "--store",
            str(store_dir),
            "--colocation",
            str(DEMO / "colocation.jsonl"),
        ]
    )
    assert rc == 0
    store = open_store(store_dir)
    try:
        calibrated = [o for o in store.all() if o.is_calibrated]
        raw = store.read(calibration=RAW)
    finally:
        store.close()
    assert calibrated, "applying the fit must emit calibrated observations"
    assert raw, "raw stays append-only beside calibrated (never overwritten)"


def test_rebuild_reconstructs_calibrated_from_raw(demo_store: Path, tmp_path: Path) -> None:
    """The whole derived layer rebuilds from immutable raw + the registry (hard rule #3)."""
    # Work on a copy so the shared demo_store stays intact for other tests.
    work = tmp_path / "store"
    _demo_into(work, tmp_path / "web")
    store = open_store(work)
    try:
        before = sum(1 for o in store.all() if o.is_calibrated)
    finally:
        store.close()
    assert before > 0

    rc = main(["rebuild", "--store", str(work), "--config", NETWORK])
    assert rc == 0
    store = open_store(work)
    try:
        after = sum(1 for o in store.all() if o.is_calibrated)
    finally:
        store.close()
    assert after == before, "rebuild reproduces the same derived rows from raw"


def test_rebuild_without_registry_only_drops(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store_dir = tmp_path / "store"
    assert main(["ingest", str(DEMO / "observations.jsonl"), "--store", str(store_dir)]) == 0
    rc = main(["rebuild", "--store", str(store_dir), "--config", NETWORK])
    assert rc == 0
    assert "no registry to reapply" in capsys.readouterr().err


# -- serve (stubbed so no socket binds) --------------------------------------


def test_serve_builds_context_and_closes_store(
    demo_store: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: list[ServerContext] = []

    def fake_serve(ctx: ServerContext, host: str = "127.0.0.1", port: int = 8000) -> None:
        captured.append(ctx)

    monkeypatch.setattr("swelter.cli.serve", fake_serve)
    rc = main(
        [
            "serve",
            "--store",
            str(demo_store),
            "--config",
            NETWORK,
            "--web",
            str(tmp_path / "web"),
            # A missing cooling-centers file must leave the overlay empty, not error.
            "--cooling-centers",
            str(tmp_path / "absent.geojson"),
        ]
    )
    assert rc == 0
    assert len(captured) == 1
    assert captured[0].cooling_centers_path is None


def test_demo_serve_runs_pipeline_then_serves(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    served: list[ServerContext] = []

    def fake_serve(ctx: ServerContext, host: str = "127.0.0.1", port: int = 8000) -> None:
        served.append(ctx)

    monkeypatch.setattr("swelter.cli.serve", fake_serve)
    rc = main(
        [
            "demo",
            "--data",
            str(DEMO),
            "--store",
            str(tmp_path / "store"),
            "--config",
            NETWORK,
            "--web",
            str(tmp_path / "web"),
            "--cooling-centers",
            COOLING,
            "--serve",
        ]
    )
    assert rc == 0
    assert len(served) == 1


# -- fetch (source routing + exit codes, no network) -------------------------


def _real_temp(node_id: str, *, source: str = SOURCE_NATIVE) -> list[Observation]:
    return [
        make_obs(
            node_id=node_id,
            parameter="temp_c",
            value=31.0,
            source=source,
            calibration=RAW,
        )
    ]


def _openaq_ledger(
    location_id: int,
    *,
    fetched_at: str,
    license_id: int = 1,
    license_name: str = "CC BY 4.0",
    valid_from: str | None = None,
    valid_to: str | None = None,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "source": "OpenAQ v3",
        "generated_at": fetched_at,
        "entries": [
            {
                "location_id": location_id,
                "license_id": license_id,
                "location_name": f"Site {location_id}",
                "provider": f"Provider {location_id}",
                "license_name": license_name,
                "license_url": "https://creativecommons.org/licenses/by/4.0/",
                "attribution": f"Provider {location_id}",
                "attribution_url": "",
                "valid_from": valid_from,
                "valid_to": valid_to,
                "upstream_url": f"{openaq.API}/locations/{location_id}",
                "fetched_at": fetched_at,
                "unavailable_fields": [],
            }
        ],
        "excluded_locations": [],
    }


def _tree_bytes(*roots: Path) -> dict[str, bytes]:
    """Capture every material file so a rejected fetch can prove it made no changes."""
    captured: dict[str, bytes] = {}
    for root in roots:
        if root.is_file():
            captured[str(root)] = root.read_bytes()
        elif root.is_dir():
            for path in sorted(root.rglob("*")):
                if path.is_file():
                    captured[str(path)] = path.read_bytes()
    return captured


def test_fetch_openaq_without_key_returns_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OPENAQ_API_KEY", raising=False)
    rc = main(
        [
            "fetch",
            "--source",
            "openaq",
            "--store",
            str(tmp_path / "store"),
            "--config",
            str(tmp_path / "net.yaml"),
            "--web",
            str(tmp_path / "web"),
        ]
    )
    assert rc == 1
    assert "needs an API key" in capsys.readouterr().err


def test_fetch_source_error_returns_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*_a: object, **_k: object) -> list[Observation]:
        raise SourceError("upstream 503")

    monkeypatch.setattr(openmeteo, "fetch", boom)
    rc = main(
        [
            "fetch",
            "--source",
            "openmeteo",
            "--store",
            str(tmp_path / "store"),
            "--config",
            str(tmp_path / "net.yaml"),
            "--web",
            str(tmp_path / "web"),
        ]
    )
    assert rc == 1
    assert "fetch failed" in capsys.readouterr().err


def test_fetch_empty_result_returns_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(openmeteo, "fetch", lambda *_a, **_k: [])
    rc = main(
        [
            "fetch",
            "--source",
            "openmeteo",
            "--store",
            str(tmp_path / "store"),
            "--config",
            str(tmp_path / "net.yaml"),
            "--web",
            str(tmp_path / "web"),
        ]
    )
    assert rc == 1
    assert "no readings returned" in capsys.readouterr().err


def test_fetch_openmeteo_happy_path_and_serve(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    node_id = openmeteo.CALIFORNIA[0].node_id
    monkeypatch.setattr(
        openmeteo,
        "fetch",
        lambda *_a, **_k: _real_temp(node_id, source=SOURCE_OPENMETEO),
    )
    served: list[ServerContext] = []

    def fake_serve(ctx: ServerContext, host: str = "127.0.0.1", port: int = 8000) -> None:
        served.append(ctx)

    monkeypatch.setattr("swelter.cli.serve", fake_serve)

    cfg = tmp_path / "net.yaml"
    rc = main(
        [
            "fetch",
            "--source",
            "openmeteo",
            "--store",
            str(tmp_path / "store"),
            "--config",
            str(cfg),
            "--web",
            str(tmp_path / "web"),
            "--cooling-centers",
            str(tmp_path / "absent.geojson"),
            "--serve",
        ]
    )
    assert rc == 0
    # The fetched network was written and is loadable; the real reading landed in the store.
    network = load_config(str(cfg))
    assert any(n.node_id == node_id for n in network.nodes)
    assert len(served) == 1
    terms = json.loads((tmp_path / "store" / "source-metadata.json").read_text(encoding="utf-8"))
    assert terms["license"] == openmeteo.LICENSE
    assert terms["attribution"] == openmeteo.ATTRIBUTION


def test_fetch_openaq_with_key_stores_real_sensors(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    nodes: dict[str, tuple[str, float, float]] = {"oaq-1": ("Site 1", 38.58, -121.49)}

    def fake(
        *_a: object, **_k: object
    ) -> tuple[list[Observation], dict[str, tuple[str, float, float]]]:
        ledger = _k.get("license_ledger")
        assert isinstance(ledger, dict)
        ledger.update(
            {
                "schema_version": 1,
                "source": "OpenAQ v3",
                "generated_at": "2026-07-16T00:00:00Z",
                "entries": [
                    {
                        "location_id": 1,
                        "license_id": 1,
                        "location_name": "Site 1",
                        "provider": "Provider",
                        "license_name": "CC BY 4.0",
                        "license_url": "https://creativecommons.org/licenses/by/4.0/",
                        "attribution": "Provider",
                        "attribution_url": "",
                        "valid_from": None,
                        "valid_to": None,
                        "upstream_url": f"{openaq.API}/locations/1",
                        "fetched_at": "2026-07-16T00:00:00Z",
                        "unavailable_fields": [],
                    }
                ],
                "excluded_locations": [],
            }
        )
        return _real_temp("oaq-1", source=SOURCE_OPENAQ), nodes

    monkeypatch.setattr(openaq, "fetch", fake)
    cfg = tmp_path / "net.yaml"
    rc = main(
        [
            "fetch",
            "--source",
            "openaq",
            "--api-key",
            "test-key",
            "--store",
            str(tmp_path / "store"),
            "--config",
            str(cfg),
            "--web",
            str(tmp_path / "web"),
        ]
    )
    assert rc == 0
    network = load_config(str(cfg))
    # OpenAQ sensors are real and precise but uncalibrated → no calibration windows.
    assert any(n.node_id == "oaq-1" for n in network.nodes)
    assert not network.calibration_windows
    ledger = json.loads(
        (tmp_path / "store" / "source-license-ledger.json").read_text(encoding="utf-8")
    )
    assert ledger["entries"][0]["location_id"] == 1
    terms = json.loads((tmp_path / "store" / "source-metadata.json").read_text(encoding="utf-8"))
    assert terms["source"] == "OpenAQ"
    assert terms["license"] == openaq.LICENSE

    capsys.readouterr()
    assert main(["export", "--store", str(tmp_path / "store"), "--format", "json"]) == 0
    exported = json.loads(capsys.readouterr().out)
    [record] = exported["observations"]
    assert record["data_license"].startswith("CC BY 4.0")
    assert record["data_attribution"] == "Provider"


def test_fetch_openaq_source_error_returns_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*_a: object, **_k: object) -> tuple[list[Observation], dict[str, object]]:
        raise SourceError("openaq 429")

    monkeypatch.setattr(openaq, "fetch", boom)
    rc = main(
        [
            "fetch",
            "--source",
            "openaq",
            "--api-key",
            "test-key",
            "--store",
            str(tmp_path / "store"),
            "--config",
            str(tmp_path / "net.yaml"),
            "--web",
            str(tmp_path / "web"),
        ]
    )
    assert rc == 1
    assert "fetch failed" in capsys.readouterr().err


def test_fetch_sensor_community_empty_hints_europe(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def empty(_area: object) -> tuple[list[Observation], dict[str, object]]:
        return [], {}

    monkeypatch.setattr(sensor_community, "fetch", empty)
    rc = main(
        [
            "fetch",
            "--source",
            "sensor-community",
            "--store",
            str(tmp_path / "store"),
            "--config",
            str(tmp_path / "net.yaml"),
            "--web",
            str(tmp_path / "web"),
        ]
    )
    assert rc == 1
    # The empty-result message steers a user to where coverage is dense.
    assert "Europe" in capsys.readouterr().err


def test_fetch_sensor_community_routes_and_stores(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    nodes: dict[str, tuple[str, float, float, str]] = {"sc-1": ("Sensor 1", 48.7758, 9.1829, "")}

    def fake(_area: object) -> tuple[list[Observation], dict[str, tuple[str, float, float, str]]]:
        return _real_temp("sc-1", source=SOURCE_SENSOR_COMMUNITY), nodes

    monkeypatch.setattr(sensor_community, "fetch", fake)
    cfg = tmp_path / "net.yaml"
    rc = main(
        [
            "fetch",
            "--source",
            "sensor-community",
            "--store",
            str(tmp_path / "store"),
            "--config",
            str(cfg),
            "--web",
            str(tmp_path / "web"),
        ]
    )
    assert rc == 0
    assert any(n.node_id == "sc-1" for n in load_config(str(cfg)).nodes)
    terms = json.loads((tmp_path / "store" / "source-metadata.json").read_text(encoding="utf-8"))
    assert terms["license"] == sensor_community.LICENSE


# -- fetch --accumulate (EXP-01: the demo store persists between runs) -------


def test_fetch_accumulate_keeps_prior_observations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without --accumulate a second fetch wipes the first; with it, both survive (the store key
    ``(node_id, timestamp, parameter, source, calibration)`` plus INSERT OR IGNORE make this
    idempotent)."""
    node_id = openmeteo.CALIFORNIA[0].node_id
    store = tmp_path / "store"
    cfg = tmp_path / "net.yaml"
    web = tmp_path / "web"

    def first(*_a: object, **_k: object) -> list[Observation]:
        return [
            make_obs(
                node_id=node_id,
                timestamp="2026-06-01T00:00:00Z",
                source=SOURCE_OPENMETEO,
                calibration=RAW,
            )
        ]

    def second(*_a: object, **_k: object) -> list[Observation]:
        return [
            make_obs(
                node_id=node_id,
                timestamp="2026-06-02T00:00:00Z",
                source=SOURCE_OPENMETEO,
                calibration=RAW,
            )
        ]

    monkeypatch.setattr(openmeteo, "fetch", first)
    rc = main(
        [
            "fetch",
            "--source",
            "openmeteo",
            "--store",
            str(store),
            "--config",
            str(cfg),
            "--web",
            str(web),
            "--accumulate",
        ]
    )
    assert rc == 0

    monkeypatch.setattr(openmeteo, "fetch", second)
    rc = main(
        [
            "fetch",
            "--source",
            "openmeteo",
            "--store",
            str(store),
            "--config",
            str(cfg),
            "--web",
            str(web),
            "--accumulate",
        ]
    )
    assert rc == 0

    with open_store(store) as opened:
        timestamps = {o.timestamp for o in opened.all() if o.node_id == node_id}
    assert timestamps == {"2026-06-01T00:00:00Z", "2026-06-02T00:00:00Z"}


def test_fetch_openaq_accumulate_retains_historical_license_periods(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = tmp_path / "store"
    cfg = tmp_path / "net.yaml"
    web = tmp_path / "web"
    args = [
        "fetch",
        "--source",
        "openaq",
        "--api-key",
        "test-key",
        "--store",
        str(store),
        "--config",
        str(cfg),
        "--web",
        str(web),
        "--accumulate",
    ]

    def day1(
        *_args: object, **kwargs: object
    ) -> tuple[list[Observation], dict[str, tuple[str, float, float]]]:
        ledger = kwargs.get("license_ledger")
        assert isinstance(ledger, dict)
        ledger.update(
            _openaq_ledger(
                1,
                fetched_at="2026-06-01T12:00:00Z",
                license_id=1,
                license_name="Terms A",
                valid_from="2026-06-01",
                valid_to="2026-06-01",
            )
        )
        return [
            make_obs(node_id="oaq-1", timestamp="2026-06-01T12:00:00Z", source=SOURCE_OPENAQ)
        ], {"oaq-1": ("Site 1", 38.58, -121.49)}

    def day2(
        *_args: object, **kwargs: object
    ) -> tuple[list[Observation], dict[str, tuple[str, float, float]]]:
        ledger = kwargs.get("license_ledger")
        assert isinstance(ledger, dict)
        ledger.update(
            _openaq_ledger(
                1,
                fetched_at="2026-06-02T12:00:00Z",
                license_id=2,
                license_name="Terms B",
                valid_from="2026-06-02",
            )
        )
        return [
            make_obs(node_id="oaq-1", timestamp="2026-06-02T12:00:00Z", source=SOURCE_OPENAQ)
        ], {"oaq-1": ("Site 1", 38.58, -121.49)}

    monkeypatch.setattr(openaq, "fetch", day1)
    assert main(args) == 0
    monkeypatch.setattr(openaq, "fetch", day2)
    assert main(args) == 0

    with open_store(store) as opened:
        observations = list(opened.all())
    assert {observation.timestamp for observation in observations} == {
        "2026-06-01T12:00:00Z",
        "2026-06-02T12:00:00Z",
    }
    ledger = json.loads((store / "source-license-ledger.json").read_text(encoding="utf-8"))
    assert {entry["license_id"] for entry in ledger["entries"]} == {1, 2}
    assert openaq.validate_license_ledger(ledger, observations=observations)

    capsys.readouterr()
    assert (
        main(
            [
                "publish",
                "--store",
                str(store),
                "--config",
                str(cfg),
                "--web",
                str(web),
                "--cooling-centers",
                str(tmp_path / "missing.geojson"),
            ]
        )
        == 0
    )
    rows = list(csv.DictReader((web / "export.csv").read_text(encoding="utf-8").splitlines()))
    by_time = {row["timestamp"]: row for row in rows}
    assert "Terms A" in by_time["2026-06-01T12:00:00Z"]["data_license"]
    assert "Terms B" not in by_time["2026-06-01T12:00:00Z"]["data_license"]
    assert "Terms B" in by_time["2026-06-02T12:00:00Z"]["data_license"]
    assert "Terms A" not in by_time["2026-06-02T12:00:00Z"]["data_license"]


def test_fetch_accumulate_rejects_malformed_old_ledger_without_mutation(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = tmp_path / "store"
    cfg = tmp_path / "net.yaml"
    web = tmp_path / "web"
    args = [
        "fetch",
        "--source",
        "openaq",
        "--api-key",
        "test-key",
        "--store",
        str(store),
        "--config",
        str(cfg),
        "--web",
        str(web),
        "--accumulate",
    ]

    def fetched(
        *_args: object, **kwargs: object
    ) -> tuple[list[Observation], dict[str, tuple[str, float, float]]]:
        ledger = kwargs.get("license_ledger")
        assert isinstance(ledger, dict)
        ledger.update(_openaq_ledger(1, fetched_at="2026-06-01T12:00:00Z"))
        return [
            make_obs(node_id="oaq-1", timestamp="2026-06-01T12:00:00Z", source=SOURCE_OPENAQ)
        ], {"oaq-1": ("Site 1", 38.58, -121.49)}

    monkeypatch.setattr(openaq, "fetch", fetched)
    assert main(args) == 0
    ledger_path = store / "source-license-ledger.json"
    ledger_path.write_text('{"schema_version":1,"entries":[]}', encoding="utf-8")
    before = _tree_bytes(cfg, store, web)

    capsys.readouterr()
    assert main(args) == 1
    assert "source provenance is invalid" in capsys.readouterr().err
    assert _tree_bytes(cfg, store, web) == before


def test_fetch_accumulate_rejects_cross_source_without_mutation(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = tmp_path / "store"
    cfg = tmp_path / "net.yaml"
    web = tmp_path / "web"
    common = ["--store", str(store), "--config", str(cfg), "--web", str(web), "--accumulate"]
    node_id = openmeteo.CALIFORNIA[0].node_id
    monkeypatch.setattr(
        openmeteo,
        "fetch",
        lambda *_a, **_k: _real_temp(node_id, source=SOURCE_OPENMETEO),
    )
    assert main(["fetch", "--source", "openmeteo", *common]) == 0
    before = _tree_bytes(cfg, store, web)

    monkeypatch.setattr(
        sensor_community,
        "fetch",
        lambda _area: (
            _real_temp("sc-1", source=SOURCE_SENSOR_COMMUNITY),
            {"sc-1": ("Sensor 1", 48.7758, 9.1829, "")},
        ),
    )
    capsys.readouterr()
    assert main(["fetch", "--source", "sensor-community", *common]) == 1
    assert "cannot mix sources" in capsys.readouterr().err
    assert _tree_bytes(cfg, store, web) == before


def test_fetch_accumulate_rejects_same_source_term_drift_without_mutation(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = tmp_path / "store"
    cfg = tmp_path / "net.yaml"
    web = tmp_path / "web"
    node_id = openmeteo.CALIFORNIA[0].node_id
    args = [
        "fetch",
        "--source",
        "openmeteo",
        "--store",
        str(store),
        "--config",
        str(cfg),
        "--web",
        str(web),
        "--accumulate",
    ]
    monkeypatch.setattr(
        openmeteo,
        "fetch",
        lambda *_a, **_k: _real_temp(node_id, source=SOURCE_OPENMETEO),
    )
    assert main(args) == 0
    before = _tree_bytes(cfg, store, web)

    monkeypatch.setattr(openmeteo, "ATTRIBUTION", "changed attribution")
    capsys.readouterr()
    assert main(args) == 1
    assert "source provenance is invalid" in capsys.readouterr().err
    assert _tree_bytes(cfg, store, web) == before


def test_rejected_fetch_rolls_back_legacy_migration_and_digest_rewrite(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = tmp_path / "store"
    store.mkdir()
    db_path = store / "observations.db"
    connection = sqlite3.connect(db_path)
    connection.executescript(
        """
        CREATE TABLE observations (
            node_id TEXT NOT NULL, timestamp TEXT NOT NULL, parameter TEXT NOT NULL,
            value REAL NOT NULL, unit TEXT NOT NULL, calibration TEXT NOT NULL,
            qc TEXT NOT NULL, uncertainty REAL, content_hash TEXT NOT NULL,
            PRIMARY KEY (node_id, timestamp, parameter, calibration)
        );
        """
    )
    node_id = openmeteo.CALIFORNIA[0].node_id
    connection.execute(
        "INSERT INTO observations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            node_id,
            "2026-06-01T00:00:00Z",
            "temp_c",
            25.0,
            "degC",
            "copernicus-cams",
            "ok",
            None,
            "legacy-hash",
        ),
    )
    connection.commit()
    connection.close()
    snapshot.write_source_metadata(
        store,
        source="Copernicus CAMS via Open-Meteo",
        license=openmeteo.LICENSE,
        attribution=openmeteo.ATTRIBUTION,
        license_url=openmeteo.LICENSE_URL,
        recorded_at="2026-07-16T12:00:00Z",
    )
    (store / "digests.jsonl").write_text('{"head":"legacy"}\n', encoding="utf-8")
    cfg = tmp_path / "net.yaml"
    web = tmp_path / "web"
    before = _tree_bytes(cfg, store, web)

    monkeypatch.setattr(
        openmeteo,
        "fetch",
        lambda *_a, **_k: _real_temp(node_id, source=SOURCE_OPENMETEO),
    )
    monkeypatch.setattr(openmeteo, "ATTRIBUTION", "changed attribution")
    capsys.readouterr()

    assert (
        main(
            [
                "fetch",
                "--source",
                "openmeteo",
                "--store",
                str(store),
                "--config",
                str(cfg),
                "--web",
                str(web),
                "--accumulate",
            ]
        )
        == 1
    )
    assert "source provenance is invalid" in capsys.readouterr().err
    assert _tree_bytes(cfg, store, web) == before


@pytest.mark.parametrize("failure_point", ["config", "database", "web"])
def test_fetch_post_validation_failure_restores_every_artifact(
    failure_point: str,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = tmp_path / "store"
    cfg = tmp_path / "net.yaml"
    web = tmp_path / "web"
    web.mkdir()
    node_id = openmeteo.CALIFORNIA[0].node_id
    args = [
        "fetch",
        "--source",
        "openmeteo",
        "--store",
        str(store),
        "--config",
        str(cfg),
        "--web",
        str(web),
        "--accumulate",
    ]
    monkeypatch.setattr(
        openmeteo,
        "fetch",
        lambda *_a, **_k: [
            make_obs(
                node_id=node_id,
                timestamp="2026-06-01T00:00:00Z",
                source=SOURCE_OPENMETEO,
            )
        ],
    )
    assert main(args) == 0
    before = _tree_bytes(cfg, store, web)
    monkeypatch.setattr(
        openmeteo,
        "fetch",
        lambda *_a, **_k: [
            make_obs(
                node_id=node_id,
                timestamp="2026-06-02T00:00:00Z",
                source=SOURCE_OPENMETEO,
            )
        ],
    )

    if failure_point == "config":
        original_write_text = Path.write_text

        def fail_config(
            self: Path,
            data: str,
            encoding: str | None = None,
            errors: str | None = None,
            newline: str | None = None,
        ) -> int:
            if self.resolve() == cfg.resolve():
                raise OSError("injected config write failure")
            return original_write_text(
                self, data, encoding=encoding, errors=errors, newline=newline
            )

        monkeypatch.setattr(Path, "write_text", fail_config)
    elif failure_point == "database":
        original_db_write = SqliteStore.write

        def fail_database(self: SqliteStore, observations: Iterable[Observation]) -> WriteResult:
            original_db_write(self, observations)
            raise OSError("injected database failure after commit")

        monkeypatch.setattr(SqliteStore, "write", fail_database)
    else:

        def fail_web(*_args: object, **_kwargs: object) -> None:
            raise OSError("injected web artifact failure")

        monkeypatch.setattr("swelter.cli._write_web_alerts", fail_web)

    capsys.readouterr()
    assert main(args) == 1
    assert "restored the prior store and artifacts" in capsys.readouterr().err
    assert _tree_bytes(cfg, store, web) == before


def test_fetch_rejects_malformed_generated_network_without_mutation(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = tmp_path / "store"
    cfg = tmp_path / "net.yaml"
    web = tmp_path / "web"
    node_id = openmeteo.CALIFORNIA[0].node_id
    args = [
        "fetch",
        "--source",
        "openmeteo",
        "--store",
        str(store),
        "--config",
        str(cfg),
        "--web",
        str(web),
        "--accumulate",
    ]
    monkeypatch.setattr(
        openmeteo,
        "fetch",
        lambda *_a, **_k: _real_temp(node_id, source=SOURCE_OPENMETEO),
    )
    assert main(args) == 0
    before = _tree_bytes(cfg, store, web)

    monkeypatch.setattr(openmeteo, "network_doc", lambda *_a, **_k: {"nodes": "invalid"})
    capsys.readouterr()
    assert main(args) == 1
    assert "network config is invalid" in capsys.readouterr().err
    assert _tree_bytes(cfg, store, web) == before


def test_fetch_without_accumulate_wipes_prior_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The default (no --accumulate) behaviour is unchanged: each fetch is a fresh snapshot."""
    node_id = openmeteo.CALIFORNIA[0].node_id
    store = tmp_path / "store"
    cfg = tmp_path / "net.yaml"
    web = tmp_path / "web"

    def first(*_a: object, **_k: object) -> list[Observation]:
        return [
            make_obs(
                node_id=node_id,
                timestamp="2026-06-01T00:00:00Z",
                source=SOURCE_OPENMETEO,
                calibration=RAW,
            )
        ]

    def second(*_a: object, **_k: object) -> list[Observation]:
        return [
            make_obs(
                node_id=node_id,
                timestamp="2026-06-02T00:00:00Z",
                source=SOURCE_OPENMETEO,
                calibration=RAW,
            )
        ]

    monkeypatch.setattr(openmeteo, "fetch", first)
    assert (
        main(
            [
                "fetch",
                "--source",
                "openmeteo",
                "--store",
                str(store),
                "--config",
                str(cfg),
                "--web",
                str(web),
            ]
        )
        == 0
    )
    monkeypatch.setattr(openmeteo, "fetch", second)
    assert (
        main(
            [
                "fetch",
                "--source",
                "openmeteo",
                "--store",
                str(store),
                "--config",
                str(cfg),
                "--web",
                str(web),
            ]
        )
        == 0
    )

    with open_store(store) as opened:
        timestamps = {o.timestamp for o in opened.all() if o.node_id == node_id}
    assert timestamps == {"2026-06-02T00:00:00Z"}


def test_fetch_accumulate_merges_network_nodes_that_come_and_go(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A node missing from today's discovery keeps its prior config entry under --accumulate, so
    its history in the store stays resolvable by ``aggregate`` (the Shape's "nodes that come and
    go" reconciliation) — while a node seen again gets its entry refreshed from today's fetch."""
    nodes_day1 = {"sc-1": ("Sensor 1", 48.7758, 9.1829, ""), "sc-2": ("Sensor 2", 48.80, 9.20, "")}
    nodes_day2 = {"sc-1": ("Sensor 1 (moved)", 48.7760, 9.1830, "")}  # sc-2 dropped out today

    def day1(_area: object) -> tuple[list[Observation], dict[str, tuple[str, float, float, str]]]:
        return [
            make_obs(node_id="sc-1", source=SOURCE_SENSOR_COMMUNITY),
            make_obs(node_id="sc-2", source=SOURCE_SENSOR_COMMUNITY),
        ], nodes_day1

    def day2(_area: object) -> tuple[list[Observation], dict[str, tuple[str, float, float, str]]]:
        return [make_obs(node_id="sc-1", source=SOURCE_SENSOR_COMMUNITY)], nodes_day2

    cfg = tmp_path / "net.yaml"
    store = tmp_path / "store"
    web = tmp_path / "web"
    args = [
        "fetch",
        "--source",
        "sensor-community",
        "--store",
        str(store),
        "--config",
        str(cfg),
        "--web",
        str(web),
        "--accumulate",
    ]

    monkeypatch.setattr(sensor_community, "fetch", day1)
    assert main(args) == 0
    monkeypatch.setattr(sensor_community, "fetch", day2)
    assert main(args) == 0

    merged = load_config(str(cfg))
    node_ids = {n.node_id for n in merged.nodes}
    assert node_ids == {"sc-1", "sc-2"}, "sc-2 dropped out today but keeps its prior entry"
    refreshed = next(n for n in merged.nodes if n.node_id == "sc-1")
    assert refreshed.label == "Sensor 1 (moved)", "sc-1 was seen again, so today's data wins"


def test_fetch_accumulate_does_not_restore_nodes_from_an_older_scope(tmp_path: Path) -> None:
    config_path = tmp_path / "net.yaml"
    config_path.write_text(
        json.dumps(
            {
                "name": "old bbox-based OpenAQ network",
                "nodes": [
                    {
                        "node_id": "oaq-yuma",
                        "label": "Yuma",
                        "lat": 32.6927,
                        "lon": -114.6277,
                        "location": "precise",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    today = openaq.network_doc("California", {"oaq-sac": ("Sacramento", 38.5816, -121.4944)})
    migrated = _merge_network_doc(config_path, today)
    assert [node["node_id"] for node in migrated["nodes"]] == ["oaq-sac"]

    # Once both documents carry the same boundary id, normal accumulation still retains a
    # California node that is absent from today's discovery.
    config_path.write_text(json.dumps(migrated), encoding="utf-8")
    tomorrow = openaq.network_doc("California", {"oaq-la": ("Los Angeles", 34.0522, -118.2437)})
    accumulated = _merge_network_doc(config_path, tomorrow)
    assert {node["node_id"] for node in accumulated["nodes"]} == {"oaq-sac", "oaq-la"}


# -- the static-payload cap (keeps the committed sample light) ---------------


def test_web_sample_cap_drops_older_buckets(demo_store: Path, tmp_path: Path) -> None:
    """``_write_web_sample`` caps the offline sample to the newest buckets under ``max_cells``."""
    web = tmp_path / "web"
    web.mkdir()
    store = open_store(demo_store)
    try:
        surface = aggregate.aggregate(store.all(), load_config(NETWORK))
    finally:
        store.close()
    all_buckets = {c.bucket for c in surface.cells}
    assert len(all_buckets) > 1, "demo spans many hourly buckets"

    _write_web_sample(web, surface, attribution="x", max_cells=1)
    sample = json.loads((web / "sample-surface.json").read_text(encoding="utf-8"))
    # With max_cells=1 only the single newest bucket survives the cap.
    assert len(sample["buckets"]) < len(all_buckets)
    assert sample["buckets"] == [max(all_buckets)]
    assert sample["rights"]["attribution"] == "x"
    assert sample["rights"]["links"] == [{"rel": "license", "href": "DATA-LICENSE"}]
