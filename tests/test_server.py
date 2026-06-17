"""The HTTP layer answers health, exports, and static files — and only ever GETs."""

from __future__ import annotations

import json
import threading
import urllib.request
from pathlib import Path
from typing import Any

import pytest

from swelter.config import NetworkConfig, NodeConfig
from swelter.server import ServerContext, make_server
from swelter.store import SqliteStore

from .conftest import make_obs


@pytest.fixture
def base_url(tmp_path: Path):  # type: ignore[no-untyped-def]
    db = SqliteStore(tmp_path / "obs.db")
    db.write([make_obs(parameter="pm25_ugm3", unit="ug/m3", value=12.0, calibration="v1")])
    config = NetworkConfig(nodes=(NodeConfig(node_id="node-01", lat=38.58, lon=-121.49),))
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text(
        '<!doctype html><html lang="en"><title>swelter</title>', "utf-8"
    )
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


def _get(url: str) -> tuple[int, str]:
    with urllib.request.urlopen(url, timeout=5) as response:  # noqa: S310 (localhost test server)
        return response.status, response.read().decode("utf-8")


def test_health(base_url: str) -> None:
    status, body = _get(f"{base_url}/health")
    payload: Any = json.loads(body)
    assert status == 200
    assert payload["status"] == "ok"


def test_export_csv(base_url: str) -> None:
    _, body = _get(f"{base_url}/export.csv")
    assert "node_id,timestamp" in body


def test_static_index(base_url: str) -> None:
    _, body = _get(f"{base_url}/")
    assert "<title>swelter</title>" in body


def test_surface_geojson(base_url: str) -> None:
    _, body = _get(f"{base_url}/api/surface.geojson")
    payload: Any = json.loads(body)
    assert payload["type"] == "FeatureCollection"


def test_writes_are_refused(base_url: str) -> None:
    request = urllib.request.Request(f"{base_url}/v1.1/Observations", method="POST", data=b"{}")
    try:
        urllib.request.urlopen(request, timeout=5)  # noqa: S310
        raised = False
    except urllib.error.HTTPError as exc:
        raised = exc.code == 405
    assert raised, "the public API must refuse writes"
