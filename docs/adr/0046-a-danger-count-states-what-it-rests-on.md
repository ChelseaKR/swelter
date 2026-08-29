# ADR 0046: A danger count states what it rests on

- Status: Accepted
- Date: 2026-08-27
- Deciders: Chelsea Kelly-Reif

## Context

Two published artifacts count danger: `exposure_brief.count_danger_days` counts calendar days for
a resident or organizer, and `chronicle._Tally` counts cell-hours for an official or a health
department. Both are explicitly decision-facing. The brief's own docstring says it "hands an
organizer sourced facts to build [a funding or advocacy] case with"; the chronicle's says officials
"act on events, not dashboards".

Both decided "Danger" purely from `cell.mean`, through `alerts.crossing`, and neither looked at
`cell.provisional` or `cell.qc_flags`. So a single QC-flagged spike — the pipeline's own "do not
trust this as a measurement" verdict — became a full Danger day or Danger hour, and the published
record carried no indication that its evidence was flagged or uncalibrated. Measured on `main` at
`1f7bd62`, from a window whose only crossing is one `spike` reading among four ordinary ones:

```text
cell.mean 95.0  cell.provisional True  cell.qc_flags ('spike',)
count.days_observed 1  count.danger_days 1
brief.lines() ['Oak & 4th: heat index reached the Danger range (≥39.4 °C) on 1 of 1 day(s) ...']
cc.danger_hours 1  cc.calibrated_readings 0  cc.provisional_readings 5
```

No calibrated reading exists anywhere in that window, and the sole Danger evidence is a value QC
already flagged. Both artifacts reported a plain, unqualified Danger day and Danger hour.

The live alerts feed does not do this. `alerts.build_feed` runs the *same* `crossing()` test and
attaches `provisional=reading.provisional` to every `Alert`, rendering it in the headline. The
threshold logic was shared between the three views on purpose, so they "can never silently drift
apart"; the caveat that belongs with it was never carried across. That is a direct miss against
hard rule 4, "caveats travel with values ... in the UI, exports, alerts, and share artifacts", and
against invariant 4 in the agent contract.

The obvious-looking fix — exclude suspicious cells from the crossing test — is the wrong one. It
would blank exactly the hours ADR 0029 exists to keep visible: the onset of a smoke front or a
genuine excursion looks like a spike at a five-minute cadence, and dropping it re-creates the
silence that ADR replaced with a visible, caveated value.

## Decision

Keep counting every crossing, and publish how much of the count swelter vouches for.

- `DangerDayCount` gains `danger_days_provisional` and `danger_days_qc_flagged`: of the counted
  Danger days, how many rest *entirely* on provisional readings, and how many entirely on readings
  QC flagged as `spike` or `flatline`. "Entirely", not "any" — one calibrated, unflagged crossing
  is enough for that day's verdict to stand on evidence the pipeline vouches for, and calling such
  a day provisional would overstate the doubt as badly as omitting it understates it.
- `CellChronicle` gains `danger_hours_provisional` and `danger_hours_qc_flagged`, the same split at
  hour granularity, where each cell-hour has exactly one heat-index reading so no "entirely"
  question arises. `Chronicle` exposes network totals as properties.
- Both counts are strict subsets: `qc_flagged <= provisional <= danger`, guaranteed because
  `aggregate._build_cells` only ever attaches `qc_flags` on the provisional branch, and the derived
  exposure and NowCast cells inherit `provisional` from any flagged component.
- The split is rendered everywhere the count is. `ExposureBrief.lines()` gains an evidence sentence
  directly under the danger sentence; `DangerDayCount.as_record()` gains both keys; the chronicle
  headline, the per-cell table, the always-rendered "what the network could not see" section, and
  the `swelter chronicle` stderr summary all carry it.
- The evidence line is rendered at zero as well, whenever there is a Danger verdict to qualify.
  "Nothing here is in doubt" is a claim, and stating it is what keeps a well-evidenced count and a
  shaky one from reading identically — the same discipline that already makes the chronicle's
  "could not see" section render at zero gaps.

Implementation: `src/swelter/exposure_brief.py`, `src/swelter/chronicle.py`, `src/swelter/cli.py`.
Acceptance evidence: `tests/test_exposure_brief.py` and `tests/test_chronicle.py`, mapped under
F-19 and F-22 in `docs/ACCEPTANCE-TEST-MAP.md`.

## Consequences

- **Benefit.** A number lifted out of a brief or a chronicle carries its own confidence. An
  organizer quoting "Danger on 12 of 30 days" can see, in the sentence underneath, whether that
  rests on calibrated measurement or on readings the pipeline flagged, and so can the agency
  reading the memo.
- **Cost.** Two new fields on each of two published record shapes, a second sentence in every brief
  that has a Danger day, and two more columns in the chronicle's per-cell table. Callers pinning
  the brief's line count or the table's column count change with it; three existing tests encoded
  exactly that and were updated.
- **Trust boundary.** No value moves. Nothing is dropped, nothing is promoted, no reading changes
  its calibration state, and no cell is ranked, scored, or compared. This is descriptive metadata
  about evidence quality, which keeps it inside the limits ADR 0027 set for the chronicle and
  ADR 0018 set for the brief; neither is superseded, both are extended.
- **Rejected alternative — exclude flagged cells from the crossing test.** Restores the ADR 0029
  blanking during exactly the events these artifacts exist to describe.
- **Rejected alternative — count a day as provisional if *any* crossing that day was.** A day with
  a calibrated 41 °C hour and an unrelated flagged spike would read as unevidenced, which is a
  different kind of dishonesty and would make the caveat worthless by making it universal.
- **Rejected alternative — a single "untrusted" count merging the two.** Uncalibrated and
  QC-flagged are different claims about a reading, and ADR 0029 built `qc_flags` precisely so the
  two shades of provisional stay distinguishable. Merging them here would undo that at the point
  where it matters most.
- **Deliberately deferred.** The zero-Danger-day case is untouched: a brief still reports "Danger
  on 0 of 30 days" without saying whether those 30 days were themselves measured on calibrated
  evidence. That is the "absence is not an all-clear" question ADR 0036 answered for the alerts
  feed, and answering it here means deciding what a *negative* finding's confidence should look
  like. It needs its own record, not a silent inclusion.
- **Deliberately deferred.** `ExposureBrief.lines()` still opens every line with "heat index" and
  "°C" regardless of the parameter counted, so a `pm25_ugm3` brief renders an AQI floor as a
  temperature. Pre-existing, unrelated to evidence quality, and worth its own fix.
