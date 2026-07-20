# Data card: US EPA AirNow / AQS reference PM2.5

## Motivation and source

swelter fits a low-cost node's calibration by regressing its raw readings onto a co-located
reference-grade monitor. This source supplies that reference side: hourly regulatory PM2.5 from the
US EPA AirNow program, which redistributes reference-monitor data from the EPA Air Quality System
(AQS). It is used only as co-location truth to fit corrections — it is never a swelter node, never
enters the node observation store, and is never shown as a swelter-calibrated sensor value.

Source: <https://docs.airnowapi.org/>. Authentication: a free AirNow API key, supplied at runtime
via `--api-key` or `AIRNOW_API_KEY` and never written into the store, a public artifact, or an error
message (the fetch redacts the key from any failure text).

## Composition

The adapter maps AirNow `aq/data` PM2.5 rows to reference readings, each carrying its public AQS site
id (`FullAQSCode`, e.g. `060670010`), a UTC hour, and a concentration in µg/m³. It reads no host- or
person-shaped field: station and agency names in the upstream rows are ignored, and only the public
site id, timestamp, and value are retained. The AQS site id travels into `Correction.reference` as
the provenance of any fit it supports.

## Collection and preprocessing

`swelter colocate --node X --monitor Y --window START..END` pulls (or loads from a committed fixture)
the reference series and pairs it against a node's stored raw readings. The reference monitor reports
hourly and the node samples about every five minutes, so pairing is driven by the sparser reference
series: each hourly reading is matched to the single nearest node sample within a documented
tolerance (default 30 minutes), which downsamples the node series to the reference cadence — one pair
per reference hour — so no hour is over-weighted in the least-squares fit. A reference hour with no
node sample in range yields no pair rather than a guessed one; ties resolve to the earlier node
sample. Rows missing an id, timestamp, or finite value, or carrying AirNow's `-999` missing marker
(any negative concentration), are dropped rather than paired into a fit. The pairing/resampling logic
is a pure, offline function; see [`../adr/0032-reference-monitor-adapter.md`](../adr/0032-reference-monitor-adapter.md).

## Calibration and quality

These are regulatory reference measurements: they are the calibration truth, not a swelter-calibrated
value, and swelter does not re-calibrate them. They exist only to fit and version a node's correction
(method, reference, window, uncertainty), which is what promotes the node's own readings past raw /
provisional — the reference readings themselves are never published as swelter observations. Coverage
is limited to sites AirNow exposes near the co-located node; absence of a nearby reference is the
no-local-reference case that transfer calibration (research-roadmap E4) and the sensor-twin tier
(EXP-09) address instead.

## Distribution and license

AirNow redistributes US federal reference-monitor data. US Government works are in the public domain
(17 U.S.C. §105); AirNow's data-exchange terms additionally require attribution and prohibit implying
EPA endorsement. Those terms are retained on the source, not relabelled under the repository CC0
dedication. Because reference readings are used only to fit a correction and never enter the store or
a published surface, no reference PM2.5 value is redistributed as a swelter observation; the emitted
co-location file is fit evidence, carrying the reference concentration beside the node's raw value.

## Maintenance and retention

The co-location pairing is run by a steward when a node is placed beside a monitor (and can be re-run
to feed drift surveillance, FIX-03). Reference readings are not accumulated into the node store. An
operator wiring a live fetch must confirm the current AirNow endpoint, query parameters, and auth
mechanism against AirNow documentation; the tested contract of this source is the pure `parse_series`
mapping, and the live fetch is not exercised by the test suite.

Owner: data steward. Last verified: 2026-07-18. Recheck cadence: every AirNow API/terms change,
adapter change, and release.
