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
