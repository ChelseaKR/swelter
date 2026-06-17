# swelter architecture

How the system is put together and why. This describes the code as it exists in
`src/swelter/`; if the two disagree, the code is right and this doc is a bug.

Author: Chelsea Kelly-Reif. Last verified: 2026-06-16 against `src/swelter/` at the
documented commit. Recheck when a module's public functions change, when a route is added
to the server, or when the store layout changes — and at least every six months.

See also: [calibration](calibration.md), [governance](governance.md),
[the API reference](api.md), and the architecture decision records in
[`docs/decisions/`](decisions/).

## One-way data flow

Data moves in one direction. A reading is captured at a node, buffered, and forwarded; it is
validated and written once as immutable raw; everything after that is derived from the raw log
and can be thrown away and rebuilt. Nothing downstream writes back upstream.

```
  nodes              ingest             store              calibrate          aggregate          serve / export
 (firmware)        ingest.py          store.py           calibrate.py        aggregate.py        api.py · server.py
 buffer &      validate · explode   append-only raw   fit per-node OLS,    snap to grid,        SensorThings subset,
 forward   ->  to Observations,  -> log (SQLite),  -> apply corrections, -> hourly rollups,  -> CSV / JSON,
   |           run QC, quarantine    INSERT OR IGNORE   emit calibrated      prefer calibrated    GeoJSON surface,
   |           malformed payloads    (idempotent)       beside raw           + QC-clean cells     static dashboard
   |                                      ^                   |                                         |
   |                                      |   drop_calibrated() rebuilds all derived from raw           |
   '--- store-and-forward, no upstream <--'<------------------'-----------------------------------------'
       state held in swelter; the only
       writer is ingest
```

The only component that writes observations is ingest. Calibration, aggregation, the API,
and export all read. The arrow back to the store from calibrate is still a *write of derived
data* keyed so it cannot collide with raw or with a prior run (see Idempotency below). The
server has no write path at all.

## Modules and what each one owns

Each module is one responsibility. Names below are the real symbols in `src/swelter/`.

### `models.py` — the vocabulary

Defines `Observation` (a frozen dataclass: `node_id`, `timestamp` as ISO-8601 UTC `…Z`,
`parameter`, `value`, `unit`, `calibration`, `qc`, `uncertainty`). Observations are
long-format — one parameter per record — so each value carries its own calibration provenance
and uncertainty rather than inheriting a row's.

- `Observation.content_hash()` is a stable SHA-256 over the value-bearing fields, for integrity
  and dedup.
- `Observation.key()` returns `(node_id, timestamp, parameter, calibration)` — the idempotent
  store identity.
- `calibration` is never empty: it is `RAW` (`"raw"`) or a correction version id, so calibrated
  and raw are always distinguishable. `is_calibrated` and `is_trustworthy` encode that for
  downstream code.
- `PARAMETERS` is the registry of measurable quantities with their plausible bounds:
  `temp_c` (degC), `humidity_pct` (%), `pm25_ugm3` (ug/m3), `pm10_ugm3` (ug/m3), `no2_ppb` (ppb),
  `heat_index_c` (degC). Adding a parameter is a one-line change here plus a calibration model.
- QC verdicts are constants here: `ok`, `range`, `spike`, `flatline`, `missing`.
- `pm25_aqi()` applies the US-EPA 2024 24-hour PM2.5 breakpoints; `heat_index_c()` is the NWS
  Rothfusz regression. `parse_timestamp()` / `format_timestamp()` canonicalise time.

### `config.py` — the network as one reviewable document

`NetworkConfig`, `NodeConfig`, `ReferenceMonitor`, `CalibrationWindow`, loaded from
`network.yaml` by `load_config()`. A community points swelter at a different city by editing one
file, not forking. The privacy boundary lives here: `NodeConfig.public_location()` snaps a node
to a `grid_resolution_m`-sided cell (default ~150 m) via `snap_to_grid()` unless the host sets
`location: precise`. `NetworkConfig.public_locations()` is the only coordinate source the rest
of the system reads — the precise lat/lon never leaves config.

### `store.py` — the append-only observation log

The `Store` protocol plus the default `SqliteStore`. `write()` is `INSERT OR IGNORE` on the
observation key (idempotent). Raw observations are append-only; `drop_calibrated()` deletes only
derived rows so the whole surface can be rebuilt from immutable raw. `store_paths()` and
`open_store()` define and open the store folder. (Layout and rationale below.)

### `ingest.py` — intake

`explode()` turns one wide node payload into long-format raw `Observation` records, one per
known parameter; unknown fields are ignored so new firmware does not break intake. `ingest()` /
`ingest_file()` validate, explode, run QC, and write, returning an `IngestResult`. A payload
missing a node id or timestamp, or yielding no known parameter, is **quarantined** to
`quarantine.jsonl` with a reason — malformed data never silently enters the record. Re-running is
safe because the store key is idempotent.

