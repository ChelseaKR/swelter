# Calibration — the part that earns trust

This is the deep dive the README points at. A community map of heat and air quality is only worth
running if a reader can tell a number they should act on from a number the network does not yet
stand behind. Calibration is how swelter draws that line, and this document explains the method
plainly enough that you can check it rather than trust it.

The short version: each node is co-located beside a reference-grade monitor for a training window;
`swelter calibrate` fits a small ordinary-least-squares correction per node and parameter; the
fitted coefficients, the residual standard deviation (published as 1-sigma uncertainty), and R-squared
are written to a versioned, timestamped registry; and every calibrated observation names the
correction version that produced it. Re-running the fit on the committed co-location data reproduces
the published registry byte-for-byte, so the calibration is auditable end to end.

Heat index is the one parameter this does not describe: nothing co-locates a heat-index reference,
so it is never fit. It is instead *derived* from a node's already-calibrated temperature plus
co-timed humidity — see **Heat index: derived, not fitted** below.

The implementation is `src/swelter/calibrate.py`. The committed evidence is
`data/demo/colocation.jsonl` (the training pairs) and `data/demo/corrections.yaml` (the published
registry). Nothing in this document is hand-computed prose detached from the code: the worked example
at the end reproduces a real registry entry.

Last verified: 2026-07-03. Recheck cadence: on any change to `src/swelter/calibrate.py`, the demo
registry, or the US-EPA PurpleAir correction lineage referenced below; otherwise every 12 months.

---

## Why low-cost sensors need correction at all

Low-cost optical and resistive sensors are good enough to map block-scale differences that no sparse
regulatory network can see, but only after their known biases are removed. Three biases dominate, and
all three are systematic — they bias the reading in a predictable direction, which is exactly what a
fitted correction can remove.

- **Humidity inflation of optical PM.** A low-cost PM sensor counts particles by how much light they
  scatter. On a humid morning, water condenses onto and around particles, they swell, they scatter
  more light, and the sensor reports more mass than is really there. The error is not noise; it tracks
  relative humidity, and it can roughly double the reported concentration at high humidity. A map that
  plots raw optical PM makes humid mornings look like pollution events. This is why the PM correction
  takes humidity as an input, not just the raw count.
- **Enclosure heating.** A sensor lives in a box on a porch or a fence. In direct sun a dark or
  poorly ventilated enclosure heats up, and the temperature sensor reports the box, not the air —
  several degrees high at the worst part of the afternoon. Because this is a near-constant offset plus
  a small slope, it corrects well with an enclosure-offset term.
- **Baseline drift.** Sensors age. Optical chambers foul, resistive elements shift, and the zero and
  the gain wander over weeks and months. A correction fit once and trusted forever slowly stops being
  true. Drift is the reason the registry is versioned and timestamped and the reason periodic
  re-co-location is part of the method rather than an afterthought (see **Drift tracking** below).

A network that ignores these draws a map that is precise and wrong. swelter treats removing them as
the core feature.

---

## Co-location training against a reference monitor

A node is placed physically beside a reference-grade monitor — a regulatory station or a known-good
instrument — for a training window, typically a few days, so the two see the same air and the same
heat. During that window we record matched pairs: the node's raw reading and the reference's value at
the same timestamp, plus the co-time relative humidity for the PM models. Those pairs are the only
evidence a correction is fit from. In the demo they are committed to `data/demo/colocation.jsonl`, one
JSON object per line:

```json
{"node_id":"node-01","parameter":"temp_c","timestamp":"2026-06-01T00:00:00Z","raw":25.09,"reference":24.76,"humidity":74.4}
{"node_id":"node-01","parameter":"pm25_ugm3","timestamp":"2026-06-01T00:00:00Z","raw":23.81,"reference":14.84,"humidity":74.4}
{"node_id":"node-01","parameter":"pm10_ugm3","timestamp":"2026-06-01T00:00:00Z","raw":45.96,"reference":28.06,"humidity":74.4}
```

`read_colocation()` loads these into `TrainingPair` records; `humidity` is optional and is only used
by the PM models. The fit needs at least three pairs for a node/parameter, and the demo windows hold
48 hourly pairs each (the first two days of the recorded week). A node that is never co-located has no
training pairs, gets no correction, and stays raw — the network never invents a correction it has no
evidence for.

---

## The exact models

