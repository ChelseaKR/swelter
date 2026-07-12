# Responsible-tech audits

Last verified: 2026-06-16. Recheck cadence: each release, and whenever a named module or its CI
gate changes.

Six audits for swelter, a community heat and air-quality sensing network. Each one is grounded in
this codebase — the modules, the demo network, the hard rules — not in generic responsible-tech
boilerplate. How the audits work, and what "auto-gated" versus "review-gated" means, is in
[audits/methodology.md](audits/methodology.md). Two of the audits have fuller write-ups:
[audits/privacy-dpia.md](audits/privacy-dpia.md) and
[audits/accessibility-report.md](audits/accessibility-report.md).

**Applicability.** Audits A–F below apply and are in scope. Internationalization is in scope
separately at [`docs/I18N.md`](I18N.md) (en/es resident-facing copy). **AI-evaluation is N/A**: no
LLM or AI feature exists anywhere in swelter; the sole runtime dependency is PyYAML, and the
pipeline is deterministic ordinary-least-squares fitting and rule-based QC, not a model. See also
the README's [Standards conformance](../README.md#standards-conformance) table for the full
11-standard declaration.

Each checklist marks every item one of two ways:

- **[auto]** — a deterministic check in `make verify` or a CI workflow blocks the merge if it
  fails. No signature needed; the machine re-proves it on every PR.
- **[review]** — needs human judgement; the gate is a dated, attributed artifact committed to the
  repo (an ADR in `docs/decisions/`, an updated section in one of these audit docs, or a manual
  review note).

The full merge gate is `make verify` = `fmt-check` + `lint` + `typecheck` + `a11y` + `i18n` +
`hygiene` + `version-check` + `test` (currently green). The supply-chain and code-scanning gates
(`pip-audit`, `gitleaks`, Semgrep, zizmor, CodeQL, a weekly full-history TruffleHog sweep, signed
releases) run as CI workflows alongside it; `gitleaks` also runs as a pre-commit hook.

---

## A. Ethics and responsibility

**The consequence that drives this audit.** swelter exists because the official record is sparse:
a city of half a million may have one regulatory air monitor and no street-level heat sensors, so
the block-scale differences that decide who suffers in a heat wave are invisible. A community map
fills that gap — but a *wrong* map is worse than no map, because it misleads the exact people it
claims to serve. A low-cost PM sensor can read double the true concentration on a humid morning; a
sensor in a sunlit black enclosure reports the box's temperature, not the air's. A map that
publishes those raw numbers as fact is precise and wrong, and a resident who trusts it makes a
worse decision than one who trusts nothing.

**The response: calibration plus honest provisional labelling.** swelter treats calibration as the
core feature. Each node is co-located against a reference monitor and gets a per-node correction
(humidity-aware PM in the US-EPA PurpleAir lineage; an enclosure-offset for temperature), with the
fit, the window, and the residual error committed and reproducible. A value the model cannot stand
behind is shown **provisional**, not dressed up as fact. In the demo network, two-thirds of the nodes
are calibrated and the rest are not; the uncalibrated nodes are surfaced raw and provisional, never
silently mixed into the trustworthy layer (`Observation.is_trustworthy` is calibrated *and* not
QC-rejected). Every value carries its 1-sigma uncertainty.

**Non-goals (stated so they cannot creep in).**

- **No surveillance.** Nodes measure the environment, not people. The firmware has no microphone,
  camera, Bluetooth, or Wi-Fi client scanning, and no per-device identifiers (hard rule 1). The
  observation schema has no field that can hold a person.
- **No individual safety claims.** The dashboard reports what the air and heat readings are, with
  public-health context and sources. It never tells an individual they are safe. "The heat index
  reads 41 °C in this cell" is a measurement; "you are safe to go out" is a claim swelter does not
  make.

**Misuse resistance.** The data is CC0 and public on purpose, so the misuse surface is not
"exfiltration" but "misrepresentation": someone strips the provisional flag and presents raw
numbers as calibrated, or maps a single-node cell as a doorstep. The defences are that calibration
state travels *with every value* through the API and export (it cannot be separated in transit
without re-authoring the data), that the public surface is read-only so the record itself cannot be
altered, and that location is grid-snapped by default so the map does not hand out home addresses.

