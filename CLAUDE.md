# CLAUDE.md — build-spec and operating contract for swelter

This file is the contract an agent works under in this repo. It is not the overview. The repo root
`README.md` is the canonical source of truth; where this file and the README disagree, the README
wins. Read the README's **Hard rules** section before you touch anything.

Author: Chelsea Kelly-Reif. Year: 2026.

## What swelter is, and who it is for

swelter is a community-owned network of low-cost heat and air-quality sensors with the pipeline,
calibration, and accessible map that make its readings trustworthy and open. Nodes measure
temperature, humidity, PM2.5/PM10, optional NO2, and a derived heat index. A time-series pipeline
ingests the readings, QC flags the bad ones, calibration corrects each node's drift against
reference monitors, and a framework-free dashboard maps urban heat islands and AQI at neighborhood
resolution. The observation data is open (CC0) and exports through open standards so anyone can
audit, reuse, or fork it.

It is built for frontline neighborhoods that live the heat-and-air exposure and rarely hold the
data — and for the collective that hosts the sensors, who own siting, location precision, and
governance. The readings are aggregate environmental measurements: no people, no devices-as-trackers,
no PII. It is a sibling to the GTFS and fare-policy civic-data work in this portfolio and reuses
their discipline around versioned data, plain-language findings, and audited accessibility.

Independent personal open-source project. Code is Apache-2.0 (`LICENSE`); observation data is
CC0-1.0 (`DATA-LICENSE`); `NOTICE` holds the independence statement. Unaffiliated with any employer
or client; no proprietary or client material; not a government system.

## Hard rules — guardrails an agent must never violate

These come straight from the README and are enforced, not aspirational. A PR that crosses any of
them fails review regardless of how clean the rest of it is. If a hard rule genuinely needs to
change, that is an ADR and a conversation with the maintainer first — never a quiet PR.

1. **No surveillance, no field that can hold a person.** The schema has no column, payload key, or
   config field that can locate or identify an individual, and it stays that way. Do not add a name,
   personal device identifier, MAC address, precise home address, account, or anything that turns an
   environmental reading into a record about a person. Do not add firmware or ingest support for
   microphones, cameras, Bluetooth, or Wi-Fi client scanning. The only identifier is the node ID the
   hosting collective assigns. Adding any of this fails review.

2. **Public locations snap to a coarse grid.** A sensor sits on someone's porch. Published
   coordinates snap to the network grid (`grid_resolution_m`, default ~150 m) via
   `config.public_location()` **unless** the node's `location` is `"precise"` and the host opted in.
   The precise value is never required to use the system. Any code path that emits coordinates — a
   new export format, API field, or map layer — routes through `public_location()` / the published
   grid and never reads the raw config coordinate directly. Snapping is deterministic: same point and
   resolution always land in the same cell.

3. **Calibrated vs raw are never silently mixed.** Every `Observation` carries a `calibration` field
   that is either the literal `"raw"` or a version id `"{parameter}.{method}.{node_id}"`. The store
   key is `(node_id, timestamp, parameter, calibration)`, so a raw reading and its calibrated
   counterpart are two distinct rows that never overwrite each other. A node with no fitted correction
   stays raw and is shown **provisional** — never promoted to calibrated. `aggregate` prefers
   calibrated, QC-clean values per cell and marks the cell provisional otherwise; it does not average
   a calibrated and a raw value as if they were the same kind of number. The state and `residual_std`
   1-sigma uncertainty survive every hop through storage, aggregation, API, and exports.

4. **Data stays open and portable.** Observations are CC0; export is a first-class command, not an
   afterthought. CSV, JSON (CC0-1.0), the read-only OGC SensorThings subset, and the Datasette-openable
   store are how the community keeps and moves its data. Do not remove an export route, hide it behind
   an account or key, or make the store non-portable.

5. **Community-owned.** Governance, siting, and any decision to share precise locations rest with the
   hosting collective (`docs/governance.md`). swelter is a tool they run, not a service that runs them.
   Do not add a hosted dependency, account requirement, or lock-in that takes that control away.

## The phased plan

