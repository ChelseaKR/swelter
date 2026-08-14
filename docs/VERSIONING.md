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
  (`node_id, timestamp, parameter, value, unit, source, calibration, qc, uncertainty, trustworthy,
  data_license, data_attribution`) is part of the contract because consumers parse positionally.
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
`parameter`, `value`, `unit`, `source`, `calibration` (`raw` or a correction version id), `qc`,
`uncertainty` (1-sigma in `unit`, or null). The idempotent store key is
`(node_id, timestamp, parameter, source, calibration)`; `content_hash()` is a SHA-256 over the
value-bearing fields, including `source`.

`uncertainty` is null **only** on a raw row. A calibrated observation must carry a 1-sigma, and one
without is refused at construction and on store read (ADR 0035): a correction is fitted with a
`residual_std`, so an absent uncertainty on a calibrated row is a broken row, not a zero-uncertainty
one, and reading it as zero published a *narrower* error bar than the evidence supported. Relaxing
this — allowing a calibrated row with a null uncertainty again — would be breaking (MAJOR), because
a consumer may now rely on a calibrated row having an error bar.

The 0.1.0 release candidate is the first public contract with source-qualified identity. Opening a
pre-contract SQLite store runs one transactional migration: strict legacy markers infer only known
native, OpenAQ, Sensor.Community, or CAMS sources; ambiguous or conflicting rows fail closed; the
new table is collision-checked before the old table is dropped; content hashes and `digests.jsonl`
are rebuilt together. Any failure rolls the database and integrity chain back. The migration is
covered by `tests/test_store.py`; after 0.1.0, another identity change is MAJOR and needs a new,
documented migration.

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

## The published data dictionary and `data_schema_version`

`GET /api/schema.json` (`src/swelter/dictionary.py`) publishes a machine-readable data dictionary
— the observation fields, the `/export.csv` column set, the `PARAMETERS` registry, and the QC
verdicts — generated from the same constants the pipeline runs on, so it cannot drift from this
document or from the running code. It carries an integer `data_schema_version` (starting at `1`,
independent of the package's `MAJOR.MINOR.PATCH`) that is the pin target for an integrator who
wants a cheap, machine-checkable signal that the data schema underneath them changed: poll
`/api/schema.json` (or read `serverSettings.dataSchemaVersion` off `GET /v1.1`) and compare against
the value last seen.

Bumping `DATA_SCHEMA_VERSION` follows exactly the "Data schema — what counts as breaking" rules
above: it moves only when a change to the observation fields, the CSV column set/order, or a QC
verdict's meaning would be MAJOR under those rules. A MINOR, additive change to the schema (a new
optional field, a new `PARAMETERS` entry, a new QC verdict) does **not** require bumping the
integer — the dictionary's contents change to reflect the addition, but the version number is
reserved for breaking schema changes, matching how the rest of this policy treats additive changes
as non-breaking.

## Deprecation path

The same path applies to both surfaces.

1. **Announce.** A field, endpoint, query parameter, or format that will be removed is marked
   deprecated in `api.md` (for the API) or in this file and the changelog (for the schema), in the
   release that introduces the deprecation, with the reason and the replacement.
2. **Keep it working.** Deprecated surface keeps functioning unchanged for at least one full MINOR
   release line after the announcement. Deprecation alone never changes behavior.
3. **Remove on a MAJOR.** Removal happens only on a MAJOR bump, and the changelog lists every removed
   item under "Breaking changes" with the migration step.
4. **Data outlives code.** Because the archive is a copyable folder of open formats with its
   source-specific license and attribution evidence, a community can always read an older archive
   with the matching older release even after a MAJOR moves on. Export is first-class precisely so
   no version bump can strand a community's data. CC0 applies only to authorized first-party or
   project-authored data; fetched records retain provider terms.

## Compatibility decisions in the 0.1.0 release candidate

No `v0.1.0` tag or public package release predates these changes. This section records how the
release-candidate surface became the initial `0.1.0` contract; it does not claim that an already
published `0.1.0` contract was changed in place. The classifications show the version impact the
same change would have after the first release.

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
- **`mean_member_sigma`, EPA NowCast, and the exposure `uncertainty_note`.** Each calibrated cell
  now also carries `mean_member_sigma` (the plain mean of the contributing members' 1-sigmas — the
  old mean-of-sigmas number, kept under its own new name). A PM2.5 cell with at least 3 of the
  preceding 12 hourly means available additionally gets a second `pm25_ugm3` reading tagged
  `aqi_window = "nowcast"` (an EPA NowCast-weighted AQI, alongside the unchanged `"hourly-mean"`
  reading — `/api/surface.geojson` never surfaces the NowCast variant, so the map snapshot's
  existing behavior is untouched). The derived `exposure` cell gains `uncertainty_note` (which
  component bounds the published level). All are new keys; nothing existing was removed, renamed,
  or retyped.
- **SensorThings pagination and new collections.** `/v1.1/Observations` gains `$top`/`$skip` (and
  the bare `top`/`skip`) with a true `@iot.count` and an `@iot.nextLink`; the default page preserves
  the prior result set, so a saved query is unaffected. `resultQuality` gains an `uncertainty` and a
  `trustworthy` flag alongside the existing `qc`. Two new collections, `/v1.1/Datastreams` and
  `/v1.1/Locations`, join the service document. Adding an endpoint, a query parameter with a safe
  default, and a field to a response object are all explicitly MINOR above.

