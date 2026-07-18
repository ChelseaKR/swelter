"""The HTTP layer answers health, exports, and static files — and only ever GETs."""

from __future__ import annotations

import http.client
import json
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from swelter import aggregate as aggregate_module
from swelter import snapshot
from swelter.config import NetworkConfig, NodeConfig
from swelter.server import ServerContext, _rights_link_header, make_server
from swelter.store import SqliteStore

from .conftest import make_obs
from .http_client import request_local


@dataclass
class _Server:
    """A running test server plus the pieces (store, context) some tests need direct access to."""

    url: str
    db: SqliteStore
    ctx: ServerContext


@pytest.fixture
def server(tmp_path: Path) -> Iterator[_Server]:
    db = SqliteStore(tmp_path / "obs.db")
    db.write([make_obs(parameter="pm25_ugm3", unit="ug/m3", value=12.0, calibration="v1")])
    config = NetworkConfig(nodes=(NodeConfig(node_id="node-01", lat=38.58, lon=-121.49),))
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text(
        '<!doctype html><html lang="en"><title>swelter</title>', "utf-8"
    )
    # A sibling whose name shares the web-dir prefix — for the path-traversal containment test.
    secret = tmp_path / "web-secret"
    secret.mkdir()
    (secret / "creds.txt").write_text("SECRET", "utf-8")
    (tmp_path / "DATA-LICENSE").write_text("CC0-1.0", "utf-8")  # repo-root file the footer cites
    ctx = ServerContext(store=db, config=config, web_dir=web)
    httpd = make_server(ctx, "127.0.0.1", 0)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield _Server(url=f"http://127.0.0.1:{port}", db=db, ctx=ctx)
    finally:
        httpd.shutdown()
        httpd.server_close()
        db.close()


@pytest.fixture
def base_url(server: _Server) -> str:
    return server.url


def _get(url: str) -> tuple[int, str]:
    response = request_local(url)
    return response.status, response.body.decode("utf-8")


def _get_with_headers(host: str, path: str, headers: dict[str, str] | None = None) -> Any:
    conn = http.client.HTTPConnection(host, timeout=5)
    conn.request("GET", path, headers=headers or {})
    response = conn.getresponse()
    response.read()  # drain so the connection can close cleanly
    conn.close()
    return response


def test_path_traversal_sibling_prefix_is_blocked(base_url: str) -> None:
    import http.client

    host = base_url.removeprefix("http://")
    conn = http.client.HTTPConnection(host, timeout=5)
    conn.request("GET", "/../web-secret/creds.txt")  # raw, un-normalized path
    status = conn.getresponse().status
    conn.close()
    assert status == 404  # a sibling sharing the web/ name prefix must not escape the root


def test_bad_query_param_returns_400_not_dropped_connection(base_url: str) -> None:
    status, _ = _get(f"{base_url}/v1.1/Observations?top=abc")
    assert status == 400, "a non-numeric top must be a clean 400, not a dropped connection"


def test_negative_top_is_clamped(base_url: str) -> None:
    _, body = _get(f"{base_url}/v1.1/Observations?top=-1")
    payload: Any = json.loads(body)
    assert payload["value"] == []  # clamped to an empty page, not a negative-slice truncation
    assert payload["@iot.count"] >= 0  # @iot.count is the true total, not the page size


def test_observation_response_carries_in_band_rights_and_link_header(base_url: str) -> None:
    response = request_local(f"{base_url}/v1.1/Observations")
    payload: Any = json.loads(response.body)
    parameters = payload["value"][0]["parameters"]
    assert parameters["source"] == "native"
    assert parameters["data_license"] == snapshot.DEFAULT_DATA_LICENSE
    assert payload["rights"]["attribution"] == snapshot.DEFAULT_DATA_ATTRIBUTION
    assert response.headers["Link"].startswith('</DATA-LICENSE>; rel="license"')


