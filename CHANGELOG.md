# Changelog

All notable changes to swelter are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project follows
[Semantic Versioning](https://semver.org/spec/v2.0.0.html) for both the public API and the data
schema (see [`docs/VERSIONING.md`](docs/VERSIONING.md)).

## [Unreleased]

### Added

- **Neighborhood heat/AQI alerts.** A generated, public alerts feed: `swelter.alerts` scans the
  latest hour of the surface and raises one alert per published cell that crosses a documented danger
  floor (US-EPA AQI 101, US-NWS heat "Danger", or exposure "High"; overridable via `alert_thresholds`
  in `network.yaml`). Served at `/api/alerts.json` and as a subscribable **Atom 1.0** feed at
  `/api/alerts.xml` (`?area=<id>` to narrow), baked into the static site, and exposed via a new
  `swelter alerts` command. The dashboard adds a "Neighborhood alerts" panel with an area picker and a
  copy-the-feed-link subscribe affordance. No account, no PII — the subscription lives in the reader's
  own tooling ([ADR 0010](docs/decisions/0010-neighborhood-alerts-feed.md), [`docs/alerts.md`](docs/alerts.md)).
- **Cooling-center overlay.** A curated, validated, provenance-bearing cooling-center dataset
  (`data/cooling_centers.geojson`) served at `/api/cooling-centers.geojson`, with a toggleable map
  overlay and an always-present accessible parity list on the dashboard. Loader enforces a public-field
  allowlist so no private contact can reach the map
  ([ADR 0011](docs/decisions/0011-cooling-center-overlay.md)).

## [0.1.0] — 2026-06-16

The first reference implementation: a runnable pipeline, a calibration engine, an accessible
dashboard, an open API, and a green merge gate.

### Added

- **Pipeline.** Ingest (validate → quarantine malformed → explode to immutable, content-hashed
  observations → QC), an idempotent, Datasette-openable SQLite store behind a pluggable `Store`
  protocol, range/spike/flatline QC with gap detection and node health, spatial/temporal
  aggregation into gridded heat-island and AQI surfaces.
- **Calibration engine.** Pure-Python ordinary least squares: humidity-aware corrections for PM
  (US-EPA PurpleAir lineage) and an enclosure-offset for temperature, fit from committed
  co-location data, with published 1-sigma uncertainty and a versioned YAML correction registry.
  Re-running the fit reproduces the published registry byte-for-byte.
- **Open data out.** CSV/JSON export and a read-only OGC SensorThings 1.1 subset, served by a
  dependency-free, single-threaded, read-only HTTP server.
- **Dashboard.** A framework-free WCAG 2.2 AA dashboard with equal map, table, and list views;
  AQI by text and pattern, not color alone; a keyboard-operable time slider; English and Spanish;
  installable as a PWA.
- **CLI.** `swelter ingest | qc | calibrate | aggregate | export | serve | demo | rebuild | version`.
  `swelter demo` replays a recorded week through the whole pipeline with no hardware.
- **Privacy by construction.** Grid-snapped public locations (precise is an explicit host opt-in), a
  schema with no field that can hold a person, and firmware with no microphone, camera, Bluetooth, or
  Wi-Fi client scanning.
- **Quality gate.** `make verify` runs ruff (format + lint), mypy `--strict`, the structural
  accessibility gate (12 checks), and 62 tests — including a calibration-replay reproducibility test.
- **Docs and governance.** Architecture, calibration, governance, API, roadmap, versioning, ADRs,
  responsible-tech audits, an accessibility conformance report (VPAT 2.5 Rev 508), reference
  firmware, and optional scale-to-zero infrastructure.

[Unreleased]: https://github.com/ChelseaKR/swelter/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/ChelseaKR/swelter/releases/tag/v0.1.0
