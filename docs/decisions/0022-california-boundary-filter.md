# ADR 0022: Filter California OpenAQ discovery against a Census boundary

Date: 2026-07-09. Status: accepted.

## Decision

The California OpenAQ adapter will keep its bounding-box query because that is the upstream API's
discovery primitive, but it will not treat the box as California. Every returned location must
fall inside or on a checked-in California MultiPolygon before it:

- counts toward `--max-locations`;
- triggers a `/locations/{id}/latest` request;
- enters the generated network document; or
- contributes to the location count reported by `swelter fetch`.

The boundary asset is the U.S. Census Bureau TIGERweb States layer, January 1, 2025 vintage,
queried for state GEOID `06` in WGS 84 and simplified with a 0.0002-degree maximum offset. The
source geometry remains a seven-part MultiPolygon, including coastal islands. A small standard-
library point-in-polygon helper supports exterior rings, holes, multiple polygons, and inclusive
boundary points; no geospatial runtime dependency is added.

The generated network document records `geographic_scope.id: US-CA` and the exact boundary
version. `--accumulate` retains prior nodes only when the previous and current scope ids match. The
first scoped run therefore does not restore nodes collected by the older bbox-only adapter. The
Pages cache key is also versioned so the public CSV and SQLite-derived surface start without
previously stored bbox spillover; immutable local raw stores are not silently rewritten.

OpenAQ's source coordinates are used only for the inclusion test. Generated node entries use
`location: coarse`, so they pass through the existing 150-metre public grid. A coordinate that an
upstream aggregator publishes is not treated as a sensor host's consent for swelter to republish a
precise home-scale location.

## Why

`CALIFORNIA_BBOX` includes land outside California near every non-rectangular border. OpenAQ can
therefore return sites around Yuma, Arizona; Sparks, Nevada; or southern Oregon even though the CLI,
network title, Pages route, and reported count all call the result "California." Limiting the number
of bbox candidates after retrieval does not fix the claim: an out-of-state site can consume the cap
and an in-state site on a later page can be skipped.

Filtering candidates before the cap makes the site budget and public count describe the stated
jurisdiction. Keeping the official geometry in the package makes runs deterministic and auditable;
fetching a boundary at runtime would add a second availability dependency to every OpenAQ refresh.
The generic geometry helper is intentionally small because swelter otherwise uses only PyYAML at
runtime and does not need a full GIS stack for one containment predicate.

## Known weakness / Consequences

The checked-in boundary is a simplified cartographic boundary, not a cadastral survey. The maximum
simplification offset is about 22 metres of latitude, which is smaller than swelter's default public
grid but can still affect a monitor extremely close to a state line. A future boundary vintage must
change the recorded scope id, update the asset provenance, and rerun the border fixtures; that scope
change intentionally starts network accumulation from current, re-evaluated locations.

The adapter still depends on OpenAQ's bbox query returning all candidate locations and on the
upstream coordinates being valid. Rows with missing, non-numeric, or non-finite coordinates are
excluded because their jurisdiction cannot be established. The append-only store contract means an
operator with an old local accumulated store keeps its historical raw rows; the scoped network no
longer maps or counts those rows, and an operator who needs a jurisdiction-pure flat export should
start a fresh store, as the Pages workflow now does.

Boundary source: [U.S. Census Bureau TIGERweb State/County service](https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/State_County/MapServer/8).

Last verified: 2026-07-09. Recheck cadence: annually when the Census state-boundary vintage changes,
and whenever the OpenAQ location-query contract or public grid resolution changes.
