# Changelog

All notable changes to swelter are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the public API/data schema follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html) as scoped in
[`docs/VERSIONING.md`](docs/VERSIONING.md).

## [Unreleased]

### Added

- **Event chronicle generator.** `swelter chronicle --from <ISO> --to <ISO>` composes the aggregated
  surface, `qc.detect_gaps`, and `qc.coverage_equity` into a citable post-event Markdown chronicle:
  Danger/Extreme-Danger and compound-exposure cell-hours per published cell, the calibrated-vs-
  provisional coverage share carried in the headline, and an always-present "what the network could
  not see" section. Descriptive counts only — no health-outcome attribution and no neighborhood
  ranking ([ADR 0027](docs/adr/0027-event-chronicle.md)).

### Fixed

- **Dense map markers are accessible targets (WCAG 2.5.8).** On a dense network the map previously
  reprojected up to ~150 readings on top of one another, so many markers fell below the 24px
  target-size/offset floor — a serious axe violation exposed on the `/sensors/` route and latent on
  `/`. `renderMap` now runs a deterministic collision relaxation that separates overlapping markers on
  their axis of least overlap until every 28px marker box clears its neighbours, keeps each marker near
  its true cell, and routes them clear of the overlaid zoom/reset controls. No reading is dropped,
  merged, or hidden: the map still exposes the complete record set and the equivalence-locked List and
  Table keep exact coordinates. See
  [`docs/audits/accessibility-report.md`](docs/audits/accessibility-report.md).
- **`/sensors/` layout stability (WCAG-adjacent, CLS).** The resident-facing Now card filled from short
  HTML placeholders a frame late, shoving the blocks below it (Lighthouse CLS 0.133). Its answer,
  temporal line, guidance, and status now reserve their heights, the card paints in the first
  synchronous render pass, and the boot fetches run in parallel; measured CLS drops to <0.06 on
  `/sensors/` and stays <0.02 on `/`.
- **Dark-mode severity-chip contrast.** The table's AQI/heat severity chips inherited the scheme
  foreground (near-white in dark mode) over their light severity fill — a genuine contrast failure the
  chips' pattern was hiding from the contrast scanner. They now use the permanent dark `--severity-ink`
  like the map cells, clearing AA in both colour schemes.
- **Verifiable selected-row contrast.** The selected List/Table row highlight is a flat, computable
  tint instead of a gradient, so a contrast scanner can read every reading in the selected row.
- **Reflow at 320px.** The `#method` legend and dataset card no longer stay side by side below the
  mobile breakpoint (a class-selector specificity gap left `.legend`/`.dataset-truth` pinned), so the
  13rem legend columns no longer overflow a 320px viewport (WCAG 1.4.10).
- **Skip link visible on focus.** The skip link uses fixed positioning and reveals instantly (no slide
  transition), so it is exposed at the viewport top when focused regardless of scroll.

### Changed

- **Browser accessibility gate.** The Playwright conformance suite allowlists only patterned-severity
  `color-contrast` *incomplete* results (map cells, braid labels, and severity chips) and the known
  axe `target-size` engine error on grid cells — never a real violation — and independently verifies a
  severity chip's 4.5:1 contrast pair. Cross-browser and copy-drift test fixes: the Now heading assertion
  tracks the current Spanish catalog, the record-set check keeps the published `label`, selection
  assertions target the pressable control, disabled controls are excluded from the focus-exposure sweep,
  and the map-reset transform assertion accepts Firefox's `translate(0px)` serialisation. See
  [`docs/audits/accessibility-report.md`](docs/audits/accessibility-report.md) for the rationale; the
  dense-marker target-size defect it described on the `/sensors/` route is now fixed (see above).

The dated `0.1.0` section is prepared release metadata; it does not assert that a Git tag or GitHub
Release exists. Publication completes only after the annotated `v0.1.0` tag passes the release
workflow.

## [0.1.0] - 2026-07-16

First public reference release: a community-operated sensing pipeline, calibration evidence model,
accessible bilingual observatory, open read/export surfaces, and portfolio-standard operational and
responsible-technology evidence.

### Added

- **Now + Explore observatory.** A resident-first current-conditions view and an analytical workspace
  with linked native-SVG history, location distribution, evidence inspector, map, sortable table, and
  plain list. Missing buckets render as gaps; uncertainty, provisional state, source, freshness, and
  time-window caveats travel with each representation ([ADR 0004](docs/adr/0004-framework-free-accessible-dashboard.md)).
- **Environmental pipeline.** Idempotent ingest, quarantine, range/spike/flatline QC, gap and health
  reporting, immutable raw rows, versioned calibration corrections, gridded aggregation, compound
  heat/air exposure, estimated-WBGT labelling, and deterministic demo/rebuild paths.
