# Data-card index

Each source that can enter a swelter store or public artifact has its own card. The card is part of
the source contract: a new adapter or context layer does not ship until its card names provenance,
method, license, refresh, limitations, and steward.

| Source | Card | Production role |
| --- | --- | --- |
| Community-operated swelter nodes | [`first-party-observations.md`](first-party-observations.md) | First-party physical measurements; CC0 only when the publishing collective has authority to dedicate them |
| Generated demonstration fixture | [`synthetic-demo.md`](synthetic-demo.md) | Deterministic test/demo observations; never evidence about a real place |
| OpenAQ v3 | [`openaq.md`](openaq.md) | California physical-sensor snapshot; upstream provider terms vary per location |
| Copernicus CAMS via Open-Meteo | [`openmeteo-cams.md`](openmeteo-cams.md) | California atmospheric model/weather series; CC BY 4.0 with attribution |
| Sensor.Community | [`sensor-community.md`](sensor-community.md) | Stuttgart-area community low-cost sensor snapshot; ODC-DbCL-1.0 |
| US EPA AirNow / AQS | [`airnow.md`](airnow.md) | Regulatory PM2.5 reference used only as co-location truth to fit corrections; public-domain data with AirNow attribution terms retained |
| Boundaries and equity/context layers | [`context-and-reference-layers.md`](context-and-reference-layers.md) | Cartography and optional descriptive context; each layer retains its own terms |

The root [`DATA-LICENSE`](../../DATA-LICENSE) defines the boundary between first-party CC0 data and
generated artifacts derived from third-party sources. A generated artifact's own `DATA-LICENSE`,
truth contract, source ledger, and per-record provenance take precedence over the repository default.

Owner: data steward. Last verified: 2026-07-18. Recheck cadence: each release, every provider-terms
change, and whenever an adapter or published schema changes.
