# swelter versioning policy

swelter follows [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html). Two surfaces
carry independent compatibility promises and are versioned under the same policy:

1. The **public read-only API** — the OGC SensorThings 1.1 subset and the CSV/JSON export shape.
2. The **data schema** — the observation fields, the store layout, and the correction-registry
   format.

A given `MAJOR.MINOR.PATCH` release of the `swelter` package states both. They can move at different
rates: a release may bump the API contract without touching the schema, or the reverse. When they
diverge in practice, the changelog and release notes state each surface's effective compatibility
level for that release.

The package version today is `0.1.0`. Pre-1.0, the spirit of the policy below holds, but a breaking
change may ship in a MINOR bump; the changelog calls out every breaking change explicitly regardless
of the version digits.

Author: Chelsea Kelly-Reif. Year: 2026.

## The three change levels

- **MAJOR** — a breaking change to either surface, as defined below. A consumer's existing client
  or saved query, or a community's stored archive, may stop working without action.
- **MINOR** — backward-compatible additions: a new endpoint, a new query parameter with a safe
  default, a new optional observation field, a new correction method, a new parameter in the
  registry. Existing consumers keep working untouched.
- **PATCH** — bug fixes and clarifications that change neither surface's contract: a corrected error
  message, a documentation fix, a performance change with identical output.

## Public API — what counts as breaking

The public API is the read-only surface in `src/swelter/api.py` and `src/swelter/server.py`: the
SensorThings 1.1 subset (`/v1.1`, `/v1.1/Things`, `/v1.1/ObservedProperties`, `/v1.1/Observations`),
the surface endpoints (`/api/surface.geojson`, `/api/surface.json`), the export endpoints
(`/export.csv`, `/export.json`), and `/health`. The contract includes the route set, the response
JSON structure and field names, the CSV column set and order, the query parameters and their
defaults, and the read-only guarantee (`serverSettings.readOnly: true`; writes return 405).

Breaking (MAJOR):

- Removing or renaming an endpoint, or removing a SensorThings entity from the service document.
- Removing or renaming a field in a response object — for example dropping `phenomenonTime`,
  `result`, or `resultQuality` from an Observation, or renaming a key inside `parameters` or
  `properties`.
- Removing or reordering a column in `/export.csv`, or renaming a CSV column. The CSV column order
  (`node_id, timestamp, parameter, value, unit, calibration, qc, uncertainty`) is part of the
  contract because consumers parse positionally.
- Changing the meaning, type, or units of an existing field — for example changing a `result` from
  a number to a string, or a `phenomenonTime` away from ISO-8601 UTC (`...Z`).
- Removing or changing the default of a query parameter in a way that changes existing results
  (e.g. changing the default `top`, or `hours` on `/api/surface.json`, such that a saved query
  returns different data).
- Weakening the read-only guarantee, or removing the open-CORS / `readOnly: true` advertisement that
  clients rely on.
- Dropping the `@iot.id` / `@iot.count` / `@iot.navigationLink` keys that make the surface a valid
  SensorThings subset.

Non-breaking (MINOR or PATCH):

- Adding a new endpoint, a new SensorThings entity, or a new field to an existing response object.
- Adding a new query parameter whose default preserves current behavior.
- Adding a new value to an open set already documented as extensible (a new observed property, a new
  correction method, a new QC verdict appearing in `resultQuality.qc`) — see the schema section,
  which governs the underlying data.
- Adding a CSV column **at the end** is treated as breaking for positional parsers and so is MAJOR;
  prefer JSON for additive needs.

## Data schema — what counts as breaking

The data schema is the shape of the data itself, independent of how it is served. It has three
parts.

### Observation fields

The `Observation` record (`src/swelter/models.py`): `node_id`, `timestamp` (ISO-8601 UTC `...Z`),
`parameter`, `value`, `unit`, `calibration` (`raw` or a correction version id), `qc`, `uncertainty`
(1-sigma in `unit`, or null). The idempotent store key is
`(node_id, timestamp, parameter, calibration)`; `content_hash()` is a SHA-256 over the value-bearing
fields.

