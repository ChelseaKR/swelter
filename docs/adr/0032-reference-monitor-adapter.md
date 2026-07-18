# ADR 0032: Assemble co-location training pairs from a reference-monitor feed

- Status: Accepted
- Date: 2026-07-18
- Deciders: Chelsea Kelly-Reif

## Context

Calibration fits a node's correction by regressing its raw readings onto a co-located reference-grade
monitor (ADR 0002). Until now that reference series was hand-built into a `colocation.jsonl` file, so
re-calibration — the operational answer to drift (FIX-03) — was a manual project rather than a
repeatable loop. Networks that *have* a nearby regulatory monitor (US EPA AirNow / AQS) should be
able to assemble the training pairs automatically from overlapping timestamps. This is EXP-02; it
complements, not replaces, the no-local-reference paths (transfer calibration E4, the sensor-twin
tier EXP-09).

Two forces shape the design. First, the reference is a third-party regulatory source with its own
rights and its own API key, so it must not be relabelled under the repository CC0 dedication (ADR
0024) and its key must never leak. Second, timestamp alignment is where a co-location goes subtly
wrong: an hourly reference paired against a five-minute node cadence needs an explicit, reviewable
resampling rule, not an ad-hoc join.

## Decision

Add `src/swelter/sources/airnow.py`, a fourth source adapter that pulls the **reference** side
(AirNow/AQS regulatory PM2.5) over the shared resilient `_http` fetch. Its readings are a distinct
`ReferenceReading` type — never a stored `Observation`, never a swelter-calibrated value, carrying no
host- or person-shaped field, only a public AQS site id, a UTC hour, and a concentration. The source
keeps its own attribution and license (public-domain data with AirNow attribution terms retained),
absent from `models.KNOWN_SOURCES` because it never enters the node store. The runtime API key is
supplied by `--api-key`/`AIRNOW_API_KEY` and redacted from any failure message, honoring the
SECURITY.md rule against printing credential-bearing URLs.

Add `src/swelter/colocate.py` and `swelter colocate --node X --monitor Y --window START..END`, which
pair a node's stored raw readings against the reference series. The pairing/resampling logic is a
**pure, offline function**: the sparser hourly reference drives the join, and each reference reading
is matched to the single nearest node sample within a documented tolerance (default 30 minutes),
downsampling the node series to the reference cadence — one pair per reference hour — with ties
resolved to the earlier sample and out-of-window references dropped rather than guessed. The command
emits `TrainingPair`s in `calibrate.read_colocation` format, extended with the reference `monitor`
id, which flows through the existing (previously unused) reference seam in `calibrate.fit` into
`Correction.reference` — the pattern `config.ReferenceMonitor.source` already named. A file with no
monitor still records the generic `reference-monitor`, so the committed demo registry rebuilds
byte-for-byte.

Acceptance criteria and evidence are recorded as F-22 in
[`../ROADMAP.md`](../ROADMAP.md) and [`../ACCEPTANCE-TEST-MAP.md`](../ACCEPTANCE-TEST-MAP.md), tested
in [`../../tests/test_colocate.py`](../../tests/test_colocate.py); the new source's provenance,
method, and retained rights are documented in [`../data-cards/airnow.md`](../data-cards/airnow.md).

## Consequences

Re-calibration for a network with a reference monitor becomes one repeatable command instead of a
hand-curated file, and the correction records which regulatory monitor it trusts. The raw/calibrated
boundary is untouched: reference readings fit a correction but are never published as observations,
and a node still needs its own fitted correction to move past provisional. The reference source's
rights travel with it and are never redistributed as swelter data.

The live AirNow fetch is a keyed, third-party request and is deliberately **not** exercised by the
test suite; the tested contract is the pure `parse_series` mapping and the pairing function. An
operator wiring a live fetch must confirm the current AirNow endpoint, query parameters, and auth
mechanism against AirNow documentation — this is the real-data gate EXP-02 named. A new superseding
ADR is warranted if the reference-side rights model changes, if reference readings are ever persisted
into a store, or if the resampling rule needs a form other than nearest-within-tolerance.
