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
- **Plain-language neighborhood exposure brief (`swelter brief`).** `swelter.exposure_brief`
  counts, per published cell, how many calendar days a parameter (default heat index) crossed its
  documented danger floor — reusing `alerts.py`'s own threshold logic, not a second definition of
  "Danger" — and joins that count with sourced, optional context: tree-canopy coverage (existing
  `context_layers.py`), an AC-access proxy (new `ac_access_layer.py`), and historical HOLC
  redlining grades (new `redlining_layer.py`). Every context sentence carries its source, source
  URL, and `last_verified` date; a layer with no coverage for a cell is omitted, never guessed.
  Real sources: USDA Forest Service California Urban Tree Canopy data, U.S. Census Bureau Local
  Air Conditioning Estimates (LACE), and the University of Richmond's Mapping Inequality HOLC
  digitization; committed sample datasets are illustrative, matching the convention
  `data/context_layers.geojson` already set
  ([ADR 0014](docs/decisions/0014-exposure-brief-and-equity-context.md)).

### Fixed

- **Live-demo cooling centers.** The GitHub Pages build now excludes the explicitly illustrative
  cooling-center dataset, evicts previously cached copies, and fails before upload if any copy
  remains. The dataset stays available to the synthetic/local demo; a public deployment must provide
  a jurisdiction-verified replacement.
- **Dashboard readable by the browser accessibility scanner.** The map markers' severity texture and
  the exposure braid's reference grid are now painted as the elements' own `background-image` layers
  instead of `content:""` `::before` overlays. The overlay construct made axe-core's `color-contrast`
  rule report "cantTell" (`pseudoContent`) on every marker reading and axis label, which the
  `a11y-advisory` gate treats as an error; the readings are dark-on-light and clear AA (zero real
  contrast violations). The visual is unchanged and the not-colour-alone texture is preserved. The
  CI gate now serves `web/` over HTTP so it scans the rendered map (a `file://` scan never loaded the
  surface data), and its committed [`.pa11y.json`](.pa11y.json) scopes a color-contrast exclusion to
  the data-viz text only, where axe still returns cantTell for overlapping markers (`bgOverlap`) and
  SVG chart labels (`imgNode`) — documented engine limitations, not page defects. Rationale and
  evidence: [`docs/audits/accessibility-report.md`](docs/audits/accessibility-report.md).

### Fixed

- **Truthful California OpenAQ scope.** Bbox candidates now pass a packaged U.S. Census California
  MultiPolygon before they consume the site cap, trigger a latest-reading request, or enter the
  generated network. This excludes nearby Arizona, Nevada, and Oregon monitors from California
  counts and surfaces, versions accumulated scope/cache state, and publishes accepted locations on
  the normal coarse grid rather than treating upstream coordinates as host consent for precision
  ([ADR 0022](docs/decisions/0022-california-boundary-filter.md)).

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
