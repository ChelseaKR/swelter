# ADR 0049: A release that cannot be checked is not a release that checked out

- Status: Accepted
- Date: 2026-09-06
- Deciders: swelter maintainers

## Context

`swelter snapshot` freezes a citable release: the immutable raw observations, the correction
registry fitted against them, and the gridded surface, behind a `MANIFEST.json` of per-file
SHA-256 digests. `swelter verify-archive` proves the store's rows are intact. `swelter restore
--verify` proves an archive round-trips (ADR 0048).

None of them proves the published surface can be **re-derived from its own inputs**. That is a
different claim, and it is one the project already makes. `docs/citability.md` says a researcher
can publish against a snapshot. The calibration-reproducibility metric promises byte-identical
registry output. ADR 0046 says a Danger-day count must state what it rests on — and a reviewer
asked to trust such a count should be able to regenerate it rather than take the digest of a file
as evidence that the number inside it follows from the readings beside it. A digest proves nobody
edited the file. It says nothing about whether the file was ever derivable from the data it ships
with.

So: a `reproduce` verb. Writing it forced three decisions that outlive the verb.

## Decision

### 1. The verdict has four states, and only one of them exits zero

`reproduced`, `mismatch`, `refused`, `indeterminate`.

A release that does not record the swelter version, the data-schema version, or the network
configuration a rebuild would need has **not been shown to be either sound or rotten**. It is
`indeterminate`. Every snapshot written before this ADR is in that state by construction, because
`MANIFEST.json` did not carry those fields.

`indeterminate` exits **2**, not 0. This is the whole point. A caller gating on `$? -eq 0` — a
release script, a `make` target, a CI step — must not be told that a release nobody could check is
a release that checked out. Sharing an exit status with success would make the gate unable to
fail on exactly the releases it exists to catch: the old ones, and the ones missing their own
provenance. That is the portfolio's dominant defect shape (an absence published as a
measurement), applied to a gate instead of to a reading, and ADR 0037 already forbids it for
values.

The verdict is computed from the required checks **having run and passed**, never from the absence
of a failure — and `NOT_APPLICABLE` is not a pass, for the reason ADR 0048 gives. A check that
never ran cannot fail, so a verdict counted from failures would call a reproduction that silently
skipped a step a success.

### 2. The network configuration is an input, and it stays outside the snapshot

The published surface depends on `network.yaml`: the grid resolution, each node's published
location, the hazard pack, the calibration windows, the reference monitors. A reproduction that
ignores it is not a reproduction.

But `network.yaml` also holds the **precise coordinates a host may have declined to publish**.
Hard rule 2 says location precision belongs to the host; ADR 0003 makes coarse publication the
default. Freezing the configuration into a citable, downloadable release would leak exactly what
those rules protect — silently, in a file whose name suggests it is metadata.

So the snapshot records a **fingerprint and nothing else**: a SHA-256 over the whole typed
configuration (`config.configuration_fingerprint`). `reproduce` refuses, **by name**, when the
`--config` it is handed is not the one that built the release.

This is honest about a real limitation rather than papering over it. Without the operator's
configuration the surface genuinely cannot be re-derived, and a third party holding only the
snapshot cannot run this verb. Saying so is strictly better than the alternative, which is
rebuilding against whichever `network.yaml` happens to be on the machine and reporting the
resulting difference as data rot. A refusal names a configuration change; a mismatch would blame
the readings for it.

The fingerprint covers every typed field, not only the fields `aggregate` reads today. A
fingerprint narrowed to a subset stops covering a field the moment the surface starts depending on
one that was left out, and the failure mode of a too-narrow fingerprint is the bad one: a silent
mismatch. Over-strict costs a truthful refusal instead.

### 3. Cross-version reproduction is reported, not attempted

If the running swelter version, or the running data-schema version, is not the one the manifest
names, the verdict is `indeterminate` and both versions are printed. Rebuilding a 0.1 release
under 0.3 and calling the difference a mismatch would blame the data for a code change.

## Consequences

- `MANIFEST.json` gains `data_schema_version` and `config_fingerprint`. A snapshot built without a
  configuration records `config_fingerprint: null` **and carries a note saying the release cannot
  be reproduced** — the absence is stated, not left to be inferred from a missing key.
- The reproduction runs through a real store, exactly as `swelter rebuild` does, rather than
  through an in-memory shortcut. A cell's value is the mean of its members and a mean of floats
  depends on summation order, so the store's ordering is part of the pipeline and a shortcut could
  differ in the last bit and be reported as a mismatch.
- `reproduce` also recomputes the manifest's own per-file digests, as a check that runs but does
  **not** stop the rebuild. The two findings compose: a digest failure alone says the frozen bytes
  were edited; a digest failure together with a surface difference says which cell that edit
  reached. A manifest listing zero files fails that check rather than passing it vacuously.
- This closes a gap the frozen surface itself creates. `aggregate.geojson` publishes the *latest*
  cell-hour per cell, so an edit to an earlier hour changes no published feature and the rebuild
  alone would report clean. The digest check is what makes such an edit visible.
- **A missing `network.yaml` records no fingerprint, not the fingerprint of an empty one.** The
  CLI's `_load_config` substitutes an empty `NetworkConfig` for a missing file so the rest of the
  pipeline can run against a network nobody has registered yet. That substitution is right for a
  pipeline verb and wrong for anything that *records* which configuration was in force: an empty
  network has a perfectly good fingerprint, and writing it into a release manifest would publish
  "built with this configuration" over a file that was never read. `snapshot` and `reproduce` ask
  `_config_or_none` instead, and `reproduce` refuses a missing configuration by its own name rather
  than reporting it as a configuration that does not match.
- A release whose frozen raw holds a reading with no value is refused rather than averaged around.
- A release freezing no observations is refused: an empty rebuild equals an empty frozen surface,
  and two absences must never agree (ADR 0048).
- The receipt carries no wall clock, so two runs against an unchanged snapshot produce identical
  bytes and the receipt can itself be archived and compared.

## Alternatives considered

**Freeze `network.yaml` into the snapshot.** Rejected: it publishes precise host coordinates.

**Freeze a privacy-safe projection of the configuration** — only the fields `aggregate` reads,
with coordinates already snapped. Attractive, and rejected for now: the projection is a second
place that must be kept in step with the aggregator, and drifting it silently narrows what the
reproduction covers. A fingerprint plus an explicit refusal has no such failure mode. Revisit if
third-party reproduction becomes a requirement rather than an operator one.

**Report `indeterminate` as exit 0** on the grounds that the issue proposing this verb said older
snapshots should be "reported, not failed". Rejected, and the deviation is deliberate: "not a
failure" was read as "not a *mismatch*" — it gets a verdict of its own and is never called a
mismatch — but it cannot also share an exit status with success without becoming a gate that
cannot fail.