The implementation spec is phased in **`docs/ROADMAP.md`** — pipeline to first reading, then
calibration, then dashboard and open API, then generalize so any community registers its own nodes
through `network.yaml`. Read the phases as the order the system was built in and the order a new
contributor should understand it in, not as work still outstanding: the pipeline, the `swelter` CLI,
the dashboard, and the merge gate are built and green. The roadmap also carries the metrics ledger
(the numbers the project holds itself to) and its recheck cadence.

## The quality bar

`make verify` is the full merge gate and it must stay green. It runs, in order:

```
fmt-check  →  ruff format --check          (formatting)
lint       →  ruff check                   (E, F, I, UP, B, SIM; line length 100)
typecheck  →  mypy --strict                (passes clean over src + tests)
a11y       →  scripts/a11y_check.py        (structural WCAG 2.2 AA gate, 12 checks)
test       →  pytest                       (62 tests, all green)
```

Non-negotiables baked into the gate:

- **`mypy --strict` passes** and **ruff is clean.** Both are merge-blocking.
- **WCAG 2.2 AA is a merge gate.** `make a11y` runs 12 structural checks. A change that fails one,
  removes the table or list view, makes the map the only way into the data, or conveys AQI/heat
  severity by color alone fails review. The map, sortable table, and plain list are three equal views
  of one surface — keep them equal.
- **Calibration must remain reproducible.** `calibrate` is pure-Python OLS (no numpy) and rounds
  fitted coefficients to 6 dp, so re-running `fit()` on the committed co-location data reproduces
  `data/demo/corrections.yaml` byte-for-byte (36 entries: 12 nodes × 3 parameters). If you change the
  fit, the rounding, or the version-id format you break this; regenerate and commit the registry in
  the same PR and explain why in an ADR.

Run `make verify` locally before you push. CI runs the same thing plus pip-audit, gitleaks, and
CodeQL. A red gate blocks merge; there is no override.

## How to run things

Python ≥3.11, src-layout package, hatchling build backend, managed and run with **uv**. One runtime
dependency (PyYAML); everything else is the standard library.

```console
$ uv sync          # create .venv and install runtime + dev deps from uv.lock (matches CI)
$ make verify      # the full merge gate; should be green before you start
$ make demo        # or: uv run swelter demo --serve
```

`make demo` replays the recorded ~16-day demo week through the whole pipeline (ingest, QC, calibrate,
aggregate, serve) with **no hardware** and serves the dashboard at `http://127.0.0.1:8000`. It is
deterministic and also regenerates the offline dashboard sample `web/sample-surface.json` — if your
change affects aggregation output that file changes; commit it in the same PR. The demo network is
the worked example in `network.yaml`: 18 nodes, 12 calibrated and 6 raw-flagged, with node-07 going
offline (the longest gap), a PM range spike, and a flatlined humidity sensor for QC to catch.

Make targets (all run through `uv run`; `make help` lists them): `install`, `gen-demo`, `ingest`,
`qc`, `calibrate`, `aggregate`, `export`, `serve`, `demo`, `rebuild`, `fmt`, `fmt-check`, `lint`,
`typecheck`, `test`, `a11y`, `verify`, `check`, `clean`. The CLI subcommands behind them: `swelter
ingest | qc | calibrate | aggregate | export | serve | demo | rebuild | version`.

## Do not modify

The README is the source of truth. Do not modify it, or any file under `src/`, `web/`, `tests/`,
`scripts/`, or `data/`. Conventional commits. New design decisions go in `docs/decisions/NNNN-kebab-title.md`
using the house ADR format (Decision / Why / Known weakness). House style for prose: plain and
concrete, no marketing adjectives; external-fact docs carry a `Last verified:` line and a recheck
cadence.

## Codebase map

The pipeline is a one-way flow: nodes buffer and forward → `ingest` validates and writes immutable
raw observations → `qc` labels → `calibrate` fits and applies per-node corrections → `aggregate`
builds gridded surfaces → `serve`/`export`. Modules under `src/swelter/`:

