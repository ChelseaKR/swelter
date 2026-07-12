"""Structured logging + run manifests: JSON-lines events, manifest schema, counter correctness,
and determinism of the manifest the demo replay fixture produces (hard rule #1: no PII/IPs)."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from swelter import __version__, obs
from swelter.cli import main

from .conftest import DEMO, ROOT

NETWORK = str(ROOT / "network.yaml")

_MANIFEST_COUNTERS = {
    "payloads_accepted",
    "payloads_quarantined",
    "corrections_applied",
    "corrections_skipped_stale",
    "cells_built",
    "cells_provisional",
}


# -- JsonLinesFormatter --------------------------------------------------------------------


def test_json_lines_formatter_emits_one_parseable_object_per_line() -> None:
    record = logging.LogRecord(
        name="swelter",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="payloads ingested",
        args=(),
        exc_info=None,
    )
    record.stage = "ingest"
    record.counters = {"payloads_accepted": 3, "payloads_quarantined": 1}
    line = obs.JsonLinesFormatter().format(record)
    payload = json.loads(line)  # must parse as a single JSON object
    assert payload["level"] == "info"
    assert payload["stage"] == "ingest"
    assert payload["event"] == "payloads ingested"
    assert payload["payloads_accepted"] == 3
    assert payload["payloads_quarantined"] == 1
    assert "ts" in payload


def test_json_lines_formatter_scrubs_person_shaped_and_ip_fields() -> None:
    record = logging.LogRecord(
        name="swelter",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="request",
        args=(),
        exc_info=None,
    )
    record.stage = "server"
    record.counters = {
        "status": 200,
        "ms": 4.2,
        "client_ip": "203.0.113.5",
        "remote_addr": "203.0.113.5",
        "email": "someone@example.com",
        "node_id": "node-01",  # a device id, not a person — must survive the scrub
    }
    payload = json.loads(obs.JsonLinesFormatter().format(record))
    assert payload["status"] == 200
    assert payload["ms"] == 4.2
    assert payload["node_id"] == "node-01"
    for forbidden in ("client_ip", "remote_addr", "email", "ip", "address"):
        assert forbidden not in payload


def test_configure_json_logging_is_idempotent_no_duplicate_handlers() -> None:
    logger = obs.configure_json_logging()
    obs.configure_json_logging()
    obs.configure_json_logging()
    json_handlers = [h for h in logger.handlers if isinstance(h.formatter, obs.JsonLinesFormatter)]
    assert len(json_handlers) == 1


def test_log_event_emits_valid_json_line(capsys: pytest.CaptureFixture[str]) -> None:
    obs.configure_json_logging()
    obs.log_event("ingest", "payloads ingested", payloads_accepted=2, payloads_quarantined=0)
    err = capsys.readouterr().err
    lines = [line for line in err.splitlines() if line.strip()]
    assert lines, "expected at least one JSON line on stderr"
    payload = json.loads(lines[-1])
    assert payload["stage"] == "ingest"
    assert payload["event"] == "payloads ingested"
    assert payload["payloads_accepted"] == 2


# -- RunManifest / write_manifest / read_manifest ------------------------------------------


def test_run_manifest_record_increments_named_counters_and_logs() -> None:
    manifest = obs.RunManifest()
    manifest.record("ingest", "payloads ingested", payloads_accepted=5, payloads_quarantined=2)
    manifest.record("ingest", "more payloads", payloads_accepted=1)
    assert manifest.payloads_accepted == 6
    assert manifest.payloads_quarantined == 2
    assert manifest.corrections_applied == 0  # untouched counters stay at zero
    assert manifest.stages == ["ingest"]  # recorded once even though .record() ran twice


def test_run_manifest_record_rejects_unknown_counter_name() -> None:
    manifest = obs.RunManifest()
    with pytest.raises(ValueError):
        manifest.record("ingest", "bad event", not_a_real_counter=1)


def test_run_manifest_to_dict_schema() -> None:
    manifest = obs.RunManifest()
    manifest.record("ingest", "payloads ingested", payloads_accepted=3)
    manifest.record("aggregate", "surface built", cells_built=10, cells_provisional=4)
    manifest.finish()
    payload = manifest.to_dict()

    assert set(payload) == {
        "run_id",
        "started_at",
        "finished_at",
        "pipeline_versions",
        "stages",
        "counters",
    }
    assert payload["run_id"] == manifest.run_id
    assert payload["finished_at"] is not None
    assert payload["pipeline_versions"] == {"swelter": __version__}
    assert payload["stages"] == ["ingest", "aggregate"]
    assert set(payload["counters"]) == _MANIFEST_COUNTERS
    assert payload["counters"]["payloads_accepted"] == 3
    assert payload["counters"]["cells_built"] == 10
    assert payload["counters"]["cells_provisional"] == 4
    assert payload["counters"]["corrections_applied"] == 0


def test_run_manifest_no_person_shaped_data_or_ips() -> None:
    """Hard rule 1: nothing in a manifest is a name, an address, or a network address."""
    manifest = obs.RunManifest()
    manifest.record("ingest", "payloads ingested", payloads_accepted=1)
    manifest.finish()
    blob = json.dumps(manifest.to_dict())
    for forbidden in ("ip_address", "email", "phone", "password", "@", "lat", "lon"):
        assert forbidden not in blob.lower()


def test_write_manifest_creates_store_dir_and_emits_valid_json(tmp_path: Path) -> None:
    store_dir = tmp_path / "fresh-store"  # deliberately not pre-created
    manifest = obs.RunManifest()
    manifest.record("aggregate", "surface built", cells_built=1, cells_provisional=0)
    manifest.finish()

    path = obs.write_manifest(store_dir, manifest)

    assert path == store_dir / "run-manifest.json"
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert on_disk == manifest.to_dict()


def test_read_manifest_round_trips(tmp_path: Path) -> None:
    manifest = obs.RunManifest()
    manifest.record("ingest", "payloads ingested", payloads_accepted=7)
    manifest.finish()
    obs.write_manifest(tmp_path, manifest)

    read_back = obs.read_manifest(tmp_path)

    assert read_back is not None
    assert read_back["run_id"] == manifest.run_id
    assert read_back["counters"]["payloads_accepted"] == 7


def test_read_manifest_missing_is_none(tmp_path: Path) -> None:
    assert obs.read_manifest(tmp_path / "no-such-store") is None


def test_read_manifest_corrupt_json_is_none(tmp_path: Path) -> None:
    (tmp_path / "run-manifest.json").write_text("{not json", encoding="utf-8")
    assert obs.read_manifest(tmp_path) is None


# -- wired into the CLI: ingest / calibrate / aggregate / demo -----------------------------


def test_ingest_writes_a_run_manifest(tmp_path: Path) -> None:
    payloads = tmp_path / "in.jsonl"
    payloads.write_text(
        '{"node_id":"node-01","timestamp":"2026-06-01T00:00:00Z","temp_c":25.0}\n'
        '{"node_id":"node-01","timestamp":"bad-timestamp","temp_c":25.0}\n',
        encoding="utf-8",
    )
    store_dir = tmp_path / "store"
    assert main(["ingest", str(payloads), "--store", str(store_dir)]) == 0

    manifest = obs.read_manifest(store_dir)
    assert manifest is not None
    assert manifest["counters"]["payloads_accepted"] == 1
    assert manifest["counters"]["payloads_quarantined"] == 1
    assert manifest["stages"] == ["ingest"]


def test_aggregate_writes_a_run_manifest_matching_the_surface(tmp_path: Path) -> None:
    store_dir = tmp_path / "store"
    assert main(["demo", "--data", str(DEMO), "--store", str(store_dir), "--config", NETWORK]) == 0
    # demo already writes a manifest; re-run `aggregate` alone and check its own fresh one.
    assert main(["aggregate", "--store", str(store_dir), "--config", NETWORK]) == 0

    manifest = obs.read_manifest(store_dir)
    assert manifest is not None
    assert manifest["stages"] == ["aggregate"]
    assert manifest["counters"]["cells_built"] > 0
    assert manifest["counters"]["cells_provisional"] >= 0
    # untouched-by-this-invocation counters reset with the fresh manifest, not carried forward
    assert manifest["counters"]["payloads_accepted"] == 0


def _demo_manifest(tmp_path: Path, name: str) -> dict[str, object]:
    store_dir = tmp_path / name
    rc = main(["demo", "--data", str(DEMO), "--store", str(store_dir), "--config", NETWORK])
    assert rc == 0
    manifest = obs.read_manifest(store_dir)
    assert manifest is not None
    return manifest


def test_demo_replay_manifest_has_expected_schema_and_counters(tmp_path: Path) -> None:
    manifest = _demo_manifest(tmp_path, "store")
    assert set(manifest) == {
        "run_id",
        "started_at",
        "finished_at",
        "pipeline_versions",
        "stages",
        "counters",
    }
    assert manifest["stages"] == ["ingest", "calibrate", "aggregate"]
    counters = manifest["counters"]
    assert isinstance(counters, dict)
    assert set(counters) == _MANIFEST_COUNTERS
    assert counters["payloads_accepted"] > 0
    assert counters["cells_built"] > 0


def test_demo_replay_manifest_is_deterministic_excluding_timestamps_and_run_id(
    tmp_path: Path,
) -> None:
    """The 'Excellent looks like' bar: replaying the same recorded fixture twice must produce
    byte-identical counters and stage order — only the run id and timestamps may differ."""
    first = _demo_manifest(tmp_path, "store-a")
    second = _demo_manifest(tmp_path, "store-b")

    def _stable(m: dict[str, object]) -> dict[str, object]:
        return {k: v for k, v in m.items() if k not in ("run_id", "started_at", "finished_at")}

    assert _stable(first) == _stable(second)
    assert first["run_id"] != second["run_id"]  # uuid4 per run, not reused


def test_health_endpoint_names_the_run_that_built_the_surface(tmp_path: Path) -> None:
    from swelter.config import NetworkConfig, NodeConfig
    from swelter.server import ServerContext, make_server
    from swelter.store import SqliteStore

    store_dir = tmp_path / "store"
    assert main(["demo", "--data", str(DEMO), "--store", str(store_dir), "--config", NETWORK]) == 0
    manifest = obs.read_manifest(store_dir)
    assert manifest is not None

    db = SqliteStore(store_dir / "observations.db")
    config = NetworkConfig(nodes=(NodeConfig(node_id="node-01", lat=38.58, lon=-121.49),))
    web = tmp_path / "web"
    web.mkdir()
    ctx = ServerContext(store=db, config=config, web_dir=web, store_dir=store_dir)
    httpd = make_server(ctx, "127.0.0.1", 0)
    port = httpd.server_address[1]
    import threading
    import urllib.request

    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        with urllib.request.urlopen(  # noqa: S310 (localhost test server)
            f"http://127.0.0.1:{port}/api/health.json", timeout=5
        ) as response:
            body = json.loads(response.read().decode("utf-8"))
    finally:
        httpd.shutdown()
        httpd.server_close()
        db.close()

    assert body["run"]["run_id"] == manifest["run_id"]
    assert body["run"]["finished_at"] == manifest["finished_at"]
    assert body["run"]["counters"] == manifest["counters"]


def test_health_endpoint_omits_run_block_without_store_dir(tmp_path: Path) -> None:
    from swelter.config import NetworkConfig, NodeConfig
    from swelter.server import ServerContext, make_server
    from swelter.store import SqliteStore

    db = SqliteStore(tmp_path / "obs.db")
    config = NetworkConfig(nodes=(NodeConfig(node_id="node-01", lat=38.58, lon=-121.49),))
    web = tmp_path / "web"
    web.mkdir()
    ctx = ServerContext(store=db, config=config, web_dir=web)  # no store_dir
    httpd = make_server(ctx, "127.0.0.1", 0)
    port = httpd.server_address[1]
    import threading
    import urllib.request

    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        with urllib.request.urlopen(  # noqa: S310 (localhost test server)
            f"http://127.0.0.1:{port}/api/health.json", timeout=5
        ) as response:
            body = json.loads(response.read().decode("utf-8"))
    finally:
        httpd.shutdown()
        httpd.server_close()
        db.close()

    assert "run" not in body


# -- optional request logging (server.py, behind SWELTER_LOG_REQUESTS) ---------------------


def test_request_logging_off_by_default_emits_no_json_lines(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from swelter.config import NetworkConfig, NodeConfig
    from swelter.server import ServerContext, make_server
    from swelter.store import SqliteStore

    monkeypatch.delenv("SWELTER_LOG_REQUESTS", raising=False)
    db = SqliteStore(tmp_path / "obs.db")
    config = NetworkConfig(nodes=(NodeConfig(node_id="node-01", lat=38.58, lon=-121.49),))
    web = tmp_path / "web"
    web.mkdir()
    ctx = ServerContext(store=db, config=config, web_dir=web)
    httpd = make_server(ctx, "127.0.0.1", 0)
    port = httpd.server_address[1]
    import threading
    import urllib.request

    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        with urllib.request.urlopen(  # noqa: S310 (localhost test server)
            f"http://127.0.0.1:{port}/health", timeout=5
        ):
            pass
    finally:
        httpd.shutdown()
        httpd.server_close()
        db.close()

    err = capsys.readouterr().err
    assert err == ""


def test_request_logging_enabled_emits_method_path_status_ms_never_ip(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from swelter.config import NetworkConfig, NodeConfig
    from swelter.server import ServerContext, make_server
    from swelter.store import SqliteStore

    monkeypatch.setenv("SWELTER_LOG_REQUESTS", "1")
    db = SqliteStore(tmp_path / "obs.db")
    config = NetworkConfig(nodes=(NodeConfig(node_id="node-01", lat=38.58, lon=-121.49),))
    web = tmp_path / "web"
    web.mkdir()
    ctx = ServerContext(store=db, config=config, web_dir=web)
    httpd = make_server(ctx, "127.0.0.1", 0)
    port = httpd.server_address[1]
    import threading
    import urllib.request

    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        with urllib.request.urlopen(  # noqa: S310 (localhost test server)
            f"http://127.0.0.1:{port}/health", timeout=5
        ):
            pass
    finally:
        httpd.shutdown()
        httpd.server_close()
        db.close()
        obs.get_logger().handlers.clear()  # don't leak the handler into later tests

    lines = [line for line in capsys.readouterr().err.splitlines() if line.strip()]
    assert lines
    payload = json.loads(lines[-1])
    assert payload["stage"] == "server"
    assert payload["method"] == "GET"
    assert payload["path"] == "/health"
    assert payload["status"] == 200
    assert isinstance(payload["ms"], (int, float))
    assert "127.0.0.1" not in json.dumps(payload)  # never the client's address