### Cell `uncertainty` means the cell's standard error — future MAJOR if redefined

Every calibrated surface cell's `uncertainty` field (on `/api/surface.json` records and the
`{param}_uncertainty` properties on `/api/surface.geojson`) used to be the plain mean of the
contributing members' 1-sigmas. It now holds the cell's own standard error,
`sqrt(sum(sigma_i^2)) / n`, over those same member sigmas — a smaller number for any cell with more
than one calibrated member, and a *different* number even for a single-member cell only by
coincidence of arithmetic (`n=1` makes the two formulas equal). The key, type, and units are
unchanged, but the value a consumer reads today at that key means something different than it did
before this correction. Because no public release predates the correction, standard error is the
initial `0.1.0` meaning. After release, silently reinterpreting that number under the same key would
be MAJOR even if the type and units stayed unchanged. The former mean-of-sigmas quantity remains
available under the unambiguous `mean_member_sigma` key.

### The CSV `trustworthy` column — initial contract; future addition would be MAJOR

The `0.1.0` export CSV includes a `trustworthy` column: the order is
`node_id, timestamp, parameter, value, unit, source, calibration, qc, uncertainty, trustworthy`.
JSON
observations gained the same `trustworthy` field, and that JSON addition is plainly MINOR.

Because this is the first public contract, its inclusion does not break a released positional
parser. After `0.1.0`, however, even appending a CSV column is MAJOR under this policy; JSON remains
the preferred additive format.

### `/api/schema.json` and `serverSettings.dataSchemaVersion` — MINOR (backward compatible)

A new endpoint (`GET /api/schema.json`, the generated data dictionary) and a new field on an
existing response object (`serverSettings.dataSchemaVersion` on `GET /v1.1`). Both are additions: no
existing endpoint, field, or default changed, and a consumer that ignores them keeps working
untouched. Under "Public API — what counts as breaking" ("Adding a new endpoint ... or a new field
to an existing response object"), this is explicitly **MINOR**. `DATA_SCHEMA_VERSION` itself starts
at `1` and is not, by its introduction, a schema change — it is a new descriptive signal about the
existing schema, not a change to the schema; only a future bump of the integer would need
evaluating against the "Data schema — what counts as breaking" rules above.

### CSV `data_license` / `data_attribution` — initial contract; future addition would be MAJOR

The `0.1.0` export CSV includes two final provenance columns: the order is `node_id, timestamp,
parameter, value, unit, source, calibration, qc, uncertainty, trustworthy, data_license,
data_attribution`. They are part of the initial contract; adding them after a public release would
have been MAJOR for positional parsers. The JSON export's changes are additive: the top-level
`license` key already existed
and now reflects the store's source metadata (with an explicit override available), while the
optional top-level `attribution` key is additive. Native stores retain the authorized first-party
CC0 default; fetched stores carry their provider terms, and provider-specific OpenAQ releases fail
closed without the per-location license ledger. The two added CSV columns carry the same
source-specific license and attribution as the JSON export.

### Heat-index plausibility ceiling (60 degC) — data-quality fix, PATCH

The QC plausibility ceiling for `heat_index_c` is 60 degC (the parameter's upper valid range,
about 137 degF — the NWS heat-index ceiling). This is a **data-quality fix**: it tightens which
raw values QC accepts as physically plausible, so QC-rejected values never reach the surface. It
changes neither surface's contract — no field, type, unit, route, query parameter, or column moves,
and the `heat_index_c` parameter, its `degC` unit, and its valid range are unchanged in shape. It
only improves the data flowing through the unchanged shape, which is the definition of **PATCH**
above ("bug fixes ... that change neither surface's contract"). The same plausible-range gate
applies to every parameter; this records the heat-index ceiling specifically.

## Release artifact trust boundary

The tag workflow separates code execution from release credentials. The `build` job has read-only
repository access and no OIDC or attestation permission; it runs the locked gates, builds the three
versioned payloads and their CycloneDX documents, smoke-tests the wheel, and uploads an unsigned
digest-bound candidate. A downstream `attest-sign` job has the OIDC and attestation permissions but
does not check out or execute repository code, install project dependencies, or run a package
manager. It accepts only the exact version-matched inventory and builder digest manifest before
attesting and signing those bytes.

The release workflow pins Node `22.12.0`, uv `0.11.28`, Hatchling `1.31.0`, and Cosign `v3.1.1`.
Cosign emits one standard v0.3 `*.sigstore.json` bundle per consumer-visible asset; the credentialed
job verifies every bundle immediately. A clean no-checkout publisher accepts only that exact staged
inventory and creates a private draft. A separate clean read-only job verifies every draft signature
and hosted attestation, then binds the full asset set—including the signature bundles—to one digest.
Repository-level verification and wheel execution happen only in a different read-only consumer
job. Finally, a fresh no-checkout promotion job re-downloads the private draft and requires an exact
match to the clean verifier's bound digest before it can make the release public. No job that runs
repository or package code has release-write permission.

## Where this is recorded

Every release records its API and schema compatibility level in the changelog and release notes.
Breaking changes are never silent: they are named, with a migration step, before the version digits
are trusted.

Last verified: 2026-07-17. Recheck cadence: review on each release, and whenever the SensorThings
subset, the export shape, the observation fields, the store layout, or the correction-registry
format change.
