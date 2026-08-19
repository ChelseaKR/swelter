# Data card: Copernicus CAMS via Open-Meteo

## Motivation and source

This keyless fallback provides current California heat and air-quality context when OpenAQ is not
available. Air quality is Copernicus Atmosphere Monitoring Service model output accessed through
Open-Meteo; weather is provided through Open-Meteo. It is not a physical sensor network.

**It is also, as of 2026-08-19, what the public deployment is actually publishing on both routes.**
The OpenAQ branch has failed closed on every run inspected back to 2026-08-16, so the "fallback" has
been the live surface continuously rather than occasionally. Any description of the deployed map as
physical-sensor data is wrong while that holds; the README's
"What the deployed site actually shows" table and each artifact's own `demo.json` / `rights` envelope
are the current record.

Sources: <https://open-meteo.com/en/docs/air-quality-api> and
<https://open-meteo.com/en/docs>. Terms: CC BY 4.0 as documented by Open-Meteo for this use.

## Composition

Hourly PM2.5, PM10, temperature, and relative humidity are requested for a checked California place
list; heat index and estimated shade WBGT are derived only from inputs inside their published
plausible range, never merely when both are present (ADR 0041). The humidity floor is 2 %RH rather
than 0, because a dead capacitive probe reports its scale floor and that reading used to derive a
mappable, several-degrees-too-cool estimated WBGT ([ADR 0043](../adr/0043-a-dead-probe-reads-zero-not-dry.md)).
CAMS genuinely reaches very low humidity over desert California, so the floor was set against the
whole published store rather than a short sample: of its 166,478 humidity rows on 2026-08-19, 1,121
(0.67%) were at or below 7 %RH, decaying smoothly — 458 at 7, 322 at 6, 213 at 5, 103 at 4, 21 at 3,
3 at 2, and 1 at 1. A 2 %RH floor reclassifies exactly one of those rows. That smooth tail is what
distinguishes real dry air from the Sensor.Community feed's spike of 25 readings at exactly `1.0`
with nothing between there and 7. Place coordinates are public
city/place centroids checked against Census geography. Values carry the explicit `openmeteo` source
identity while their calibration state remains `raw`; source provenance is never presented as a
swelter calibration.

## Collection and preprocessing

Coordinates are batched while preserving result alignment. Failed chunks are skipped, not silently
shifted onto another place. Open-Meteo may map nearby centroids to the same atmospheric grid cell;
the public map therefore must not imply block-level independence or a sensor at each point.

## Quality and uses

CAMS is model/reanalysis output already processed upstream and is not fitted by swelter. It is useful
for broad spatial/temporal context and demonstration, not a substitute for local calibrated sensors,
regulatory determinations, or individual safety advice.

The endpoints return elapsed hours and forecast hours in one array. Only the elapsed ones are
ingested: the adapter drops every hour after the fetch instant, so a predicted hour can never become
the store's newest bucket, the current reading, or an alert
([ADR 0039](../adr/0039-a-forecast-hour-is-not-an-observation.md)). swelter publishes measurements;
it does not publish a forecast.

## Distribution and license

Generated artifacts retain **CC BY 4.0 (Copernicus CAMS via Open-Meteo)** and the exact attribution
baked by the adapter. The repository's CC0 dedication does not apply. Attribution must appear in the
truth contract, UI, export, and generated `DATA-LICENSE`.

## Maintenance and retention

The reference workflow requests a short past/forecast window daily and may accumulate results in an
evictable Actions cache. Provider/API and licensing changes trigger a card and adapter review.

Owner: data steward. Last verified: 2026-08-19. Recheck cadence: provider terms/API changes and each
release.
