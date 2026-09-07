# ADR 0053: A season is a property of the data, not of the run

- Status: Accepted
- Date: 2026-09-07
- Deciders: swelter maintainers

## Context

ADR 0031 made alert thresholds into hazard packs — versioned, cited data a network selects with
`hazard_pack:`. ADR 0050 added the smoke pack and explicitly declined the third thing EXP-13 asked
for, `hazard_pack: auto-season`, on one specific ground, recorded in `docs/alerts.md`:

> switching packs by calendar month would make the published artifacts depend on the date the
> pipeline ran, and the gate that holds the committed demo artifacts to a fresh replay would
> disagree with itself across a month boundary. It needs its own design.

That objection is exactly right and it is not an argument against the feature. A network whose
hazard genuinely changes with the year — heat in July, smoke in October, cold in January — has to
edit `network.yaml` four times a year today, or accept alerting on the wrong hazard for months at a
time. The gap is real. What was missing was a rule for *which* clock the switch reads.

There is a second question the deferral did not name, and it is the harder one: a calendar mapping
months to hazards is a claim about a place's climate. Shipping one would mean asserting a
climatology everywhere swelter runs.

## Decision

### 1. The month comes from the surface's newest bucket

`alerts.pack_for_surface` resolves the pack from `Surface.newest_bucket()` — the same reference
instant `build_feed` calls "now", the map's `latestBucket()`, and the hour the feed stamps itself
with. Nothing in the path reads a wall clock.

That is what makes the feature shippable. A replay of a fixed store selects the same pack forever,
so `scripts/demo_artifact_check.py` compares a committed artifact against a replay that cannot
drift across a month boundary. It also makes the switch *reviewable*: the month published beside
the feed's own timestamp can be checked against it by a reader.

Measured, not asserted. Replacing `month_of(newest)` with `datetime.now().month` turns two tests
red, and one of them prints today's month appearing in a record whose data is from October.

### 2. A surface with no cells has no month, and publishes none

An empty surface falls back to the default pack and emits **no** `pack_selection` record. Emitting
a month derived from anything else would be a date invented to fill a field — an absence rendered
as a value (ADR 0037), in a field whose whole purpose is to let a reader check the switch.

### 3. The calendar is the network's; only the packs are swelter's

`season_calendar` is declared in `network.yaml`. swelter ships packs, each carrying cited
thresholds, and ships **no calendar**.

The alternative — a built-in "northern hemisphere" calendar — would have swelter asserting that
fire season runs September to November and that winter is a hazard, for every place it runs. The
collective in Fresno and the collective in Duluth do not have the same year, and neither needs
swelter's opinion about it. This is the same line ADR 0050 drew inside the smoke pack, where the
EPA breakpoint is EPA's and the three-cell minimum is stated as swelter's own.

### 4. An incomplete calendar is refused, not defaulted

`config_concerns` / `swelter doctor` reject a calendar that does not cover all twelve months
exactly once, names an unknown pack, or claims a month twice. An uncovered month would resolve to
heat in a place whose calendar deliberately omits it — the same safety surprise
`_hazard_pack_concerns` already refuses one level up, where a winter network believes it alerts on
cold and does not.

`pack_for_month` raises rather than falling back, so reaching it with an uncovered month means
validation was bypassed and says so, instead of quietly alerting on heat in a month the network
called smoke season.

A `season_calendar` on a network that names a *single* pack is likewise an **error**, not something
ignored. A calendar nothing reads is a host believing they configured a season and did not.

### 5. Override keys are validated against the whole calendar

A seasonal network uses several packs across the year and may legitimately set `heat_index_c` *and*
`wind_chill_c`. Validating overrides against one pack would reject the others as unknown — and an
ignored `alert_thresholds` key is precisely how a host comes to believe they lowered a danger floor
and did not (the case `alerts.resolve_thresholds` already documents).

### 6. The surface carries the union of the calendar's parameters, all year

The rollup happens before the month is knowable — the month comes from the surface being built — so
`aggregate` takes the union across every pack the calendar can select. A smoke/cold network
therefore carries wind chill through July: a wider surface, not a wrong one. The alternative is a
January in which the cold pack has nothing to read, because a cell that was never aggregated cannot
be alerted on later.

### 7. The switch is published, because it happened without the configuration changing

A seasonal feed carries `pack_selection` (`pack`, `selected_by: season-calendar`, `month`). A pack
that changes while `network.yaml` does not is an unexplained change in what the network calls
dangerous unless something on the surface records it.

It is emitted **only** for a seasonal feed. ADR 0031's promise — a network naming no pack produces a
byte-identical feed — is held by a test that compares *serialized* feeds rather than checking fields
one by one, because the smoke pack's first version broke exactly this promise by adding a key to
every feed and a field-by-field test did not notice.

## Consequences

A collective can write its year down once and stop editing `network.yaml` seasonally. The published
feed says which pack is in force and why, and the artifact gate stays deterministic across a month
boundary — the objection ADR 0050 raised is answered rather than worked around.

The costs are two, both accepted deliberately. A seasonal surface is wider than it needs to be in
any single month, which is more rows in the store's rollup for a network with several packs. And
the calendar is a configuration burden this project cannot lift: a collective that gets its own
seasons wrong will alert on the wrong hazard, and swelter can only refuse a calendar that is
*incomplete*, never one that is merely mistaken about its own climate.

Dashboard copy naming the active pack to a resident is **not** shipped here. It is a published
resident-facing surface change and needs the accessibility and Spanish review paths any such change
needs (#106); #236 stays open for it.

A superseding ADR is needed if the pack ever has to change within a month (a declared smoke episode
overriding the calendar), or if `pack_selection` graduates from a seasonal-only key to something
every feed carries — which would be a data-schema decision, not a side effect.