Breaking (MAJOR):

- Removing or renaming a field, or changing its type or units.
- Changing the timestamp format away from `YYYY-MM-DDTHH:MM:SSZ`.
- Changing the store key tuple, or changing what `content_hash()` covers, so a previously written
  archive no longer dedups or verifies against the new code.
- Adding a **required** field that an existing archive cannot supply.
- Adding any field capable of holding a person or a per-device identifier. This is forbidden by a
  hard rule (no surveillance, by construction), not merely a version bump: such a PR fails review.

Non-breaking (MINOR):

- Adding a new **optional** observation field with a safe default (mirroring how `uncertainty` is
  null when raw).
- Adding a new value to an extensible set: a new entry in `PARAMETERS` (with its unit and valid
  range), or a new QC verdict alongside `ok`, `range`, `spike`, `flatline`, `missing`. Consumers
  that switch on these sets are expected to tolerate unknown values; the docs say so.

### Store layout

The store is a copyable folder (`src/swelter/store.py`): `observations.db` (SQLite, Datasette-
openable), `quarantine.jsonl`, `aggregate.geojson`, `corrections.yaml`. Raw observations are
append-only; `drop_calibrated()` drops the derived (non-raw) records so they can be rebuilt from raw.

Breaking (MAJOR):

- Renaming or removing a file in the store folder, or changing the `observations.db` table/column
  names that Datasette and direct SQLite readers depend on.
- Changing the layout such that an archive written by an older release can no longer be opened or
  rebuilt by the new code.
- Making the raw table no longer append-only, or making `drop_calibrated()` touch raw rows.

Non-breaking (MINOR or PATCH):

- Adding a new derived file or a new column that older readers can ignore.
- A pluggable backend (e.g. a Parquet store) implementing the same `Store` protocol — additive, not
  a change to the existing SQLite layout.

### Correction-registry format

`corrections.yaml` / `CorrectionRegistry` (`src/swelter/calibrate.py`): a top-level `version` and a
list of corrections, each with a `version` id of the form `{parameter}.{method}.{node_id}`,
`node_id`, `parameter`, `method` (`epa-humidity`, `enclosure-offset`, `linear`), `predictors`,
`coefficients` (rounded to 6 dp), `intercept`, `residual_std`, `r2`, `n`, `reference`,
`window_start`, `window_end`.

Breaking (MAJOR):

- Bumping the registry's top-level `version` integer — that is the format version, and an increment
  signals a format a previous loader cannot read.
- Removing or renaming a per-correction field, or changing the version-id format
  (`{parameter}.{method}.{node_id}`).
- Changing how coefficients are rounded (6 dp), since byte-for-byte reproducibility of the committed
  registry is a published guarantee and a CI gate; a rounding change re-writes every committed
  registry.

Non-breaking (MINOR):

- Adding a new correction `method` to the documented set.
- Adding a new optional per-correction field that older loaders ignore.

A correction is itself versioned data, not code: re-co-locating a node and re-fitting produces a new
correction under the same version-id scheme, recorded with its window — an audit trail, not a schema
change.

## Deprecation path

The same path applies to both surfaces.

1. **Announce.** A field, endpoint, query parameter, or format that will be removed is marked
   deprecated in `api.md` (for the API) or in this file and the changelog (for the schema), in the
   release that introduces the deprecation, with the reason and the replacement.
2. **Keep it working.** Deprecated surface keeps functioning unchanged for at least one full MINOR
   release line after the announcement. Deprecation alone never changes behavior.
3. **Remove on a MAJOR.** Removal happens only on a MAJOR bump, and the changelog lists every removed
   item under "Breaking changes" with the migration step.
