# swelter roadmap

The phased implementation spec. It mirrors the build plan in the repo `README.md` (the canonical
overview): pipeline to first reading, then calibration, then the dashboard and open API, then
generalize so any community registers its own nodes through `network.yaml`. The README is the
source of truth; where this file and the README disagree, the README wins.

Author: Chelsea Kelly-Reif. Year: 2026.

## Current state

The pipeline, the `swelter` CLI, the dashboard, and the merge gate are built and green: `make
verify` passes (fmt-check, lint, typecheck, a11y, test) with the full pytest suite green. The worked example in
`network.yaml` is a downtown network whose node count is a knob (`SWELTER_DEMO_NODES`); two-thirds of
the nodes have committed co-location records and publish calibrated values, the rest have none and
publish raw, flagged provisional. The published correction registry in `data/demo/corrections.yaml`
holds three corrections per co-located node (PM2.5 and PM10 by `epa-humidity`, temperature by
`enclosure-offset`) — 300 corrections across the 100 co-located nodes at the default size. `swelter
demo` replays a recorded week through the whole pipeline with no hardware.

Read the phases below as the order the system was built in and the order a new contributor should
understand it in, not as work still outstanding.

## Phase 1 — pipeline to first reading

Turn a recorded raw stream into a queryable, QC-flagged dataset locally, with no hardware.

Files it touches:

- `src/swelter/models.py` — the `Observation` frozen dataclass, the `PARAMETERS` registry
  (`temp_c`, `humidity_pct`, `pm25_ugm3`, `pm10_ugm3`, `no2_ppb`, `heat_index_c`), QC verdicts
  (`ok`, `range`, `spike`, `flatline`, `missing`), `content_hash()`, `pm25_aqi()`,
  `heat_index_c()`.
- `src/swelter/config.py` — `NetworkConfig`, `NodeConfig`, `snap_to_grid()`, `load_config()`.
- `src/swelter/store.py` — the `Store` protocol and `SqliteStore`; the store is a copyable folder
  (`observations.db`, `quarantine.jsonl`, `aggregate.geojson`, `corrections.yaml`); `write()` is
  `INSERT OR IGNORE`.
- `src/swelter/ingest.py` — `explode()` a wide payload into raw `Observation`s; quarantine
  malformed payloads; ignore unknown fields; run QC; return an `IngestResult`.
- `src/swelter/qc.py` — range/spike/flatline checks, `detect_gaps()`, `node_health()`.
- `src/swelter/export.py` — `to_csv()`, `to_json()`, `summarize()`, `filter_observations()`.
- `src/swelter/cli.py` — `ingest`, `qc`, `export` subcommands.
- `scripts/gen_demo_data.py`, `data/demo/observations.jsonl`.
- `tests/` — ingest, store, QC, models, export.

Definition of done: one command turns a recorded raw stream into a queryable, QC-flagged dataset
locally. Ingestion is idempotent (re-running a file adds nothing); malformed payloads are
quarantined, not ingested; QC labels every reading and deletes nothing; `swelter export` emits flat
CSV/JSON carrying each value's calibration state and QC verdict.

## Phase 2 — calibration

Fit per-node corrections from co-location windows, apply them to the live stream with published
uncertainty, and keep calibrated and raw always distinguishable.

Files it touches:

- `src/swelter/calibrate.py` — pure-Python OLS (no numpy); `TrainingPair`, `Correction`,
  `CorrectionRegistry` (YAML), `fit()` / `fit_one()` / `apply()` / `read_colocation()`. PM is
  humidity-aware (`corrected = a*raw + b*humidity + c`, US-EPA PurpleAir lineage); temperature uses
  an enclosure offset (`corrected = a*raw + c`). Each calibrated value carries `residual_std` as its
  1-sigma uncertainty. Version id = `"{parameter}.{method}.{node_id}"`; methods `epa-humidity`,
  `enclosure-offset`, `linear`. Coefficients are rounded to 6 dp.
- `src/swelter/models.py` — `Observation.calibrated()` and the `is_calibrated` /
  `is_trustworthy` invariants.
