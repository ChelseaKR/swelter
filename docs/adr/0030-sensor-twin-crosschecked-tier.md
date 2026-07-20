# ADR 0030: Derive a "cross-checked" drift smoke-alarm from twin agreement, never a calibration tier

- Status: Accepted
- Date: 2026-07-18
- Deciders: Chelsea Kelly-Reif

## Context

`qc.twin_agreement` already computed the inter-sensor agreement statistic between two co-located
low-cost nodes — paired residuals `value_a - value_b`, the population-standard-deviation spread, and
how many pairs matched — over a configured `TwinWindow`. What it did not do was *say anything about
that number*: a spread of 0.2 µg/m³ and a spread of 40 µg/m³ came back as bare figures a reader had
to interpret unaided.

The monitoring-gap evidence (EXP-09) says frontline networks often have no reference monitor to
co-locate against, so the calibrated tier is out of reach and every reading sits at `raw`. Those
networks still want a QC signal stronger than "raw": a drift smoke-alarm that fires when two sensors
that should agree stop agreeing. The hazard in building one is obvious and severe — a "cross-checked"
label is one careless step from reading as "accurate," which it is not. Two twins with the same
humidity bias agree tightly with each other while both reading high; agreement bounds **precision**,
never **accuracy**. Hard rule #3 forbids blurring raw and calibrated, and the US EPA's own guidance
treats co-location agreement among non-reference sensors as a data-quality/QC input, not a conferral
of regulatory-grade accuracy.

## Decision

Add an explicit, documented **cross-checked** verdict derived from the existing agreement statistic,
living entirely in QC/health metadata and dashboard copy. It never touches an `Observation` value,
never assigns a calibration version, never sets `uncertainty`, and no surface promotes a
cross-checked reading past provisional.

`TwinAgreement` gains a resolved `agreement_threshold` (the largest residual spread, in the
parameter's own unit, that still reads as agreement) and two derived properties:
`cross_checked` (a boolean) and `status`, a three-state drift smoke-alarm:

- `cross-checked` — at least `qc.MIN_TWIN_PAIRS` matched pairs and a spread within the bar;
- `diverged` — enough pairs, spread over the bar (the alarm fires; investigate the hardware);
- `insufficient-data` — too few matched pairs to judge, so no free `cross-checked` pass on thin
  evidence.

The bar comes from `qc.TWIN_AGREEMENT_THRESHOLD` (conservative per-parameter defaults), overridable
per pair by a new optional `TwinWindow.agreement_threshold` in `network.yaml`. The verdict rides
along under the existing `twin_agreement` key in `qc.health_report`, and is now surfaced by
`swelter qc` (JSON and human output), the live `/api/health.json` (wired to `config.twin_windows`),
and its static `sample-health.json` mirror. `docs/calibration.md` states plainly that cross-checked
≠ calibrated and gives the EPA non-regulatory framing.

Implementation: `src/swelter/qc.py` (`TwinAgreement`, `twin_agreement`, `twin_agreement_json`,
`MIN_TWIN_PAIRS`, `TWIN_AGREEMENT_THRESHOLD`), `src/swelter/config.py`
(`TwinWindow.agreement_threshold`), `src/swelter/cli.py` (`cmd_qc`, `_write_web_health`),
`src/swelter/server.py` (`/api/health.json`). Acceptance evidence: F-22 in
[`ACCEPTANCE-TEST-MAP.md`](../ACCEPTANCE-TEST-MAP.md), tested in `tests/test_qc.py`. This decision
extends, and does not supersede, the twin-agreement statistic the codebase already carried.

## Consequences

**A middle QC tier without a middle trust tier.** Networks with no reference monitor gain an honest,
public drift alarm — "our twins agree within ±X, and here is the month they stopped." The math is a
paired standard deviation against a documented bar; a reader can check it. But the value axis stays
strictly two-state (raw vs. reference-calibrated): cross-checked is metadata *about* raw readings,
not a third calibration state. Every map, table, export, API, and share surface still shows a
twin-checked node as provisional, exactly as before.

**The bars are conventions, not physics.** `TWIN_AGREEMENT_THRESHOLD` holds conservative starting
values, not empirically derived control limits; a network that knows its hardware should set
`agreement_threshold` per pair. A `diverged` verdict is a prompt to investigate, not a proof of
fault, and a `cross-checked` verdict is not a certificate of correctness — two identically-biased
twins pass it while both being wrong. The naming was chosen to survive an SME honesty read; if a
future surface ever renders this tier in a way that could read as accuracy, that is a hard-rule-#3
regression, not a copy tweak.

**Additive and back-compatible.** `agreement_threshold` defaults to `None` and the `twin_agreement`
block only appears when a network configures `twin_windows`, so the committed demo network — which
ships its twin example commented out — produces byte-identical `network.yaml` parsing and health
JSON. The `_twin_agreement_json` helper was renamed to the public `twin_agreement_json` so the CLI
and the health report share one serializer; the JSON gains `agreement_threshold`, `cross_checked`,
and `status` keys.

**Numbering.** Renumbered to ADR 0030 / F-25 at merge: sibling remediation branches also claimed
0027/F-22, and the collision was resolved by renumbering, as anticipated here.