### `qc.py` — label, never delete

Per-node/parameter `range`, `spike`, and `flatline` checks via `apply()`; `detect_gaps()` finds
outages; `node_health()` summarises liveness and flagged fraction. QC tags a reading; it never
removes one. Every check is a pure function over parsed observations, so QC is testable offline
against recorded streams.

### `calibrate.py` — co-location fit and the versioned registry

Pure-Python OLS, no numpy. `TrainingPair` is one co-located measurement; `read_colocation()`
loads them. `fit_one()` / `fit()` produce a `Correction` per node/parameter; `apply()` emits a
calibrated observation beside each raw one that has a correction. PM is humidity-aware
(`corrected = a·raw + b·humidity + c`, US-EPA PurpleAir lineage); temperature and heat index use
an enclosure-offset (`corrected = a·raw + c`). Each calibrated value carries the fit's
`residual_std` as its 1-σ uncertainty. The `CorrectionRegistry` persists to YAML. Coefficients
are rounded to 6 dp (`PRECISION`) so re-fitting committed co-location data reproduces the
registry byte-for-byte. A node with no correction stays raw and shows provisional. (See
[calibration](calibration.md).)

### `aggregate.py` — the gridded surface

`aggregate()` snaps each reading to its *published* grid cell and rolls values up by hour. For a
given cell/hour/parameter it averages calibrated, QC-clean values when any exist; a cell with
only raw or flagged readings is still shown but marked `provisional`. PM2.5 cells carry EPA AQI
and category. The result is a `Surface`, rendered by `snapshot_geojson()` (map) and
`to_records()` (slider/table).

### `export.py` — leaving with the data

`to_csv()` and `to_json()` (the JSON payload declares `"license": "CC0-1.0"`) emit flat dumps
where each row carries calibration version, QC verdict, and uncertainty — a value's
trustworthiness travels with it. `summarize()` builds the CLI banner; `filter_observations()`
mirrors the store query in memory.

### `api.py` — the read-only API shape

A subset of OGC SensorThings 1.1: `service_document()`, `things()` (nodes, with grid-snapped
locations only), `observed_properties()` (parameters), `observations()` (readings). The service
document advertises `readOnly: true`. These are pure functions returning dicts; `to_csv` /
`to_json` are re-exported so callers have one import for the API and its dumps. (See
[the API reference](api.md).)

### `server.py` — the thin HTTP layer

A stdlib `http.server.HTTPServer`, single-threaded and read-only. Routes: `/health`, `/v1.1`,
`/v1.1/Things`, `/v1.1/ObservedProperties`, `/v1.1/Observations`, `/api/surface.geojson`,
`/api/surface.json?hours=N`, `/export.csv`, `/export.json`, and static files from `web/`. Only
`GET` is served; `POST`/`PUT`/`DELETE`/`PATCH` return `405`. CORS is open because the data is
open. (Detail below.)

### `cli.py` — the one-command surface

The `swelter` console script. Subcommands `ingest`, `qc`, `calibrate`, `aggregate`, `export`,
`serve`, `demo`, `rebuild`, `version`. Each is a thin wrapper over the library, so anything the
CLI does is scriptable and testable. (`make demo` below.)

## The store: a folder you can copy

The store is a directory, not a service. `store_paths()` defines its layout:

```
store/                       (or store/demo for the demo)
  observations.db            SQLite — the whole append-only archive, Datasette-openable
  quarantine.jsonl           payloads that failed validation, with a reason each
  aggregate.geojson          the rendered gridded surface (derived)
  corrections.yaml           the published correction registry (versioned data)
```

`observations.db` holds one `observations` table keyed
`PRIMARY KEY (node_id, timestamp, parameter, calibration)` with a `content_hash` column and two
indexes. To back up or hand off the network, copy the folder.

**Why SQLite + files, no cluster.** A neighbourhood collective has to run, back up, and walk
away with this on a Raspberry-Pi-class host with no cloud. A single SQLite file is the whole
archive; Datasette opens it directly for ad-hoc queries; the sidecar files are plain text and
YAML anyone can read. There is no database server to operate, no proprietary format to be locked
into, and no node that failing takes the data down with it. This is recorded in
[`docs/decisions/`](decisions/).

**The pluggable store seam.** `Store` is a `Protocol` (`write`, `read`, `all`, `node_ids`,
`count`, `close`). `SqliteStore` is the default implementation. A Parquet/Arrow backend can
implement the same methods and drop in without touching ingest, calibrate, aggregate, or the
API — they depend only on the protocol. The seam is why "SQLite for now" is not a one-way door.

## The single-threaded, read-only server

