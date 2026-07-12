# Positioning: where swelter is useful and unique

What swelter is for in a crowded field, who needs it, what to claim, what not to claim, and how a
free, community-owned instance sustains itself. This is a strategy note, not a spec; the README is
the source of truth and the hard rules in it bind everything here.

Author: Chelsea Kelly-Reif. Year: 2026.

This note is built from a 2026 scan of the competitive, funding, and demand landscape. External
facts carry citations inline; the volatile ones (federal funding status especially) carry a recheck
cadence at the foot of the file. Treat the market claims as dated, not permanent.

## The position, in one sentence

swelter is the open, community-owned **trust layer** for neighborhood heat-and-air exposure: every
reading is calibrated against a reference monitor, labeled with its uncertainty and calibration
state, snapped to a privacy grid, served through open standards, and the collective keeps it.

**The headline capability underneath that sentence is that a community can run it themselves.**
Copy `network.yaml`, register your nodes, your reference monitor, and your co-location windows, and
`ADD-YOUR-NEIGHBORHOOD.md` walks a non-specialist through a working instance — dashboard, API, and
exports — in an afternoon with no hardware at all (real sensors take longer). There is no account,
no hosted service, and no vendor to switch off: the whole thing runs on a Raspberry-Pi-class host and
scales to zero when it is quiet. This is what turns "trust layer" from a feature claim into a
survival claim — see the funding-path evidence below (local ownership is the one factor that has
been shown to outlast a grant cycle) and ADR 0021.

The uniqueness is not any single feature — it is the **set**. In the scan, every comparable tool
held one to three of the properties below; none held all of them.

| Property | PurpleAir | OpenAQ | AirNow Fire & Smoke | Clarity | IQAir | CAPA Heat Watch | swelter |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Continuous (not one day a year) | yes | yes | yes | yes | yes | no (one day) | yes |
| Heat **and** air as published surfaces | partial | partial | no | no | no | heat only | yes |
| Per-node calibration **with published uncertainty** | no | no (pass-through) | corrected, hidden | yes (closed) | yes (opaque) | n/a | yes |
| CC0 / no-account export | no (restricted licence) | CC BY + registration | government | no | no | reports only | yes |
| Open-standard egress (OGC SensorThings) | no | no | no | no | no | no | yes |
| Community-owned governance | no | no | no | no | no | vendor-run | yes |
| Merge-gated WCAG 2.2 AA, bilingual, map = table = list | no | no | partial | no | no | no | yes |
| Self-hostable: copy one config file, run your own instance, no vendor | no (proprietary devices) | no (hosted platform) | no (federal service) | no (hosted SaaS) | no (hosted SaaS) | no (vendor-run campaign) | yes |

"partial" on heat: PurpleAir and OpenAQ carry temperature and humidity but do not publish a
calibrated heat surface. "partial" on accessibility: AirNow has a list view and does not use colour
alone for AQI, so accessible elements exist there; the full gated, bilingual, three-equal-views
package was not found elsewhere.

## What to claim — and what to stop claiming

Claim discipline is itself a differentiator: the field's credibility problem is overstatement. Say
only what holds.

**Say:**

- Heat is treated as a calibrated, first-class published surface (heat index), not an uncorrected
  byproduct.
- Every reading names its calibration version and carries a 1-sigma uncertainty (`residual_std`);
  calibrated and raw are never silently mixed; uncalibrated nodes are shown provisional.
- Data is CC0 and exportable with no account through CSV, JSON, the OGC SensorThings subset, and a
  copyable Datasette-openable store.
- The hosting collective owns siting, location precision, and governance; there is no hosted
  dependency to switch off.
- Any community can register its own network by copying `network.yaml` — a working demo instance
  (dashboard, API, exports) stands up in an afternoon with no hardware; going live with real sensors
  takes longer, because co-location and siting take real time (`ADD-YOUR-NEIGHBORHOOD.md`).
- The dashboard meets WCAG 2.2 AA as a merge gate, in English and Spanish, with map, table, and list
  as three equal views.

**Do not say:**

- **"swelter uniquely measures heat."** False. PurpleAir and OpenAQ carry temperature; NOAA/NIHHIS
  via CAPA maps neighborhood heat.[^capa] Reframe to "heat as a calibrated, first-class surface."
- **"Humidity-aware PM calibration is novel."** It is the EPA US-wide standard (Barkjohn et al.
  2021): the correction cuts PurpleAir PM2.5 RMSE from ~8 to ~3 µg/m³ and needs a humidity term.[^barkjohn]
  swelter follows it; the edge is the per-node fit plus the exposed per-reading uncertainty that
  AirNow and IQAir do not surface.[^airnow]
- **"Competitors own your data" (re: Clarity).** Clarity lets cities retain ownership. The honest
  contrast is no account, no hosted dependency, CC0 — not data capture.[^clarity]
- **"Regulatory-grade."** EPA is explicit that corrected low-cost data is non-regulatory and
  complements, not replaces, reference monitors.[^epa-nonreg] Claim "credible and auditable."
