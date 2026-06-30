"""QC labels readings; it never deletes them."""

from __future__ import annotations

from typing import Any

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


def test_health_report_summarizes_status_and_gaps() -> None:
    live = [
        make_obs(node_id="node-01", timestamp=f"2026-06-01T{h:02d}:00:00Z", value=25.0)
        for h in (10, 11, 12)  # hourly, complete, recent → ok
    ]
    # node-07 reports, goes silent for 12 hours, then resumes — an internal gap and a sparse record.
    gappy = [
        make_obs(node_id="node-07", timestamp="2026-06-01T00:00:00Z", value=24.0),
        make_obs(node_id="node-07", timestamp="2026-06-01T12:00:00Z", value=24.0),
    ]
    report: Any = qc.health_report([*live, *gappy], expected_interval_s=3600.0)
    assert report["summary"]["total"] == 2
    assert report["summary"]["degraded"] == 1  # node-07 backfilled sparsely → degraded
    assert any(g["node_id"] == "node-07" for g in report["gaps"])
    assert {n["node_id"] for n in report["nodes"]} == {"node-01", "node-07"}


def test_health_report_handles_empty() -> None:
    report: Any = qc.health_report([])
    assert report["summary"] == {"total": 0, "ok": 0, "degraded": 0, "offline": 0}
    assert report["nodes"] == []


def test_coverage_equity_counts_calibrated_vs_raw_per_cell() -> None:
    # node-01 has a fitted correction (a calibrated row); node-02 is raw-only.
    obs = [
        make_obs(node_id="node-01", calibration="temp_c.enclosure-offset.node-01"),
        make_obs(node_id="node-02"),  # default calibration is raw
    ]
    node_cells = {"node-01": ("c1", "Cedar & 4th"), "node-02": ("c2", "Oak & 4th")}
    report: Any = qc.coverage_equity(obs, node_cells)
    s = report["summary"]
    assert s["nodes"] == 2
    assert s["calibrated_nodes"] == 1
    assert s["raw_nodes"] == 1
    assert s["confirmed_cells"] == 1
    assert s["provisional_cells"] == 1
    assert s["coverage_gap"] is True  # one cell has no calibrated node yet
    cells = {c["cell_id"]: c for c in report["cells"]}
    assert cells["c1"]["confirmed"] is True
    assert cells["c2"]["confirmed"] is False


def test_coverage_equity_groups_nodes_in_one_cell() -> None:
    # Two nodes published into the same cell — one calibrated confirms the cell.
    obs = [
        make_obs(node_id="a", calibration="pm25_ugm3.epa-humidity.a"),
        make_obs(node_id="b"),
    ]
    node_cells = {"a": ("c1", "Block"), "b": ("c1", "Block")}
    report: Any = qc.coverage_equity(obs, node_cells)
    cell = report["cells"][0]
    assert cell["nodes"] == 2
    assert cell["calibrated_nodes"] == 1
    assert cell["raw_nodes"] == 1
    assert cell["confirmed"] is True
    assert report["summary"]["cells"] == 1
    assert report["summary"]["coverage_gap"] is False  # every cell has a calibrated node


def test_coverage_equity_rides_along_in_health_report() -> None:
    obs = [make_obs(node_id="node-01", timestamp=f"2026-06-01T{h:02d}:00:00Z") for h in (0, 1, 2)]
    coverage = qc.coverage_equity(obs, {"node-01": ("c1", "Cedar")})
    report: Any = qc.health_report(obs, coverage=coverage)
    assert report["coverage_equity"]["summary"]["nodes"] == 1
    # The liveness summary is untouched by the coverage block riding along.
    assert set(report["summary"]) == {"total", "ok", "degraded", "offline"}


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


def test_node_health_flags_incomplete_node_as_degraded() -> None:
    obs = [make_obs(node_id="node-A", timestamp=f"2026-06-01T{i:02d}:00:00Z") for i in range(5)]
    # node-B is online (recent last reading) but missed 3 of the 5 hours — a mid-window outage.
    obs += [
        make_obs(node_id="node-B", timestamp="2026-06-01T00:00:00Z"),
        make_obs(node_id="node-B", timestamp="2026-06-01T04:00:00Z"),
    ]
    health = {
        h.node_id: h
        for h in qc.node_health(
            obs, "2026-06-01T04:00:00Z", offline_after_s=7200, expected_interval_s=3600
        )
    }
    assert health["node-A"].status == "ok"
    assert health["node-B"].status == "degraded"  # online, but only 40% complete