`make_server()` builds a plain `HTTPServer`, which is single-threaded; `serve()` runs it.
Two deliberate choices:

- **Read-only by construction.** `do_GET` is the only real handler; `do_POST` and its aliases
  send `405`. There is no code path that writes an observation through HTTP, so the public
  surface cannot alter the record. Writes happen only through `ingest`, on the operator's side.
- **Single-threaded on purpose.** A community dashboard sits behind a static cache or CDN and
  needs almost no concurrency. Serialising requests keeps the one SQLite reader safe without
  locks or a connection pool. The process is stateless — it reads the store and answers — so it
  is scale-to-zero friendly and runs unchanged on a tiny host. (`SqliteStore` is opened with
  `check_same_thread=False` precisely because the single server thread is not the thread that
  created it; single-threading is what keeps that access serialised.)

## Calibration is versioned data, not code

Corrections live in `corrections.yaml`, a `CorrectionRegistry` keyed by node and parameter. Each
entry names the version that produced it — version id format `{parameter}.{method}.{node_id}`,
methods `epa-humidity` (PM), `enclosure-offset` (temp / heat index), `linear` (default). The fit
itself is plain OLS in `calibrate.py`, but *which* correction is applied to *which* node is a
data decision recorded in a committed file, reviewed as a diff with an audit trail.

Because coefficients round to 6 decimal places, re-running `fit()` on the committed
co-location pairs reproduces the registry byte-for-byte: anyone can check a calibration instead
of trusting it. Recalibrating a node is a data change, not a code release.

## What `make demo` does

`make demo` runs `uv run swelter demo --serve`, which executes `cmd_demo` against `data/demo`
with the store at `store/demo`. Step by step:

1. **Fresh store.** Deletes `store/demo/observations.db` so each run starts clean; replay is
   idempotent anyway.
2. **Ingest.** `ingest_file("data/demo/observations.jsonl")` replays the recorded ~16-day hourly
   week (18 nodes, including node-07's offline gap, a PM range spike, and a flatlined humidity
   sensor) into immutable raw, running QC and quarantining anything malformed.
3. **Calibrate.** Reads `data/demo/colocation.jsonl`, `fit()`s the registry, writes it to
   `store/demo/corrections.yaml`, then `apply()`s corrections and writes the calibrated
   observations beside the raw. The 12 nodes with co-location records become calibrated; the 6
   without stay raw-flagged.
4. **Aggregate.** Rolls the store up with `aggregate()` and writes the GeoJSON surface to
   `store/demo/aggregate.geojson`.
5. **Refresh the offline sample.** Regenerates `web/sample-surface.json` (the last 24 buckets) so
   the dashboard renders without a server.
6. **Summary.** Prints the `summarize()` banner from real counts, including the longest gap.
7. **Serve** (because `--serve`). Opens the store read-only and runs the server at
   `http://127.0.0.1:8000` — dashboard, SensorThings API, and exports — until Ctrl-C.

No hardware is involved at any step; the demo data is committed and deterministic
(`scripts/gen_demo_data.py`). `make rebuild` reruns steps 3–4 from immutable raw to prove the
derived surface is reproducible.

## How the quality attributes are realized structurally

These are properties of the structure, not promises bolted on after.

**Integrity — content hashing and append-only.** Every observation carries a
`content_hash()` (SHA-256 over its value-bearing fields). Raw observations are written once and
never mutated: `Observation` is a frozen dataclass, and an edit is a new record, not an
overwrite. `store.write()` only ever inserts. The raw log is therefore immutable evidence, and
every derived surface can be rebuilt from it via `drop_calibrated()` + re-apply.

**Idempotency.** The store key is `(node_id, timestamp, parameter, calibration)` and `write()`
is `INSERT OR IGNORE`. Replaying the same stream — a node backfilling after an outage, a re-run
of `make demo` — never double-counts. Re-ingesting is always safe. Calibrated rows get a
distinct `calibration` value in the key, so they coexist with raw rather than colliding.

**Privacy — grid snap and a no-PII schema.** The published coordinate is the grid-cell centre
from `snap_to_grid()`; `public_location()` is the only coordinate the rest of the system can
read, and aggregation snaps to that published cell, never the precise one. The schema has no
field that can hold a person — no device id, no MAC, no owner, no precise coordinate in the
observation record. A reading cannot identify who took it because there is nowhere to put that.
(See [governance](governance.md) for the rules this enforces.)

**Reproducibility.** Demo data is committed and generated deterministically; calibration
coefficients round to a fixed precision so the registry reproduces byte-for-byte; the entire
derived surface (calibrated values, aggregate GeoJSON, the dashboard sample) is a pure function
of the immutable raw log plus the committed registry, regenerated by `make rebuild`. Given the
same inputs, anyone gets the same outputs.
