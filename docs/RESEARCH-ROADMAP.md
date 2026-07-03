# Research roadmap — synthetic panel + cited evidence

> [!NOTE]
> **Framing.** This roadmap is built from two inputs: the **synthetic persona
> panel** in [`USER-RESEARCH.md`](USER-RESEARCH.md) (LLM personas exercising the
> real product — *not* real interviews, *not* evidence of demand) and **cited
> external research** (real sources, URLs accessed 2026-06-30, in the evidence
> section below). It **complements** the existing phased plan in
> [`ROADMAP.md`](ROADMAP.md) — it does **not** replace it. Phases 1–4 are built and
> green; Phase 5 ("differentiate and sustain") names the forward direction. Every
> item here is tagged **[corroborates …]** where it independently re-discovers a
> Phase 5 item or an audit finding, or **[NET-NEW]** where the panel surfaced it
> fresh. Nothing here changes a hard rule; each item is meant to land as its own PR
> with its own tests and ADR, inside the existing calibration, privacy, openness,
> and accessibility discipline.
>
> **Last assembled: 2026-06-30.** Effort scale: **S** ≈ an afternoon · **M** ≈ a day
> or two · **L** ≈ a week+. Priority: **P0** now · **P1** next · **P2** soon ·
> **P3** opportunistic.

---

## Research basis / evidence

The findings below are external and citable; they set the *stakes* the backlog is
prioritised against. High-stakes claims (mortality ranking, calibration validity,
monitoring inequity, compound risk) are cross-checked against ≥2 sources. Short
**keys** in bold are referenced by the backlog tables.

