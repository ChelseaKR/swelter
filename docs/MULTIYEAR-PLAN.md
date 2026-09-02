# swelter multiyear plan, 2026 to 2029

[`ROADMAP.md`](ROADMAP.md) records delivery state through Phase 5 and the completion loop for the
first release. [`RESEARCH-ROADMAP.md`](RESEARCH-ROADMAP.md) records a prioritised backlog assembled
from a synthetic persona panel and cited external research. Neither says what order the *next two
to three years* run in, or which of it is engineering and which is waiting on a person. This file
does, and only that; it introduces no new direction of its own.

Owner: Chelsea Kelly-Reif. Last verified: 2026-08-27. Recheck cadence: quarterly, at each release,
and whenever a phase gate opens or a blocker named here clears.

## How to read this

Every phase states three things and one more where it applies:

- **Delivers** — the outcome, not the activity.
- **Depends on** — what must be true first.
- **Done when** — an observable condition, not a feeling. Where a gate or an artifact can decide
  it, the gate is named.
- **Blocked on people** — where the work cannot be finished by engineering at all, because it needs
  a named human reviewer, an account the maintainer controls, or a real community partner.

Nothing here overrides a hard rule. The standing refusals in
[`README.md`](../README.md#non-negotiable-product-rules), [`CLAUDE.md`](../CLAUDE.md), and the
[ADR log](adr/README.md) bind every phase, and the "will not do" list at the foot of this file
restates the ones a plan is most likely to trip over.

## The through-line

swelter's value is a traceable path from measurement to claim. Everything below is one of four
kinds of work on that path, and the ordering follows from which link is weakest:

1. **The claim must be honest.** Where a published number is more confident than its evidence, fix
   that first. It is cheap, it is engineering-only, and every later phase inherits the discipline.
2. **The proof must be trustworthy.** The gates that certify honesty have to be capable of failing.
   A gate structurally unable to report a bad result is worse than no gate.
3. **The record must be released.** A reference implementation nobody can cite, install, or verify
   is a repository, not a project.
4. **The record must meet real people.** Everything after release is about residents, stewards,
   agencies, and partners — and most of it is gated on humans, not on code.

Phases 1 to 3 are the first three links. Phase 4 onward is the fourth, and it slows down, because
people are slower than compilers and this plan should say so rather than pretend otherwise.

---

## Phase 1 — Evidence quality travels with the count

**Status: built. Delivered by this change.**

**Delivers.** The two decision-facing artifacts that count danger — the resident/organizer exposure
brief and the institution-facing event chronicle — publish how much of each count rests on readings
the pipeline does not vouch for, instead of reporting a QC-flagged spike as a plain Danger day.
Closes [#199](https://github.com/ChelseaKR/swelter/issues/199); recorded in
[ADR 0046](adr/0046-a-danger-count-states-what-it-rests-on.md).

**Depends on.** Nothing. `qc_flags` and `provisional` already travel to the cell
([ADR 0029](adr/0029-event-aware-qc-visible-provisional.md)); only these two consumers ignored them.

**Done when.** `count_danger_days` and `CellChronicle` carry the provisional/QC-flagged split, it
renders in every place the count renders, `make verify` is green, and F-19 and F-22 in
[`ACCEPTANCE-TEST-MAP.md`](ACCEPTANCE-TEST-MAP.md) name tests that fail without it. **Met.**

---

## Phase 2 — The gates can fail

**Target: 2026 Q3 to Q4. Engineering-only except where noted.**

**Delivers.** Every merge gate is capable of reporting a bad result, and the release preflight can
actually run.

- Land the mutation-harness fix and the core-safety tests
  ([#200](https://github.com/ChelseaKR/swelter/pull/200),
  [#204](https://github.com/ChelseaKR/swelter/pull/204)). Until they merge, `main` still carries a
  mutation gate whose sandbox omits `scripts/`, so the calibrate cross-check dies at collection and
  mutmut scores a collection failure as zero killed rather than as a skip. The 80 percent floor in
  the `Makefile` stays where it is; the fix is to make the measurement real, never to lower the bar
  to meet a broken measurement.
- Commit the dated mutation baseline. `make mutation-baseline-check`, `make release-readiness`, and
  the `preflight` job of `release.yml` all read `docs/audits/mutation-baseline.json`, and that file
  does not exist in the repository. The release workflow's first job would fail on a missing
  artifact before it evaluated a single mutant. This cannot be produced until the harness fix
  lands: `[tool.mutmut]` on `main` has no `also_copy`, so the sandbox omits `scripts/`, the
  calibrate cross-check dies at collection, and any baseline generated today would record the
  structurally impossible 0.00 percent and fail its own 80 percent floor. Generating one from
  `main` would be committing a known-false number.
- Rebuild `web/sample-surface.json`, which drifts whenever the gate regenerates it because
  [#142](https://github.com/ChelseaKR/swelter/pull/142) changed heat-index uncertainty without
  rebuilding the fixture. **Done.** Regenerating with `swelter demo --web web` moves 11 of 1050
  cells, all `heat_index_c`, only `uncertainty` and `mean_member_sigma`, every value widening by
  1.48x to 1.75x. What remains open is the *guard*: nothing fails when the committed fixture and
  the pipeline disagree, which is why it drifted for five days unnoticed. A full replay costs 14.3
  seconds measured locally, so a comparison test is affordable; it was not added here because its
  byte-determinism across machines is unverified from one machine, and a flaky merge gate is worse
  than a stale fixture. Verifying that is its own task.
- Keep infrastructure failure separate from code failure in the DORA evidence run. **Already
  built**, and this plan initially overstated the gap: `scripts/dora_evidence.py` already partitions
  completed runs into `success`, `FAILED_CONCLUSIONS`, and `cancelled`, excludes cancellations from
  the change-failure denominator entirely, and reports `cancelled_runs` beside the rate. A run that
  concluded `cancelled` with zero steps — "job was not acquired by Runner of type hosted" — is
  therefore already not counted as a change failure. What is genuinely open is narrower: a
  cancellation caused by a runner never picking the job up is indistinguishable in the snapshot
  from one a human triggered, and neither is distinguishable from a job that died in two seconds on
  an Actions spending limit. That is a labelling improvement to an existing correct metric, not a
  missing metric.
- Extend the mutation-selected set beyond `calibrate`, `models`, and `qc` once the harness is
  trustworthy, starting with the surviving mutants in the correction-registry serialization and the
  OLS solver.

**Depends on.** Phase 1's discipline, and nothing else technical. The upstream standards-pin
authentication stays degraded until the maintainer mints `STANDARDS_PIN_TOKEN`
([#119](https://github.com/ChelseaKR/swelter/issues/119)) — the offline byte-integrity half of that
gate is blocking today and stays blocking, so this does not hold the phase up.

**Done when.** A scheduled mutation run reports a real score against the unchanged 80 percent floor
for four consecutive weeks; `docs/audits/mutation-baseline.json` is committed and
`mutation_report.py verify-baseline` passes against it; regenerating the web fixture is a no-op;
and the DORA snapshot distinguishes infrastructure cancellation from change failure, as
[`DORA.md`](DORA.md) already requires of the change-failure metric.

**Blocked on people.** `STANDARDS_PIN_TOKEN` is an account action only the maintainer can take.

---

## Phase 3 — v0.1.0

**Target: 2026 Q4 to 2027 Q1. Substantially blocked on people.**

**Delivers.** The first real tagged release, through the completion loop
[`ROADMAP.md`](ROADMAP.md) already specifies: verified merge candidate, annotated tag, rebuilt
artifacts with SBOM, provenance, signatures and consumer verification, deployed site, recorded
rollback readiness.

**Depends on.** Phase 2, plus four things engineering cannot supply:

- A named reviewer completing current NVDA, VoiceOver, keyboard-only, and reflow walkthroughs, and
  an independent Spanish translation and representational-harm review
  ([#106](https://github.com/ChelseaKR/swelter/issues/106)). No automated result substitutes.
- A PyPI trusted publisher and a protected GitHub release environment
  ([#108](https://github.com/ChelseaKR/swelter/issues/108)).
- The merge and Pages governance controls the July 2026 remediation deliberately excluded
  ([#105](https://github.com/ChelseaKR/swelter/issues/105)).
- A retained DORA baseline and a hosted performance baseline
  ([#109](https://github.com/ChelseaKR/swelter/issues/109)), the second of which needs a real
  deployment window rather than lab Lighthouse numbers relabelled as field evidence.

Engineering can still finish [#107](https://github.com/ChelseaKR/swelter/issues/107) — retiring or
narrowing the tracked static-analysis suppressions until the hygiene gate reports none — and that
is the one Phase 3 item with no human dependency.

**Done when.** `DEFINITION_OF_DONE.md`'s RELEASE-GATE is satisfied at the tagged commit, every item
either met or explicitly dispositioned, with no automated result standing in for a human review.

**Blocked on people.** Almost all of it: #105, #106, #108, and half of #109. This is the honest
reason a release date is not written here. The engineering was portfolio-complete before this plan
was drafted; the release is waiting on reviewers and account configuration, and calling that a
schedule slip would misdescribe it.

---

## Phase 4 — A dark source is visibly dark

**Target: 2027 Q1 to Q2. Engineering, with one posture decision.**

**Delivers.** The gap between what the README says the pipeline supports and what the deployed
routes actually serve is closed or stated, and closes permanently rather than by re-editing a
snapshot table.

- Establish why OpenAQ fails closed on every run with no publishable per-location license ledger
  ([#179](https://github.com/ChelseaKR/swelter/issues/179)). The guard is correct
  ([ADR 0024](adr/0024-preserve-source-specific-data-terms.md)); the question is whether OpenAQ
  still publishes per-location terms at all. The two honest outcomes are to map recoverable terms
  and keep failing closed, or to retire the OpenAQ route and stop describing it as available.
  Relaxing the ledger check to make the fetch pass is not one of them.
- Turn the per-run fallback annotation into a persistence signal. A single fallback is a supported
  outcome ([ADR 0034](adr/0034-a-refused-fetch-is-not-an-empty-area.md)); four days of them is an
  outage that reported success. [#180](https://github.com/ChelseaKR/swelter/issues/180) is closed
  by a visibility floor — each route now annotates the run when a fallback wins — and the changelog
  entry that closed it says so, naming the trend comparison across recent runs as still outstanding.
  That comparison is what distinguishes a transient outage from a persistent one, and it needs a
  fresh issue rather than reopening a closed one.
- Close the daily-refresh workflow branch that swallows an empty result, which ADR 0034 named as a
  separate gap outside its own scope. The issue it pointed at is closed, so this needs restating as
  a current one before it is worked.

**Depends on.** A run with a live API key against the OpenAQ v3 endpoints, which is an operator
action rather than an offline one.

**Done when.** Every published route's source matches its declared first choice, or a dated record
says why it does not and the deploy run says so at the time rather than in a README snapshot; and
the OpenAQ data card, the README source table, and the "what the deployed site actually shows"
section move together in one change.

---

## Phase 5 — The resident interpretation gap

**Target: 2027 Q2 to Q4. Engineering plus bilingual review capacity.**

**Delivers.** The step from a published number to something a resident can act on, in English and
Spanish, without swelter making a personal safety claim. This is the whole of
[`RESEARCH-ROADMAP.md`](RESEARCH-ROADMAP.md)'s "Now" band that remains unbuilt, plus the two
expansion items that sit directly on it:

- **R1** sourced, non-prescriptive per-category guidance, cited and bilingual.
- **R3** a Spanish in-page trust and calibration summary, so the why-trust-this story is not
  English-only chrome.
- **R5's outstanding half** — the caveats the data layer already carries reaching the legend, the
  marker, the alert headline, and the share artifact.
- **R9** a plain-language gloss of "uncertainty" and "provisional" at the point of use.
- **E7** a CDC HeatRisk-style guidance layer paired with AQI atop the existing compound surface.
- **E2** the deep trust panel: calibration version, uncertainty, QC verdict, and reference-monitor
  lineage as a first-class view rather than buried provenance.

**Depends on.** Phase 1's evidence-quality vocabulary, which is what R5 and E2 render; a settled
source posture from Phase 4, since guidance copy that names a source should name the right one; and
the reading-level and EN/ES parity gates that already exist.

**Done when.** Every guidance string has a public citation and an `es` counterpart, the parity and
reading-level gates pass, and a caveat present in the data is present in the rendered view — with
the correspondence proven by a test, not by inspection.

**Blocked on people.** Independent Spanish review of safety-adjacent copy is a human task
(#106 again), and adding more resident-facing guidance widens what needs reviewing. Advocacy
framing for the brief stays a human editorial decision by
[ADR 0018](adr/0018-exposure-brief-and-equity-context.md)'s own terms.

---

## Phase 6 — Calibration grows up

**Target: 2027 Q4 to 2028 Q3. Engineering, with one hard external dependency.**

**Delivers.** Calibration stops being a one-time fit and becomes an operated process. The ADR log
has been accumulating this list deliberately, each item deferred with a reason:

- The FIX-03 cluster that [ADR 0028](adr/0028-calibration-drift-surveillance.md) explicitly held
  back because each item touches what a value *is*: correction expiry and demotion to provisional,
  holdout and `n - p` fit statistics, a higher minimum publishable `n`, and the registry-schema
  bump those imply. ADR 0028 shipped drift *surveillance* only, and named a superseding ADR as the
  trigger for making drift enforce anything.
- More `(parameter, sensor_model)` calibration families beyond the three
  [ADR 0017](adr/0017-sensor-model-calibration-families.md) registered as a starting set.
- `window_end`, `n`, and `r2` as export and `resultQuality` columns, the additive half
  [ADR 0038](adr/0038-a-correction-version-that-names-its-fit.md) left for later.
- Extending [ADR 0041](adr/0041-a-derived-reading-is-only-as-real-as-its-inputs.md)'s input
  plausibility guard into `calibrate.apply`'s derivation path, named there as follow-up work rather
  than a silent inclusion.
- **E4**, the no-local-reference transfer-calibration path: a travelling reference unit, or chained
  co-location to a distant AQS site, with the weakened provenance recorded honestly. This is the
  single largest unlock for a community with no regulatory monitor nearby, and the research
  roadmap's own evidence says the nearest monitor averages about 19 km in urban areas.

**Depends on.** The reference-monitor adapter from
[ADR 0032](adr/0032-reference-monitor-adapter.md), which exists but whose live AirNow fetch is
deliberately unexercised by the test suite. Someone has to confirm the real endpoint, parameters,
and auth against the live service before E4 rests on it.

**Done when.** A correction can expire, and an expired one demotes its readings to provisional
without any value being rewritten; the calibration replay stays byte-for-byte reproducible from
committed co-location data throughout; and a network with no nearby reference can produce a
correction whose provenance says exactly how it was obtained.

**Blocked on people.** E4 needs a real reference relationship — a borrowed unit, or an agency
willing to host a co-location window. That is a relationship, not a ticket.

---

## Phase 7 — Scale that a collective can still own

**Target: 2028 Q1 to Q3. Engineering.**

**Delivers.** The store stops being a growth problem before it becomes one.
[ADR 0045](adr/0045-published-export-is-windowed-the-accumulating-store-is-not.md) windowed the
published export after `export.csv` reached 314 MB growing about 15 MB a day, and was explicit that
per-day shards, a columnar record shape, and omitting null keys were rejected *as the fix* because
none of them bound the count of readings published — they remain composable follow-ups. The
retention policy itself (FIX-09: rollups, retention windows, monthly archive files) was named out
of scope by [ADR 0013](adr/0013-accumulating-fetch-store-via-actions-cache.md), which said plainly
that a cache ceiling is not a retention policy.

Also here: an incremental publish path instead of a full re-aggregate, deferred by
[ADR 0020](adr/0020-static-publish-command.md) on the grounds that shipped networks are within
cost — which stops being true at some size, and this phase is where that is measured rather than
assumed.

**Depends on.** A network large enough for the question to be real. Until one exists, this phase is
speculative and should stay unbuilt; building retention for a hypothetical scale is how a project
acquires machinery nobody needs.

**Done when.** A multi-year store rebuilds, verifies, and publishes within the maintainer's
documented budget, with raw observations still immutable and every retained row still carrying its
source terms.

**Explicitly not in this phase.** A Parquet/Arrow `Store` backend. It is a declared seam and a
declared non-goal, and `docs/ARCHITECTURE.md` says no documentation should imply otherwise. It
becomes a candidate only when a real network outgrows a single-board host, and then it needs its
own ADR first.

---

## Phase 8 — Meeting the people it is for

**Target: 2028 onward. Almost entirely blocked on people.**

**Delivers.** The one thing no amount of engineering produces: evidence that this is useful to the
residents, stewards, and agencies it was built for.

- Field validation with a community partner — comprehension, actionability, governance, and
  maintenance burden, tested with people who would host or use the network. Until this happens,
  the personas in [`USER-RESEARCH.md`](USER-RESEARCH.md) are design inputs and nothing more, and no
  validated-demand or equal-comprehension claim may be made. `ROADMAP.md` already says this; it is
  restated here because it is the easiest sentence in the project to quietly drop.
- Accessible analytical depth validated with blind, low-vision, keyboard, cognitive-accessibility,
  and Spanish-speaking participants *before* more chart forms are added.
- Deployment hardening exercised by a real operator: backup and restore, source and license
  rollback, and a decision on whether a production ingest deployment needs a hardened edge.
- The remaining commons work that is genuinely optional until someone asks for it — **E10**
  cooling-center auto-ingest from open civic datasets, and the dashboard and API wiring for the
  canopy, AC-access, and redlining context layers, which
  [ADR 0023](adr/0023-context-layer-overlay.md) gated on a CBO and equity framing review precisely
  so context cannot read as an implied ranking.
- **E12** signed and staged firmware OTA, a declared 0.1.0 non-goal that `HARDWARE.md` describes as
  intended and not implemented. It needs its own ADR, real hardware, and a key-management posture
  before it is a plan item rather than a wish.

**Depends on.** Phases 3 and 5 — a partner should be handed a released, interpretable thing.

**Done when.** A dated partner-research artifact exists with a named participant group, and the
claims in `POSITIONING.md` that are currently phrased as hypotheses are either evidenced or
withdrawn.

**Blocked on people.** All of it. This is the phase where the project's limit is not the code.

---

## What this plan will not do

Restated so a future phase does not quietly propose one of them. Each has a reason recorded in the
ADR log or the roadmap's non-goals, and each needs a superseding ADR before it is reopened.

- No write path on the public server, and no subscriber list, contact detail, or person-shaped
  field anywhere (ADR 0005, ADR 0007, ADR 0010).
- No computed neighborhood score, rank, priority, vulnerability index, or grade — including any
  chronicle that weights, normalizes, or ranks cells (ADR 0023, ADR 0027, ADR 0028).
- No reading promoted past provisional without that node's own fitted correction. Cross-checked is
  a precision smoke alarm, never an accuracy tier (ADR 0017, ADR 0030).
- No absence published as a number, and no unknown value narrowing an interval (ADR 0036,
  ADR 0037, ADR 0041, ADR 0043).
- No forecast hour stored as an observation. A forecast product is a different product and needs
  its own ADR and its own field (ADR 0039).
- No regulatory, medical, individualized-safety, or emergency-notification claim; no block-scale
  accuracy claim for coarse model sources; no public exact host coordinates by default
  (`ROADMAP.md` non-goals).
- No shipped Parquet/Arrow backend, multi-writer cluster, mobile app, account system, or client
  analytics/RUM (`ROADMAP.md` non-goals).
- No claim of current manual assistive-technology or independent Spanish signoff until #106 has a
  dated reviewer artifact.

## Where the numbers live

This file states no metric values. The measurement ledger is in
[`ROADMAP.md`](ROADMAP.md#metrics-ledger), the deployment evidence in [`DORA.md`](DORA.md), and the
feature-to-test contract in [`ACCEPTANCE-TEST-MAP.md`](ACCEPTANCE-TEST-MAP.md). A phase is done when
those say so, not when this file does.
