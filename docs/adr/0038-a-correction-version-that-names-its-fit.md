# ADR 0038: A correction version that names its fit

- Status: Accepted
- Date: 2026-08-14
- Supersedes: the version-id format decided in
  [ADR 0002](0002-calibration-as-versioned-data.md) (that ADR's registry-as-data decision stands)
- Deciders: Chelsea Kelly-Reif

## Context

ADR 0002 is titled "calibration as versioned data" and `calibrate.py` promises "a YAML registry
keyed by node and parameter, each entry naming the version that produced it. Recalibrating a node is
a data change with a diff and an audit trail." The version string could not support that, because it
was not derived from the fit:

```python
version=f"{parameter}.{method}.{node_id}",
```

A pure function of `(parameter, method, node_id)`. No window, no date, no coefficient hash, no
serial. Two corrections fit from genuinely different co-location evidence (issue #149):

```
fit A: temp_c.enclosure-offset.node-01 | coeffs (1.00,) intercept -2.0
fit B: temp_c.enclosure-offset.node-01 | coeffs (0.85,) intercept -6.0
SAME VERSION STRING? True
published value on the same raw 40.0 °C reading:  A -> 38.0 °C,  B -> 28.0 °C   (10 °C apart)
SAME STORE PRIMARY KEY?  True
```

Ten degrees apart, one identifier. `store.py`'s `PRIMARY KEY (node_id, timestamp, parameter, source,
calibration)` plus `INSERT OR IGNORE` treated them as the same row. Nothing in any *published*
artifact could name which fit produced a number: the CSV export and the SensorThings `resultQuality`
carry `calibration`, `uncertainty`, and `trustworthy`; the surface cell carries `method`. Two
datasets downloaded a year apart, with different corrections behind them, both say
`temp_c.enclosure-offset.node-01` and both say `trustworthy: true`. The audit trail existed only in
the git history of `corrections.yaml`, which does not travel with the data.

The stale-value consequence was already defended against and that deserves saying: `cmd_calibrate`
and `cmd_rebuild` both call `store.drop_calibrated()` and `cmd_demo` unlinks the DB, so
`INSERT OR IGNORE` never silently retained a superseded value through the shipped commands. What was
left is the provenance claim, which the record could not back.

## Decision

The version id gains a fit identity:

```
{parameter}.{method}.{node_id}@{window_end}-{digest}
```

for example `temp_c.enclosure-offset.node-01@20260602T230000Z-36672bc8`.

- `window_end` compacted (`20260602T230000Z`) is human-readable: a reader can see how old the
  evidence behind a number is without opening the registry.
- `digest` is the first 8 hex of a SHA-256 over the fit's `predictors`, `coefficients`, `intercept`,
  `residual_std`, `r2`, `n`, `reference`, `window_start`, `window_end`, and sensor `model` — every
  field that changes what the correction does or what it was fit from. Two fits from different
  evidence cannot collide even when their windows end at the same instant.
- Coefficients are already rounded to `PRECISION` before the digest is taken, so the id inherits the
  byte-for-byte reproducibility the published registry guarantees:
  `test_published_corrections_are_reproducible` still holds, fit ids included.
- A **derived** heat index (ADR 0014) carries the fit id of the *temperature* correction it was
  computed from. Its value changes when that fit changes, so its identity must too.

The separator is `@`, and the fit id contains no `.`, on purpose. Two places parse this string
positionally: `aggregate.py` takes `calibration.split(".")[1]` as the cell's published `method`, and
`export.py` takes `version.rsplit(".", 1)[0]` as the correction *family* for its CLI banner. Both
see exactly what they saw before, so this change does not silently alter the published surface's
`method` field or the export summary.

`docs/VERSIONING.md` already declared a version-id format change **MAJOR**. This is that change,
made inside the pre-1.0 `0.1.0` line and recorded in the changelog as breaking.

## Consequences

Every published value now names the fit behind it: the CSV export, the SensorThings
`resultQuality`'s parent record, the store row, and the registry entry all carry the same
fit-identifying string, so a downloaded dataset can be traced to one correction without the git
history. Re-fitting a node produces a genuinely new identity rather than overwriting the meaning of
an old one, which is what ADR 0002's title claimed.

Costs and accepted trade-offs:

- **The committed `data/demo/corrections.yaml` is regenerated** (300 entries, one `version:` line
  each). The fit itself is unchanged: every coefficient, `residual_std`, `r2`, `n`, and window in
  the file is byte-identical; only the ids gained their suffix.
- **Stored `calibration` values change**, so `Observation.content_hash()` changes for calibrated
  rows and an existing store's calibrated rows do not match a re-derived id. Raw rows are immutable
  and unaffected, and `swelter rebuild` re-derives calibrated rows from them; the shipped calibrate/
  rebuild/demo commands already drop calibrated rows before rewriting, so no command silently mixes
  old and new ids.
- **Version ids are ~26 characters longer.** `swelter calibrate`'s summary column is now sized to
  the widest id it is printing rather than a fixed 28.
- **A consumer that matched the id exactly against a stored string must re-read it after a re-fit.**
  That is the intended behaviour: the old string's stability was the defect.
- **The remaining half of issue #149 is not addressed here.** `export.py`'s CSV fields and
  `api.py`'s `resultQuality` still do not carry `window_end`, `n`, or `r2` as their own columns, so
  a consumer wanting the fit's *statistics* (not just its identity) still needs the registry. The
  identity is now in the record, which is what made the provenance claim false; the statistics are a
  separate, additive change.
- **An expired or drifted correction still changes nothing in the published record.**
  `qc.correction_ages` and `steward` compute `aging`/`correction_expired` as side-channel reports,
  documented as deliberate in `qc.py`. Unchanged here, but the fit id is the field that would let a
  consumer join to that report.

Executable evidence:

- `tests/test_calibrate.py::test_two_different_fits_of_one_node_never_share_a_version_id`
- `tests/test_calibrate.py::test_a_fit_id_is_reproducible_and_names_its_window`
- `tests/test_calibrate.py::test_published_corrections_are_reproducible` (unchanged, still green
  against the regenerated registry)
- `tests/test_calibrate.py::test_heat_index_derives_from_calibrated_temp_and_co_timed_humidity`
- `tests/test_aggregate.py::test_confirmed_cell_carries_calibration_provenance` (the positional
  `method` parse, unchanged)

The acceptance contract is maintained under F-04 in
[`../ACCEPTANCE-TEST-MAP.md`](../ACCEPTANCE-TEST-MAP.md).
