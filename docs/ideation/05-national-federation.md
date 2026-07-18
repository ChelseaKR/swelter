# National expansion as federation — a staged plan for model-assisted execution

Author: Chelsea Kelly-Reif. Date: 2026-07-18. Last verified: 2026-07-18. Recheck cadence: whenever a
real instance count changes, the funding landscape shifts (see `POSITIONING.md`), or a hard rule or
trust boundary changes.

This document answers one question — *does it make sense to expand swelter nationally?* — and, where
the answer is yes, decomposes the work into small, verifiable tasks a **less-capable executing model**
can run one at a time without having to make strategic judgments. It is a plan, not a spec; the
[`README.md`](../../README.md) hard rules and [`docs/ARCHITECTURE.md`](../ARCHITECTURE.md) bind
everything here. It is net-new relative to `03-expansions.md` (it operationalizes EXP-14 and EXP-15)
and `04-impact-and-sequencing.md`.

## 1. The verdict

- **A centralized national monitoring service: no.** It contradicts swelter's own survival thesis —
  the one factor shown to outlast a grant cycle is *local ownership* (Imperial County; `POSITIONING.md`)
  — and it contradicts the architecture (single-writer SQLite, scale-to-zero, no hosted service, no
  account, non-goals in `ROADMAP.md`). A national service would make swelter just another hosted
  platform, which is precisely what it is differentiated *against* (OpenAQ, Clarity, PurpleAir, IQAir).
- **A national *federation* of community-owned instances, plus an adoption engine: yes.** This is the
  honest scale story and it is already sketched as EXP-14: a thin national layer that **reads and
  attributes, never holds**. Each community owns its data, siting, precision, and governance; the
  national layer aggregates published surfaces per-network and points back at the owner. The nation
  reads; it never becomes the vendor.
- **But it must be sequenced from real validation.** swelter already runs a live public demo observatory
  on GitHub Pages, ingesting and republishing **real fetched third-party data** (OpenAQ California
  regulatory monitors; Sensor.Community Stuttgart low-cost sensors) on a daily cron — so the software and
  data pipeline are genuinely deployed and public. What has **not** happened is a **community operating its
  own first-party swelter node network** — hardware it sited, co-located and calibrated, and governs
  locally (authenticated node ingest, per-node calibration from real co-location, local governance) —
  which is precisely the operating model federation would scale. All personas are synthetic
  (`RESEARCH-ROADMAP.md`), no named community steward runs an instance, and `03-expansions.md` states
  federation is premature until at least two real *community-operated* instances exist. So the plan
  front-loads proving one community-operated instance, then a handful, and treats national scale as a
  later phase *gated* on real adoption. Building the federation tooling early is fine; *operating* a
  national layer before real community instances exist is not.

The rest of this document is the "yes" path: what national means for swelter (§2), how the executing
model must work (§3), the phase gates and the human-only milestones (§4), the model-executable task
backlog (§5), and the failure modes the plan is designed against (§6).

## 2. What "national" means for swelter — three pillars

1. **An adoption engine.** Make the "register your own network in an afternoon" promise bulletproof and
   supported: one-command stand-up, a readiness preflight, a hosted-free deploy template, and an
   onboarding runbook a non-specialist can follow. Hundreds of *owned* instances is the goal, not one
   big one.
2. **A federation read/directory layer.** A `federation.yaml` registry, a static `swelter federate`
   builder that merges members' published SensorThings/surface endpoints into one **per-network-attributed**
   national surface (fail-closed on missing terms), and an accessible, account-free national directory.
   Static-first, so the federation layer is itself un-hostage-able.
3. **A governance / data-trust kit.** The legal and organizational instruments a real collective needs —
   host consent, precise-location disclosure, siting records, succession/dissolution — so ownership is
   durable, not just asserted.

**What stays invariant at national scale (never traded for reach):** no central data ownership (read,
never hold); no person-shaped data or surveillance; the authenticated-write / public-read boundary;
coarse public locations by default; raw and calibrated never blur; caveats travel to every surface;
map/table/list outcome-equivalence and the WCAG/bilingual gates; source-license fail-closed — a
member's terms and attribution are never relabelled; no invented release, deployment, or partnership.

## 3. How the executing model must work (read this before any task)

- **One task per pull request.** Take the lowest-numbered unblocked `NF-` task in §5. Do only that task.
- **Preserve every hard rule.** If a task seems to require person-data, central data holding, precise
  locations by default, blurring raw/calibrated, or dropping a caveat, **stop and report** — the task is
  mis-scoped, not a license to break a rule.
