# Audit methodology

Last verified: 2026-06-16. Recheck cadence: each release, and whenever an audit's CI gate or
its underlying module changes.

This document explains how the swelter responsible-tech audits work, what makes them evidence
rather than marketing, and how each one maps to a gate in CI. The audit set itself is in
[../RESPONSIBLE-TECH-AUDITS.md](../RESPONSIBLE-TECH-AUDITS.md); the two longer write-ups it
references are [privacy-dpia.md](privacy-dpia.md) and
[accessibility-report.md](accessibility-report.md).

## What an audit is here

An audit in this repo is a committed Markdown document plus the CI checks that keep it true. It
is not a one-time PDF signed by a consultant and filed away. The point of committing it next to
the code is that it goes stale visibly: if a claim in an audit no longer matches the code, the
gate that backs the claim fails, or the audit's "Last verified" line ages past its recheck
cadence and a reviewer notices in the diff. An audit you cannot regenerate is a claim you cannot
check, which is the same failure mode swelter rejects in its data — a value you cannot trace
back to its source.

Three properties follow from treating audits as committed evidence:

- **Regenerated, not archived.** The accessibility report summarises the output of
  `scripts/a11y_check.py`, which runs on every PR. The privacy DPIA's central claim — that the
  schema has no field that can hold a person — is checked against `src/swelter/models.py`, which
  the type and test gates exercise on every PR. When the code changes, the audit is re-run, not
  re-asserted.
- **Versioned with the thing they describe.** An audit lives in the same commit as the code it
  audits. `git log` over `docs/audits/` and over the module it covers tells you whether the
  audit predates a relevant change. There is no separate audit repository to drift out of sync.
- **Scoped honestly.** Each audit says what its automated gate can and cannot prove. The
  structural a11y gate cannot judge colour contrast or live screen-reader semantics; it says so,
  and the manual review covers the rest. An audit that overclaims its own coverage is worse than
  no audit.

## The two gate kinds

Every checklist item in the audit set is marked one of two ways. The distinction is the load-
bearing part of the method, so it is defined once here and referenced everywhere.

- **Auto-gated (blocks merge).** A deterministic check runs in `make verify` (the full merge
  gate: `fmt-check` + `lint` + `typecheck` + `a11y` + `test`) or in a dedicated CI workflow. If
  it fails, the merge is blocked. No human signature is needed because the machine re-proves the
  claim on every PR. Example: "a data-table equivalent to the map exists" is one of the twelve
  structural checks in `scripts/a11y_check.py`; if someone deletes the table, `make a11y` exits
  non-zero and the build is red.
- **Review-gated (needs a signed artifact).** The claim cannot be reduced to a deterministic
  check — it needs human judgement (a screen-reader pass, a threat-model review of a new field,
  a coverage-equity reading of a neighborhood map). The gate is satisfied by a dated, attributed
  artifact committed to the repo: a manual review note, an ADR in `docs/decisions/`, or an
  updated section in one of these audit docs, signed by the reviewer with a date. The artifact
  is the evidence; the audit checklist points at it.

A review-gated item is not a weaker item. It is an item where the honest answer is "a person
looked, here is who and when," recorded so the next person can see it was done and when it last
happened.

## How each audit maps to a CI gate

| Audit | Primary CI gate | Kind | What the gate proves |
|-------|-----------------|------|----------------------|
| A. Ethics and responsibility | `make test` (calibrated-vs-raw and provisional-labelling tests); `make verify` | auto + review | Uncalibrated values are labelled provisional through the pipeline; the non-goals (no surveillance, no individual safety claim) are review-gated against new code. |
| B. Bias and fairness | `make test` (aggregate provisional-cell tests); coverage-equity review | auto + review | A cell with no calibrated, QC-clean value is marked provisional, not dropped; per-neighborhood coverage is read by a human each release. |
| C. Privacy and data protection | `make test` + `make typecheck` (schema has no PII field; `snap_to_grid` / `public_location` tests); DPIA review | auto + review | The `Observation` schema cannot hold a person; published coordinates are grid-snapped unless a host opts in. |
| D. Transparency and explainability | `make test` (every calibrated value carries a version id and uncertainty); data-card review | auto + review | Calibration state and uncertainty travel with every value to the API and export; the data card is current. |
| E. Accessibility | `make a11y` (12 structural WCAG 2.2 AA checks); manual NVDA/VoiceOver review | auto + review | The structural floor holds on every PR; the manual review covers what the script cannot. |
| F. Security | `pip-audit`, `gitleaks`, CodeQL workflows; `make test` (read-only server returns 405 on writes); STRIDE review | auto + review | Dependencies, secrets, and code are scanned; the public surface rejects writes; new trust boundaries get a threat-model read. |

"CodeQL", "pip-audit", and the signed-release step run as GitHub Actions workflows alongside the
`make verify` gate that runs locally and in CI. `gitleaks` also runs as a local pre-commit hook
(`.pre-commit-config.yaml`), so a secret is caught before it reaches a branch as well as in CI.

## Regeneration

- Accessibility report: re-run `make a11y` and update the date and the manual-review line in
  [accessibility-report.md](accessibility-report.md).
- Privacy DPIA: re-read the data inventory and the node-location threat model against
  `src/swelter/models.py` and `src/swelter/config.py`; update [privacy-dpia.md](privacy-dpia.md).
- Bias, ethics, transparency, security: re-read the relevant checklist in
  [../RESPONSIBLE-TECH-AUDITS.md](../RESPONSIBLE-TECH-AUDITS.md) against the named modules and
  the live demo network, and update the "Last verified" line.

The cadence is each release. An audit whose "Last verified" line is older than its last relevant
code change is a finding in its own right.

---
Author: Chelsea Kelly-Reif. swelter is an independent personal open-source project; see NOTICE.