- **Absence as proof.** The SensorThings and full-WCAG-AA uniqueness rest on not finding a
  competitor that does them. State it that way, not as "no one does."

## Who needs it (demand is real and specific)

- **Frontline orgs & residents.** Collectives already buy their way to this: WE ACT runs 18 QuantAQ
  monitors across Northern Manhattan to "democratize air quality data";[^weact] Boston's Common
  SENSES runs 70+ community-sited heat-and-air-and-noise sensors.[^commonsenses] swelter is the open,
  low-cost, no-vendor path to the same end. (Common SENSES is the closest analog and is
  university- and city-backed — swelter's answer is replicable, framework-free, no institution
  required.)
- **Municipal & public health.** Chief Heat Officers (Miami-Dade 2021, then Los Angeles and others)
  deploy resources off neighborhood heat-vulnerability maps;[^cho] heat-action-plan reviews name a
  gap between identifying vulnerable people and reaching them.[^hap] swelter's gridded heat-index
  surface fits, and CDC pairs HeatRisk with AQI, validating the heat-and-air pairing.[^cdc] For a
  public-entity partner specifically, the merge-gated WCAG 2.2 AA + bilingual posture above is also
  a DOJ ADA Title II compliance asset — see
  [`AGENCY-COMPLIANCE-PACK.md`](AGENCY-COMPLIANCE-PACK.md) (ROADMAP Phase 5.4).
- **Researchers & academia.** Low-cost sensor data is widely held back for lacking calibration, QA,
  and traceability;[^research-qa] the field wants raw and processed data with machine-readable
  provenance.[^fair] swelter's append-only raw log, rebuildable calibrated records, versioned
  calibration ids, and uncertainty field answer this directly.
- **Journalists & advocacy.** ProPublica built its own neighborhood toxic-air analysis because
  official data could not answer the question, and newsrooms reused it;[^propublica] census-tract
  data is often too coarse to show pollution inequity.[^edf] swelter's open, exportable, auditable
  surface is reuse-ready.

## The sharpest real wedges

- **Continuous vs. one day.** The funded incumbent for neighborhood heat — NOAA/NIHHIS delivered by
  the sole vendor CAPA Strategies — is a one-day-a-year, temperature-only volunteer car traverse
  producing a modeled snapshot.[^capa] swelter is standing, community-owned, continuous
  infrastructure. Honest caveat: CAPA's mobile traverse beats a fixed grid on single-snapshot spatial
  resolution; swelter wins on **time and ownership**, not snapshot density.
- **Compound exposure is the health story.** CDC reads heat and AQI together;[^cdc] joint heat and
  PM2.5 exposure carries materially higher mortality than either alone.[^compound] Few tools publish
  both. This is opportunity and unproven-market risk at once — see ADR 0009.
- **Uncertainty prevents trust collapse.** EPA-convened experts tie sensor-data uncertainty to
  "distrust of data … loss of public confidence."[^trust] Publishing uncertainty and QC flags is the
  documented antidote, and is swelter's quiet moat.
- **Survival = local ownership.** The one community air network that outlived its grant (Imperial
  County) did so because equipment ownership transferred to the community.[^imperial] swelter's hard
  rules encode the empirically-supported durability factor.

## Funding path (order matters; the 2025 landscape shifted)

1. **Philanthropy first.** The federal environmental-justice pipeline that fit swelter best — EPA
   Thriving Communities Grantmaking, Community Change Grants, and the ARP/IRA enhanced air-monitoring
   grants ($53.4M to 132 projects in 2022) — was largely terminated or rescinded in 2025 and is in
   active litigation.[^epa-ej][^ira] Treat those as **proof of demand, not live funding**. Target
   instead Kresge's Climate Change, Health & Equity initiative[^kresge] and RWJF's Local Data for
   Equitable Communities[^rwjf] — both fund community nonprofits using local data for action and
   reward community ownership, data sovereignty, and post-grant sustainability.
2. **Research co-applicant.** NIEHS (as the open-data instrument inside a community-engaged research
   center; it prefers community-based participatory research)[^niehs] and NSF CIVIC, Track A,
   climate and environmental instability (needs a university plus community partner).[^civic]
3. **Indirect public health.** CDC BRACE / Climate-Ready States & Cities, via a state or local
   health-department grantee.[^brace]
4. **The honest weak spot** is grant-management track record, not the tool. Pair with a fiscal
   sponsor or an established community org as lead applicant. swelter's governance model (the
   collective owns siting, precision, and decisions) is the community-ownership evidence reviewers
   reward — surface it.

## Risks and failure modes to design against

- **Drift and maintenance death-spiral** — the dominant decay mechanism for these networks.[^drift]
  swelter's QC (drift / flatline / spike / gap, `node_health`) and low-maintenance, single-dependency
  design hedge it, but a **named local steward** is still required.
- **Equity-washing** — sensors in frontline neighborhoods can worsen information disparities if the
  data is not calibrated.[^equity] The calibration layer is what makes siting credible, not
  decorative.
