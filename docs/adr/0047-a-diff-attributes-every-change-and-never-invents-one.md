# ADR 0047: A diff attributes every change to one kind, and never invents one out of an absence

- Status: Accepted
- Date: 2026-09-06
- Deciders: swelter maintainers

## Context

`swelter verify-archive` proves nothing was tampered with. Nothing proved what *legitimately*
changed. A steward or a journalist holding two `sample-surface.json` files from different days
could only eyeball two GeoJSONs, and an organiser who says "the block got worse this week" had no
way to show whether the number moved or the calibration did — which are different claims about the
same cell, and only one of them is about the weather. ADR 0038 made every correction name its fit
precisely so that distinction could be drawn; nothing drew it.

Two hazards make this more than a convenience.

First, **a diff is where absence turns into arithmetic**. The natural implementation of "what
changed" subtracts one side from the other, and a cell that exists on one side only then reads as a
fall to zero — the exact failure ADR 0037 forbids, arriving through a tool built to explain data
rather than publish it.

Second, **an attribution is a claim**. Saying "this changed because the calibration changed" is a
statement a reader will repeat. A vocabulary that is open, or that quietly widens, lets a tool
assert a cause it did not establish.

Once `swelter diff`'s `kind` field is emitted in machine-readable output, consumers branch on it,
and it is a public contract whether or not it was intended as one.

## Decision

`swelter diff` (`src/swelter/diff.py`) attributes every difference to exactly one kind from a
closed vocabulary: `value_change`, `calibration_version`, `qc_state`, `source_or_rights_change`,
`absent_to_present`, `present_to_absent`, `schema_version_change`. The vocabulary is deliberately
the shape of `nearmiss`'s `tools/diff_datasets.py`, so two sibling projects answer "why is this
number different from last week's" in one language.

Three rules bind the implementation.

1. **Absence is never a delta.** A reading present on one side only is reported as
   `absent_to_present` or `present_to_absent`, carrying only the side that exists. No arithmetic is
   performed against a missing value and no `delta` key is emitted anywhere in the output. A
   recorded `null` — `uncertainty: null` means "no error bar, and here is why" (ADR 0035) — is a
   value and is compared as one; only a *missing key* is an absence.

2. **An unrecorded version is not a matching version.** If either input records no schema version,
   the report says so and says the two were *not compared*. Only two versions that are both
   recorded and different are a refusal, and `--allow-schema-skew` overrides that deliberately.

3. **Two readings are only compared when they describe the same instant.** The default alignment
   pairs by `(cell_id, parameter, bucket, aqi_window)`. `--align latest` compares each side's most
   recent reading per cell and parameter, and every record it produces carries both buckets,
   because a change between two instants must say which two.

An unknown field attributes to `value_change`, the least specific claim available, rather than to a
cause nothing established.

## Consequences

A steward can show whether a number or a fit moved, and a reviewer asked to trust a Danger-day
count (ADR 0046) can see what changed under it. The command is offline, stdlib-only, and
deterministic, so it can be run against archived artifacts by someone with no swelter store.

Adding a change kind is a contract change and belongs in a superseding ADR, not a patch.

Rule 3 forced a correction with immediate effect: `aqi_window` is part of a reading's identity
because the surface publishes two `pm25_ugm3` records for the same cell and bucket — an
`hourly-mean` record carrying an error bar and a `nowcast` record explaining why it has none. Under
a `(cell, parameter, bucket)` key those collapse (1050 records in the committed
`web/sample-surface.json` become 900), and half of every PM2.5 comparison would then be made
against whichever record happened to be last in the file. A remaining collision is a refusal rather
than a guess.

`--align latest` is opt-in rather than default because the two alignments answer different
questions and a default that silently picked one would put a plausible number behind a meaning
nobody chose.