### Checklist

| # | Item | Gate | CI |
|---|------|------|----|
| A1 | Uncalibrated values are labelled raw/provisional end to end (not silently mixed) | **[auto]** | `make test` — calibrated-vs-raw and `is_trustworthy` tests |
| A2 | Every calibrated value carries a 1-sigma uncertainty | **[auto]** | `make test` — calibration applies `residual_std` |
| A3 | Calibration is reproducible from committed co-location data to byte-identical corrections | **[auto]** | `make test` — calibration replay |
| A4 | No surveillance: schema has no person-bearing field | **[auto]** | `make typecheck` + `make test` (schema tests) |
| A5 | A PR adding a person-bearing field, mic/camera/BT/Wi-Fi scan, or per-device id is rejected | **[review]** | ADR / PR review against hard rule 1 |
| A6 | The dashboard makes no individual safety claim; guidance is framed as context with sources | **[review]** | UI-copy review note, updated here on `web/` change |
| A7 | Misuse scan re-read each release (misrepresentation, single-node-cell doorstepping) | **[review]** | This section's "Last verified" date |

---

## B. Bias and fairness

**The fairness stake is coverage, not a classifier.** swelter makes no predictions about people,
so there is no model bias in the usual sense. The fairness question is geographic: *which
neighborhoods get a trustworthy reading, and which get only a provisional one or none at all?* The
whole reason the network exists is that official monitors are sparse in frontline areas — the
low-income, low-canopy, older-housing blocks that carry the worst heat and air. If swelter
reproduces that sparsity, it fails on its own terms.

**The two-tier-map risk.** Calibrated values are trustworthy; raw values are shown provisional.
That distinction is honest and necessary (audit A). But it creates a fairness hazard: if the
calibrated nodes cluster in one part of the network and the raw nodes in another, the map splits
into a confident half and a provisional half — and if the provisional half lands on the frontline
blocks, the tool has quietly recreated the very inequity it was built to expose. In the demo
network this is visible and deliberate as a test case: the first two-thirds of the nodes are
calibrated and the rest are raw, and a coverage-equity read has to confirm the raw set is not
concentrated in the highest-exposure cells. **Calibration access must not become a proxy for
neighborhood.**

**Mitigations.**

- The aggregator does not drop a cell that lacks a calibrated, QC-clean value — it marks the cell
  **provisional** (`aggregate.py`). A gap is shown as a gap, never as "Good" by omission. Absence
  of a confident reading is itself reported, so an under-covered block is visible rather than
  blank.
- Co-location capacity (time at the reference monitor) is the scarce resource that decides who gets
  calibrated. Allocating it is a governance decision the hosting collective owns; the audit's job
  is to surface the current distribution, not to optimise it silently.
- Coverage equity is read per neighborhood each release: how many calibrated vs raw nodes, and
  whether the raw/provisional cells correlate with the frontline blocks the network is for.

### Checklist

| # | Item | Gate | CI |
|---|------|------|----|
| B1 | A cell with no calibrated, QC-clean value is marked provisional, not dropped or defaulted | **[auto]** | `make test` — aggregate provisional-cell tests |
| B2 | Raw and calibrated cells are distinguishable on the map, table, and list | **[auto]** | `make test` + `make a11y` (severity by text/pattern) |
| B3 | Per-neighborhood coverage read each release: calibrated vs raw node counts | **[review]** | Coverage-equity note, updated here |
| B4 | Raw/provisional cells checked for correlation with highest-exposure blocks | **[review]** | Coverage-equity note |
| B5 | Co-location allocation recorded as a governance decision, not an implicit default | **[review]** | `docs/governance.md` / ADR |
| B6 | New node onboarding does not default the frontline blocks to the raw tier | **[review]** | Onboarding review against this audit |

---

## C. Privacy and data protection

**DPIA in brief; the full assessment is [audits/privacy-dpia.md](audits/privacy-dpia.md).**

