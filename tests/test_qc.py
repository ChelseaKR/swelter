"""QC labels readings; it never deletes them."""

from __future__ import annotations

from swelter import qc
from swelter.models import Observation

from .conftest import make_obs


def _series(
    values: list[float], parameter: str = "temp_c", unit: str = "degC"
) -> list[Observation]:
    return [
        make_obs(
            timestamp=f"2026-06-01T{i:02d}:00:00Z",
            parameter=parameter,
            unit=unit,
            value=v,
        )
        for i, v in enumerate(values)
    ]


def test_range_flag_marks_impossible_values() -> None:
    flagged = qc.apply([make_obs(value=80.0)])  # 80 °C is outside the plausible range
    assert flagged[0].qc == "range"


def test_spike_is_isolated_departure() -> None:
    flagged = {o.timestamp: o.qc for o in qc.apply(_series([25.0, 25.0, 40.0, 25.0, 25.0]))}
    assert flagged["2026-06-01T02:00:00Z"] == "spike"
    assert flagged["2026-06-01T00:00:00Z"] == "ok"


def test_flatline_detects_stuck_sensor() -> None:
    flagged = qc.apply(_series([41.0] * 6, parameter="humidity_pct", unit="%"))
    assert all(o.qc == "flatline" for o in flagged)


def test_gentle_drift_is_not_flagged() -> None:
    flagged = qc.apply(_series([25.0, 25.5, 26.0, 26.4, 27.0, 27.3]))
    assert all(o.qc == "ok" for o in flagged)


def test_detect_gaps_finds_the_outage() -> None:
    series = [
        make_obs(timestamp=t)
        for t in ("2026-06-01T00:00:00Z", "2026-06-01T01:00:00Z", "2026-06-01T08:00:00Z")
    ]
    gaps = qc.detect_gaps(series, expected_interval_s=3600)
    assert len(gaps) == 1
    assert gaps[0].seconds == 7 * 3600


def test_node_health_marks_offline() -> None:
    obs = [
        make_obs(node_id="node-01", timestamp="2026-06-01T00:00:00Z"),
        make_obs(node_id="node-02", timestamp="2026-06-05T00:00:00Z"),
    ]
    health = {
        h.node_id: h for h in qc.node_health(obs, "2026-06-05T00:00:00Z", offline_after_s=3600)
    }
    assert health["node-02"].online is True
    assert health["node-01"].online is False
