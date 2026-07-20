# Data card: community-operated swelter observations

## Motivation and ownership

A hosting collective measures neighborhood heat and air conditions using devices it operates. The
collective controls siting, precision, calibration, publication, and whether it has authority to
dedicate the observations to CC0. The reference repository is tooling, not the data controller for a
third party's deployment.

## Composition

Long-format observations contain a collective-assigned node id, UTC timestamp, parameter, numeric
value, unit, calibration state/version, QC verdict, and optional uncertainty. Supported measurements
include temperature, relative humidity, PM2.5, PM10, optional NO2, and derived heat index/estimated
shade WBGT. Aggregation may also emit compound exposure rows. The observation record has no person,
account, MAC address, contact field, or coordinate; node placement is stored separately in operator
configuration.

## Collection and processing

Firmware samples environmental sensors and may buffer payloads during connectivity loss. The
operator-side `ingest-serve` listener authenticates a fresh request with per-node HMAC before passing
it through normal validation, quarantine, QC, and idempotent SQLite insertion. Calibration fits are
versioned from co-location evidence. Public surfaces use the host-approved location mode—coarse grid
by default—and aggregate by published cell and hour.

## Uses and limits

Intended for community awareness, research, journalism, stewardship, and advocacy. It is not a
regulatory monitor, medical advice, an individual safety determination, or a person-tracking system.
Raw/uncalibrated and stale values remain provisional. Estimated shade WBGT is not an instrumented
black-globe measurement.

## Distribution and license

When the collective owns the relevant rights and chooses the repository default, first-party
observations and their generated aggregates are dedicated under CC0-1.0. Code remains Apache-2.0.
The dedication does not reach third-party provider data or context layers merely because swelter
processed them.

## Maintenance and retention

The local steward owns retention and backups. Raw rows are append-only; derived rows can be rebuilt.
Snapshots record hashes and coverage. Exact node coordinates and HMAC keys remain operator-local and
outside exported observations. Review calibration on the cadence in `docs/calibration.md`, source
freshness per deployment, and this card each release.

Owner: hosting collective's data steward. Last verified: 2026-07-16. Recheck cadence: each release,
schema change, new parameter, or governance/license change.
