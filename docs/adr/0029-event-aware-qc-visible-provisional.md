# ADR 0029: Map suspicious-QC readings as visible provisional, never blank the map during an event

- Status: Accepted
- Date: 2026-07-18
- Deciders: Chelsea Kelly-Reif

## Context

QC labels a reading; it never deletes one (`qc.py`). But aggregation did delete: `_bucket_observations`
dropped every `QC_REJECTED` value before it could reach a cell — range, spike, flatline, and missing
alike (`aggregate.py`, `if obs.qc in QC_REJECTED: continue`). Two of those verdicts are heuristic
suspicion, not physical impossibility:

- **spike** — a departure from the local median greater than a per-parameter threshold. The onset of a
  wildfire-smoke front or a genuine pollution excursion looks exactly like this at a five-minute
  cadence.
- **flatline** — a run of identical values. A real calm stretch at the sensor noise floor can produce
  it.

So the worst hour of a real event is precisely when a flagged-then-dropped cell blanks the map — for
the residents who most need it. That inverts QC's own stated contract ("label, never delete") and
trips invariant 4 (caveats travel) and invariant 5 (a map is never the only way in, but the data must
be *there* to reach): dropping is not a caveat, it is silence.

Physical impossibility is different. A `range` value outside the parameter's plausible bounds, or a
`missing` marker, is not a measurement and must not be placed even provisionally.

## Decision

Split the rejection set and stop dropping suspicion.

- `models.py` gains `QC_UNMAPPABLE = frozenset({QC_RANGE, QC_MISSING})` (never placed) and
  `QC_SUSPICIOUS = frozenset({QC_SPIKE, QC_FLATLINE})` (placed, but never trusted). `QC_REJECTED`
  stays their union, so `node_health` still counts a spike or flatline as a flagged reading — a
  suspicious value is still evidence of a struggling node.
- `aggregate._bucket_observations` drops only `QC_UNMAPPABLE`. A suspicious reading flows to the
  existing provisional lane (it is already `is_trustworthy == False`, so it can never join the trusted
  mean), and the set of QC verdicts present in a cell is carried onto the cell as `qc_flags`.
- `CellReading.qc_flags` (a sorted tuple of verdict strings, empty for a clean-but-uncalibrated cell)
  travels through the surface GeoJSON/JSON, the CSV/JSON export, the data dictionary, and the
  dashboard legend/table/evidence panel, so a cell that is provisional *because it is suspicious* is
  visibly distinct from one that is provisional *because it is uncalibrated*. The exposure and NowCast
  derived cells inherit the flags of the component cells they are built from.

Implementation: `models.py`, `aggregate.py`, `export.py`, `dictionary.py`, `schemas/sample-surface.schema.json`,
and `web/app.js`. Acceptance evidence: the smoke-front and calm-week fixtures in `tests/test_aggregate.py`
and `web/tests/`, mapped under F-02 in `docs/ACCEPTANCE-TEST-MAP.md`.

## Consequences

- **Benefit.** A smoke front stays on the map, labelled provisional and flagged, through the event.
  The honest failure mode moves from *silence* to *a visible, caveated value* — which residents,
  screen-reader users, and exports can all read.
- **Cost.** One new consumer-visible field (`qc_flags`) on the cell contract; the Python↔JS schema
  contract and both test sides move together. A provisional cell now carries more nuance, so the
  legend must teach two shades of provisional.
- **Trust boundary.** No value is ever promoted: a suspicious reading is provisional and flagged, never
  calibrated (invariant 3 intact). Range/missing stays unmapped (no physically impossible value
  reaches a surface).
- **Rejected trade-off.** Keeping the drop and "just widening the thresholds" would still blank real
  events that exceed any fixed threshold, and would weaken detection of true faults. Visible-provisional
  keeps both detection and presence.
- **Deliberately deferred (own follow-up PRs + ADRs):** (b) per-network QC thresholds in `network.yaml`
  (today the thresholds remain the documented module defaults); (c) multi-node corroboration, so a
  simultaneous excursion seen by ≥2 nodes is recognised as an event and not flagged at all; (d)
  variance-scaled flatline exemption at the sensor noise floor. A new superseding or extending ADR
  records each when built.
