# Data card: synthetic demonstration fixture

## Motivation

The fixture makes ingest, QC, calibration, aggregation, accessibility, export, and publication
reproducible without hardware or a live provider.

## Composition

`data/demo/observations.jsonl`, co-location pairs, corrections, and generated web surfaces describe
a fictional network. The current default generator creates 150 nodes with a mixture of calibrated
and raw/provisional readings, a deliberate offline gap, a range spike, and a flatline so the
pipeline's failure states are visible. Custom generator configurations may use another count.

For the exact default fixture only, `web_preview: statewide-california` changes an in-memory copy of
the network while baking static web artifacts. It assigns the synthetic nodes deterministically to
public California place names and centroids so the statewide map has geographic context. It does not
rewrite `network.yaml`, the observation store, or the calibration evidence. Copied or edited network
configs must remove this directive and use their own node coordinates.

## Collection and preprocessing

The records are generated deterministically by `scripts/gen_demo_data.py`; no people, homes, live
sensors, provider measurements, or environmental conditions are sampled. Public California place
centroids are geographic reference points for the default static presentation only. The synthetic
values do not describe conditions at those places and do not claim a real statewide pattern.
Co-location fits and surfaces are derived through the same code paths as an operator deployment.

**Known limit of the co-location pairs.** The generator draws each co-location `raw` value
independently of the observation it publishes for the same node and instant, so only 0.5% of the
committed pairs match the corresponding stored observation. Re-running the fit over
`data/demo/colocation.jsonl` reproduces the published registry byte for byte (that is a CI gate),
but the committed fit cannot be cross-checked against `data/demo/observations.jsonl` the way it could
in a real deployment, where a co-location `raw` *is* the node's recorded reading. Tracked in
[#149](https://github.com/ChelseaKR/swelter/issues/149).

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

Owner: maintainer. Last verified: 2026-07-31. Recheck cadence: each generator/schema change and
release.
