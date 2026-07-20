"""A read-only, dependency-free HTTP server for the dashboard, the API, and the exports.

Built on the standard library's ``http.server`` on purpose: no framework, no always-on
worker, nothing that failing takes the data down with it. The process is stateless — it reads
the store and answers — so it is happy behind a scale-to-zero front end and runs just as well
on a Raspberry-Pi-class host with no cloud at all. It only ever answers ``GET``; there is no
write path to expose.
"""

from __future__ import annotations

import contextlib
import gzip
import hashlib
import json
import mimetypes
import os
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import aggregate, alerts, api, calibrate, cooling_centers, export, obs, qc, snapshot
from .aggregate import Surface
from .config import NetworkConfig
from .models import RAW
from .store import SqliteStore, Store, store_paths

#: Opt-in request logging (method/path/status/ms only, never IPs — hard rule 1). Off by
#: default: a community dashboard's request log is operationally uninteresting until someone
#: asks for it, and JSON lines on stderr are noise for the common `swelter serve` terminal use.
_REQUEST_LOG_ENV = "SWELTER_LOG_REQUESTS"

_RIGHTS_BEARING_STATIC_FILES = frozenset(
    {
        "alerts.es.xml",
        "alerts.json",
        "alerts.xml",
        "export.csv",
        "sample-health.json",
        "sample-surface.json",
        "surface-24h.json",
        "surface-7d.json",
    }
)


def _request_logging_enabled() -> bool:
    return os.environ.get(_REQUEST_LOG_ENV, "").strip().lower() in ("1", "true", "yes", "on")


@dataclass
class ServerContext:
    """Everything a request needs: the store to read, the network, and the static dashboard."""

    store: Store
    config: NetworkConfig
    web_dir: Path
    base_url: str = "http://localhost:8000"
    cooling_centers_path: Path | None = None  # curated cooling-center dataset (optional overlay)
    # The store directory `/api/health.json` reads `run-manifest.json` (obs.read_manifest) and
    # the integrity chain head (qc.health_report's store_dir) from. None when a caller builds a
    # ServerContext without a store-backed pipeline run behind it (e.g. tests); the health
    # report simply omits the `run` and `integrity` blocks in that case.
    store_dir: Path | None = None
    data_terms: snapshot.DataTerms | None = None


def _resolved_data_terms(ctx: ServerContext) -> snapshot.DataTerms:
    if ctx.store_dir is None:
        if ctx.data_terms is not None:
            return ctx.data_terms
        return snapshot.DataTerms(
            snapshot.DEFAULT_DATA_SOURCE,
            snapshot.DEFAULT_DATA_LICENSE,
            snapshot.DEFAULT_DATA_ATTRIBUTION,
        )
    try:
        return snapshot.load_data_terms(ctx.store_dir, observations=list(ctx.store.all()))
    except ValueError as exc:
        raise RuntimeError("store data-rights provenance is incomplete") from exc


def _load_registry(store_dir: Path | None) -> calibrate.CorrectionRegistry | None:
    """The correction registry in ``store_dir`` (``corrections.yaml``), else ``None``.

    ``None`` (no store dir, no file, or an empty registry) makes ``/api/health.json`` omit its
    ``calibration`` drift block, exactly the JSON shape it had before drift surveillance existed.
    """
    if store_dir is None:
        return None
    path = store_paths(store_dir)["registry"]
    if not path.is_file():
        return None
    registry = calibrate.CorrectionRegistry.from_yaml(path)
    return registry if len(registry) else None


def _store_version(store: Store) -> object:
    """A cheap fingerprint of the store's contents, or ``None`` if it can't be fingerprinted.

    The store is append-only for raw rows, but ``drop_calibrated()`` (the rebuild path) deletes
    and rewrites derived rows *without changing the row count* — so the version key must include
    a change counter, not just ``count()``, or a rebuild would serve a stale cached surface.

    SQLite exposes two complementary change counters. ``connection_change_count()`` catches
    same-connection rewrites, but not work committed by another process. ``data_version()``
    catches those cross-connection commits, but SQLite deliberately leaves it unchanged for this
    connection's own writes. The fingerprint therefore needs both counters as well as the count.
    """
    if isinstance(store, SqliteStore):
        return (
            "sqlite",
            store.count(),
            store.connection_change_count(),
            store.data_version(),
        )
    path = getattr(store, "path", None)
    if path is not None:
        candidate = Path(path)
        if candidate.is_file():
            return ("mtime", candidate.stat().st_mtime_ns)
    return None  # unknown backend: no fingerprint available, so no caching


