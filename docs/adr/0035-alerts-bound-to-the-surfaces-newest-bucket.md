# ADR 0035: Bind alerts to the surface's newest bucket, not an unbounded latest-per-cell scan

- Status: Accepted
- Date: 2026-08-06
- Deciders: Chelsea Kelly-Reif

## Context

ADR 0010 decided the alerts feed should scan "the latest hour of the aggregated surface" and raise
one alert per cell crossing a documented danger floor. `alerts.build_feed`'s docstring restated that
promise ("an alert is about now, not an hour last week"), but no code enforced it: there is no clock
and no max-age check anywhere in `alerts.py`, in `Surface.latest_by_cell()` (which is genuinely
per-cell latest — the most recent reading *that cell ever had*, with no floor on how old that is),
or in `cmd_alerts` (which passes `build_feed` the entire store history via `store.all()`).

The measured consequence (issue #148): a node that stops reporting keeps its last reading in
`latest_by_cell()` forever. If that last reading crossed a danger floor, `build_feed` keeps emitting
an alert for it, stamped `provisional: false`, inside a feed whose own `bucket` ("generated") is the
current newest hour from every *other* node still reporting. A neighborhood whose sensor died
mid-heat-wave gets a standing Danger alert for the rest of the summer; one whose sensor died during a
cool spell gets a standing all-clear, the worse failure mode. The alert entry's own `bucket` field is
honest about when the reading was taken, so a reader who inspects it is not misled — this is a
correctness bug in what gets published as *active*, not a dishonesty bug in what a single field
claims (hard rule 4 is intact) — but the docstring's guarantee is exactly the part a subscriber
relies on without reading each entry's `bucket`.

`web/app.js` does not have this bug: `activeAlerts()` filters `c.bucket === bucket` where
`bucket = latestBucket()`, the max of every cell's bucket across the whole loaded surface. So the
feed and the map could show different things for the same cell at the same moment, from the same
underlying data — a subscriber and a dashboard visitor could disagree about whether a block is
currently in danger.

## Decision

Bound `build_feed` by the surface's newest bucket, matching what `web/app.js` already does. A new
`Surface.newest_bucket()` (`aggregate.py`) returns `max(cell.bucket for cell in surface.cells)` —
every cell, every parameter, not just the ones a given hazard pack alerts on. `build_feed` computes
this once, keeps using `latest_by_cell()` to find each cell/parameter's most recent reading exactly
as before, and now only raises an alert when that reading's `bucket` equals the surface's newest
bucket. A cell/parameter whose latest reading predates the newest bucket elsewhere on the surface no
longer clears the check — it stays visible to anyone browsing history (the reading is not deleted or
hidden), but it cannot keep broadcasting a danger crossing into a feed stamped as current.

This needs no wall clock: "now" is still derived entirely from which hour buckets are present in the
data, so `tests/test_alerts.py::test_feed_timestamp_is_data_derived_not_wallclock` holds unmodified
and a re-run against the same store stays byte-for-byte reproducible.

`Surface.newest_bucket()` is not a new concept invented for this fix — it names a pattern this
codebase already had in three places, previously duplicated as an inline `max((cell.bucket for cell
in surface.cells), default=...)`: `cli.py`'s `_write_web_sample` (the `sample-surface.json` the
dashboard loads first) and `cmd_publish`'s `data_hour` manifest field. Centralizing it means the
feed, the static snapshot that seeds `web/app.js`'s `state.buckets`, and the publish manifest all
read "now" the same way by construction, not by three independently-typed expressions that could
silently drift apart. `web/app.js`'s `latestBucket()` — `state.buckets[state.buckets.length - 1]`,
where `state.buckets` comes from exactly those baked/served payloads — resolves to the identical
value for the identical surface. `cli.py`'s two existing call sites were refactored onto the new
method with no change in the value each already produced (`_write_web_sample`'s `default=None`
branch and `cmd_publish`'s `default=""` branch are both preserved).

`alerts.py`'s docstring is updated to describe this bound instead of the guarantee it previously
stated but did not implement.

## Alternatives considered

- **An explicit `max_age_hours` parameter** (the issue's option 2). More flexible for a network on a
  non-hourly interval, but it still needs a reference instant to measure age *from*, and the only
  reference instant available without a wall clock is the surface's own newest bucket — so this
  option reduces to option 1 plus an extra tunable that has no current caller and no cited default.
  Deferred until a network actually needs a looser bound than "the latest bucket present."
- **Publish a stale-node signal instead of suppressing** (the issue's option 3). The most
  informative option — a subscriber could see "this cell hasn't reported since X" rather than
  silence — but it does not fix the reported harm: a Danger headline would still appear for a dead
  node, just with an added field a naive reader (an RSS client, a chat webhook that reads
  `.headline`) has no reason to check. The measured failure is the standing headline itself, so
  suppressing publication is the fix; a staleness field on the *cell*, surfaced elsewhere (the map
  already shows a node's last-seen bucket), is a reasonable follow-up but not a substitute.
- **Do nothing beyond the docstring** (state the actual per-cell-forever behavior instead of "about
  now"). Rejected: it would make the code and the docs agree, but leaves the actual harm — a dead
  node broadcasting Danger indefinitely, and the feed disagreeing with the map — unfixed.

## Consequences

A cell whose sensor has gone dark stops generating a standing alert once any other part of the
surface has moved past its last reading's hour; the feed and `web/app.js` now derive "current" from
the same reference instant by construction. `Surface.newest_bucket()` is a small new public surface
on `Surface` that other "what hour is this artifact as of" call sites should prefer over re-deriving
their own `max(...)` expression.

One accepted trade-off: the reference instant is the surface's global newest bucket across every
parameter, not per-parameter. If a network's air-quality nodes are all momentarily behind its heat
nodes (or vice versa), a genuinely fresh but not-globally-newest reading is held back from alerting
for that one bucket, exactly mirroring what the map already does in the same circumstance — this
keeps the two surfaces in agreement rather than introducing a second, alerts-only definition of
"current." A network whose alerting parameters and non-alerting surface parameters routinely report
on different cadences may see this bound more often than a single-cadence network; no such network is
in the fixture data today, and this is a candidate follow-up if it becomes a problem in practice.

Executable evidence:

- `tests/test_alerts.py::test_dead_node_stale_reading_does_not_raise_an_alert`
- `tests/test_aggregate.py::test_newest_bucket_is_the_max_across_every_cell_and_parameter`
- `tests/test_aggregate.py::test_newest_bucket_is_none_for_an_empty_surface`
- `tests/test_alerts.py::test_feed_timestamp_is_data_derived_not_wallclock` (unchanged, still green)

The acceptance contract is maintained under F-18 in
[`../ACCEPTANCE-TEST-MAP.md`](../ACCEPTANCE-TEST-MAP.md).