- **Authenticated node write boundary.** A separate HMAC-SHA256 ingest listener with per-node keys,
  freshness/replay checks, impersonation refusal, key rotation, and quarantine for authentication
  failures. The public server remains GET-only.
- **Open read and publication surfaces.** CSV/JSON, a read-only OGC SensorThings 1.1 subset,
  static-site publication with a content manifest, citable data snapshots, alerts in JSON/Atom, and
  source-aware exports.
- **Live-source adapters.** OpenAQ, Copernicus CAMS/weather through Open-Meteo, and Sensor.Community,
  plus deterministic synthetic data. California OpenAQ discovery is boundary-filtered before caps
  or publication ([ADR 0022](docs/adr/0022-california-boundary-filter.md)).
- **Source-license provenance.** Source data cards, source-specific attribution/terms, and a fail-
  closed OpenAQ `source-license-ledger.json` publication contract. First-party/project-authored CC0
  no longer overwrites third-party rights ([ADR 0024](docs/adr/0024-preserve-source-specific-data-terms.md)).
- **Action and context layers.** Neighborhood danger-threshold alert feeds, provenance-bearing
  cooling-center data with accessible list parity, tree-canopy context, and a descriptive exposure
  brief with sourced AC-access and historical-redlining context. Illustrative fixtures are barred
  from production publication.
- **Accessibility and language gates.** Equivalent map/table/list outcomes, keyboard and reduced-
  motion behavior, non-color severity, English/Spanish parity, BCP-47/UTF-8/CLDR checks, structural
  WCAG checks, and real-browser CI. Current manual assistive-technology and independent Spanish
  release signoff remains tracked in issue #106 rather than inferred from automation.
- **Operational evidence.** A definition of done, acceptance-test map, DORA baseline, MADR-compatible
  decision log, source data cards, DPIA, data-flow inventory, threat model, fairness and ethics scans,
  residual-risk register, standards-pin evidence, and incident/recovery runbooks.
- **Quality and supply-chain gates.** Strict typing, formatting/lint/security/complexity checks,
  branch coverage, Python and web suites, documentation/standards drift checks, dependency and secret
  scanning, workflow analysis, release artifact signing/provenance, and consumer verification.

### Changed

- Reframed the project around a traceable measurement-to-claim path and community portability instead
  of treating the map as the product.
- Made SQLite plus generated files the explicit shipped store; Parquet/Arrow remains an unimplemented
  protocol extension.
- Made observation identity source-qualified and added a fail-closed transactional migration for
  pre-contract stores, including collision checks and atomic integrity-chain regeneration
  ([ADR 0024](docs/adr/0024-preserve-source-specific-data-terms.md)).
- Added pinned structured logging and a deterministic vendored MessageFormat build while retaining
  the standard-library server and framework-free browser architecture
  ([ADR 0025](docs/adr/0025-pinned-structured-logging.md),
  [ADR 0026](docs/adr/0026-vendored-messageformat-runtime.md)).
- Moved the authoritative architecture decision log from the legacy house-format `docs/decisions/`
  paths to `docs/adr/` while preserving old URLs. The historical context-layer collision moved from
  ADR 0013 to ADR 0023; accumulation/cache remains ADR 0013.
- Replaced blanket observation-data CC0 wording with a rights boundary that distinguishes authorized
  first-party, synthetic, fetched-provider, and context/reference data.

### Fixed

- Prevented raw and calibrated observations from being silently mixed in aggregation and publication.
- Prevented OpenAQ bounding-box spillover from being described as California and ensured retained
  locations use the normal public privacy grid.
- Prevented illustrative cooling-center/context fixtures and incomplete OpenAQ rights metadata from
  entering production artifacts.
- Added timeout, cache-invalidation, conditional-request, and stale-publication behavior to the
  read/static paths while preserving the single-reader design.
- Removed stale test counts, false current Parquet/latency/OTA claims, duplicated changelog sections,
  and unsupported manual accessibility/translation assertions from release-facing documentation.

### Security

- Added authenticated ingest, strict read/write separation, dependency/workflow/secret/static
  analysis, log-safety checks, least-privilege workflow defaults, signed release artifacts, build
  provenance, SBOM generation, and documented rollback/incident paths.
- Documented browser geolocation, local preference storage, service-worker/static caches, source
  adapters, GitHub Actions caches, precise node coordinates, and generated publication artifacts as
  explicit trust boundaries.
- The repository/Pages governance exception intentionally excluded from this remediation remains
  tracked in [issue #105](https://github.com/ChelseaKR/swelter/issues/105).

[Unreleased]: https://github.com/ChelseaKR/swelter/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/ChelseaKR/swelter/releases/tag/v0.1.0
