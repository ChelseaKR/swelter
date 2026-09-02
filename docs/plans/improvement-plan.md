# Improvement plan and running log

- **Status:** Phases 1-4 complete; nothing committed
- **Owner:** working-tree session, 2026-08-28
- **Last verified:** 2026-08-28
- **Recheck cadence:** every session that touches this plan

Working note: nothing in this session is committed. The owner withheld commit permission, so
every change below lives in the working tree only. This file is the durable record of what was
found, what was changed, and what is left.

## Repository state, verified rather than assumed

- Local `main` is at `53f9d29`; `origin/main` is at `b725a7e`, two commits ahead
  (`1f7bd62` for #142, `b725a7e` for #204). The working tree is therefore behind, and HEAD may
  not be moved in this session. Files touched upstream that this session avoids editing where
  possible: `src/swelter/calibrate.py`, `src/swelter/qc.py`, `tests/test_calibrate.py`,
  `tests/test_models.py`, `tests/test_qc.py`, `pyproject.toml`, `docs/calibration.md`,
  `docs/RESEARCH-ROADMAP.md`.
- PR #204 **has** merged. PR #200 has **not**, and its entire diff (`also_copy = ["scripts/"]`
  under `[tool.mutmut]`) is already on `origin/main` inside #204's first commit. #200 is
  superseded, not stale-in-the-usual-sense. It is left open; closing is the owner's call.
- 8 open issues, 7 open PRs, as stated.

## Issue classification

| Issue | Classification | Note |
|---|---|---|
| #199 Danger counts ignore QC/provisional | Real defect | **Already in flight** in PR #205 (mergeable, clean). Not duplicated here. |
| #179 OpenAQ fails closed every run | Real defect, **blocked** | Root cause needs a live authenticated `GET /v3/locations` call. This session is offline and has no `OPENAQ_API_KEY`. Cannot be closed honestly without that evidence. |
| #119 `STANDARDS_PIN_TOKEN` | Missing external configuration | Owner action (mint PAT, add secret). Not code. |
| #109 Hosted performance + retained DORA baselines | Missing evidence, blocked | Needs hosted field data and a real retained deployment window. |
| #108 PyPI trusted publisher | Missing external configuration | Owner action. |
| #107 Retire/narrow suppressions | Real, incremental | Ratchet exists (`SUPPRESSION_CEILING`). Actionable in small steps. |
| #106 Human a11y and Spanish signoff | Aspiration until a human does it | Cannot be automated, and must not be claimed. |
| #105 Merge and Pages governance | Missing external configuration | Owner action on repository settings. |

## What the open PRs already cover

| PR | Covers | State |
|---|---|---|
| #207 kill calibrate mutation survivors | `tests/test_calibrate.py` assertions against the OLS solver and registry serialization | Open, **conflicting** with `main` |
| #206 rebuild `web/sample-surface.json` | Stale offline fallback fixture after #142 | Open, **conflicting** with `main` |
| #205 Danger counts carry QC state | Issue #199 in full, plus `docs/MULTIYEAR-PLAN.md` | Open, clean |
| #203 / #202 / #201 | Dependabot lock bumps | Open |
| #200 mutmut `also_copy` | Superseded by merged #204 | Open |

Everything those PRs touch is out of scope for this session.

## The defect class this session hunts

The portfolio rule: *a check that cannot fail is worse than no check.* This repository has
already fought that fight twice and kept the evidence:
`test_workflow_policy_gate_refuses_to_pass_on_no_workflows` and
`test_reading_level_gate_refuses_to_pass_when_it_scores_nothing` in
[`tests/test_quality_gates.py`](../../tests/test_quality_gates.py). Both were the same bug: a gate
whose corpus went empty printed a universal claim about the empty set and returned 0.

The remaining instances of that exact shape, each verified by running the gate against an empty
corpus, are the subject of Phase 1 and Phase 2.

## Phases

### Phase 1 — gates that pass on an empty corpus — DONE

| # | Gate | Vacuous behaviour, verified by running it | Guard added |
|---|---|---|---|
| 1 | `scripts/log_safety_check.py` | `[PASS] production log calls are structured and PII-safe` with zero files scanned | `corpus_problems`; each of `src`, `scripts`, `infra` must contribute a file; the PASS line names the counts |
| 2 | `scripts/acceptance_map_check.py` | `PASS (0 shipped features; paths, symbols, roadmap, ISO 25010:2023 verified)` | an empty feature map or an empty roadmap inventory is a problem |
| 3 | `scripts/adr_immutability_check.py` | `PASS (0 Accepted base ADR(s) unchanged)` | `corpus_problems`: zero Accepted base ADRs is a refusal |
| 4 | `scripts/i18n_parity.py` | two empty catalogs reported `EN/ES at key parity (0 keys)` | a fourth check: the EN catalog must have strings |
| 5 | `web/tests/run-pa11y.cjs` | `Pa11y: 0/0 pages passed`, exit 0 | `configProblems`: non-empty, and covering every published route; unreadable severity now throws instead of clearing |

