# ADR 0037: Absence is never published as a number, and never narrows an interval

- Status: Accepted
- Date: 2026-08-14
- Deciders: Chelsea Kelly-Reif

## Context

`aggregate._bucket_observations` read a calibrated member's missing 1-sigma as `0.0`:

```python
b.trusted_unc[key].append(obs.uncertainty if obs.uncertainty is not None else 0.0)
```

`_build_cells` then averaged and combined that list, so an *unknown* uncertainty entered the
arithmetic as a **perfect instrument**. Measured, from issue #147:

| members' 1-sigma | provisional | cell `uncertainty` | `mean_member_sigma` |
|---|---|---|---|
| (0.8, 0.8) | False | 0.5657 | 0.8000 |
| **(0.8, None)** | **False** | **0.4000** | **0.4000** |
| (0.8, 0.8, 0.8, 0.8) | False | 0.4000 | 0.8000 |

Adding a member whose uncertainty is unknown *halved* `mean_member_sigma` and dropped the cell
standard error to 0.400 — below the 0.800 of the one member actually measured. Knowing less made
the published error bar tighter, on a cell still stamped `provisional: false`. Every other
missing-data rule in this codebase points the other way (a value without a valid correction stays
provisional; a QC-rejected reading is never mapped; a gap is a gap), and this one inverted it in the
single direction that can hurt someone deciding whether it is safe to be outside.

The same coercion made `has_unc = any(uncs)` do double duty: after it, a list of genuine zeros (a
fit whose `residual_std` rounded to `0.0`, `calibrate.py:271`) is indistinguishable from a list of
unknowns, so a perfect fit published `uncertainty: null` — unknown — where the truth was zero. The
same conflation, mirrored.

Reachability: `calibrate.apply` is the only production writer of calibrated rows and always passes
`correction.residual_std`, so the mixed case was not reachable through the shipped CLI. Nothing
enforced that. `models.Observation` had no invariant, `store.py`'s `uncertainty` column is nullable
and round-trips `None` faithfully, and `tests/conftest.py` defaulted it to `None` — so the test
suite blessed exactly the state that makes the bug live. Any future calibrated writer (a
reference-monitor adapter, an import path, a restored archive) turns it on.

Two related cases in the same family, also from #147: NowCast PM2.5 cells published
`uncertainty: null` with no note on 100 records stamped `provisional: false` — the reading a person
is most likely to act on, because it is the one that tracks a smoke plume, shipping as fact with
nothing attached. And `QC_MISSING` is a verdict defined in `models.py`, published in the machine-
readable data dictionary, and written by no code path in the repository: a consumer writing
`if row.qc == "missing"` gets dead code and a false sense that gaps arrive in-band.

## Decision

**One rule, in one place: an unknown sigma is not a zero, and absence never narrows an interval.**

`aggregate.combine_member_sigmas(sigmas)` is now the single site that turns member 1-sigmas into the
cell's two published numbers, and `trusted_unc` carries `float | None` end to end:

- **Any unknown member sigma ⇒ the cell publishes no numeric uncertainty at all**, plus an
  `uncertainty_note` saying how many members were unknown. Averaging over the known ones only was
  rejected: it still quotes an interval for a cell whose spread is partly unmeasured, and still
  reads as more confident than the evidence supports.
- **A member sigma of exactly `0.0` is a measurement, not an absence.** `is not None` replaces
  `any(...)`, so `[0.0, 0.0]` publishes `0.0` — a different published fact from `null`.
- The cell stays `provisional: false`. Provisional means *uncalibrated*, and blurring it to also
  mean "calibrated but incompletely characterized" would cost the distinction hard rule 3 exists to
  protect. The missing error bar is reported as a missing error bar, with its reason.

