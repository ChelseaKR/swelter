# ADR 0043: A dead probe reads zero, not dry

- Status: Accepted
- Date: 2026-08-19
- Deciders: Chelsea Kelly-Reif

## Context

[ADR 0041](0041-a-derived-reading-is-only-as-real-as-its-inputs.md) closed the leak where a derived
heat metric was computed from an input the pipeline had already rejected. It named one case it did
not close, and left it open on purpose:

> **This does not make `0.0` %RH honest.** A humidity of exactly zero is inside the published range
> `[0.0, 100.0]`, so nothing flags it and this change does not either […] Deciding whether
> `humidity_pct.valid_min` should exclude it is a change to a published range and the data
> dictionary, so it is recorded here and left open rather than settled as a side effect of this fix.

This ADR settles it. The measurement that settles it is larger than the one ADR 0041 had.

Re-measured on 2026-08-19 against both feeds that reach a published surface, through the repository's
own adapters, plus the whole accumulated California store as actually published in `export.csv`:

| Sample | Humidity readings | At or below 5 %RH | Minimum |
|---|---|---|---|
| Sensor.Community live fetch (page 2 source), 1,066 sensors around Stuttgart and Berlin | 460 | **26 (5.65%)** | 0.0 %RH |
| CAMS/Open-Meteo live fetch (page 1 source), 337 places × 64 hourly buckets | 21,568 | 0 | 7.0 %RH |
| The published California store, `export.csv` at the 2026-08-19 deploy | 166,478 | **341 (0.21%)** | 1.0 %RH |

**The two feeds fail in opposite shapes, and that is the whole argument.**

On Sensor.Community, every low reading is a sentinel:

| Value | Count | Probe |
|---|---|---|
| exactly `1.0` %RH | 25 | DHT22 |
| exactly `0.0` %RH | 1 | BME280 |

— and there is nothing at all between `1.0` and the lowest real reading of `7.0`. A spike against an
empty band is a hardware fault: a failed capacitive readout lands on its scale floor.

On CAMS, the same low band is a smooth tail, because a model grid cell over desert California in a
heat wave really is that dry:

| %RH | 7 | 6 | 5 | 4 | 3 | 2 | 1 |
|---|---|---|---|---|---|---|---|
| readings in the published store | 458 | 322 | 213 | 103 | 21 | 3 | 1 |

Monotone decay, no spike, no gap. Those are readings, not sentinels — a 64-hour sample simply did not
reach far enough into a dry spell to see them, and the accumulated store does.

Either way the old floor was wrong. `0.0` and `1.0` were inside the published range `[0.0, 100.0]`,
so `range_flag` returned `QC_OK`, aggregation mapped them, and ADR 0041's input guard passed them
straight through to a derived heat index and estimated WBGT. Every humidity row in the published
store carries `ok`, `flatline`, or `spike` — **not one carries `range`**, including the `1.0`.

The published WBGT that results is wrong in the dangerous direction, every time, because the Stull
wet-bulb term is monotone in humidity. Recomputed from the shipped `wbgt_c` against each sentinel's
own co-reported temperature:

| Sentinel reading | Published estimated WBGT | At a plausible 55 %RH | Error |
|---|---|---|---|
| 46.2 °C @ `1.0` %RH | 26.13 | 40.05 | **−13.92 °C** |
| 38.9 °C @ `1.0` %RH | 21.71 | 33.36 | −11.65 °C |
| 36.2 °C @ `1.0` %RH | 20.08 | 30.89 | −10.81 °C |
| 35.0 °C @ `0.0` %RH | 19.14 | 29.79 | −10.65 °C |
| 30.3 °C @ `1.0` %RH | 16.51 | 25.49 | −8.98 °C |

The first row is the shape of the harm in one line. A sensor reporting a 46 °C afternoon publishes
an estimated WBGT of 26 — a number a reader checking whether it is safe to be outside reads as an
ordinary warm day — because its humidity probe is dead. The reading carries no QC flag, no
provisional marker beyond the one every uncalibrated reading carries, and nothing else on the
surface contradicts it. This is the repository's stated worst failure mode: absence rendered as a
value, on a public-health-adjacent surface, in the under-warning direction.

