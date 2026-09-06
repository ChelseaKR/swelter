# ADR 0048: A check that could not run is not a check that passed

- Status: Accepted
- Date: 2026-09-06
- Deciders: swelter maintainers

## Context

The store is "one copyable directory" (ADR 0001) and `docs/runbooks/operations.md` says to copy
it. Nothing checked that a copy was complete, that it restored, or that the rights envelope, the
correction registry and the integrity chain survived the trip. A collective that has never
restored its own store does not know that it has a backup; it knows that it has a file. Next bet
5 (#233) asks for that exercise to be rehearsable by a non-engineer steward, with a receipt they
can keep.

Writing that verb surfaced a hazard that is larger than backups, and is the reason this is an ADR
rather than a changelog line.

**`swelter verify-archive` exits 0 over a store with no rows.** Nothing mismatched, so nothing
failed. That is the right answer to the question `verify-archive` asks — "has anything here been
tampered with" — and the wrong answer to "did my backup work". Worse, the failure composes: the
chained daily digest of zero days folds to the empty string, so an archive of an empty store
records an empty head, a restore of it recomputes an empty head, the two compare equal, and every
integrity check reports success over no data whatsoever. Three green checks, one absence matched
against another, and a receipt saying the archive is sound.

The same shape appears in the softer checks. A store that has never been calibrated has no
`corrections.yaml`. If "there was no registry to compare" is reported as a pass, an archive of a
never-calibrated store is indistinguishable, in the receipt, from one whose registry survived
intact. The tally rises, and the number it rises to means less than it did before.

This is the portfolio's dominant defect class arriving inside a verification tool: absence
rendered as a value, and a gate that cannot fail.

## Decision

`swelter backup` and `swelter restore` (`src/swelter/backup.py`) are built on three rules.

1. **A check reports three outcomes, not two.** `PASS`, `FAIL`, and `NOT_APPLICABLE`. The last is
   counted and printed on its own line and is never folded into the pass tally. The receipt's
   `summary` carries `passed`, `failed` and `not_applicable` as separate integers.

2. **A verdict is built from the required checks having run, not from the absence of failures.**
   `REQUIRED_CHECKS` names the six questions a restore must answer — `manifest`, `members`,
   `file_digests`, `row_count`, `row_hashes`, `digest_chain` — and the verdict is `verified` only
   when every one of them is present and `PASS`. A check that never ran cannot fail, so a verdict
   that counts failures would call an empty verification a success.

3. **Two absences never agree.** A store with no observations is refused at backup time rather
   than archived. A chain head is recorded as `null` for a rowless store, never as the empty
   string the fold produces, and a `null` on either side of the comparison is a failure rather
   than a match. The restored database file is checked for existence *before* the store is
   opened, because `open_store` creates a database when none exists and would otherwise
   manufacture the empty store that passes everything.

Everything else follows from being fail-closed. Extraction goes to a staging directory that is
never the operator's store, and the staged copy is moved into place only on a `verified` verdict,
so a failed drill leaves the target exactly as it was — including not existing. Nothing calls
`tarfile.TarFile.extractall`: members are read one at a time, and an absolute name, a `..`
segment, a symlink, a hardlink or a device entry is a refusal before any byte is written.
`--prune` refuses to delete anything at all while any archive in the directory cannot be
verified, and clamps `--keep` to at least one, because deleting on the strength of a listing you
could not read is a decision made out of absence.

Archives are byte-reproducible: members are sorted, ownership and modification times are
normalised to zero, and nothing in the manifest records a wall clock. Two backups of an unchanged
store are the same bytes, so an operator can tell "the store changed" from "the backup ran
again".

## Consequences

A steward can rehearse recovery on a schedule (`swelter restore <archive> --verify-only` writes
no store) and keep the receipt. The receipt is byte-identical across runs on the same archive, so
it can be committed as evidence.

Verification is not switchable off. `--verify` is accepted so that a runbook line can say so
explicitly, and it changes nothing; there is no flag that restores without checking, because a
restore nobody checked is the thing this verb exists to replace.

Two deliberate limits. The retention policy is supplied on the command line (`--keep`) rather
than read from `network.yaml`: `NetworkConfig` is fingerprinted field-by-field by
`is_builtin_demo_web_preview`, so adding a typed field to it is a config-schema change that
deserves its own review rather than a passenger on this one. And a backup refuses a store with an
open SQLite journal instead of checkpointing it, because a tool whose job is to produce a
trustworthy copy should not be the thing that decides another process's transaction is finished.

The three-outcome rule is a contract. Adding a required check, or moving one between required and
conditional, changes what `verified` asserts and belongs in a superseding ADR.