**The invariant moves to the boundary.** `Observation.__post_init__` refuses a calibrated
observation with no `uncertainty`: a correction is fitted from recorded co-location evidence and
always has a `residual_std`, so a calibrated value without a 1-sigma is a broken row, not a
zero-uncertainty one. Every writer — CLI, adapters, imports, and `store`'s row hydration — passes
through that constructor. `store._row_to_obs` re-raises with the remediation (`swelter rebuild`,
which re-derives calibrated rows from the immutable raw ones) rather than repairing the row, because
the only available repairs are inventing a number or reading absence as zero.

**A null uncertainty says why.** `uncertainty_note` is no longer exposure-only. Any cell publishing
no number carries the reason on every surface: which axis bounds an `exposure` level (unchanged), how
many member sigmas were unknown, or — new — that a **NowCast** record blends unevenly-weighted hours
and no combined sigma is derived for that blend. NowCast keeps `provisional: false`: it is derived
from calibrated hourly means, and marking it provisional would say "uncalibrated", which is false.
What was missing was the caveat, not the calibration.

**A published vocabulary says which of its terms can appear.** `models.QC_EMITTED` names the four
verdicts QC can actually put on a reading; `QC_MISSING` is documented as reserved and never emitted,
and the data dictionary publishes `emitted: false` for it with a description pointing at where
absence actually lives (the absence of a row, plus `detect_gaps`). Removing the constant was
rejected: `QC_UNMAPPABLE` must still reject the verdict if an ingest path ever sends one, and
deleting a published term is a bigger break than telling the truth about it.

## Consequences

A cell whose members are not all characterized publishes no error bar instead of a falsely tight
one. A perfect fit publishes `0.0` instead of `null`. A NowCast reading carries its caveat. A
consumer reading the data dictionary is told which QC verdicts can occur.

Costs and accepted trade-offs:

- **A calibrated row without an uncertainty is now a hard error at read time**, not a silently
  degraded value. A store holding one (only reachable by writing SQLite directly or restoring an
  archive from before this change) fails loudly on read, naming the row and the fix. Failing closed
  is the point: the alternative is publishing a number swelter cannot stand behind.
- **`tests/conftest.py`'s `make_obs` now supplies a default sigma** for calibrated observations that
  do not name one, because the invariant forbids the state the factory used to default to. Tests
  that care about the value still pass their own.
- **The mixed-sigma path is unreachable from the shipped pipeline** once the invariant holds, so its
  rollup handling is defence in depth. It is kept and tested at the accumulator level: the invariant
  is one line that a future refactor could weaken, and the rollup must not be the place that then
  invents a number.
- **`uncertainty_note` on non-exposure records is an additive field** older readers ignore (MINOR
  under `docs/VERSIONING.md`). The *value* published for a mixed-sigma cell changes from a number to
  `null`, which is a correction to a wrong number rather than a redefinition of the field's meaning:
  `uncertainty` still means the cell standard error, computed the same way, over members that all
  have one.
- **This does not give NowCast an error bar.** It states that it has none. Deriving a defensible
  combined sigma for an unevenly-weighted blend is a real statistical question and is left open
  rather than answered with a fabricated number.

Executable evidence:

- `tests/test_aggregate.py::test_an_unknown_member_sigma_never_shrinks_the_published_error_bar`
- `tests/test_aggregate.py::test_a_cell_with_an_unknown_member_sigma_publishes_no_number_and_says_why`
- `tests/test_aggregate.py::test_nowcast_record_states_that_it_has_no_error_bar`
- `tests/test_aggregate.py::test_exposure_note_relays_why_a_confirmed_component_has_no_numeric_uncertainty`
- `tests/test_models.py::test_a_calibrated_observation_without_an_uncertainty_is_refused`
- `tests/test_store.py::test_a_stored_calibrated_row_with_no_uncertainty_is_refused_not_read_as_zero`
- `tests/test_qc.py::test_qc_never_emits_the_missing_verdict_and_gaps_are_reported_separately`
- `tests/test_dictionary.py::test_the_dictionary_says_which_verdicts_nothing_ever_emits`

The acceptance contract is maintained under F-28 in
[`../ACCEPTANCE-TEST-MAP.md`](../ACCEPTANCE-TEST-MAP.md).