4. **Data outlives code.** Because the archive is a copyable folder of open formats (CC0
   observations), a community can always read an older archive with the matching older release even
   after a MAJOR moves on. Export is first-class precisely so no version bump can strand a
   community's data.

## Recorded changes since 0.1.0

This section applies the policy above to the concrete surface and data-quality changes made after
`0.1.0`. They are recorded here, ahead of the release that ships them, so the compatibility level of
each change is unambiguous before the version digits move.

### Additive surface/API fields — MINOR (backward compatible)

These are additions: new fields and collections alongside the existing ones, each with a default
that preserves current behavior. A consumer that ignores them keeps working untouched, so under the
rules above ("Public API — what counts as breaking", "Adding a new field to an existing response
object") they are **MINOR**, not breaking.

- **Aggregate / surface fields.** Each cell now carries its host-assigned `label` (the named block),
  a calibrated 1-sigma `uncertainty` (`null` when the cell is provisional), and
  `aqi_window = "hourly-mean"` (disclosing that the published AQI is an hourly mean, not a 24-hour
  NowCast). On `/api/surface.json?hours=N` cells these appear as `label`, `uncertainty`, `aqi`
  (PM2.5), `aqi_window`, and `provisional`. `/api/surface.geojson` (served as
  `application/geo+json`) gains `label` and, per parameter, `*_uncertainty` and `*_provisional`
  properties. All are new keys; nothing existing was removed, renamed, or retyped.
- **SensorThings pagination and new collections.** `/v1.1/Observations` gains `$top`/`$skip` (and
  the bare `top`/`skip`) with a true `@iot.count` and an `@iot.nextLink`; the default page preserves
  the prior result set, so a saved query is unaffected. `resultQuality` gains an `uncertainty` and a
  `trustworthy` flag alongside the existing `qc`. Two new collections, `/v1.1/Datastreams` and
  `/v1.1/Locations`, join the service document. Adding an endpoint, a query parameter with a safe
  default, and a field to a response object are all explicitly MINOR above.

### The CSV `trustworthy` column — additive in shape, but flagged

The export CSV gained a final `trustworthy` column: the order is now
`node_id, timestamp, parameter, value, unit, calibration, qc, uncertainty, trustworthy`. JSON
observations gained the same `trustworthy` field, and that JSON addition is plainly MINOR.

The CSV column is the one place where "additive" and "backward-compatible" come apart under this
policy. The section above states deliberately that **adding a CSV column at the end is treated as
breaking for positional parsers and so is MAJOR**, because the CSV column set and order are part of
the contract that consumers parse positionally. A parser that hard-codes "8 columns" or reads only
through `uncertainty` is unaffected; a parser that asserts the exact column count is not. It is
recorded here explicitly rather than waved through as minor, and consumers with additive needs are
pointed at the JSON export (where `trustworthy` is unambiguously MINOR), consistent with the
guidance above.

### Heat-index plausibility ceiling (60 degC) — data-quality fix, PATCH

The QC plausibility ceiling for `heat_index_c` is 60 degC (the parameter's upper valid range,
about 137 degF — the NWS heat-index ceiling). This is a **data-quality fix**: it tightens which
raw values QC accepts as physically plausible, so QC-rejected values never reach the surface. It
changes neither surface's contract — no field, type, unit, route, query parameter, or column moves,
and the `heat_index_c` parameter, its `degC` unit, and its valid range are unchanged in shape. It
only improves the data flowing through the unchanged shape, which is the definition of **PATCH**
above ("bug fixes ... that change neither surface's contract"). The same plausible-range gate
applies to every parameter; this records the heat-index ceiling specifically.

## Where this is recorded

Every release records its API and schema compatibility level in the changelog and release notes.
Breaking changes are never silent: they are named, with a migration step, before the version digits
are trusted.

Last verified: 2026-06-17. Recheck cadence: review on each release, and whenever the SensorThings
subset, the export shape, the observation fields, the store layout, or the correction-registry
format change.
