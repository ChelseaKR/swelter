# ADR 0002: Keep calibration corrections as versioned data with an audit trail, not as code

Date: 2026-06-16. Status: accepted.

## Decision

Per-node, per-parameter corrections live in a committed YAML registry
(`corrections.yaml`), not in source. `swelter.calibrate` fits each correction
from recorded co-location pairs with pure-Python OLS (no numpy): `fit()` and
`fit_one()` regress a node's raw readings onto a reference monitor's true values,
and `CorrectionRegistry` reads and writes the registry. PM is humidity-aware
(`corrected = a·raw + b·humidity + c`, US-EPA PurpleAir lineage, method
`epa-humidity`); temperature and heat index use an enclosure offset
(`corrected = a·raw + c`, method `enclosure-offset`); everything else is
`linear`. Each entry carries a version id `"{parameter}.{method}.{node_id}"`, the
training window, the reference source, the fitted coefficients, `residual_std`,
`r2`, and `n`. `apply()` emits an additional calibrated `Observation` tagged with
the version and carrying `residual_std` as its 1-sigma uncertainty; a node with
no correction stays raw and is rendered provisional. Coefficients and metrics are
rounded to `PRECISION = 6` decimal places.

## Why

A low-cost PM sensor can read double the true concentration on a humid morning,
and a sensor baking in a dark enclosure reports the box's temperature, not the
air's — a network that ignores this draws a map that is precise and wrong, so
calibration is a core feature, not a post-processing step. Treating corrections
as data means recalibrating a node is a reviewable diff in `corrections.yaml`
with a full audit trail, not a code change and a redeploy, and the `version`,
`window_start`/`window_end`, `reference`, and `n` fields record the provenance of
every fitted value. Fixed 6-dp rounding makes the fit reproducible: re-running
`fit` on the committed co-location data (`data/demo/colocation.jsonl`) reproduces
the published registry (`data/demo/corrections.yaml`, three entries per co-located
node — temp, PM2.5, PM10) byte-for-byte, so anyone can check a calibration instead
of trusting it. We rejected hard-coding coefficients in Python (no diff-able history, no
reproducibility check, fit and stored values can drift apart) and an opaque
calibration library (unauditable by a community group, and a runtime dependency
we explicitly avoid).

## Known weakness / Consequences

OLS in pure Python is intentionally plain: `fit_one` requires at least 3 pairs,
solves via the normal equations with Gaussian elimination, and raises on a
singular system, so co-location data with no variation simply cannot be fit
rather than producing a misleading result. The model is linear and assumes the
correction is stable across the deployment; sensor drift over time is not modeled
and is handled only by refitting in a later window and committing a new registry.
Reproducibility depends on the committed co-location data and the fixed precision
staying put — changing `PRECISION` or the predictor set rewrites every fitted
value, so those are breaking changes to the published registry.
