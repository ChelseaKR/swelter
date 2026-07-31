# swelter roadmap

The product goal is a community-owned measurement-to-action record: residents can see current heat
and air conditions, investigate change and uneven exposure, inspect evidence, and take the data with
them without surrendering control to an account or vendor.

Owner: Chelsea Kelly-Reif. Last verified: 2026-07-18. Recheck cadence: monthly, each release, and
after partner research or a material incident. The [root README](../README.md) describes the current
product; this file records delivery state, next decisions, and measurable success.

## Current state

The reference implementation now includes:

- deterministic demo and fetched-source intake through one QC/calibration/aggregation model;
- immutable raw observations in a copyable SQLite store, quarantine, integrity verification, and
  versioned calibration evidence;
- an authenticated node write listener separate from the public GET-only server;
- source adapters for OpenAQ, CAMS/Open-Meteo, and Sensor.Community with source-specific licensing;
- compound exposure, alerts, context/action layers, static publication, citable snapshots, and an
  OGC SensorThings subset;
- bilingual Current reading and Readings views with linked history, distribution, evidence, map, table,
  list, and export paths;
- automated quality/accessibility/language/security/release gates and dated responsible-technology,
  operational, DORA, standards-pin, and source-data evidence.

The committed calibration fixture contains **300 corrections across the 100 co-located nodes** at
the 150-node default size. This count is not hand-maintained: `scripts/docs_figures_check.py`
recomputes it from `data/demo/corrections.yaml` and fails if the sentence drifts.

The implementation is portfolio-complete enough for a first real `v0.1.0` release, subject to the
release checklist and honest treatment of the open items below. Package metadata alone is not a
release; the annotated tag and published artifacts must exist before release claims change.

## Shipped feature inventory

These stable IDs are the roadmap side of the executable one-to-one contract in
[`ACCEPTANCE-TEST-MAP.md`](ACCEPTANCE-TEST-MAP.md). A shipped feature is added, renamed, or removed in
both tables and with its referenced tests in the same change.

| Feature ID | Shipped roadmap outcome |
| --- | --- |
| F-01 | Phase 1: ingest and quarantine |
| F-02 | Phase 1: QC and node health |
| F-03 | Phase 1: portable export |
| F-04 | Phase 2: calibration |
| F-05 | Phase 2: derived heat and exposure |
| F-06 | Phase 3: read-only API |
| F-07 | Phase 3: exposure observatory |
| F-08 | Phase 3: accessible alternatives |
| F-09 | Phase 3: bilingual resident UI |
| F-10 | Phase 4: register a network |
| F-11 | Authenticated node write path |
| F-12 | Firmware buffering |
| F-13 | Live OpenAQ adapter |
| F-14 | Live CAMS/Open-Meteo adapter |
| F-15 | Live Sensor.Community adapter |
| F-16 | Static publication |
| F-17 | Citable data snapshot |
| F-18 | Public alerts and personal watches |
| F-19 | Context and equity brief |
| F-20 | Archive verification |
| F-21 | Release |
| F-22 | Event chronicle generator |
| F-23 | Calibration-drift surveillance in the health report |
| F-24 | Event-aware QC keeps suspicious readings visible, provisional, and flagged |
| F-25 | Sensor-twin cross-checked precision tier |
| F-26 | EXP-13: multi-hazard packs and a cold pack |
| F-27 | Reference-monitor co-location adapter |

## Delivery history

### Phase 1 — trustworthy local pipeline: complete

Turn recorded payloads into idempotent, QC-labelled, exportable observations with malformed input
quarantined. The shipped backend is SQLite plus generated files; raw observations are immutable and
rebuild inputs remain portable.

### Phase 2 — calibration evidence: complete

Fit per-node corrections from recorded co-location windows; publish method, reference, fit window,
uncertainty, and version. Raw and calibrated observations remain distinguishable at every layer.
Sensor-twin agreement adds a "cross-checked" precision verdict — a drift smoke-alarm bounding
precision, never accuracy — that stays QC/health metadata and never promotes a reading to calibrated
(F-25, [ADR 0030](adr/0030-sensor-twin-crosschecked-tier.md)).

### Phase 3 — public observatory and interfaces: complete

Publish equivalent map/table/list outcomes, read-only SensorThings/CSV/JSON, English/Spanish UI, and
installable static delivery. The current interface links Current reading and Readings with history,
location distribution, and persistent evidence inspection.

### Phase 4 — community portability: complete as a reference implementation

Another collective can copy and validate `network.yaml`, preview privacy-snapped locations, ingest
its nodes, and publish without a hosted swelter account. Real hardware deployment, local governance,
and calibration still require a named community steward; the project does not claim one-afternoon
physical deployment.

### Phase 5 — evidence and action: complete for the reference surface