def _etag_matches(if_none_match: str, etag: str) -> bool:
    if if_none_match.strip() == "*":
        return True
    quoted = f'"{etag}"'
    return any(
        token.strip().removeprefix("W/") in (etag, quoted) for token in if_none_match.split(",")
    )


def _rights_link_header(terms: snapshot.DataTerms) -> str:
    """RFC 8288 links that keep a downloaded representation attached to its rights evidence."""
    links = ['</DATA-LICENSE>; rel="license"; type="text/plain"']
    if terms.ledger_content is not None:
        links.append('</source-license-ledger.json>; rel="describedby"; type="application/json"')
    return ", ".join(links)


def _rights_cache_token(terms: snapshot.DataTerms) -> str:
    """Stable cache discriminator for response bodies containing a rights envelope."""
    digest = hashlib.sha256(
        json.dumps(snapshot.rights_envelope(terms), sort_keys=True).encode("utf-8")
    )
    if terms.ledger_content is not None:
        digest.update(terms.ledger_content)
    return digest.hexdigest()[:16]


class _ResponseCache:
    """Process-lifetime cache: the aggregated surface plus precomputed response bodies.

    Keyed on ``_store_version()``. A single slot is kept (not one per version) because the
    store only ever has one "current" version at a time; a version bump invalidates everything
    at once rather than accumulating stale entries.
    """

    def __init__(self) -> None:
        self.version: object = object()  # sentinel that matches no real version
        self.surface: Surface | None = None
        self.bodies: dict[str, tuple[bytes, bytes | None, str]] = {}

    def surface_for(self, store: Store, config: NetworkConfig) -> Surface:
        version = _store_version(store)
        if version is None or version != self.version:
            surface = aggregate.aggregate(store.all(), config)
            if version is not None:
                self.version = version
                self.surface = surface
                self.bodies = {}  # the store moved on; every cached body is now stale
            return surface
        if self.surface is None:
            raise RuntimeError("response cache version exists without a computed surface")
        return self.surface

    def body_for(self, store: Store, cache_id: str) -> tuple[bytes, bytes | None, str] | None:
        version = _store_version(store)
        if version is None or version != self.version:
            return None  # store moved since the surface was last computed; caller must rebuild
        return self.bodies.get(cache_id)

    def store_body(
        self, store: Store, cache_id: str, entry: tuple[bytes, bytes | None, str]
    ) -> None:
        version = _store_version(store)
        if version is not None and version == self.version:
            self.bodies[cache_id] = entry