The estimate is also insensitive down there, which is the other half of the argument: at 35 °C,
`wbgt_c` returns 19.14, 19.29, 19.36, 19.21 and 19.23 for 0, 0.5, 1, 2 and 3 %RH. The band the
sentinels occupy carries no usable signal even if a reading in it were real.

## Decision

**`humidity_pct.valid_min` is 2.0, not 0.0.** No instrument in this network can resolve a surface
relative humidity below 2 %RH — it is under every one of their stated error bars — so a value there
is refused the way every other implausible value is refused: with the vocabulary that already
exists, and no new state.

`Parameter("humidity_pct", "%", 2.0, 100.0)` is the whole implementation. Everything else follows
from bounds the pipeline already reads:

- `qc.range_flag` returns `QC_RANGE`, which is in `QC_UNMAPPABLE`, so aggregation never places the
  reading on a cell "even provisionally" (ADR 0029).
- `models.is_within_range` returns `False`, so `models.derive_heat_metrics` (ADR 0041) derives
  **nothing** — no heat index and no estimated WBGT reaches a published surface from a dead probe.
- The raw humidity row still travels: stored, exported, flagged `range`, and counted as node-trouble
  evidence in `node_health`. QC labels a reading; it never deletes one.

Why 2.0 and not some other number, in the order the evidence supports it:

1. **It clears every sentinel actually observed.** `0.0` and `1.0` are the two values live probes
   report when their readout fails. A floor at `0.5` would have caught the BME280 and passed all 25
   DHT22s — and the DHT22s are 96% of the problem.
2. **It is at or below each probe's own stated accuracy.** DHT22 is ±2–5 %RH, BME280 ±3 %RH, SHT31
   ±2 %RH. A reading under 2 %RH is smaller than the instrument's own error bar, so the hardware
   cannot distinguish it from zero and neither should the range.
3. **It costs the real distribution almost nothing.** This is the number that matters, because the
   CAMS tail is real and a floor set too high would delete genuine desert readings. Across the
   166,478 humidity rows in the published California store, `valid_min = 2.0` reclassifies exactly
   **one** — the single `1.0` — and keeps all 3 at `2.0`, all 21 at `3.0`, and the rest of the tail.
   0.0006% of the store, against 5.65% of a physical-sensor feed's humidity readings caught.
4. **Nothing is lost even when a sub-2 reading is real.** `wbgt_c` is essentially flat across the
   band: at 35 °C it returns 19.14, 19.29, 19.36, 19.21 and 19.23 for 0, 0.5, 1, 2 and 3 %RH. A
   reading the floor excludes could not have moved the published estimate anyway.

Rejected alternatives:

- **Drop the reading at the adapter, the way `_PM_OVER_RANGE` drops the SDS011 999.9 sentinel.**
  That works for a saturation code that is unambiguously not a number. It is wrong here: PM's
  sentinel is outside the plausible range and humidity's is inside it, so treating humidity the same
  way would delete an observation that QC is supposed to *label*. It would also lose the fault from
  `node_health`, where a network operator needs to see it, and it would put the rule in three
  adapters instead of one registry entry.
- **A new QC verdict for "sensor floor".** ADR 0041 already rejected inventing a third state for
  this family of problem, and the existing verdict is exactly right: the value fell outside the
  parameter's physically plausible range. A new verdict would make every consumer switch on a term
  that means what `range` already means.
- **Leave the range and special-case exactly `0.0`.** The measurement says the sentinel is not one
  value. Special-casing `0.0` would have caught 1 of the 26 readings that needed catching.
- **A floor of 5.0.** It clears both sentinels too, and against the 64-hour live sample it looked
  free. Against the published store it is not: it would reclassify 128 real CAMS readings instead of
  one. This is exactly the overreach the store measurement caught — a short sample made an empty band
  look wider than it is.