def test_provider_rights_header_links_to_exact_ledger() -> None:
    terms = snapshot.DataTerms(
        "OpenAQ",
        "Provider-specific (see ledger)",
        "OpenAQ and the underlying data providers",
        ledger_content=b"{}",
    )
    header = _rights_link_header(terms)
    assert 'rel="license"' in header
    assert '</source-license-ledger.json>; rel="describedby"' in header


def test_health_endpoint_returns_summary(base_url: str) -> None:
    status, body = _get(f"{base_url}/api/health.json")
    payload: Any = json.loads(body)
    assert status == 200
    assert set(payload["summary"]) == {"total", "ok", "degraded", "offline"}
    assert "nodes" in payload and "gaps" in payload


def test_options_preflight_is_204_with_cors(base_url: str) -> None:
    response = request_local(f"{base_url}/v1.1/Observations", method="OPTIONS")
    assert response.status == 204
    assert response.headers.get("Access-Control-Allow-Origin") == "*"


def test_repo_license_route_served(base_url: str) -> None:
    status, body = _get(f"{base_url}/DATA-LICENSE")
    assert status == 200
    assert "CC0" in body


def test_datastreams_endpoint(base_url: str) -> None:
    _, body = _get(f"{base_url}/v1.1/Datastreams")
    payload: Any = json.loads(body)
    assert payload["@iot.count"] >= 1


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


def test_alerts_json_endpoint(base_url: str) -> None:
    status, body = _get(f"{base_url}/api/alerts.json")
    payload: Any = json.loads(body)
    assert status == 200
    assert "alerts" in payload and "thresholds" in payload and "generated" in payload


def test_alerts_atom_endpoint(base_url: str) -> None:
    import xml.etree.ElementTree as ET

    status, body = _get(f"{base_url}/api/alerts.xml")
    assert status == 200
    root = ET.fromstring(body)  # noqa: S314 -- our own server's response, not external input (#107)
    assert root.tag.endswith("feed")


def test_alerts_atom_es_endpoint(base_url: str) -> None:
    import xml.etree.ElementTree as ET

    status, body = _get(f"{base_url}/api/alerts.es.xml")
    assert status == 200
    root = ET.fromstring(body)  # noqa: S314 -- our own server response; malformed would raise (#107)
    assert root.tag.endswith("feed")
    assert root.get("{http://www.w3.org/XML/1998/namespace}lang") == "es"


def test_cooling_centers_endpoint_empty_when_unconfigured(base_url: str) -> None:
    # The fixture builds a context with no cooling-center path, so the overlay is a valid empty set.
    status, body = _get(f"{base_url}/api/cooling-centers.geojson")
    payload: Any = json.loads(body)
    assert status == 200
    assert payload["type"] == "FeatureCollection"
    assert payload["features"] == []


def test_writes_are_refused(base_url: str) -> None:
    response = request_local(f"{base_url}/v1.1/Observations", method="POST", body=b"{}")
    assert response.status == 405, "the public API must refuse writes"


def test_handler_has_a_read_timeout() -> None:
    # Slow-loris defense: a handler with no socket timeout can be tied up indefinitely by a
    # client that opens a connection and never finishes sending a request.
    from swelter.server import _make_handler

    ctx = ServerContext(
        store=SqliteStore(":memory:"),
        config=NetworkConfig(nodes=()),
        web_dir=Path("."),
    )
    handler_cls = _make_handler(ctx)
    assert handler_cls.timeout == 10


