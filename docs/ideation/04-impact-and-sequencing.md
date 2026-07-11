# Impact × effort and sequencing

Date: 2026-07-01. Covers FIX-01…FIX-13 ([`02-large-scale-fixes.md`](02-large-scale-fixes.md)) and
EXP-01…EXP-15 ([`03-expansions.md`](03-expansions.md)). "Impact" here means leverage on the
project's own stated goals — trustworthy readings, honest surfaces, community durability, equity
of access — not feature volume. This sequence is deliberately *beyond* (and interleaved with, not
replacing) `docs/ROADMAP.md` Phase 5 and the `docs/RESEARCH-ROADMAP.md` Now/Next/Later; where an
item should wait for an R/E item, that dependency is stated.

## Impact × effort matrix

Impact: ★★★ mission-critical / credibility-critical · ★★ strong · ★ real but narrower.

| Effort → / Impact ↓ | S | M | L | XL |
| --- | --- | --- | --- | --- |
| **★★★** | FIX-12 (docs-figures gate) | FIX-05 (export licensing) · FIX-04 (sound uncertainty) · FIX-10 (config doctor) | FIX-02 (event-aware QC) · FIX-03 (calibration lifecycle) · FIX-07 (dashboard tests/contract) | FIX-09 (store growth) |
| **★★** | EXP-08 (siting what-if) | FIX-08 (server survivability) · FIX-11 (observability) · FIX-13 (integrity chain) · FIX-06 (bilingual feeds) · EXP-04 (`swelter publish`) · EXP-05 (steward console) · EXP-10 (event chronicles) · EXP-01 (accumulating archive) | FIX-01 (authenticated ingest) · EXP-02 (reference feed) · EXP-13 (multi-hazard packs) | EXP-12 (indoor cohorts) · EXP-14 (federation) |
| **★** | EXP-11 (print cards) | EXP-03 (sensor-model families) · EXP-06 (WBGT) · EXP-07 (canopy overlay) · EXP-09 (twin tier) | EXP-15 (data-trust kit) | — |

Placement judgment calls, stated: FIX-05 is small code but ★★★ because it is a live licensing
error on the public demo; FIX-01 is ★★ not ★★★ because no real network is deployed yet — the
honest alternative (re-scope the docs) is S-effort and available immediately; EXP-01 is rated on
demo leverage, but it becomes ★★★ the day a real community instance exists; EXP-12/EXP-14/EXP-15
are transformative but gated (below), so their near-term "impact" is the design/ADR, not the
capability.

## Dependency notes

- **The schema-contract spine.** FIX-07's Python↔JS schema contract should land *before* the
  surface-shape changers (FIX-02, FIX-04, FIX-03's stale flag, EXP-06's new parameter), or each of
  those pays its own breakage tax. R11 (data dictionary) and FIX-07 should share one schema
  source of truth rather than growing two.
- **The calibration chain.** FIX-03 (lifecycle) → EXP-02 (reference feeds make re-calibration
  routine) → EXP-03 (per-model families) → EXP-09 (twin tier for the no-reference case, alongside
  research-roadmap E4). FIX-03's registry schema bump should happen once, carrying EXP-03's model
  field, not twice.
- **The scale chain.** FIX-08 (cache) is the quick relief; FIX-09 (rollups/retention) is the real
  fix and should follow FIX-04 so cells are rolled up in their final statistical shape; EXP-01
  (accumulation) needs FIX-09 to not eat the repo/CI and FIX-05 to be licensable; EXP-10
  (chronicles) needs EXP-01's history to be worth generating.
- **The static/ops chain.** EXP-04 (`publish`) subsumes part of FIX-08 for static deployments and
  is the delivery vehicle for EXP-11 (cards) and EXP-14's static federation builder; FIX-11
  (manifests) feeds EXP-05 (console) and EXP-10 (chronicle provenance); FIX-13 (digest chain)
  underwrites research-roadmap E3 (citable snapshots) and EXP-10's citability.
- **The language chain.** FIX-06 (server-side catalog) should follow, not precede,
  research-roadmap R1's guidance-string work — one catalog design, two consumers (dashboard,
  feeds) — and both feed EXP-11's print cards. All ES-visible items share the native-speaker
  review gate.
- **The write-path decision.** FIX-01 either lands or the README/audit language gets re-scoped;
  EXP-12 and any real hardware deployment depend on that decision being made, not deferred.

## Suggested sequence (beyond the existing roadmaps)

The research roadmap's "Now" (R1/R2/R3/R5/R9/E8) is resident-facing copy and is already the right
first sprint; this sequence is the *structural* track to run alongside and after it.

**Now — make the trust story true and unbreakable (mostly S/M, high credibility leverage).**
1. FIX-05 — the export/Pages licensing error is live on the public demo; fix first, it is the
   cheapest ★★★ in the folder.
