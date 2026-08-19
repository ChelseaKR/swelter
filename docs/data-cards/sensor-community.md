# Data card: Sensor.Community snapshot

## Motivation and source

Sensor.Community is a community-run network of low-cost physical air sensors. The reference route
queries a 30 km area around Stuttgart, where coverage is dense, to show the type of raw community
measurement swelter is intended to calibrate.

Source: <https://sensor.community/en/>. API: keyless area endpoint.

## Composition

The latest row per sensor maps supported PM2.5, PM10, temperature, and humidity fields; heat index
and estimated shade WBGT are derived only when both inputs are inside their published plausible
range, never merely when both are present (ADR 0041). Public sensor id, upstream coordinate, and
reported hardware family are retained in the generated network metadata.

## Collection and preprocessing

The area endpoint is a latest snapshot, not a guaranteed history. Invalid coordinates and nonfinite
values are excluded. The SDS011 PM fault/over-range sentinel is dropped before QC. A faulted
temperature or humidity probe is kept and flagged, but supports no derived heat metric: on two live
area fetches on 2026-08-18, 13 of 272 temperature readings (4.78%) were physically impossible values
near -145 °C. Upstream sensor
locations are published infrastructure coordinates, but the generated network still needs a clear
deployment policy before reuse outside the reference demonstration.

## Calibration and limits

Values remain raw/provisional; swelter has not co-located or calibrated these devices. Hardware,
siting, humidity effects, uptime, and coverage vary. A dense Stuttgart view is not evidence of equal
coverage elsewhere.

## Distribution and license

Sensor.Community database contents are published under **ODC-DbCL-1.0**. Generated artifacts retain
that term and the Sensor.Community attribution. The repository's CC0 dedication does not apply.

## Maintenance and retention

The reference route refreshes daily and may restore an evictable accumulated Actions cache. A fetch
failure may publish the primary route as a clearly declared fallback; in that case the fallback's
source and license replace Sensor.Community's in every artifact claim.

Owner: data steward. Last verified: 2026-07-16. Recheck cadence: provider terms/API changes and each
release.