- **Follow the repo work sequence** (`CLAUDE.md`): write observable acceptance criteria into
  `docs/ACCEPTANCE-TEST-MAP.md`, make the smallest coherent change, add an ADR under `docs/adr/` for a
  load-bearing decision, update the changelog and the relevant data card / API doc, then run the gate.
- **The acceptance of a task is a passing gate, not your opinion.** Every task below names the check that
  proves it. Run `uv sync && make verify` and `make web-test` before opening the PR; `git diff --check`.
- **Human-gated tasks:** if a task is marked **[HUMAN-GATE]**, you may draft the artifact but must not
  present it as reviewed, funded, legal, deployed, or partner-validated. Stop at the gate and hand off.
- **Never fabricate evidence.** No measured baseline, review signoff, partnership, or instance count that
  did not happen. Absence of a competitor or a review is stated as "not found" / "not yet performed".

## 4. Phases, gates, and the human-only milestones

Phases advance only when their gate is met with *real* evidence.

- **Phase 0 — prove one.** Tasks NF-01, NF-02, NF-11. Gate to Phase 1: one real community instance has
  run for at least a season with a named local steward and an honest written field write-up. Milestone
  **M-A** below is the precondition.
- **Phase 1 — a handful (3–5).** Tasks NF-03, NF-04, NF-05, NF-10. Gate: two or more real instances
  federate into one attributed surface; milestones **M-B**, **M-D**.
- **Phase 2 — regional (5–20).** Tasks NF-06, NF-07, NF-08. Gate: a funded regional steward network;
  milestones **M-C**, **M-F**.
- **Phase 3 — national.** Task NF-09 and scale hardening across the earlier tasks. Gate: a national
  coalition of owned instances with sustainable local stewardship.

**Human-only milestones (a model cannot do these; surface them, do not simulate them):**

- **M-A. Recruit and support the first real community instance** — real hardware, siting, co-location,
  a named steward. Everything else is downstream of this.
- **M-B. Fiscal sponsor or established community org as lead applicant** — the honest weak spot is
  grant-management track record, not the tool (`POSITIONING.md`).
- **M-C. Funding, in the documented order** — philanthropy first (Kresge CCHE, RWJF Local Data), then a
  research co-applicant (NIEHS community-based participatory research; NSF CIVIC), then indirect public
  health (CDC BRACE via a state/local grantee). Treat the terminated federal EJ pipeline as proof of
  demand, not live funding, and recheck its litigation status before any proposal.
- **M-D. Pro-bono legal review** of the governance/data-trust kit before it is anything but a template.
- **M-E. The hosted-infrastructure decision.** Default is **none** — stay static and federated to
  preserve scale-to-zero and no-vendor. Any hosted national service is a new ADR, a new trust boundary,
  and the observability tier change `ROADMAP.md` already describes; do not add one to "look national".
- **M-F. Real partner research** on comprehension, actionability, and maintenance burden before any
  validated-demand or equal-comprehension claim.

## 5. The model-executable task backlog

Each task: **goal**, **files** (where to work), **steps**, **acceptance** (the gate that proves it), and
the **invariants** it must not break. Tasks are additive and reversible; none weakens a hard rule.

### NF-01 — One-command instance quickstart
- **Goal.** `swelter quickstart --out <dir>` stands up a complete, servable static instance (config +
  demo data + published surface/exports/manifest) in a single command, so a newcomer sees a working
  observatory before touching hardware.
- **Files.** `src/swelter/cli.py` (a `cmd_quickstart` composing the existing `init` + `demo` + `publish`
  paths — do not duplicate their logic), `tests/test_cli.py`, ADR `docs/adr/NNNN-quickstart.md`,
  `docs/ADD-YOUR-NEIGHBORHOOD.md`, changelog, an ACCEPTANCE-TEST-MAP row.
- **Steps.** Reuse `cmd_init`, `cmd_demo`, `cmd_publish`; emit the same audited file set as `publish`.
- **Acceptance.** A test asserts the emitted file set is servable and matches `publish`'s manifest;
  `make verify` green.
- **Invariants.** Coarse locations; caveats travel; no network required.

### NF-02 — Adopter readiness preflight
- **Goal.** `swelter doctor --adopt` (or extend `doctor`) prints one plain-language "are you ready to
  publish" report: config validity, coarse-location preview per node (`node-preview`), missing
  co-location/calibration, and license posture — bilingual-ready.
- **Files.** `src/swelter/cli.py`, `src/swelter/config.py` (compose existing `config_concerns`,
  `consent_concerns`, `node-preview`), tests, changelog, ACCEPTANCE-TEST-MAP row.