### Phase 2 — evidence a gate claims but does not hold — DONE

| # | Where | What it could not report | Fix |
|---|---|---|---|
| 6 | `make sbom` / `make sbom-validate` | a shell `for` loop's exit status is its last iteration's, so a failed wheel BOM was swallowed and the `dist/*.cdx.json` glob then validated the sdist alone | `set -e` in the loop; a pairing assertion that every built artifact has a BOM beside it |
| 7 | `scripts/dora_evidence.py` | `PASS (check)` identical for a full window and for the committed zero-record, all-metrics-unavailable state | `coverage_summary` in the PASS line |
| 8 | `scripts/release_artifacts.py` | both branches of `validate-publishing-gap` printed the same `[FAIL]`, so every schema assertion was decorative | the two outcomes now read differently (both still exit 1, which is correct) |
| 9 | `scripts/release_artifacts.py` | `"105" in text` could not tell an issue reference from three digits | a reference regex |
| 10 | `scripts/workflow_policy_check.py` | a version-annotation exemption keyed to an `actions/cache` SHA that left `pages.yml` at the v4.3.0 to v6.1.0 bump | entry retired; `stale_exemptions` reports any exemption that matches no `uses:` line |
| 11 | `scripts/docs_figures_check.py` | an advisory rule warning forever about the correct state, running and discarding a `pytest --collect-only` each time | absence of the claim is a pass; the collection is lazy |

### Phase 3 — a caveat that did not travel — DONE

12. `src/swelter/cards.py` printed `provisional` for a QC-flagged spike, identical to an
    uncalibrated but unremarkable reading. `state-flagged` was already in both catalogs and
    already loaded. Fixed; three tests added.

### Phase 4 — documentation — DONE

Changelog, this plan. No acceptance-map row changes: nothing here ships a new feature outcome.

### Not done, and why

- **#179 (OpenAQ)** — needs a live authenticated `GET /v3/locations`. Offline, no API key. Blocked.
- **#119 / #108 / #105** — repository and account configuration only. Owner action.
- **#109** — needs hosted field data and a real retained deployment window.
- **#106** — needs named human reviewers. Must never be claimed.
- **#199** — real, and already fixed in open PR #205. Not duplicated.
- **`docs/audits/mutation-baseline.json`** — absent, so `make mutation-baseline-check` and
  `make release-readiness` cannot pass. It cannot be generated honestly until a mutation run is
  done on a tree that includes #204's `also_copy`. Left alone; this session's tree is behind.
- **`dora_evidence.check` never evaluates a DORA threshold.** True, and reported, but making a
  DORA metric merge-blocking is a policy decision for the owner, not a defect fix.

## Running log

- 2026-08-28: read `CLAUDE.md`, `README.md`, all 8 issues, all 7 PRs. Verified repository state
  against `origin/main` rather than against the brief. Baseline `make verify-core`: all 19 gates
  passed, 960 tests, 91.33% branch coverage.
- 2026-08-28: empty-corpus probe run against every `scripts/*.py` gate; five vacuous-pass gates
  confirmed by execution.
- 2026-08-28: Phases 1-4 implemented. Every guard was broken deliberately, watched to fail, and
  restored: 13 of 13 failed when broken and passed when restored. The `make sbom` loop was
  demonstrated in both shapes against a stand-in generator that fails for the wheel.
- 2026-08-28: final `make verify` -> `SWELTER_VERIFY_EXIT=2`. `verify-core` all 19 gates passed;
  `verify-web`, `firmware-test`, `infra-synth` and `verify-package` passed; `verify-security`
  failed 1 of 7 on `security-osv`, which fails at its own version assertion
  (`osv-scanner --version` is 2.5.1 locally, `OSV_SCANNER_VERSION` is pinned at 2.3.8) before the
  scan runs at all. That assertion reads only the installed binary and a Makefile constant this
  session did not touch, so it fails identically on a pristine checkout; CI installs the
  checksum-verified pinned build.
- 2026-08-28: note for whoever runs the next session -- the agent scratchpad at
  `/private/tmp/claude-501/.../scratchpad/` is shared between concurrently running agents. A first
  `make verify` log written to a generic filename there was overwritten mid-run by another
  repository's agent. Use a collision-proof filename.
- 2026-08-29: the `security-osv` version-assertion failure logged on 2026-08-28 is resolved.
  `OSV_SCANNER_VERSION` and both workflow installs move 2.3.8 -> 2.5.1. Checked before bumping:
  2.5.1 scans the same two lockfiles and reports no issues, so the old pin concealed nothing.
  Break-tested: a wrong pin fails `make security-osv` with exit 2, the correct one passes with 0.