**Data inventory.** swelter processes aggregate environmental measurements only: temperature,
humidity, PM2.5, PM10, NO2, and a derived heat index — one value per parameter per node per
timestamp. The `Observation` record (`models.py`) is `node_id`, `timestamp`, `parameter`, `value`,
`unit`, `calibration`, `qc`, `uncertainty`. **There is no PII field**: no name, device id, MAC,
owner, account, or precise person-coordinate, and the dataclass is frozen so one cannot be added at
runtime.

**The one real risk: node location.** A node sits on a host's porch or fence, so a precise
published coordinate points at someone's home — and hosts in frontline neighborhoods may have
specific reasons not to want that inferable. This is an indirect identifier held in *config*
(`network.yaml`), never in the observation record.

**Threat model and the grid-snap mitigation.** The threats are re-identifying a host's home off the
map or the API, triangulating across the map/API/export, and single-node-cell doorstepping. The
mitigation is in code, not policy: `config.public_location()` is the only coordinate the rest of
the system may read, and it returns `snap_to_grid(...)` — the centre of a ~150 m cell — unless the
host explicitly sets `location: precise`. The default is `coarse`; precise is opt-in. The API's
`things()`, the GeoJSON surface, the dashboard, and the export all read this one path, so there is
no second, finer coordinate to leak. Full threat table in the DPIA.

**Firmware has no sensors of people.** No microphone, camera, Bluetooth, or Wi-Fi client scanning;
no per-device identifiers. There is nothing on the device that can sense a person to begin with
(hard rule 1).

### Checklist

| # | Item | Gate | CI |
|---|------|------|----|
| C1 | Observation schema has no PII field and is frozen | **[auto]** | `make typecheck` + `make test` (schema tests) |
| C2 | Published coordinates are grid-snapped unless host opts into `precise` | **[auto]** | `make test` — `snap_to_grid` / `public_location` tests |
| C3 | Default node location is `coarse` (opt-in, not opt-out, for precise) | **[auto]** | `make test` — default-location test |
| C4 | No code path publishes raw `node.lat` / `node.lon` directly | **[auto]** | `make test` — all surfaces read `public_locations()` |
| C5 | Firmware carries no mic, camera, Bluetooth, or Wi-Fi client scan | **[review]** | Firmware review against hard rule 1 |
| C6 | DPIA re-read each release; residual risks current | **[review]** | [audits/privacy-dpia.md](audits/privacy-dpia.md) date |
| C7 | A PR adding any indirect identifier to the record is rejected | **[review]** | PR review / ADR |

---

## D. Transparency and explainability

**The principle: a value's trustworthiness is inspectable, not asserted.** A reader should be able
to trace why a number is what it is, and the dashboard should be candid about what it does not
know.

**A data card for the published surface.**

| Field | Value |
|-------|-------|
| What it is | Hourly, grid-aggregated heat and air-quality surface from a community sensor mesh |
| Parameters | temp_c (°C), humidity_pct (%), pm25_ugm3 (µg/m³), pm10_ugm3 (µg/m³), no2_ppb (ppb), heat_index_c (°C) |
| Spatial unit | ~150 m grid cells (deployer-configurable); never raw host coordinates by default |
| Temporal unit | Hourly rollups |
| Calibration | Per-node, per-parameter corrections; PM is humidity-aware (US-EPA PurpleAir lineage), temp/heat-index use an enclosure-offset; version id format `{parameter}.{method}.{node_id}` |
| Uncertainty | Each calibrated value carries `residual_std` as a 1-sigma error bar |
| AQI | US-EPA 2024 24h PM2.5 breakpoints; category travels with the cell |
| Provenance per value | node_id, calibration version (or `raw`), QC verdict (ok/range/spike/flatline/missing) |
| Known limitations | Low-cost sensors drift and read high in humidity; uncalibrated nodes shown provisional; a 150 m cell does not claim per-address resolution |
| Reproducibility | Re-running `swelter calibrate` on committed co-location data reproduces the registry byte-for-byte |
| License | Observations CC0-1.0; code Apache-2.0 |

**Every value carries its calibration state and uncertainty.** This is structural, not a UI
nicety: `calibration` is never empty (it is `raw` or a version id), and `uncertainty` is set when a
value is calibrated. Both travel through the SensorThings API (`resultQuality.uncertainty` and
`parameters.calibration` in `api.py`) and through the CSV/JSON export. A consumer cannot receive a
value without also receiving how much to trust it.