- **[heat-deadliest]** Extreme heat is the **deadliest US weather hazard** — more
  annual deaths than floods, tornadoes, hurricanes, or lightning; the CDC counted
  **2,394 heat-related deaths in 2024** (2,415 in 2023), themselves believed to be
  undercounts.
  [FoxWeather](https://www.foxweather.com/extreme-weather/heat-deadliest-weather-united-states) ·
  [APHA](https://www.apha.org/publications/public-health-newswire/public-health-newswire/articles/extreme-heat-kills-more-people-than-any-other-extreme-weather-event) ·
  [USAFacts/CDC+NOAA](https://usafacts.org/articles/how-many-people-die-from-extreme-heat-in-the-us/) ·
  [Washington Post (undercount)](https://www.washingtonpost.com/climate-environment/2024/07/01/extreme-heat-deaths-heatwave-heatstroke/)
- **[ej-distribution]** The burden lands unequally: formerly **redlined**
  neighborhoods run hotter today (mean ~2.6 °C, up to ~7 °C, across 94% of 108 US
  areas — Hoffman et al. 2020,
  [Virginia Mercury](https://virginiamercury.com/briefs/there-may-be-a-link-between-urban-heat-islands-and-past-redlining-practices-study-finds/) ·
  [PBS](https://www.pbs.org/wnet/peril-and-promise/2020/01/redlined-neighborhoods/));
  low-income / majority-POC blocks carry ~26% / ~38% **less tree canopy**
  ([American Forests](https://www.americanforests.org/article/the-need-for-tree-equity-is-heating-up/) ·
  [PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC8081227/)); indoor heat deaths
  cluster among isolated, low-income **elders** — Maricopa 2019: 91% who died indoors
  had AC that was off/too-high/broken
  ([Fortune](https://fortune.com/2024/08/02/heatwave-deaths-expose-air-conditioning-crisis-elderly-and-minorities-most-at-risk/) ·
  [CAP](https://www.americanprogress.org/article/protecting-older-adults-from-the-growing-threats-of-extreme-heat/)).
- **[monitoring-gap]** The official record is **sparse and inequitably placed**:
  nearest regulatory PM2.5 monitor averages ~18.8 km (urban); under the 2024
  standard ~44% of exceeding urban areas (~20M people) go undetected; low-cost
  sensors skew to higher-income, whiter areas.
  [ACS ES&T Letters](https://pubs.acs.org/doi/10.1021/acs.estlett.4c00605) ·
  [ACS press](https://www.acs.org/pressroom/presspacs/2024/october/us-air-pollution-monitoring-network-has-gaps-in-coverage-say-researchers.html) ·
  [Monitor equity](https://pmc.ncbi.nlm.nih.gov/articles/PMC12329718/) ·
  [Sensor placement & injustice](https://pmc.ncbi.nlm.nih.gov/articles/PMC10499371/)
- **[calibration]** Low-cost sensors are credible **only after calibration**: the
  US-EPA PurpleAir correction with a humidity term cuts PM2.5 **RMSE ~8 → ~3
  µg/m³** (Barkjohn et al. 2021); EPA applies it on the AirNow Fire & Smoke Map;
  corrected data remains a **non-regulatory** tier.
  [AMT 14:4617](https://amt.copernicus.org/articles/14/4617/2021/) ·
  [EPA/PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC8422884/) ·
  [AirNow technical approach](https://www.epa.gov/air-sensor-toolbox/technical-approaches-sensor-data-airnow-fire-and-smoke-map) ·
  [EPA non-regulatory QA](https://www.epa.gov/air-sensor-toolbox/quality-assurance-air-sensors)
- **[drift]** Sensors **drift**; long-term deployments need periodic re-evaluation/
  re-co-location, and unmaintained networks suffer data discontinuity.
  [Long-term eval](https://www.sciencedirect.com/science/article/pii/S0048969721058757) ·
  [NYC mesonet network calibration](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12797186/) ·
  [Community-network discontinuity](https://www.nature.com/articles/s41612-025-01216-4)
- **[standards]** The dashboard must speak to current standards: **WHO 2021** PM2.5
  guideline (5 µg/m³ annual / 15 µg/m³ 24-h) and **EPA 2024** PM2.5 NAAQS lowered to
  **9.0 µg/m³** with a revised AQI.
  [WHO 2021 (IQAir)](https://www.iqair.com/us/newsroom/2021-who-air-quality-guidelines) ·
  [WHO review](https://pmc.ncbi.nlm.nih.gov/articles/PMC8553929/) ·
  [EPA 2024 NAAQS](https://www.epa.gov/pm-pollution/final-reconsideration-national-ambient-air-quality-standards-particulate-matter-pm) ·
  [EPA overview PDF](https://www.epa.gov/system/files/documents/2024-02/pm-naaqs-overview.pdf)
- **[compound]** **Compound** heat + PM2.5 exposure is ~3× deadlier than either
  alone (Rahman et al. 2022); CDC pairs HeatRisk with the AQI.
  [AJRCCM](https://www.atsjournals.org/doi/10.1164/rccm.202204-0657OC) ·
  [USC/Keck](https://keck.usc.edu/news/risk-of-death-surges-when-extreme-heat-and-air-pollution-coincide/) ·
  [WRI](https://www.wri.org/insights/extreme-heat-air-pollution) ·
  [CDC HeatRisk + AQI](https://www.cdc.gov/heat-health/hcp/clinical-guidance/how-to-use-the-heatrisk-tool-and-air-quality-index.html)
- **[trust]** EPA-convened experts tie sensor-data **uncertainty** to public
  distrust; publishing uncertainty + QC flags is the documented antidote.
  [ACS ES&T Air](https://pubs.acs.org/doi/10.1021/acsestair.4c00125)
- **[reuse]** Researchers/journalists hold low-cost data back for missing
  calibration, QA, and **FAIR** provenance; newsrooms have built their own analyses
  because official data couldn't answer the question.
  [QA for credible data](https://pmc.ncbi.nlm.nih.gov/articles/PMC11534011/) ·
  [Make data FAIR](https://www.openaire.eu/how-to-make-your-data-fair) ·
  [ProPublica](https://www.propublica.org/article/whats-polluting-the-air-not-even-the-epa-can-say)
- **[commons]** Comparable networks: **OpenAQ** models FAIR open aggregation;
  **Imperial County / IVAN** shows community ownership is the survival factor;
  **Array of Things** shows vendor-run nets wind down when cost/maintenance aren't
  owned locally.
  [OpenAQ](https://openaq.org/about/) ·
  [IVAN](https://ivan-imperial.org/about) ·
  [Imperial durability](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC7037815/) ·
  [Array of Things wind-down](https://www.technologyreview.com/2022/08/19/1057848/array-of-things-goes-global/) ·
  [Chicago Sun-Times](https://chicago.suntimes.com/environment/2025/09/11/chicago-air-pollution-monitor-sensors-public-health-environmental-justice)
- **[a11y]** Accessible data viz requires a screen-reader **data-table equivalent**
  for every non-trivial chart, never colour alone, plus a plain-text summary.
  [USWDS](https://designsystem.digital.gov/components/data-visualizations/) ·
  [TPGi](https://www.tpgi.com/making-data-visualizations-accessible/)
- **[language]** **Language access** for LEP residents is a health-equity and
  civil-rights obligation (EO 13166, Title VI), sharpest in climate emergencies; the
  **DOJ 2024 ADA Title II** rule makes WCAG 2.1 AA load-bearing for public agencies.
  [EPA LEP](https://www.epa.gov/lep) ·
  [Just Solutions](https://justsolutionscollective.org/language-justice-in-climate-disasters-state-models-addressing-title-vi-gaps/) ·
  [SEHN](https://www.sehn.org/sehn/2024/7/22/let-me-say-my-word-let-me-understand-yours-language-access-and-translation-for-socio-environmental-justice)

**Volatile / flagged.** Heat-death counts and the federal-funding landscape shift
year to year (see `POSITIONING.md` recheck cadence); the Hoffman 2020 magnitudes
and the Barkjohn RMSE figures are stable and widely replicated; the "no competitor
does X" claims should stay phrased as "we did not find one" (`POSITIONING.md`).

---

## How this maps to the existing roadmap

[`ROADMAP.md`](ROADMAP.md) Phase 5 (proposed) names five leverage points. This panel
re-discovers four of them and adds detail; the cross-references below let a reader
see what is corroboration vs net-new.

| Phase 5 item (existing) | Status | This roadmap sharpens it with |
| --- | --- | --- |
| 5.1 Compound heat-and-air exposure surface | **built** (ADR 0009) | E7 (HeatRisk-style guidance layer atop it) |
| 5.2 Make the trust layer visible | proposed | E2, E3, R5, R9 |
| 5.3 Register-your-own-network as headline | proposed | E4, E6, E8 |
| 5.4 Accessibility + bilingual as a certifiable asset | proposed | E9, R2, R8 |
| 5.5 Close the data-to-action gap (plain-language brief) | proposed | R1, E1, E7 |

---

## Remediation backlog (close honest gaps in what exists)

| ID | Item | Personas | Pri | Effort | Evidence · tag |
| --- | --- | --- | --- | --- | --- |
| R1 | **Sourced, non-prescriptive per-category guidance** in the dashboard ("Heat is Danger today — older adults should limit time outside, per CDC/NWS") — context **with a citation**, **never** a personal safety claim; **en + es** together | A1, A2, A3, C1 | P0 | M | **[heat-deadliest][compound][standards]** · **[corroborates ROADMAP 5.5 + audit A6]** |
| R2 | **Bilingual-by-gate** for resident-facing guidance strings — a check that fails CI if a guidance key exists in `en` but not `es` (or vice versa). ✅ Implemented 2026-06-30 (working tree, uncommitted) — `tests/test_i18n.py` enforces G6 key-parity + G5 placeholder parity + referenced-key resolution | A3, B4 | P0 | S | **[language]** · **[corroborates governance §6 + INTERNATIONALIZATION-STANDARD]** |
| R3 | **Spanish in-page trust/calibration summary** ("cómo leer esto / qué es el ICA") so the *why-trust-this* story is bilingual, not just chrome | A3 | P1 | S | **[language][trust]** · **[NET-NEW vs ROADMAP]** |
| R4 | **Heat-index trustworthiness** — let a network co-locate/calibrate heat index, **or** derive it from already-calibrated temp + humidity, so heat stops being demo-provisional where the inputs are confirmed; keep it honestly provisional where they aren't. ✅ Implemented 2026-07-03 (`roadmap/r4-heat-index-trustworthiness-calibrate-`) — `calibrate.apply()` derives a calibrated `heat_index_c` (version `heat_index_c.derived-enclosure.{node_id}`) from a node's calibrated `temp_c` + co-timed humidity via `models.heat_index_c`, propagating the temp correction's `residual_std` as uncertainty; stays raw/provisional wherever temp is raw or humidity is missing; adds no entry to `corrections.yaml` (still byte-for-byte reproducible) — see ADR 0012 and `calibration.md`'s "Heat index: derived, not fitted" | C2, A1, A2, E2 | P1 | M | **[heat-deadliest]** + `calibration.md` · **[NET-NEW vs ROADMAP]** |
| R5 | **Caveats travel with the value** — propagate the hourly-vs-24-h AQI window note and the provisional flag into every legend, marker, alert headline, and export, not just `api.md` | D2, C1, E2 | P1 | M | **[standards][trust]** · **[corroborates audit D + api.md]** |
| R6 | **Coverage-equity surfaced** in `swelter qc` / `/api/health.json` — calibrated vs raw node counts per block, flagging when the provisional tier concentrates on frontline cells. ✅ Implemented 2026-06-30 (working tree, uncommitted) — `qc.coverage_equity` (descriptive calibrated-vs-raw per cell + `coverage_gap` flag) surfaced in `swelter qc` and `/api/health.json`; the frontline-correlation half of B4 is deferred (needs external demographic context swelter does not hold + governance sign-off) | B2, F1 | P1 | M | **[monitoring-gap][ej-distribution]** · **[corroborates audit B3/B4]** |
| R7 | **Host-facing "what's public about your node" preview** — show a host exactly the grid-snapped coordinate the map/API publishes, so coarse-by-default is *visible* | B1 | P2 | S | privacy/DPIA · **[NET-NEW]** |
| R8 | **Manual a11y pass as a first-class artifact** — surface the dated NVDA/VoiceOver/contrast review and a "known a11y gaps" note alongside the auto gate | D1, A5 | P2 | S | **[a11y]** · **[corroborates audit E6/E7]** |
| R9 | **Point-of-use gloss of "uncertainty" and "provisional"** — one screen-reader-friendly line each, so the honesty is legible to non-experts | A5, A1 | P1 | S | **[trust][a11y]** · **[NET-NEW]** |
| R10 | **Precise-opt-in consent reference** — a field/check linking a `precise` node to its governance-log consent entry; flag a precise node with no recorded consent | D3 | P2 | S | privacy · **[corroborates governance §4]** |
| R11 | **Machine-readable data dictionary + data-schema version signal** for surface/export fields, so integrators can pin against the README's semver promise | E3, D4 | P2 | M | **[reuse][commons]** · **[corroborates README semver + ADR 0007]** |

## Expansion backlog (new capability)

| ID | Item | Personas | Pri | Effort | Evidence · tag |
| --- | --- | --- | --- | --- | --- |
| E1 | **Plain-language neighborhood exposure brief / advocacy export** — "this block ran Danger N days this month," with sourced canopy/AC/redlining context, built on the existing export surface | C3, C1, R(esidents) | P1 | M | **[ej-distribution][compound][commons]** · **[corroborates ROADMAP 5.5]** |
| E2 | **Deepen the "show your work" trust view** — calibration version, ± uncertainty, QC verdict, and reference-monitor lineage as a first-class panel, not buried provenance | E1-res, D2, A5 | P2 | M | **[trust][reuse]** · **[corroborates ROADMAP 5.2]** |
| E3 | **Citable, versioned data snapshot + citation string / DOI** — a frozen, identified release a researcher/journalist can publish against | E1-res, E2-journ, D4 | P1 | M | **[reuse][commons]** · **[extends ROADMAP 5.2 · NET-NEW]** |
| E4 | **"No local reference" / transfer-calibration path** — guidance + tooling to calibrate when no regulatory monitor is nearby (travelling reference unit; chained co-location to a distant AQS/AirNow site), provenance recorded honestly | B3, C1 | P1 | L | **[monitoring-gap][calibration][drift]** · **[NET-NEW]** |
| E5 | **Privacy-preserving alert delivery recipe** — a documented, collective-run SMS/WhatsApp bridge where contact details **never touch swelter**, hardening the existing webhook pattern | A4, C3 | P2 | M | **[ej-distribution]** + ADR 0010 · **[extends alerts.md · NET-NEW]** |
| E6 | **Round-trip interoperability proof** — swelter → SensorThings → a standard client, and a parameter crosswalk to OpenAQ/Sensor.Community, so swelter feeds the commons it draws from | D4, E3-dev, E1-res | P2 | M | **[commons][reuse]** · **[corroborates ROADMAP 5.3 + ADR 0007]** |
| E7 | **CDC HeatRisk-style heat guidance layer** paired with AQI atop the compound surface — sourced, non-prescriptive, bilingual | A2, C1 | P2 | M | **[compound][heat-deadliest]** + ADR 0009 · **[extends ROADMAP 5.1/5.5]** |
| E8 | **Funder / partner evidence pack** — a one-pager assembling community-ownership, sustainability, and coverage-equity evidence. ✅ Implemented 2026-06-30 (working tree, uncommitted) — `docs/FUNDER-EVIDENCE-PACK.md`, all claims cited from existing repo evidence, honest limits stated | F1 | P2 | S | **[commons][monitoring-gap]** · **[corroborates ROADMAP 5.3 + POSITIONING]** |
| E9 | **Accessibility + bilingual compliance hook** for agency partners — package WCAG 2.2 AA + en/es against the DOJ ADA Title II rule | C1, C2, F1 | P2 | S | **[language][a11y]** · **[corroborates ROADMAP 5.4]** |
| E10 | **Cooling-center overlay auto-ingest** from open civic datasets (today the overlay is curated/manual) | C2, A4 | P3 | M | ADR 0011 · **[NET-NEW]** |
| E11 | **Caveat-baked share card / screenshot** — an export image that carries provisional + hourly-window labels so a number can't travel context-free | E2-journ, C2 | P2 | S | **[trust][standards]** · **[NET-NEW]** |
| E12 | **Signed, staged OTA firmware updates** — `HARDWARE.md` documents OTA as *intended, not implemented*; close it so drift fixes don't require a USB visit per node | B2, B3 | P3 | L | **[drift][commons]** · **[corroborates HARDWARE.md]** |

---

## Sequenced roadmap (Now / Next / Later)

Ordered by leverage and tied to Phase 5. Each item is its own PR + test + ADR; none
weakens a hard rule.

**Now — close the resident interpretation gap, bilingually, and make durability
legible.** (Mostly S/M; highest mission + funding leverage.)
- **R1** sourced guidance + **R2** bilingual-by-gate + **R3** Spanish trust summary →
  the data-to-action bridge the mission audience needs, in both languages
  (**ROADMAP 5.5**). **[heat-deadliest][compound][language]**
- **R5** caveats travel with the value + **R9** plain-language uncertainty/provisional
  gloss → the honesty stays legible and un-croppable (**ROADMAP 5.2**). **[trust][standards]**
- **E8** funder evidence pack → assembles the survival case while the rest ships
  (**ROADMAP 5.3**). **[commons]**

**Next — confirm heat, watch equity, serve research and agencies.**
- **R4** heat-index trustworthiness → heat becomes confirmable, not always provisional.
  **[heat-deadliest]**
- **R6** coverage-equity surface → the fairness risk the audits name becomes a live
  metric. **[monitoring-gap]**
- **E1** advocacy brief + **E7** HeatRisk-style guidance layer (**ROADMAP 5.5/5.1**).
- **E3** citable DOI snapshot + **R11** data dictionary/semver → research/dev reuse
  (**ROADMAP 5.2**). **[reuse]**
- **E9** compliance hook + **R8** manual-a11y artifact (**ROADMAP 5.4**). **[a11y][language]**

**Later — replicability depth and interoperation.**
- **E4** no-local-reference / transfer calibration → the single biggest unlock for
  communities without a nearby monitor (**ROADMAP 5.3**). **[monitoring-gap][calibration]**
- **E2** deep trust view, **E6** round-trip interop, **E5** alert delivery recipe,
  **E11** caveat share card, **R7** host preview, **R10** consent reference,
  **E10** cooling auto-ingest, **E12** OTA.

## Recommended first sprint

The triage and Phase 5 converge on the same starting line: the engine is trusted;
the resident-facing *interpretation and durability story* is the gap. Ship, in one
sprint, the afternoon/day-sized, mission-and-funding wins:

1. **R1 + R2 — sourced guidance, bilingual by gate.** Bridges number → decision for
   every resident persona (A1–A3, C1) *and* keeps es parity true, with the
   safety-claim line firmly held (audit A6). The single highest-leverage mission
   move. **[heat-deadliest][compound][language]**
2. **R5 + R9 — caveats and uncertainty that stay legible.** Cheap, and turns the
   honesty engine from "invisible/expert-only" into something residents and
   screen-reader users can read (A5, D2, E2). **[trust][standards]**
3. **R3 — Spanish trust summary.** Completes the bilingual trust story end to end
   (A3). **[language]**
4. **E8 — funder evidence pack.** A one-pager that converts the community-ownership +
   sustainability + coverage-equity story into the durability case a funder rewards
   (F1), while the engineering items above ship. **[commons]**

Bundle the day-sized **R6** (coverage-equity surface) if capacity allows — it makes
the fairness commitment in audit B observable rather than asserted.

## Traceability matrix (persona → findings)

| Persona | Remediations | Expansions |
| --- | --- | --- |
| A1 Eleanor (elder) | R1, R9 | E7 |
| A2 Marisol (asthma parent) | R1, R4 | E7 |
| A3 Rosa (Spanish-first) | R1, R2, R3 | — |
| A4 Darnell (renter, no AC) | — | E5, E10 |
| A5 James (blind/SR) | R8, R9 | E2 |
| B1 Tomás (host) | R7 | — |
| B2 Devon (steward) | R6 | E12 |
| B3 Hana (calibration lead) | — | E4, E12 |
| B4 Lucía (a11y/lang keeper) | R2 | E9 |
| C1 Dr. Awad (public health) | R1, R5 | E1, E7, E9 |
| C2 Mateo (heat official) | R4 | E9, E10, E11 |
| C3 Renata (EJ organiser) | — | E1, E5 |
| D1 Grace (a11y auditor) | R8 | — |
| D2 Alex (skeptic) | R5 | E2, E11 |
| D3 Imani (privacy auditor) | R10 | — |
| D4 Stefan (standards steward) | R11 | E3, E6 |
| E1 Dr. Chen (researcher) | R11 | E2, E3, E6 |
| E2 Priya (journalist) | R5 | E3, E11 |
| E3 Wei (developer) | R11 | E3, E6 |
| F1 Karen (funder) | R6 | E8, E9 |
| F2 Chelsea (maintainer) | all (scope discipline) | all (per-PR + ADR) |

## What to validate with real users / risks

This roadmap is built on **synthetic** personas and **real** literature. Before
building anything beyond the cheapest copy changes, validate:

- **Does guidance help or scare?** R1/E7 assume sourced, non-prescriptive context
  helps residents decide. With real residents, test that it does **not** read as a
  safety promise (hard-rule and audit-A6 risk) or, conversely, increase anxiety on
  provisional days. Heat undercount and the synergistic compound risk
  (**[heat-deadliest][compound]**) make the stakes of getting this wording right
  high. Test wording with a public-health partner.
- **Will a host trust the grid-snap preview (R7)?** Validate that showing the public
  coordinate reassures rather than alarms, and never nudges a host toward `precise`.
- **Is transfer calibration (E4) scientifically defensible?** It must not let a
  network claim accuracy it can't support; pair with a domain expert and keep the
  non-regulatory framing (**[calibration]**). High effort, high replicability payoff
  — but the highest scientific risk in the backlog.
- **Coverage-equity metric design (R6).** Surfacing it could be misread as ranking
  neighborhoods; design the framing with a CBO partner, and treat co-location
  allocation as the governance decision it is (audit B5).
- **Demand is unverified.** No real funder, official, researcher, or resident has
  asked for any of this. Treat counts of "personas who raised it" as **panel
  coverage, not demand**.

## Honest limits

This is simulated research over a real product. It is good at surfacing plausible
gaps and forcing the "who is this for?" question; it is **bad** at telling you which
gaps matter, how many real stakeholders exist, or what they'd adopt. It
over-represents the author's mental model and the repo's own framing (the personas
literally read the docs), and it will miss what only real users surprise you with.
The prior synthetic study ([`research/user-research-panel.md`](research/user-research-panel.md))
correctly drove a wave of now-shipped fixes — which is exactly the right use of this
method: **a hypothesis generator that lowers the cost of real discovery, never a
substitute for it.** Do not prioritise off this document alone. Use it to design the
questions for, and reduce the cost of, real interviews with frontline residents,
hosts, a public-health partner, and a candidate funder.

Author: Chelsea Kelly-Reif, 2026. swelter is an independent personal open-source
project; see `NOTICE`. Companion document: [`USER-RESEARCH.md`](USER-RESEARCH.md).
