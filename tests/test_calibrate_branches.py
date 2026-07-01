"""Calibration-honesty branches: refuse to fit on too little evidence, never double-calibrate,
tolerate a missing humidity term, and skip malformed co-location lines.

These reinforce hard rule #3 (calibrated and raw are distinct, never silently mixed) at the
branch level the line-coverage suite leaves untested.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from swelter import calibrate
from swelter.calibrate import CorrectionRegistry, TrainingPair

from .conftest import make_obs


def test_fit_one_refuses_too_few_pairs() -> None:
    """A correction earned from one or two points would be noise dressed as calibration."""
    pairs = [
        TrainingPair(
            node_id="node-01",
            parameter="temp_c",
            timestamp="2026-06-01T00:00:00Z",
            raw=1.0,
            reference=2.0,
        )
    ]
    with pytest.raises(ValueError, match="at least 3"):
        calibrate.fit_one("node-01", "temp_c", pairs, "ref")


def test_apply_does_not_recalibrate_a_calibrated_reading() -> None:
    """An already-calibrated input passes through untouched — no calibrating a calibrated value."""
    registry = CorrectionRegistry()
    registry.add(
        calibrate.fit_one(
            "node-01",
            "temp_c",
            [
                TrainingPair(
                    node_id="node-01",
                    parameter="temp_c",
                    timestamp=f"2026-06-01T{i:02d}:00:00Z",
                    raw=float(i),
                    reference=2.0 * i + 1.0,
                )
                for i in range(5)
            ],
            "ref",
        )
    )
    already = make_obs(value=10.0, calibration="temp_c.enclosure-offset.node-01", uncertainty=0.5)
    out = calibrate.apply([already], registry)
    assert len(out) == 1
    assert out[0] is already


def test_pm_fit_tolerates_a_pair_missing_humidity() -> None:
    """A humidity-aware PM fit must not crash on a pair with no humidity, and ``predict`` with
    humidity omitted falls back to a zero humidity term rather than raising."""
    rows: list[tuple[float, float | None]] = [
        (2.0, 40.0),
        (4.0, None),
        (6.0, 60.0),
        (8.0, 45.0),
        (10.0, 70.0),
    ]
    pairs = [
        TrainingPair(
            node_id="node-01",
            parameter="pm25_ugm3",
            timestamp=f"2026-06-01T{i:02d}:00:00Z",
            raw=raw,
            reference=0.5 * raw + 0.2 * (hum or 0.0) + 1.0,
            humidity=hum,
        )
        for i, (raw, hum) in enumerate(rows)
    ]
    correction = calibrate.fit_one("node-01", "pm25_ugm3", pairs, "ref")
    assert correction.predictors == ("raw", "humidity")
    raw_coef = correction.coefficients[0]
    assert correction.predict(10.0, None) == pytest.approx(correction.intercept + raw_coef * 10.0)


def test_read_colocation_skips_blank_and_non_dict_lines(tmp_path: Path) -> None:
    """A committed co-location file is human-edited; blank and non-object lines are ignored,
    not parsed into bogus training pairs."""
    path = tmp_path / "colo.jsonl"
    path.write_text(
        "\n"
        "[1, 2, 3]\n"  # valid JSON, but not an object → skipped
        '{"node_id":"n1","parameter":"temp_c",'
        '"timestamp":"2026-06-01T00:00:00Z","raw":1.0,"reference":2.0}\n'
        "   \n",
        encoding="utf-8",
    )
    pairs = calibrate.read_colocation(path)
    assert len(pairs) == 1
    assert pairs[0].node_id == "n1"
    assert pairs[0].humidity is None
