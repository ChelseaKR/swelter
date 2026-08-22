"""Calibration: it recovers a known relationship, carries error bars, and reproduces."""

from __future__ import annotations

import importlib
import sys
from collections.abc import Callable
from pathlib import Path

from swelter import calibrate
from swelter.calibrate import CorrectionRegistry, TrainingPair
from swelter.models import heat_index_c, wbgt_c

from .conftest import DEMO, make_obs

ROOT = Path(__file__).resolve().parent.parent


def _pairs(parameter: str, fn: Callable[[int], float], n: int = 8) -> list[TrainingPair]:
    return [
        TrainingPair(
            node_id="node-01",
            parameter=parameter,
            timestamp=f"2026-06-01T{i:02d}:00:00Z",
            raw=float(i),
            reference=fn(i),
        )
        for i in range(n)
    ]


def test_fit_recovers_linear_relationship() -> None:
    correction = calibrate.fit_one(
        "node-01", "temp_c", _pairs("temp_c", lambda i: 2.0 * i + 1.0), "ref"
    )
    assert correction.predictors == ("raw",)
    assert abs(correction.coefficients[0] - 2.0) < 1e-6
    assert abs(correction.intercept - 1.0) < 1e-6
    assert correction.r2 > 0.999
    assert abs(correction.predict(5.0, None) - 11.0) < 1e-6


def test_pm_correction_is_humidity_aware() -> None:
    rows = [(2.0, 40.0), (4.0, 55.0), (6.0, 60.0), (8.0, 45.0), (10.0, 70.0), (12.0, 50.0)]
    pairs = [
        TrainingPair(
            node_id="node-01",
            parameter="pm25_ugm3",
            timestamp=f"2026-06-01T{i:02d}:00:00Z",
            raw=raw,
            reference=0.5 * raw + 0.2 * hum + 1.0,
            humidity=hum,
        )
        for i, (raw, hum) in enumerate(rows)
    ]
    correction = calibrate.fit_one("node-01", "pm25_ugm3", pairs, "ref")
    assert correction.predictors == ("raw", "humidity")
    expected = 0.5 * 10.0 + 0.2 * 70.0 + 1.0
    assert abs(correction.predict(10.0, 70.0) - expected) < 1e-6


def test_apply_emits_calibrated_beside_raw() -> None:
    registry = CorrectionRegistry()
    registry.add(
        calibrate.fit_one("node-01", "temp_c", _pairs("temp_c", lambda i: 2.0 * i + 1.0), "ref")
    )
    out = calibrate.apply([make_obs(value=10.0)], registry)
    assert len(out) == 2
    calibrated = [o for o in out if o.is_calibrated]
    assert len(calibrated) == 1
    assert abs(calibrated[0].value - 21.0) < 1e-6
    assert calibrated[0].uncertainty is not None


def test_node_without_correction_stays_raw() -> None:
    out = calibrate.apply([make_obs(node_id="node-99", value=10.0)], CorrectionRegistry())
    assert len(out) == 1
    assert not out[0].is_calibrated


def test_registry_yaml_roundtrip(tmp_path: Path) -> None:
    registry = CorrectionRegistry()
    registry.add(
        calibrate.fit_one("node-01", "temp_c", _pairs("temp_c", lambda i: 2.0 * i + 1.0), "ref")
    )
    path = tmp_path / "corrections.yaml"
    registry.to_yaml(path)
    assert CorrectionRegistry.from_yaml(path).to_dict() == registry.to_dict()


def test_published_corrections_are_reproducible() -> None:
    """Re-running the fit on the committed co-location data reproduces the registry exactly."""
    fitted = calibrate.fit(calibrate.read_colocation(DEMO / "colocation.jsonl"))
    published = CorrectionRegistry.from_yaml(DEMO / "corrections.yaml")
    assert fitted.to_dict() == published.to_dict()
    assert len(fitted) == len(published)
    assert len(fitted) > 0 and len(fitted) % 3 == 0  # 3 parameters per calibrated node


# -- sensor-model-aware families (EXP-03) ----------------------------------------------------


def test_predictors_for_unknown_model_matches_parameter_default() -> None:
    """No model, or a model with no registered family, behaves exactly as before model-awareness."""
    assert calibrate.predictors_for("pm25_ugm3") == ("raw", "humidity")
    assert calibrate.predictors_for("pm25_ugm3", None) == ("raw", "humidity")
    assert calibrate.predictors_for("pm25_ugm3", "SomeUnknownSensor") == ("raw", "humidity")
    assert calibrate.predictors_for("no2_ppb", "PMS5003") == ("raw",)  # parameter has no PM family