- **A floor of 1.5.** Identical in outcome to 2.0 on every reading measured here. 2.0 is preferred
  only because it is the number the probe datasheets justify, rather than one fitted to this
  sample.

## Consequences

Measured on 2026-08-19, the new floor removes **26 of 460** Sensor.Community humidity readings
(5.65%) from the mappable set, together with the 26 heat-index and 26 estimated-WBGT values ADR 0041
would otherwise have derived from them, and **1 of 166,478** humidity rows in the published
California store (0.0006%), with its derived pair. The correction lands where the fault lives: a
physical-sensor feed loses about one humidity reading in eighteen, a model feed loses one in a
hundred and sixty-six thousand.

Verified end to end against the live feed after the change: one `swelter fetch --source
sensor-community` on 2026-08-19 returned 1,636 observations from 583 nodes, of which **22 nodes
reported exactly `1.0` %RH**. Every one of those humidity rows is stored with `qc = "range"`, and
every one of those nodes emitted `temp_c` and no `heat_index_c` or `wbgt_c` at all. The hottest of
them read 44.1 °C: it would have published an estimated WBGT of **24.86** where a plausible humidity
gives 38.13. It now publishes none.

Costs and accepted trade-offs:

- **A node with a dead humidity probe now shows no heat index and no estimated WBGT at all**, rather
  than showing a comfortably low one. That is the intended trade and the same one ADR 0041 made: the
  map shows less, and what it shows is real. `temp_c` and PM from that node still publish normally.
- **A published range moved.** Under `docs/VERSIONING.md` this is a MINOR, additive-in-spirit change
  — no observation field, CSV column, or QC verdict meaning changed, and `DATA_SCHEMA_VERSION` stays
  at 2 — but it is visible in `/api/schema.json`, whose `parameters` block is generated from
  `PARAMETERS`, so a consumer pinning the old bounds will see 2.0 where it saw 0.0. VERSIONING.md now
  names range changes explicitly so the next one is not judged from scratch.
- **Already-stored rows keep their old verdict, and one such row exists today.** `qc.apply` runs on
  newly fetched observations, not retroactively over an accumulated store, so the single `1.0` %RH
  row already in the published California store stays `ok` — and keeps its derived heat index and
  estimated WBGT — until that store is rebuilt or evicted from its Actions cache. One row in 166,478,
  in the one direction where the estimate is flat, so it is not worth a migration; it is worth
  saying out loud rather than implying the fix is retroactive. The Sensor.Community store, which
  holds the sentinels that matter, is discarded and refetched by ADR 0044 in the same change.
- **This is a floor on plausibility, not a claim about calibration.** A humidity reading at 8 %RH
  from an uncalibrated low-cost probe is still an uncalibrated low-cost reading, shown raw and
  provisional like every other.

Revisit this if a network publishes from genuinely extreme-arid terrain, or if a probe family enters
the network whose failure mode is a value above 2 %RH. The discriminator to re-measure is the *shape*
of the low tail, not its minimum: real dry air decays smoothly toward the floor, a dead probe piles
up on one value with a gap above it.

Executable evidence:

- `tests/test_models.py::test_a_dead_probe_humidity_is_outside_the_published_range`
- `tests/test_models.py::test_no_derived_heat_metric_from_a_dead_humidity_probe`
- `tests/test_models.py::test_the_humidity_floor_admits_genuinely_very_dry_readings`
- `tests/test_qc.py::test_a_dead_probe_humidity_is_flagged_out_of_range`
- `tests/test_sensor_community.py::test_parse_derives_no_heat_metric_from_a_dead_humidity_probe`
- `tests/test_openmeteo.py::test_to_observations_derives_no_heat_metric_from_a_dead_humidity_probe`

The acceptance contract is maintained under F-05 and F-15 in
[`../ACCEPTANCE-TEST-MAP.md`](../ACCEPTANCE-TEST-MAP.md).