- `src/swelter/store.py` — `drop_calibrated()` drops the derived (non-raw) records, leaving the immutable raw log to rebuild from (the rebuild itself is `swelter rebuild` / `calibrate.apply`).
- `src/swelter/config.py` — `ReferenceMonitor`, `CalibrationWindow`.
- `src/swelter/cli.py` — `calibrate`, `rebuild` subcommands.
- `data/demo/colocation.jsonl`, `data/demo/corrections.yaml`.
- `tests/` — calibration fit, apply, registry round-trip, the byte-for-byte reproducibility check.

Definition of done: calibrated-vs-raw labeling is enforced through the pipeline — a node with no
correction stays raw and is shown provisional. Re-running `swelter calibrate` against the committed
co-location data reproduces `data/demo/corrections.yaml` byte-for-byte (6-dp coefficients make this
hold). Every calibrated observation names its correction version and carries a 1-sigma uncertainty.

## Phase 3 — dashboard and open API

Build the map, table, and list views; the read-only OGC SensorThings subset; and the heat-island
and AQI surfaces. Meet WCAG 2.2 AA as a merge gate.

Files it touches:

- `src/swelter/aggregate.py` — snap to published grid cells, hourly rollups, prefer calibrated +
  QC-clean values (else mark the cell `provisional`); PM2.5 cells carry EPA AQI and category;
  `Surface.snapshot_geojson()` and `to_records()`.
- `src/swelter/api.py` — the SensorThings 1.1 subset (Things = nodes, ObservedProperties =
  parameters, Observations = readings); `service_document` advertises `readOnly: true`.
- `src/swelter/server.py` — stdlib `http.server`, single-threaded, GET-only (writes → 405); routes
  `/health`, `/v1.1`, `/v1.1/Things`, `/v1.1/ObservedProperties`, `/v1.1/Observations`,
  `/api/surface.geojson`, `/api/surface.json`, `/export.csv`, `/export.json`, and static `web/`.
- `src/swelter/cli.py` — `aggregate`, `serve`, `demo` subcommands; `swelter demo --serve`
  regenerates `web/sample-surface.json`.
- `web/` — framework-free WCAG 2.2 AA dashboard: map, sortable table, and plain list as three equal
  views of one surface; AQI severity by text and pattern, never color alone; keyboard-operable time
  slider that announces via `aria-live`; en + es bundles; PWA (`manifest.webmanifest`, `sw.js`).
- `scripts/a11y_check.py` — the 12-check structural WCAG gate run by `make a11y` / `make verify`.
- `tests/` — aggregate, api, server, and the a11y gate.

Definition of done: WCAG 2.2 AA is met and gated (`make a11y` green, 12 checks); the map is never
the only way in (table and list carry the same surface with identical filtering); the API is
read-only and serves the SensorThings subset plus CSV/JSON; Spanish has parity with English; `api.md`
documents the surface and deep-links per observed property.

## Phase 4 — generalize

Make swelter point at any community's network without code changes.

Files it touches:

- `network.yaml` — the worked example a community copies and edits: `name`, `grid_resolution_m`,
  `languages`, `nodes[]`, `reference_monitors[]`, `calibration_windows[]`.
- `src/swelter/config.py` — `load_config()` and `public_location()` so a host's exact coordinates
  snap to a ~150 m grid unless the node opts into `precise`.
- `docs/` — an "add your neighborhood in an afternoon" guide
  ([`ADD-YOUR-NEIGHBORHOOD.md`](ADD-YOUR-NEIGHBORHOOD.md), with a resident-facing
  [`ABOUT-THE-NETWORK.md`](ABOUT-THE-NETWORK.md) note) and the finished hardware build doc
  (firmware sampling, store-and-forward, BOM, enclosure).
- `tests/` — config loading and the snap-to-grid privacy behavior across `coarse` / `precise`.

Definition of done: a community stands up its own instance by editing a copy of `network.yaml` —
registering its nodes, its reference monitors, and its co-location windows — and runs the same
pipeline, gate, dashboard, and API. Nothing about the worked downtown example is hard-coded into the
modules.

## Phase 5 — differentiate and sustain (proposed, not built)

Unlike phases 1–4, this phase is **not yet built**: it is the forward direction from the 2026 market,
funding, and demand scan in [`POSITIONING.md`](POSITIONING.md). It is recorded here so a contributor
sees where the project is headed and why; each item lands as its own PR with its own tests and ADR,
not as a single drop. Nothing here changes a hard rule, and everything stays inside the existing
calibration, privacy, openness, and accessibility discipline.

