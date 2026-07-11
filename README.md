# swelter — a community heat and air-quality sensing network with open data

[![CI](https://github.com/ChelseaKR/swelter/actions/workflows/ci.yml/badge.svg)](https://github.com/ChelseaKR/swelter/actions/workflows/ci.yml)
[![code: Apache-2.0](https://img.shields.io/badge/code-Apache--2.0-blue.svg)](LICENSE)
[![data: CC0-1.0](https://img.shields.io/badge/data-CC0--1.0-brightgreen.svg)](DATA-LICENSE)
[![accessibility: WCAG 2.2 AA](https://img.shields.io/badge/accessibility-WCAG%202.2%20AA-success.svg)](docs/accessibility/ACR.md)

**[▶ Live demo](https://chelseakr.github.io/swelter/)** — the dashboard on **real, current** data, refreshed daily, in two views you can switch between: **[all of California](https://chelseakr.github.io/swelter/)** (Copernicus CAMS air quality + heat across 337 cities, on a county-outline map) and **[Stuttgart](https://chelseakr.github.io/swelter/sensors/)** (real community low-cost sensors, Sensor.Community). AQI and heat-island map with table and list views, English and Spanish.

> A neighborhood-owned mesh of low-cost heat and air-quality sensors, a time-series pipeline that
> ingests their readings, calibration that corrects sensor drift against reference monitors, and an
> accessible public dashboard that maps urban heat islands and AQI block by block. Built for
> frontline neighborhoods that live the exposure and rarely hold the data. The readings are
> aggregate environmental measurements: no people, no devices-as-trackers, no PII. The data is open
> by default and exports through open standards so anyone can audit, reuse, or fork it.

**Status:** Maintained — reference implementation · independent personal open-source project ·
Apache-2.0 · unaffiliated with any employer or client; contains no proprietary or client material;
not a government system and not built for a government customer.

**Supported versions:** pre-1.0, only the latest release is supported. Per
[`docs/VERSIONING.md`](docs/VERSIONING.md), a breaking change may still ship in a MINOR bump before
1.0, but every breaking change is called out explicitly in the [CHANGELOG](CHANGELOG.md).

**Why this domain.** Extreme heat kills more people in the United States than any other weather
hazard, and the burden lands hardest on low-income neighborhoods with little tree canopy, older
housing, and the worst air. The public reference networks that exist are sparse: a city of half a
million might have one regulatory air monitor and no fixed heat sensors at street level, so the
block-scale differences that decide who suffers are invisible in the official record. Low-cost
sensors can fill that gap, but only if someone handles the unglamorous parts honestly: they drift,
they read high in humidity, and a dashboard that maps raw values without calibration misleads the
people it claims to serve. swelter is the calibration, the open pipeline, and the readable map,
owned by the community that hosts the sensors. It is a sibling project to the GTFS and fare-policy
civic-data work in this portfolio and reuses their discipline around versioned data, plain-language
findings, and audited accessibility.

---

## What it does

- **Ingests** readings from a mesh of low-cost sensor nodes (temperature, humidity, and particulate
  matter at PM2.5 / PM10, with optional NO2 and a wet-bulb-globe-style heat index derived on
  device) into a time-series store, tolerating gaps, duplicates, and nodes that drop offline.
- **Calibrates** each node. A field calibration corrects for the known biases of low-cost sensors
  (humidity inflation of optical PM counts, enclosure heating, slow baseline drift) by co-locating
  nodes next to a reference-grade monitor for a training window and fitting a per-node correction
  that is then applied to the live stream. Every published value carries its correction provenance.
- **Maps** the results: an interactive heat-island and AQI map at neighborhood resolution, with a
  time slider, and the same data offered as a sortable table and a plain list so the map is never
  the only way in.
- **Exports** everything through open standards. A read-only **OGC SensorThings API** serves the
  observations for tooling; flat **CSV and JSON** dumps and a bundled **Datasette** instance let a
  resident, a reporter, or a researcher query the full history without an account or a key.

```console
$ swelter export --since 2026-06-01 --format csv --store store > heat.csv
swelter: 177,050 observations from 150 nodes (100 calibrated, 50 raw-flagged)
         calibration applied: pm10_ugm3.epa-humidity ×100; pm25_ugm3.epa-humidity ×100; temp_c.enclosure-offset ×100
         coverage: 2026-06-01T00:00:00Z → 2026-06-08T00:00:00Z, longest gap 2940 min (node-07 offline)
         data license: CC0-1.0 (observations) · see DATA-LICENSE
```

The calibration models, their training windows, error bounds, and the reference monitors they were
fit against are documented in `docs/calibration.md` and queryable from the API, so a value's
trustworthiness is inspectable rather than asserted.

- **Citable, versioned data snapshots.** `swelter snapshot` freezes the immutable raw observations,
  the fitted correction registry, and the latest gridded surface into a self-contained, identified
  release — a `MANIFEST.json` with per-file SHA-256, record count, and observation time-window, plus
  a dataset `DATA-CITATION.cff` (Citation File Format 1.2.0, `type: dataset`, CC0-1.0, distinct from
  the repository's software `CITATION.cff`) and a ready-to-paste `CITATION.txt`. Local artifacts
  only — no external DOI service is called; pass `--doi` once a collective has minted one (e.g. via
  Zenodo/DataCite), otherwise the release carries an honestly-labelled placeholder.

  ```console
  $ swelter snapshot --store store --out dist/snapshot --doi 10.5281/zenodo.1234567
  swelter: snapshot 0.1.0 → dist/snapshot (126510 raw observations, 3 file(s))
  Kelly-Reif, C. (2026). swelter observation snapshot 0.1.0 [Data set]. CC0-1.0. https://doi.org/10.5281/zenodo.1234567
  ```

**Synthetic demo vs. real data.** `swelter demo` replays a *synthetic* fixture (deterministic, the
calibration story made checkable) — the dashboard labels it as such. `swelter fetch` pulls **real**
current data from a live open-data source — no API key, no hardware — through the identical pipeline
(QC, aggregation, map/table/list, API, export). Every value carries its provenance, and the
dashboard shows the source on screen. Three real sources ship:

- `swelter fetch --source openaq` — dense **real physical sensors across California** from
  [OpenAQ](https://openaq.org) (community PurpleAir nodes, regulatory reference monitors, and more),
  often several per neighborhood — the source that actually delivers swelter's **block-by-block**
  promise with real hardware. Real but *uncalibrated*, so ingested **raw** and shown **provisional**.
  Needs a free API key (`OPENAQ_API_KEY`, or `--api-key`; sign up at
  [explore.openaq.org](https://explore.openaq.org/register)); throttled and capped for the free tier.
- `swelter fetch --source openmeteo` — real hourly air quality (Copernicus CAMS) and weather for
  **337 cities across all of California**, from [Open-Meteo](https://open-meteo.com), drawn on a
  California county-outline basemap. **Keyless**, real and current, but *model/reanalysis* output —
  coarse (nearby cities share a grid cell), **not** physical sensors and **not** swelter-calibrated.
  (The place list is coordinate-checked point-in-polygon against US Census county boundaries; the
  basemap is public-domain cartographic data.) The live demo uses this when no OpenAQ key is set.
- `swelter fetch --source sensor-community` — real **physical low-cost sensors** from the community
  [Sensor.Community](https://sensor.community) network (dense in Europe; defaults to Stuttgart, its
  origin). These are exactly what swelter is built for: community-owned, low-cost, and *uncalibrated*
  — so they ingest as **raw** and the dashboard shows them **provisional**, the honest posture for a
  sensor that drifts until a reference monitor corrects it. The adapter also drops the SDS011's
  999.9 µg/m³ over-range fault sentinel so a saturated sensor never reads as "Hazardous."
- `swelter fetch --source sensor-community` — real **physical low-cost sensors** from the community
  [Sensor.Community](https://sensor.community) network (dense in Europe; defaults to Stuttgart, its
  origin). These are exactly what swelter is built for: community-owned, low-cost, and *uncalibrated*
  — so they ingest as **raw** and the dashboard shows them **provisional**, the honest posture for a
  sensor that drifts until a reference monitor corrects it. The adapter also drops the SDS011's
  999.9 µg/m³ over-range fault sentinel so a saturated sensor never reads as "Hazardous."

---

## Hard rules (enforced, not aspirational)

1. **No surveillance, by construction.** Nodes measure the environment, not people. The firmware has
   no microphone, no camera, no Bluetooth or Wi-Fi client scanning, and no per-device identifiers
   beyond a node ID the hosting collective assigns. There is nothing in the data that locates a
   person, and the schema has no field that could carry one. A pull request that adds one fails
   review.
2. **Exact node locations are the host's to disclose.** A sensor sits on someone's porch or fence.
   Public coordinates are snapped to a coarse grid (default ~150 m) unless the host opts into a
   precise location, and the precise value is never required to use the system. Hosting a sensor
   must not expose where a person lives.
3. **Calibrated and raw are always distinguishable.** A reading is labeled with its calibration
   state and the correction applied, or it is flagged raw. The map and the export never silently mix
   the two, and an uncalibrated node is shown as provisional, not as fact.
4. **The data is open and portable.** Observations are published under CC0; the code is Apache-2.0.
   Export is a first-class command, not an afterthought, so the community can leave with its data and
   stand the network up elsewhere. No lock-in to this codebase or any host.
5. **Owned by the people who host it.** Governance, sensor siting, and any decision to share precise
   locations rest with the local collective, documented in `docs/governance.md`. swelter is a tool
   they run, not a service that runs them.

---

## Architecture

```
swelter/
├── README.md
├── firmware/                      # node firmware (C / MicroPython) for the sensor hardware
│   ├── src/                       # sampling, on-device heat index, store-and-forward buffer
│   └── hardware/                  # BOM, enclosure notes, assembly guide (build-it-yourself)
├── src/swelter/
│   ├── ingest.py                  # MQTT/HTTP intake → validate → time-series store; idempotent
│   ├── store.py                   # time-series schema (Parquet + SQLite/Datasette; pluggable)
│   ├── calibrate.py               # co-location fit, drift correction, per-node correction registry
│   ├── qc.py                      # range/spike/flatline checks; gap detection; node health
│   ├── aggregate.py               # spatial/temporal rollups; heat-island and AQI surfaces
│   ├── api.py                     # read-only OGC SensorThings + CSV/JSON export
│   ├── server.py                  # serves the dashboard and the API; scale-to-zero friendly
│   └── config.py                  # nodes, calibration windows, grid resolution as versioned files
├── web/                           # framework-free WCAG 2.2 AA dashboard: map + table + list views
├── infra/                         # optional serverless deploy (CDK), scale-to-zero, budget alarm
├── docs/                          # ARCHITECTURE, calibration.md, governance.md, DATA-LICENSE, ADRs, audits/, accessibility/
└── pyproject.toml
```

Readings flow one way: nodes buffer and forward to `ingest`, which validates and writes immutable
observations to the store; `calibrate` fits and registers per-node corrections from co-location
windows; `aggregate` builds the gridded heat and AQI surfaces the dashboard and API read. The store
is plain columnar files plus a SQLite database that Datasette can open directly, so the whole archive
is a folder you can copy. The firmware uses store-and-forward buffering so a node that loses
connectivity backfills when it returns rather than losing the gap. Calibration corrections are
versioned data in a registry, not code, so recalibrating a node is a data change with an audit trail.

## The calibration engine (the part that earns trust)

A low-cost PM sensor can read double the true concentration on a humid morning, and a sensor in a
black enclosure in the sun reports the box's temperature, not the air's. A network that ignores this
produces a map that is precise and wrong. swelter treats calibration as the core feature, not a
footnote.

- **Co-location training.** A node is placed beside a reference-grade monitor (a regulatory station
  or a known-good instrument) for a training window. `calibrate` fits a per-node, per-parameter
  correction — a humidity-aware PM correction in the lineage of the US-EPA PurpleAir model, an
  enclosure-offset term for temperature — and records the window, the reference source, the fitted
  coefficients, and the residual error.
- **Drift tracking.** Sensors age. The correction registry is versioned and timestamped; periodic
  re-co-location updates it, and a node whose residuals widen past a bound is flagged for service
  before its data is trusted. Each published observation names the correction version that produced
  it.
- **Honest error bars.** Every calibrated value carries an uncertainty derived from the calibration
  residuals. The dashboard shows AQI categories with their confidence, and a value the model cannot
  stand behind is shown as provisional rather than dressed up as certain.
- **Auditable end to end.** The training data, the fit, the bounds, and the corrections are committed
  and queryable. Anyone can re-run `swelter calibrate` against the recorded co-location data and
  reproduce the published corrections, so the calibration is checkable, not taken on faith.

---

## Quality attributes (engineered for, not assumed)

This section works through the full system-quality-attribute list and ties each to a concrete
decision. Grouped for readability; every attribute is named. A community sensing network lives or
dies on trustworthy readings, an honest map, and data the community can keep, so those clusters
carry weight.

### Correctness, accuracy, and trust in readings
**Correctness** and **accuracy** — calibrated against reference monitors with residuals recorded;
QC checks reject impossible values before they publish. **Precision** and **fidelity** — observations
keep their native units and timestamps; corrections are applied without lossy rounding, and a value's
uncertainty is published with it. **Integrity** — observations are immutable once written and
content-hashed; an edit is a new record, never an overwrite. **Determinability** and **predictability**
— the same raw stream and the same correction version yield the same published values, every run.
**Repeatability** and **reproducibility** — calibration is re-runnable from committed co-location data
to byte-identical corrections; aggregation is deterministic. **Provability** — every observation
carries its node, correction version, and QC verdict, so a reader can trace why a number is what it is.
**Traceability** — raw reading → correction → aggregate → map tile is recorded end to end. **Relevance**
— gridded at neighborhood scale because block-level exposure is the question, not city averages.
**Effectiveness** — measured against reference monitors, reported as error against ground truth, not
asserted.

### Privacy, security, accountability
**Confidentiality** and **securability** — no PII exists to leak; the schema cannot hold one; the API
is read-only and the write path is authenticated per node. **Integrity** (supply chain) — pinned,
hashed dependencies; signed releases; SLSA-friendly Actions. **Vulnerability** management — pip-audit,
gitleaks, and CodeQL in CI; firmware dependencies pinned. **Auditability** and **accountability** —
the full observation archive, calibration registry, and QC log are committed evidence; releases record
data, code, and calibration versions. **Credibility** and **transparency** — calibration methods,
error bounds, and known sensor limitations are documented openly; the dashboard says what it does not
know. **Autonomy** — the hosting collective controls siting, location precision, and sharing, recorded
in governance docs.

### Usability, learnability, reach
**Accessibility** — WCAG 2.2 AA enforced as a merge gate; the map always has an equivalent data table
and a plain list, and AQI severity is never color alone. **Usability** and **convenience** — open the
dashboard, read your block, download the CSV; no account. **Learnability**, **familiarity**, and
**intuitiveness** — a map with a time slider and a legend that explains AQI in plain words; first
reading visible within one screen. **Interactivity** and **responsiveness** — the time slider redraws
without a round-trip; tiles and tables are pre-aggregated for fast pans. **Discoverability** — example
queries and an API browser are linked from the dashboard. **Demonstrability** — `make demo` replays a
recorded week of sensor data into a live dashboard with no hardware. **Understandability** — each
reading shows its calibration state and confidence. **Seamlessness** — map, table, list, and export
read the same underlying observations. **Localizability** — all dashboard strings live in per-language
bundles; Spanish ships in v1 given the communities served. **Convenience**, **mobility**, and
**ubiquity** — mobile-first, installable as a PWA, usable on a phone at a tenant meeting or a city
council hearing.

### Dependability, resilience, safety
**Dependability** and **reliability** — a node dropping offline degrades coverage gracefully; the
pipeline backfills from node buffers rather than losing data. **Availability** — the dashboard is
static plus a scale-to-zero API; there is no always-on component that failing takes the data down with
it. **Fault-tolerance**, **resilience**, **robustness**, and **survivability** — store-and-forward
firmware survives connectivity loss; malformed payloads are quarantined, not ingested; the archive is
a copyable folder that outlives any single host. **Recoverability** — the store and all derived
surfaces rebuild from immutable raw observations via `make rebuild`. **Degradability** and
**failure transparency** — a stale or uncalibrated node is labeled provisional on the map, never
silently shown as good. **Redundancy** — overlapping node coverage and dual QC paths (range and
temporal) catch
single-sensor failures. **Stability** and **durability** — versioned observation snapshots; semver on
the public API and data schema. **Safety** — heat and AQI guidance shown on the dashboard is framed as
public-health context with sources, and the system never tells an individual they are safe, only what
the air and heat readings are.

### Performance, scale, cost
**Efficiency** — columnar storage and pre-aggregated tiles keep queries cheap. **Scalability** and
**elasticity** — ingestion is stateless and horizontal; serverless API scales to zero between visitors;
the store partitions by time so it grows without slowing. **Timeliness** — readings reach the dashboard
within a sampling interval; ingestion and aggregation latency are asserted in CI. **Affordability** —
the whole network is buildable from a documented bill of materials at low per-node cost, and the cloud
footprint is single-digit dollars a month with a budget alarm, because a community group is funding it.
**Process capabilities** and **producibility** — `make verify` reproduces the full gate; one command
builds and publishes the artifact set.

### Maintainability, evolvability, modularity
**Maintainability**, **modifiability**, and **evolvability** — small modules behind interfaces; ruff +
mypy strict; the store backend is pluggable. **Extensibility** and **flexibility** — new sensor
parameters and new calibration models plug in via a registry; the export layer takes new formats
without touching ingest. **Adaptability** — point it at a different city's nodes and reference monitors
through config. **Modularity**, **composability**, and **orthogonality** — ingest, store, calibrate,
aggregate, serve, and export are independent layers. **Simplicity** — files and SQLite, no cluster, no
proprietary database. **Reusability** — the calibration and QC modules are importable and corpus-agnostic.
**Analyzability** — typed, documented, with an architecture doc. **Configurability**, **customizability**,
and **tailorability** — one config sets nodes, grid resolution, calibration windows, and languages.
**Upgradability** — pinned dependencies with a documented bump path; firmware over-the-air updates are
signed and staged.

### Operability, serviceability, sustainability
**Operability** and **manageability** — a node-health view and a 2 a.m. runbook; a health endpoint for
the API. **Administrability** — config-over-code; siting and calibration policy live in committed YAML,
no admin console required. **Observability** — structured logs and metrics on ingestion, QC, and node
liveness. **Debuggability** — any observation can be traced from raw payload to map tile under a debug
flag. **Serviceability / supportability** and **repairability** — the hardware guide covers field
service, and most software fixes are data or config edits; sensors are chosen for repairable,
off-the-shelf parts. **Deployability** and **installability** — `uv sync` + a one-command deploy from
source (`make demo` / `swelter serve`), or the optional CDK stack in `infra/`; no PyPI package or
container image is published today (see Standards conformance, DOC-14). **Agility** — a CI smoke suite
on every PR. **Autonomy**, **self-sustainability**, and **sustainability** — runs on cheap commodity
hardware and a scale-to-zero backend with no paid dependency, so the network survives lean years and
keeps reporting untended.

### Compatibility, interoperability, standards, verification
**Compatibility** and **interoperability** — the OGC SensorThings API and CSV/JSON exports let standard
GIS and analysis tools consume the data unchanged. **Interchangeability** — the store backend and the
sensor hardware swap without touching callers; SensorThings means another platform can read swelter and
swelter can read another. **Standards compliance** — OGC SensorThings, WCAG 2.2 AA, semver, conventional
commits, SPDX headers, CC0 for the data. **Inspectability** — raw observations, corrections, and QC
logs are all viewable and queryable. **Composability** — observations are plain data others can pipe and
join. **Testability** — recorded sensor streams and reference data make ingestion, calibration, and
aggregation unit-testable offline; verification attributes (provability, repeatability, reproducibility,
traceability, demonstrability) are covered above and exercised by the calibration replay.

### Distribution, portability, installation
**Distributability** — the data ships as a downloadable archive and a public API; the code is
distributed as source (git clone + `uv sync`) with signed, provenance-attested sdist/wheel artifacts
attached to each GitHub Release — not (yet) published to PyPI or a container registry (tracked gap,
see Standards conformance below). **Portability** — pure-Python services plus open data formats run on Linux,
macOS, and a Raspberry-Pi-class host. **Installability** — one command for the service, a documented
flash for the firmware. **Deployability** — committed IaC stands the cloud copy up; a host can also run
it on a single board computer with no cloud at all.

---

## Accessibility and Section 508 conformance

swelter targets **WCAG 2.2 Level AA** and conformance with the **Revised Section 508 Standards**
(36 CFR Part 1194), which incorporate WCAG 2.0 A/AA by reference for web content and add the functional
performance criteria of Chapter 3. A community-run dashboard is not federal ICT, so Section 508 is not
legally required here. Building to it anyway is deliberate: the people most exposed to heat and bad air
include disabled residents and elders, and an environmental-justice tool that is not itself accessible
fails the people it is for. Conforming to the standard governments audit to also makes the data usable
to the widest public.

- A committed **Accessibility Conformance Report (ACR)** using the **VPAT 2.5 (Rev 508)** template lives
  at `docs/accessibility/ACR.md`, with tables for the WCAG 2.x A/AA success criteria, the Revised 508
  software (Chapter 5) and support-documentation (Chapter 6) criteria, and the **Functional Performance
  Criteria** (use without vision, with limited vision, without hearing, with limited reach and strength,
  with limited cognition).
- The interactive map has a **non-visual equivalent**: the same observations render as a sortable data
  table and a plain readings list with identical filtering, so a screen-reader user gets the full
  dataset without the map. AQI and heat severity are conveyed by text and pattern, never color alone, and
  every chart has an associated data table.
- The dashboard passes automated checks (axe) **and** manual screen-reader review (NVDA, VoiceOver); the
  time slider is keyboard operable with announced value changes, and focus is never trapped.
- Accessibility is a **merge-blocking CI gate**; a regression fails the build. The ACR is regenerated and
  re-committed on each release, the same audit-as-artifact discipline as the calibration record.

## Standards conformance

swelter is audited against a shared, personal standards set (quality, security/supply-chain, CI/CD,
release/versioning, accessibility, observability, i18n, AI-evaluation, documentation, responsible
tech). Per that standard's own rule, a repo must declare which standards apply and state a reason
for any N/A — silent omission is itself a defect, which is why this table exists. States below are
current as of the **2026-07-05** conformance audit and same-day remediation pass; `Applies — gap`
rows name the specific missing piece rather than leaving it implicit.

| Standard | Applies? | State |
|---|---|---|
| Quality & metrics | Applies | Gap — `make verify` (fmt-check, lint incl. bandit `S` + complexity `C901`, typecheck, a11y, i18n, test) is green and merge-blocking with a 90%-branch-coverage floor (93%+ measured); REVIEW artifacts (DORA ledger, per-source data cards, acceptance-test↔feature mapping) not yet written |
| Code quality | Applies | Gap — ruff (incl. bandit + mccabe ≤10) and `mypy --strict` are clean over `src`/`tests`; `.github/CODEOWNERS` committed; ADRs use a house format, not MADR (`docs/adr/`); no mutation testing yet on `calibrate.py`/`qc.py` |
| Security & supply chain | Applies | Gap — pip-audit, gitleaks, and CodeQL (`python` + `actions`) run in CI; releases are signed (cosign) with SLSA provenance and now re-run `make verify` at the tag; still missing: Semgrep, osv-scanner, scheduled TruffleHog, zizmor, Scorecard, and a CycloneDX SBOM |
| CI/CD | Applies | Gap — CI runs `make verify` directly (no hand-mirrored steps to drift); all 22 `uses:` are SHA-pinned. **No branch-protection ruleset is enforced yet** — see the incident note below; that is a manual GitHub-settings step this repo's maintainer still needs to take |
| Release & versioning | Applies | Gap — semver policy in `docs/VERSIONING.md`; releases now assert an annotated tag, a dated CHANGELOG section, and a green `make verify` before signing/publishing; still missing: SBOM attachment, a `verify-published` job, and a single source of truth for `__version__` |
| Accessibility | Applies | Gap — WCAG 2.2 AA structural gate (12 checks) is merge-blocking; a VPAT 2.5 ACR is committed; the axe/pa11y browser pass and Lighthouse CI are still advisory-only, not blocking |
| Observability | Applies — light tier | **Tier B**: the deployed GitHub Pages dashboard (static; lab Web-Vitals/Lighthouse gates not yet wired). **Tier A: N/A** — no deployed always-on service; the stdlib `swelter serve` is an optional local/self-hosted process, not a hosted backend. **RUM: N/A** — deliberate privacy choice, no client-side telemetry of any kind |
| Internationalization | Applies | Gap — `docs/I18N.md` tracks this in detail; UTF-8, BCP-47, EN/ES key-parity, and the CLDR-pin guard (G1/G3/G4/G6/G12) are live merge-blocking gates; the hardcoded-string ratchet and full plural-category completeness (G2/G7) are not yet wired |
| AI evaluation | **N/A** | No LLM or AI feature anywhere in swelter; the sole runtime dependency is PyYAML, and the pipeline (ingest → QC → calibration → aggregation) is deterministic ordinary-least-squares fitting and rule-based flagging, not a model |
| Documentation | Applies | Gap — README, `CLAUDE.md`, ADRs, and `docs/audits/` are committed and dated; no automated staleness/pin-drift gate yet (tracked) |
| Responsible tech | Applies | Gap — six dated audits at `docs/RESPONSIBLE-TECH-AUDITS.md` (A–F) plus a DPIA and an accessibility report; being refreshed against the 2026-07-01 authenticated write path (`ingest-serve`) |

**Known gate-integrity incident (disclosed, not hidden).** On 2026-07-02 three commits (the
authenticated-write-path feature) merged directly to `main` with a red `make verify` and no PR
reference — the only such commits in this repo's history. The 2026-07-05 audit caught it; the
red gate was fixed the same day (ruff/mypy clean again) and this table, `release.yml`'s
re-verify-at-tag step, and `.github/CODEOWNERS` are part of closing the gap. **A GitHub branch-
protection ruleset that would have prevented this is not yet enabled** — that is a manual,
repo-settings action the maintainer must take (see the incident note this remediation pass could
not apply on the maintainer's behalf).

## Build plan

- **Phase 1 — pipeline to first reading.** Node firmware sampling and store-and-forward; ingestion into
  the time-series store; QC checks; CSV/JSON export. Definition of done: one command turns a recorded
  raw stream into a queryable, QC-flagged dataset locally.
- **Phase 2 — calibration.** Co-location fit, the correction registry, drift tracking, and published
  uncertainty. Calibrated-vs-raw labeling enforced through the pipeline. Calibration replay reproduces
  committed corrections in CI.
- **Phase 3 — dashboard and open API.** The map, table, and list views; the OGC SensorThings API and
  Datasette bundle; heat-island and AQI surfaces. WCAG 2.2 AA met and gated; mobile-first; deployed
  behind a real URL with Spanish parity.
- **Phase 4 — generalize.** A `network.yaml` so any community can register its nodes and reference
  monitors and stand up its own instance, with an "add your neighborhood in an afternoon" guide
  ([`docs/ADD-YOUR-NEIGHBORHOOD.md`](docs/ADD-YOUR-NEIGHBORHOOD.md)) and the hardware build doc finished.

## Engineering and open-source practices

pytest for every deterministic component (ingest, QC, calibration, aggregation, export); ruff + mypy
strict in CI; calibration and aggregation runs are content-hashed and reproducible; `make verify`
reproduces the full gate end to end. The repo ships LICENSE (Apache-2.0 for code), DATA-LICENSE (CC0 for
observations), NOTICE (independence statement), CODE_OF_CONDUCT, CONTRIBUTING, SECURITY, a semver policy
covering the API and data schema, ADRs, and committed `docs/audits/`. Conventional commits; pinned,
SLSA-friendly GitHub Actions; signed releases; Dependabot. Firmware is built and checked in CI alongside
the services.

## Definition of done

A neighborhood collective can build a node from the documented parts, flash it, watch its readings land
in the store, run `swelter calibrate` to correct it against a reference monitor and reproduce the same
corrections anyone else would get, open a dashboard that maps their block's heat and air with honest
confidence and a full table alternative, and download the entire history as CC0 CSV — with every CI gate,
including the accessibility gate, green.

## For Claude Code

[`CLAUDE.md`](CLAUDE.md) is the build spec and operating contract: the product framing, the hard
rules as guardrails, the phased plan ([`docs/ROADMAP.md`](docs/ROADMAP.md)), and the quality bar.
Execute phases in order, keep `make verify` green, and never weaken the hard rules — a change that
adds a field able to hold a person, mixes calibrated and raw silently, or breaks the accessibility
gate does not merge. Start at [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).
