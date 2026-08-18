# Data card: Copernicus CAMS via Open-Meteo

## Motivation and source

This keyless fallback provides current California heat and air-quality context when OpenAQ is not
available. Air quality is Copernicus Atmosphere Monitoring Service model output accessed through
Open-Meteo; weather is provided through Open-Meteo. It is not a physical sensor network.

Sources: <https://open-meteo.com/en/docs/air-quality-api> and
<https://open-meteo.com/en/docs>. Terms: CC BY 4.0 as documented by Open-Meteo for this use.

## Composition

Hourly PM2.5, PM10, temperature, and relative humidity are requested for a checked California place
list; heat index and estimated shade WBGT are derived only from inputs inside their published
plausible range, never merely when both are present (ADR 0041). Place coordinates are public
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

Owner: data steward. Last verified: 2026-07-16. Recheck cadence: provider terms/API changes and each
release.
