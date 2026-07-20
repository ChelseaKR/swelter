# Funder & partner evidence pack

A one-page case a fiscal sponsor, community-based organization, or grant reviewer can read in a
sitting: what swelter is, the need it answers, the evidence that its design survives, and how a
funder's money turns into durable, community-owned infrastructure. It assembles evidence that is
already cited elsewhere in this repo — it adds no new claims. Where a claim is volatile or unproven,
it says so.

This pack is **descriptive, not a pitch**: every external fact carries a source, the funding
landscape is dated, and the honest weak spots are stated rather than hidden. It complements
[`POSITIONING.md`](POSITIONING.md) (the strategy note) and the cited evidence in
[`RESEARCH-ROADMAP.md`](RESEARCH-ROADMAP.md); the claim-by-claim engineering verification map
(which CI job enforces which claim, and where a reviewer checks it) is
[`evidence-pack.md`](evidence-pack.md). The README is the source of truth and its hard rules
bind everything here.

Author: Chelsea Kelly-Reif, 2026. swelter is an independent personal open-source project,
unaffiliated with any employer or client; see [`../NOTICE`](../NOTICE).

Last verified: 2026-06-30. Recheck cadence: federal-funding status is volatile under 2025–2026
litigation — recheck quarterly and **before any proposal**. Recheck the demand examples annually.

---

## In one sentence

swelter is an open, community-operated **trust layer** for neighborhood heat-and-air exposure: every
reading states its source and calibration/QC state, calibrated values carry evidenced uncertainty,
uncalibrated readings stay provisional, public locations use the privacy policy, and open interfaces
keep the record portable. Any community can run its own instance: copy one config file
([`network.yaml`](../network.yaml)), follow [`ADD-YOUR-NEIGHBORHOOD.md`](ADD-YOUR-NEIGHBORHOOD.md),
and the collective owns it outright — no account, no hosted service, nothing a funder or a vendor can
switch off later.

## The need (the stakes a funder is buying down)

- **Heat is the deadliest US weather hazard.** The CDC counted **2,394 heat-related deaths in 2024**
  (2,415 in 2023), themselves believed to be undercounts.[^heat][^undercount]
- **The official record is sparse and inequitably placed.** The nearest regulatory PM2.5 monitor
  averages ~18.8 km in urban areas; under the 2024 standard ~44% of exceeding urban areas (~20M
  people) go undetected, and low-cost sensors skew to higher-income, whiter areas.[^gap][^sensor-eq]
- **The burden lands unequally.** Formerly redlined neighborhoods run hotter today (mean ~2.6 °C, up
  to ~7 °C across 94% of 108 US areas); low-income / majority-POC blocks carry ~26% / ~38% less tree
  canopy.[^redline][^canopy]
- **Compound heat + air is the under-served health story.** Joint extreme-heat and PM2.5 exposure
  carries materially higher mortality than either alone, and the CDC reads HeatRisk with the AQI —
  few tools publish both.[^compound][^cdc]

A community map fills the gap — but a *wrong* map is worse than no map. That is the problem the
design below is built to avoid.

## Why this design survives (the durability case funders reward)

- **Local ownership is the empirically-supported survival factor.** The one community air network
  that outlived its grant — Imperial County / IVAN — did so because equipment ownership transferred
  to the community; vendor-run networks (Array of Things) wound down when cost and maintenance were
  not owned locally.[^imperial][^aot] swelter's hard rules **encode** community ownership: governance,
  siting, and location precision rest with the hosting collective, and there is no hosted dependency
  to switch off ([`governance.md`](governance.md), README hard rule 5).
- **Replication is not a roadmap promise, it is a working path.** A community stands up a working
  instance — dashboard, open API, exports — by copying `network.yaml` and following
  `ADD-YOUR-NEIGHBORHOOD.md`, with recorded demo data and no hardware, in an afternoon; real sensors
  and real co-location take longer. This is the concrete mechanism behind "local ownership": there is
  no code to write, no company in the loop, and the whole store is a copyable folder a departing
  funder's grant cannot strand.
- **Lean by design.** Two direct runtime dependencies (PyYAML and structlog); everything else is
  the Python standard
  library. It runs on a Raspberry-Pi-class host with no cloud at all — cheap to run and durable
  across lean years, hedging the maintenance death-spiral that decays these networks.[^drift]