2. FIX-12 — stop the docs drifting while everything else changes underneath them.
3. FIX-10 — the silent `alert_thresholds` typo failure is safety-relevant and small.
4. FIX-07 (start with the schema contract + pure-function tests) — the spine later work needs.
5. Decide FIX-01 (build vs re-scope the claim) as an ADR now, even if the build lands later.

**Next — make the numbers as honest as the labels, and survive real conditions.**
6. FIX-04 → FIX-02 (in that order: settle what a cell publishes, then who gets to appear in it).
7. FIX-03 + EXP-02 as one arc: corrections that age, and the reference plumbing that renews them.
8. FIX-08, then FIX-11 + FIX-13 (survivability, then evidence of operation and integrity).
9. EXP-04 (`publish`) — retire the untested workflow bash; unlock the static-first story.
10. FIX-06 — Spanish parity for the feeds, sequenced behind R1's catalog work.

**Later — grow the record, the operators, and the scope.**
11. FIX-09 → EXP-01 → EXP-10: the store that scales, the archive that accumulates, the chronicle
    that makes it citable.
12. EXP-05 + EXP-08: the steward's instruments.
13. EXP-03, EXP-06, EXP-09, EXP-07, EXP-11: audience and capability widening, each its own PR+ADR.
14. EXP-13 (hazard packs) once the heat core has survived a real season of the above.
15. EXP-14 / EXP-12 / EXP-15: pursue the *gate* (design ADR, governance review, legal review)
    before any build — see below.

## Items gated on humans, legal review, SMEs, or real data — defer and say so

Per the portfolio ethos: these are not "do later," they are "do not fake." Each names its gate and
what may proceed before the gate clears (usually: a design note or ADR, nothing user-facing).

| Item | Gate | What may proceed pre-gate |
| --- | --- | --- |
| FIX-01 (authenticated ingest) | Security review of the auth design; a real deployment to serve | ADR + threat-model sketch; or the honest doc re-scope |
| FIX-02 (QC thresholds/corroboration) | SME sanity check against low-cost-sensor QC literature; validation against at least one real recorded event (e.g. a Sensor.Community smoke day) | The provisional-not-absent display change (that half is pure honesty, no science risk) |
| FIX-03 / EXP-02 (fit statistics, reference pairing) | Statistical/atmospheric SME review of holdout design and resampling rules; AirNow API terms (real-data) | Correction-age plumbing and stale flags |
| FIX-06 / EXP-11 / all ES-visible copy | Native-Spanish reviewer (the open role the i18n migration memo names); R1's public-health wording partner for guidance text | Catalog structure, EN artifacts, parity gates |
| EXP-01 (accumulating archive) | Source terms-of-use review for retention/republication (OpenAQ CC BY, Sensor.Community CC BY-SA, Open-Meteo/CAMS) | The `--accumulate` flag against the synthetic demo store |
| EXP-06 (WBGT guidance bands) | Occupational-health SME on guidance copy; estimation-method citation review | The estimated parameter itself, clearly caveated, without action guidance |
| EXP-07 (canopy overlay) | CBO/equity partner on framing (context vs implied ranking); dataset license | The allowlist overlay module, with a fixture dataset, unshipped |
| EXP-09 (twin tier) | SME on naming/semantics so "cross-checked" cannot read as accuracy | The paired-agreement statistic in health reports, unlabeled |
| EXP-10 (event chronicles) | Public-health partner wording review before institutional use (same gate as R1) | The generator against synthetic data, marked draft |
| EXP-12 (indoor cohorts) | Hard-rules/privacy governance review **first** (D3-persona scrutiny); possible outcome is a reasoned "no" ADR | Nothing user-facing; only the DPIA-extension analysis |
| EXP-14 (federation) | ≥2 real instances existing; directory-governance decision | The `federation.yaml` format + two-fetch static demo |
| EXP-15 (data-trust kit) | Pro-bono legal review before anything is labeled usable | Plain-language drafts marked "unreviewed template — not legal advice" |
| Everything resident-facing | The research roadmap's standing caveat applies here too: demand is unverified; validate with real residents/hosts/officials before building past the cheap version | — |

## Closing honesty note

This folder was produced by one deep code-reading pass on 2026-07-01. It is good at finding
structural gaps that are visible in source (licensing plumbing, statistical shortcuts,
docs-vs-code drift) and bad at knowing which capabilities any real community will adopt — the
same asymmetry `docs/RESEARCH-ROADMAP.md` declares for its method. Treat the fixes as
higher-confidence than the expansions: most fixes correct something observably untrue or fragile
today; every expansion is a hypothesis until a real steward, resident, or partner reacts to it.
