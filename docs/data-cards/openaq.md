# Data card: OpenAQ v3 California snapshot

## Motivation and source

OpenAQ aggregates physical air-quality stations from many original providers. Swelter uses its v3
API to demonstrate neighborhood-scale physical measurements across California when an operator
supplies an API key. OpenAQ is an access layer, not the original licensor.

Source: <https://docs.openaq.org/>. Authentication: `X-API-Key`, supplied at runtime and never
written into the store or public artifact.

## Composition

The adapter maps supported PM2.5, PM10, temperature, and relative-humidity readings into swelter
observations and derives heat index/estimated shade WBGT when inputs are present. Node ids are based
on public OpenAQ location ids. Each selected location retains its upstream provider, license name or
identifier, license URL, attribution, source URL, and fetch time in generated
`source-license-ledger.json` when OpenAQ supplies those fields. That artifact also carries a
top-level schema/version/source and an `unavailable_fields` list rather than inventing missing
metadata or a blanket license.

## Collection and preprocessing

Discovery uses an OpenAQ bounding box, then checks every candidate against the packaged U.S. Census
California MultiPolygon before it consumes the location cap or triggers a latest-reading request.
Per-location calls are throttled and transient failures are skipped. Recent readings are collapsed
to one newest-hour snapshot after excluding values outside the documented recency window. Public
locations pass through swelter's coarse grid; upstream publication is not treated as host consent
for exact-coordinate republication.

## Calibration and quality

These are physical measurements but are not calibrated by swelter. They remain `raw` and render
provisional. OpenAQ mixes community and regulatory networks, so hardware, siting, QC, units, and
license completeness vary. Coverage is capped and uneven; “California” does not imply statewide or
block-complete coverage.

## Distribution and license

Provider-specific terms apply. There is no blanket CC license for a mixed OpenAQ export. A generated
artifact must ship `source-license-ledger.json` and preserve provider attribution/terms;
records whose required reuse terms are unavailable are identified as such and are not represented
as cleared for unrestricted redistribution. The root CC0 dedication does not apply.

## Maintenance and retention

The reference Pages workflow refreshes daily when this source succeeds and may restore an
accumulated Actions cache. Cache retention is controlled by GitHub's cache lifecycle and is not a
durable archive guarantee. The published truth contract, surface, export, license file, and ledger
must all name the same source selection.

Owner: data steward. Last verified: 2026-07-16. Recheck cadence: every OpenAQ API/terms change,
adapter change, and release.
