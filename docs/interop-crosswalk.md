# Interoperability: SensorThings round-trip + the outbound parameter crosswalk

swelter *ingests* real readings from OpenAQ and Sensor.Community (`swelter fetch --source
openaq` / `--source sensor-community`), mapping each network's own parameter names into
swelter's vocabulary. This page documents the other direction: what swelter *publishes* — over
the read-only OGC SensorThings 1.1 subset (ADR 0007) — looks like in the vocabulary those same
two commons networks use. The goal is a closed loop: swelter feeds the commons it draws from,
not just the other way round.

Two things this crosswalk deliberately is **not**:

- **Not a unit converter.** It maps a swelter parameter name to the name (and unit) the target
  network would attach to the same quantity; it never rescales a value. Where the units already
  agree (all of PM2.5, PM10, temperature, humidity), that is because swelter's own inbound
  adapters (`swelter/sources/openaq.py`, `swelter/sources/sensor_community.py`) already ingest
  those networks in those units — the crosswalk is the literal inverse of those maps.
- **Not a guess where there is no equivalent.** `heat_index_c` is swelter-derived (from
  temperature + humidity via the NWS heat index formula); neither network publishes a heat
  index, so both entries are `None`. Sensor.Community has no NO2 sensor, so its NO2 entry is
  `None` too. OpenAQ v3 does name NO2, but typically reports it in µg/m³ or ppm rather than
  swelter's ppb, and swelter has no inbound OpenAQ-NO2 adapter to invert against — that unit is
  recorded honestly as a label, with no conversion performed or implied.

## The table

Generated from `swelter.crosswalk.crosswalk_table()` (also available as `swelter crosswalk
--format json|csv`, read-only, no network):

| swelter param | swelter unit | OpenAQ param | OpenAQ unit | Sensor.Community `value_type` | SC unit |
| --- | --- | --- | --- | --- | --- |
| `temp_c` | degC | `temperature` | degC | `temperature` | degC |
| `humidity_pct` | % | `relativehumidity` | % | `humidity` | % |
| `pm25_ugm3` | ug/m3 | `pm25` | ug/m3 | `P2` | ug/m3 |
| `pm10_ugm3` | ug/m3 | `pm10` | ug/m3 | `P1` | ug/m3 |
| `no2_ppb` | ppb | `no2` | ppb (see caveat above — no conversion performed) | — | — |
| `heat_index_c` | degC | — | — | — | — |

## The round-trip proof

`tests/test_roundtrip_interop.py` plays a "standard SensorThings client": a plain dict walker
over the JSON `swelter.api` already emits (no swelter-specific knowledge, no external client
library). It:

1. Builds swelter `Observation` records across multiple nodes and parameters (raw and
   calibrated), and renders them through `api.things()`, `api.datastreams()`,
   `api.observed_properties()`, and `api.observations()` — exactly what `swelter.server` serves.
2. Asserts the payloads carry the documented SensorThings keys (`@iot.count`,
   `value[].result`, `value[].parameters.parameter`, `unitOfMeasurement.symbol`, ...).
3. Walks `Observations` back to `(node, parameter, value, unit)` using only those documented
   fields, and confirms the recovered values match the inputs exactly — including that
   calibration dedupe (raw vs. calibrated at the same node/timestamp/parameter/source) resolved the
   way `api.observations()` promises.
4. For every recovered/`ObservedProperty` parameter, calls `crosswalk.to_openaq` /
   `crosswalk.to_sensor_community` and asserts the expected commons label comes back —
   confirming the exported stream is translatable into OpenAQ/Sensor.Community terms end to end.

`tests/test_crosswalk.py` separately proves the crosswalk table is complete (every parameter in
`swelter.models.PARAMETERS` has an entry) and symmetric (for every parameter with an inbound
adapter, `to_openaq`/`to_sensor_community` is the exact inverse of `sources/openaq.py _PARAM`
and `sources/sensor_community.py _MAP`).

See also: [ADR 0007](adr/0007-ogc-sensorthings-export.md) (the SensorThings export
itself), [`docs/api.md`](api.md) (the full HTTP surface).
