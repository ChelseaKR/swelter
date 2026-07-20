# ADR 0027: Generate a citable post-event chronicle, descriptive counts only

- Status: Accepted
- Date: 2026-07-18
- Deciders: Chelsea Kelly-Reif

## Context

Officials and health departments act on *events* — a July heat wave, a wildfire-smoke episode — not
on a live dashboard. After a window closes they need a short, attachable account they can put in a
council memo or an after-action report, with every figure traceable to the archive. swelter already
answers the resident-facing historical question ("this block ran Danger N days") in
[`exposure_brief.py`](../../src/swelter/exposure_brief.py) ([ADR 0018](0018-exposure-brief-and-equity-context.md)),
and the compound heat-and-air exposure surface ([ADR 0009](0009-compound-heat-air-exposure-surface.md))
already places heat and air on one ordinal. What was missing is the institution-facing, event-scoped
view: for a bounded `[from, to]` UTC window, how many cell-hours reached the NWS "Danger"/"Extreme
Danger" tier, how many were compound, and — first-class — what the network *could not* see.

The forces that shape the decision are honesty rules, not features. A count of hours next to a
neighborhood name is one editorial step away from an implied ranking, and one citation away from an
implied health-outcome claim; both are hard project rules the coverage-equity read
([`qc.coverage_equity`](../../src/swelter/qc.py)) already refuses. Uncertainty must not be relegated
to a footnote a busy reader skips. And a chronicle that silently omits its blind spots when there
happen to be none teaches readers to treat "we saw nothing" as "nothing happened."

## Decision

Add a pure module [`chronicle.py`](../../src/swelter/chronicle.py) and a read-only
`swelter chronicle --from <ISO> --to <ISO> --store <dir> [--out <file>]` command. The module composes
existing outputs only — it imports and never modifies them: the surface from
[`aggregate.aggregate`](../../src/swelter/aggregate.py) (heat-index cells and the derived
`exposure`/`compound` layer), reporting gaps from `qc.detect_gaps`, per-cell calibration coverage
from `qc.coverage_equity`, and the NWS tier from `models.heat_index_category`. Its only I/O is
reading the `[from, to]` window through the existing `Store` seam; everything else is a pure function
over already-parsed observations, so it is deterministic and testable offline.

A frozen `Chronicle` holds, per published cell, the Danger/Extreme-Danger cell-hours, the
compound-exposure cell-hours, and the calibrated-vs-provisional reading counts (coverage confidence),
plus the reporting gaps, the uncalibrated-cell count, the coverage-equity refusal note carried
verbatim, and a sha256 digest of the window's observations for citability. `to_markdown()` renders it
with the calibrated share in the **headline** (not a footnote) and an **always-present** "what the
network could not see" section — rendered even when there are zero gaps and zero provisional
readings. The output is descriptive counts and hours only: it never attributes a health outcome and
never ranks, scores, or compares neighborhoods. Acceptance evidence is feature **F-22** in
[`ACCEPTANCE-TEST-MAP.md`](../ACCEPTANCE-TEST-MAP.md), anchored to
[`tests/test_chronicle.py`](../../tests/test_chronicle.py).

## Consequences

Institutions get an event artifact whose every number is reproducible from the store and pinned by a
content digest, without swelter growing a new measurement path or a hosted dependency — the chronicle
is a view over data already published. Because uncertainty and blind spots are structural, not
optional, a chronicle cannot flatter the network by omission. Reusing `aggregate`, `qc`, and `models`
keeps the "Danger" definition identical across the live alerts feed, the exposure brief, and the
chronicle, so the three cannot quietly drift apart.

The costs and boundaries: the chronicle inherits every upstream limit (grid-snapped locations, the
provisional/calibrated split, model/estimated status), and it must never be presented as an
epidemiological analysis — the refusal to attribute outcomes or rank blocks is load-bearing, and
institutional wording still needs the public-health review gate the roadmap names before external
use. It reports over whatever history the store holds; multi-week windows depend on the accumulating
archive ([ADR 0013](0013-accumulating-fetch-store-via-actions-cache.md)). A future ADR should
supersede this one if a chronicle is ever asked to weight, normalize, or rank cells, or to make any
claim beyond descriptive counts — that would cross the same line this decision draws and
`qc.coverage_equity` already holds.