The position (ADR 0008): swelter is the open, community-owned trust layer for neighborhood
heat-and-air exposure. The work below is the highest-leverage way to make that real, ordered by
leverage.

1. **Compound heat-and-air exposure surface** (ADR 0009) — **built.** Combines the calibrated heat
   index and the PM2.5 AQI into one published neighborhood `exposure` level, since the joint exposure
   is where the harm concentrates and no incumbent publishes both together. Lives in `models.py`
   (`heat_index_category`, `exposure_level`), `aggregate.py` (the derived `exposure` cell), the
   surface API and `api.md`, and the dashboard as a measurement option across map, table, and list —
   provisional flags and the calibrated/raw line intact, severity in text not color alone. The
   flagship differentiator.
2. **Make the trust layer visible** — surface the calibration version, ±uncertainty, QC verdict, and
   reference-monitor lineage as a first-class "show your work" view, not buried provenance. This is
   the moat for the researcher and credibility audiences; mostly `web/` and `api.md`.
3. **Register-your-own-network as the headline capability** — lean on `network.yaml`, the no-hosted-
   dependency, scale-to-zero design, and `ADD-YOUR-NEIGHBORHOOD.md` as the replicability and
   sustainability story (local ownership is the documented survival factor). Largely docs and
   packaging, little new code.
4. **Accessibility and bilingual as a certifiable asset** — the DOJ 2024 ADA Title II rule makes
   WCAG 2.1 AA legally load-bearing for public agencies; swelter clears 2.2 AA and ships en + es
   against a documented language-justice gap. Package this as a compliance hook for agency partners.
5. **Close the data-to-action gap** — a lightweight plain-language neighborhood brief / advocacy
   export, because the research is consistent that data alone is not the product. Builds on the
   existing export surface.

Definition of done is per-item and per-PR. The phase as a whole is done when swelter can point a
funder at a working compound-exposure surface, an auditable trust view, and a one-afternoon
register-your-network path — the three things the scan says the four audiences and the
philanthropy-first funding path reward.

## Fixes (security, audit, governance)

Separate from phases 1–5, these are targeted fixes addressing audit findings, security
requirements, or governance commitments. Each ships as its own PR with its own tests and ADR.

### FIX-01 — Authenticated node write path (ingest-serve with per-node HMAC)

**Status: ✅ Done** (merged 2026-07-01)

The node→ingest write boundary was documented as authenticated (RESPONSIBLE-TECH-AUDITS.md) but
not implemented. Fixed:

- **Per-node key provisioning:** `swelter node-key <node_id>` issues or rotates a 256-bit HMAC
  key in an operator-local `node-keys.yaml` (never in `network.yaml`, never committed). The key is
  printed once for the operator to copy into the node's uncommitted `config.py` as `ingest_key`.
- **Request signing:** Firmware (`firmware/src/signing.py`) signs every HTTP POST over
  `(node_id, timestamp, body_hash)` with RFC 2104 HMAC-SHA256. Three headers carry the node id,
  signing timestamp, and signature. The same module runs on MicroPython and desktop CPython.
- **Signature verification:** `swelter ingest-serve` (write-only listener on 127.0.0.1:8100)
  verifies each request: unknown node → 401, signature mismatch → 401, timestamp outside the
  ±300s replay window → 401. Failed requests land in `quarantine.jsonl` with an `auth:` reason.
- **Replay protection:** The signed timestamp is the sending time (not observation time), so
  backfill after an outage works; the store's idempotency (`INSERT OR IGNORE`) ensures a captured
  and replayed request cannot alter the record.