Compound heat/air exposure, threshold alerts, contextual canopy/AC-access/redlining views, cooling-
center support, caveat-preserving share artifacts, citable snapshots, archive integrity, data
dictionary/crosswalk, and source-license provenance are implemented. Context remains descriptive,
never a person-level vulnerability score or individualized safety direction.

## Recommended completion loop

### 1. Release candidate

- Keep `make verify`, `make web-test`, browser checks, and workflow checks green on the exact merge
  candidate.
- Close or explicitly disposition every `DEFINITION_OF_DONE.md` item and PR-template attestation.
- Regenerate demo/publication evidence and verify source truth, license ledger, manifests, and hashes.
- Complete current NVDA, VoiceOver, keyboard/reflow, and independent Spanish review, or keep the gap
  visibly open in [issue #106](https://github.com/ChelseaKR/swelter/issues/106) and avoid a fresh human-
  conformance claim.
- Confirm `pyproject.toml`, `CITATION.cff`, and the dated changelog section match `0.1.0`.

### 2. Review and merge

- Review the acceptance-test map, threat model, DPIA, source cards, data-flow inventory, and residual
  risks against the actual diff.
- Require independent review where the template says REVIEW; an automated job cannot self-attest.
- Merge only after all required checks for the branch are green. The repository/Pages enforcement
  exception intentionally excluded from this remediation is tracked in
  [issue #105](https://github.com/ChelseaKR/swelter/issues/105).

### 3. Tag, publish, and verify

- Create the annotated `v0.1.0` tag from the verified merge commit.
- Let the release workflow rebuild from that tag, generate SBOM/provenance/signatures/checksums, and
  run consumer verification before publication.
- Deploy the static site from the verified source/license artifact; smoke-test Current reading, Readings,
  table/list, language, export, freshness, and source attribution paths.
- Record release/deploy evidence and rollback readiness. If a verification fails, stop publication or
  roll back using [`runbooks/operations.md`](runbooks/operations.md).

### 4. Observe and learn

- Update [`DORA.md`](DORA.md) from Actions after the release window.
- Triage incidents and source/license/freshness failures; retire suppressions under
  [issue #107](https://github.com/ChelseaKR/swelter/issues/107).
- Conduct real partner research before making validated-demand or equal-comprehension claims. Current
  personas and synthetic research are design inputs, not partner validation.

## Metrics ledger

The schema is fixed by the portfolio standard: **Metric, Target, Measured by, Gate, Owner**. Targets
describe the desired outcome; passing a proxy is not relabelled as the outcome itself.

| Metric | Target | Measured by | Gate | Owner |
|---|---|---|---|---|
| Raw/calibrated integrity | No path overwrites raw data or presents an uncorrected value as calibrated | Store invariants, rebuild/aggregate/API/export/UI tests, archive verification | AUTO | Maintainer |
| Calibration reproducibility | Same committed co-location inputs and version produce byte-identical registry output | Calibration replay and registry round-trip tests | AUTO | Data steward |
| Calibration accuracy evidence | Every calibrated family publishes held evidence, residual uncertainty, reference, and fit window; no unevidenced accuracy claim | Correction registry, calibration tests, data card/reviewer check | AUTO + REVIEW | Data steward |
| Source-license integrity | Every published source has accurate terms/attribution; OpenAQ never publishes without a valid per-location ledger | Source truth/license/manifest tests plus data-card review | AUTO + REVIEW + RELEASE | Data steward |
| Jurisdiction and provenance | Public counts/surfaces match the named source and geographic scope | Boundary/source adapter tests, generated source artifact, publish smoke | AUTO + RELEASE | Data steward |
| Accessibility automation | Structural and browser checks pass; map outcomes remain available in semantic table/list paths | `make a11y`, web tests, real-browser accessibility job | AUTO | Maintainer |
| Accessibility human outcome | A keyboard, NVDA, and VoiceOver user can complete Current reading/Readings/filter/evidence/export tasks without the visual map | Dated named review artifact and ACR update | REVIEW + RELEASE | Accessibility reviewer |
| Spanish completeness | Every English UI key has a Spanish value with valid encoding/tagging | i18n parity, UTF-8, BCP-47, CLDR gates | AUTO | Maintainer |
| Spanish clarity | Independent reviewer finds critical safety/source/caveat copy accurate and understandable | Dated bilingual review artifact | REVIEW + RELEASE | Language reviewer |
| Privacy/location | No person-shaped field or logged secret; coarse publication remains default; raw browser geolocation is not retained | Schema/log-safety/location tests, DPIA/threat review | AUTO + REVIEW | Privacy owner |
| Branch coverage | At least the configured 90% branch floor with no test-count target | Coverage-gated Python suite | AUTO | Maintainer |
| Web interaction contract | Linked views, state, caveats, keyboard behavior, and static/live schema stay compatible | `make web-test` and browser smoke | AUTO | Maintainer |
| Static freshness | Page names source and generated time; stale/failed source does not masquerade as current | Publish/source-truth tests and post-deploy smoke | AUTO + RELEASE | Operations owner |
| Deployment frequency | Track successful push- and scheduled Pages deployments without prescribing vanity volume | Actions query in `DORA.md` | REVIEW | Operations owner |
| Lead time for changes | Track push-to-successful-deploy P50/P90 and investigate sustained regression | Actions query in `DORA.md` | REVIEW | Operations owner |
| Change failure rate | No failed completed deployment is ignored; cancellation is reported separately | Actions conclusions plus incident issues in `DORA.md` | REVIEW | Operations owner |
| Recovery readiness | Publication can be disabled or rolled back with source/license/location integrity preserved | Runbook exercise or incident record | RELEASE | Operations owner |
| Operational cost | Reference static deployment stays within the maintainer's documented budget and has no required paid swelter service | Provider billing review and architecture review | REVIEW | Operations owner |

The fail-closed DORA window, retained query metadata, and input digest are in
[`DORA.md`](DORA.md). Metric values belong there rather than being copied into this roadmap; no tier
is claimed until complete row-level evidence is committed.

## Observability

**Tier declaration: Tier C — library and operator-run CLI.** The portfolio standard names
`swelter` in Tier C. Its optional read-only HTTP server is started and owned by the local operator;
the project does not operate a long-lived API service. The public Pages observatory is a static,
account-free build artifact with no project-run browser telemetry collector or runtime backend.

- OTel traces, metrics, a collector stack, RED/USE metrics, SLOs, burn-rate alerts, and
  `/livez`/`/readyz` are **N/A — no project-operated network service exists**. A future hosted API
  changes the tier and must add those controls before deployment.
- Browser OTel and field Core Web Vitals RUM are **N/A — the static civic site deliberately sends
  no client telemetry**. Same-origin static fetches do not cross into a project-operated backend.
  Lighthouse lab measurements remain an AUTO quality regression gate; they are not relabelled as
  field evidence.
- Opt-in `swelter --log-format json` is the Tier-C signal, rendered by the exactly locked structlog
  JSON processor. Human-readable output remains the default. The JSON shape, redaction behavior,
  and no-PII/no-secret static scan are AUTO gates.

| Metric | Target | Measured by | Gate | Owner |
|---|---|---|---|---|
| Tier-C JSON log validity | Every opted-in line parses and carries the documented service, severity, timestamp, trace placeholders, stage, and message fields | CLI/log formatter tests | AUTO | Maintainer |
| Log data safety | Zero secret- or person-shaped fields/literals cross production log calls | `scripts/log_safety_check.py`, scrubber tests, Semgrep | AUTO | Privacy owner |
| Static frontend lab LCP | Under 2.5 seconds on `/` and `/sensors/` | Lighthouse CI and committed route baseline | AUTO | Maintainer |
| Static frontend lab INP proxy | Total blocking time under 200 ms; INP remains field-only and is not inferred | Lighthouse CI and committed route baseline | AUTO | Maintainer |
| Static frontend lab CLS | Under 0.1 on both routes | Lighthouse CI and committed route baseline | AUTO | Maintainer |
| Field RUM / browser traces | N/A — no client telemetry collector or hosted runtime API | Architecture/privacy review | REVIEW | Privacy owner |

## Next validated bets

These are hypotheses, not promises. Each requires a problem statement, partner evidence, acceptance
criteria, test/review mapping, and an ADR when it changes architecture.

1. **Field validation with a community partner.** Test comprehension, actionability, governance, and
   maintenance burden with people who would host/use the network.
2. **Calibration operations.** Add steward-facing drift review, scheduled re-co-location evidence, and
   explicit promotion/retirement decisions for corrections.
3. **Source resilience.** Measure and improve provider-outage behavior, stale-state communication,
   retry budgets, and reproducible license/attribution changes.
4. **Accessible analytical depth.** Validate the history/distribution/evidence workspace with blind,
   low-vision, keyboard, cognitive-accessibility, and Spanish-speaking participants before adding more
   chart forms.
5. **Deployment hardening.** Exercise backup/restore and source/license rollback for a real operator;
   decide whether a production ingest deployment needs a hardened edge/proxy reference.
6. **Governance closure.** Resolve issue #105 when the maintainer authorizes the excluded live GitHub
   settings/environment changes.

## Explicit non-goals for 0.1.0

- Regulatory, medical, individualized safety, or emergency-notification certification.
- A claim of block-scale accuracy for coarse model/reanalysis sources.
- Automatic promotion of low-cost readings without reference calibration.
- Public exact sensor-host coordinates by default.
- Signed/staged firmware OTA; it remains a documented future capability.
- A shipped Parquet/Arrow backend, multi-writer cluster, mobile app, user account system, or client
  analytics/RUM.
- A claim of current manual assistive-technology or independent Spanish signoff until issue #106 has a
  dated reviewer artifact.