- **Acceptance.** Tests cover a ready config and each common misconfiguration; `make verify` green.
- **Invariants.** No new schema field; coarse-by-default preview; no secret printed.

### NF-03 — Federation registry format
- **Goal.** A `federation.yaml` schema + parser: per member, its published base URL, steward contact
  *channel* (never a person field), license, languages, coverage bounding box, and an explicit,
  revocable `listed_consent` (bool + date). Unlisting is deleting the entry.
- **Files.** `schemas/federation.schema.json`, `src/swelter/federation.py` (parse + validate),
  `src/swelter/config.py` if needed, tests, ADR (extends/realizes EXP-14), data-card note, changelog,
  ACCEPTANCE-TEST-MAP row.
- **Acceptance.** Parser + a `swelter doctor`-style validator reject malformed entries and a missing
  `listed_consent`; schema committed and validated both sides if it reaches a surface.
- **Invariants.** No person-shaped field (contact is a channel/URL, not a name); consent explicit.

### NF-04 — `swelter federate` static builder (EXP-14 core, proof-first)
- **Goal.** Fan out to each member's read-only SensorThings/surface endpoints and emit one merged,
  **per-network-attributed** national surface (GeoJSON) plus a federation manifest — static output, no
  server. Fail closed if any member's license/attribution is absent (reuse the source-license seam).
- **Files.** `src/swelter/federation.py`, `src/swelter/cli.py` (`cmd_federate`), a two-instance
  **fixture** (the existing California + Stuttgart demo surfaces), `tests/test_federation.py`, ADR,
  `docs/interop-crosswalk.md`, changelog, ACCEPTANCE-TEST-MAP row.
- **Steps.** Build the **format and a two-fixture proof only** — not a live registry service. Reuse
  `api`/`crosswalk` to read members; every published cell carries `network`, `steward_channel`,
  `license`, `attribution`, freshness, and the same provisional/uncertainty caveats it had at the source.
- **Acceptance.** The two-fixture federation produces one surface in which every cell names its owning
  network and no member's terms are relabelled; a missing-terms fixture fails closed. `make verify` green.
- **Invariants.** Read, never hold: the builder derives a surface, it does not create a central store.
  Source terms travel; caveats travel; coarse locations only.

### NF-05 — Accessible national directory
- **Goal.** A static, account-free directory page rendered from `federation.yaml`: each member's name,
  steward channel, coverage, license, languages, and last-federated time. Framework-free; map/table/list
  equivalence if it shows a map; WCAG 2.2 AA; English/Spanish parity.
- **Files.** `web/` (a new page or route in the framework-free discipline), `web/i18n/*.json`, web tests,
  `scripts/a11y_check.py` coverage, ADR if it is a durable interaction, changelog, ACCEPTANCE-TEST-MAP row.
- **Acceptance.** `make a11y`, the web unit/browser gates, and i18n parity pass; unlisting a member (remove
  from `federation.yaml`) removes it from the page. Reading-level ≤ Grade 8 for resident copy.
- **Invariants.** A map is never the only way in; no client telemetry; consent-driven listing.

### NF-06 — Federated freshness and coverage monitor
- **Goal.** A read-only cross-instance report: which members are stale, their coverage, and calibration
  posture — for a regional coordinator, never holding member data.
- **Files.** `src/swelter/federation.py`, `src/swelter/cli.py`, tests, changelog, ACCEPTANCE-TEST-MAP row.
- **Acceptance.** Reports per-member freshness/coverage from fixtures; a test proves it stores nothing.
- **Invariants.** Read, never hold; descriptive coverage, never a neighborhood ranking.

### NF-07 — Language access beyond English/Spanish
- **Goal.** Make the catalog system pluggable for additional languages and add one third-language proof
  catalog behind the existing parity/encoding/BCP-47 gates, so national language access can grow.
- **Files.** `web/i18n/`, `src/swelter/locales/`, the i18n scripts, docs. **[HUMAN-GATE]** native-speaker
  review per new language — a machine-drafted catalog ships labelled machine-translated or waits.
- **Acceptance.** i18n parity/encoding/BCP-47/CLDR gates pass for the new language; the machine-translation
  label is present until a named human review exists.
- **Invariants.** No unperformed translation review claimed as complete.

### NF-08 — Governance / data-trust kit (EXP-15) — **[HUMAN-GATE]**
- **Goal.** Draft adoptable instruments: a plain-language + Spanish model host agreement, a
  precise-location disclosure/consent form (feeding the existing `consent_ref`), a siting decision record,
  and a succession/dissolution checklist — US-general baseline with jurisdiction caveats stated.
