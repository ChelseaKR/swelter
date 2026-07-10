# ADR 0014: Historical Danger-day counts plus sourced canopy/AC-access/redlining context (E1)

Date: 2026-07-09. Status: accepted.

## Decision

Add `swelter.exposure_brief` — the historical, per-area sibling of `swelter.alerts` — plus two
new context-layer datasets that follow the pattern ADR 0013 set for tree canopy.

- **`count_danger_days(surface, ...)`** counts, per published cell, how many distinct calendar
  days a parameter (default `heat_index_c`) had at least one hourly reading at or above its
  danger floor. It does not re-derive what "Danger" means: it calls `alerts.crossing()` (renamed
  from a private `_crossing` so it can be reused) against `alerts.DEFAULT_THRESHOLDS` /
  `alerts.resolve_thresholds()`, the exact table and per-network override rule the live alerts
  feed already uses. A cell that never reported the parameter is absent from the result, not
  zero-filled — "no data" and "zero Danger days" are different claims.
- **`ExposureBrief`** joins one cell's `DangerDayCount` with whatever context is available for
  that same cell from three optional datasets, and renders plain-language, sourced lines — one
  sentence per fact, each carrying its citation and `last_verified` date. A missing context
  layer, or a layer with no coverage for a given cell, means that sentence is omitted, never
  guessed.
- **`swelter.ac_access_layer`** and **`swelter.redlining_layer`** are new sibling modules to
  `swelter.context_layers` and `swelter.cooling_centers` — not extensions of either. Each is a
  curated, validated GeoJSON `FeatureCollection` with a closed `ALLOWED_PROPERTIES` allowlist
  enforcing **one** descriptive measurement per feature plus its provenance
  (`source`, `source_url`, `last_verified`), the same discipline ADR 0013 established so no
  context layer can grow into an implied composite ranking. `ac_access_layer` publishes
  `no_ac_pct` (a modeled percentage); `redlining_layer` publishes `holc_grade` (A/B/C/D, a
  historical fact copied from its source, not a swelter judgment).
- A new `swelter brief` CLI subcommand builds and prints the brief(s) for the current store's
  surface, text or JSON, for one area or all of them — the CLI/library shape `swelter alerts` and
  `swelter export` already use.
- Illustrative sample datasets (`data/ac_access_layer.geojson`, `data/redlining_layer.geojson`)
  are committed on the synthetic demo network's published grid cells, labelled exactly as
  illustrative as `data/context_layers.geojson` already is — not a real survey, not a real HOLC
  determination for this fictional location.

## Why — the three data sources, and what was actually confirmed

The roadmap item (E1 / F5) asked for *real*, citable sources, not invented statistics, and to
confirm actual availability for swelter's real geographic scope before committing to a source.
swelter's live deployments (README) are **all of California** (Copernicus CAMS, 337 cities) and
**Stuttgart, Germany** (Sensor.Community). Two of the three sources below are US-specific and do
not apply to a Stuttgart deployment; that gap is documented, not papered over.

1. **Tree canopy** (reused, not re-sourced — `context_layers.py`, ADR 0013 already ships this).
   Real source: **USDA Forest Service Urban Tree Canopy assessments**, specifically the
   California-specific product built with CAL FIRE and NOAA (0.6 m NAIP-derived canopy rasters
   for California's census-defined urban areas): <https://www.fs.usda.gov/r05/state-private-tribal/california-urban-canopy-data>,
   also indexed at the national FSGeodata Clearinghouse
   <https://data.fs.usda.gov/geodata/rastergateway/treecanopycover/>. Public domain (CC0, US
   government work). Confirmed available and California-wide; not evaluated for Stuttgart (a
   German/EU deployment would use a national or Copernicus urban tree-cover product instead —
   out of scope for this PR).

