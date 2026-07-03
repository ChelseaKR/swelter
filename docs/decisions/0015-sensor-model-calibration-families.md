# ADR 0015: Key calibration families by (parameter, sensor model), not parameter alone

Date: 2026-07-03. Status: accepted.

## Decision

`NodeConfig` gains an optional `sensor_model` field (`network.yaml`: `sensor_model: PMS5003`) — a
public hardware family string, never a serial number or other per-device identifier. `config.py`
enforces that at construction: a `sensor_model` matching a serial-number shape (a long digit run,
an explicit "serial"/"S/N" marker, a MAC address, a UUID) raises `ValueError`, the same hard-rule-1
posture the existing `label_concerns` heuristics take toward node labels, but as a hard rejection
rather than a warning, since a leaked serial number is a standing violation, not a style nit.

`calibrate.py`'s per-parameter `_PREDICTORS`/`_METHOD` tables gain model-specific companions,
`_MODEL_PREDICTORS`/`_MODEL_METHOD`, keyed by `(parameter, model)`. `predictors_for(parameter,
model=None)` and the new `_method_for(parameter, model)` try `(parameter, model)` first, fall back
to `parameter` alone, then to the existing defaults — so a node with no model, or a model with no
registered family, fits exactly as it did before this change. Three families are registered for PM:
PMS5003 and SDS011 (no onboard humidity compensation) keep the humidity-aware EPA-PurpleAir-lineage
predictor set under a model-specific method id (`epa-humidity-pms5003` / `epa-humidity-sds011`);
SPS30 (Sensirion firmware applies its own RH compensation before the reading reaches swelter) drops
the humidity predictor entirely (`linear-onboard-rh-sps30`) — a genuinely different regression
form, not just a different label.

`Correction` gains a `model: str = ""` field, threaded through `fit_one` (new `model` parameter,
default `""`) and `fit` (new `models: dict[str, str] | None` parameter — node_id → sensor_model,
typically built from a loaded `NetworkConfig`). `CorrectionRegistry.to_dict()` serializes `model`
only when non-empty; `from_dict()` reads it back with `entry.get("model", "")`. `swelter calibrate`
and `swelter demo` build the node→model mapping from the loaded config and pass it through.

`sources/sensor_community.py` no longer discards the sensor hardware type the Sensor.Community API
already reports (`sensor.sensor_type.name`): `parse_measurements` and `network_doc` carry it
through as the discovered node's `sensor_model`, widening their node-metadata tuple from
`(label, lat, lon)` to `(label, lat, lon, model)`.

## Why

`calibrate._METHOD` keyed corrections by parameter only, but the US-EPA PurpleAir humidity-
correction lineage the docs cite is sensor-family-specific — different low-cost PM sensors have
measurably different humidity responses because they differ in optics and, for a device like the
SPS30, whether the sensor already applies its own RH compensation in firmware. Fitting every PM
sensor against the same predictor set either wastes a predictor (redundant humidity term on an
already-compensated SPS30 reading) or omits one (a PMS5003/SDS011 with no onboard compensation).
Recording the family also fixed a latent issue in the Sensor.Community adapter, which already knew
each sensor's hardware type and was throwing it away before this change — exactly the kind of
information a (parameter, model) calibration family needs.

We rejected two alternatives. First, hard-coding per-model logic as special-cased branches in
`fit_one` — rejected because it does not compose with the existing per-parameter fallback and would
need a new special case for every future family, where a data-driven `(parameter, model)` table
extends by adding an entry. Second, treating a model as a numeric prior a node could borrow instead
of its own co-location fit ("assume every PMS5003 has bias X") — rejected outright: hard rule #3
forbids labeling anything calibrated that was not fit from that specific node's own evidence, and a
model-typical bias band is a property of the hardware family in aggregate, not of one node's
enclosure, siting, or individual sensor lot. A registered `sensor_model` changes only which
regression form a node's own co-location fit uses; it never changes whether that node has a fitted
correction at all, and it never promotes a node past `raw`/provisional on its own.

## Known weakness / Consequences

**Registry schema bump.** `corrections.yaml` gains an optional `model` field. It is additive and
omitted when empty, so every existing entry — including the entire committed demo registry, since
none of its nodes register a `sensor_model` — parses and round-trips byte-for-byte identically to
before this change; `fit()`'s `models` parameter defaults to `None`/`{}`, which is exactly the old
behavior. This coordinates with FIX-03 (drift/re-calibration tracking): any future change to the
registry schema should treat `model` as already-reserved rather than re-using the key.

**The registered families are a starting set, not exhaustive.** Only PMS5003, SDS011, and SPS30
have entries in `_MODEL_PREDICTORS`/`_MODEL_METHOD`; any other `sensor_model` string — including a
real one like "SEN55" or "OPC-N3" — silently falls back to the per-parameter default rather than
erroring. That is the intended fail-safe (an unrecognized model must not break a fit that used to
work), but it means a documented family only exists once someone adds its table entry, and until
then the per-model bias section in `docs/calibration.md` does not yet describe that hardware.

**The serial-number rejection is a heuristic, not a guarantee.** `_check_sensor_model`'s patterns
(long digit run, "serial"/"S/N" marker, MAC-shaped, UUID-shaped) catch the obvious shapes the same
way `label_concerns` catches obvious address-like labels, but a sufficiently unusual serial-number
format could still slip through as a technically-valid-looking model string. This is a defense in
depth alongside code review, not a substitute for it.