swelter fits ordinary least squares — nothing more exotic — and does it in pure Python so the math is
inspectable line by line. The solver builds the normal equations `(XᵀX)β = Xᵀy` and solves them by
Gaussian elimination with partial pivoting (`_ols` and `_solve` in `calibrate.py`). There is no numpy,
no opaque library, and no hidden regularization. Which predictors a parameter regresses on is fixed,
small, and physically motivated; the intercept is always included.

### PM (PM2.5, PM10): humidity-aware, US-EPA PurpleAir lineage

```
corrected = a·raw + b·humidity + c
```

- `a` scales the raw optical reading, `b` removes the humidity inflation described above, and `c` is
  the offset.
- Method id: `epa-humidity`. The form — a linear correction on the raw reading with a relative-humidity
  term — is in the lineage of the US-EPA correction for PurpleAir sensors, which adds a humidity term
  precisely to undo optical PM's humidity bias. swelter fits its own per-node coefficients rather than
  adopting fixed national constants, because each node's enclosure, siting, and sensor lot differ; the
  *structure* is borrowed, the *numbers* are local and earned from that node's co-location window.

### Temperature: enclosure-offset

```
corrected = a·raw + c
```

- `a` is a small gain correction and `c` is the enclosure offset — the few degrees a sun-baked box adds.
- Method id: `enclosure-offset`.

### Default

Any other parameter falls back to a simple linear correction (`corrected = a·raw + c`, method id
`linear`). No parameter is special-cased anywhere else in the pipeline; adding one is a model entry
here plus its predictor list. `heat_index_c` is the one exception — see the section below — it is
never fit and so never falls back to this default either.

The predictor-to-method mapping, verbatim from the engine:

| Parameter | Predictors | Method id |
|---|---|---|
| `pm25_ugm3` | `raw`, `humidity` | `epa-humidity` |
| `pm10_ugm3` | `raw`, `humidity` | `epa-humidity` |
| `temp_c` | `raw` | `enclosure-offset` |
| (default) | `raw` | `linear` |
| `heat_index_c` | *(derived, not fit — see below)* | `derived-enclosure` |

---

## Heat index: derived, not fitted

Heat index does not fit the co-location model above, because there is nothing to co-locate it
against: a reference-grade instrument reports temperature and humidity, not a "true" heat index, so
`data/demo/colocation.jsonl` has no `heat_index_c` rows and `swelter calibrate` never produces a
`heat_index_c` entry in the registry. Earlier, `calibrate._METHOD` still listed `heat_index_c` as
using the `enclosure-offset` method — a claim that never actually fired, so every heat-index
observation stayed raw/provisional forever, even for a node whose temperature was tightly
calibrated. See ADR 0014 for the full reasoning; this section documents the fix plainly.

Instead, `calibrate.apply()` derives a calibrated heat index directly. For every raw `heat_index_c`
observation whose `(node_id, timestamp)` has *both* a calibrated `temp_c` (produced by the
enclosure-offset correction earlier in the same `apply()` call) and a co-timed humidity reading
(`humidity_index()` — raw, since humidity has no fitted correction in this network; see the caveat
below), it emits an additional observation:

```
calibrated_heat_index_c = models.heat_index_c(calibrated_temp_c, humidity_pct)
```

using the same NWS Rothfusz function `data/demo` was generated from. This is recomputation from
exact, calibrated inputs, not a new statistical fit — no coefficient is estimated, so it adds
nothing to `corrections.yaml` and the byte-for-byte co-location replay is untouched.

The emitted observation is tagged `heat_index_c.derived-enclosure.{node_id}` (method id
`derived-enclosure`, distinct from `enclosure-offset` so a reader can tell "recomputed from
calibrated inputs" from "fit against a reference" at a glance) and carries an `uncertainty` equal to
the *temperature* correction's `residual_std` — heat index is monotonic and steep in temperature over
the operating range, so the temperature error bar carried forward is a simple, defensible
1-sigma stand-in rather than a properly propagated variance through the nonlinear regression. It does
not account for humidity's own uncertainty, because humidity is uncalibrated in this network (see
below), and it does not scale by the local `∂HI/∂T`, which would be a more precise but more
complex propagation.

**Caveat, stated honestly:** humidity is never calibrated in this demo network — no node has a
fitted humidity correction, so `humidity_index()` always returns raw, QC-passing humidity, and that
is what the heat-index derivation uses. A calibrated heat index is therefore calibrated with respect
to temperature and exact with respect to the Rothfusz function, but it inherits whatever error an
uncalibrated humidity sensor carries. If a network ever fits a humidity correction,
`humidity_index()` would need to prefer it — that is out of scope here.