- **Privacy grid vs. block-level demand** — journalists push toward block resolution[^edf] while
  swelter snaps to ~150 m. Defend the trade-off explicitly: block-level **signal** without
  porch-level **coordinates** (ADR 0003).
- **Institutional analogs exist** (Common SENSES; the wound-down Array of Things) — lead with
  framework-free, replicable, no-vendor.

## Verify before publishing externally

The scan flagged these as not directly confirmed against a primary page; check them before putting a
number or a hard negative in public material:

- CAPA Heat Watch's average campaign cost (~$19.5k), community count ("80+"), and program age, and
  whether CAPA's *raw* data (vs. its public reports) is closed.
- The current operational status of Array of Things.
- The SensorThings and full-WCAG-AA "no competitor does this" claims — phrase as "we did not find
  one."
- Each federal funding program's litigation and appropriations status at application time.

## Sources

[^capa]: CAPA Strategies Heat Watch / NOAA NIHHIS — https://www.capastrategies.com/heat-watch ; https://www.heat.gov/
[^barkjohn]: Barkjohn et al. 2021, US-wide PurpleAir correction — https://amt.copernicus.org/articles/14/4617/2021/
[^airnow]: EPA technical approaches, AirNow Fire and Smoke Map — https://www.epa.gov/air-sensor-toolbox/technical-approaches-sensor-data-airnow-fire-and-smoke-map
[^clarity]: Clarity Movement — https://www.clarity.io/
[^epa-nonreg]: EPA, quality assurance for air sensors (non-regulatory tier) — https://www.epa.gov/air-sensor-toolbox/quality-assurance-air-sensors
[^weact]: WE ACT Community Air Monitoring — https://weact.org/programs/air-quality-monitoring/
[^commonsenses]: Common SENSES (Boston) — https://www.commonsensesproject.org
[^cho]: LA Chief Heat Officer expands cooling centers — https://www.esri.com/about/newsroom/blog/los-angeles-chief-heat-officer-expands-cooling-centers
[^hap]: Review of US heat action plans — https://pmc.ncbi.nlm.nih.gov/articles/PMC10088943/
[^cdc]: CDC, HeatRisk and the Air Quality Index — https://www.cdc.gov/heat-health/hcp/clinical-guidance/how-to-use-the-heatrisk-tool-and-air-quality-index.html
[^research-qa]: QA considerations for credible low-cost sensor data (ACS ES&T Air) — https://pmc.ncbi.nlm.nih.gov/articles/PMC11534011/
[^fair]: Making data FAIR — https://www.openaire.eu/how-to-make-your-data-fair
[^propublica]: ProPublica, "What's Polluting the Air? Not Even the EPA Can Say" — https://www.propublica.org/article/whats-polluting-the-air-not-even-the-epa-can-say
[^edf]: EDF, investigating air-pollution inequity at the neighborhood scale — https://blogs.edf.org/global-clean-air/2022/11/16/investigating-air-pollution-inequity-at-the-neighborhood-scale/
[^compound]: Compound extreme-heat and air-pollution events — https://www.ou.edu/news/articles/2025/september/extreme-heat-air-pollution-compound-events-increasing
[^trust]: EPA-convened experts on sensor-data uncertainty and trust — https://pubs.acs.org/doi/10.1021/acsestair.4c00125
[^imperial]: Imperial County Community Air Monitoring Network — https://www.ncbi.nlm.nih.gov/pmc/articles/PMC7037815/
[^epa-ej]: EPA EJ grant terminations and litigation (2025) — https://earthjustice.org/press/2025/nonprofits-tribes-and-local-governments-sue-trump-administration-for-terminating-epa-grant-programs
[^ira]: IRA Section 60201 environmental and climate justice block grants tracker — https://iratracker.org/programs/ira-section-60201-environmental-and-climate-justice-block-grants/
[^kresge]: Kresge Climate Change, Health & Equity initiative — https://kresge.org/news-views/kresge-launches-next-phase-of-climate-change-health-equity-initiative-with-18-6m-investment/
[^rwjf]: RWJF grants — https://www.rwjf.org/en/grants.html
[^niehs]: NIEHS Climate Change and Health Initiative — https://www.niehs.nih.gov/news/factor/2025/1/science-highlights/climate-change-health-report
[^civic]: NSF Civic Innovation Challenge — https://www.nsf.gov/funding/opportunities/civic-civic-innovation-challenge/505728/nsf24-534
[^brace]: CDC Climate-Ready States & Cities Initiative — https://www.cdc.gov/climate-health/php/climate_ready/index.html
[^drift]: Community sensor networks, drift and data discontinuity — https://www.nature.com/articles/s41612-025-01216-4
[^equity]: Low-cost networks can reduce or worsen information disparities — https://pmc.ncbi.nlm.nih.gov/articles/PMC10329730/

Last verified: 2026-06-18. Recheck cadence: federal funding status (the philanthropy-first ordering
and the EPA/IRA rows) is volatile under 2025–2026 litigation — recheck quarterly and before any
proposal. Recheck the competitive table and the demand examples at least annually, and whenever a
named tool changes its data licence or adds a heat surface.
