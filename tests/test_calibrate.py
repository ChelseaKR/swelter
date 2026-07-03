"""Calibration: it recovers a known relationship, carries error bars, and reproduces."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from swelter import calibrate
from swelter.calibrate import CorrectionRegistry, TrainingPair

from .conftest import DEMO, make_obs


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
    assert sps30.version == "pm25_ugm3.linear-onboard-rh-sps30.node-01"

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