**The dashboard says what it does not know.** A cell with no calibrated, QC-clean value is labelled
provisional rather than shown as fact. A node offline for a stretch (node-07 in the demo is the
longest gap) produces a visible gap, not an interpolated guess. AQI categories are shown with their
confidence. The README's standing commitment — "the dashboard says what it does not know" — is
enforced by the provisional labelling, not left to copy.

### Checklist

| # | Item | Gate | CI |
|---|------|------|----|
| D1 | Calibration state (`raw` or version id) is present on every value | **[auto]** | `make test` — `calibration` never empty |
| D2 | Calibrated values carry a 1-sigma uncertainty through API and export | **[auto]** | `make test` — API/export carry `uncertainty` |
| D3 | QC verdict travels with every value | **[auto]** | `make test` — export/API include `qc` |
| D4 | Provisional cells are labelled, not defaulted to a clean reading | **[auto]** | `make test` — aggregate provisional marking |
| D5 | Calibration is reproducible byte-for-byte from committed data | **[auto]** | `make test` — calibration replay |
| D6 | The data card is current with the parameters, methods, and limitations | **[review]** | This section's "Last verified" date |
| D7 | Calibration method docs (`docs/calibration.md`) match the fitted models | **[review]** | Doc review against `calibrate.py` |

---

## E. Accessibility

**Summary; the full report is [audits/accessibility-report.md](audits/accessibility-report.md).**

**WCAG 2.2 AA is the floor, not the ceiling.** The residents most exposed to heat and bad air
include disabled people and elders; a tool that is not usable fails the people it is for.

**The structural gate.** `scripts/a11y_check.py` runs in `make a11y` (part of `make verify`) on
every PR and holds twelve structural checks with no browser: a page language, a single `<h1>`, a
skip link to an in-page id, labelled controls, `main`/`header` landmarks, image alt text, no
positive `tabindex`, an en/es language switch, `prefers-reduced-motion`, a visible focus indicator,
and — the load-bearing one — **a real data-table equivalent so the map is never the only way in.**
All twelve pass as of the verified date. The map, the sortable table, and the plain list are three
equal views of one aggregated surface; AQI severity is conveyed by text and pattern, never colour
alone.

