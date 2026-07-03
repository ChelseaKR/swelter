"""The published data dictionary must never drift from the constants it is generated from."""

from __future__ import annotations

import json
import threading
import urllib.request
from pathlib import Path
from typing import Any

import pytest

from swelter import export
from swelter.config import NetworkConfig, NodeConfig
from swelter.dictionary import DATA_SCHEMA_VERSION, build_data_dictionary
from swelter.models import (
    PARAMETERS,
    QC_FLATLINE,
    QC_MISSING,
    QC_OK,
    QC_RANGE,
    QC_REJECTED,
    QC_SPIKE,
)
from swelter.server import ServerContext, make_server
from swelter.store import SqliteStore


def test_data_schema_version_is_a_positive_int() -> None:
    assert isinstance(DATA_SCHEMA_VERSION, int)
    assert DATA_SCHEMA_VERSION > 0


def test_parameters_match_the_registry_exactly() -> None:
    doc = build_data_dictionary()
    by_name = {p["name"]: p for p in doc["parameters"]}
    assert set(by_name) == set(PARAMETERS)
    for name, param in PARAMETERS.items():
        entry = by_name[name]
        assert entry["unit"] == param.unit
        assert entry["valid_min"] == param.valid_min
        assert entry["valid_max"] == param.valid_max


def test_csv_columns_equal_export_csv_fields() -> None:
    # Drift guard: the dictionary must import export._CSV_FIELDS, never restate it.
    doc = build_data_dictionary()
    assert doc["csv_columns"] == list(export._CSV_FIELDS)


def test_qc_verdicts_cover_all_five_constants_and_flag_rejected() -> None:
    doc = build_data_dictionary()
    by_name = {v["name"]: v for v in doc["qc_verdicts"]}
    assert set(by_name) == {QC_OK, QC_RANGE, QC_SPIKE, QC_FLATLINE, QC_MISSING}
    for name, entry in by_name.items():
        assert entry["rejected"] == (name in QC_REJECTED)
    assert by_name[QC_OK]["rejected"] is False


def test_dictionary_carries_version_signals_and_license() -> None:
    doc = build_data_dictionary()
    assert doc["data_schema_version"] == DATA_SCHEMA_VERSION
    assert doc["generated_from"] == "swelter"
    assert isinstance(doc["package_version"], str) and doc["package_version"]
    assert "license" in doc


def test_observation_fields_cover_the_dataclass() -> None:
    doc = build_data_dictionary()
    names = {f["name"] for f in doc["observation_fields"]}
    assert names == {
        "node_id",
        "timestamp",
        "parameter",
        "value",
        "unit",
        "calibration",
        "qc",
        "uncertainty",
        "trustworthy",
    }


def test_calibration_block_names_the_raw_sentinel() -> None:
    doc = build_data_dictionary()
    calibration: Any = doc["calibration"]
    assert calibration["raw_sentinel"] == "raw"
    assert "{node_id}" in calibration["correction_version_format"]


@pytest.fixture
def base_url(tmp_path: Path):  # type: ignore[no-untyped-def]
    db = SqliteStore(tmp_path / "obs.db")
    config = NetworkConfig(nodes=(NodeConfig(node_id="node-01", lat=38.58, lon=-121.49),))
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text('<!doctype html><title>swelter</title>', "utf-8")
    ctx = ServerContext(store=db, config=config, web_dir=web)
    httpd = make_server(ctx, "127.0.0.1", 0)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        httpd.shutdown()
        httpd.server_close()
        db.close()


def test_schema_endpoint_returns_the_dictionary(base_url: str) -> None:
    with urllib.request.urlopen(f"{base_url}/api/schema.json", timeout=5) as response:  # noqa: S310
        status = response.status
        content_type = response.headers.get("Content-Type")
        body = response.read().decode("utf-8")
    assert status == 200
    assert content_type is not None and "application/json" in content_type
    payload: Any = json.loads(body)
    assert payload["data_schema_version"] == DATA_SCHEMA_VERSION


def test_service_document_advertises_data_schema_version(base_url: str) -> None:
    with urllib.request.urlopen(f"{base_url}/v1.1", timeout=5) as response:  # noqa: S310
        payload: Any = json.loads(response.read().decode("utf-8"))
    assert payload["serverSettings"]["dataSchemaVersion"] == DATA_SCHEMA_VERSION
