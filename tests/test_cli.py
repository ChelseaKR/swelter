"""End-to-end CLI: the demo replay and the export path a community actually runs."""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import pytest

from swelter import ingest_server
from swelter.cli import main
from swelter.models import parse_timestamp
from swelter.store import open_store, store_paths

from .conftest import ROOT


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["version"]) == 0
    assert "swelter" in capsys.readouterr().out


def test_crosswalk_csv(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["crosswalk"]) == 0
    out = capsys.readouterr().out
    assert "swelter_param" in out.splitlines()[0]
    assert "pm25_ugm3" in out


def test_crosswalk_json(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["crosswalk", "--format", "json"]) == 0
    rows = json.loads(capsys.readouterr().out)
    heat_index = next(row for row in rows if row["swelter_param"] == "heat_index_c")
    assert heat_index["openaq_param"] is None


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
    es_atom = (web / "alerts.es.xml").read_text(encoding="utf-8")
    assert es_atom.startswith("<?xml")
    assert 'xml:lang="es"' in es_atom
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


# -- ingest-serve / node-key (the authenticated node write path) -------------------------------
#
# `cmd_ingest_serve` and `cmd_node_key` (src/swelter/cli.py) had zero test references before
# this — a gap the FIX-01 code review caught. `cmd_ingest_serve` runs a blocking listener
# (`ingest_server.serve()` calls `serve_forever()`), so its error paths are driven directly
# through `main()`, and its happy path is driven by stubbing the blocking call the same way
# `test_cli_flows.py` already stubs `cmd_serve`'s `serve()`.


def test_ingest_serve_missing_keys_file_is_a_clean_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = main(
        [
            "ingest-serve",
            "--keys",
            str(tmp_path / "no-such-keys.yaml"),
            "--store",
            str(tmp_path / "store"),
        ]
    )
    assert rc == 1
    assert "not found" in capsys.readouterr().err


def test_ingest_serve_empty_keys_file_is_a_clean_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    keys_file = tmp_path / "node-keys.yaml"
    keys_file.write_text("")  # exists, parses, but issues no node keys
    rc = main(["ingest-serve", "--keys", str(keys_file), "--store", str(tmp_path / "store")])
    assert rc == 1
    assert "holds no node keys" in capsys.readouterr().err


def test_node_key_creates_a_key_ingest_serve_actually_authenticates_against(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`swelter node-key` issues a key; `swelter ingest-serve` must load and use that exact key.

    Two things are checked: (1) `cmd_ingest_serve` itself wires the CLI-issued keys file into
    the listener's `IngestServerContext` correctly (driven through `main()`, with the blocking
    `ingest_server.serve()` call stubbed so the test doesn't hang — the same pattern
    `test_cli_flows.py` uses for `cmd_serve`); and (2) the CLI-issued key is not just present in
    the context object but actually usable — a real listener built from it accepts a request
    signed with the printed key and refuses one signed with a wrong key.
    """
    keys_file = tmp_path / "node-keys.yaml"
    store_dir = tmp_path / "store"

    assert main(["node-key", "node-1", "--keys", str(keys_file)]) == 0
    out = capsys.readouterr()
    issued_key = out.out.strip()
    assert len(issued_key) == 64 and all(c in "0123456789abcdef" for c in issued_key)
    assert "issued ingest key for node-1" in out.err

    # (1) cmd_ingest_serve loads that exact key into the context it hands the listener.
    captured: list[ingest_server.IngestServerContext] = []

    def fake_serve(
        ctx: ingest_server.IngestServerContext, host: str = "127.0.0.1", port: int = 8100
    ) -> None:
        captured.append(ctx)

    monkeypatch.setattr("swelter.ingest_server.serve", fake_serve)
    rc = main(
        [
            "ingest-serve",
            "--keys",
            str(keys_file),
            "--store",
            str(store_dir),
            "--skew",
            "60",
        ]
    )
    assert rc == 0
    assert len(captured) == 1
    ctx = captured[0]
    assert ctx.keys["node-1"].hex() == issued_key
    assert ctx.skew_s == 60
    assert ctx.quarantine_path == store_paths(store_dir)["quarantine"]

    # (2) that key is genuinely usable: build a real listener the same way ingest-serve does
    # (make_server from an IngestServerContext loaded straight from the CLI-issued keys file)
    # and drive it with a real HTTP POST signed with the printed key. Pin the clock so the
    # replay window is deterministic regardless of when this test happens to run. cmd_ingest_serve
    # closed ctx.store in its `finally` the moment the stubbed serve() returned (correct cleanup
    # behavior on its part), so reopen a fresh handle onto the same on-disk store for this check.
    timestamp = "2026-07-01T12:00:00Z"
    ctx.now = lambda: parse_timestamp(timestamp).timestamp()
    ctx.store = open_store(store_dir)
    httpd = ingest_server.make_server(ctx, "127.0.0.1", 0)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        body = json.dumps(
            {
                "node_id": "node-1",
                "timestamp": "2026-07-01T11:55:00Z",
                "readings": {"pm25_ugm3": 5.0},
            }
        ).encode()
        good_sig = ingest_server.sign(bytes.fromhex(issued_key), "node-1", timestamp, body)

        status, payload = _ingest_post(
            f"http://127.0.0.1:{port}{ingest_server.INGEST_ROUTE}",
            body,
            {
                ingest_server.NODE_HEADER: "node-1",
                ingest_server.TIMESTAMP_HEADER: timestamp,
                ingest_server.SIGNATURE_HEADER: good_sig,
            },
        )
        assert status == 200
        assert payload["written"] == 1

        bad_sig = ingest_server.sign(bytes(32), "node-1", timestamp, body)  # wrong key
        status, payload = _ingest_post(
            f"http://127.0.0.1:{port}{ingest_server.INGEST_ROUTE}",
            body,
            {
                ingest_server.NODE_HEADER: "node-1",
                ingest_server.TIMESTAMP_HEADER: timestamp,
                ingest_server.SIGNATURE_HEADER: bad_sig,
            },
        )
        assert status == 401
    finally:
        httpd.shutdown()
        httpd.server_close()
        ctx.store.close()


def _ingest_post(url: str, body: bytes, headers: dict[str, str]) -> tuple[int, dict[str, Any]]:
    request = urllib.request.Request(  # noqa: S310 (localhost)
        url, data=body, headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:  # noqa: S310 (localhost)
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))
