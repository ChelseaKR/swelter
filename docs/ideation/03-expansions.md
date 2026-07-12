# Expansions (EXP-01 … EXP-15)

Date: 2026-07-01. Three horizons: **H1** deepen the core, **H2** adjacent capabilities/audiences/
integrations, **H3** transformative bets. Net-new relative to `docs/ROADMAP.md` Phase 5 and
`docs/RESEARCH-ROADMAP.md` E1–E12; where an idea extends an existing ID it says exactly how.
Effort tiers as in `02-large-scale-fixes.md`. None of these weaken a hard rule.

---

## H1 — Deepen the core

### EXP-01 — The accumulating archive: make the live demo longitudinal

**Pitch.** Stop deleting the store on every fetch (`cli.cmd_fetch` unlinks `observations.db` each
run) — accumulate the daily Pages fetches into a persistent, idempotent archive so the time slider
covers weeks and the heat-island story becomes visible over a season.

**Impact.** Transforms the demo from a snapshot into the actual product promise: block-scale
exposure *over time*. Researchers/journalists (E-group personas) get a real series; the compound-
exposure surface (ADR 0009) becomes historically queryable. The store key
`(node_id, timestamp, parameter, calibration)` with `INSERT OR IGNORE` was built for exactly this
and is currently unused for it.

**Shape.** `swelter fetch --accumulate`: open, don't unlink; persist the store between CI runs
(GitHub Actions cache or a data branch — decide in an ADR; mind repo-size limits with FIX-09's
monthly archive files); reconcile `network.yaml` merging for nodes that come and go; slider bounds
from the store, not from one fetch. Depends on FIX-09 for growth and FIX-05 for honest licensing of
the accumulated third-party data.

**Effort.** M (L with the CI persistence design). **Risks.** Source terms-of-use for retention/
republication (real-data gate); Pages artifact size (cap the baked sample — `_write_web_sample`
already caps cells; extend to serve sliced history via static files).

**Excellent.** The public demo shows "this June vs last June" for a California cell; re-running a
fetch twice adds zero rows; archive growth rate is documented and bounded.

### EXP-02 — Reference-monitor feed adapter: co-location pairs on tap

**Pitch.** A fourth source adapter that pulls the *reference* side (AirNow/AQS regulatory
monitors) so co-location training pairs are assembled automatically from overlapping timestamps
instead of hand-built `colocation.jsonl`.

**Impact.** Today calibration evidence is manually curated; this makes re-calibration (the drift
answer, FIX-03) an operational loop instead of a project. Complements research-roadmap E4, which
handles the *no-local-reference* case; this is the automation for networks that *have* one —
together they cover the whole reference landscape.

**Shape.** `sources/airnow.py` over the shared `_http.py`; `swelter colocate --node X --monitor Y
--window …` emits `TrainingPair`s (`calibrate.read_colocation` format) from stored raw node data +
fetched reference series; provenance (monitor AQS id) flows into `Correction.reference` — the
field already exists (`config.ReferenceMonitor.source` names the pattern). Continuous mode feeds
FIX-03's drift surveillance.

**Effort.** L. **Risks.** AirNow API terms and keying (real-data gate); timestamp alignment
subtleties (hourly reference vs 5-min node cadence) need documented resampling rules — SME
sanity check on the pairing methodology.

**Excellent.** A steward runs one command after placing a node beside a monitor and gets a
registry-ready correction with committed evidence; the demo gains a recorded real co-location
worked example.

### EXP-03 — Sensor-model-aware calibration families

