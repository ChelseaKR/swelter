# Data card: synthetic demonstration fixture

## Motivation

The fixture makes ingest, QC, calibration, aggregation, accessibility, export, and publication
reproducible without hardware or a live provider.

## Composition

`data/demo/observations.jsonl`, co-location pairs, corrections, and generated web surfaces describe
a fictional network. The default generator produces a mixture of calibrated and raw/provisional
nodes, a deliberate offline gap, a range spike, and a flatline so the pipeline's failure states are
visible. Counts vary by generator configuration and are not documentation claims.

## Collection and preprocessing

The records are generated deterministically by `scripts/gen_demo_data.py`; no people, homes, live
sensors, provider APIs, or real jurisdiction facts are sampled. Co-location fits and surfaces are
derived through the same code paths as an operator deployment.

## Uses

Appropriate for tests, onboarding, screenshots explicitly labelled synthetic, and local demos. It
must not be used to describe real environmental exposure, cooling-center availability, AC access,
tree canopy, historical redlining, or sensor coverage.

## Distribution and license

The project-authored synthetic observations are dedicated under CC0-1.0. Optional illustrative
context files retain the separate license stated in each file's metadata; see
[`context-and-reference-layers.md`](context-and-reference-layers.md).

## Maintenance

Schema and generator changes update the fixture, expected outputs, acceptance-test map, and this
card together. Public fallback use must keep the synthetic label in the truth contract, UI, export,
and generated `DATA-LICENSE`.

Owner: maintainer. Last verified: 2026-07-16. Recheck cadence: each generator/schema change and
release.
