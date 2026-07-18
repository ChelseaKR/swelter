# Responsible-technology audit methodology

swelter treats an audit as versioned evidence tied to an implementation and an accountable owner,
not as a timeless badge. The current A–F review is in
[`../RESPONSIBLE-TECH-AUDITS.md`](../RESPONSIBLE-TECH-AUDITS.md).

Owner: Chelsea Kelly-Reif. Last verified: 2026-07-16. Recheck cadence: every release, every material
trust-boundary/source/interaction change, and after incidents.

## Four questions for every topic

Each A–F topic answers the same questions:

1. **What can go wrong, for whom, and at what scale?** Name affected people, system boundaries,
   failure modes, reversibility, and unequal exposure.
2. **What did the design do about it?** Point to implemented controls, not intentions.
3. **How is the control tested or reviewed?** Separate deterministic automation from human judgment
   and release/operational proof.
4. **What remains?** Record residual risk, owner, cadence, and a tracked issue when the gap stays open.

The six topics are ethics/consequences, bias/fairness, privacy/data protection, transparency/
explainability, accessibility, and security. AI evaluation is N/A because swelter has no prompt,
retrieval, trained/foundation model, or model-version surface; deterministic regression and rule-based
QC are evaluated as calibration/data logic instead.

## Evidence classes

The repository-wide [definition of done](../../DEFINITION_OF_DONE.md) uses three classes:

- **AUTO:** reproducible checks that can fail deterministically, such as schema, location, QC,
  calibration, source/license, i18n, browser, security, and integrity tests.
- **REVIEW:** dated, attributed human judgment, such as threat/DPIA review, source-terms approval,
  fairness reading, keyboard/screen-reader task completion, or independent Spanish review.
- **RELEASE:** evidence that exists only for the actual artifact/environment, such as exact-tag build,
  SBOM/signature/provenance, deployment smoke, rollback readiness, and current source freshness.

Passing one class does not satisfy another. In particular, axe/pa11y does not prove a current NVDA or
VoiceOver pass; catalog parity does not prove Spanish clarity; a planned release workflow does not
prove a release or rollback occurred.

## Evidence chain

| Topic | Primary artifacts | AUTO evidence | REVIEW/RELEASE evidence |
|---|---|---|---|
| A. Ethics and consequences | `ethics-consequence-scan.md`, source cards, product rules | provisional/caveat/source/publication tests | harms/benefits review; source/publication signoff |
| B. Bias and fairness | `fairness-review.md`, fixture coverage summaries | coverage/provisional/context tests | geographic/calibration/access/language review; partner validation when available |
| C. Privacy and data protection | `privacy-dpia.md`, `data-flow.md`, ADR 0003 | schema, public-location, log-safety, browser-state tests | DPIA/consent/retention review; precise-location incident exercise |
| D. Transparency and explainability | source cards, API/dictionary, provenance UI | calibration/QC/uncertainty/license/freshness propagation tests | data-card and caveat comprehension review |
| E. Accessibility | ACR, accessibility report, acceptance-test map | structural and real-browser accessibility/interaction gates | named keyboard/reflow/NVDA/VoiceOver review; issue #106 tracks currency |
| F. Security | threat model, SECURITY, runbook | authenticated-ingest, read-only, dependency/secret/static/workflow/log gates | threat review, incident response, exact-release supply-chain evidence |

## Regeneration procedure

1. Resolve the exact code/artifact/environment being audited and inspect changes since the previous
   artifact.
2. Refresh [`data-flow.md`](data-flow.md) for stores, browser state, sources, caches, logs, CI,
   publication, and external recipients.
3. Re-run the complete automated gate plus focused tests for changed boundaries. Record command and
   ref, but avoid volatile counts unless generated from a source of truth.
4. Review each A–F section using the four questions. Update the DPIA, threat model, fairness scan,
   ethics scan, source cards, ACR, and residual-risk register where the change reaches them.
5. Obtain applicable named human attestations. If one is missing, leave it open; do not infer it.
6. For a release, attach exact-tag/artifact/deployment/rollback evidence and refresh DORA/incident
   data after the observation window.
7. Update owner, `Last verified`, and recheck trigger in the same change.

## Staleness and acceptance

An audit is stale when its verified date predates a relevant implementation change, an external
source/standard has crossed its recheck trigger, or an artifact claims a human/release action that
cannot be produced. Staleness is a finding, not a reason to silently advance the date.

Accepted architecture rationale lives in [`../adr/`](../adr/README.md). The old
`docs/decisions/` directory is retained only for historical links. A material reversal gets a new ADR
and an updated risk decision; accepted history is not rewritten to make the present look inevitable.

Open exceptions remain explicit:

- [#105](https://github.com/ChelseaKR/swelter/issues/105) — intentionally excluded live repository/
  Pages governance;
- [#106](https://github.com/ChelseaKR/swelter/issues/106) — current assistive-technology and independent
  Spanish review;
- [#107](https://github.com/ChelseaKR/swelter/issues/107) — suppression retirement/code-quality follow-
  up.