**Status.** ✅ Implemented 2026-07-03 (branch `roadmap/exp-03-sensor-model-aware-calibration-fa`) —
`NodeConfig.sensor_model` (rejects serial-number-like values, hard rule #1); `calibrate._MODEL_PREDICTORS`/
`_MODEL_METHOD` keyed by (parameter, model) with fallback to parameter, then default; `Correction.model`
serialized only when non-empty (demo registry rebuilds byte-for-byte); `sensor_community.py` now maps
its known sensor type onto `sensor_model` instead of discarding it; per-model bias section in
`docs/calibration.md` states plainly that a model-typical prior is never calibration and never promotes
a node past provisional. See `docs/decisions/0017-sensor-model-calibration-families.md`.

**Pitch.** Teach the pipeline what hardware produced a reading: an optional, public-safe
`sensor_model` in `network.yaml` nodes, and per-model correction lineages (PMS5003 vs SDS011 vs
SPS30 have different humidity responses).

**Impact.** `calibrate._METHOD` keys corrections by parameter only; the EPA lineage the docs cite
is sensor-family-specific. Per-model defaults raise correction quality and let an uncalibrated
node borrow an honest *prior* label ("typical PMS5003 bias band") without ever being promoted past
provisional. Also fixes a latent adapter issue: `sensor_community.py` already knows sensor types
and discards them.

**Shape.** `NodeConfig.sensor_model` (public string, no serial numbers — hard rule 1 review);
`_METHOD`/`_PREDICTORS` keyed by (parameter, model) with fallback; registry entries record model;
`docs/calibration.md` gains a per-model bias section. No change to the raw/calibrated boundary.

**Effort.** M. **Risks.** Must not imply model-typical priors are calibration — labeling reviewed
against audit A1. Registry schema bump coordinates with FIX-03.

**Excellent.** Two co-located different-model sensors get visibly different fitted forms with the
right predictors each; the model string appears in the trust view lineage (ROADMAP 5.2).

### EXP-04 — `swelter publish`: the fully static instance

**Pitch.** Promote the bash choreography in `.github/workflows/pages.yml` into a tested first-class
command that emits a complete static site — sliced surface/history JSON, alerts feeds, exports,
licenses — so a community can host on any static host with *no server process at all*.

**Impact.** The cheapest possible sustainability story (ROADMAP 5.3's replication pitch gets an
even lower floor than scale-to-zero): a network whose read path is a folder on any free static
host. Also deletes the workflow-only logic that currently lives untested in YAML (the fallback
chain, `/sensors/` copying, DATA-LICENSE juggling — 40 lines of bash today).

**Shape.** `cli.cmd_publish`: compose the existing `_write_web_*` bakers plus per-window surface
slices (`surface-24h.json`, `surface-7d.json`), `export.csv`, license files (FIX-05), and a
`publish-manifest.json` (FIX-11); rewrite `pages.yml` to `swelter fetch … && swelter publish …`;
document the S3/CloudFront variant so `infra/cdk` serves the artifact instead of needing the
Lambda stub at all (retiring the `handler.py` drift seam for read-only deployments).

**Effort.** M. **Risks.** Static slicing must match live-API semantics (FIX-07's schema contract
is the guard); Datasette-Lite (WASM) linkage is a nice-to-have, keep optional.

**Excellent.** `swelter fetch && swelter publish && rsync` is a working instance; the Pages
workflow contains no logic that isn't also a tested CLI path.

### EXP-05 — The steward console: calibration age, service queue, co-location planner

**Status: done.** `swelter status --plan` (`--json` optional) ships in `src/swelter/steward.py` —
a pure, import-only `plan()` composing `qc.health_report`, `qc.coverage_equity`, and the
correction registry's window ages (FIX-03) into one ranked, evidence-cited `Action` list: offline
nodes rank above degraded nodes above expired-vs-expiring corrections above coverage gaps, and
coverage gaps are ordered strictly by ascending `calibrated_nodes` (never by neighborhood
characteristics — the `coverage_equity` note travels verbatim into each action's evidence). The
CLI (`cli.cmd_status`) prints the plan plain-language to stderr or as JSON, and always closes with
"The tool proposes; the collective disposes" (audit B4/B5). `web/steward.html` was scoped out of
this pass per the spec's own "optionally" — the CLI report is the core deliverable. See
`tests/test_steward.py` and `roadmap/exp-05-steward-console-calibration-age-s`.

**Pitch.** One operator surface (static page or rich CLI report) that turns existing signals —
`qc.health_report`, coverage-equity, FIX-03 correction ages, QC flag rates — into a prioritized
"what needs doing" list for the 2 a.m. steward.

**Impact.** The B-group personas run the network with raw JSON today (`/api/health.json`). A
service queue ("node-07 offline 49h; node-12 correction expires in 3 weeks; cell X still has no
calibrated node") operationalizes the audits' review-gated items (B3, B5) and makes local
ownership — the documented survival factor (**[commons]**) — cheaper to exercise.

**Shape.** `swelter status --plan` composing existing module outputs into ranked actions with
plain-language reasons; optionally a `web/steward.html` (same framework-free discipline, behind no
auth since it exposes only already-public data). Co-location planning (which cell next) stays
*descriptive* — ordering by coverage, never by neighborhood characteristics (audit B4 boundary,
same refusal `qc.coverage_equity` already encodes).

**Effort.** M. **Risks.** Recommendation framing must not become the silent optimizer audit B5
warns about — the tool proposes, the collective disposes, and the output says so.

**Excellent.** A new steward can run one command and know the three most useful physical actions
this week; every recommendation names its evidence.

### EXP-06 — Wet-bulb globe temperature as a first-class parameter

**Pitch.** Add `wbgt_c` to the `PARAMETERS` registry with an estimation method, calibration
support, and occupational-heat framing — the metric outdoor-work guidance actually uses.

**Impact.** The README's own hardware framing mentions a "wet-bulb-globe-style heat index," but
only `heat_index_c` exists in `models.py`. WBGT unlocks a concrete new audience — outdoor workers
and the organizations that watch out for them — adjacent to, not duplicating, E7's CDC
HeatRisk-style resident guidance layer.

**Shape.** `models.py` estimation (documented approximation from temp/humidity, honest about the
no-solar-radiometer limitation, labeled "estimated WBGT"); parameter registry + QC bounds +
`_SPIKE_THRESHOLD` entries; surface/table/list plumbing is parameter-generic already
(`aggregate.SURFACE_PARAMETERS` + one dashboard label set). Guidance thresholds only with sourced,
non-prescriptive copy per the R1 pattern and audit A6.

**Effort.** M. **Risks.** Estimated WBGT without a black-globe sensor has real error — publish the
method's documented bounds or don't ship the bands (SME gate on the guidance copy; the estimation
itself is publishable with citations). Firmware black-globe support is a separate hardware ADR.

**Excellent.** WBGT appears across map/table/list/API/export with its "estimated" caveat
inseparable (R5 discipline), and an occupational-health reviewer signs off on the wording.

---

## H2 — Adjacent capabilities, audiences, integrations

### EXP-07 — Descriptive context overlays: tree canopy and shade

**Pitch.** A second curated overlay in the `cooling_centers.py` mold: public-domain tree-canopy /
land-cover context per cell, strictly descriptive, so residents can *see* the canopy-heat
relationship the evidence base documents rather than being told a score.

**Impact.** The research basis (**[ej-distribution]**) cites canopy inequity as core to why heat
lands unequally; today the map shows readings with no context layer. For organizers (persona C3)
this is the visual argument for shade investment — made honestly, as two layers a viewer relates,
never a swelter-computed vulnerability ranking (the B4/coverage-equity refusal extended to
context data).

**Shape.** A `context_layers.py` module copying `cooling_centers.py`'s allowlist-validation
pattern (provenance, license, `last_verified` per feature); a canopy-percent property per cell
sourced from a public dataset chosen with care; dashboard toggle + table column with source line;
ADR defining the "descriptive context, no composite index" rule for all future overlays.

**Effort.** M. **Risks.** Dataset choice and framing need a CBO/equity review (gate) — the line
between "context" and "implied ranking" is the whole design problem here. Data licensing check.

**Excellent.** A resident can toggle canopy context and the UI never says or implies "this
neighborhood scores worse"; the overlay module rejects any dataset field outside its allowlist.

### EXP-08 — Siting what-if: coverage simulation for governance decisions

**Pitch.** `swelter plan --add-node lat,lon` — show what a candidate node or co-location slot does
to coverage (new cells, redundancy, distance-to-reference) before hardware moves.

**Impact.** Co-location time is the scarce resource the audits call a governance decision (B5);
this gives the collective a *what-if* instrument for it. Also serves ADD-YOUR-NEIGHBORHOOD
adopters sizing their first buy.

**Shape.** Pure-function simulation over `NetworkConfig` (+`snap_to_grid`): candidate → published
cell, cell-coverage delta, nearest reference monitor distance for future co-location; text + JSON
output; zero new data collection. Optional dashboard "planning" mode fed by a static JSON.

**Effort.** S/M. **Risks.** Keep outputs descriptive (cells, distances) — no exposure-weighted
"optimal placement" scoring without governance framing (same boundary as EXP-05).

**Excellent.** A collective meeting can compare three siting options in minutes with printouts;
the tool's numbers are reproducible from config alone.

### EXP-09 — The sensor-twin tier: precision cross-checks without a reference

**Pitch.** A documented middle trust tier — "cross-checked" — from co-locating two *low-cost*
nodes: bounds precision (inter-sensor agreement), never accuracy, for networks still waiting on a
reference monitor.

**Impact.** The monitoring-gap evidence says frontline networks often have no reference access;
E4 (transfer calibration) is the full answer and is L-effort with the highest scientific risk in
the backlog. This is the humbler, faster sibling: it claims *only* what twin agreement can
support, giving stewards a drift smoke-alarm ("these twins diverged 40% this month") and honest
language between raw and calibrated.

**Shape.** A `twin_windows:` config block; a `qc`-side agreement statistic (paired residual spread
over a window) surfaced in health reports; a new observation *annotation* (not a calibration
version — the value stays RAW; hard rule 3 untouched, the tier lives in QC/health metadata and
dashboard copy). Explicit docs: cross-checked ≠ calibrated, with the EPA non-regulatory framing.

**Effort.** M. **Risks.** Naming/semantics need an SME pass so the tier can't be read as accuracy
(gate); interaction with FIX-02's corroboration logic should share code.

**Excellent.** A no-reference network can say "our twins agree within ±X" with the math public,
and no surface anywhere promotes a cross-checked value past provisional.

### EXP-10 — Event chronicles: the heat-wave post-mortem generator

**Pitch.** After an event window, generate a citable chronicle: hours over Danger per cell,
compound-exposure hours, coverage confidence, and — first-class — what the network *couldn't* see
(gaps, provisional shares), as HTML/Markdown with the FIX-13 digest for citability.

**Impact.** Officials and health departments (personas C1/C2) act on events, not dashboards.
Research-roadmap E1 is the resident-facing monthly brief; this is the institution-facing,
event-scoped analytic — different audience, different rigor, shared honesty discipline. Pairs
with the funder-evidence narrative (E8) without touching it.

**Shape.** `swelter chronicle --from --to`: reuse `aggregate` records + `qc.detect_gaps` +
coverage-equity; template with sourced threshold definitions (R1's citation pattern); uncertainty
and provisional accounting in the headline, not a footnote; ES parity via FIX-06's server-side
catalog. Statistical claims stay descriptive (counts, hours) — no health-outcome attribution.

**Effort.** M/L. **Risks.** Wording review with a public-health partner before institutional use
(gate, same as R1's); depends on EXP-01/FIX-09 for real multi-week windows.

**Excellent.** A city staffer can attach the chronicle to a council memo with every number
traceable to the archive digest; the "what we could not see" section is never empty-by-omission.

### EXP-11 — Low-tech distribution: printable neighborhood cards from the feed

**Status: Implemented.** `swelter cards` (`src/swelter/cards.py`, `src/swelter/qr.py`) ships this —
one print-CSS bilingual card per published cell, composing the aggregated surface, the
cooling-center overlay, and the committed R1/i18n guidance strings, with a per-cell feed QR
(`?area=<cell_id>`, the same query the alerts feed accepts) and a `--large-type` variant. See
`tests/test_cards.py` and `tests/test_qr.py`.

**Pitch.** Auto-generate print artifacts — a door flyer / fridge card per neighborhood cell with
current-week readings, what they mean, the cooling-center nearest, and the feed QR — bilingual,
from the same data the alerts feed uses.

**Impact.** The residents most at risk (isolated elders — the Maricopa indoor-deaths evidence the
research basis cites) are least likely to install a PWA. E11 is a *screenshot share card* for
social/press; this is the paper channel for community distribution — genuinely different medium
and audience. Extends the alerts surface (ADR 0010) offline.

**Shape.** `swelter cards --area X --lang es`: print-CSS HTML (the framework-free discipline
extends naturally; `@media print` in `web/styles.css` territory) composing feed + cooling-center +
R1 guidance strings; large-type variant (the A1 persona's tremor/low-vision needs); generated into
the publish artifact (EXP-04) so a volunteer can print this week's cards for a building lobby.

**Effort.** S/M. **Risks.** Depends on R1 (guidance copy) and FIX-06 (ES strings) landing first;
print contrast/type review belongs in the manual a11y pass (R8's artifact).

**Excellent.** A tenant association can print 50 current, accurate, Spanish-and-English cards in
five minutes, and every card carries its data-hour and provisional flags like every other surface.

---

## H3 — Transformative bets

### EXP-12 — Indoor-heat cohorts: the deadliest gap, behind a governance airlock

**Pitch.** An explicitly opt-in, aggregate-only indoor-heat module for buildings (not homes as
individually identifiable units): "N of M monitored units in this building exceeded 30 °C
overnight" — never per-unit, never per-person.

**Impact.** Indoor deaths dominate the mortality evidence the project cites (91% of Maricopa's
2019 indoor deaths had non-functioning AC). Outdoor mapping — the entire current scope — cannot
see this. Tenant organizing (C3) around habitability is the natural user. It is also the idea in
this folder with the most privacy tension, which is why the design *is* the airlock.

**Shape (gated design sketch, not a build plan).** New node class `indoor` whose observations
never enter the public store: a separate cohort store aggregating to building-level counts with a
k-threshold (publish nothing below k units); governance.md extension defining building-collective
consent; hard-rules review — the current schema refusal ("no field that can hold a person") must
be shown to survive, since an indoor temp *is* home-adjacent data even when aggregated. If the
review concludes it can't be done inside the rules, the honest outcome is a published ADR saying
why not.

**Effort.** XL. **Risks.** Privacy/governance gate before any code (the D3 persona's domain);
legal exposure around habitability claims; possible answer is "no". That is acceptable.

**Excellent.** Either a k-anonymous, collective-consented cohort surface whose DPIA extension a
hostile reviewer accepts — or a public, reasoned ADR declining the capability. Both outcomes are
wins for the project's credibility.

### EXP-13 — Multi-hazard packs: cold, smoke-event mode, one pipeline

**Pitch.** Generalize the hazard layer: a "hazard pack" abstraction (parameters + thresholds +
guidance sources + alert floors) making cold snaps and wildfire-smoke episodes first-class the way
heat is — same pipeline, same honesty.

**Impact.** The same frontline blocks that overheat in July freeze in January and choke in fire
season; networks that serve year-round survive (the sustainability evidence in POSITIONING.md is
about staying alive between summers). Technically cheap because the pipeline is already
parameter-generic; conceptually it converts swelter from "heat tool" to "exposure commons."

**Shape.** Factor `alerts.DEFAULT_THRESHOLDS` + `models` band tables + guidance keys into
declarative packs (versioned data, like corrections); a cold pack (wind-chill parameter, NWS cold
thresholds); a smoke-event mode building on FIX-02's corroboration (event framing, NowCast from
FIX-04, cooling→clean-air-center overlay variant of `cooling_centers.py`). Each pack lands as its
own ADR + PR per the Phase 5 discipline.

**Effort.** L (per pack M once the abstraction exists). **Risks.** Scope creep is the real one —
the packs must not dilute the heat mission before EXP-01/FIX-02 make the core seasonal story
solid; guidance sources per pack need the R1-style citation review.

**Excellent.** A collective enables the cold pack by config alone; every pack's thresholds are
cited, versioned data; the dashboard reads seasonally correct without a deploy.

### EXP-14 — Federation: the network of networks

**Pitch.** A directory + federated read layer over many swelter instances: one regional map that
reads N community-owned SensorThings endpoints, with provenance per network and zero central
ownership of anyone's data.

**Impact.** Every instance today is an island; the commons evidence (**[commons]**) says
aggregation layers (OpenAQ) are where reuse happens. Federation is the scale story that preserves
hard rule 5 (community ownership) — the region reads, it never holds. Goes beyond E6 (a
round-trip interop *proof*) to an operating capability with a registry.

**Shape.** A `federation.yaml` registry format (instance URL, steward contact channel, license,
languages); a `swelter federate` static builder that fans out to member `/v1.1` + surface
endpoints and emits a merged, per-network-attributed surface (static-first, per EXP-04, so the
federation layer is itself unhostable-hostage); cross-network schema versioning leaning on R11's
data dictionary. Member consent to be listed is explicit and revocable.

**Effort.** XL. **Risks.** Premature until ≥2 real instances exist — the honest sequencing is to
build the *format and proof* only (a two-instance demo from the CA + Stuttgart fetches), not a
registry service nobody asked for; governance of the directory itself is a human gate.

**Excellent.** Two real communities appear on one map, each label reading "owned by X collective,
served from their instance," and unlisting requires nothing but asking.

### EXP-15 — The community data-trust template pack

**Pitch.** Turn `docs/governance.md` from an excellent template document into an adoptable legal/
organizational kit: model agreements for host consent, precise-location disclosure, data
stewardship succession, and dissolution — reviewed by an actual lawyer, licensed openly.

**Impact.** The governance doc already carries the right norms (host consent, right-to-leave,
CC0-outlives-the-group); what a real tenants' association lacks is the *instrument* — something
they can sign. The research roadmap's R10 (consent reference field) records consent; this creates
the thing being recorded. It is also the portfolio's responsible-tech ethos expressed in its most
durable medium: paper that protects people.

**Shape.** A `docs/governance/` kit: plain-language + ES model host agreement, siting decision
record template, precise-location consent form (feeding R10's machine reference), succession/
dissolution checklist; jurisdiction caveats stated honestly (templates, not legal advice, until
reviewed); pro-bono legal review as the explicit publication gate.

**Effort.** L (mostly non-code). **Risks.** Legal review gate is hard (do not publish as "legal"
without it); jurisdictional variance means shipping a US-general baseline with a documented
adaptation process.

**Excellent.** A collective can go from "we want a network" to "our hosts have signed something
that protects them" using only the repo — and a lawyer who reads the kit finds the caveats already
say what she would have said.
