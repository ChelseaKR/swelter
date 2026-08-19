# ADR 0041: A derived reading is only as real as its inputs

- Status: Accepted
- Date: 2026-08-18
- Deciders: Chelsea Kelly-Reif

## Context

Three source adapters derive heat index and estimated shade WBGT from a temperature and a humidity
reading. All three did it the same way — compute whenever both inputs are present:

```python
if temp is not None and humid is not None:
    hi = heat_index_c(float(temp), float(humid))
    _emit(out, node_id, ts, "heat_index_c", hi, "degC")
```

Present, not plausible. That is the whole defect. `range_flag` marks a value outside its published
range `QC_RANGE`, which is in `QC_UNMAPPABLE`, so aggregation never places it on a cell "even
provisionally" (ADR 0029) — the pipeline's own verdict is *this is not a measurement*. But the
metric derived from that same rejected number was emitted as an ordinary observation, and it
frequently lands back **inside** the derived parameter's own range. There it is indistinguishable
from a real reading: QC passes it `ok`, aggregation maps it, and the public surface publishes a
broken sensor's arithmetic as a clean, unflagged value.

This is live, not hypothetical. Two Sensor.Community area fetches taken on 2026-08-18 (599 and 597
sensors around Stuttgart and Berlin):

| Measured on the live feed | Count |
|---|---|
| Temperature readings returned | 272 |
| Physically impossible temperatures (≈-141 to -147 °C) | **13 (4.78%)** |
| Humidity readings returned | 254 |
| Humidity reading of exactly `0.0` %RH | 1 |
| PM sentinels at 999.9 / 1999.9 µg/m³ dropped by the existing `_PM_OVER_RANGE` guard | 3 per parameter |

The ≈-145 °C cluster is a faulted DHT/BME probe reporting its register default. The existing PM
guard shows the shape of the problem was already understood for particulates — `_PM_OVER_RANGE`
drops the SDS011 saturation sentinel *before* QC — while the temperature/humidity path grew no
equivalent.

Whether a rejected input leaks depends on where it lands, and the leaking bands are wide and
realistic. Measured by sweeping the published ranges:

| Rejected input | Derived value | Published as |
|---|---|---|
| `temp_c = -41.0`, RH 50% | `wbgt_c = -39.48` | **clean, mapped** |
| `temp_c = -40.01`, RH 0% | `wbgt_c = -27.21` | **clean, mapped** |
| `temp_c = 80.0`, RH 10% (sun-baked enclosure) | `wbgt_c = 53.11` | **clean, mapped** |
| `temp_c = 60.5`, RH 90% | `wbgt_c = 59.21` | **clean, mapped** |
| `humidity_pct = 110`, 35 °C (condensing sensor) | `wbgt_c = 36.16` | **clean, mapped** |
| `humidity_pct = 200`, 30 °C | `wbgt_c = 40.26` | **clean, mapped** |
| `humidity_pct = -1`, 35 °C | `heat_index_c = 32.61` | **clean, mapped** |

The whole cold band `temp_c ∈ [-61.72, -40.01]` leaks a mappable WBGT, as does everything from just
past the +60 °C ceiling up to roughly +85 °C at low humidity. Humidity above 100 %RH — what a
condensing low-cost sensor reports in fog — leaks a mappable WBGT at essentially every realistic
temperature. `heat_index_c` is largely self-protecting against a bad temperature (it passes the air
temperature through below 26.7 °C, so an impossible temperature stays impossible) but not against a
bad humidity.

The direction of the error is not safe in either sign. A derived WBGT built from an impossible
temperature can read reassuringly mild on a hot day or alarmingly severe on a calm one, on a surface
whose stated purpose is helping someone decide whether it is safe to be outside.

At the two instants sampled, no leaked value happened to be published — the ≈-145 °C cluster sits
outside the leak band, and neither sample contained a >100 %RH reading. The fault mode that feeds
the leak, however, is continuously present at ~5% of temperature readings, and the guard that would
catch it did not exist.

## Decision

**A derived reading is only as real as the inputs under it. Derivation happens in one place, and
that place requires plausible inputs.**

`models.derive_heat_metrics(temp_c, humidity_pct)` is now the single site that turns a temperature
and a humidity into derived heat metrics, and the three adapters call it instead of calling
`heat_index_c`/`wbgt_c` themselves:

