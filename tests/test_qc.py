"""QC labels readings; it never deletes them."""

from __future__ import annotations

from typing import Any

from swelter import qc
from swelter.calibrate import Correction, CorrectionRegistry
from swelter.config import TwinWindow
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


def _twin_series(
    node_id: str, values: list[float], parameter: str = "pm25_ugm3", unit: str = "ug/m3"
) -> list[Observation]:
    return [
        make_obs(
            node_id=node_id,
            timestamp=f"2026-06-01T{i:02d}:00:00Z",
            parameter=parameter,
            unit=unit,
            value=v,
        )
        for i, v in enumerate(values)
    ]


_TWIN_WINDOW = TwinWindow(
    node_a="twin-a",
    node_b="twin-b",
    parameter="pm25_ugm3",
    start="2026-06-01T00:00:00Z",
    end="2026-06-01T23:00:00Z",
)


def test_twin_agreement_identical_series_has_zero_spread() -> None:
    values = [10.0, 11.0, 12.0, 13.0]
    obs = _twin_series("twin-a", values) + _twin_series("twin-b", values)
    [result] = qc.twin_agreement(obs, [_TWIN_WINDOW])
    assert result.n_pairs == len(values)
    assert result.residual_spread == 0.0
    # Cross-checked is annotation only: it never touches a value or assigns a calibration.
    assert all(o.calibration == "raw" and o.value in values for o in obs)


def test_twin_agreement_divergent_series_has_nonzero_spread() -> None:
    obs = _twin_series("twin-a", [10.0, 20.0, 10.0, 20.0]) + _twin_series(
        "twin-b", [10.0, 10.0, 20.0, 20.0]
    )
    [result] = qc.twin_agreement(obs, [_TWIN_WINDOW])
    assert result.n_pairs == 4
    assert result.residual_spread > 0.0


def test_twin_agreement_no_matching_timestamps_reports_zero_pairs() -> None:
    # Same window, same parameter, but the two nodes' readings never land near each other in
    # time (a full day apart) — nothing pairs within the default tolerance.
    obs = _twin_series("twin-a", [10.0, 11.0])
    obs.extend(
        make_obs(
            node_id="twin-b",
            timestamp=f"2026-06-02T{i:02d}:00:00Z",
            parameter="pm25_ugm3",
            unit="ug/m3",
            value=v,
        )
        for i, v in enumerate([10.0, 11.0])
    )
    window = TwinWindow(
        node_a="twin-a",
        node_b="twin-b",
        parameter="pm25_ugm3",
        start="2026-06-01T00:00:00Z",
        end="2026-06-02T23:00:00Z",
    )
    [result] = qc.twin_agreement(obs, [window])
    assert result.n_pairs == 0
    assert result.residual_spread == 0.0


def test_twin_agreement_window_filters_out_of_range_readings() -> None:
    # twin-b's second reading falls outside the configured window and must not be paired.
    obs = [
        *_twin_series("twin-a", [10.0, 11.0]),
        make_obs(
            node_id="twin-b",
            timestamp="2026-06-01T00:00:00Z",
            parameter="pm25_ugm3",
            unit="ug/m3",
            value=10.0,
        ),
        make_obs(
            node_id="twin-b",
            timestamp="2026-06-05T00:00:00Z",
            parameter="pm25_ugm3",
            unit="ug/m3",
            value=999.0,
        ),
    ]
    [result] = qc.twin_agreement(obs, [_TWIN_WINDOW])
    assert result.n_pairs == 1
    assert result.residual_spread == 0.0


def test_twin_agreement_skips_twin_bs_unmatched_leading_readings() -> None:
    # twin-b reports twice before twin-a starts (beyond tolerance) — those leading readings must
    # be skipped rather than matched, and pairing resumes once the two series overlap in time.
    obs = [
        make_obs(
            node_id="twin-b",
            timestamp="2026-06-01T00:00:00Z",
            parameter="pm25_ugm3",
            unit="ug/m3",
            value=1.0,
        ),
        make_obs(
            node_id="twin-b",
            timestamp="2026-06-01T01:00:00Z",
            parameter="pm25_ugm3",
            unit="ug/m3",
            value=2.0,
        ),
        make_obs(
            node_id="twin-b",
            timestamp="2026-06-01T02:00:00Z",
            parameter="pm25_ugm3",
            unit="ug/m3",
            value=10.0,
        ),
        make_obs(
            node_id="twin-a",
            timestamp="2026-06-01T02:00:00Z",
            parameter="pm25_ugm3",
            unit="ug/m3",
            value=10.0,
        ),
    ]
    [result] = qc.twin_agreement(obs, [_TWIN_WINDOW])
    assert result.n_pairs == 1
    assert result.residual_spread == 0.0