def test_predictors_for_known_model_family_overrides_parameter_default() -> None:
    """SPS30's onboard RH compensation means its PM family drops the humidity predictor."""
    assert calibrate.predictors_for("pm25_ugm3", "SPS30") == ("raw",)
    assert calibrate.predictors_for("pm10_ugm3", "SPS30") == ("raw",)
    # PMS5003/SDS011 keep the humidity-aware default predictor set — only the method id differs.
    assert calibrate.predictors_for("pm25_ugm3", "PMS5003") == ("raw", "humidity")
    assert calibrate.predictors_for("pm25_ugm3", "SDS011") == ("raw", "humidity")


def test_fit_one_model_selects_method_and_predictors() -> None:
    rows = [(2.0, 40.0), (4.0, 55.0), (6.0, 60.0), (8.0, 45.0), (10.0, 70.0), (12.0, 50.0)]
    pairs = [
        TrainingPair(
            node_id="node-01",
            parameter="pm25_ugm3",
            timestamp=f"2026-06-01T{i:02d}:00:00Z",
            raw=raw,
            reference=0.5 * raw + 0.2 * hum + 1.0,
            humidity=hum,
        )
        for i, (raw, hum) in enumerate(rows)
    ]
    sps30 = calibrate.fit_one("node-01", "pm25_ugm3", pairs, "ref", model="SPS30")
    assert sps30.predictors == ("raw",)
    assert sps30.method == "linear-onboard-rh-sps30"
    assert sps30.model == "SPS30"
    # What the correction is *for* is still the first three dot-separated segments; the fit's own
    # identity follows "@" (issue #149), so the assertion is on the prefix plus a non-empty fit id.
    family, _, identity = sps30.version.partition("@")
    assert family == "pm25_ugm3.linear-onboard-rh-sps30.node-01"
    assert identity

    pms = calibrate.fit_one("node-01", "pm25_ugm3", pairs, "ref", model="PMS5003")
    assert pms.predictors == ("raw", "humidity")
    assert pms.method == "epa-humidity-pms5003"
    assert pms.model == "PMS5003"

    default = calibrate.fit_one("node-01", "pm25_ugm3", pairs, "ref")
    assert default.predictors == ("raw", "humidity")
    assert default.method == "epa-humidity"
    assert default.model == ""


def test_fit_gives_different_models_different_fitted_forms() -> None:
    """Two co-located nodes with different sensor models fit different regression forms."""
    rows = [(2.0, 40.0), (4.0, 55.0), (6.0, 60.0), (8.0, 45.0), (10.0, 70.0), (12.0, 50.0)]
    pairs = [
        TrainingPair(
            node_id=node_id,
            parameter="pm25_ugm3",
            timestamp=f"2026-06-01T{i:02d}:00:00Z",
            raw=raw,
            reference=0.5 * raw + 0.2 * hum + 1.0,
            humidity=hum,
        )
        for node_id in ("node-pms", "node-sps")
        for i, (raw, hum) in enumerate(rows)
    ]
    registry = calibrate.fit(pairs, models={"node-pms": "PMS5003", "node-sps": "SPS30"})
    pms = registry.get("node-pms", "pm25_ugm3")
    sps = registry.get("node-sps", "pm25_ugm3")
    assert pms is not None and sps is not None
    assert pms.predictors == ("raw", "humidity")
    assert sps.predictors == ("raw",)  # a genuinely different regression form, not just a label
    assert pms.method != sps.method


def test_fit_without_models_is_unaffected() -> None:
    """Omitting `models` (or passing an empty mapping) is identical to fitting with none at all —
    this is what keeps the committed demo registry reproducible byte-for-byte."""
    fitted_default = calibrate.fit(calibrate.read_colocation(DEMO / "colocation.jsonl"))
    fitted_empty_models = calibrate.fit(calibrate.read_colocation(DEMO / "colocation.jsonl"), {})
    assert fitted_default.to_dict() == fitted_empty_models.to_dict()