def test_surface_request_is_cached_across_requests(
    server: _Server, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The aggregated surface is the most expensive read on every request; a second request
    # against an unchanged store must reuse it rather than re-running aggregate.aggregate().
    calls = 0
    original = aggregate_module.aggregate

    def counting(*args: Any, **kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(aggregate_module, "aggregate", counting)

    status1, _ = _get(f"{server.url}/api/surface.geojson")
    status2, _ = _get(f"{server.url}/api/surface.geojson")
    assert status1 == status2 == 200
    assert calls == 1, "a repeat request against an unchanged store must not re-aggregate"


def test_surface_records_and_alerts_share_the_cached_aggregate(
    server: _Server, monkeypatch: pytest.MonkeyPatch
) -> None:
    # _surface, _surface_records, and _alerts all read the surface; within one store version
    # they should share a single aggregate.aggregate() call, not one each.
    calls = 0
    original = aggregate_module.aggregate

    def counting(*args: Any, **kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(aggregate_module, "aggregate", counting)

    _get(f"{server.url}/api/surface.geojson")
    _get(f"{server.url}/api/surface.json")
    _get(f"{server.url}/api/alerts.json")
    assert calls == 1


def test_etag_conditional_get_returns_304(server: _Server) -> None:
    host = server.url.removeprefix("http://")
    first = _get_with_headers(host, "/api/surface.geojson")
    assert first.status == 200
    etag = first.getheader("ETag")
    assert etag, "a 200 for a cacheable payload must carry an ETag"

    second = _get_with_headers(host, "/api/surface.geojson", {"If-None-Match": etag})
    assert second.status == 304
    assert second.getheader("ETag") == etag


def test_etag_mismatch_returns_full_body(server: _Server) -> None:
    host = server.url.removeprefix("http://")
    response = _get_with_headers(host, "/api/surface.geojson", {"If-None-Match": '"stale"'})
    assert response.status == 200


def test_surface_cache_invalidates_after_store_write(server: _Server) -> None:
    # connection_change_count() bumps on a write without the row *count* necessarily telling the
    # same story on its own — the version key must react to a write, not just to row count.
    _, first_body = _get(f"{server.url}/api/surface.geojson")
    first = json.loads(first_body)

    server.db.write(
        [
            make_obs(
                node_id="node-01",
                parameter="pm25_ugm3",
                unit="ug/m3",
                value=999.0,
                calibration="v1",
                timestamp="2026-06-01T05:00:00Z",
            )
        ]
    )

    _, second_body = _get(f"{server.url}/api/surface.geojson")
    second = json.loads(second_body)
    assert first != second, "a store write must invalidate the cached surface, not serve stale data"


def test_surface_cache_invalidates_after_rebuild_with_unchanged_row_count(
    server: _Server,
) -> None:
    # drop_calibrated() deletes and (via re-ingest) rewrites derived rows without necessarily
    # changing the row count. This same connection's change counter must invalidate the cache;
    # SQLite's data_version deliberately does not move for a connection's own writes.
    _, first_body = _get(f"{server.url}/api/surface.geojson")
    first = json.loads(first_body)  # warms the cache

    count_before = server.db.count()
    server.db.drop_calibrated()
    server.db.write([make_obs(parameter="pm25_ugm3", unit="ug/m3", value=42.0, calibration="v1")])
    assert server.db.count() == count_before  # row count unchanged; own change count still moved

    _, second_body = _get(f"{server.url}/api/surface.geojson")
    second = json.loads(second_body)
    assert second != first
    assert second["features"][0]["properties"]["pm25_ugm3"] == 42.0


def test_surface_cache_invalidates_after_out_of_process_rebuild(server: _Server) -> None:
    # The realistic case: `swelter rebuild` runs as a *separate* process/connection against the
    # same store file while `swelter serve` keeps its own long-lived connection open. A rebuild
    # that leaves the row count unchanged must still invalidate the server's cached surface — the
    # version key can't rely on this connection's own change count, which never sees writes made
    # through a different connection (see swelter.server._store_version).
    _, first_body = _get(f"{server.url}/api/surface.geojson")
    json.loads(first_body)  # warms the cache

    other = SqliteStore(server.db.path)
    try:
        count_before = server.db.count()
        other.drop_calibrated()
        other.write([make_obs(parameter="pm25_ugm3", unit="ug/m3", value=77.0, calibration="v2")])
        assert server.db.count() == count_before  # row count unchanged from this connection's view
    finally:
        other.close()

    _, second_body = _get(f"{server.url}/api/surface.geojson")
    second = json.loads(second_body)
    assert second["features"], "an out-of-process rebuild must not be served from a stale cache"
    assert second != json.loads(first_body)
    assert second["features"][0]["properties"]["pm25_ugm3"] == 77.0