**The manual review.** The script cannot judge computed colour contrast or live ARIA semantics
(e.g. the time slider's `aria-live` value announcements). Those are covered by a dated, attributed
manual pass (NVDA, VoiceOver, keyboard-only) recorded in the accessibility report. The structural
gate auto-blocks merge; the manual review is review-gated and committed.

**Table/list equivalents.** The same observations render as a sortable table and a plain list with
identical filtering, so a screen-reader user gets the full dataset without the map. Check 7 of the
structural gate fails the build if the table is removed.

### Checklist

| # | Item | Gate | CI |
|---|------|------|----|
| E1 | 12 structural WCAG 2.2 AA checks pass | **[auto]** | `make a11y` |
| E2 | A data-table equivalent to the map exists (map is never the only way in) | **[auto]** | `make a11y` — check 7 |
| E3 | No positive `tabindex`; skip link targets an in-page id | **[auto]** | `make a11y` — checks 5, 9 |
| E4 | en/es language switch present; `<html lang>` set | **[auto]** | `make a11y` — checks 1, 10 |
| E5 | CSS honours `prefers-reduced-motion` and shows a visible focus indicator | **[auto]** | `make a11y` — checks 11, 12 |
| E6 | Colour contrast (1.4.3/1.4.11) confirmed | **[review]** | Accessibility report manual pass |
| E7 | Screen-reader pass (NVDA/VoiceOver) incl. time-slider announcements | **[review]** | [audits/accessibility-report.md](audits/accessibility-report.md) |

---

## F. Security

**STRIDE sketch over the swelter trust boundaries.** Two boundaries matter: the public read path
(anyone → the dashboard/API) and the node write path (a sensor → ingest).

| STRIDE | Where it applies | Defence |
|--------|------------------|---------|
| **Spoofing** | A fake node submitting readings | Authenticated per-node write path; the public API has no write path to spoof |
| **Tampering** | Altering the published record | Observations are immutable and content-hashed (`content_hash`); the public surface is read-only (`server.py` returns 405 on POST/PUT/DELETE/PATCH); raw is append-only |
| **Repudiation** | Disputing what a value was | Every observation carries node, calibration version, and QC verdict; the archive is committed evidence |
| **Information disclosure** | Leaking a host's home | Node location grid-snapped by default (audit C); no PII exists to disclose |
| **Denial of service** | Flooding the single-threaded server | Read-only and stateless behind a static cache/CDN, scale-to-zero; no always-on component whose failure takes the data down |
| **Elevation of privilege** | Turning read access into write | No write path on the public surface; static file serving is path-confined to `web/` (`_static` resolves and bounds the target) |

**Read-only public API.** `server.py` answers `GET` only; `do_POST` and its aliases for PUT,
DELETE, and PATCH return `405 "swelter's public API is read-only"`. The SensorThings service
document advertises `readOnly: true`. The public surface cannot alter the record by construction.

**Authenticated per-node write path.** Ingest is the only way data enters, and it is the
authenticated boundary; the node↔ingest credential is separate from the public surface, which has
no write capability at all. Malformed payloads are quarantined (`quarantine.jsonl`) with a reason,
not ingested, so a bad or hostile payload cannot poison the record — it lands in quarantine for
review.

**Supply chain.**

- **Pinned dependencies.** One runtime dependency (PyYAML); everything else is the standard
  library. Dev tools and pre-commit hooks are pinned to exact revisions
  (`.pre-commit-config.yaml`); `uv.lock` pins the resolved set.
- **`pip-audit`** — known-vulnerability scan of the dependency set, in CI.
- **`gitleaks`** — secret scanning, both as a pre-commit hook and in CI, so a secret is caught
  before it reaches a branch.
- **CodeQL** — static analysis of the Python in CI.
- **Signed releases** — release artifacts are signed; SLSA-friendly pinned GitHub Actions.

### Checklist

| # | Item | Gate | CI |
|---|------|------|----|
| F1 | Public server returns 405 on POST/PUT/DELETE/PATCH | **[auto]** | `make test` — read-only server tests |
| F2 | Static serving is path-confined to `web/` (no traversal) | **[auto]** | `make test` — `_static` bound test |
| F3 | Malformed payloads are quarantined, not ingested | **[auto]** | `make test` — ingest quarantine tests |
| F4 | Observations are immutable and content-hashed | **[auto]** | `make test` — `content_hash` / frozen tests |
| F5 | Dependencies scanned for known vulnerabilities | **[auto]** | `pip-audit` workflow |
| F6 | No secrets committed | **[auto]** | `gitleaks` (pre-commit + CI) |
| F7 | Static analysis on the codebase | **[auto]** | CodeQL workflow |
| F8 | Dependencies and Actions pinned to exact versions | **[auto]** | `uv.lock` + pinned `.pre-commit-config.yaml`; bump review |
| F9 | Releases are signed | **[review]** | Signed-release workflow + release note |
| F10 | STRIDE re-read when a new trust boundary or field is added | **[review]** | Threat-model review / ADR |

---

## Coverage at a glance

| Audit | Auto-gated items | Review-gated items |
|-------|------------------|--------------------|
| A. Ethics and responsibility | A1–A4 | A5–A7 |
| B. Bias and fairness | B1–B2 | B3–B6 |
| C. Privacy and data protection | C1–C4 | C5–C7 |
| D. Transparency and explainability | D1–D5 | D6–D7 |
| E. Accessibility | E1–E5 | E6–E7 |
| F. Security | F1–F8 | F9–F10 |

Auto-gated items are re-proven by `make verify` or a CI workflow on every PR. Review-gated items
are satisfied by a committed, dated, attributed artifact and are re-read each release; see
[audits/methodology.md](audits/methodology.md).

---
Author: Chelsea Kelly-Reif, 2026. swelter is an independent personal open-source project,
unaffiliated with any employer or client; see NOTICE.
