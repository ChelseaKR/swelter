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
<https://open-meteo.com/en/docs>. Terms come in two separate parts, set out under
[Distribution and license](#distribution-and-license). **Data license:** CC BY 4.0, with
attribution. **API access:** Open-Meteo's free, keyless API is for non-commercial use only and is
rate-limited. Commercial use needs a paid API subscription.

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

Open-Meteo's terms separate two things that this card used to merge into one line: the license on
the *data* and the conditions for *calling the API*. Meeting one does not satisfy the other.

**Data license (what travels with published values).** Open-Meteo publishes API output under
CC BY 4.0. Its licence page names the data sources, and its terms apply the same licence to data
from the free API and from a paid subscription. CC BY 4.0 allows commercial reuse with attribution.
Generated artifacts keep **CC BY 4.0 (Copernicus CAMS via Open-Meteo)** and the exact attribution
baked by the adapter. The repository's CC0 dedication does not apply. Attribution must appear in the
truth contract, UI, export, and generated `DATA-LICENSE`.

**API access (who may call which endpoint, and how often).** As of 2026-10-17, per Open-Meteo's
terms and pricing pages:

- The free API (`api.open-meteo.com`, `air-quality-api.open-meteo.com`) is offered **for
  non-commercial use only**. It allows fewer than 10,000 calls per day, 5,000 per hour, and 600 per
  minute. The comparison table on those pages also lists 300,000 calls per month. Open-Meteo
  reserves the right to block applications that misuse it.
- The terms list as **non-commercial** use: private or non-profit websites or apps without
  subscriptions or advertising, home automation, public research at public institutions, and
  educational content. They list as **commercial** use: sites or apps that have subscriptions or
  show advertisements, integration into commercial products or promotional activities, and
  undisclosed research at commercial entities. Open-Meteo points to Creative Commons'
  NonCommercial interpretation for the definition.
- Commercial use, or more calls than the free limits, needs a **paid API subscription**. The
  subscription comes with an API key for the customer endpoints (`customer-api.open-meteo.com`,
  and `customer-air-quality-api.open-meteo.com` for air quality). Requests carry `&apikey=`, and
  the parameters and responses are otherwise the same as the free API.

**Where the reference deployment stands.** The public reference site runs one scheduled batched
fetch a day, plus a rebuild on each push to `main`. A run sends 337 California places in chunks of
100, so it makes 8 HTTP requests before any retries: 4 to air quality and 4 to weather. Even if
every coordinate counts as a separate call, that is about 674 calls per run, far below the free
limits. The site sells no subscriptions and shows no advertisements. **We believe this posture fits
the free non-commercial tier.** Open-Meteo has not confirmed that. Two items are open for the owner
to confirm with Open-Meteo before relying on that belief:

1. the "Support this work on Ko-fi" donation link in the dashboard footer and README; and
2. Google Analytics 4 page counts on the reference pages
   ([ADR 0055](../adr/0055-google-analytics-4-on-the-public-pages.md)).

Neither is a subscription or an advertisement, but the terms do not explicitly cover either one.

**Other deployments.** A collective's own deployment makes its own access decision under these
terms. A paid, contracted, advertising-supported, or otherwise commercial deployment must use its
own Open-Meteo subscription. To use one, set `OPENMETEO_API_KEY` in the fetch environment, and
`swelter fetch --source openmeteo` switches to the customer endpoints
([ADR 0056](../adr/0056-open-meteo-access-is-separate-from-its-data-license.md)). The key is sent
only in the request to Open-Meteo. It is never printed, logged, stored, cached, or written to an
artifact, and `swelter doctor` reports only whether it is set. The reference workflow does not set
it. With no key, requests are identical to the free-host requests made before key support existed.
A key changes how the data is accessed. It does not change the data license or the attribution
above.

Evidence: the terms, pricing, and licence pages at <https://open-meteo.com/en/terms>,
<https://open-meteo.com/en/pricing>, and <https://open-meteo.com/en/licence>. On 2026-10-17 a direct
fetch of open-meteo.com was blocked from the verification environment. The text quoted above was
read from those pages' published source in the `open-meteo/open-meteo-website` GitHub repository
(`src/routes/en/terms`, `src/routes/en/pricing`, `src/routes/en/licence`). The customer-host
pattern `customer-<api>.open-meteo.com` comes from that site's request builder. Open-Meteo says
changes to its terms take effect when posted and are tracked in that repository's history. Owner:
data steward. Last verified: 2026-10-17. Recheck trigger: any change to Open-Meteo's terms,
pricing, or licence pages, or that repository's history for them; any change to the reference
site's funding, advertising, analytics, or fetch volume; and each release.

## Maintenance and retention

The reference workflow requests a short past/forecast window daily and may accumulate results in an
evictable Actions cache. Provider/API and licensing changes trigger a card and adapter review.

Owner: data steward. Last verified: 2026-10-17 (API access terms; the rest of this card 2026-08-19).
Recheck cadence: provider terms/API changes and each release.
