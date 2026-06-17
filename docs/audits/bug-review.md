# Codebase bug review

_Date: 2026-06-17. Method: multi-agent review — 10 finders fanned out across the code areas,
each finding then independently verified by an adversarial skeptic that tried to refute it (and
ran the code to confirm). 33 candidates reported, 29 confirmed after verification (the rest were
duplicates of the same root cause or false alarms). Every confirmed defect below has been fixed
and pinned by a regression test in `tests/test_bugfixes.py` (or `tests/test_server.py`)._

## High severity

| # | Defect | Location | Fix |
| --- | --- | --- | --- |
| 1 | PM2.5 AQI: a mean landing in an EPA breakpoint gap (9.0–9.1, 35.4–35.5, …) fell through to **500 / Hazardous** — clean air shown as maximum danger | `models.pm25_aqi` | Truncate the concentration to 0.1 µg/m³ before the band lookup (EPA convention); reject NaN |
| 2 | A `NaN` reading was silently dropped by SQLite (NULL on a NOT NULL column) and **mis-counted as a duplicate** | `ingest.explode` | Reject non-finite floats at validation |
| 3 | One malformed JSONL line **aborted the whole ingest batch**, losing every valid reading and writing no quarantine | `ingest.read_jsonl` | Per-line parse guard → quarantine the bad line, keep the valid ones |
| 4 | Spike QC used out-of-range neighbours in its median, **mislabeling valid readings next to a fault as spikes** | `qc._series_flags` | Take the median over QC-clean neighbours only |
| 5 | A humidity-aware PM correction with no co-timed humidity **silently used RH=0** and published a badly-wrong value as trustworthy | `calibrate.apply` | Skip calibration (leave raw/provisional) when the humidity predictor is missing |
| 6 | **CSV formula injection** via attacker-controlled `node_id` in the headline export | `export.to_csv` | Prefix formula-trigger cells (`= + - @ \t \r`) with a quote |
| 7 | **Static-file path traversal**: a lexical `startswith` guard let a sibling dir sharing the web-dir name prefix escape the root | `server._static` | Boundary-correct `Path.is_relative_to` check |
| 8 | The a11y gate **double-counted** a redundantly-labelled control, masking a genuinely unlabelled one (failed open) | `scripts/a11y_check.py` | Evaluate labelling per control |

## Medium severity

| # | Defect | Location | Fix |
| --- | --- | --- | --- |
| 9 | `Infinity` passed validation and produced **non-RFC JSON** (`Infinity` token) on export | `ingest` / `export` | Reject non-finite at ingest; `allow_nan=False` and map non-finite → null on export |
| 10 | `read(since/until)` compared timestamps **lexically**, so a valid non-canonical bound (offset, fractional seconds) silently dropped rows | `store.read` | Normalise bounds via `parse_timestamp`/`format_timestamp` |
| 11 | A single singular co-location group **aborted the entire fit** and crashed the CLI | `calibrate.fit` | Skip the singular group with a warning; fit the rest |
| 12 | Negative `top` **silently truncated** the API result with a misleading `@iot.count` | `api.observations` | Clamp `top` to ≥ 0 |
| 13 | Non-numeric `top`/`hours` raised an uncaught `ValueError` → **dropped connection** instead of a 400 | `server` | Defensive parsing + a 400/500 catch-all in `do_GET` |
| 14–16 | `ingest`/`calibrate` crashed with a raw traceback on a missing input file; stale SW served old assets after deploy | `cli`, `web/sw.js` | `is_file()` guards; stale-while-revalidate + cache-version bump + `reg.update()` |

## Low severity

`content_hash` docstring corrected (dedup is key-based); QC ordered by raw string not parsed
datetime; `-0.0` coefficient could break byte-for-byte reproducibility (now normalised);
`humidity_index` used QC-rejected humidity (now filtered); SW returned `undefined` for offline
`/export` navigations (now a defined 503); i18n left stale text on a failed locale load (now
falls back per-key to the English default); firmware buffer did an O(n) read+rewrite per append
at capacity (now amortised O(1) with a cached count + batched trim); a firmware docstring
mismatch.

## Result

`make verify` is green after the fixes: ruff (format + lint), `mypy --strict`, the structural
accessibility gate (12/12), and **83 tests** (62 original + 21 new regression tests). The
end-to-end demo and the calibration-replay reproducibility check still pass unchanged.
