# ADR 0023: Add a curated, descriptive-only context-layer overlay, starting with tree canopy

- Status: Accepted
- Date: 2026-07-08
- Deciders: Chelsea Kelly-Reif

## Context

The research base this project follows cites canopy inequity as core to why heat lands unequally
across a city; today the surface shows readings with no context for *why* two blocks two minutes
apart differ. For organizers, an honest canopy layer next to the heat surface is the visual
argument for shade investment — made as two related facts a viewer reads themselves, never a
swelter-computed "this neighborhood is worse" score. Keeping that boundary at the schema level
(an allowlist, not a docstring promise) is what makes the rule enforceable by `make verify` rather
than only by review discipline.

The committed dataset is an **illustrative sample** on the synthetic demo network's published grid
cells — it is labelled as such in its metadata and is explicitly not a real canopy survey. A real
deployment replaces it with a jurisdiction's published tree-canopy or land-cover dataset (for
example a USFS Urban Tree Canopy assessment or a city open-data portal) under that source's
license, keeping the `last_verified` discipline this repo applies to every external-fact artifact.

## Decision

Add `swelter.context_layers`, a curated GeoJSON overlay module for **descriptive per-cell
context data** — data that helps explain *why* readings differ from block to block, starting with
percent tree-canopy cover. It follows `cooling_centers.py`'s pattern (ADR 0011) but exists to
enforce one additional, non-negotiable rule for this whole family of overlays:

- A context-layer feature publishes **one descriptive measurement** per grid cell (`canopy_pct`, a
  plain 0-100 percentage) plus its provenance (`source`, `source_url`, `last_verified`) and an
  optional public `notes` string. `ALLOWED_PROPERTIES` is the enforcement point: there is no
  `score`, `rank`, `priority`, `vulnerability`, `index`, or `grade` field in the schema, so a future
  edit cannot smuggle a swelter-computed composite ranking onto the map through this dataset. This
  mirrors the exposure layer's honesty boundary (ADR 0009) and the project's standing refusal to
  publish a computed coverage-equity or vulnerability score: swelter shows what a dataset says,
  never a synthesized verdict about a neighborhood.
- The dataset is a curated GeoJSON `FeatureCollection` (`data/context_layers.geojson`) with
  explicit provenance: a set-level `license`, `attribution`, `source`, and `last_verified`, plus a
  `source` and `last_verified` on every feature. `swelter.context_layers` loads and **validates**
  it: every feature needs an in-range coordinate and a numeric `canopy_pct` in `[0, 100]`, and
  properties are held to the documented allowlist.
- Each feature's `cell_id` defaults to the same `"{lat:.6f},{lon:.6f}"` key `aggregate.py` already
  publishes for grid cells (`ContextLayerSet.by_cell_id()`), so a caller can join canopy context
  onto the heat/AQI surface by cell without any additional geocoding.
- It is **not** part of the CC0 observation stream — it is separately licensed civic/environmental
  data with its own metadata, the same posture as the cooling-center overlay.

This ADR intentionally scopes the first cut to the loader/validator and the committed sample
dataset — the reproducible, testable core a future dashboard toggle and table column read from. A
map layer, list-view parity, and the `docs/adr/0011`-style API route are follow-on work once
a real (non-illustrative) canopy dataset and its CBO/equity framing review are in hand; wiring the
map before that review exists would risk exactly the "context reads as an implied ranking" failure
mode this ADR is meant to prevent.

## Consequences

Canopy datasets go stale on a survey cadence measured in years, not the network's near-real-time
readings — the metadata's `last_verified` says how old the measurement is, but swelter cannot
itself refresh a third party's survey. The one-descriptive-field discipline here is deliberately
narrow: adding a second context layer (e.g. impervious-surface percent) is a new, reviewed
allowlist addition to this module or a sibling module, not an implicit relaxation of this one's
allowlist. The `cell_id` join is exact-string keyed on the grid resolution the source data used to
place its points; if a context dataset is authored at a different grid resolution than the running
network's `grid_resolution_m`, its cells will not align 1:1 and a future loader should validate
that explicitly rather than silently joining nothing. Dashboard/API wiring, translated copy, and
the CBO/equity framing review the ideation risk calls out are deferred to a follow-on PR; this ADR
covers the loader, validator, and dataset only.

Last verified: 2026-07-08. Recheck cadence: review the committed sample and the field allowlist
whenever the dashboard's context-layer wiring lands or a real canopy dataset replaces the sample.