2. **AC access.** Real source: the **U.S. Census Bureau's Local Air Conditioning Estimates
   (LACE)**, an experimental, model-based estimate of AC prevalence built by fusing the American
   Housing Survey and American Community Survey via cross-survey modeling, published at four
   geographies (national/state/county/**census tract**):
   <https://www.census.gov/data/experimental-data-products/lace.html>. Confirmed downloadable as
   plain CSV per geography level, e.g. the tract file at
   `https://www2.census.gov/programs-surveys/demo/datasets/lace/2023/LACE_23_Tract.csv` (2023
   vintage). This is the real proxy dataset the task asked to confirm exists — plain ACS alone
   does not carry an AC-access question; LACE is the Census Bureau's own purpose-built product to
   fill that gap. It is nationwide (all California tracts included); it does not cover Germany.
   **Known gap:** LACE is tract-level, not swelter-cell-level. A real deployment joins it by
   geocoding each published grid cell to its census tract — that join is out of scope here, the
   same boundary `context_layers.py` draws for canopy (this module loads and validates an
   already-joined per-cell dataset; it does not do the geocoding itself).

3. **Redlining.** Real source: **Mapping Inequality: Redlining in New Deal America** (Nelson,
   Winling, et al., Digital Scholarship Lab, University of Richmond, part of *American Panorama*):
   <https://dsl.richmond.edu/panorama/redlining/>. Confirmed downloadable as GeoJSON/Shapefile per
   city, and as a unified US-wide vector file, with an ArcGIS Living Atlas mirror; a companion
   crosswalk to 2010 Census tracts exists at
   <https://github.com/americanpanorama/mapping-inequality-census-crosswalk>. License CC
   BY-NC-SA. Citation: Nelson, Robert K., LaDale Winling, et al. "Mapping Inequality: Redlining in
   New Deal America." Ed. Robert K. Nelson and Edward L. Ayers. *American Panorama: An Atlas of
   United States History*, 2023. <https://dsl.richmond.edu/panorama/redlining>. **Known gap,
   confirmed, not assumed:** HOLC only surveyed and graded ~239 US cities in 1935-1940 — a real
   deployment in a place HOLC never mapped (a small town, a rural area, anywhere outside the US)
   has **no** redlining feature and must show "no data," never a defaulted or interpolated grade.
   Sacramento, CA (near this repo's demo-network coordinates) does have a digitized 1937 HOLC map
   (e.g. area D4: <https://dsl.richmond.edu/panorama/redlining/map/CA/Sacramento/area_descriptions/D4>),
   confirming California coverage exists for at least the state's larger cities; it does not
   confirm coverage for every one of the 337 cities the live California deployment covers, and
   does not apply to Stuttgart at all.

## Framing discipline (why this is not the advocacy copy itself)

Every rendered sentence is of the shape "X is true of this area, per \[source\], as of \[date\]" —
a citation an organizer can build a case with, not a case swelter makes for them. It never says a
grade *causes* today's readings, never blends the three context numbers with the day-count into
one score, and never extrapolates AC access or canopy for a cell the source dataset doesn't
cover. Final advocacy-framing copy — the words a printed neighborhood card or testimony actually
uses beyond these sourced facts — stays a `[HUMAN]`-gated editorial decision, the same posture
F4 and F6 already hold for equity-context framing; this ADR ships the sourced, reviewable data
layer underneath that decision, not the decision itself.

## Known weakness / Consequences

- The committed datasets are **illustrative samples**, not real LACE/HOLC data, because the demo
  network's coordinates are a synthetic street grid, not a real geocoded place — publishing real
  statistics against fake coordinates would itself be a false claim. A real deployment must swap
  in its actual jurisdiction's LACE tract join and Mapping Inequality city export before this
  feature is safe to show to residents, exactly as ADR 0013 already requires for canopy.
- `ac_access_layer` and `redlining_layer` duplicate `context_layers.py`'s small coordinate/schema
  validators rather than sharing a base module — consistent with how `cooling_centers.py` and
  `context_layers.py` already chose independence over a shared dependency for this family.
- `count_danger_days` currently supports the three parameters `alerts.py` already alerts on
  (`heat_index_c`, `pm25_ugm3`, `exposure`); adding a fourth means extending
  `alerts._floor_and_band`-equivalent logic in `exposure_brief.py`, reviewed the same way a new
  alert parameter would be.
- No map/dashboard wiring or translated (es) copy ships in this PR — `swelter brief` is a
  CLI/library surface today, the same staged scope ADR 0013 chose for canopy (loader/validator/CLI
  first, UI wiring as reviewed follow-on work once real data and framing review are in hand).

Last verified: 2026-07-09. Recheck cadence: whenever a real (non-illustrative) LACE or Mapping
Inequality dataset replaces a sample, or when map/dashboard wiring for this family lands.