def test_cross_checked_when_twins_agree_within_bound() -> None:
    # Two twins tracking each other closely (residuals well under the pm25 default bar of 5 µg/m³)
    # read as cross-checked — precision confirmed, never accuracy.
    obs = _twin_series("twin-a", [10.0, 11.0, 12.0, 13.0]) + _twin_series(
        "twin-b", [10.5, 11.2, 11.8, 13.3]
    )
    [result] = qc.twin_agreement(obs, [_TWIN_WINDOW])
    assert result.n_pairs == 4
    assert result.agreement_threshold == qc.TWIN_AGREEMENT_THRESHOLD["pm25_ugm3"]
    assert result.residual_spread <= result.agreement_threshold
    assert result.cross_checked is True
    assert result.status == "cross-checked"


def test_diverged_when_twins_exceed_bound_fires_smoke_alarm() -> None:
    # Twins swinging in opposite directions blow past the agreement bar: the drift smoke-alarm
    # fires (diverged), and the pair is NOT cross-checked.
    obs = _twin_series("twin-a", [10.0, 20.0, 10.0, 20.0]) + _twin_series(
        "twin-b", [20.0, 10.0, 20.0, 10.0]
    )
    [result] = qc.twin_agreement(obs, [_TWIN_WINDOW])
    assert result.n_pairs == 4
    assert result.residual_spread > result.agreement_threshold
    assert result.cross_checked is False
    assert result.status == "diverged"


def test_too_few_pairs_reads_insufficient_data_not_cross_checked() -> None:
    # A perfectly tight but tiny window (fewer than MIN_TWIN_PAIRS matched pairs) has no basis for
    # a verdict: it reads insufficient-data, never a free cross-checked pass on thin evidence.
    n = qc.MIN_TWIN_PAIRS - 1
    values = [10.0] * n
    obs = _twin_series("twin-a", values) + _twin_series("twin-b", values)
    [result] = qc.twin_agreement(obs, [_TWIN_WINDOW])
    assert result.n_pairs == n
    assert result.residual_spread <= result.agreement_threshold
    assert result.cross_checked is False
    assert result.status == "insufficient-data"


def test_window_agreement_threshold_override_tightens_the_bar() -> None:
    # The same closely-agreeing twins are marked diverged when the pair sets a stricter bar than
    # the per-parameter default — the documented config knob is honoured.
    obs = _twin_series("twin-a", [10.0, 11.0, 12.0, 13.0]) + _twin_series(
        "twin-b", [10.5, 11.2, 11.8, 13.3]
    )
    strict = TwinWindow(
        node_a="twin-a",
        node_b="twin-b",
        parameter="pm25_ugm3",
        start="2026-06-01T00:00:00Z",
        end="2026-06-01T23:00:00Z",
        agreement_threshold=0.1,
    )
    [result] = qc.twin_agreement(obs, [strict])
    assert result.agreement_threshold == 0.1
    assert result.status == "diverged"
    assert result.cross_checked is False


def test_cross_check_never_touches_value_or_calibration_state() -> None:
    # Hard rule #3: computing the cross-checked tier — whether the twins agree or diverge — mutates
    # no observation, promotes nothing past provisional, and assigns no calibration version.
    values = [10.0, 20.0, 10.0, 20.0]
    diverging = _twin_series("twin-a", values) + _twin_series("twin-b", list(reversed(values)))
    before = [(o.node_id, o.timestamp, o.value, o.calibration, o.uncertainty) for o in diverging]
    [result] = qc.twin_agreement(diverging, [_TWIN_WINDOW])
    report: Any = qc.health_report(diverging, twin_windows=[_TWIN_WINDOW])
    after = [(o.node_id, o.timestamp, o.value, o.calibration, o.uncertainty) for o in diverging]
    assert before == after
    assert all(o.calibration == "raw" and o.uncertainty is None for o in diverging)
    assert result.status == "diverged"
    # The verdict rides along as QC/health metadata; it is not a value on the calibration axis.
    assert report["twin_agreement"][0]["cross_checked"] is False


def test_health_report_omits_twin_agreement_by_default() -> None:
    report: Any = qc.health_report([make_obs(node_id="node-01")])
    assert "twin_agreement" not in report


def test_health_report_omits_twin_agreement_when_observations_empty_and_no_windows() -> None:
    report: Any = qc.health_report([])
    assert "twin_agreement" not in report


def test_health_report_surfaces_twin_agreement_when_configured() -> None:
    values = [10.0, 10.0, 10.0]
    obs = _twin_series("twin-a", values) + _twin_series("twin-b", values)
    report: Any = qc.health_report(obs, twin_windows=[_TWIN_WINDOW])
    assert report["twin_agreement"] == [
        {
            "node_a": "twin-a",
            "node_b": "twin-b",
            "parameter": "pm25_ugm3",
            "n_pairs": 3,
            "residual_spread": 0.0,
            "agreement_threshold": 5.0,
            "cross_checked": True,
            "status": "cross-checked",
            "window_start": "2026-06-01T00:00:00Z",
            "window_end": "2026-06-01T23:00:00Z",
        }
    ]
    # The rest of the report shape (summary keys) is unaffected by the twin block riding along.
    assert set(report["summary"]) == {"total", "ok", "degraded", "offline"}