- **Tests:** two layers, not one. Function-level: key provisioning, signing/verification, and
  every `verify_request()` refusal reason (missing headers, unknown node, replay window,
  signature mismatch) are unit-tested directly, plus server-firmware signature compatibility.
  Handler-level: a real `make_server()` listener is started on a background thread and driven
  with genuine HTTP POSTs to prove the *running server*, not just the crypto function, does the
  right thing — a validly-signed request is written to the store and returns 200; a missing or
  bad signature returns 401 and lands in `quarantine.jsonl`; a payload `node_id` that
  impersonates a different node than the one authenticated is refused by the handler's
  post-auth impersonation check (`claimed != node` in `_post()`), not just accepted by
  `verify_request()`; an unknown node with an otherwise well-formed signature is refused before
  any crypto compare runs. The `ingest-serve`/`node-key` CLI subcommands are covered too: the
  missing- and empty-keys-file error paths, and an end-to-end check that a key issued by
  `swelter node-key` is the exact key `swelter ingest-serve` loads and a real listener built
  from it authenticates against.

Files touched:
- `firmware/src/signing.py` — RFC 2104 HMAC-SHA256 (MicroPython-compatible)
- `firmware/src/main.py` — HttpForwarder signs requests when `ingest_key` is set
- `src/swelter/ingest_server.py` — New module: authenticated listener, key storage, verification
- `src/swelter/cli.py` — `ingest-serve` and `node-key` subcommands
- `tests/test_ingest_server.py` — function-level auth/crypto tests plus real-listener HTTP
  integration tests (valid write, refused/quarantined auth failures, handler-level impersonation
  rejection, unknown-node rejection)
- `tests/test_firmware_signing.py` — 10 tests for firmware-server signature compatibility
- `tests/test_cli.py` — `ingest-serve`/`node-key` CLI coverage (error paths + an issued key
  authenticating against a real listener)

## Metrics ledger

These are the numbers the project holds itself to. External-fact rows (the EPA breakpoint and AQI
methodology the accuracy and AQI metrics depend on) carry a recheck cadence below the table.

| Metric | Target | Measured by | Gate |
| --- | --- | --- | --- |
| Accuracy vs reference (PM2.5, PM10) | Calibrated residual_std published per node; corrected values track the co-located reference better than raw | `calibrate.fit()` residual_std + R² on the held co-location window; `tests/` assert corrected error < raw error | `make verify` (test) — fails if a fit regresses below the recorded bound |
| Accuracy vs reference (temp) | Enclosure-offset correction reduces bias against the reference monitor | `calibrate` residual_std for `enclosure-offset` corrections | `make verify` (test) |
| Calibration reproducibility | Re-running `swelter calibrate` on committed co-location data reproduces `corrections.yaml` byte-for-byte (coefficients 6 dp) | Registry round-trip test diffs the rebuilt YAML against the committed file | `make verify` (test) — merge-blocking |
| Accessibility | WCAG 2.2 AA; map has an equivalent sortable table and plain list; AQI never color alone; time slider keyboard-operable | `scripts/a11y_check.py` (12 structural checks) | `make a11y` / `make verify` (a11y) — merge-blocking |
| Ingestion idempotency | Re-ingesting any payload file adds zero rows | `store.write()` `INSERT OR IGNORE` on key `(node_id, timestamp, parameter, calibration)`; ingest tests re-run a file and assert the count is unchanged | `make verify` (test) |
| Quarantine integrity | Malformed payloads are quarantined, never ingested; unknown fields ignored | `ingest.explode()` + `quarantine.jsonl`; ingest tests on malformed inputs | `make verify` (test) |
| Privacy (no PII, coarse location) | No schema field can hold a person; published coords snap to ~150 m unless a node opts into `precise` | Schema review (a PR adding a person-bearing field fails review); `config.public_location()` snap tests | Review + `make verify` (test) |
| Type safety | `mypy --strict` passes | `mypy --strict` over `src` and `tests` | `make verify` (typecheck) — merge-blocking |
| Lint / format | ruff clean (line-length 100; E, F, I, UP, B, SIM) | `ruff check` and `ruff format --check` | `make verify` (fmt-check, lint) — merge-blocking |
| Cost | Single-digit dollars a month; scale-to-zero, no always-on component, no paid dependency (runtime dep: PyYAML only) | Static dashboard + GET-only stdlib server; budget alarm on the optional cloud copy | Architecture review — no merge gate (operational target) |

Last verified: 2026-06-16. Recheck cadence: the accuracy and AQI rows depend on the US-EPA 2024
24-hour PM2.5 breakpoints and the AQI methodology in `models.py`; recheck on each EPA breakpoint
revision, and at least annually.