def test_correction_model_omitted_from_dict_when_empty() -> None:
    """`model` only appears in the serialized dict when non-empty, so demo entries (no model)
    stay byte-for-byte identical to the pre-model-awareness schema."""
    correction = calibrate.fit_one(
        "node-01", "temp_c", _pairs("temp_c", lambda i: 2.0 * i + 1.0), "ref"
    )
    entry = CorrectionRegistry({"node-01:temp_c": correction}).to_dict()["corrections"][0]
    assert "model" not in entry

    modeled = calibrate.fit_one(
        "node-01", "temp_c", _pairs("temp_c", lambda i: 2.0 * i + 1.0), "ref", model="PMS5003"
    )
    modeled_entry = CorrectionRegistry({"node-01:temp_c": modeled}).to_dict()["corrections"][0]
    assert modeled_entry["model"] == "PMS5003"


def test_correction_model_roundtrips_through_yaml(tmp_path: Path) -> None:
    registry = CorrectionRegistry()
    registry.add(
        calibrate.fit_one(
            "node-01", "pm25_ugm3", _pairs("pm25_ugm3", lambda i: 2.0 * i + 1.0), "ref", "SPS30"
        )
    )
    path = tmp_path / "corrections.yaml"
    registry.to_yaml(path)
    reloaded = CorrectionRegistry.from_yaml(path)
    restored = reloaded.get("node-01", "pm25_ugm3")
    assert restored is not None
    assert restored.model == "SPS30"
    assert reloaded.to_dict() == registry.to_dict()


def _temp_registry() -> CorrectionRegistry:
    registry = CorrectionRegistry()
    registry.add(
        calibrate.fit_one("node-01", "temp_c", _pairs("temp_c", lambda i: 2.0 * i + 1.0), "ref")
    )
    return registry


def test_heat_index_derives_from_calibrated_temp_and_co_timed_humidity() -> None:
    """A calibrated temp_c plus co-timed raw humidity derives a calibrated heat_index_c."""
    registry = _temp_registry()
    ts = "2026-06-01T00:00:00Z"
    observations = [
        make_obs(parameter="temp_c", value=10.0, timestamp=ts),  # -> 21.0 via the fit above
        make_obs(parameter="humidity_pct", unit="%", value=65.0, timestamp=ts),
        make_obs(parameter="heat_index_c", value=30.0, timestamp=ts),  # raw on-device reading
    ]
    out = calibrate.apply(observations, registry)

    heat_calibrated = [o for o in out if o.parameter == "heat_index_c" and o.is_calibrated]
    assert len(heat_calibrated) == 1
    derived = heat_calibrated[0]
    # The derived value names the *temperature* fit it was computed from, not just its node: a
    # re-fit of temp_c changes the heat index published for that node, so it must change its id
    # too (issue #149).
    temp_version = registry.get("node-01", "temp_c")
    assert temp_version is not None
    family, _, identity = derived.calibration.partition("@")
    assert family == "heat_index_c.derived-enclosure.node-01"
    assert identity == temp_version.version.partition("@")[2]
    assert identity
    assert abs(derived.value - heat_index_c(21.0, 65.0)) < 1e-9

    temp_correction = registry.get("node-01", "temp_c")
    assert temp_correction is not None
    assert derived.uncertainty == temp_correction.residual_std

    # The raw heat_index_c reading still passes through unchanged.
    heat_raw = [o for o in out if o.parameter == "heat_index_c" and not o.is_calibrated]
    assert len(heat_raw) == 1
    assert heat_raw[0].value == 30.0

    # No new registry entry was created: the derivation never touches corrections.yaml.
    assert registry.get("node-01", "heat_index_c") is None
    assert all(c.parameter != "heat_index_c" for c in registry.all())


def test_heat_index_stays_provisional_when_temp_is_raw() -> None:
    """A node with no temp_c correction gets no derived heat index — it stays raw/provisional."""
    ts = "2026-06-01T00:00:00Z"
    observations = [
        make_obs(node_id="node-99", parameter="temp_c", value=10.0, timestamp=ts),
        make_obs(node_id="node-99", parameter="humidity_pct", unit="%", value=65.0, timestamp=ts),
        make_obs(node_id="node-99", parameter="heat_index_c", value=30.0, timestamp=ts),
    ]
    out = calibrate.apply(observations, CorrectionRegistry())  # no corrections at all
    heat = [o for o in out if o.parameter == "heat_index_c"]
    assert len(heat) == 1
    assert not heat[0].is_calibrated
    assert heat[0].value == 30.0