- **Either input outside its published range ⇒ nothing is derived.** Not a flagged value, not a
  substituted one — the reading is simply absent, and absence is never published as a number
  (ADR 0037). Emitting it with `QC_RANGE` was rejected: adapters do not assign QC verdicts (`qc.apply`
  does), and a derived row whose only honest verdict is "unmappable" carries no information that the
  already-flagged input rows do not.
- **A derived value outside its own range is also not emitted.** In-range inputs can still produce
  an impossible result (a real 60 °C at 100 %RH has no meaningful heat index). QC would flag it
  anyway; not emitting it keeps one rule instead of two.
- **The raw inputs still travel.** QC labels a reading, it never deletes one. The impossible
  temperature and the condensing humidity are still written, still flagged, still exported, and
  still count as node-trouble evidence in `node_health`. Only the *derivation* is withheld.

`models.is_within_range(parameter, value)` is the value-level form of `qc.range_flag`, for callers
that hold a number rather than an `Observation` — which is exactly the adapters' situation, since
they must decide whether an input is a measurement before there is an observation to label. Both
read the same `PARAMETERS` bounds, so there is one definition of plausible, not two.

## Consequences

A faulted probe no longer contributes a derived heat metric to the map under any of the three real
sources. On the cached live payload, the five nodes reporting ≈-145 °C emitted derived readings
before this change and emit none after it; every in-range node derives exactly as it did.

Costs and accepted trade-offs:

- **Fewer derived rows from imperfect sensors.** A node whose temperature is fine but whose humidity
  is faulted loses its heat index and WBGT entirely, rather than getting a heat index computed from a
  bad humidity. That is the intended trade: the map shows less, and what it shows is real.
- **The guard is at the adapter boundary, not in `calibrate.py`.** `calibrate.apply` also derives a
  heat index, from an already-*calibrated* temperature plus a co-timed humidity (ADR 0014). That path
  starts from a fitted correction rather than a raw feed value and is left unchanged here; extending
  the same input check to it is follow-up work, not a silent inclusion.
- **This does not make `0.0` %RH honest.** A humidity of exactly zero is inside the published range
  `[0.0, 100.0]`, so nothing flags it and this change does not either — yet a surface-level relative
  humidity of exactly 0.00% from a low-cost capacitive probe is a dead-sensor reading, not weather,
  and it drags a derived WBGT down by about 10 °C (at 35 °C: 19.14 instead of 29.12) in the
  under-warning direction. One such reading appeared in 254 live humidity readings. Deciding whether
  `humidity_pct.valid_min` should exclude it is a change to a published range and the data
  dictionary, so it is recorded here and left open rather than settled as a side effect of this fix.
- **No published range changed.** This ADR applies the existing bounds consistently; it does not
  redefine what is plausible.

It also closes a latent crash. `wbgt_c` raises `ValueError: math domain error` for any negative
humidity (`math.pow(rh, 1.5)`), and the Open-Meteo call site — unlike the other two — had no
exception suppression around it, so a single negative relative-humidity value in the CAMS response
would have aborted the whole statewide fetch. The range check short-circuits before that call, so
the case is now excluded rather than merely caught.

Executable evidence:

- `tests/test_models.py::test_no_derived_heat_metric_from_a_rejected_input`
- `tests/test_models.py::test_derive_heat_metrics_drops_a_derived_value_outside_its_own_range`
- `tests/test_models.py::test_derive_heat_metrics_derives_from_plausible_inputs`
- `tests/test_models.py::test_derive_heat_metrics_rejects_nonfinite_inputs`
- `tests/test_models.py::test_is_within_range_matches_the_published_bounds`
- `tests/test_sensor_community.py::test_parse_derives_no_heat_metric_from_a_faulted_probe`
- `tests/test_sensor_community.py::test_parse_derives_no_heat_metric_from_a_condensing_humidity_reading`
- `tests/test_openaq.py::test_parse_latest_derives_no_heat_metric_from_a_rejected_input`
- `tests/test_openmeteo.py::test_to_observations_derives_no_heat_metric_from_a_rejected_input`

The acceptance contract is maintained under F-05 in
[`../ACCEPTANCE-TEST-MAP.md`](../ACCEPTANCE-TEST-MAP.md).
