# ADR 0008: Position swelter as the open trust layer for neighborhood heat-and-air, and hold claim discipline

Date: 2026-06-18. Status: accepted.

## Decision

swelter's market position is the open, community-owned **trust layer** for neighborhood
heat-and-air exposure: calibrated readings, each carrying a calibration version and a 1-sigma
uncertainty, calibrated and raw never mixed, locations snapped to a privacy grid, served through
open standards (OGC SensorThings, CSV, JSON, Datasette), governed by the hosting collective. The
differentiator is the **whole set**, not any one feature — a 2026 scan found every comparable tool
(PurpleAir, OpenAQ, AirNow Fire and Smoke Map, Clarity, IQAir, CAPA Heat Watch) holding only one to
three of these properties. The full landscape, audiences, and funding path are in
[`../POSITIONING.md`](../POSITIONING.md).

With the position comes a **claim-discipline rule** that binds docs, dashboard copy, and external
material: state only what holds. Specifically, do not claim swelter uniquely measures heat (PurpleAir
and OpenAQ carry temperature; CAPA maps heat), do not claim humidity-aware PM calibration is novel
(it is the EPA Barkjohn US-wide standard swelter follows), do not claim rival platforms capture your
data when they do not (e.g. Clarity lets cities keep ownership), and never imply regulatory-grade
output (EPA classifies low-cost sensors as non-regulatory) — say "credible and auditable" instead.
Where uniqueness rests on not finding a competitor that does something, phrase it as that, not as an
absolute negative.

## Why

The credibility problem in low-cost environmental sensing is overstatement: uncalibrated data gets
dismissed, and inflated claims accelerate the dismissal. The honest, narrow position is also the
defensible one — calibration with published uncertainty is exactly what regulators and researchers
say is missing and what prevents the trust collapse documented for these networks, so leading with it
turns swelter's hard rules (ADRs 0002, 0003, 0004, 0006, 0007) into the market story rather than
fine print. Holding claim discipline protects the one asset a community-owned tool cannot buy back
once spent: trust. Writing the position and the do-not-say list down as a decision of record keeps
later copy — a new export banner, a grant abstract, a dashboard string — from quietly drifting into
claims the project cannot stand behind, the same failure the "block-by-block" wording correction on
the dashboard already fixed once.

## Known weakness / Consequences

A position is a snapshot of a moving market. The competitive table will age as named tools change
licences or add heat surfaces, and the funding ordering (philanthropy first) reflects a specific
2025–2026 moment of federal environmental-justice funding being cut and litigated — both need
rechecking on the cadence in `POSITIONING.md`, not treating as settled. The claim-discipline rule is
a review burden with no automated gate: nothing in `make verify` checks prose for overstatement, so
it depends on reviewers holding the line. The "whole set" framing is honest but harder to pitch than
a single silver-bullet claim, and the closest analog (Boston's Common SENSES: community-sited
heat-and-air, university- and city-backed) means "community-owned and open" — not the sensor combo —
has to carry the differentiation.

Last verified: 2026-06-18. Recheck cadence: with `POSITIONING.md` — competitive and demand claims at
least annually, funding status quarterly under current litigation.