- **Files.** `docs/governance/`, links from `docs/governance.md`, changelog.
- **Acceptance.** The kit renders and cross-links; every document states plainly it is a template, not
  legal advice, **until M-D (legal review) is complete**. A model must not remove that caveat.
- **Invariants.** Consent explicit and revocable; no claim of legal review that has not happened.

### NF-09 — National funder / evidence pack — **[HUMAN-GATE]**
- **Goal.** Extend the existing funder-evidence pack (E8) to a program level: community-ownership,
  federation-preserves-ownership, coverage-equity, and sustainability evidence, with the honest
  funding-landscape caveats and recheck cadence from `POSITIONING.md`.
- **Files.** `docs/FUNDER-EVIDENCE-PACK.md` (or a national companion), changelog.
- **Acceptance.** Every claim cites existing repo evidence; volatile funding facts carry a recheck date;
  no validated-demand claim without M-F.
- **Invariants.** Claim discipline: say only what the implementation and evidence prove.

### NF-10 — Member conformance harness
- **Goal.** `swelter federate --check <url>` validates a candidate instance's SensorThings/surface/license
  conformance before it can be listed, so the directory cannot list a non-conforming or unattributed feed.
- **Files.** `src/swelter/federation.py`, `src/swelter/cli.py`, `tests/test_federation.py`, changelog,
  ACCEPTANCE-TEST-MAP row.
- **Acceptance.** Passes the demo instance's endpoints; fails a malformed/unattributed fixture.
- **Invariants.** Source-license fail-closed; no data retained.

### NF-11 — Onboarding automation and deploy template
- **Goal.** A scripted new-community scaffold: a `network.yaml` template, a first-instance runbook, and a
  hosted-free deploy template (Pages/S3/CDN) building on the tested `swelter publish` path, so a
  non-specialist reaches a live static instance without swelter expertise.
- **Files.** `docs/ADD-YOUR-NEIGHBORHOOD.md`, `infra/` deploy template, `docs/runbooks/`, changelog.
  **[HUMAN-GATE]** real hardware, siting, and co-location remain a community responsibility.
- **Acceptance.** Following the runbook against the demo produces a live static instance; the deploy
  template synthesizes/validates in CI. No claim of one-afternoon *physical* deployment.
- **Invariants.** No hosted swelter dependency introduced; scale-to-zero preserved.

### NF-12 — Accessibility and reading-level at scale (cross-cutting)
- **Goal.** Every new national surface (directory, federated map) keeps map/table/list equivalence,
  keyboard/reduced-motion behavior, and passes the reading-level and i18n gates.
- **Files.** wherever NF-05/NF-06 add surfaces; the a11y/i18n gates.
- **Acceptance.** `make a11y`, web browser gates, reading-level, and i18n parity green on every new surface.
- **Invariants.** A map is never the only way in; current manual assistive-technology review stays honestly
  tracked (issue #106), never inferred from automation.

## 6. Non-negotiables and the failure modes this plan is designed against

- **Centralization creep — the dominant risk.** The national layer must never become a data holder or a
  vendor. Every federated surface is *derived and attributed*, and the source of truth stays with the
  owning collective. If a task starts to build a central store or a required hosted service, it is wrong.
- **Equity-washing.** Uncalibrated data placed in frontline neighborhoods can worsen information
  disparities. The calibration/uncertainty layer is what makes national siting credible; federation must
  carry each member's calibration and provisional state, never flatten it.
- **Drift death-spiral at scale.** More instances multiply the maintenance-death risk. Each instance still
  needs a named local steward; the plan's adoption engine and steward tooling hedge it but do not remove
  the human requirement.
- **Funding cliff.** Philanthropy-first, local-ownership-as-survival. Do not architect a national program
  that dies when one grant ends.
- **Premature scale.** Do not operate a federation before two real instances exist; building the tooling is
  allowed, running the national layer on fixtures-as-if-real is not.

## 7. Honest limits

This is a plan built on a **deployed** product (a live public demo observatory on real fetched
OpenAQ/Sensor.Community data), real literature, and synthetic personas — but no **community-operated**
instance is yet running (no collective owns and governs a first-party swelter node network), and no
real community, funder, or agency has yet asked for a national program. Its first and hardest step
(M-A) is not something a model can do. Treat the task backlog as the *technical enablement*
of national federation; the organizing, funding, legal, and field validation are human work that gates
every phase. Reassess this whole document the moment the real-instance count changes.