A raw `heat_index_c` observation is left provisional in exactly two cases: its node's temperature
never got calibrated (no correction, or the reading itself was QC-rejected), or the co-timed
humidity is missing or QC-rejected. Both are honest outcomes: a node with no trustworthy inputs has
no basis for a trustworthy derived value, and the map shows it as provisional rather than promoting
it on an uncalibrated input.

---

## Per-model bias: sensor-model-aware calibration families

The predictor-to-method mapping above is keyed by parameter alone, but the EPA-PurpleAir humidity
lineage it borrows from is sensor-family-specific: different low-cost PM sensors have measurably
different humidity responses because they differ in optics, onboard firmware, and whether they
apply their own RH compensation before a reading ever leaves the device. A node can optionally
register which hardware family produced its readings — `NodeConfig.sensor_model` in
`network.yaml`, e.g. `sensor_model: PMS5003` — and `calibrate.py` uses it to select a
(parameter, model) correction family when one is registered, falling back to the per-parameter
default above for a node with no model or an unrecognized one. **This changes nothing about the
raw/calibrated boundary (hard rule #3):** a model-aware correction is still fit from that node's
own co-location evidence, the same as every other correction in this document; the model only
picks which regression form to fit. `network.yaml`'s `sensor_model` field is public and must never
hold a serial number or other per-device identifier — `swelter.config` rejects values that look
like one (a long digit run, an explicit "serial"/"S/N" marker, a MAC address, a UUID) at load time
(hard rule #1).

The known families and the typical bias each is registered for:

| Model | Onboard RH compensation | Registered family | Predictors | Method id |
|---|---|---|---|---|
| PMS5003 (Plantower) | No | humidity-aware, EPA-PurpleAir lineage | `raw`, `humidity` | `epa-humidity-pms5003` |
| SDS011 (Nova Fitness) | No | humidity-aware, EPA-PurpleAir lineage | `raw`, `humidity` | `epa-humidity-sds011` |
| SPS30 (Sensirion) | Yes (firmware-side) | linear, no humidity term | `raw` | `linear-onboard-rh-sps30` |

- **PMS5003 and SDS011** are both optical particle counters with no onboard humidity correction, so
  they fit the same humidity-aware form as the per-parameter default — the model-specific method id
  exists so the registry and every calibrated observation's `calibration` version id trace which
  family's bias the fit corrected, even though the regression form is identical.
- **SPS30** applies its own RH compensation in firmware before the reading reaches swelter, so most
  of the humidity-driven inflation described above is already removed by the time the raw value is
  read. Adding a second humidity term at the network level would just fit noise against an already-
  compensated signal, so the SPS30 family drops it and fits a plain linear correction instead.
- These are *typical* biases for each hardware family, described qualitatively here and encoded as
  a difference in predictor set / method id — not as a numeric prior a node can borrow instead of
  its own co-location fit. Every coefficient in the registry, model-aware or not, is still earned
  from that specific node's own training pairs (see **Co-location training** above); a model only
  changes which regression form those pairs are fit against.

### A model-typical bias is not calibration

**A registered `sensor_model` alone never promotes a node past provisional.** Knowing a node runs a
PMS5003 tells you the *shape* of correction a co-location fit for that node is likely to need — the
family it borrows from — not what that node's actual coefficients are. A node with a
`sensor_model` and no co-location fit has exactly the same `calibration: raw` status, the same
provisional presentation on the map and table, and the same absence from the registry as a node
with no model set at all (audit A1: raw and calibrated must never be silently blurred). If a future
feature ever surfaces a "typical PMS5003 bias band" as a documented prior for context, it must be
labeled explicitly as a prior, sourced independently of any specific node's evidence, and rendered
in a way that cannot be mistaken for a fitted, node-specific correction — hard rule #3 forbids
treating it as one.

`src/swelter/sources/sensor_community.py` is where this field's provenance often originates: the
Sensor.Community API already reports each sensor's hardware type (`sensor.sensor_type.name`), and
the adapter maps it onto the discovered node's `sensor_model` in the generated `network.yaml`
instead of discarding it — the readings stay raw/provisional exactly as they did before (that
adapter has no co-location evidence to fit from), but the hardware family survives for the day a
co-location window is recorded for one of these real sensors.

---

## Honest error bars: residual standard deviation as 1-sigma uncertainty

A correction is only as good as how tightly the node tracks the reference after it is applied. swelter
measures that with the residuals — the gaps between each reference value and what the fitted model
predicts for that pair — and publishes the residual standard deviation as the value's 1-sigma
uncertainty.

```
residual_i  = reference_i − model(raw_i, humidity_i)
residual_std = sqrt( Σ residual_i² / n )
```

The divisor is `n`, the number of training pairs, so `residual_std` is the root-mean-square of the
residuals over the co-location window. Every calibrated observation carries this number as its
`uncertainty` field, in the parameter's own unit (degrees C for temperature, µg/m³ for PM). It is a
statement about the spread of the fit, read as roughly plus-or-minus one standard deviation, not a
guarantee about any single live reading. A wide `residual_std` is itself information: it means this
node's correction is loose, and the dashboard should — and does — present such values with less
confidence than a tight one.

This is the difference between an error bar that is earned and one that is asserted. The number comes
straight out of how well the node agreed with ground truth, run by run.

### R-squared reporting

Alongside the uncertainty, each correction records R-squared, the fraction of the reference's variance
the fit explains:

```
r2 = 1 − ( Σ residual_i² / Σ (reference_i − mean_reference)² )
```

R-squared and `residual_std` answer different questions, and the registry reports both. `residual_std`
is the absolute spread in real units — how many degrees or µg/m³ you should treat as uncertain.
R-squared is the relative goodness of fit — whether the model is tracking the real signal at all. A
temperature fit near `r2 = 0.99` is tracking the air closely; a PM fit nearer `r2 = 0.7` is doing real
work but leaves more residual scatter, which is exactly what its larger `residual_std` says. Reporting
both keeps either from being read in isolation.

---

## Drift tracking, re-co-location, and the versioned registry

Sensors age, so a correction is a snapshot, not a permanent fact. The registry is versioned data, not
code: a YAML file (`data/demo/corrections.yaml` in the demo) keyed by node and parameter, where each
entry carries its training window start and end timestamps and the reference it was fit against.
Recalibrating a node is a data change — a diff against the committed registry, reviewable and
reversible — not a code edit.

- **Periodic re-co-location.** A node is brought back beside a reference monitor on a cadence, or after
  service, and re-fit. The new correction replaces the old entry for that node/parameter; the version
  id stays stable (it identifies the node/parameter/method, not the run) while the coefficients,
  window timestamps, residual_std, and R-squared update. The timestamps make the registry an audit
  trail: you can always see when a node was last grounded against truth.
- **Widening residuals as a service signal.** Drift shows up as a `residual_std` that grows from one
  co-location to the next. A node whose residuals widen past the network's bound is flagged for service
  before its data is trusted, rather than quietly publishing a correction that has stopped being true.
- **Provenance on every value.** Because each calibrated observation names its correction version, and
  the registry entry for that version carries its window, you can trace any published number back to
  the co-location that justifies it.

### Version id format

A correction version id is:

```
{parameter}.{method}.{node_id}
```

For example `temp_c.enclosure-offset.node-01` or `pm25_ugm3.epa-humidity.node-07`. It names what was
corrected (parameter), how (method), and for whom (node) — enough to find the registry entry and read
its coefficients, window, and error. It is the string stored in each observation's `calibration` field,
which is how the rest of the pipeline tells a calibrated reading from a raw one.

---

## The correction-registry YAML schema

`data/demo/corrections.yaml` is the published registry. Its schema:

```yaml
version: 1                       # registry schema version (integer)
corrections:                     # list, one entry per fitted node/parameter
  - version: string              # "{parameter}.{method}.{node_id}"
    node_id: string              # the node this correction belongs to
    parameter: string            # one of the PARAMETERS names (e.g. temp_c, pm25_ugm3)
    method: string               # epa-humidity | enclosure-offset | linear
    predictors: [string, ...]    # ordered predictor names, e.g. [raw, humidity] or [raw]
    coefficients: [float, ...]   # one coefficient per predictor, same order, 6 dp
    intercept: float             # the constant term c, 6 dp
    residual_std: float          # 1-sigma uncertainty in the parameter's unit, 6 dp
    r2: float                    # coefficient of determination, 6 dp
    n: integer                   # number of co-location training pairs used
    reference: string            # the reference monitor / source identifier
    window_start: string         # ISO-8601 UTC timestamp of the first training pair
    window_end: string           # ISO-8601 UTC timestamp of the last training pair
    model: string                # OPTIONAL — sensor family, e.g. "PMS5003"; omitted when unknown
```

`coefficients` is positional: `coefficients[i]` multiplies `predictors[i]`, and the prediction is
`intercept + Σ coefficients[i]·predictors[i]`. For a temperature entry `predictors` is `[raw]`, so
there is one coefficient; for a PM entry `predictors` is `[raw, humidity]`, so there are two. Each
co-located node contributes three corrections (temp, PM2.5, PM10), so the demo registry holds 300
corrections from the 100 co-located nodes. The remaining third of the network has no co-location
records, so those nodes appear nowhere in the registry and their readings publish raw.

`model` is a schema addition (EXP-03): it is only written when the node that produced the
correction had a `sensor_model` registered in `network.yaml`, so every existing entry — including
the whole committed demo registry, since none of its nodes register a model — parses and
round-trips identically to before this field existed. A reader can treat a missing `model` key
exactly as an empty string.

---

## Reproducibility: anyone can check rather than trust

The point of committing both the training data and the registry is that the calibration is not asked
to be believed. It can be reproduced.

- **Fixed precision.** Every coefficient, intercept, `residual_std`, and `r2` is rounded to 6 decimal
  places (`PRECISION = 6` in `calibrate.py`). Fixed precision is what makes the fit reproducible
  byte-for-byte across machines and Python builds, instead of differing in the last floating-point
  digit.
- **Deterministic fit.** The training pairs are sorted by timestamp before fitting and the registry is
  emitted in sorted key order, so the output ordering and the numbers do not depend on input order or
  dict iteration.
- **The check.** Re-running `swelter calibrate` against the committed `data/demo/colocation.jsonl`
  reproduces `data/demo/corrections.yaml` byte-for-byte. This is exercised in CI (the calibration
  replay), so a change that would alter the published corrections cannot land silently. You can run it
  yourself and diff the result against the committed file; if they differ, something in the data or the
  method changed, and that is exactly the signal you want.

That is the whole trust argument: the evidence is committed, the method is plain OLS in readable
Python, and the output is reproducible to the byte. Calibration is checkable, not taken on faith.

---

## Cross-checked: an inter-sensor agreement statistic, not a calibration tier

Some no-reference networks — no regulatory monitor to co-locate against — still want a QC signal
stronger than "raw." **Cross-checked** is that signal, and it is deliberately narrow: two low-cost
nodes placed side by side (a "sensor twin" pair) for a window, and `qc.twin_agreement` reports how
tightly their readings of the same parameter agree — paired by nearest timestamp, the spread
(population standard deviation) of the residuals `value_a - value_b`, plus how many pairs matched.

**Read it correctly, or not at all:**

- **Cross-checked bounds precision, never accuracy.** A tight residual spread rules out sensor
  noise, drift, or a hardware fault as the source of disagreement between the two nodes — it says
  the twins are *consistent with each other*. It says nothing about whether either twin reads the
  *true* concentration or temperature. Two twins with the same systematic bias (both reading PM2.5
  high on a humid morning, say) will agree tightly with each other while both being wrong in the
  same direction. Only a reference-grade co-location (the rest of this document) can establish
  accuracy.
- **Cross-checked ≠ calibrated.** A twin-agreement statistic never touches an `Observation`'s
  `value`, never assigns a correction version, and never sets `uncertainty`. `calibration` stays the
  `raw` sentinel (hard rule #3 — every value the pipeline ships is either raw or corrected by a
  reference-fitted registry entry; a twin check is neither). This is QC/health metadata, surfaced
  under `twin_agreement` in `qc.health_report`'s JSON, not a third value on the calibration axis.
- **EPA non-regulatory framing.** This mirrors how the US EPA treats low-cost sensor networks in its
  own guidance: co-location agreement among non-reference sensors informs data quality and QC flags,
  it does not confer regulatory-grade accuracy. swelter's cross-checked tier is that same
  QC-not-accuracy read, not a house-brand claim of correctness.
- **No surface promotes a cross-checked value past provisional.** The map, the table, the export, and
  the API all still show a node with only a twin-agreement record as **provisional** raw data, exactly
  as before this feature existed. `twin_agreement` is additive annotation for an operator's health
  dashboard — evidence that a QC/health investigation can lean on — never a signal that changes what a
  reader sees on the map.

Configure a pair in `network.yaml` under `twin_windows` (`node_a`, `node_b`, `parameter`, `start`,
`end` — see the worked example in the repo root); pass the parsed windows to
`qc.health_report(..., twin_windows=config.twin_windows)` to have the read ride along under
`twin_agreement`. Omit `twin_windows` (the default) and the JSON shape is byte-for-byte what it was
before this section existed.

---

## How a reader interprets a value's trust

Every observation is one of two things, and the dashboard, the export, and the API never silently mix
them.

- **Calibrated, with uncertainty.** Its `calibration` field holds a correction version id (for example
  `temp_c.enclosure-offset.node-01`) and its `uncertainty` field holds the `residual_std` for that
  correction, in the value's unit. Read it as "the air was about this, give or take roughly one sigma."
  A calibrated value that also passes QC is what the README calls *publishable*: it is the only kind of
  value the map presents as fact.
- **Raw / provisional.** Its `calibration` field is the sentinel `raw` and it has no uncertainty.
  Either the node was never co-located, or QC rejected the reading (range, spike, flatline, missing).
  The map and table show it as **provisional**, never dressed up as certain. A provisional reading is
  not hidden — coverage matters — but it is labeled so no one acts on a number the network cannot stand
  behind.

A reader's rule of thumb: a number with a correction version and an error bar is a measurement you can
use; a number marked provisional is a hint, not a fact.

---

## Worked example: node-01 temperature (R² ≈ 0.99)

Take the temperature correction for `node-01` from the demo. Its 48 co-location pairs span
`2026-06-01T00:00:00Z` to `2026-06-02T23:00:00Z` (the first two days of the recorded week). Because
temperature uses the enclosure-offset model, the fit regresses the reference temperature on the node's
raw temperature with an intercept: `corrected = a·raw + c`.

`swelter calibrate` fits and writes this entry to `data/demo/corrections.yaml`:

```yaml
- version: temp_c.enclosure-offset.node-01
  node_id: node-01
  parameter: temp_c
  method: enclosure-offset
  predictors:
  - raw
  coefficients:
  - 0.908949
  intercept: 2.248444
  residual_std: 0.476025
  r2: 0.991959
  n: 48
  reference: reference-monitor
  window_start: '2026-06-01T00:00:00Z'
  window_end: '2026-06-02T23:00:00Z'
```

Reading it:

- The fitted model is **`corrected = 0.908949·raw + 2.248444`**. The intercept near +2 °C is the
  enclosure offset — the box reads about two degrees warm at baseline — and the slope just under 1 is a
  small gain correction.
- **R² = 0.991959** says the corrected node tracks the reference almost exactly: the model explains
  over 99% of the reference's variance over the window. Temperature is an easy quantity to correct,
  which is why temperature R² lands near 0.99 while the humidity-bound PM fits for the same nodes sit
  lower (around 0.6 to 0.8 in this demo) and carry correspondingly larger `residual_std`.
- **residual_std = 0.476025 °C** is the published 1-sigma uncertainty. Every calibrated temperature
  observation from node-01 carries `±0.48 °C` as its `uncertainty`. So a corrected reading of, say,
  31.0 °C means "about 31, give or take roughly half a degree."

Applying it to a single raw reading: a raw `27.0 °C` from this node co-located against a reference of
`26.89 °C` corrects to `0.908949 × 27.0 + 2.248444 ≈ 26.79 °C` — within the published half-degree of the
reference's `26.89 °C`, which is the fit doing its job.

To reproduce this entry, run `swelter calibrate` against `data/demo/colocation.jsonl` and compare the
`temp_c.enclosure-offset.node-01` block to the committed `data/demo/corrections.yaml`. They match to
the byte. That is the whole promise: you do not have to trust the half-degree error bar, you can
re-derive it.

---

## See also

- `src/swelter/calibrate.py` — the engine (OLS, registry, fit/apply).
- `data/demo/colocation.jsonl` — the committed co-location training pairs.
- `data/demo/corrections.yaml` — the published, reproducible correction registry.
- `src/swelter/models.py` — `Observation.calibration`, `uncertainty`, and the calibrated-vs-raw
  invariant the map relies on.
- `src/swelter/qc.py` — `twin_agreement()` and `TwinAgreement`, the cross-checked precision tier
  (QC/health metadata only — see the section above).
- `src/swelter/config.py` — `TwinWindow`, `NetworkConfig.twin_windows`.
