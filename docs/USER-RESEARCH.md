# User research — synthetic persona panel

> [!WARNING]
> **These personas and interviews are synthetic.** They were generated as a
> structured brainstorming device — LLM personas exercising the **real** swelter
> dashboard, CLI, API, firmware, and docs — *not* conducted with real people. No
> real resident, host, official, or researcher said any of this. Treat every
> "quote" and preference as a **hypothesis to validate**, never as evidence of
> demand or proof that a feature is wanted. This is consistent with how the project
> labels its synthetic data (see [`audits/methodology.md`](audits/methodology.md))
> and how the prior synthetic study was labelled
> ([`research/user-research-panel.md`](research/user-research-panel.md)).
>
> Everything a persona "values today" maps to a feature that **actually exists in
> this repo**; nothing about the product is invented. External facts carry inline
> citations to real sources (see [Research basis](#research-basis-sources) at the
> foot of this file). The honest next step is real discovery with ≥5 people per
> group — especially frontline residents, hosts, and a public-health partner.
>
> **Last assembled: 2026-06-30.**

The companion document, [`RESEARCH-ROADMAP.md`](RESEARCH-ROADMAP.md), turns these
interviews plus the cited research into a triaged backlog that **complements** the
existing phased plan in [`ROADMAP.md`](ROADMAP.md) (it does not replace it).

---

## Why do this at all

swelter is built "for frontline neighborhoods that live the exposure and rarely
hold the data" (README). That mission spans far more roles than the resident who
opens the map: the host whose porch holds a node, the steward who runs ingest at
2 a.m., the health official who needs a citable number, the researcher who reuses
an authorized first-party CC0 archive or source-aware provider export, the auditor who checks the
privacy grid, the funder who decides
whether it lives. Role-playing the full cast around the real product surfaces gaps
a single author misses and forces the question *"who is each feature for?"* — the
same discipline the project applies to its calibration and accessibility work.

The synthesis is tagged so it does not become a wishlist. In the roadmap, each
item is marked **[corroborates …]** where it independently re-discovers something
already in [`ROADMAP.md`](ROADMAP.md) (Phase 5) or the audits — triangulation is a
signal — and **[NET-NEW]** where the panel surfaced it fresh.

## How to read a persona

Each card is the simulated interview compressed to five lines: **Goal · Values
today** (grounded in a real, shipped feature) **· Gets stuck · Wants next ·
Adopts-if / Walks-if.** "Values today" never references something that does not
exist in the repo as of this date.

## Method

- **Sampling frame.** swelter's real stakeholder universe, organised by
  *relationship to the product*, not by demographics:
  - **Live & Use** — residents who live the heat-and-air exposure: a heat-vulnerable
    elder, a parent of an asthmatic child, a Spanish-first renter, a low-income
    renter with no AC, a blind screen-reader user.
  - **Host & Steward** — the collective that runs the network: a sensor host, a
    data/ops steward, a calibration lead, an accessibility-and-language keeper.
  - **Decide & Respond** — institutions that act on the data: a public-health
    department epidemiologist, a city heat-response official, a community-based
    EJ organiser.
  - **Assure & Audit** — independent scrutiny: an accessibility auditor, a
    sensor-skeptic ex-regulatory scientist, a responsible-tech/privacy auditor, an
    open-data/standards steward from the Sensor.Community / OpenAQ ecosystem.
  - **Reuse & Research** — people who consume the open data: an atmospheric /
    public-health researcher, a data journalist, a civic-tech API developer.
  - **Fund & Operate** — a philanthropy program officer and the owner/maintainer.
- **Protocol.** For each persona: a concrete goal, a walkthrough of the live
  surfaces they would touch (dashboard map/table/list, `swelter` CLI, the
  SensorThings + surface + export API, the alerts feed, the firmware and hardware
  docs, governance and calibration docs), what worked, where they stalled, and an
  open "what would make this a 10/10" prompt. Technical personas were allowed to
  inspect source and re-run the pipeline; resident personas worked only through the
  UI on their stated device.
- **Research basis.** The stakes, vulnerabilities, and best-practice bars below are
  not invented — they are drawn from current literature and standards, cited inline
  and listed at the foot of this file:
  - Extreme heat is the **deadliest** US weather hazard — it kills more Americans
    each year than floods, tornadoes, hurricanes, or lightning, and the CDC counted
    **2,394 heat-related deaths in 2024** (2,415 in 2023), figures themselves
    believed to be undercounts.[^heat-deadliest][^heat-deaths][^heat-undercount]
  - The burden is unevenly distributed: formerly **redlined** neighborhoods run
    hotter today (mean ~2.6 °C, up to ~7 °C, across 94% of 108 US areas
    studied),[^redlining] low-income and majority-POC blocks carry markedly **less
    tree canopy** (~26% / ~38% less),[^treeequity] and indoor heat deaths cluster
    among **isolated, low-income elders** — in 2019 Maricopa County, 91% of those
    who died indoors *had* AC that was off, set too high, or broken.[^elders]
  - The official record is **sparse**: the nearest regulatory PM2.5 monitor sits on
    average ~18.8 km (urban) away, and under the 2024 standard ~44% of exceeding
    urban areas — ~20M people — go undetected.[^gaps][^monitor-equity] This is the
    gap low-cost networks fill.
  - Low-cost sensors are only credible **after calibration**: the US-EPA PurpleAir
    correction with a humidity term cuts PM2.5 RMSE from ~8 to ~3 µg/m³,[^barkjohn]
    sensors **drift** and need periodic re-co-location,[^drift] and corrected
    low-cost data remains a **non-regulatory** tier.[^epa-nonreg]
  - Standards the dashboard must speak to: the **WHO 2021** PM2.5 guideline (5
    µg/m³ annual / 15 µg/m³ 24-h),[^who] the **EPA 2024** PM2.5 NAAQS lowered to 9.0
    µg/m³ with a revised AQI,[^naaqs] and **CDC's** pairing of HeatRisk with the
    AQI.[^cdc-heatrisk]
  - Comparable networks teach what to copy and what to fear: **OpenAQ** on open,
    FAIR aggregation;[^openaq] **Imperial County / IVAN** on community ownership as
    the survival factor;[^imperial] **Array of Things** on how vendor-run sensor
    nets wind down when cost and maintenance aren't owned locally.[^aot]
  - Accessibility and language are mission-critical, not polish: a non-visual
    **data-table equivalent** for every non-trivial chart is the documented
    best practice,[^a11y-dataviz] and **language access** for LEP residents is a
    health-equity and civil-rights obligation, sharpest in climate
    emergencies.[^lep]
- **Synthesis.** Frictions → **R**emediations; wishes → **E**xpansions, both in the
  roadmap, each tagged corroborates/NET-NEW with an effort estimate (S ≈ an
  afternoon · M ≈ a day or two · L ≈ a week+).

---

## Persona roster

| ID | Persona | Group · context | Primary goal | Top friction |
| --- | --- | --- | --- | --- |
| **A1** | **Eleanor, 78** | Live & Use · low vision + hand tremor, top-floor apartment, no AC, tablet | Decide if it's safe to walk to the store this afternoon | Heat shown only as a *provisional* number; no "what this means for me" |
| **A2** | **Marisol, 35** | Live & Use · parent of asthmatic 8-yo, bilingual, mid Android | Decide if her kid can play outside today | Compound heat+air is exactly her question, but exposure is provisional until heat calibrates |
| **A3** | **Rosa, 54** | Live & Use · Spanish-monolingual renter, older phone | Read her block's air in Spanish she trusts | Chrome is Spanish; the *calibration/trust* explainer she's pointed to is English-only |
| **A4** | **Darnell, 41** | Live & Use · low-income renter, gig driver, no AC, prepaid data | Know when his block crosses a danger line without babysitting a map | Alerts exist as a feed, but subscribing assumes an RSS reader he doesn't run |
| **A5** | **James, 44** | Live & Use · blind, NVDA/VoiceOver power user, QA by trade | Operate the whole dashboard non-visually and trust it | The strong table/list path is real; he wants the *uncertainty* he hears to mean something |
| **B1** | **Tomás, 67** | Host & Steward · retiree hosting a porch node, privacy-conscious | Help the block without exposing where he lives | Has to take "coarse grid" on faith — wants to *see* what the public map publishes about him |
| **B2** | **Devon, 39** | Host & Steward · collective lead / data + ops steward | Keep the network honest and running on a laptop | `swelter qc` shows gaps and node health; coverage *equity* across blocks is a manual read |
| **B3** | **Hana, 33** | Host & Steward · calibration lead, volunteer chemist | Get every node calibrated against a reference | Their county has **no** nearby reference monitor to co-locate against |
| **B4** | **Lucía, 29** | Host & Steward · accessibility & language keeper | Keep es parity real, not machine output | New health/guidance copy risks shipping English-first and stranding es |
| **C1** | **Dr. Awad, 48** | Decide & Respond · county climate-health epidemiologist | Target outreach to the hottest, smokiest blocks | Wants block-level *and* a defensible non-regulatory caveat in one place |
| **C2** | **Mateo, 52** | Decide & Respond · city heat-response official / CHO | Site cooling resources and name worst blocks publicly | Heat index is published provisional in the demo — no calibrated heat fact to state |
| **C3** | **Renata, 44** | Decide & Respond · CBO / tenants'-association EJ organiser | Turn readings into an advocacy ask a landlord/agency can't dodge | The data is open and honest, but there's no plain-language neighborhood brief to hand over |
| **D1** | **Grace, 37** | Assure & Audit · accessibility auditor, screen-reader user | Confirm the WCAG 2.2 AA claim is lived, not asserted | Structural gate is real; she wants the manual SR/contrast pass surfaced as an artifact |
| **D2** | **Alex, 51** | Assure & Audit · ex-regulatory scientist, sensor skeptic | Catch any place the map overstates certainty | Hourly AQI from EPA 24-h breakpoints — wants the window disclosure everywhere it's shown |
| **D3** | **Imani, 40** | Assure & Audit · responsible-tech / privacy auditor | Verify "no PII, coarse by default" by construction | Verifiable in code and the DPIA; wants the precise-opt-in consent trail easier to inspect |
| **D4** | **Stefan, 46** | Assure & Audit · open-data / standards steward (Sensor.Community + OpenAQ) | Confirm swelter interoperates and won't fork the commons | SensorThings subset + source-aware exports are right; wants round-trip *into* OpenAQ/Sensor.Community proven |
| **E1** | **Dr. Chen, 50** | Reuse & Research · atmospheric / public-health researcher (CBPR) | Reuse the archive with machine-readable provenance | Reproducible to the byte; wants a citable, versioned snapshot + DOI to publish against |
| **E2** | **Priya, 36** | Reuse & Research · data journalist on a heat story | Cite block-level heat/air without overclaiming | Caveats live on screen but don't survive a screenshot; heat is provisional in the demo |
| **E3** | **Wei, 31** | Reuse & Research · civic-tech developer / API integrator | Build a neighborhood app on the API | Read-only API is clean; wants stable schema versioning and a machine-readable data dictionary |
| **F1** | **Karen, 55** | Fund & Operate · climate/health-equity program officer | Decide if a grant survives past its term | Needs replicability + sustainability + coverage-equity evidence in one pack |
| **F2** | **Chelsea** | Fund & Operate · owner / maintainer | Keep `make verify` green and the hard rules intact | Wants the panel to sharpen Phase 5, not balloon scope or weaken a hard rule |

---

## Group A — Live & Use (residents who live the exposure)

### A1 — Eleanor, 78 (low vision + hand tremor, top-floor apartment, no AC)
- **Goal:** decide if it's safe to walk three blocks to the store this afternoon.
- **Values today:** the dashboard **defaults to the List view**, not the map, and
  she can switch units to **°F**; severity is in **words and pattern, not colour
  alone**; the **"use my location → nearest location"** button finds her block
  without typing; nothing asks her to log in.
- **Gets stuck:** the heat reading on her block is **provisional** (the demo
  co-locates temperature and PM, not the derived heat index — `api.md`), and the
  page — correctly — "never tells an individual they are safe." She is left with an
  honest number and no bridge to *her* decision, exactly the gap the research on
  isolated elder heat deaths warns about.[^elders]
- **Wants next:** a short, **sourced** "what this means" line per category ("Heat is
  Danger today — older adults should limit time outside, per CDC/NWS"), framed as
  context with a citation, never a personal safety promise.
- **Adopts if:** she gets one clear number, in °F, with one plain sentence of
  sourced context. **Walks if:** every reading that matters reads "provisional" and
  the tool only ever says "no."

### A2 — Marisol, 35 (parent of an asthmatic 8-year-old, bilingual, mid Android)
- **Goal:** decide if her son can play outside today.
- **Values today:** the **compound heat-and-air `exposure` surface** (ADR 0009) is
  literally her question answered as one level — and it is honest: it is the
  *higher* of the heat and air concern, flags a `compound` day when both bite, and
  **stays provisional until both components are confirmed**. PM2.5 cells show an
  **AQI category in plain words** with a **"What is AQI?"** explainer and EPA health
  guidance.
- **Gets stuck:** on a hot, smoky day — the days the literature shows are
  *synergistically* deadlier, ~3× either exposure alone[^compound] — the exposure
  level reads provisional precisely because heat isn't calibrated, so the one number
  built for her parents-of-sensitive-kids case is the one she's told not to lean on.
- **Wants next:** sensitive-group guidance tied to the AQI category in **both**
  en + es, and a network path to confirm heat so exposure stops being provisional.
- **Adopts if:** the compound level becomes confirmable and speaks to asthma.
  **Walks if:** the scariest days are always the provisional ones.

### A3 — Rosa, 54 (Spanish-monolingual renter, older phone)
- **Goal:** read her block's air quality in Spanish she actually trusts.
- **Values today:** the dashboard ships **en + es bundles** with full chrome
  parity; the legend, the provisional note, and the "we don't tell you you're safe"
  framing read as real translation; locations carry **human block labels**, not
  cell codes.
- **Gets stuck:** the deeper **trust/calibration explainer** the footer points to
  is English-only — and language access for LEP residents is precisely a
  health-equity and civil-rights obligation, sharpest in climate
  emergencies.[^lep] "La parte en español me da confianza; la explicación en inglés
  me la quita."
- **Wants next:** an in-page Spanish "cómo leer esto / qué es el ICA" summary, so
  the trust story is bilingual end to end, not just the chrome.
- **Adopts if:** the explanation of *why to trust a number* is in her language.
  **Walks if:** Spanish stops at the buttons.

### A4 — Darnell, 41 (low-income renter, gig driver, no AC, prepaid data)
- **Goal:** be told when his block crosses a danger line, without watching a map.
- **Values today:** the **neighborhood alerts feed** (ADR 0010) publishes every
  cell past a documented danger floor (AQI ≥ 101, heat index ≥ 39.4 °C / 103 °F,
  exposure ≥ High) as **`/api/alerts.json` and a subscribable Atom feed** — **no
  account, no subscriber list, no PII** — and the dashboard is a small PWA he can
  install. The whole posture fits a renter who can't run AC all day.[^elders]
- **Gets stuck:** "subscribe in any RSS/Atom reader" assumes a reader he's never
  used; the collective-run webhook→SMS bridge runs in *its* infra, not something he
  can self-serve.
- **Wants next:** a dead-simple way for the collective to opt him into SMS/WhatsApp
  alerts that keeps contact details **out of swelter** (the privacy posture is the
  point, not an obstacle).
- **Adopts if:** a danger-day text reaches him without him configuring anything.
  **Walks if:** acting on alerts requires tooling he doesn't have.

### A5 — James, 44 (blind, NVDA/VoiceOver power user, QA engineer)
- **Goal:** operate the entire dashboard non-visually and actually trust it.
- **Values today:** this is a genuine non-visual map equivalent — the **sortable
  table and plain list are equal views of one surface** with identical filtering, a
  real `tablist` with roving tabindex, AQI/heat severity in **text and pattern**,
  the time slider **keyboard-operable and announced via `aria-live`**, and the
  **on-screen ± uncertainty** now reaches the UI. That table-equivalent-for-every-
  chart pattern is exactly the documented best practice.[^a11y-dataviz]
- **Gets stuck:** he hears "± 0.5 °C" but the page doesn't tell a non-expert what a
  1-σ residual *means*; and a provisional cell announces a value with no error bar,
  which to him reads as "less trustworthy," not "uncalibrated."
- **Wants next:** a one-line, screen-reader-friendly gloss of uncertainty and of
  "provisional," so the honesty he can hear is also legible.
- **Adopts if:** the careful science is narratable. **Walks if:** the table green-
  lights a number whose trust state he can't interpret by ear.

---

## Group B — Host & Steward (host and run the network)

### B1 — Tomás, 67 (retiree hosting a porch node, privacy-conscious)
- **Goal:** help the block without advertising where he lives.
- **Values today:** **coarse ~150 m grid-snap is the default and the floor**;
  `precise` is a per-node, host-only opt-in that needs his recorded consent
  (`governance.md` §3–§4); the firmware has **no GPS, mic, camera, BT, or Wi-Fi
  scanning** by construction (hard rule 1); and `ABOUT-THE-NETWORK.md` explains all
  this in neighbor-language he can read.
- **Gets stuck:** he has to *trust* that the published coordinate is the cell
  centre and not his porch — the guarantee is in code and the DPIA, but he can't see
  it as a host.
- **Wants next:** a host-facing "this is exactly what the public map and API
  publish about your node" preview, so coarse-by-default is visible, not asserted.
- **Adopts if:** he can see his node is grid-snapped. **Walks if:** he can't tell
  what's public about him.

### B2 — Devon, 39 (collective lead / data + ops steward)
- **Goal:** keep the network honest and running from a laptop, untended.
- **Values today:** `swelter qc` and **`/api/health.json`** give per-node
  status (ok/degraded/offline), completeness, flagged fraction, and the **longest
  gaps listed**, not just counted; the store is a **copyable folder**; governance,
  the **right to leave**, and roles are documented; `make verify` is the merge gate.
- **Gets stuck:** the fairness question the audits themselves raise — *are the
  uncalibrated/provisional cells concentrated in the frontline blocks?* (audit
  B3/B4) — is a manual per-release read, not something the dashboard or `qc`
  surfaces. That's the exact two-tier-map hazard.[^monitor-equity]
- **Wants next:** a coverage-equity view (calibrated vs raw nodes per block) in `qc`
  / the health panel, so the steward sees inequity forming.
- **Adopts if:** the tool flags coverage inequity. **Walks if:** he has to compute
  equity by hand every month.

### B3 — Hana, 33 (calibration lead, volunteer chemist)
- **Goal:** get every node calibrated against a reference, then keep it calibrated.
- **Values today:** the **calibration engine is the heart of the product** — pure-
  Python OLS, humidity-aware PM in the **EPA PurpleAir lineage**,[^barkjohn]
  enclosure-offset temp, **published `residual_std` and R²**, a **versioned registry
  that rebuilds byte-for-byte**, and **drift tracking via re-co-location** with a
  service flag when residuals widen — all documented in `calibration.md`.
- **Gets stuck:** her county has **no nearby regulatory monitor** to co-locate
  against — the same sparsity that motivates the whole project.[^gaps] Without a
  reference, every node stays raw/provisional.
- **Wants next:** a "no local reference" path — guidance/tooling for transfer
  calibration (a travelling reference-grade unit, or co-locating one node at a
  distant AQS/AirNow site and chaining), with the provenance recorded honestly.
- **Adopts if:** she can calibrate without a monitor next door. **Walks if:**
  calibration assumes a reference she'll never have.

### B4 — Lucía, 29 (accessibility & language keeper)
- **Goal:** keep Spanish parity a real translation, not machine output
  (`governance.md` §6).
- **Values today:** all dashboard strings live in **per-language bundles**; es ships
  in v1 "because of who the network serves"; the a11y gate is **merge-blocking**.
- **Gets stuck:** any *new* health-guidance or trust copy (what A1/A2/A3 ask for)
  risks landing English-first, duplicating a language gap — and language access is a
  civil-rights obligation, not a nice-to-have.[^lep]
- **Wants next:** a rule (and ideally a check) that resident-facing guidance strings
  can't ship unless both `en` and `es` bundles carry them.
- **Adopts if:** new copy is bilingual by gate. **Walks if:** guidance ships in
  English and es catches up later.

---

## Group C — Decide & Respond (act on the data institutionally)

### C1 — Dr. Awad, 48 (county climate-health epidemiologist)
- **Goal:** target heat-and-smoke outreach to the most exposed blocks.
- **Values today:** a **gridded, hourly heat-and-AQI surface** at neighborhood
  resolution — exactly the block-scale signal the sparse regulatory network can't
  give[^gaps] — with **AQI from EPA 2024 breakpoints**,[^naaqs] a **compound
  exposure layer**, and the honest **non-regulatory** framing[^epa-nonreg] she needs
  to use it without overclaiming. The **cooling-center overlay** (ADR 0011) pairs
  exposure with where to send people.
- **Gets stuck:** she wants the "hourly AQI, not the official 24-h AQI" caveat
  (stated in `api.md` as `aqi_window: "hourly-mean"`) to be unmissable wherever a
  number travels into a briefing or a screenshot.
- **Wants next:** a per-block exposure summary she can drop into a health advisory,
  caveat attached, plus CDC HeatRisk-style framing alongside AQI.[^cdc-heatrisk]
- **Adopts if:** it's citable with the caveat baked in. **Walks if:** the hourly-vs-
  24-h distinction is easy to lose downstream.

### C2 — Mateo, 52 (city heat-response official / Chief Heat Officer)
- **Goal:** site cooling resources and name the worst blocks at a podium.
- **Values today:** **continuous, standing** infrastructure — unlike the one-day-a-
  year volunteer heat traverse that is the funded incumbent[^capa] — owned by the
  community, with a public, **source-attributed** surface he can cite, a **"worst right now"**
  readable map/table, and a cooling-center overlay.
- **Gets stuck:** in the demo, **heat index is published raw/provisional** (only
  temp and PM are co-located — `api.md`), so the single fact he most needs to state
  out loud — "this block's heat is X" — is the one the system tells him not to assert
  as fact.
- **Wants next:** a network configuration where heat index is calibrated (or derived
  from already-calibrated temp + humidity) so heat becomes a podium-ready, confirmed
  number.
- **Adopts if:** he can state a calibrated heat figure. **Walks if:** all heat is
  provisional.

### C3 — Renata, 44 (CBO / tenants'-association EJ organiser)
- **Goal:** turn readings into an advocacy ask a landlord or agency can't dodge.
- **Values today:** the data is **exportable with no account and its actual source terms**, the network is
  **community-owned with a right to leave**, and the **alerts feed** documents
  danger days — all the ingredients of an accountability story, and the kind of
  block-scale evidence newsrooms have had to build themselves because official data
  couldn't answer the question.[^propublica]
- **Gets stuck:** "data alone is not the product" — the research is consistent that
  the gap is from data to action,[^imperial] and swelter hands her CSVs and a map,
  not a plain-language neighborhood brief she can put in front of a landlord.
- **Wants next:** a lightweight, sourced "neighborhood exposure brief" / advocacy
  export (this block ran Danger N days this month, here's the canopy/AC context),
  built on the existing export surface.
- **Adopts if:** it produces a handout, not a spreadsheet. **Walks if:** she has to
  build the narrative from raw rows every time.

---

## Group D — Assure & Audit (independent scrutiny)

### D1 — Grace, 37 (accessibility auditor, daily screen-reader user)
- **Goal:** confirm the WCAG 2.2 AA claim is lived, not a badge.
- **Values today:** accessibility is a **merge-blocking CI gate** (12 structural
  checks), there's a committed **ACR/VPAT 2.5 (Rev 508)**, the map has a **real
  data-table + list equivalent**, severity is never colour alone, and the project is
  candid (it self-marks cognitive load only "Partially Supports"). This is the rare
  case of the documented best practice actually shipped.[^a11y-dataviz]
- **Gets stuck:** the structural gate can't judge computed contrast or live ARIA;
  the **manual NVDA/VoiceOver pass** exists in `audits/accessibility-report.md` but
  isn't surfaced as a dated, prominent artifact a third party can rely on.
- **Wants next:** the manual a11y pass published as a first-class, dated artifact
  alongside the auto gate; a "known a11y gaps" note kept current.
- **Adopts if:** the manual review is inspectable. **Walks if:** "AA" rests on
  structural checks alone.

### D2 — Alex, 51 (ex-regulatory atmospheric scientist, sensor skeptic)
- **Goal:** catch any place the presentation overstates the science.
- **Values today:** the engine holds up — **calibrated vs raw never silently
  mixed**, **1-σ uncertainty for calibrated values** through API and export, **reproducible
  registry**, and `pm25_aqi()` on **EPA 2024 breakpoints**.[^naaqs] The
  uncertainty-as-trust posture is exactly what EPA-convened experts recommend as the
  antidote to public distrust.[^trust]
- **Gets stuck:** AQI is computed from **hourly** means against **24-hour**
  breakpoints; `api.md` discloses `aqi_window: "hourly-mean"`, but he wants that
  caveat to ride the value into every surface, legend, alert headline, and export —
  not just the API doc.
- **Wants next:** the hourly-vs-24-h window disclosure propagated everywhere a
  category word appears; optionally a NowCast option.
- **Adopts if:** the window is impossible to lose. **Walks if:** a named EPA
  category rides an hourly value with no on-surface caveat.

### D3 — Imani, 40 (responsible-tech / privacy & data-protection auditor)
- **Goal:** verify "no PII, coarse by default" by construction, not by promise.
- **Values today:** the `Observation` schema is a **frozen dataclass with no
  person-bearing field**, **`public_location()` is the only coordinate path** (grid-
  snap by default), there's a committed **DPIA** and a six-part responsible-tech
  audit, and the API is **read-only**. The misuse model is honestly named as
  *misrepresentation*, not exfiltration.
- **Gets stuck:** the precise-location **consent trail** lives in a human governance
  log (`governance.md` §8) plus a `network.yaml` diff — auditable, but spread across
  two places and easy to let drift.
- **Wants next:** a tighter, inspectable link between a `precise` node and its
  recorded consent (e.g. a consent reference field or a check that flags a precise
  node lacking a log entry).
- **Adopts if:** precise-opt-ins are provably consented. **Walks if:** precision can
  be flipped without a traceable record.

### D4 — Stefan, 46 (open-data / standards steward, Sensor.Community + OpenAQ)
- **Goal:** confirm swelter strengthens the open-AQ commons instead of forking it.
- **Values today:** a **read-only OGC SensorThings 1.1 subset** (Things, Locations,
  Datastreams, ObservedProperties, Observations) with true `@iot.count` +
  `nextLink`, source-aware CSV/JSON, and a **Datasette-openable** store —
  and swelter already **ingests real Sensor.Community (Stuttgart) and OpenAQ
  (California) data** through the same pipeline, dropping the SDS011 999.9 µg/m³
  over-range sentinel honestly. This is the FAIR, harmonised posture OpenAQ
  models.[^openaq]
- **Gets stuck:** ingestion *from* those networks is proven; he hasn't seen the
  round-trip *back* — a swelter network published so an OpenAQ/Sensor.Community
  client consumes it cleanly.
- **Wants next:** a documented, tested round-trip (swelter → SensorThings → a
  standard client) and a published data dictionary mapping swelter parameters to the
  ecosystem's.
- **Adopts if:** swelter is a good citizen in both directions. **Walks if:** it only
  consumes the commons.

---

## Group E — Reuse & Research (consume the open data)

### E1 — Dr. Chen, 50 (atmospheric / public-health researcher, CBPR)
- **Goal:** reuse the archive in a study with machine-readable provenance.
- **Values today:** the field holds low-cost data back for missing calibration, QA,
  and traceability;[^research-qa] swelter answers that directly — an **append-only
  raw log**, **rebuildable calibrated records**, **versioned correction ids**, a
  **1-σ uncertainty per calibrated value**, and a **byte-for-byte reproducible** calibration she
  can re-run. That's the "check rather than trust" promise delivered.
- **Gets stuck:** to publish *against* a dataset she needs a **citable, frozen,
  versioned snapshot** with a stable identifier — the store is a live folder, not a
  pinned release with a DOI.
- **Wants next:** a versioned data snapshot + citation string / DOI, and uncertainty
  carried through the aggregated surface (it already rides the per-observation API
  and export).
- **Adopts if:** she can cite a frozen version. **Walks if:** "the data" is a moving
  folder.

### E2 — Priya, 36 (data journalist on a heat story)
- **Goal:** cite block-level heat and air without overstating it.
- **Values today:** **no-account export with source-specific terms and attribution**, filterable
  CSV/JSON carrying **calibration version, QC verdict, uncertainty, and an explicit
  `trustworthy` flag**, and a network whose **provisional vs confirmed** line is
  explicit — the reuse-ready, auditable surface newsrooms otherwise build
  themselves.[^propublica]
- **Gets stuck:** heat is provisional in the demo, and the on-screen caveats don't
  **survive a screenshot** — a single hot-cell image could travel without its
  "provisional / hourly" context.
- **Wants next:** caveats that ride the artifact (a screenshot/share card that bakes
  in provisional + hourly-window labels), and a one-paragraph "how to cite this
  responsibly" methods note.
- **Adopts if:** the caveat can't be cropped off. **Walks if:** the map hands her a
  scary number she can't responsibly run.

### E3 — Wei, 31 (civic-tech developer / API integrator)
- **Goal:** build a neighborhood app on the API.
- **Values today:** the API is **read-only and predictable** — `GET`-only (405 on
  writes), **JSON errors**, **OPTIONS 204 + open CORS**, 60 s caching, gzip, true
  `@iot.count` with `nextLink`, a `dedupe` toggle, and flat `/api/surface.json` +
  `/export.*` paths that are "flat, honest, predictable." The alerts feed and
  cooling-center overlay are clean GeoJSON/Atom.
- **Gets stuck:** he wants the **data schema's semver** (the README promises semver
  on the public API and data schema) expressed as something machine-readable he can
  pin against, plus a data dictionary for surface fields.
- **Wants next:** a published, versioned schema / data dictionary for the surface
  and export fields, and a changelog he can watch.
- **Adopts if:** the schema is pinnable. **Walks if:** fields shift under him without
  a version signal.

---

## Group F — Fund & Operate

### F1 — Karen, 55 (climate/health-equity philanthropy program officer)
- **Goal:** decide whether this survives past a grant term.
- **Values today:** the project already reasons like a fundable one
  (`POSITIONING.md`): **community ownership** as the documented survival
  factor,[^imperial] a **scale-to-zero, two-dependency Python runtime with no hosted lock-in**
  design that survives lean years, a **register-your-own-network** path
  (`ADD-YOUR-NEIGHBORHOOD.md`), and a **WCAG 2.2 AA target + bilingual evidence posture** as
  procurement input given the DOJ ADA Title II rule.[^ada] It avoids the vendor-run wind-down
  that ended Array of Things.[^aot]
- **Gets stuck:** she needs the *evidence* assembled — replicability, sustainability,
  and **coverage equity** (is the frontline getting the calibrated tier?[^monitor-equity])
  — in one place, not scattered across a roadmap, audits, and a positioning note.
- **Wants next:** a funder-facing one-pager / evidence pack pulling the
  community-ownership, sustainability, and coverage-equity story together.
- **Adopts if:** the durability case is assembled. **Walks if:** she has to
  reconstruct it from a dozen docs.

### F2 — Chelsea (owner / maintainer)
- **Goal:** keep `make verify` green and the five hard rules intact while moving
  Phase 5 forward.
- **Values today:** the contract is explicit — README is source of truth, hard rules
  are enforced not aspirational, calibration is reproducible, the a11y gate blocks
  merge, and **Phase 5** already names the forward direction (compound exposure
  built; trust-layer-visible, register-your-own, compliance asset, and data-to-
  action proposed).
- **Gets stuck:** the risk is scope-creep that quietly weakens a hard rule (a guidance
  string that becomes a safety claim; an alert bridge that pulls contact details into
  swelter; a precise-location convenience that erodes consent).
- **Wants next:** a panel that **sharpens Phase 5**, every item landing as its own
  PR + test + ADR, nothing touching a hard rule.
- **Adopts if:** the roadmap complements `ROADMAP.md` and stays inside the
  calibration/privacy/openness/accessibility discipline. **Walks if:** it reads as a
  rewrite or invites a hard-rule exception.

---

## Cross-cutting themes (what the cast agrees on)

1. **The honesty engine is the moat — and it now reaches the UI.** Calibrated-vs-raw
   separation, calibrated-value 1-σ uncertainty (on screen as well as in the API/export),
   reproducible registry, and "we don't tell you you're safe" earn trust across
   experts (D2, E1, E2) and even anxious residents (A2). This is rarer than almost
   any comparable network[^openaq][^imperial] and aligns with what EPA-convened
   experts recommend.[^trust] **Don't lose it.**
2. **The remaining resident gap is interpretation, not data.** A1, A2, A3, A5 all
   want the careful number bridged to a decision with **sourced, non-prescriptive
   guidance** in **both languages** — never a safety promise. This is the largest
   single lever for the mission audience, and it is squarely the literature's
   "data-to-action gap."[^imperial][^lep]
3. **Heat is the headline hazard but the softest layer.** Heat kills more Americans
   than any other weather hazard,[^heat-deadliest] yet the demo publishes heat index
   **provisional**. Residents (A1, A2), the heat official (C2), and the journalist
   (E2) all hit this. Enabling calibrated (or honestly-derived) heat is high-leverage
   and high-visibility.
4. **Coverage equity is the fairness risk no one is watching live.** B2, F1, and the
   audits (B3/B4) converge: if the calibrated tier clusters away from frontline
   blocks, swelter recreates the very monitoring inequity it exists to fix.[^monitor-equity]
   It should be a *surfaced* metric, not a manual per-release read.
5. **Community ownership is the survival story — make it legible.** F1, C3, B1, and
   the funding research[^imperial][^aot] all point the same way: the right-to-leave,
   no-lock-in, register-your-own design is the durability case; it just needs to be
   *assembled* and *shown* (to funders, hosts, and partners), not left implicit.
6. **Interoperate in both directions.** D4, E3, E1 want swelter to be a good citizen
   of the open-AQ commons — not just ingest Sensor.Community/OpenAQ (proven) but
   publish a clean round-trip, a pinnable schema, and a citable snapshot.[^openaq]

## Honest limits of this exercise

This is **simulated**. It can generate plausible needs and obvious gaps, but it
**cannot** tell you which are real, how many residents/hosts/officials actually
exist for swelter, or what any of them would adopt. It over-represents the author's
mental model and the repo's own framing, and it will miss what only real users
surprise you with — especially the lived reality of frontline residents, hosts who
weigh exposing their home, and a health department's procurement and liability
constraints. Several personas (B3's no-local-reference county, C3's advocacy
handoff, F1's funder calculus) hinge on facts a real conversation would correct.

The prior synthetic study ([`research/user-research-panel.md`](research/user-research-panel.md),
2026-06-17) drove a wave of fixes now visible in the product (block labels, search,
"use my location," °F/°C, on-screen uncertainty, default List view, SensorThings
pagination, the alerts and cooling-center features). That is the right use of this
method: **a hypothesis generator that lowers the cost of real discovery**, not a
substitute for it. Do **not** prioritise off this document alone — use it to design
the questions for, and reduce the cost of, interviews with real community members.

➡️ Continue to the triaged, research-backed backlog: [`RESEARCH-ROADMAP.md`](RESEARCH-ROADMAP.md).

---

## Research basis (sources)

External facts are cited inline above; URLs were accessed **2026-06-30**. Volatile
or contested items are flagged in the roadmap's evidence section. Sources marked
*(repo POSITIONING)* are already vetted in [`POSITIONING.md`](POSITIONING.md) and
reused here.

[^heat-deadliest]: Extreme heat is the deadliest US weather hazard (more than floods, tornadoes, hurricanes, lightning). FoxWeather, https://www.foxweather.com/extreme-weather/heat-deadliest-weather-united-states ; APHA, https://www.apha.org/publications/public-health-newswire/public-health-newswire/articles/extreme-heat-kills-more-people-than-any-other-extreme-weather-event
[^heat-deaths]: CDC heat-related deaths: 2,394 (2024), 2,415 (2023); NOAA 30-yr averages (heat 183 vs flood 88, tornado 72, hurricane 48, lightning 36). USAFacts, https://usafacts.org/articles/how-many-people-die-from-extreme-heat-in-the-us/
[^heat-undercount]: Heat deaths are systematically undercounted. Washington Post, https://www.washingtonpost.com/climate-environment/2024/07/01/extreme-heat-deaths-heatwave-heatstroke/ ; Scientific American, https://www.scientificamerican.com/article/u-s-deaths-from-heat-are-dangerously-undercounted/
[^redlining]: Hoffman, Shandas & Pendleton (2020), *Climate* — 94% of 108 US areas hotter in formerly redlined ("D") vs "A" areas (~2.6 °C mean, up to ~7 °C / 13 °F). Reported: Virginia Mercury, https://virginiamercury.com/briefs/there-may-be-a-link-between-urban-heat-islands-and-past-redlining-practices-study-finds/ ; PBS, https://www.pbs.org/wnet/peril-and-promise/2020/01/redlined-neighborhoods/
[^treeequity]: Tree-canopy disparity: low-income areas ~26% less canopy, majority-POC ~38% less. American Forests Tree Equity Score, https://www.americanforests.org/tools-research-reports-and-guides/tree-equity-score/ ; https://www.americanforests.org/article/the-need-for-tree-equity-is-heating-up/ ; tree cover/temperature & income across 5,723 communities, https://pmc.ncbi.nlm.nih.gov/articles/PMC8081227/
[^elders]: Indoor heat deaths cluster among isolated, low-income elders; Maricopa County 2019: 91% who died indoors had AC that was off/too-high/broken. Fortune, https://fortune.com/2024/08/02/heatwave-deaths-expose-air-conditioning-crisis-elderly-and-minorities-most-at-risk/ ; Center for American Progress, https://www.americanprogress.org/article/protecting-older-adults-from-the-growing-threats-of-extreme-heat/ ; public-housing indoor-temperature study, https://www.ncbi.nlm.nih.gov/pmc/articles/PMC6651653/
[^gaps]: US regulatory PM2.5 network is sparse; under the 2024 standard ~44% of exceeding urban areas (~20M people) go undetected, ~2.8M live in uncaptured hotspots. ACS ES&T Letters, https://pubs.acs.org/doi/10.1021/acs.estlett.4c00605 ; ACS press, https://www.acs.org/pressroom/presspacs/2024/october/us-air-pollution-monitoring-network-has-gaps-in-coverage-say-researchers.html
[^monitor-equity]: Nearest regulatory monitor avg ~18.8 km (urban) / ~51.9 km (rural); hotspots skew higher-POC/low-SES; low-cost sensors skew to higher-income, whiter areas. https://pmc.ncbi.nlm.nih.gov/articles/PMC12329718/ ; https://pmc.ncbi.nlm.nih.gov/articles/PMC10499371/
[^barkjohn]: Barkjohn, Gantt & Clements (2021), *AMT* 14:4617 — US-wide PurpleAir correction with an RH term cuts PM2.5 RMSE ~8 → ~3 µg/m³ (≈12,000 24-h pairs, 16 states). https://amt.copernicus.org/articles/14/4617/2021/ ; EPA/PMC, https://pmc.ncbi.nlm.nih.gov/articles/PMC8422884/
[^drift]: Low-cost sensors drift; periodic re-evaluation/recalibration is needed. Long-term network eval, https://www.sciencedirect.com/science/article/pii/S0048969721058757 ; NYC mesonet network-calibration, https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12797186/ ; community-network data discontinuity (npj Clim Atmos Sci), https://www.nature.com/articles/s41612-025-01216-4 *(repo POSITIONING)*
[^epa-nonreg]: EPA — corrected low-cost sensor data is a non-regulatory tier that complements, not replaces, reference monitors. https://www.epa.gov/air-sensor-toolbox/quality-assurance-air-sensors *(repo POSITIONING)*
[^airnow]: EPA applies the US-wide correction to PurpleAir on the AirNow Fire & Smoke Map, displayed alongside regulatory data. https://www.epa.gov/air-sensor-toolbox/technical-approaches-sensor-data-airnow-fire-and-smoke-map
[^who]: WHO 2021 Global Air Quality Guidelines — PM2.5 annual 5 µg/m³, 24-h 15 µg/m³. IQAir, https://www.iqair.com/us/newsroom/2021-who-air-quality-guidelines ; review, https://pmc.ncbi.nlm.nih.gov/articles/PMC8553929/
[^naaqs]: EPA 2024 — primary annual PM2.5 NAAQS lowered 12.0 → 9.0 µg/m³; AQI revised. https://www.epa.gov/pm-pollution/final-reconsideration-national-ambient-air-quality-standards-particulate-matter-pm ; overview, https://www.epa.gov/system/files/documents/2024-02/pm-naaqs-overview.pdf
[^compound]: Compound heat + PM2.5: coexposure mortality ~3× either alone (Rahman et al., *AJRCCM* 2022), https://www.atsjournals.org/doi/10.1164/rccm.202204-0657OC ; USC/Keck summary (deaths 21% more likely; CVD +29.9%, resp +38%; 75+ +36.2%), https://keck.usc.edu/news/risk-of-death-surges-when-extreme-heat-and-air-pollution-coincide/ ; WRI, https://www.wri.org/insights/extreme-heat-air-pollution
[^cdc-heatrisk]: CDC pairs HeatRisk with the Air Quality Index for clinical/public guidance. https://www.cdc.gov/heat-health/hcp/clinical-guidance/how-to-use-the-heatrisk-tool-and-air-quality-index.html *(repo POSITIONING)*
[^imperial]: Imperial County (IVAN / Comité Cívico del Valle) community-owned network; equipment-ownership transfer to the community is the documented survival factor. IVAN, https://ivan-imperial.org/about ; performance study, https://pmc.ncbi.nlm.nih.gov/articles/PMC7309036/ ; durability, https://www.ncbi.nlm.nih.gov/pmc/articles/PMC7037815/ *(repo POSITIONING)*
[^aot]: Array of Things (Chicago) wound down — ~$2,500/node too costly to scale, nodes outlived design life; a successor Microsoft bus-shelter network ended in <2 years. MIT Tech Review, https://www.technologyreview.com/2022/08/19/1057848/array-of-things-goes-global/ ; Chicago Sun-Times, https://chicago.suntimes.com/environment/2025/09/11/chicago-air-pollution-monitor-sensors-public-health-environmental-justice
[^openaq]: OpenAQ aggregates and harmonises open AQ data (FAIR); reference monitors since 2015, air sensors since 2021; 2B+ points across 134 countries (Sep 2025). https://openaq.org/about/ ; data platform, https://openaq.org/about/initiatives/openaq-data-platform/
[^trust]: EPA-convened experts tie sensor-data uncertainty to public distrust; publishing uncertainty + QC flags is the documented antidote. https://pubs.acs.org/doi/10.1021/acsestair.4c00125 *(repo POSITIONING)*
[^propublica]: ProPublica built its own neighborhood toxic-air analysis because official data couldn't answer the question. https://www.propublica.org/article/whats-polluting-the-air-not-even-the-epa-can-say *(repo POSITIONING)*
[^research-qa]: Low-cost sensor data is held back for lacking calibration/QA/traceability; the field wants raw + processed data with machine-readable (FAIR) provenance. https://pmc.ncbi.nlm.nih.gov/articles/PMC11534011/ ; https://www.openaire.eu/how-to-make-your-data-fair *(repo POSITIONING)*
[^a11y-dataviz]: Accessible data viz: provide a screen-reader data-table equivalent for every non-trivial chart, never colour alone, add a plain-text summary. USWDS, https://designsystem.digital.gov/components/data-visualizations/ ; TPGi, https://www.tpgi.com/making-data-visualizations-accessible/
[^lep]: Language access for LEP residents is a health-equity and civil-rights obligation (EO 13166, Title VI), sharpest in climate disasters. EPA LEP, https://www.epa.gov/lep ; Just Solutions, https://justsolutionscollective.org/language-justice-in-climate-disasters-state-models-addressing-title-vi-gaps/ ; SEHN, https://www.sehn.org/sehn/2024/7/22/let-me-say-my-word-let-me-understand-yours-language-access-and-translation-for-socio-environmental-justice
[^ada]: DOJ 2024 ADA Title II rule makes WCAG 2.1 AA load-bearing for state/local government web content. *(repo POSITIONING / ROADMAP Phase 5.4)*
[^capa]: CAPA Strategies / NOAA NIHHIS Heat Watch — a one-day-a-year volunteer car traverse, temperature only. https://www.capastrategies.com/heat-watch ; https://www.heat.gov/ *(repo POSITIONING)*
