# ADR 0005: Serve over a single-threaded, GET-only stdlib HTTP server

- Status: Accepted
- Date: 2026-06-16
- Deciders: Chelsea Kelly-Reif
- Dependency-count posture superseded by: ADR 0025

## Context

A community dashboard sits behind a static cache or CDN and needs almost no
concurrency, so single-threaded is enough — and serialising requests is what
keeps the one SQLite reader safe (see ADR 0001). The process is stateless: it
reads the store and answers, so it is happy behind a scale-to-zero front end and
runs just as well on a Raspberry-Pi-class host with no cloud at all. GET-only is
not a config toggle but the shape of the code: there is no write path to expose,
so the public surface cannot be used to alter the record, which matches the
read-only API in `api.py`. The standard library means no web framework as a
runtime dependency (PyYAML is the only one) and nothing whose failure takes the
data down with it. We rejected an ASGI/WSGI framework with a worker pool
(concurrency this deployment does not need, an always-on process to babysit, a
dependency to track) and exposing any write endpoint (it would contradict the
append-only store and the no-write-path guarantee).

## Decision

`swelter.server` is built on the standard library's `http.server.HTTPServer`:
no framework, no always-on worker. It is single-threaded and read-only — only
`GET` is answered; `do_POST` and its `PUT`/`DELETE`/`PATCH` aliases return
`405 "swelter's public API is read-only"`. The handler reads the store and
answers, holding no mutable state. Routes are `/health`, the SensorThings subset
under `/v1.1` (`/v1.1/Things`, `/v1.1/ObservedProperties`, `/v1.1/Observations`),
`/api/surface.geojson`, `/api/surface.json?hours=N`, `/export.csv`,
`/export.json`, and static files from `web/`. Static serving resolves paths and
rejects anything escaping `web_dir`. CORS is open (`Access-Control-Allow-Origin:
*`) because the data is open, with a short `Cache-Control: public, max-age=60`.
`make_server` builds it; `serve()` runs it until interrupted.

## Consequences

Single-threaded means one slow request blocks the next; this is acceptable only
because the expected fronting is a static cache and the payloads are small
(`/api/surface.json` trims to the most recent `hours` buckets). Under direct,
high-concurrency public load with no cache the server would be a bottleneck —
the answer is to put a cache in front, not to add threads behind the single
SQLite reader. `http.server` is explicitly not hardened for hostile direct
exposure, so production deployments belong behind a reverse proxy or CDN. Open
CORS is deliberate for open data but means any origin can read; there is nothing
to protect because there is no write path and no personal data in the schema.