- **Calibration is the credibility moat.** Nodes promoted to calibrated state are co-located against
  a reference monitor and receive an evidenced correction (humidity-aware PM follows the US-EPA
  PurpleAir lineage); the fit, window, and residual error are recorded and reproducible. Nodes without
  an applicable correction stay raw/provisional and do not borrow a 1-sigma claim.[^barkjohn]
  Corrected low-cost data is **non-regulatory** and complements, not replaces, reference monitors —
  and we say so.[^epa-nonreg]
- **The fairness commitment is observable, not asserted.** The two-tier-map risk is real: if
  calibrated nodes cluster in one part of the network and raw nodes in another, the map can recreate
  the very inequity it exposes. swelter surfaces the calibrated-vs-raw distribution per published
  cell — in `swelter qc` and `/api/health.json` — so an under-calibrated block is visible and the
  next co-location can be aimed at it (Responsible-tech audit B3; see
  [`RESPONSIBLE-TECH-AUDITS.md`](RESPONSIBLE-TECH-AUDITS.md)). This is descriptive coverage of
  calibration, **not** a ranking of neighborhoods; correlating a coverage gap with frontline blocks
  needs demographic context swelter does not hold, and is a governance judgment.

## Who needs it (demand is real and specific)

- **Frontline orgs & residents** already buy their way to this: WE ACT runs 18 monitors across
  Northern Manhattan; Boston's Common SENSES runs 70+ community-sited sensors.[^weact][^commonsenses]
  swelter is the open, low-cost, no-vendor path to the same end.
- **Municipal & public health** deploy off neighborhood heat-vulnerability maps (Chief Heat Officers
  in Miami-Dade, Los Angeles, and others); swelter's gridded heat-index surface fits.[^cho]
- **Researchers & journalists** hold low-cost data back for missing calibration, QA, and FAIR
  provenance; ProPublica built its own analysis because official data could not answer the
  question. swelter's append-only raw log, rebuildable calibrated records, versioned calibration ids,
  and uncertainty field answer this directly.[^research-qa][^propublica]

## The funding path (order matters; the 2025 landscape shifted)

1. **Philanthropy first.** The federal environmental-justice pipeline that fit swelter best (EPA
   Thriving Communities / Community Change Grants; ARP/IRA air-monitoring grants — $53.4M to 132
   projects in 2022) was largely terminated or rescinded in 2025 and is in active litigation. Treat
   it as **proof of demand, not live funding.**[^epa-ej][^ira] Target instead Kresge's Climate Change,
   Health & Equity initiative and RWJF's local-data-for-equity work — both fund community nonprofits
   using local data for action and reward community ownership and post-grant sustainability.[^kresge][^rwjf]
2. **Research co-applicant.** NIEHS (as the open-data instrument inside a community-engaged research
   center) and NSF CIVIC Track A (university plus community partner).[^niehs][^civic]
3. **Indirect public health.** CDC BRACE / Climate-Ready States & Cities, via a state or local
   health-department grantee.[^brace]

## What we are asking for, and what a funder gets

- **Ask:** seed support for hardware, a named local steward, and co-location time at a reference
  monitor (the scarce resource that decides who gets calibrated).
- **Get:** standing, community-operated heat-and-air infrastructure that the collective can run from
  a copied config file; no-account, source-aware exports; calibrated values with evidenced uncertainty
  and visibly provisional raw values; and an English/Spanish dashboard targeting WCAG 2.2 AA with
  automated gates and equivalent map/table/list outcomes. Current manual assistive-technology and
  independent Spanish signoff is tracked in issue #106. The collective can keep/fork the code and
  store without depending on a swelter-hosted account.

## Honest limits (stated so they cannot be glossed)

- **The weak spot is grant-management track record, not the tool.** Pair swelter with a fiscal
  sponsor or an established community org as lead applicant.[^positioning]
- **Demand for *this implementation* is unverified.** The persona panel in
  [`USER-RESEARCH.md`](USER-RESEARCH.md) is synthetic — a hypothesis generator, not evidence that a
  real funder, official, researcher, or resident has asked for this. Validate with real partners
  before building beyond the cheapest copy.
- **Non-regulatory tier.** Corrected low-cost data is credible and auditable, not regulatory-grade,
  and swelter says so on every surface.[^epa-nonreg]
