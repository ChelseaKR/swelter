# ADR 0036: Publish the absence when an area stops reporting, instead of going quiet about it

- Status: Accepted
- Date: 2026-08-14
- Deciders: Chelsea Kelly-Reif

## Context

[ADR 0035](0035-alerts-bound-to-the-surfaces-newest-bucket.md) fixed the reported half of issue #148:
a node that stops reporting can no longer keep broadcasting the danger crossing it was in when it
went dark. Bounding `build_feed` by the surface's newest bucket removes the standing Danger headline.

It removes the block from the feed entirely, though, and that is the half issue #148 called "the
worse half" when it described a sensor that dies during a cool spell: *"a neighbourhood whose sensor
died during a cool spell gets a standing all-clear."* Suppression alone gives every dark block the
cool-spell treatment. An alerts feed's whole meaning is "here is what is dangerous right now", so a
block it does not mention is read as a block that is fine. `count: 0` reads as "nothing is wrong
anywhere", when what it actually says is "nothing crossed a floor among the cells still reporting."

The two states this collapses together are not equivalent, and they are not equally safe to confuse:

| | Before ADR 0035 | After ADR 0035 alone | The truth |
|---|---|---|---|
| Node dark, last reading was Danger | Standing `Danger` | (nothing) | Unknown |
| Node dark, last reading was fine | (nothing) | (nothing) | Unknown |
| Node reporting, reading is fine | (nothing) | (nothing) | Not crossing a floor |

Rows two and three are indistinguishable to a subscriber, and swelter has to be able to tell someone
that it cannot tell. That is hard rule 4 — caveats travel with values — applied to the case where
there is no value: missingness is one of the things the rule requires to keep travelling, through
"alerts" specifically, and today it does not.

There is a second, mechanical problem. Atom entries persist in a reader. A subscriber who received a
`Danger` entry for their block keeps seeing it; ADR 0035 stops swelter re-publishing it, but nothing
retracts the copy already sitting in the reader. The last word on a block whose sensor died mid-heat
wave stays "Danger", indefinitely, in every reader that fetched it.

ADR 0035 rejected the issue's option 3, "publish it with an explicit staleness field", because it
kept the Danger headline for a dead node — the exact harm being fixed — behind a field a naive
reader has no reason to check. That reasoning holds and is not reversed here. It also said in as
many words that a staleness signal "is a reasonable follow-up but not a substitute". This is that
follow-up, in the form that does not reintroduce the harm: not an alert with a flag on it, but a
different kind of record that has no severity and no value to misread.

## Decision

`build_feed` publishes a `StaleArea` record for every cell/parameter whose latest reading predates
the feed's bucket — the same cells ADR 0035 suppresses — in a `stale` array beside `alerts`.

The record deliberately carries **no value**: no `value`, `severity`, `unit`, `aqi`, or `threshold`.
The last reading is not a measurement of now, and republishing it, even labelled, hands a consumer a
number to put in a "current conditions" column. What it carries instead is the shape of the absence:

- `status: "no-current-reading"` — self-describing, so a consumer that flattens the feed's arrays
  still cannot mistake it for a reading.
- `last_bucket` and `hours_since_last_reading` — when the block was last heard from, and how long
  ago in whole hours relative to the feed's own bucket. `null`, never `0`, when the gap's size is not
  computable: zero would read as "it reported just now", the reassuring answer.
- `withdrawn` — `true` when that last reading *did* cross a danger floor, so an alert for it was
  published before the node went quiet. This record retracts that alert. It does not report that the
  danger passed; it reports that swelter can no longer see.
- A plain-language `headline` (EN, plus the machine-drafted ES the rest of the feed already carries)
  that says there is no current reading and that swelter cannot tell whether the block is dangerous.

In Atom, each stale record is an entry carrying `<category term="no-current-reading"/>`, published
**under the same `<id>` as the alert it supersedes** and stamped with the *feed's* `<updated>`, not
the block's last bucket. Both details are load-bearing: a reader keys entries by id and ignores an
update stamped older than the copy it holds, so this is what replaces a standing Danger headline in
a subscriber's reader with the withdrawal.

`AlertFeed.for_area` narrows `stale` the same way it narrows `alerts`, so a resident subscribed to
one block is still told when that block goes dark. The dashboard's "Neighborhood alerts" panel says
the same thing the feed does: the status line names how many areas have no current reading, and each
is listed with no value and no "go to this reading" button, because there is no reading to go to.

`schemas/alerts.schema.json` requires `stale` and `stale_count`. A feed that omits them is not
asserting "nothing is unseen" — it is not answering the question, and it does not validate.

## Consequences

The feed distinguishes "not crossing a floor" from "cannot see", and a subscriber whose own block
goes dark hears about it instead of hearing nothing. A Danger entry already delivered to a reader is
retracted in place rather than left standing. `count: 0` keeps its old meaning for existing
consumers (no behaviour change to `alerts`), and the new information is additive.

Costs and accepted trade-offs:

- **The feed can get longer, proportionally to how much of the network is dark.** One entry per dark
  cell/parameter, in JSON and in Atom. That is the honest size of the gap; a network with many dark
  cells has a subscriber who needs to know that more, not less. In the committed demo fixture every
  cell reports in the newest bucket, so `stale` is empty and the baked artifacts gain only the empty
  array and its note.
- **A cell that never reported a parameter at all is not published as stale.** Only a cell/parameter
  that has reported before and is now behind the newest bucket appears. Publishing "unknown" for
  every parameter no node ever measured would be noise, not information. The limit is real and worth
  naming: this feed reports blocks that *went* dark, not the absence of coverage in the first place.
- **`hours_since_last_reading` measures against the surface's newest bucket, not the wall clock.**
  On a static deployment whose last publication is itself old, the number is the gap between two
  data timestamps, not the gap to right now. That keeps the artifact deterministic (a re-run
  reproduces it byte for byte), and the existing whole-feed staleness caveat still covers "this
  whole feed is old" separately in the dashboard.
- **A chat/SMS bridge that reads `.alerts[]` only will not post withdrawals.** `docs/alerts.md` now
  says so at the recipe and shows the second pass over `.stale[]`. swelter cannot enforce anything
  in a collective's own fork.

This does not reverse ADR 0035 and does not restore anything ADR 0035 suppressed: no danger crossing
from a stale reading is republished, and no stale record carries a severity or a value. A future
decision to attach a per-cell staleness signal to the *surface* (the map already knows each cell's
bucket) would supersede the dashboard half of this record, not the feed half.

Executable evidence:

- `tests/test_alerts.py::test_dead_node_is_published_as_no_current_reading_not_as_silence`
- `tests/test_alerts.py::test_dead_node_that_was_safe_when_it_died_is_still_published_as_unknown`
- `tests/test_alerts.py::test_stale_atom_entry_updates_the_alert_it_supersedes`
- `tests/test_alerts.py::test_one_area_subscription_still_hears_that_its_own_node_went_dark`
- `tests/test_alerts.py::test_an_unparseable_bucket_reports_an_unknown_gap_not_a_zero_hour_one`
- `web/tests/schema-contract.test.js::an alerts feed carrying a stale area validates, and one without `stale` does not`
- `web/tests/app.unit.test.js::area alert copy — an area the feed cannot see is said out loud, not left to an empty list`

The acceptance contract is maintained under F-18 in
[`../ACCEPTANCE-TEST-MAP.md`](../ACCEPTANCE-TEST-MAP.md).
