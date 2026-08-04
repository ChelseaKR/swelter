# ADR 0039: Decide whether evidence requires sensors before planning hardware

- Status: Accepted
- Date: 2026-07-09
- Deciders: Chelsea Kelly-Reif

## Context

Sensor projects often begin with procurement and discover the actual decision, consent process,
maintenance load, and evidence limits later. That sequence creates abandoned hardware and claims
that outlive their calibration. swelter's strongest product boundary is its trust discipline, so
the first planning tool should be able to say that existing public data is enough, that an urgent
decision cannot wait for a study, or that hardware is inappropriate until a community mandate and
steward exist.

A declarative rule table keeps that safety posture reviewable. Tests enumerate every possible input
combination, confirm that each reaches a complete outcome, and assert that missing governance,
missing stewardship, urgent timelines, and raw uncalibrated readings cannot unlock network-scale
deployment.

## Decision

Ship a framework-free project planner at `/planner/` that begins with the decision a community
needs to make, not a sensor count. Six closed-choice inputs cover purpose, evidence already in hand,
decision window, stewardship capacity, community governance, and calibration readiness. An ordered,
declarative decision table returns one of these postures:

- do not deploy until governance or stewardship exists;
- use trusted public evidence for an urgent decision;
- prove the gap with public data before adding hardware;
- stop expansion and calibrate existing raw readings;
- run or strengthen a bounded pilot; or
- operate a governed network in reviewable stages.

The result includes next moves, evidence needed before the next gate, and red lines. The form has no
free-text, identity, contact, or location field. It makes no network request, creates no account,
uses no browser storage, and transmits nothing. Copy and print are explicit local actions. Public
locations remain coarse by default, and no recommendation can promote raw readings to trustworthy.

## Consequences

The planner is decision support, not community consent or a substitute for public-health,
calibration, legal, or research-method review. Closed choices improve privacy and make the rule
table testable, but they compress local context. The copied plan must therefore be discussed and
amended by the hosting collective rather than treated as an automated approval. The initial route
is English-only; an indexable Spanish route and equivalent native copy belong in the language SEO
work rather than a runtime selector that search engines cannot read independently.

Last verified: 2026-07-09. Recheck cadence: each release that changes governance, calibration,
public-location, or project-readiness rules.