def test_heat_index_derivation_leaves_corrections_registry_byte_for_byte() -> None:
    """Deriving heat index during apply() never adds a fitted entry to the published registry."""
    fitted = calibrate.fit(calibrate.read_colocation(DEMO / "colocation.jsonl"))
    published = CorrectionRegistry.from_yaml(DEMO / "corrections.yaml")

    ts = "2026-06-01T00:00:00Z"
    observations = [
        make_obs(node_id="node-01", parameter="temp_c", value=25.09, timestamp=ts),
        make_obs(node_id="node-01", parameter="humidity_pct", unit="%", value=74.4, timestamp=ts),
        make_obs(node_id="node-01", parameter="heat_index_c", value=25.09, timestamp=ts),
    ]
    calibrate.apply(observations, fitted)  # exercised for its side-on-registry effects, if any

    # The registry read from the committed file and the freshly re-fit registry are unaffected by
    # having run apply() against them: still byte-for-byte identical, still no heat_index_c rows.
    assert fitted.to_dict() == published.to_dict()
    assert all(c.parameter != "heat_index_c" for c in fitted.all())
    assert all(c.parameter != "heat_index_c" for c in published.all())


def test_two_different_fits_of_one_node_never_share_a_version_id() -> None:
    """Issue #149: the version id must name the fit, not just the node/parameter/method.

    Before this, `version` was a pure function of `(parameter, method, node_id)`. Two corrections
    fit from genuinely different co-location evidence — 10 °C apart in what they publish for the
    same raw reading — carried the same identifier, the same store primary key, and the same
    `calibration` value in every export. A dataset downloaded a year later said `trustworthy: true`
    under the same string with different numbers behind it, and nothing in the published record
    could tell the two apart.
    """
    fit_a = calibrate.fit_one("node-01", "temp_c", _pairs("temp_c", lambda i: i - 2.0), "ref")
    fit_b = calibrate.fit_one(
        "node-01", "temp_c", _pairs("temp_c", lambda i: 0.85 * i - 6.0), "ref"
    )

    # The fixture reproduces the issue's premise: materially different corrections.
    raw_reading = 40.0
    assert abs(fit_a.predict(raw_reading, None) - fit_b.predict(raw_reading, None)) > 5.0

    assert fit_a.version != fit_b.version
    # What the correction is for is unchanged and still positionally parseable; only the fit id
    # after "@" differs.
    assert fit_a.version.partition("@")[0] == "temp_c.enclosure-offset.node-01"
    assert fit_a.version.partition("@")[0] == fit_b.version.partition("@")[0]
    assert fit_a.version.split(".")[1] == "enclosure-offset"  # aggregate.py reads the method here
    assert fit_a.version.rsplit(".", 1)[0] == "temp_c.enclosure-offset"  # export.py's family
    assert "." not in fit_a.version.partition("@")[2]  # the fit id never adds a dot-segment

    # Different ids mean different store rows: `INSERT OR IGNORE` on
    # (node_id, timestamp, parameter, source, calibration) can no longer treat a re-fitted value as
    # a duplicate of the value it supersedes.
    reading = make_obs(parameter="temp_c", value=raw_reading)
    a_row = reading.calibrated(fit_a.version, fit_a.predict(raw_reading, None), fit_a.residual_std)
    b_row = reading.calibrated(fit_b.version, fit_b.predict(raw_reading, None), fit_b.residual_std)
    assert a_row.key() != b_row.key()
    assert a_row.content_hash() != b_row.content_hash()


def test_a_fit_id_is_reproducible_and_names_its_window() -> None:
    # The id has to be stable across runs and machines, or the committed registry stops
    # reproducing byte for byte — the property the whole audit trail rests on.
    pairs = _pairs("temp_c", lambda i: 2.0 * i + 1.0)
    first = calibrate.fit_one("node-01", "temp_c", pairs, "ref")
    again = calibrate.fit_one("node-01", "temp_c", list(reversed(pairs)), "ref")
    assert first.version == again.version

    identity = first.version.partition("@")[2]
    assert identity.startswith("20260601T070000Z")  # the compact end of the co-location window
    assert identity.endswith(first.version[-8:])
    # A fit from the same coefficients but a different window is a different fit.
    later = calibrate.fit_one(
        "node-01",
        "temp_c",
        [
            TrainingPair(
                node_id="node-01",
                parameter="temp_c",
                timestamp=f"2026-07-01T{i:02d}:00:00Z",
                raw=float(i),
                reference=2.0 * i + 1.0,
            )
            for i in range(8)
        ],
        "ref",
    )
    assert later.coefficients == first.coefficients
    assert later.intercept == first.intercept
    assert later.version != first.version