def _make_handler(ctx: ServerContext) -> type[BaseHTTPRequestHandler]:  # noqa: C901 (#107)
    # Ruff's mccabe walker sums every nested method's branches into this factory function because
    # the handler class is defined inside it (closure over `ctx`, the stdlib http.server pattern);
    # most methods below are independently simple. Documented exception, not a silent one — see
    # swelter-REMEDIATION.md Quick win 5 (CQ-05).
    cache = _ResponseCache()

    class Handler(BaseHTTPRequestHandler):
        server_version = "swelter/0.1"
        _status_sent: int = 0  # set by send_response(); read for optional request logging
        # BaseHTTPRequestHandler honors this for socket reads/writes: a client that opens a
        # connection and trickles bytes (or none) no longer ties up the single request thread
        # indefinitely. Slow-loris defense without switching off the single-threaded model
        # (ADR 0005 — the one SQLite reader stays serialised).
        timeout = 10

        def log_message(self, *_: object) -> None:  # keep stdout clean; structured logs elsewhere
            return

        def send_response(self, code: int, message: str | None = None) -> None:
            self._status_sent = code  # captured for optional request logging, never IPs
            super().send_response(code, message)

        def do_GET(self) -> None:  # noqa: C901 (http.server API; flat route dispatch, see above) (#107)
            started = time.monotonic()
            self._status_sent = 0
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/") or "/"  # normalise trailing slashes
            query = parse_qs(parsed.query)
            v = f"/v{api.SENSORTHINGS_VERSION}"
            try:
                if path in ("/health", "/healthz"):
                    self._json({"status": "ok", "observations": ctx.store.count()})
                elif path == v:
                    self._json(
                        api.service_document(ctx.base_url),
                        data_terms=_resolved_data_terms(ctx),
                    )
                elif path == f"{v}/Things":
                    self._json(
                        api.things(ctx.config, ctx.base_url),
                        data_terms=_resolved_data_terms(ctx),
                    )
                elif path == f"{v}/Locations":
                    self._json(
                        api.locations(ctx.config, ctx.base_url),
                        data_terms=_resolved_data_terms(ctx),
                    )
                elif path == f"{v}/Datastreams":
                    self._json(
                        api.datastreams(ctx.config, ctx.base_url),
                        data_terms=_resolved_data_terms(ctx),
                    )
                elif path == f"{v}/ObservedProperties":
                    self._json(
                        api.observed_properties(ctx.base_url),
                        data_terms=_resolved_data_terms(ctx),
                    )
                elif path == f"{v}/Observations":
                    self._observations(query)
                elif path == "/api/surface.geojson":
                    self._surface()
                elif path == "/api/surface.json":
                    self._surface_records(query)
                elif path == "/api/health.json":
                    self._health()
                elif path == "/api/schema.json":
                    self._schema()
                elif path == "/api/alerts.json":
                    self._alerts(query, fmt="json")
                elif path == "/api/alerts.xml":
                    self._alerts(query, fmt="atom")
                elif path == "/api/alerts.es.xml":
                    self._alerts(query, fmt="atom", lang="es")
                elif path == "/api/cooling-centers.geojson":
                    self._cooling_centers()
                elif path == "/export.csv":
                    self._export(query, fmt="csv")
                elif path == "/export.json":
                    self._export(query, fmt="json")
                elif path in ("/LICENSE", "/DATA-LICENSE", "/NOTICE"):
                    self._repo_file(path.lstrip("/"))
                elif path == "/source-license-ledger.json":
                    self._source_license_ledger()
                else:
                    self._static(path)
            except BrokenPipeError:  # client went away mid-response
                return
            except ValueError as exc:  # bad query param: non-numeric top/hours, bad timestamp
                self._safe_error(400, f"bad request: {exc}")
            except Exception:  # never drop the connection with no response
                self._safe_error(500, "internal error")
            finally:
                if _request_logging_enabled():
                    ms = round((time.monotonic() - started) * 1000, 1)
                    obs.log_event(
                        "server",
                        "request",
                        method="GET",
                        path=path,
                        status=self._status_sent,
                        ms=ms,
                    )

        def do_POST(self) -> None:
            self._safe_error(405, "swelter's public API is read-only")

        do_PUT = do_DELETE = do_PATCH = do_POST

        def do_OPTIONS(self) -> None:
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "*")
            self.send_header("Content-Length", "0")
            self.end_headers()

        # -- helpers -------------------------------------------------------------

        def _safe_error(self, code: int, message: str) -> None:
            # JSON error body. Headers may already be on the wire (error mid-body); then there is
            # nothing more to do, so the whole attempt is best-effort.
            with contextlib.suppress(Exception):
                body = json.dumps({"error": message, "status": code}).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(body)

        def _observations(self, query: dict[str, list[str]]) -> None:
            obs = ctx.store.read(
                parameter=_one(query, "parameter"),
                node_id=_one(query, "node"),
                since=_one(query, "since"),
                until=_one(query, "until"),
            )
            top = int(_one(query, "top") or _one(query, "$top") or "1000")
            skip = int(_one(query, "skip") or _one(query, "$skip") or "0")
            dedupe = _one(query, "dedupe") != "false"
            orderby = (_one(query, "order") or _one(query, "$orderby") or "").lower()
            order = "desc" if "desc" in orderby else "asc"
            terms = _resolved_data_terms(ctx)
            document = api.observations(
                obs,
                ctx.base_url,
                top=top,
                skip=skip,
                dedupe=dedupe,
                order=order,
                data_license=terms.license,
                data_attribution=terms.attribution,
                data_license_url=terms.license_url,
                terms_by_observation=snapshot.export_terms_by_observation(terms, obs),
            )
            document["rights"] = snapshot.rights_envelope(terms)
            self._json(document, data_terms=terms)

        def _surface(self) -> None:
            surface = cache.surface_for(ctx.store, ctx.config)
            terms = _resolved_data_terms(ctx)
            document = surface.snapshot_geojson()
            document["rights"] = snapshot.rights_envelope(terms)
            self._json(
                document,
                content_type="application/geo+json",
                cache_id="surface.geojson",
                data_terms=terms,
            )

        def _surface_records(self, query: dict[str, list[str]]) -> None:
            # Flat per-(cell, hour, parameter) records for the dashboard's time slider,
            # trimmed to the most recent `hours` buckets to keep the payload small.
            surface = cache.surface_for(ctx.store, ctx.config)
            hours = max(0, int(_one(query, "hours") or "48"))
            buckets = sorted({c.bucket for c in surface.cells})[-hours:] if hours else []
            keep = set(buckets)
            records = [c.as_record() for c in surface.cells if c.bucket in keep]
            terms = _resolved_data_terms(ctx)
            self._json(
                {
                    "interval": surface.interval,
                    "buckets": buckets,
                    "cells": records,
                    "rights": snapshot.rights_envelope(terms),
                },
                cache_id=f"surface.json:hours={hours}",
                data_terms=terms,
            )

        def _alerts(self, query: dict[str, list[str]], *, fmt: str, lang: str = "en") -> None:
            # The generated neighborhood-alerts feed: cells crossing a danger threshold in the
            # latest hour. `?area=<area_id>` narrows it to one cell (the per-neighborhood feed).
            # `lang="es"` (the /api/alerts.es.xml route) renders the Atom feed via the
            # machine-translated swelter.i18n_alerts catalog; see AlertFeed.to_atom.
            surface = cache.surface_for(ctx.store, ctx.config)
            feed = alerts.build_feed(
                surface,
                network=ctx.config.name,
                base_url=ctx.base_url,
                thresholds=ctx.config.alert_thresholds or None,
            )
            area = _one(query, "area")
            if area:
                feed = feed.for_area(area)
            cache_id = f"alerts.{fmt}:lang={lang}:area={area or ''}"
            terms = _resolved_data_terms(ctx)
            if fmt == "atom":
                self._body(
                    feed.to_atom(lang=lang).encode("utf-8"),
                    "application/atom+xml; charset=utf-8",
                    cache_id=cache_id,
                    data_terms=terms,
                )
            else:
                document = feed.to_json()
                document["rights"] = snapshot.rights_envelope(terms)
                self._json(document, cache_id=cache_id, data_terms=terms)

        def _cooling_centers(self) -> None:
            # The curated cooling-center overlay. Served validated; an absent/empty dataset
            # returns a valid empty FeatureCollection so the dashboard can simply hide it.
            path = ctx.cooling_centers_path
            if path is not None and path.is_file():
                dataset = cooling_centers.load(path)
            else:
                dataset = cooling_centers.empty()
            self._json(dataset.to_geojson(), content_type="application/geo+json")

        def _health(self) -> None:
            # Per-node liveness/quality from the raw stream — the "how many sensors are reporting"
            # coverage view. Heavy-ish (reads raw), but cached 60s like the other reads. The
            # calibrated-vs-raw coverage-equity read rides along (needs the full stream + config to
            # know which nodes are calibrated and which published cell each sits in).
            coverage = qc.coverage_equity(ctx.store.all(), aggregate.node_cell_map(ctx.config))
            # Correction-drift surveillance rides along when the store folder holds a correction
            # registry (corrections.yaml): each calibrated node/parameter's correction age vs the
            # latest reading, flagged past the drift horizon. Descriptive only — reads window_end,
            # changes no value (hard rule #3). Absent when no registry is on disk.
            registry = _load_registry(ctx.store_dir)
            report = qc.health_report(
                ctx.store.read(calibration=RAW),
                coverage=coverage,
                store_dir=ctx.store_dir,
                registry=registry,
            )
            # Name the pipeline run that built the currently-published surface, if one has run
            # against this store (obs.write_manifest, wired into ingest/calibrate/aggregate/demo).
            # A store predating this feature, or one no pipeline command has touched yet, simply
            # gets no `run` block rather than a broken health endpoint.
            if ctx.store_dir is not None:
                manifest = obs.read_manifest(ctx.store_dir)
                if manifest is not None:
                    report["run"] = {
                        "run_id": manifest.get("run_id"),
                        "finished_at": manifest.get("finished_at"),
                        "counters": manifest.get("counters"),
                    }
            terms = _resolved_data_terms(ctx)
            report["rights"] = snapshot.rights_envelope(terms)
            self._json(report, data_terms=terms)

        def _schema(self) -> None:
            # The machine-readable data dictionary: generated from the running code's own
            # source-of-truth constants (PARAMETERS, the QC_* verdicts, export._CSV_FIELDS), so it
            # cannot drift from what the pipeline actually does. `data_schema_version` is the pin
            # target — see docs/VERSIONING.md.
            terms = _resolved_data_terms(ctx)
            document = api.schema_document(
                data_source=terms.source,
                data_license=terms.license,
                data_attribution=terms.attribution,
                data_license_url=terms.license_url,
            )
            document["rights"] = snapshot.rights_envelope(terms)
            self._json(document, data_terms=terms)

        def _export(self, query: dict[str, list[str]], *, fmt: str) -> None:
            obs = ctx.store.read(
                parameter=_one(query, "parameter"),
                node_id=_one(query, "node"),
                since=_one(query, "since"),
                until=_one(query, "until"),
            )
            terms = _resolved_data_terms(ctx)
            terms_by_observation = snapshot.export_terms_by_observation(terms, obs)
            if fmt == "csv":
                self._body(
                    export.to_csv(
                        obs,
                        license=terms.license,
                        attribution=terms.attribution,
                        terms_by_observation=terms_by_observation,
                    ).encode("utf-8"),
                    "text/csv; charset=utf-8",
                    data_terms=terms,
                )
            else:
                self._body(
                    export.to_json(
                        obs,
                        license=terms.license,
                        attribution=terms.attribution,
                        terms_by_observation=terms_by_observation,
                    ).encode("utf-8"),
                    "application/json",
                    data_terms=terms,
                )

        def _static(self, path: str) -> None:
            rel = path.lstrip("/") or "index.html"
            web_root = ctx.web_dir.resolve()
            target = (web_root / rel).resolve()
            # Boundary-correct containment check — a lexical startswith() would let a sibling
            # directory sharing the web-dir name prefix (e.g. web-secret) escape the root.
            if not target.is_relative_to(web_root) or not target.is_file():
                self._safe_error(404, "not found")
                return
            content_type, _ = mimetypes.guess_type(str(target))
            data_terms = _resolved_data_terms(ctx) if rel in _RIGHTS_BEARING_STATIC_FILES else None
            self._body(
                target.read_bytes(),
                content_type or "application/octet-stream",
                data_terms=data_terms,
            )

        def _repo_file(self, name: str) -> None:
            # Serve the repo-root LICENSE / DATA-LICENSE / NOTICE so the footer's citation trail
            # resolves under `swelter serve` (web_dir's parent is the repo root in that layout).
            if name == snapshot.DATA_LICENSE_FILENAME:
                terms = _resolved_data_terms(ctx)
                self._body(
                    snapshot.render_data_license(terms).encode("utf-8"),
                    "text/plain; charset=utf-8",
                    data_terms=terms,
                )
                return
            target = ctx.web_dir.resolve().parent / name
            if target.is_file():
                self._body(target.read_bytes(), "text/plain; charset=utf-8")
            else:
                self._safe_error(404, "not found")

        def _source_license_ledger(self) -> None:
            terms = _resolved_data_terms(ctx)
            if terms.ledger_content is None:
                self._safe_error(404, "not found")
                return
            self._body(terms.ledger_content, "application/json", data_terms=terms)

        def _json(
            self,
            payload: object,
            content_type: str = "application/json",
            *,
            cache_id: str | None = None,
            data_terms: snapshot.DataTerms | None = None,
        ) -> None:
            self._body(
                json.dumps(payload).encode("utf-8"),
                content_type,
                cache_id=cache_id,
                data_terms=data_terms,
            )

        def _body(
            self,
            data: bytes,
            content_type: str,
            *,
            cache_id: str | None = None,
            data_terms: snapshot.DataTerms | None = None,
        ) -> None:
            # `cache_id` names one of the "big three" aggregated payloads (surface/alerts); it
            # keys a process-lifetime cache of the compressed bytes + ETag alongside the cached
            # Surface, so a repeat request within the same store version skips re-gzip and
            # re-hash entirely. Endpoints that pass no `cache_id` (static files, exports, the
            # observation feed) still get an ETag, just computed fresh each time — they are
            # already cheap, so precomputing would only add bookkeeping.
            effective_cache_id = cache_id
            if effective_cache_id is not None and data_terms is not None:
                effective_cache_id = (
                    f"{effective_cache_id}:rights={_rights_cache_token(data_terms)}"
                )
            cached = (
                cache.body_for(ctx.store, effective_cache_id)
                if effective_cache_id is not None
                else None
            )
            if cached is not None:
                data, gzip_data, etag = cached
            else:
                etag = hashlib.sha256(data).hexdigest()[:16]
                compressible = len(data) > 1024 and _compressible(content_type)
                if effective_cache_id is not None:
                    gzip_data = gzip.compress(data) if compressible else None
                    cache.store_body(ctx.store, effective_cache_id, (data, gzip_data, etag))
                else:
                    want_gzip = compressible and "gzip" in self.headers.get("Accept-Encoding", "")
                    gzip_data = gzip.compress(data) if want_gzip else None

            if_none_match = self.headers.get("If-None-Match")
            if if_none_match and _etag_matches(if_none_match, etag):
                # A 304 carries no body — RFC 9110 forbids Content-Length here.
                self.send_response(304)
                self.send_header("ETag", f'"{etag}"')
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Cache-Control", "public, max-age=60")
                if data_terms is not None:
                    self.send_header("Link", _rights_link_header(data_terms))
                self.end_headers()
                return

            encoded = gzip_data is not None and "gzip" in self.headers.get("Accept-Encoding", "")
            body = gzip_data if (encoded and gzip_data is not None) else data
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            if encoded:
                self.send_header("Content-Encoding", "gzip")
                self.send_header("Vary", "Accept-Encoding")
            self.send_header("ETag", f'"{etag}"')
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")  # open data: read from anywhere
            self.send_header("Cache-Control", "public, max-age=60")
            if data_terms is not None:
                self.send_header("Link", _rights_link_header(data_terms))
            self.end_headers()
            self.wfile.write(body)

    return Handler


def _compressible(content_type: str) -> bool:
    return content_type.startswith("text/") or any(
        token in content_type for token in ("json", "javascript", "csv", "xml", "svg")
    )


def _one(query: dict[str, list[str]], key: str) -> str | None:
    values = query.get(key)
    return values[0] if values else None


def make_server(ctx: ServerContext, host: str, port: int) -> HTTPServer:
    """Build (but do not start) the HTTP server.

    Single-threaded on purpose: a community dashboard sits behind a static cache / CDN and
    needs almost no concurrency, and serialising requests keeps the one SQLite reader safe.
    """
    if _request_logging_enabled():
        obs.configure_json_logging()
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