- **Uniqueness claims are "we did not find one," not "no one does."** The open-standard egress and
  full-gated-WCAG-AA "no competitor does this" claims rest on a 2026 scan, not exhaustive
  proof.[^positioning]

## Sources

[^heat]: USAFacts / CDC+NOAA, US extreme-heat deaths — https://usafacts.org/articles/how-many-people-die-from-extreme-heat-in-the-us/
[^undercount]: Washington Post, heat-death undercount — https://www.washingtonpost.com/climate-environment/2024/07/01/extreme-heat-deaths-heatwave-heatstroke/
[^gap]: ACS ES&T Letters, US PM2.5 monitoring gaps — https://pubs.acs.org/doi/10.1021/acs.estlett.4c00605
[^sensor-eq]: Low-cost sensor placement & injustice — https://pmc.ncbi.nlm.nih.gov/articles/PMC10499371/
[^redline]: Hoffman et al. 2020, redlining and urban heat (Virginia Mercury) — https://virginiamercury.com/briefs/there-may-be-a-link-between-urban-heat-islands-and-past-redlining-practices-study-finds/
[^canopy]: American Forests, tree-equity canopy gap — https://www.americanforests.org/article/the-need-for-tree-equity-is-heating-up/
[^compound]: Compound extreme-heat and air-pollution mortality — https://www.atsjournals.org/doi/10.1164/rccm.202204-0657OC
[^cdc]: CDC, HeatRisk and the Air Quality Index — https://www.cdc.gov/heat-health/hcp/clinical-guidance/how-to-use-the-heatrisk-tool-and-air-quality-index.html
[^imperial]: Imperial County Community Air Monitoring Network durability — https://www.ncbi.nlm.nih.gov/pmc/articles/PMC7037815/
[^aot]: Array of Things wind-down — https://www.technologyreview.com/2022/08/19/1057848/array-of-things-goes-global/
[^drift]: Community sensor networks, drift and data discontinuity — https://www.nature.com/articles/s41612-025-01216-4
[^barkjohn]: Barkjohn et al. 2021, US-wide PurpleAir correction — https://amt.copernicus.org/articles/14/4617/2021/
[^epa-nonreg]: EPA, quality assurance for air sensors (non-regulatory tier) — https://www.epa.gov/air-sensor-toolbox/quality-assurance-air-sensors
[^weact]: WE ACT Community Air Monitoring — https://weact.org/programs/air-quality-monitoring/
[^commonsenses]: Common SENSES (Boston) — https://www.commonsensesproject.org
[^cho]: LA Chief Heat Officer expands cooling centers — https://www.esri.com/about/newsroom/blog/los-angeles-chief-heat-officer-expands-cooling-centers
[^research-qa]: QA considerations for credible low-cost sensor data — https://pmc.ncbi.nlm.nih.gov/articles/PMC11534011/
[^propublica]: ProPublica, "What's Polluting the Air? Not Even the EPA Can Say" — https://www.propublica.org/article/whats-polluting-the-air-not-even-the-epa-can-say
[^epa-ej]: EPA EJ grant terminations and litigation (2025) — https://earthjustice.org/press/2025/nonprofits-tribes-and-local-governments-sue-trump-administration-for-terminating-epa-grant-programs
[^ira]: IRA Section 60201 environmental and climate justice block grants tracker — https://iratracker.org/programs/ira-section-60201-environmental-and-climate-justice-block-grants/
[^kresge]: Kresge Climate Change, Health & Equity initiative — https://kresge.org/news-views/kresge-launches-next-phase-of-climate-change-health-equity-initiative-with-18-6m-investment/
[^rwjf]: RWJF grants — https://www.rwjf.org/en/grants.html
[^niehs]: NIEHS Climate Change and Health Initiative — https://www.niehs.nih.gov/news/factor/2025/1/science-highlights/climate-change-health-report
[^civic]: NSF Civic Innovation Challenge — https://www.nsf.gov/funding/opportunities/civic-civic-innovation-challenge/505728/nsf24-534
[^brace]: CDC Climate-Ready States & Cities Initiative — https://www.cdc.gov/climate-health/php/climate_ready/index.html
[^positioning]: swelter positioning note, competitive scan and claim discipline — [`POSITIONING.md`](POSITIONING.md)
