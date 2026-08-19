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
near -145 °C.

Probe faults on this network are common enough to be a design constraint, not an edge case. A second
live sample on 2026-08-19 (1,066 sensors across Stuttgart and Berlin, 460 humidity readings) found
**26 readings (5.65%) at or below 5 %RH — 25 of them exactly `1.0` %RH from DHT22 probes and one
exactly `0.0` %RH from a BME280 — with nothing at all between `1.0` and the lowest real reading of
7.0 %RH.** Those are scale-floor sentinels from a failed capacitive readout, and until ADR 0043 they
were inside the published humidity range, so each one published an estimated shade WBGT 6–14 °C
cooler than the same temperature at a plausible humidity. `humidity_pct.valid_min` is now 2.0, so
they are flagged `range`, never mapped, and derive nothing — see
[`../adr/0043-a-dead-probe-reads-zero-not-dry.md`](../adr/0043-a-dead-probe-reads-zero-not-dry.md).

Upstream sensor locations are published infrastructure coordinates, but the generated network still
needs a clear deployment policy before reuse outside the reference demonstration.

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
source and license replace Sensor.Community's in every artifact claim. That is what the `/sensors/`
route did on every run from at least 2026-08-16 to 2026-08-19: the restored cache store predated the
`source-metadata.json` requirement, so `--accumulate` refused and was handed the same store back on
the next run, with no path to recovery. The store is now discarded rather than refused forever
([ADR 0044](../adr/0044-an-unattributable-store-is-discarded-not-refused-forever.md)), and the cache
key moved to `scope-v3`.

Owner: data steward. Last verified: 2026-08-19. Recheck cadence: provider terms/API changes and each
release.
