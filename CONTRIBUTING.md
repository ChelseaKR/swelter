# Contributing to swelter

Thanks for considering a contribution. swelter is an independent personal open-source project by
Chelsea Kelly-Reif. The code is Apache-2.0; the observation data is CC0-1.0. The repo root
`README.md` is the canonical overview — read it first, especially the **Hard rules** section, which
this document turns into a checklist for reviewers.

This is a community heat and air-quality sensing network. People rely on the map to decide whether
it is safe to be outside. That raises the bar for changes: a number that is precise and wrong is
worse than no number. Most of what follows exists to keep that from happening.

## Development setup

You need Python 3.11 or newer and [uv](https://docs.astral.sh/uv/). The package uses a src-layout
under `src/swelter/`, hatchling as the build backend, and a single runtime dependency (PyYAML);
everything else is the standard library.

```console
$ git clone https://github.com/ChelseaKR/swelter
$ cd swelter
$ uv sync          # create .venv and install runtime + dev deps from uv.lock
$ make verify      # run the full merge gate; should be all green before you start
```

`uv sync` installs from the committed `uv.lock`, so your environment matches CI. The Make targets
all run through `uv run`, so you do not need to activate the virtualenv by hand.

Optional but recommended: install the local guardrails that mirror CI.

```console
$ uv run pre-commit install
```

## Running the demo

`make demo` (or `uv run swelter demo --serve`) replays the recorded demo week through the whole
pipeline — ingest, QC, calibrate, aggregate, serve — with no hardware, and serves the dashboard at
`http://127.0.0.1:8000`. The demo network is the worked example in `network.yaml`: 18 nodes, 12 of
them calibrated from co-location records and 6 left raw-flagged, with node-07 going offline (the
longest gap), a PM range spike, and a flatlined humidity sensor for QC to catch.

`swelter demo` is deterministic. It also regenerates the offline dashboard sample at
`web/sample-surface.json`. If your change affects aggregation output, that file will change; commit
it in the same PR so the dashboard sample stays in step.

Useful per-stage targets while developing: `make ingest`, `make qc`, `make calibrate`,
`make aggregate`, `make export`, `make serve`, `make rebuild`. Run `make help` for the full list.

## Commit and PR conventions

- **Conventional commits.** `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`, `ci:`, etc.
  Scope is optional (`feat(calibrate): ...`). The subject line says what changed, in the
  imperative.
- **One concern per PR.** A bug fix and a refactor in the same PR are two PRs.
- **House style for prose.** Plain, concrete language. No marketing adjectives. Docs that state an
  external fact carry a `Last verified:` line and a recheck cadence.
- **Architecture decisions** go in `docs/decisions/NNNN-kebab-title.md` using the ADR format in the
  house style (Decision / Why / Known weakness). If your PR changes a load-bearing design choice,
  add an ADR.
- Update `CHANGELOG.md` under `Unreleased` for anything user-visible.

## The merge gate

Every PR must pass `make verify`, which is the full gate, end to end:

```
fmt-check  →  ruff format --check          (formatting)
lint       →  ruff check                   (E, F, I, UP, B, SIM; line length 100)
typecheck  →  mypy --strict                (must pass clean)
a11y       →  scripts/a11y_check.py        (structural WCAG 2.2 AA gate, 12 checks)
test       →  pytest                       (the suite is currently 62 tests, all green)
```

Run it locally before you push: `make verify`. CI runs the same thing, plus pip-audit, gitleaks,
and CodeQL (see `SECURITY.md`). A red gate blocks merge; there is no override for "just this once".

## Hard rules — these make a PR fail review

These come straight from the README's hard rules and are enforced, not aspirational. A reviewer will
reject a PR that does any of the following, regardless of how clean the rest of it is.

1. **Adds a field that could hold a person, or any surveillance capability.** The schema has no
   field that can locate or identify an individual, and it stays that way. Do not add a column,
   payload key, or config field that holds a name, a personal device identifier, a MAC address, a
   precise home address, an account, or anything that turns an environmental reading into a record
   about a person. Do not add firmware or ingest support for microphones, cameras, Bluetooth or
   Wi-Fi client scanning, or per-device tracking. Nodes measure the environment, not people. The
   only identifier is the node ID the hosting collective assigns. A PR adding any of this fails
   review.

2. **Mixes calibrated and raw silently.** Calibrated and raw values must always be distinguishable
   in storage, in aggregation, in the API, in exports, and on the map. A change that merges the two
   without carrying the calibration label, or that shows an uncalibrated value as if it were
   calibrated, fails review. (See the calibrated-vs-raw invariant below.)

3. **Breaks the accessibility gate.** `make a11y` is merge-blocking. A change that fails any of the
   12 structural WCAG checks, removes the table or list view, makes the map the only way into the
   data, or conveys AQI/heat severity by color alone fails review. The map, sortable table, and
   plain list are three equal views of one surface; keep them equal.

4. **Removes or degrades the export path.** Export is first-class. CSV, JSON (CC0-1.0), the
   read-only OGC SensorThings subset, and the Datasette-openable store are how the community keeps
   and moves its data. A PR that removes an export route, hides it behind an account or key, or
   makes the store non-portable fails review.

If you think a hard rule genuinely needs to change, that is an ADR and a conversation with the
maintainer first — not a PR that quietly crosses the line.

## Invariants you must preserve

These are the two properties most PRs can accidentally break. Keep them true.

### Calibrated vs raw

Every `Observation` carries a `calibration` field that is either the literal `"raw"` or a version id
of the form `"{parameter}.{method}.{node_id}"` (methods: `epa-humidity` for PM, `enclosure-offset`
for temperature and heat index, `linear` as default). The store key is
`(node_id, timestamp, parameter, calibration)`, so a raw reading and its calibrated counterpart are
two distinct rows that never overwrite each other — raw is append-only and immutable, and
`drop_calibrated()` can rebuild every derived value from raw alone.

Downstream this means:

- A node with no fitted correction stays **raw** and is shown **provisional** — never silently
  promoted to calibrated.
- `aggregate` prefers calibrated, QC-clean values per cell and marks the cell **provisional**
  otherwise; it does not average a calibrated and a raw value together as if they were the same
  kind of number.
- The API, CSV, and JSON all expose the calibration state. Do not drop it on the way out.
- Calibrated values carry `residual_std` as their 1-sigma uncertainty. Do not strip the uncertainty
  when you move a value through a layer.

If your change touches `models.py`, `calibrate.py`, `aggregate.py`, `api.py`, or `export.py`, check
that calibrated and raw remain distinguishable at every hop.

### Grid-snap (location privacy)

Exact node locations belong to the host. `config.snap_to_grid(lat, lon, grid_m)` returns the centre
of the grid cell containing a point, and `public_location()` snaps to a ~150 m grid (the network's
`grid_resolution_m`, default 150) **unless** the node's `location` is set to `"precise"` and the
host has opted in. `aggregate` snaps observations to published grid cells before they reach the
dashboard or API.

Preserve this:

- Never publish a precise coordinate for a node whose `location` is `"coarse"`. The coarse grid is
  the default and the precise value must never be required to use the system.
- Snapping is deterministic: the same point and the same resolution always land in the same cell, so
  re-running aggregation reproduces the same cells. Do not introduce a snap that depends on input
  order or wall-clock time.
- If you add a code path that emits coordinates (a new export format, a new API field, a new map
  layer), route it through `public_location()` / the published grid — do not read the raw config
  coordinate directly.

### Reproducibility of corrections

`calibrate` is pure-Python OLS (no numpy) and rounds fitted coefficients to 6 decimal places, so
re-running `fit()` on the committed co-location data reproduces `corrections.yaml` byte-for-byte
(the demo registry is 36 entries: 12 nodes × 3 parameters). If you change the fit, the rounding, or
the version-id format, you will break that byte-for-byte reproduction and the calibration replay
test. Regenerate and commit the registry in the same PR, and explain why in the commit and an ADR.

## Questions

Open an issue, or for anything sensitive use the private channel described in `SECURITY.md` and
`CODE_OF_CONDUCT.md`. The maintainer is Chelsea Kelly-Reif.

Last verified: 2026-06-16. Recheck when the toolchain, Make targets, or hard rules change (at least
once per release).
