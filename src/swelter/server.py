"""A read-only, dependency-free HTTP server for the dashboard, the API, and the exports.

Built on the standard library's ``http.server`` on purpose: no framework, no always-on
worker, nothing that failing takes the data down with it. The process is stateless — it reads
the store and answers — so it is happy behind a scale-to-zero front end and runs just as well
on a Raspberry-Pi-class host with no cloud at all. It only ever answers ``GET``; there is no
write path to expose.
"""

from __future__ import annotations

import json
import mimetypes
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import aggregate, api, export
from .config import NetworkConfig
from .store import Store


@dataclass
class ServerContext:
    """Everything a request needs: the store to read, the network, and the static dashboard."""

    store: Store
    config: NetworkConfig
    web_dir: Path
    base_url: str = "http://localhost:8000"


def _make_handler(ctx: ServerContext) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "swelter/0.1"

        def log_message(self, *_: object) -> None:  # keep stdout clean; structured logs elsewhere
            return

        def do_GET(self) -> None:  # noqa: N802 (http.server API)
            parsed = urlparse(self.path)
            path = parsed.path
            query = parse_qs(parsed.query)
            try:
                if path in ("/health", "/healthz"):
                    self._json({"status": "ok", "observations": ctx.store.count()})
                elif path == f"/v{api.SENSORTHINGS_VERSION}":
                    self._json(api.service_document(ctx.base_url))
                elif path == f"/v{api.SENSORTHINGS_VERSION}/Things":
                    self._json(api.things(ctx.config, ctx.base_url))
                elif path == f"/v{api.SENSORTHINGS_VERSION}/ObservedProperties":
                    self._json(api.observed_properties(ctx.base_url))
                elif path == f"/v{api.SENSORTHINGS_VERSION}/Observations":
                    self._observations(query)
                elif path == "/api/surface.geojson":
                    self._surface()
                elif path == "/api/surface.json":
                    self._surface_records(query)
                elif path == "/export.csv":
                    self._export(query, fmt="csv")
                elif path == "/export.json":
                    self._export(query, fmt="json")
                else:
                    self._static(path)
            except BrokenPipeError:  # client went away mid-response
                return

        def do_POST(self) -> None:  # noqa: N802
            self.send_error(405, "swelter's public API is read-only")

        do_PUT = do_DELETE = do_PATCH = do_POST

        # -- helpers -------------------------------------------------------------

        def _observations(self, query: dict[str, list[str]]) -> None:
            obs = ctx.store.read(
                parameter=_one(query, "parameter"),
                node_id=_one(query, "node"),
                since=_one(query, "since"),
                until=_one(query, "until"),
            )
            top = int(_one(query, "top") or "1000")
            self._json(api.observations(obs, ctx.base_url, top=top))

        def _surface(self) -> None:
            surface = aggregate.aggregate(ctx.store.all(), ctx.config)
            self._json(surface.snapshot_geojson())

        def _surface_records(self, query: dict[str, list[str]]) -> None:
            # Flat per-(cell, hour, parameter) records for the dashboard's time slider,
            # trimmed to the most recent `hours` buckets to keep the payload small.
            surface = aggregate.aggregate(ctx.store.all(), ctx.config)
            hours = int(_one(query, "hours") or "48")
            buckets = sorted({c.bucket for c in surface.cells})[-hours:]
            keep = set(buckets)
            records = [c.as_record() for c in surface.cells if c.bucket in keep]
            self._json({"interval": surface.interval, "buckets": buckets, "cells": records})

        def _export(self, query: dict[str, list[str]], *, fmt: str) -> None:
            obs = ctx.store.read(
                parameter=_one(query, "parameter"),
                node_id=_one(query, "node"),
                since=_one(query, "since"),
                until=_one(query, "until"),
            )
            if fmt == "csv":
                self._body(export.to_csv(obs).encode("utf-8"), "text/csv; charset=utf-8")
            else:
                self._body(export.to_json(obs).encode("utf-8"), "application/json")

        def _static(self, path: str) -> None:
            rel = path.lstrip("/") or "index.html"
            target = (ctx.web_dir / rel).resolve()
            if not str(target).startswith(str(ctx.web_dir.resolve())) or not target.is_file():
                self.send_error(404, "not found")
                return
            content_type, _ = mimetypes.guess_type(str(target))
            self._body(target.read_bytes(), content_type or "application/octet-stream")

        def _json(self, payload: object) -> None:
            self._body(json.dumps(payload).encode("utf-8"), "application/json")

        def _body(self, data: bytes, content_type: str) -> None:
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Access-Control-Allow-Origin", "*")  # open data: read from anywhere
            self.send_header("Cache-Control", "public, max-age=60")
            self.end_headers()
            self.wfile.write(data)

    return Handler


def _one(query: dict[str, list[str]], key: str) -> str | None:
    values = query.get(key)
    return values[0] if values else None


def make_server(ctx: ServerContext, host: str, port: int) -> HTTPServer:
    """Build (but do not start) the HTTP server.

    Single-threaded on purpose: a community dashboard sits behind a static cache / CDN and
    needs almost no concurrency, and serialising requests keeps the one SQLite reader safe.
    """
    return HTTPServer((host, port), _make_handler(ctx))


def serve(ctx: ServerContext, host: str = "127.0.0.1", port: int = 8000) -> None:
    """Run the server until interrupted."""
    httpd = make_server(ctx, host, port)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
