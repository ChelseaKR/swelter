# Architecture decision records

Decisions of record for swelter, a community heat and air-quality sensing
network. Each ADR captures one decision, why it was made, and what it costs.
Format: `# ADR NNNN: <decision>`, then `## Decision`, `## Why`, and
`## Known weakness / Consequences`. Accepted records are not edited in place; a
later ADR supersedes an earlier one.

| ADR | Decision | Status |
| --- | --- | --- |
| [0001](0001-sqlite-and-files-store.md) | Store observations in a copyable SQLite-and-files folder, not a database cluster | accepted |
| [0002](0002-calibration-as-versioned-data.md) | Keep calibration corrections as versioned data with an audit trail, not as code | accepted |
| [0003](0003-grid-snapped-public-locations.md) | Publish grid-snapped locations by default; precise coordinates are opt-in | accepted |
| [0004](0004-framework-free-accessible-dashboard.md) | Ship a framework-free dashboard with three equal views, held to WCAG 2.2 AA | accepted |
| [0005](0005-read-only-stdlib-server.md) | Serve over a single-threaded, GET-only stdlib HTTP server | accepted |
| [0006](0006-apache-code-cc0-data.md) | License the code Apache-2.0 and the observations CC0-1.0 | accepted |
| [0007](0007-ogc-sensorthings-export.md) | Expose a read-only OGC SensorThings 1.1 subset for interoperability | accepted |
| [0008](0008-market-position-trust-layer.md) | Position swelter as the open trust layer for neighborhood heat-and-air, and hold claim discipline | accepted |
| [0009](0009-compound-heat-air-exposure-surface.md) | Add a compound heat-and-air exposure surface as the flagship differentiating feature | accepted |
| [0010](0010-neighborhood-alerts-feed.md) | Deliver neighborhood heat/AQI alerts as a generated public feed, not a subscriber list | accepted |
| [0011](0011-cooling-center-overlay.md) | Add a curated, provenance-bearing cooling-center overlay with accessible list parity | accepted |
| [0012](0012-gate-bypass-incident-and-ruleset.md) | Incident note: the 2026-07-02 gate bypass, and the branch-protection ruleset that should prevent recurrence | accepted |
| [0013](0013-accumulating-fetch-store-via-actions-cache.md) | `swelter fetch --accumulate` persists the demo store via a GitHub Actions cache | accepted |
| [0018](0018-strict-config-doctor.md) | Validate `network.yaml` loudly and add a `swelter doctor` gate | accepted |
