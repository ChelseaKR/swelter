# Architecture decision records

docs/adr/ is the source of record for accepted architecture decisions. Records use a compact
MADR-compatible structure: status, date, deciders, context, decision, and consequences. Accepted
records are append-only; a material reversal gets a new ADR that supersedes the old one.

Copy [`template.md`](template.md) for a new record, assign the next unused number, and keep every
field concrete enough for a reviewer to compare with the implementation.

The earlier docs/decisions/ paths remain in the repository so bookmarks and historical review
links do not break. New links and new decisions must use this directory.

## Numbering

ADR 0013 was historically assigned to two records. The accumulation/cache decision keeps 0013
because deployed workflow and CLI commentary already cite it. The context-layer overlay is now ADR
0023. The legacy file at docs/decisions/0013-context-layer-overlay.md remains as historical
evidence of the collision.

## Index

- [ADR 0000 — Record architecture decisions](0000-record-architecture-decisions.md)
- [ADR 0001: Store observations in a copyable SQLite-and-files folder, not a database cluster](0001-sqlite-and-files-store.md) — identity posture superseded by ADR 0024; dependency-count posture superseded by ADR 0025
- [ADR 0002: Keep calibration corrections as versioned data with an audit trail, not as code](0002-calibration-as-versioned-data.md)
- [ADR 0003: Publish grid-snapped locations by default; precise coordinates are opt-in](0003-grid-snapped-public-locations.md)
- [ADR 0004: Ship a framework-free dashboard with three equal views, targeting WCAG 2.2 AA](0004-framework-free-accessible-dashboard.md) — build/runtime-dependency posture superseded by ADR 0026; schematic/collision-relaxation map posture superseded by ADR 0033
- [ADR 0005: Serve over a single-threaded, GET-only stdlib HTTP server](0005-read-only-stdlib-server.md) — dependency-count posture superseded by ADR 0025
- [ADR 0006: License code under Apache-2.0 and observations under CC0-1.0](0006-apache-code-cc0-data.md) — superseded by ADR 0024
- [ADR 0007: Expose a read-only OGC SensorThings 1.1 subset for interoperability](0007-ogc-sensorthings-export.md)
- [ADR 0008: Position swelter as the open trust layer for neighborhood heat-and-air, and hold claim discipline](0008-market-position-trust-layer.md)
- [ADR 0009: Add a compound heat-and-air exposure surface as the flagship differentiating feature](0009-compound-heat-air-exposure-surface.md)
- [ADR 0010: Deliver neighborhood heat/AQI alerts as a generated public feed, not a subscriber list](0010-neighborhood-alerts-feed.md)
- [ADR 0011: Add a curated, provenance-bearing cooling-center overlay with accessible list parity](0011-cooling-center-overlay.md)
- [ADR 0012: Incident note — the 2026-07-02 gate bypass and the ruleset that should prevent recurrence](0012-gate-bypass-incident-and-ruleset.md)
- [ADR 0013: `swelter fetch --accumulate` persists the demo store via a GitHub Actions cache](0013-accumulating-fetch-store-via-actions-cache.md) — identity posture superseded by ADR 0024
- [ADR 0014: Derive calibrated heat index from calibrated temperature, don't fit it](0014-heat-index-derived-from-calibrated.md)
- [ADR 0015: Validate `network.yaml` loudly, and add a `swelter doctor` gate](0015-strict-config-doctor.md)
- [ADR 0016: Bake the provisional label and hourly-window caveat into share-card pixels, not overlaid HTML](0016-caveat-baked-share-card.md)
- [ADR 0017: Key calibration families by (parameter, sensor model), not parameter alone](0017-sensor-model-calibration-families.md)
- [ADR 0018: Historical Danger-day counts plus sourced canopy/AC-access/redlining context (E1)](0018-exposure-brief-and-equity-context.md)
- [ADR 0019: Ship an estimated WBGT parameter, without guidance bands](0019-estimated-wbgt.md)
- [ADR 0020: Promote the Pages bash choreography into a tested `swelter publish` command](0020-static-publish-command.md)
- [ADR 0021: Lead with "register your own network" as the headline capability](0021-register-your-own-network-headline.md)
- [ADR 0022: Filter California OpenAQ discovery against a Census boundary](0022-california-boundary-filter.md)
- [ADR 0023: Add a curated, descriptive-only context-layer overlay, starting with tree canopy](0023-context-layer-overlay.md)
- [ADR 0024: Preserve source-specific data terms through every release surface](0024-preserve-source-specific-data-terms.md)
- [ADR 0025: Add pinned structured logging without changing the stdlib server architecture](0025-pinned-structured-logging.md)
- [ADR 0026: Compile and vendor MessageFormat without adopting a frontend framework](0026-vendored-messageformat-runtime.md)
- [ADR 0027: Generate a citable post-event chronicle, descriptive counts only](0027-event-chronicle.md)
- [ADR 0028: Surface correction-drift age in the health report, without changing any calibrated value](0028-calibration-drift-surveillance.md)
- [ADR 0029: Map suspicious-QC readings as visible provisional, never blank the map during an event](0029-event-aware-qc-visible-provisional.md)
- [ADR 0030: Derive a "cross-checked" drift smoke-alarm from twin agreement, never a calibration tier](0030-sensor-twin-crosschecked-tier.md)
- [ADR 0031: Generalize the alert layer into versioned hazard packs, and ship a cold pack](0031-multi-hazard-packs.md)
- [ADR 0032: Assemble co-location training pairs from a reference-monitor feed](0032-reference-monitor-adapter.md)
- [ADR 0033: Preserve statewide geography and cluster only the overview](0033-statewide-geographic-map-clustering.md)
- [ADR 0034: A refused fetch is not an empty area](0034-a-refused-fetch-is-not-an-empty-area.md)
- [ADR 0035: Bind alerts to the surface's newest bucket, not an unbounded latest-per-cell scan](0035-alerts-bound-to-the-surfaces-newest-bucket.md)
- [ADR 0036: Publish the absence when an area stops reporting, instead of going quiet about it](0036-published-absence-for-areas-that-stop-reporting.md)
- [ADR 0037: Absence is never published as a number, and never narrows an interval](0037-absence-is-never-published-as-a-number.md)
