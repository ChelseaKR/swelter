# Ideation — large-scale fixes and expansions

Drafted: 2026-07-01. Author of the pass: a repo-wide deep-dive over source, tests, CI, docs, and
data as they exist on `main` at commit `3db161a`.

## What this folder is

This is the third layer of forward planning for swelter, and it is deliberately different from the
two layers that already exist:

- [`../ROADMAP.md`](../ROADMAP.md) is the original phased build spec (Phases 1–4 built; Phase 5
  "differentiate and sustain" proposed) plus the metrics ledger.
- [`../RESEARCH-ROADMAP.md`](../RESEARCH-ROADMAP.md) + [`../USER-RESEARCH.md`](../USER-RESEARCH.md)
  (2026-06-30) turned a synthetic-stakeholder panel and cited literature into a triaged backlog
  (R1–R11 remediations, E1–E12 expansions).

This folder holds what those documents do **not**: structural fixes and expansion bets found by
reading the actual code — the aggregation path, the QC math, the licensing plumbing of the export
surface, the untested 2,600-line dashboard — rather than by replaying personas or the build spec.
Every item here is intended to be **net-new**. Where an idea touches an existing item (e.g. builds
on ROADMAP Phase 5.2 or research-roadmap E4), it cites that item by ID and states what goes
*beyond* it. Nothing here restates R1–R11 or E1–E12.

## Index

| File | Contents |
| --- | --- |
| [`01-deep-dive.md`](01-deep-dive.md) | Current-state assessment from this reading: architecture, genuine strengths, structural debt actually observed, portfolio position |
| [`02-large-scale-fixes.md`](02-large-scale-fixes.md) | FIX-01…FIX-13 — deep structural fixes (correctness, licensing, equity of machine-readable surfaces, calibration lifecycle, scale, operability) |
| [`03-expansions.md`](03-expansions.md) | EXP-01…EXP-15 — expansions in three horizons (deepen the core / adjacent capabilities / transformative bets) |
| [`04-impact-and-sequencing.md`](04-impact-and-sequencing.md) | Impact×effort matrix over all IDs, dependencies, a Now/Next/Later sequence beyond the existing roadmaps, and the human/legal/SME/real-data gate list |

## How to read this honestly

These are **ideas for evaluation, not commitments**, and not a promise of demand: no real resident,
steward, funder, or official has asked for any of them (the same caveat
[`../RESEARCH-ROADMAP.md`](../RESEARCH-ROADMAP.md) carries). Several items exist precisely because
the code and the docs currently *disagree* — those are labeled as such, because in this project
honesty is the feature. Items that need a domain expert, a governance decision, real users, or
legal review are listed separately in `04-impact-and-sequencing.md` and should be deferred, not
faked, per the portfolio ethos. Everything here respects the five hard rules in the repo
`README.md` and the `CLAUDE.md` contributor contract; nothing proposes weakening a gate.
