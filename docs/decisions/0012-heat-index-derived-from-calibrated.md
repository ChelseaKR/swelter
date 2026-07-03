# ADR 0012: Derive calibrated heat index from calibrated temperature, don't fit it

Date: 2026-07-03. Status: accepted.

## Decision

`heat_index_c` stops claiming a co-location fit it never receives. Before this
change, `calibrate._METHOD` mapped `heat_index_c` to `enclosure-offset` as if a
node's on-device heat index were fit against a reference the way temperature
and PM are — but no co-location data for `heat_index_c` exists in
`data/demo/colocation.jsonl`, `fit()` never produces a `heat_index_c` entry,
`registry.get(node_id, "heat_index_c")` is always `None`, and every heat-index
observation stayed raw/provisional regardless of how well-calibrated the
node's temperature was. That mapping is removed.

In its place, `calibrate.apply()` runs a second pass after the existing
correction loop. For each raw `heat_index_c` observation whose `(node_id,
timestamp)` has *both* a calibrated `temp_c` (produced by the enclosure-offset
correction in the same `apply()` call) and a co-timed humidity reading (via
the existing `humidity_index()` — raw, since humidity has no fitted
correction in this network), it emits an additional observation:

```
calibrated_heat_index = models.heat_index_c(calibrated_temp_c, humidity_pct)
```

tagged with version `heat_index_c.derived-enclosure.{node_id}` and method
`derived-enclosure` (a new method id, distinct from `enclosure-offset`,
because this is a recomputation from calibrated inputs, not a fit). A raw
`heat_index_c` whose node's temperature stayed raw, or whose co-timed
humidity is missing or QC-rejected, is left alone — it stays raw/provisional,
exactly as before.

Uncertainty is propagated, not re-derived: the emitted observation's
`uncertainty` is the calibrating temperature correction's `residual_std`.
Heat index is monotonic and steep in temperature over the operating range
(∂HI/∂T is generally > 1 in the Rothfusz regime), so carrying the temperature
correction's 1-sigma forward is a defensible, conservative stand-in for a
proper propagated variance, and it is honest about what it is: temperature's
error bar, not a fitted heat-index error bar. Humidity's contribution to
uncertainty is not modeled, because humidity itself is uncalibrated in this
network (see Known weakness).

`corrections.yaml` is unaffected: this derivation never touches the
registry, adds no entries, and changes no fitted coefficient, so the
byte-for-byte co-location replay (`fit()` on `colocation.jsonl` reproduces
`corrections.yaml` exactly) still holds. Re-running `swelter calibrate`
produces the same 300-entry registry either way.

## Why

The roadmap's R4 item ("Heat-index trustworthiness") named the honesty gap
directly: heat index was permanently provisional even for a node whose
temperature had a tight, well-verified correction, because nothing in the
pipeline ever calibrated heat index itself. Two ways to close that gap were
available: (a) co-locate and fit heat index the way temperature and PM are
fit, which would need a reference-grade heat-index instrument in the field —
one does not exist in this demo network and rarely exists at all, since heat
index is itself a derived quantity, not a thing a reference station reports;
or (b) recompute heat index from inputs that are already calibrated. (b) is
exact, not approximate: the NWS Rothfusz regression is a closed-form function
of temperature and humidity, so given a trustworthy temperature and a
trustworthy humidity, the recomputed heat index is exactly as trustworthy as
its inputs — there is no fitting error to add. This also keeps the
byte-for-byte corrections-registry reproducibility hard rule untouched,
because it adds no new fitted entry; the registry stays the 100-co-located-
node, 3-parameter (temp, PM2.5, PM10) shape it already is.

We rejected inventing synthetic heat-index co-location data to make the
existing `enclosure-offset` registry path fire, because that would be
inventing evidence the network does not have — exactly the kind of thing the
calibration-reproducibility hard rule exists to prevent. We rejected leaving
`heat_index_c: enclosure-offset` in `_METHOD` as dead-but-harmless code,
because a method id that is documented (`calibration.md`'s predictor table)
and looks live but structurally can never fire is itself a trust problem in a
project whose whole premise is that a reader can check the pipeline rather
than trust it.

## Known weakness

Humidity has no fitted correction anywhere in this demo network (`humidity`
has no entry in `calibrate._PREDICTORS`/`_METHOD`), so the humidity term
feeding the derived heat index is always the raw humidity reading, never a
calibrated one — the derived heat index is only as good as an uncalibrated
humidity input, and this ADR does not change that. `humidity_index()` reads
only raw, QC-passing humidity today; if a network ever adds a fitted humidity
correction, `humidity_index()` would need to prefer the calibrated reading
when one exists, the same way a humidity-aware PM correction should. That is
out of scope here and is called out honestly rather than silently assumed
away.

The derivation also inherits whatever error the temperature correction
carries: a node whose enclosure-offset fit is loose (a wide `residual_std`)
produces a derived heat index that is only as trustworthy as that loose fit,
and the propagated uncertainty (the temperature correction's `residual_std`
carried forward unchanged) is a simplification, not a rigorously propagated
variance through the nonlinear Rothfusz function — it does not account for
humidity's own uncertainty (which is unmeasured, per above) or for the
partial derivative of heat index with respect to temperature varying across
the operating range. A future revision could scale by the local `∂HI/∂T`
instead of using the temperature residual_std unscaled, if the difference
turns out to matter in practice.

Heat index stays provisional in exactly two cases: the node's temperature was
never co-located (or QC-rejected at that instant), or humidity at that
instant is missing/QC-rejected. Both are correct, honest outcomes, not gaps
introduced by this change — a node with no calibrated inputs has no basis for
a calibrated heat index.
