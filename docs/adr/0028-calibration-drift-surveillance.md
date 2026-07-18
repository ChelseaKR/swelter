# ADR 0028: Surface correction-drift age in the health report, without changing any calibrated value

- Status: Accepted
- Date: 2026-07-18
- Deciders: Chelsea Kelly-Reif

## Context

Every fitted correction records the co-location `window_end` it was trained against
(`calibrate.Correction`, persisted in `corrections.yaml` since Phase 2), but nothing ever read that
field back. So no surface could answer the plainest maintenance question about a calibrated value:
*how old is the evidence behind it?* The research roadmap's own **[drift]** citation
([`docs/RESEARCH-ROADMAP.md`](../RESEARCH-ROADMAP.md)) is explicit that low-cost sensors drift within
months and that unmaintained networks suffer data discontinuity — long-term low-cost-sensor
evaluation, NYC-mesonet network re-calibration, and community-network discontinuity all point the
same way. A correction fit from a window that closed over a year ago is stale evidence for a value
published today, and until now that staleness was invisible.

The obvious over-reach — expiring an aged correction's output back to provisional, or ranking
neighborhoods by how stale their calibration is — collides with hard rules. Hard rule #3 keeps raw
and calibrated distinct and immutable: a calibrated value must not silently change or get demoted as
a side effect of a health read. And a per-neighborhood staleness ranking is exactly the
coverage-equity refusal already documented in `qc.coverage_equity` — descriptive coverage is
allowed; a ranking of blocks is a governance judgment swelter does not emit.

## Decision

Add **descriptive, read-only** drift surveillance to the health report and nothing more.

- A pure helper `qc.correction_ages(observations, registry, *, horizon_days=...)` returns, for each
  correction with a recorded `window_end`, a `CorrectionAge` (version, `window_end`, age in days
  against the latest observation, and an `aging` flag once the age passes the horizon). Corrections
  with no `window_end` are skipped; an empty observation set returns `[]`.
- `qc.CALIBRATION_DRIFT_HORIZON_DAYS = 365.0` is the default horizon, a function parameter cited to
  the **[drift]** literature. It is descriptive: crossing it never changes a value.
- `qc.health_report(..., registry=...)` grows an optional `calibration` block (via
  `qc.calibration_block`) — present only when a registry is supplied — carrying those per-correction
  ages plus a fresh/aging summary and a standing "never a value change, never a neighborhood
  ranking" note.
- It is surfaced on `/api/health.json` (the server loads `corrections.yaml` from the store folder),
  in `swelter qc` (JSON plus a human summary line and per-aging-correction lines), and threaded
  through `swelter status`. The Python↔JS health contract in
  [`schemas/sample-health.schema.json`](../../schemas/sample-health.schema.json) documents the
  optional block, kept in lockstep by the Python and JS schema-contract tests.

Acceptance evidence: F-23 in [`docs/ACCEPTANCE-TEST-MAP.md`](../ACCEPTANCE-TEST-MAP.md), with anchors
`tests/test_qc.py::test_correction_ages_flags_aged_and_fresh`,
`tests/test_qc.py::test_health_report_calibration_block_flags_aging`, and
`tests/test_server.py::test_health_endpoint_surfaces_calibration_drift`.

Explicitly **not** decided here, and deferred to a later FIX-03 change because each would touch what
a value *is* or how it is computed (and the reproducibility contract): expiring an aged correction's
output to provisional with a calibration-state suffix; holdout / `n − p` fit statistics and a higher
minimum publishable `n`; any registry-schema bump or regenerated `data/demo/corrections.yaml`.

## Consequences

- **Benefit.** A steward can finally see, on the same health surface they already read, which
  corrections are past their re-co-location horizon — the maintenance signal the **[drift]**
  literature says a low-cost network needs — without trusting a hidden heuristic.
- **Reproducibility untouched.** `calibrate.apply()` and `data/demo/corrections.yaml` are not
  modified and no calibrated value changes, so the byte-for-byte co-location replay
  (`tests/test_calibrate.py::test_published_corrections_are_reproducible`) is unaffected (hard rule
  #3).
- **Additive, absent by default.** The block appears only when a registry is supplied, so every
  existing consumer of the health JSON sees the shape it always had.
- **Refusals preserved.** The metric is per-correction and ordered by the registry's own sorted key,
  never a ranking of neighborhoods (the coverage-equity refusal), and an `aging` flag never demotes
  a value to provisional.
- **Import direction.** `qc` now imports `calibrate.CorrectionRegistry`; `calibrate` imports only
  `models`, so no cycle is introduced.
- **New superseding ADR trigger.** Making drift *enforce* anything — expiry, demotion, a minimum
  `n`, or a registry-schema change — is a decision this ADR deliberately did not make, and needs its
  own record.
