# ADR 0039: A forecast hour is not an observation

- Status: Accepted
- Date: 2026-08-16
- Deciders: Chelsea Kelly-Reif

## Context

ADR 0035 decided that "now" is the newest hour bucket present in the data — no wall clock, so the
published artifact is reproducible and the map, the feed and the publish manifest cannot drift apart.
That is the right rule for a store of observations. It is the wrong answer the moment the store
contains a prediction, and `sources/openmeteo.py` was putting predictions in it.

`fetch()` defaults to `past_days=2, forecast_days=1`, and Open-Meteo's `forecast_days=1` returns
*every* hour of the current UTC day, including hours that have not occurred. `to_observations()`
iterated the `time` array and emitted an `Observation` for each entry with no comparison against any
reference instant, so future hours entered the store as ordinary readings. The Pages workflow passes
`--past-days 1` and no forecast argument, so `forecast_days=1` stood on every deploy.

Measured on the live artifacts at 2026-08-15T14:40:49Z (issue #168):

- `publish-manifest.json` reported `"data_hour": "2026-08-15T23:00:00Z"` — eight hours and nineteen
  minutes in the future at the moment of reading, and nine hours ahead of the deploy that wrote it.
- `sample-surface.json` held exactly one bucket, `2026-08-15T23:00:00Z`, across 2,359 cells.
- `alerts.json` was stamped `"generated": "2026-08-15T23:00:00Z"` with 35 alerts, all in that
  bucket: 17 `heat_index_c` at **Danger**, 17 `exposure` at High, 1 PM2.5 at Unhealthy for Sensitive
  Groups. The first headline read, verbatim: `Calexico: heat index is in the Danger range
  (41.04 °C) (provisional, not yet calibrated), as of 2026-08-15T23:00:00Z.`

Reproduced locally against the current adapter: an eight-hour response straddling the current hour
produces a surface whose `newest_bucket()` is three hours ahead of the wall clock and an alerts feed
carrying a Danger heat headline for an hour that has not happened.

This is a different kind of wrongness from an uncalibrated reading, and the difference is why the
existing caveats do not cover it. `provisional: true`, "Upstream model", and "not a
Swelter-calibrated sensor network" all describe **how the number was produced**. None of them says
**the hour it describes has not happened**. A resident told "heat index is in the Danger range as of
23:00Z" at 14:40Z is being told about a measurement that does not exist. The feed is also stamped
`generated` in the future, which places it ahead of everything real in any reader that orders by
time.

Nothing downstream can recover from this, and nothing downstream should try. `newest_bucket()` is
`max(cell.bucket)` by design, and the alerts feed's staleness rule (ADR 0036) is built on it: with a
forecast hour present, every genuinely current cell is *behind* the newest bucket, so the correct
readings are the ones that read as stale. The fix has to be upstream of the store.

## Decision

**An hour that has not happened is not an observation, and the adapter refuses to mint one.**

`openmeteo.to_observations()` takes a `now` reference instant and skips every hour after it. `now`
defaults to `datetime.now(UTC)`, so a caller that forgets it gets the safe behaviour; passing an
explicit instant is for tests and for reproducing a past fetch, never an opt-in to clipping.
`fetch()` resolves the instant once, logs it, and passes it down, so one fetch clips every place
against one reference rather than drifting across a five-minute statewide run.

Three alternatives were rejected:

- **`forecast_days=0`.** That is how Open-Meteo returns *today's already-elapsed* hours; without it
  the window ends at the close of yesterday and there is no current reading at all. The window stays
  wide; the mapping is what narrows.
- **Ingest forecast hours behind a marker.** `Observation` has no field that can say "this is a
  prediction", and adding one means every consumer — surface, export, API, alerts, dashboard, the
  published schema — has to learn to honour it, with a wrong default at every site that forgets.
  Swelter publishes measurements; a forecast product is a different product and would deserve its
  own ADR.
- **Filter later, in `aggregate` or `alerts`.** By then the row is in the store and in the export,
  the integrity chain has hashed it, and `--accumulate` has carried it into tomorrow. The boundary
  belongs where the response is still a response.

The clip is a comparison against a real instant, so it is a wall-clock read — the only one in the
pipeline. It does not weaken ADR 0035: everything downstream still derives "now" from the buckets
present, and those buckets are now guaranteed to be hours that have happened. `alerts`'s
reproducibility test (`test_feed_timestamp_is_data_derived_not_wallclock`) is unaffected, because
what varies with the clock is *which hours are fetched*, never how a given store is rendered.

This is scoped to Open-Meteo, the only adapter that serves predictions. OpenAQ and Sensor.Community
return measured readings, and inventing a general "no future timestamps" rule at ingest would put a
clock in the write path for a defect neither of them has.

## Consequences

`data_hour` in `publish-manifest.json` is at or before the deploy that wrote it. The Now card, the
alerts feed and the Atom feed describe an hour that has occurred. A Danger heat alert is about
weather that happened.

Costs and accepted trade-offs:

- **Up to an hour of the freshest model output is dropped** when the current hour's value is
  published slightly ahead of the hour it stamps. Clipping at the hour boundary rather than at the
  instant was considered and rejected: it re-admits partial-hour predictions to save one hour of
  latency on a daily deploy.
- **`to_observations` is no longer clock-free.** Its default now depends on the wall clock, which
  makes an un-parameterised call non-deterministic across days. Every test passes an explicit
  instant, and the parameter is documented as the reproducibility seam.
- **The adapter drops data with no per-row record of the drop.** The count is not published; the
  fetch logs the reference instant it clipped against, which is what makes the deploy log auditable
  without adding a "rejected observations" artifact for rows that were never observations.
- **A store accumulated before this change still holds forecast rows.** They are immutable raw
  observations and are not rewritten. They age out of the newest bucket within a day and the next
  fetch stops adding more; a store that must be clean is rebuilt from a fresh fetch.

Executable evidence:

- `tests/test_openmeteo.py::test_to_observations_never_emits_an_hour_that_has_not_happened`
- `tests/test_openmeteo.py::test_to_observations_clips_against_the_wall_clock_when_no_reference_is_given`
- `tests/test_openmeteo.py::test_fetch_does_not_let_a_forecast_hour_become_the_newest_reading`

The acceptance contract is maintained under F-14 in
[`../ACCEPTANCE-TEST-MAP.md`](../ACCEPTANCE-TEST-MAP.md).