def test_the_demo_generator_and_models_agree_on_heat_index_and_wbgt() -> None:
    """`scripts/gen_demo_data.py` keeps its own copy of the NWS Rothfusz heat index and the WBGT
    estimate, and `calibrate`'s module docstring says `apply` uses "the same NWS Rothfusz function
    the demo generator uses". It is a *copy*, not the same function (issue #149).

    The copy is deliberate and kept: an independent implementation is what makes the committed
    fixture evidence rather than a restatement of the code under test — if the generator imported
    `models`, a wrong formula would produce a fixture that agrees with it and hides itself. What was
    missing is the check that the two agree, so that "the same function" is a verified claim instead
    of a comment. This is that check.
    """
    sys.path.insert(0, str(ROOT))
    generator = importlib.import_module("scripts.gen_demo_data")

    grid = [
        (temp, humidity)
        for temp in (10.0, 20.0, 26.6, 26.7, 30.0, 32.2, 35.0, 40.0, 45.0, 50.0)
        for humidity in (5.0, 20.0, 40.0, 55.0, 70.0, 85.0, 100.0)
    ]
    for temp, humidity in grid:
        assert generator.heat_index_c(temp, humidity) == round(heat_index_c(temp, humidity), 2), (
            f"heat index disagrees at {temp} °C / {humidity}%"
        )
        assert generator.wbgt_c(temp, humidity) == round(wbgt_c(temp, humidity), 2), (
            f"WBGT disagrees at {temp} °C / {humidity}%"
        )


def test_heat_index_temp_slope_regimes() -> None:
    """The propagation slope is 1 below the regression floor, >1 hot-humid, and never <1."""
    # Below the 26.7 degC floor heat index is the air temperature: slope exactly 1.
    assert calibrate._heat_index_temp_slope(20.0, 50.0) == 1.0
    # Hot and humid (Danger band): the Rothfusz slope is well above 1.
    assert calibrate._heat_index_temp_slope(35.0, 70.0) > 1.5
    # Hot and very dry: the raw regression slope dips below 1; the floor keeps it at 1.
    assert calibrate._heat_index_temp_slope(27.0, 5.0) == 1.0
    # At the branch point the difference quotient stays on the regression side of 26.7 degC —
    # the value discontinuity there must not inflate the slope.
    assert calibrate._heat_index_temp_slope(26.7, 60.0) < 4.0


def test_heat_index_uncertainty_scales_by_local_slope() -> None:
    """Hot-humid derived heat index carries sigma_T scaled by |dHI/dT|, not sigma_T unscaled."""
    noisy = [
        TrainingPair(
            node_id="node-01",
            parameter="temp_c",
            timestamp=f"2026-06-01T{i:02d}:00:00Z",
            raw=float(i),
            reference=2.0 * i + 1.0 + (0.4 if i % 2 else -0.4),
        )
        for i in range(8)
    ]
    registry = CorrectionRegistry()
    registry.add(calibrate.fit_one("node-01", "temp_c", noisy, "ref"))
    correction = registry.get("node-01", "temp_c")
    assert correction is not None
    assert correction.residual_std > 0

    ts = "2026-06-01T00:00:00Z"
    observations = [
        make_obs(parameter="temp_c", value=17.0, timestamp=ts),  # calibrates to ~35 degC
        make_obs(parameter="humidity_pct", unit="%", value=70.0, timestamp=ts),
        make_obs(parameter="heat_index_c", value=36.0, timestamp=ts),
    ]
    out = calibrate.apply(observations, registry)
    derived = [o for o in out if o.parameter == "heat_index_c" and o.is_calibrated]
    assert len(derived) == 1
    calibrated_temp = correction.predict(17.0, None)
    assert calibrated_temp > calibrate._HI_REGRESSION_FLOOR_C
    slope = calibrate._heat_index_temp_slope(calibrated_temp, 70.0)
    assert slope > 1.0
    assert derived[0].uncertainty == calibrate._round(slope * correction.residual_std)
    # The scaled error bar is strictly wider than the unscaled sigma_T it replaces.
    assert derived[0].uncertainty is not None
    assert derived[0].uncertainty > correction.residual_std