- **`models.py`** — the `Observation` frozen dataclass (`node_id`, `timestamp` ISO-8601 UTC
  `...Z`, `parameter`, `value`, `unit`, `calibration` [`raw` or a version id], `qc`, `uncertainty`);
  `content_hash()` (sha256), immutable, idempotent store key `(node_id, timestamp, parameter,
  calibration)`. The `PARAMETERS` registry (`temp_c`, `humidity_pct`, `pm25_ugm3`, `pm10_ugm3`,
  `no2_ppb`, `heat_index_c`), QC verdicts (`ok`, `range`, `spike`, `flatline`, `missing`),
  `pm25_aqi()` (US-EPA 2024 24-hour breakpoints), `heat_index_c()` (NWS Rothfusz).
- **`config.py`** — `NetworkConfig`, `NodeConfig` (`location: coarse|precise`), `ReferenceMonitor`,
  `CalibrationWindow`, `snap_to_grid(lat, lon, metres)` → grid-cell centre, `load_config(network.yaml)`,
  and `public_location()` — the privacy boundary that snaps to a ~150 m grid unless a host opts into
  `precise`.
- **`store.py`** — the `Store` protocol plus `SqliteStore` (default). The store is a copyable folder:
  `observations.db` (SQLite, Datasette-openable), `quarantine.jsonl`, `aggregate.geojson`,
  `corrections.yaml`. `write()` is `INSERT OR IGNORE` (idempotent); raw is append-only;
  `drop_calibrated()` rebuilds derived records from raw alone. Pluggable (a Parquet backend could
  implement the same protocol).
- **`ingest.py`** — `explode()` a wide payload into raw `Observation`s; malformed payloads are
  quarantined, not ingested; unknown fields ignored; runs QC; idempotent; returns an `IngestResult`.
- **`qc.py`** — range/spike/flatline checks, `detect_gaps()`, `node_health()`. Labels, never deletes.
- **`calibrate.py`** — pure-Python OLS (no numpy): `TrainingPair`, `Correction`, `CorrectionRegistry`
  (YAML), `fit()` / `fit_one()` / `apply()` / `read_colocation()`. PM is humidity-aware
  (`corrected = a*raw + b*humidity + c`, US-EPA PurpleAir lineage); temperature uses an enclosure
  offset (`corrected = a*raw + c`). Each calibrated value carries `residual_std` as its 1-sigma
  uncertainty. Version id `"{parameter}.{method}.{node_id}"`; methods `epa-humidity` (PM),
  `enclosure-offset` (temp/heat index), `linear` (default). Coefficients rounded to 6 dp so the
  registry rebuilds byte-for-byte.
- **`aggregate.py`** — snaps to published grid cells, hourly rollups, prefers calibrated + QC-clean
  values per cell (else marks the cell `provisional`); PM2.5 cells carry EPA AQI and category.
  `Surface.snapshot_geojson()` and `to_records()`.
- **`export.py`** — `to_csv()`, `to_json()` (license CC0-1.0), `summarize()` banner,
  `filter_observations()`.
- **`api.py`** — read-only OGC SensorThings 1.1 subset (Things = nodes, ObservedProperties =
  parameters, Observations = readings) plus CSV/JSON; the `service_document` advertises `readOnly: true`.
- **`server.py`** — stdlib `http.server`, single-threaded, GET-only (writes → 405). Routes:
  `/health`, `/v1.1`, `/v1.1/Things`, `/v1.1/ObservedProperties`, `/v1.1/Observations`,
  `/api/surface.geojson`, `/api/surface.json?hours=N`, `/export.csv`, `/export.json`, and static
  `web/`. Scale-to-zero friendly; CORS open (open data).
- **`cli.py`** — the `swelter` console script and its subcommands (above). `swelter demo` replays
  `data/demo` through the whole pipeline with no hardware, optionally serves the dashboard
  (`--serve`), and regenerates `web/sample-surface.json`.

Supporting tree: `network.yaml` (the worked-example config), `data/demo/` (deterministic recorded
data and the published `corrections.yaml`, generated by `scripts/gen_demo_data.py`), `web/` (the
framework-free WCAG 2.2 AA dashboard, en + es, PWA), `scripts/a11y_check.py` (the structural a11y
gate), and `docs/` (ROADMAP, governance, ADRs in `decisions/`, `audits/`, `accessibility/`).

Last verified: 2026-06-16. Recheck when the toolchain, module layout, Make targets, or hard rules
change (at least once per release).
