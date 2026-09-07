# ADR 0050: A hazard that only one node can see is not an event

- Status: Accepted
- Date: 2026-09-07
- Deciders: swelter maintainers

## Context

`hazard_packs.py` shipped `heat` and `cold` (ADR 0031). The third pack EXP-13 named, smoke, was
deferred. For a California network that gap is the wrong half of the year: after heat season, the
hazard is smoke, and PM2.5 is the parameter a low-cost network measures best relative to model
output.

Two things had to be decided to ship it, and neither is obvious from the issue that asked for it.

**Which PM2.5 number a smoke alert is about.** `aggregate` publishes two: the hourly mean
(`aqi_window="hourly-mean"`) and the EPA NowCast (`aqi_window="nowcast"`), and it has always kept
them strictly apart -- `Surface.latest_by_cell` skips NowCast rows so the map never shows one in
place of the promised hourly mean. An hourly mean lags a plume by design, which is precisely the
case NowCast exists for and precisely the hour a resident is deciding whether to go outside.

**What makes several high readings one event.** A single node reading 300 ug/m3 is a node. It
might be a barbecue under the sensor, or a failing ADC. What distinguishes a smoke episode is that
it arrives across a neighbourhood at once. But an absolute floor alone would declare an event
every hour of a week-long episode, and would put a chronically poor airshed permanently "in an
event", which tells a resident nothing.

## Decision

### 1. A pack names the averaging window its alerts read, and never falls back

`HazardPack` gains `aqi_window`. Heat and cold keep `"hourly-mean"`, so a network that named no
pack produces a byte-identical feed. Smoke selects `"nowcast"`, and `Surface.latest_by_cell` gains
a keyword to make that a **selection, not a preference**: a cell with no NowCast row -- fewer than
three trailing hours exist, so `models.nowcast_concentration` returned `None` -- is simply absent
from a smoke feed. It does not fall back to the hourly mean.

Falling back would publish a number from one window under a feed that named the other. That is the
same class of error as publishing a stale reading as current (ADR 0036, issue #148): the value is
real, and the sentence around it is false. The feed carries `aqi_window` at its root so a consumer
never has to infer which number it is reading.

### 2. An event needs several cells that have each risen against their own past

`EventRule` is pack data, with a citation, exactly like a threshold. A cell qualifies when it is at
or above `floor` **and** has risen at least `rise` above its own reading `lookback_hours` earlier.
An event needs `minimum_cells` such cells in the same hour.

Both halves are per-cell and both are required. The rise is what makes it an episode rather than a
description of the airshed; the cell count is what makes it an event rather than a node.

The smoke rule's numbers are 35.5 ug/m3 (the 2024 EPA breakpoint where the AQI leaves "Moderate"),
a 20 ug/m3 rise over three hours, and three cells. **Only the first is EPA's.** The other two are
swelter's, and the citation says so in terms rather than attributing them to a standards body that
never set them: no published standard says how many sensors make a smoke event, because that
depends on a network's own density.

### 3. The event rule reads the hourly means, and the record says so

This is the decision that surprised us, and it is why the window lives on the rule as well as on
the pack.

**NowCast has no history.** `aggregate._nowcast_cells` derives exactly one NowCast row per cell, at
that cell's most recent bucket. There is no NowCast reading three hours ago and there never will
be, so a rise cannot be measured in that window at all. The first implementation asked for one and
got "no comparable earlier hour" on every surface, including surfaces in an obvious episode.

So the smoke pack **alerts on NowCast and detects its event on the hourly means**. Those are two
different questions -- "what is the air right now" and "has it climbed over three hours" -- and
each is answered in the window that can answer it. `HazardEvent.aqi_window` names the window the
verdict was measured on, rather than leaving a reader to assume it matches the alerts beside it.

### 4. The verdict is published whether or not an event is running, and "not determined" is its own answer

`HazardEvent` carries `evaluated`, `active`, `qualifying_cells`, `minimum_cells`, and a `reason`
sentence, and it appears on every smoke feed.

- A feed that carried the record only during an episode would let its absence mean two things,
  "checked, no event" and "this pack looks for no events", and the reassuring reading is the one
  swelter must never give by default. So the key is absent for packs with no rule and present with
  `active: false` for a pack with one.
- `evaluated=False` is not `active=False`. A surface with no cell having readings in both the
  current hour and the lookback hour cannot answer the question, and answering "no event" there
  would be an absence rendered as an all-clear. It gets its own sentence in EN and ES.
- A cell whose earlier reading is missing does not qualify and is **not** treated as a rise from
  zero. An absent reading is not a low reading.

## Consequences

- A network enables smoke by config alone, like every other pack. No fork, no deploy.
- Existing networks are untouched: a byte-identity test compares the serialized default feed
  against the heat feed, so a new key added to the feed fails there rather than slipping through.
- The event is network-wide by construction, so `AlertFeed.for_area` carries it into a
  single-block subscription unchanged. A resident subscribed to one block is still in the smoke.
- The Spanish strings are machine-drafted and labelled as such by the existing feed-level
  `translation` marker (#106 still tracks independent review). The event sentence is a swelter
  judgement about swelter's own rule, not a restatement of an EPA one, which is why the acceptance
  row asks for honesty-of-framing review of it specifically.
- **Not decided here:** `hazard_pack: auto-season`, which EXP-13 also proposes. Switching packs by
  calendar month makes the published output depend on the date the pipeline runs, which would make
  the committed demo artifacts and the gate that holds them to a fresh replay disagree with each
  other on a date boundary. That needs its own design for how the switch is recorded and how the
  artifact gate stays deterministic across it, and it is deliberately left out rather than shipped
  half-considered.
- **Not decided here:** resident-facing guidance copy. As in ADR 0031, the pack carries sourced
  pointers to the authority's own public guidance as provenance, never advice.

## Alternatives considered

**Read the event rule on NowCast anyway, comparing against the hourly mean three hours back.**
Rejected: it compares two different quantities and calls the difference a rise. The number would
move for reasons that are not the air changing.

**Declare an event on the absolute floor alone.** Rejected: it declares an event every hour of a
long episode and permanently in a poor airshed. The reader learns nothing from a light that is
always on.

**Let a cell with no NowCast row fall back to its hourly mean.** Rejected under decision 1. It is
the more useful-looking behaviour and the less honest one.

**Fold the smoke floors into the heat pack.** Rejected: a network that selects smoke should be told
exactly what it is now alerting on, and silently carrying heat thresholds into a smoke feed would
mean its floors no longer match its name.
