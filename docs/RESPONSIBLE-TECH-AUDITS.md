# Responsible-tech audits

Instantiates the pinned
[`RESPONSIBLE-TECH-FRAMEWORK`](standards/RESPONSIBLE-TECH-FRAMEWORK.md) for the current swelter
architecture, providers, exposure observatory, and authenticated node path.

Last verified: 2026-07-16. Accountable owner: Chelsea Kelly-Reif. Machine-assisted analysis:
OpenAI Codex; this is not a REVIEW-GATE signoff. Named-human A–D/F review is pending.
Recheck cadence: each release and whenever a named surface, source, trust boundary, or gate changes.

## Applicability and evidence

| Concern | State | Primary artifact |
| --- | --- | --- |
| A. Ethics and responsibility | Applies | [`audits/ethics-consequence-scan.md`](audits/ethics-consequence-scan.md) |
| B. Bias and fairness | Applies | [`audits/fairness-review.md`](audits/fairness-review.md) |
| C. Privacy/data protection | Applies | [`audits/privacy-dpia.md`](audits/privacy-dpia.md), [`audits/data-flow.md`](audits/data-flow.md) |
| D. Transparency/explainability | Applies | [`data-cards/`](data-cards/README.md), acceptance-test map |
| E. Accessibility | Applies | [`accessibility/ACR.md`](accessibility/ACR.md); manual release review open in [#106](https://github.com/ChelseaKR/swelter/issues/106) |
| F. Security | Applies | [`audits/threat-model.md`](audits/threat-model.md), [`audits/residual-risk-register.md`](audits/residual-risk-register.md) |
| Internationalization | Applies | [`I18N.md`](I18N.md); independent Spanish review open in [#106](https://github.com/ChelseaKR/swelter/issues/106) |
| AI evaluation | N/A — no prompt, retrieval, trained/foundation model, or model-version surface; deterministic OLS and rule-based QC are not AI | README standards ledger |

`[AUTO]` means a deterministic merge/release gate. `[REVIEW]` means a dated committed artifact and
the matching PR/release attestation. A manual result is never inferred from an automated check.

## A. Ethics and responsibility

**What could go wrong?** A stale, provisional, model-derived, or estimated value could be mistaken
for individualized safety advice; a confident ranking could divert attention from unmeasured
neighborhoods; exact host location or context proxies could harm people even if the tool works as
designed; downstream reuse could strip caveats and license terms.

**How do we test?** Automated tests preserve calibration/provisional state, uncertainty, freshness,
source, export provenance, coarse location, and no-person schema invariants. The consequence scan
maps residents, hosts, bystanders, stewards, providers, reusers, and people represented by context.

**What do we commit to?** No surveillance or person-shaped field; no individual “safe” claim,
diagnosis, regulatory claim, or sensitive-attribute inference; no silent state/source mixing; no
illustrative or third-party data represented as first-party CC0 fact. Harmful publication follows
the documented containment/rollback runbook.

**How is it enforced?**

| Control | Gate | Evidence/status |
| --- | --- | --- |
| Raw/provisional/model/calibrated state and uncertainty survive pipeline/UI/export | AUTO | Calibration, aggregate, schema, web, and export tests |
| Person-shaped fields/surveillance capability remain absent | AUTO + REVIEW | Schema/firmware checks plus PR hard-rule attestation |
| Source/license truth travels with generated artifact | AUTO + REVIEW | Publish/source-ledger tests and source-card review |
| Consequence, misuse, non-goal, owner, and rollback decision current | REVIEW | [`audits/ethics-consequence-scan.md`](audits/ethics-consequence-scan.md) |

## B. Bias and fairness

**What could go wrong?** Geographic provider/calibration gaps can create a two-tier map; confirmed-
first rankings can hide the places with least evidence; model and physical-sensor routes are not
comparable; historical/proxy context can stigmatize; equal EN/ES keys and a table alternative do not
prove equal comprehension or task success.

**How do we test?** Aggregate tests keep provisional/missing cells visible. Source cards distinguish
coverage and method. The committed fixture is disaggregated by confidence only as test evidence,
never presented as demographic representation. EN/ES structural parity and accessible alternatives
are automatic; lived-language and assistive-technology outcomes require named reviewers.

**What do we commit to?** Never infer sensitive attributes; show missing/provisional coverage;
preserve source/method distinctions; omit unsupported context; involve the hosting collective in
real deployment segments and calibration/siting allocation.

**How is it enforced?**

| Control | Gate | Evidence/status |
| --- | --- | --- |
| Cells lacking confirmed data remain visible and provisional | AUTO | Aggregate/schema/web tests |
| EN/ES keys/placeholders and equivalent data views remain present | AUTO | i18n, structural a11y, and web tests |
| Coverage/ranking/context representational-harm review current | REVIEW | [`audits/fairness-review.md`](audits/fairness-review.md) |
| Independent Spanish and current screen-reader task review | REVIEW | Open and blocking formal signoff: [#106](https://github.com/ChelseaKR/swelter/issues/106) |

## C. Privacy and data protection

**What could go wrong?** A porch sensor can narrow a host's home; a stolen node key can forge data;
raw browser location or saved interests can leak; accumulated build/service-worker caches can retain
data longer than expected; open artifacts cannot be recalled.

**How do we test?** Schema and config tests prove coordinate separation/coarse default; ingest tests
cover HMAC/freshness/refusal; web tests cover saved-state/clear behavior; secret and source scans
cover credentials. The DPIA inventories what/why/where/access/retention for operator, GitHub, Pages,
and browser flows.

**What do we commit to?** Exact coordinates/keys stay operator-local; precise publication is host
opt-in; browser location is explicit, in-memory, and optional; preferences/watches remain same-origin
and user-clearable; no analytics/account/background push; disclose irreversible open copies.

**How is it enforced?**

| Control | Gate | Evidence/status |
| --- | --- | --- |
| No person/coordinate in observation and coarse location default | AUTO | Models/config/aggregate/API tests |
| Authenticated write boundary and secret exclusion | AUTO | Ingest/firmware compatibility and secret-scanning gates |
| Browser geolocation/storage/cache behavior stays within inventory | AUTO + REVIEW | Web tests plus [`audits/data-flow.md`](audits/data-flow.md) |
| DPIA and residual risks current | REVIEW | [`audits/privacy-dpia.md`](audits/privacy-dpia.md), [`audits/residual-risk-register.md`](audits/residual-risk-register.md) |

## D. Transparency and explainability

**What could go wrong?** A surface can imply a sensor where CAMS supplies a model grid, statewide or
block-complete coverage where a provider is capped, calibration where values are raw, 24-hour AQI
where the UI uses NowCast, or CC0 where third-party terms bind.

**How do we test?** The schema/contract tests keep state, uncertainty, source, window, and license
fields aligned. Publication emits a truth contract, manifest, source-specific `DATA-LICENSE`, and—
for OpenAQ—a per-location `source-license-ledger.json`. Every source has a card.

**What do we commit to?** Name physical sensor vs atmospheric model vs synthetic fixture; publish
raw/provisional/calibrated/estimated state and uncertainty; show freshness and limitations; preserve
provider terms; never invent unavailable metadata.

**How is it enforced?**

| Control | Gate | Evidence/status |
| --- | --- | --- |
| Calibration/QC/uncertainty/source/license survive API/export/surface | AUTO | Schema, export, API, publish, demo-contract tests |
| Source ledger required for mixed OpenAQ artifacts | AUTO | OpenAQ/publication fail-closed tests |
| Per-source method/license/retention limitations current | REVIEW | [`data-cards/`](data-cards/README.md) |
| Every shipped feature maps to acceptance evidence | REVIEW + AUTO | [`ACCEPTANCE-TEST-MAP.md`](ACCEPTANCE-TEST-MAP.md) and docs gate |

## E. Accessibility

**What could go wrong?** The linked visualizations, custom map, tabs, range controls, inspector, and
analytical density may pass structure/axe while failing real keyboard, screen-reader, magnification,
motion, cognitive, or touch use. A stale ACR can overstate support.

**How do we test?** Structural checks, real-browser axe/pa11y, keyboard/reflow/target/motion tests,
and Lighthouse cover mechanically testable criteria. The release review requires named NVDA and
VoiceOver walkthroughs, keyboard-only completion, 200%/320px reflow, and current ACR remarks.

**What do we commit to?** WCAG 2.2 AA floor, map/table/list data parity, text/pattern—not color-only—
state, visible focus, reduced motion, and no claim that automation completed manual review.

**How is it enforced?**

| Control | Gate | Evidence/status |
| --- | --- | --- |
| Structural and browser WCAG regressions block | AUTO | Accessibility jobs invoked by the full verification gate |
| Primary task has nonvisual/keyboard/reflow alternatives | AUTO + REVIEW | Web/browser tests and ACR |
| Current NVDA/VoiceOver and release ACR signoff | REVIEW | Not yet claimed; [#106](https://github.com/ChelseaKR/swelter/issues/106) |

## F. Security

**What could go wrong?** Forged node data, source/build/cache poisoning, key/coordinate disclosure,
artifact/license tampering, direct-server denial of service, browser injection, or compromised
release identity can undermine a public record even without user accounts.

**How do we test?** HMAC/freshness/quarantine, read-only routes, path confinement, safe rendering,
archive hashes, source contracts, locked dependencies, SAST/SCA/secret/workflow scans, SBOM,
signatures, provenance, and consumer verification address mechanical controls. STRIDE covers all
boundaries and the residual register names what remains.

**What do we commit to?** Separate read/write processes; least privilege and secret separation;
no unresolved fixed high/critical finding; fail-closed source/license publication; immutable
versioned releases; operational containment without silent data rewriting.

**How is it enforced?**

| Control | Gate | Evidence/status |
| --- | --- | --- |
| Code/dependency/secret/workflow/release controls block | AUTO | Full verification and release workflows |
| Trust-boundary STRIDE is current | REVIEW | [`audits/threat-model.md`](audits/threat-model.md) |
| Residual risks have impact, control, owner, and trigger | REVIEW | [`audits/residual-risk-register.md`](audits/residual-risk-register.md) |
| Incident containment and recovery are actionable | REVIEW | [`runbooks/operations.md`](runbooks/operations.md) |

## Release attestation

This refresh updates the A–D/F analysis and automatic evidence for the observatory/source changes;
it does **not** close the human REVIEW gates. Named-human A–D/F review, the accountable-owner release
decision, the current NVDA/VoiceOver sequence, and independent Spanish review remain pending. The
machine-readable [`release-review-attestations.json`](audits/release-review-attestations.json) binds
completed reviews to the exact source tree and blocks the release preflight while any row is pending.
Issue #106 remains the AT/Spanish review gate. A separate open issue is still required for the A–D/F
human-review gap before the README conformance ledger can truthfully claim or track it. The live
ruleset/Pages-environment/required-check/cache governance block is outside this remediation by user
direction and remains tracked in issue #105.