def test_health_report_surfaces_twin_agreement_for_empty_observations() -> None:
    report: Any = qc.health_report([], twin_windows=[_TWIN_WINDOW])
    # No matched pairs is not a pass: too little evidence to judge reads insufficient-data, and the
    # verdict never flips to cross-checked on an empty window.
    assert report["twin_agreement"] == [
        {
            "node_a": "twin-a",
            "node_b": "twin-b",
            "parameter": "pm25_ugm3",
            "n_pairs": 0,
            "residual_spread": 0.0,
            "agreement_threshold": 5.0,
            "cross_checked": False,
            "status": "insufficient-data",
            "window_start": "2026-06-01T00:00:00Z",
            "window_end": "2026-06-01T23:00:00Z",
        }
    ]


# -- correction-drift surveillance (FIX-03, safe subset) ---------------------------------------


def _correction(node_id: str, parameter: str, window_end: str) -> Correction:
    """A minimal fitted correction with a chosen co-location ``window_end`` — the only field the
    age math consults. The other fields are plausible fixed values; drift surveillance reads none
    of them, and it never touches an observation's value or state (hard rule #3)."""
    method = "enclosure-offset"
    return Correction(
        version=f"{parameter}.{method}.{node_id}",
        node_id=node_id,
        parameter=parameter,
        method=method,
        predictors=("raw",),
        coefficients=(1.0,),
        intercept=0.0,
        residual_std=0.5,
        r2=0.99,
        n=48,
        reference="reference-monitor",
        window_start="2024-01-01T00:00:00Z",
        window_end=window_end,
    )


def _registry(*corrections: Correction) -> CorrectionRegistry:
    registry = CorrectionRegistry()
    for correction in corrections:
        registry.add(correction)
    return registry


def test_correction_ages_flags_aged_and_fresh() -> None:
    # Latest reading is 2026-06-08. node-01's correction closed 2+ years earlier (aging);
    # node-02's closed a few weeks earlier (fresh).
    obs = [make_obs(node_id="node-01", timestamp="2026-06-08T00:00:00Z")]
    registry = _registry(
        _correction("node-01", "temp_c", "2024-01-01T00:00:00Z"),
        _correction("node-02", "temp_c", "2026-05-01T00:00:00Z"),
    )
    ages = {a.node_id: a for a in qc.correction_ages(obs, registry)}
    assert ages["node-01"].aging is True
    assert ages["node-01"].age_days > 365
    assert ages["node-02"].aging is False
    assert ages["node-02"].age_days < 365


def test_correction_ages_horizon_is_a_parameter() -> None:
    obs = [make_obs(timestamp="2026-06-08T00:00:00Z")]
    registry = _registry(_correction("node-01", "temp_c", "2026-01-01T00:00:00Z"))  # ~158 days old
    assert qc.correction_ages(obs, registry)[0].aging is False  # default 365-day horizon
    tight = qc.correction_ages(obs, registry, horizon_days=90.0)[0]
    assert tight.aging is True  # same age, tighter horizon → aging


def test_correction_ages_empty_without_observations() -> None:
    registry = _registry(_correction("node-01", "temp_c", "2024-01-01T00:00:00Z"))
    assert qc.correction_ages([], registry) == []  # no latest reading to anchor "how long ago"


def test_correction_ages_skips_correction_without_window_end() -> None:
    obs = [make_obs(timestamp="2026-06-08T00:00:00Z")]
    registry = _registry(_correction("node-01", "temp_c", ""))  # no anchor → skipped
    assert qc.correction_ages(obs, registry) == []


def test_health_report_calibration_block_flags_aging() -> None:
    obs = [make_obs(node_id="node-01", timestamp=f"2026-06-08T{h:02d}:00:00Z") for h in (0, 1, 2)]
    registry = _registry(
        _correction("node-01", "temp_c", "2024-01-01T00:00:00Z"),  # aging
        _correction("node-02", "temp_c", "2026-05-20T00:00:00Z"),  # fresh
    )
    report: Any = qc.health_report(obs, registry=registry)
    block = report["calibration"]
    assert block["horizon_days"] == qc.CALIBRATION_DRIFT_HORIZON_DAYS
    assert block["summary"] == {"corrections": 2, "aging": 1, "fresh": 1}
    flagged = {c["version"]: c["aging"] for c in block["corrections"]}
    assert flagged["temp_c.enclosure-offset.node-01"] is True
    assert flagged["temp_c.enclosure-offset.node-02"] is False
    # The liveness summary shape is untouched by the calibration block riding along.
    assert set(report["summary"]) == {"total", "ok", "degraded", "offline"}


def test_health_report_calibration_absent_without_registry() -> None:
    report: Any = qc.health_report([make_obs(node_id="node-01")])
    assert "calibration" not in report


def test_health_report_calibration_present_but_empty_when_registry_empty() -> None:
    # An empty registry is still "supplied" → the block appears with zero corrections, so a reader
    # can tell "no calibration at all" from "the surveillance was never asked for".
    report: Any = qc.health_report([make_obs()], registry=CorrectionRegistry())
    assert report["calibration"]["summary"] == {"corrections": 0, "aging": 0, "fresh": 0}
