# ADR 0021: Lead with "register your own network" as the headline capability

- Status: Accepted
- Date: 2026-07-08
- Deciders: Chelsea Kelly-Reif

## Context

The 2026 positioning scan (`POSITIONING.md`, ADR 0008) names "survival = local ownership" as the
sharpest evidenced wedge: the one community air network that outlived its grant did so because
equipment ownership transferred to the community, while vendor-run networks wound down when cost and
maintenance were not owned locally. swelter already encodes this — Phase 4 built `network.yaml`,
`config.public_location()`, and `ADD-YOUR-NEIGHBORHOOD.md` specifically so a community could take
over without touching source code — but the roadmap and positioning docs described it as
infrastructure, not as the pitch. A funder or a partner org skimming `POSITIONING.md` or
`FUNDER-EVIDENCE-PACK.md` before this change would read "trust layer" and "compound exposure" before
ever reaching the fact that they can run the whole thing themselves, on their own hardware, with no
account and no company that can shut it off. That ordering undersells the project's actual
differentiator against the closest institutional analogs (Common SENSES, the wound-down Array of
Things): swelter does not just publish open data, it hands over the whole instance.

Making replicability a first-class, table-scored property (rather than only narrative prose) also
keeps it honest to the claim-discipline the rest of `POSITIONING.md` holds itself to — a table cell
is checked against the same comparables and can be marked "no" or "partial" instead of only ever
appearing as an unfalsifiable adjective.

## Decision

Positioning and funder-facing material now lead with replicability — a community can stand up its
own instance by copying `network.yaml` and following
[`ADD-YOUR-NEIGHBORHOOD.md`](../ADD-YOUR-NEIGHBORHOOD.md), with no hosted dependency and no code
change — instead of treating it as a Phase 4 implementation footnote. This is a positioning and
packaging decision, not a new feature: the capability (Phase 4, already built) does not change.
What changes is where it sits in the story told to the four audiences in
[`POSITIONING.md`](../POSITIONING.md) and to funders in
[`FUNDER-EVIDENCE-PACK.md`](../FUNDER-EVIDENCE-PACK.md).

Concretely:

- `POSITIONING.md`'s one-sentence position now names "runs as your own instance, no account, no
  vendor" alongside the trust-layer claim, and the comparison table gains a
  **"Self-hostable, no vendor lock-in"** row so the replicability property is scored against the
  same six comparables as every other property, not left as prose alone.
- `POSITIONING.md`'s "Say" list adds the one-afternoon setup claim, scoped to what is true today
  (demo data and no hardware in an afternoon; real hardware takes longer) and cross-referenced to
  `ADD-YOUR-NEIGHBORHOOD.md` so the claim is checkable, not asserted.
- `FUNDER-EVIDENCE-PACK.md` adds replicability to the durability case: local ownership is already
  the cited, empirically-supported survival factor (Imperial County vs. Array of Things); this ADR
  makes the mechanism — copy `network.yaml`, no hosted dependency, scale-to-zero on a
  Raspberry-Pi-class host — an explicit, named piece of evidence rather than something a reader has
  to infer from the hard rules.
- `pyproject.toml`'s description and keywords name the replicable-network property, since PyPI /
  repo-search packaging metadata is one of the places a prospective adopter first meets the project.
- `ROADMAP.md` marks this Phase 5 item done and points at this ADR, matching the pattern set by
  Phase 5 item 1 (ADR 0009).

## Consequences

This is a documentation and packaging change with no code, schema, or API surface touched — by
design, per the roadmap item ("largely docs and packaging, little new code") — so it carries no new
test surface and does not move any metric in the ROADMAP.md ledger. The risk is the opposite of
usual: overstating readiness. The comparison-table row and the "Say" claim are worded to match what
`ADD-YOUR-NEIGHBORHOOD.md` actually delivers today (a working demo network in an afternoon; real
hardware and real co-location take longer), and neither claims zero operational burden — a named
local steward is still required (`POSITIONING.md`, "risks and failure modes"). If a future PR changes
what `ADD-YOUR-NEIGHBORHOOD.md` promises, this ADR's claims need to move with it or they become the
overstatement claim discipline exists to prevent.

Last verified: 2026-07-08. Recheck cadence: whenever `ADD-YOUR-NEIGHBORHOOD.md`'s setup steps change,
or alongside the annual competitive-table recheck cadence in `POSITIONING.md`.
