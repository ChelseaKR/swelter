"""QC labels readings; it never deletes them."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from swelter import qc
from swelter.calibrate import Correction, CorrectionRegistry
from swelter.config import TwinWindow
from swelter.models import QC_EMITTED, QC_MISSING, Observation, format_timestamp

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


def test_a_dead_probe_humidity_is_flagged_out_of_range() -> None:
    """The two sentinel values a failed capacitive readout produces get the verdict that already
    means "not a measurement" — no new state, and the raw row is kept, not deleted (ADR 0043)."""
    readings = [
        make_obs(timestamp="2026-06-01T00:00:00Z", parameter="humidity_pct", unit="%", value=0.0),
        make_obs(timestamp="2026-06-01T01:00:00Z", parameter="humidity_pct", unit="%", value=1.0),
        make_obs(timestamp="2026-06-01T02:00:00Z", parameter="humidity_pct", unit="%", value=41.0),
    ]
    flagged = qc.apply(readings)
    assert [o.qc for o in flagged] == ["range", "range", "ok"]
    assert len(flagged) == len(readings)  # QC labels a reading, it never deletes one
    assert [o.value for o in flagged] == [0.0, 1.0, 41.0]


def test_spike_is_isolated_departure() -> None:
    flagged = {o.timestamp: o.qc for o in qc.apply(_series([25.0, 25.0, 40.0, 25.0, 25.0]))}
    assert flagged["2026-06-01T02:00:00Z"] == "spike"
    assert flagged["2026-06-01T00:00:00Z"] == "ok"


def test_flatline_detects_stuck_sensor() -> None:
    flagged = qc.apply(_series([41.0] * 6, parameter="humidity_pct", unit="%"))
    assert all(o.qc == "flatline" for o in flagged)


def test_qc_never_emits_the_missing_verdict_and_gaps_are_reported_separately() -> None:
    # Issue #147: `QC_MISSING` is a published verdict nothing writes. This pins the fact that it
    # stays that way — a gap is a gap in the *rows*, surfaced by `detect_gaps`, not an observation
    # asserting that a reading did not happen. If a future path starts emitting it, this fails and
    # the published data dictionary (which says the verdict is never emitted) gets updated with it.
    series = (
        _series([25.0, 25.0, 40.0, 25.0, 25.0])  # a spike
        + _series([41.0] * 6, parameter="humidity_pct", unit="%")  # a flatline
        + [make_obs(value=80.0)]  # out of range
        + [  # a genuine reporting gap: 00:00 then 12:00, nothing between
            make_obs(node_id="node-07", timestamp="2026-06-01T00:00:00Z", value=25.0),
            make_obs(node_id="node-07", timestamp="2026-06-01T12:00:00Z", value=25.0),
        ]
    )
    flagged = qc.apply(series)
    verdicts = {o.qc for o in flagged}
    assert verdicts <= QC_EMITTED
    assert QC_MISSING not in verdicts
    assert {"ok", "spike", "flatline", "range"} & verdicts  # the fixture really exercises QC

    # The gap is reported, just not as a row: it is its own artifact, computed from the timestamps
    # that are present.
    gaps = qc.detect_gaps(flagged, 3600)
    assert any(gap.node_id == "node-07" for gap in gaps)


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


# -- the published JSON contracts ---------------------------------------------------------------
#
# `health_report`, `coverage_equity`, and `calibration_block` back `/api/health.json` and
# `swelter qc --json`. Their key names are the contract a reader parses, so the key sets are
# asserted exactly: a renamed or dropped key is a breaking change to a published surface, not a
# refactor. The core-safety mutation gate had no test that noticed one.


def _hourly(node_id: str, hours: list[int], **kwargs: Any) -> list[Observation]:
    return [
        make_obs(node_id=node_id, timestamp=f"2026-06-01T{h:02d}:00:00Z", **kwargs) for h in hours
    ]


def test_health_report_json_contract() -> None:
    # node-07 reports at 00:00, goes silent, and comes back at 12:00 — one node entry and one gap,
    # so every published key of both shapes is present to be named.
    report: Any = qc.health_report(_hourly("node-07", [0, 12]))
    assert set(report) == {"interval_s", "latest", "summary", "nodes", "gaps"}
    assert report["interval_s"] == 3600.0  # the documented default sampling interval
    assert report["latest"] == "2026-06-01T12:00:00Z"
    assert set(report["summary"]) == {"total", "ok", "degraded", "offline"}
    assert set(report["nodes"][0]) == {
        "node_id",
        "status",
        "observations",
        "completeness",
        "flagged_fraction",
        "online",
        "last_seen",
    }
    assert set(report["gaps"][0]) == {"node_id", "parameter", "start", "end", "minutes"}
    assert report["gaps"][0] == {
        "node_id": "node-07",
        "parameter": "temp_c",
        "start": "2026-06-01T00:00:00Z",
        "end": "2026-06-01T12:00:00Z",
        "minutes": 720,  # twelve hours, reported in whole minutes
    }


def test_health_report_empty_json_contract() -> None:
    # With nothing to report the shape is the same minus `latest`: there is no latest reading to
    # name, and inventing one would be a claim the data does not support.
    report: Any = qc.health_report([])
    assert set(report) == {"interval_s", "summary", "nodes", "gaps"}
    assert report["gaps"] == []
    assert report["interval_s"] == 3600.0


def test_health_report_status_counts_start_from_zero() -> None:
    # Two nodes, both degraded: the seeded counters have to start at zero and accumulate per
    # status, so neither a pre-set count nor a lookup that ignores the status can pass.
    obs = _hourly("node-A", [0, 5]) + _hourly("node-B", [0, 5])
    report: Any = qc.health_report(obs, expected_interval_s=3600.0)
    assert report["summary"] == {"total": 2, "ok": 0, "degraded": 2, "offline": 0}


def test_health_report_calls_a_node_offline_after_three_intervals() -> None:
    # `offline_after_s` is three sampling intervals, and the boundary belongs to "still online":
    # a node exactly three intervals quiet has not yet missed enough to be called offline.
    obs = [
        make_obs(node_id="live", timestamp="2026-06-01T03:00:00Z"),
        make_obs(node_id="edge", timestamp="2026-06-01T00:00:00Z"),  # 10800 s = 3 * 3600
        make_obs(node_id="gone", timestamp="2026-05-31T23:59:59Z"),  # 10801 s
    ]
    report: Any = qc.health_report(obs, expected_interval_s=3600.0)
    online = {n["node_id"]: n["online"] for n in report["nodes"]}
    assert online == {"live": True, "edge": True, "gone": False}


def test_health_report_reports_at_most_max_gaps_worst_first() -> None:
    # Twelve readings three hours apart produce eleven gaps; the default cap publishes ten of
    # them, and the cap is a parameter a caller can raise.
    start = datetime(2026, 6, 1, tzinfo=UTC)
    obs = [
        make_obs(
            node_id="node-01",
            timestamp=format_timestamp(start + timedelta(hours=3 * i)),
        )
        for i in range(12)
    ]
    assert len(qc.detect_gaps(obs, 3600.0)) == 11
    capped: Any = qc.health_report(obs, expected_interval_s=3600.0)
    assert len(capped["gaps"]) == 10
    raised: Any = qc.health_report(obs, expected_interval_s=3600.0, max_gaps=11)
    assert len(raised["gaps"]) == 11


def test_health_report_rounds_flagged_fraction_to_three_places() -> None:
    obs = [
        *_hourly("node-01", [0, 1]),
        make_obs(node_id="node-01", timestamp="2026-06-01T02:00:00Z", value=80.0),  # out of range
    ]
    report: Any = qc.health_report(qc.apply(obs), expected_interval_s=3600.0)
    assert report["nodes"][0]["flagged_fraction"] == 0.333  # 1 of 3, at the published resolution


def test_health_report_carries_every_side_block_it_is_given(tmp_path: Path) -> None:
    # The four optional reads are additive and each one is keyed by name; a block that silently
    # dropped its argument would leave the caller's configured read out of the published JSON.
    (tmp_path / "digests.jsonl").write_text(
        '{"head": "abc123", "days": 2, "last_day": "2026-06-01"}\n', encoding="utf-8"
    )
    obs = _hourly("twin-a", [0, 1], parameter="pm25_ugm3", unit="ug/m3")
    obs += _hourly("twin-b", [0, 1], parameter="pm25_ugm3", unit="ug/m3")
    report: Any = qc.health_report(
        obs,
        coverage=qc.coverage_equity(obs, {"twin-a": ("c1", "Cedar")}),
        store_dir=tmp_path,
        twin_windows=[_TWIN_WINDOW],
        registry=_registry(_correction("twin-a", "pm25_ugm3", "2026-01-01T00:00:00Z")),
        calibration_horizon_days=90.0,
    )
    assert set(report) == {
        "interval_s",
        "latest",
        "summary",
        "nodes",
        "gaps",
        "coverage_equity",
        "integrity",
        "twin_agreement",
        "calibration",
    }
    assert report["integrity"]["head"] == "abc123"
    assert report["calibration"]["horizon_days"] == 90.0  # the caller's horizon, not the default
    assert report["twin_agreement"][0]["n_pairs"] == 2


def test_health_report_carries_side_blocks_for_an_empty_network(tmp_path: Path) -> None:
    # The empty-observations branch attaches the same blocks through the same implementation, so
    # a network that has not reported yet still shows the reads its operator configured.
    (tmp_path / "digests.jsonl").write_text(
        '{"head": "abc123", "days": 2, "last_day": "2026-06-01"}\n', encoding="utf-8"
    )
    report: Any = qc.health_report(
        [],
        coverage=qc.coverage_equity([], {"node-01": ("c1", "Cedar")}),
        store_dir=tmp_path,
        registry=CorrectionRegistry(),
        calibration_horizon_days=90.0,
    )
    assert set(report) == {
        "interval_s",
        "summary",
        "nodes",
        "gaps",
        "coverage_equity",
        "integrity",
        "calibration",
    }
    assert report["coverage_equity"]["summary"]["nodes"] == 1
    assert report["integrity"]["available"] is True
    assert report["calibration"]["horizon_days"] == 90.0


def test_integrity_block_reports_the_published_chain_head(tmp_path: Path) -> None:
    (tmp_path / "digests.jsonl").write_text(
        '{"date": "2026-06-01", "row_count": 3, "digest": "d1", "chain": "c1"}\n'
        '{"head": "c1", "days": 1, "last_day": "2026-06-01"}\n',
        encoding="utf-8",
    )
    report: Any = qc.health_report([], store_dir=tmp_path)
    assert report["integrity"] == {
        "available": True,
        "head": "c1",
        "last_verified_day": "2026-06-01",
        "days": 1,
    }


def test_integrity_block_is_unavailable_until_a_steward_writes_digests(tmp_path: Path) -> None:
    # `swelter verify-archive --write` has not run: the block says so rather than implying a
    # verified chain, and it carries no head, day, or count to be mistaken for one.
    report: Any = qc.health_report([], store_dir=tmp_path)
    assert report["integrity"] == {"available": False}


def test_coverage_equity_json_contract() -> None:
    # c1 has four nodes, two of them calibrated; c2 and c3 have none. The mixed cell is what makes
    # a per-cell tally that stopped counting, or a summary that read the raw column instead of the
    # calibrated one, visible.
    obs = [
        make_obs(node_id="a1", calibration="temp_c.enclosure-offset.a1"),
        make_obs(node_id="a2", calibration="temp_c.enclosure-offset.a2"),
        make_obs(node_id="a3"),
        make_obs(node_id="a4"),
        make_obs(node_id="b1"),
        make_obs(node_id="b2"),
        make_obs(node_id="c1n"),
    ]
    node_cells = {
        "a1": ("c1", "Cedar & 4th"),
        "a2": ("c1", "Cedar & 4th"),
        "a3": ("c1", "Cedar & 4th"),
        "a4": ("c1", "Cedar & 4th"),
        "b1": ("c2", "Oak & 4th"),
        "b2": ("c2", "Oak & 4th"),
        "c1n": ("c3", "Pine & 9th"),
    }
    report: Any = qc.coverage_equity(obs, node_cells)
    assert set(report) == {"summary", "cells", "note"}
    assert report["summary"] == {
        "cells": 3,
        "confirmed_cells": 1,
        "provisional_cells": 2,
        "nodes": 7,
        "calibrated_nodes": 2,
        "raw_nodes": 5,
        "calibrated_node_fraction": 0.286,
        "confirmed_cell_fraction": 0.333,
        "coverage_gap": True,
    }
    assert report["cells"][0] == {
        "cell_id": "c1",
        "label": "Cedar & 4th",  # the cell's own label, carried through from `node_cells`
        "nodes": 4,
        "calibrated_nodes": 2,
        "raw_nodes": 2,
        "confirmed": True,
    }
    assert [c["cell_id"] for c in report["cells"]] == ["c1", "c2", "c3"]


def test_coverage_equity_note_states_what_the_read_is_not() -> None:
    # The caveat travels with the numbers (hard rule #4). It is asserted verbatim because a
    # reworded or dropped caveat changes what the published block claims.
    report: Any = qc.coverage_equity([], {})
    assert report["note"] == (
        "Descriptive coverage of calibration, not a ranking of neighborhoods. Whether a "
        "coverage gap correlates with frontline blocks (audit B4) needs external context "
        "swelter does not hold and is a governance decision."
    )


def test_coverage_equity_of_an_empty_network_divides_by_nothing() -> None:
    report: Any = qc.coverage_equity([], {})
    assert report["summary"]["calibrated_node_fraction"] == 0.0
    assert report["summary"]["confirmed_cell_fraction"] == 0.0
    assert report["summary"]["coverage_gap"] is False  # no cells, so no cell is uncovered
    assert report["cells"] == []


def test_calibration_block_json_contract() -> None:
    obs = [make_obs(node_id="node-01", timestamp="2026-06-08T00:00:00Z")]
    registry = _registry(_correction("node-01", "temp_c", "2026-01-01T00:00:00Z"))
    block: Any = qc.calibration_block(obs, registry)
    assert set(block) == {"horizon_days", "summary", "corrections", "note"}
    assert block["horizon_days"] == qc.CALIBRATION_DRIFT_HORIZON_DAYS
    assert set(block["corrections"][0]) == {
        "node_id",
        "parameter",
        "version",
        "window_end",
        "age_days",
        "aging",
    }
    assert block["corrections"][0]["node_id"] == "node-01"
    assert block["corrections"][0]["parameter"] == "temp_c"
    assert block["corrections"][0]["window_end"] == "2026-01-01T00:00:00Z"


def test_calibration_block_forwards_the_horizon_it_was_given() -> None:
    # A block that dropped the horizon on the way to `correction_ages` would quietly report every
    # correction against the 365-day default, whatever the operator configured.
    obs = [make_obs(node_id="node-01", timestamp="2026-06-08T00:00:00Z")]
    registry = _registry(_correction("node-01", "temp_c", "2026-01-01T00:00:00Z"))  # ~158 days
    default: Any = qc.calibration_block(obs, registry)
    assert default["summary"] == {
        "corrections": 1,
        "aging": 0,
        "fresh": 1,
    }
    tight: Any = qc.calibration_block(obs, registry, horizon_days=90.0)
    assert tight["horizon_days"] == 90.0
    assert tight["summary"] == {"corrections": 1, "aging": 1, "fresh": 0}
    assert tight["corrections"][0]["aging"] is True


def test_calibration_block_note_states_what_drift_surveillance_never_does() -> None:
    # Verbatim for the same reason as the coverage note: this caveat is the reason the block is
    # allowed to exist beside calibrated values without demoting any of them.
    block: Any = qc.calibration_block([], CorrectionRegistry())
    assert block["note"] == (
        "Descriptive drift surveillance — the age of each correction's co-location evidence "
        "against the latest observation. It never changes a calibrated value or its state "
        "(hard rule #3: a correction being aging does not demote its output to provisional), "
        "and it is never a ranking of neighborhoods, only a per-correction recalibration "
        "signal."
    )


# -- the arithmetic behind a verdict -------------------------------------------------------------


def test_node_health_completeness_expects_every_parameter_over_the_span() -> None:
    # One node reporting two parameters over a six-hour span owes 7 readings per parameter. It
    # filed 8 of the 14, so it is 57% complete — not 100% because it filed 8 of one parameter's
    # worth, which is what a per-parameter expectation is there to prevent.
    obs = _hourly("node-01", [0, 1, 2, 5, 6])
    obs += _hourly("node-01", [0, 2, 6], parameter="humidity_pct", unit="%")
    [health] = qc.node_health(
        obs, "2026-06-01T06:00:00Z", offline_after_s=100000, expected_interval_s=3600.0
    )
    assert health.observations == 8
    assert health.completeness == 0.571  # 8 / 14, at the published resolution
    assert health.status == "degraded"


def test_node_health_completeness_never_exceeds_one() -> None:
    # A node sampling twice as fast as the configured interval is not 150% complete; over-
    # reporting is capped rather than published as a completeness above full.
    obs = [
        make_obs(node_id="node-01", timestamp=t)
        for t in ("2026-06-01T00:00:00Z", "2026-06-01T00:30:00Z", "2026-06-01T01:00:00Z")
    ]
    [health] = qc.node_health(
        obs, "2026-06-01T01:00:00Z", offline_after_s=100000, expected_interval_s=3600.0
    )
    assert health.completeness == 1.0


def test_node_health_counts_clean_readings_as_the_remainder_of_the_flagged_ones() -> None:
    obs = qc.apply(
        [
            *_hourly("node-01", [0, 1]),
            make_obs(node_id="node-01", timestamp="2026-06-01T02:00:00Z", value=80.0),
        ]
    )
    [health] = qc.node_health(
        obs, "2026-06-01T02:00:00Z", offline_after_s=100000, expected_interval_s=3600.0
    )
    assert (health.observations, health.flagged, health.ok) == (3, 1, 2)
    assert health.last_seen == "2026-06-01T02:00:00Z"


def test_detect_gaps_boundary_is_strictly_longer_than_the_tolerated_interval() -> None:
    # The default tolerance is 1.5 intervals, and a stretch exactly that long is still on time.
    on_time = [
        make_obs(timestamp="2026-06-01T00:00:00Z"),
        make_obs(timestamp="2026-06-01T01:30:00Z"),  # exactly 1.5 * 3600 s
    ]
    assert qc.detect_gaps(on_time, 3600.0) == []
    late = [
        make_obs(timestamp="2026-06-01T00:00:00Z"),
        make_obs(timestamp="2026-06-01T01:31:00Z"),  # one minute past the tolerance
    ]
    assert len(qc.detect_gaps(late, 3600.0)) == 1
    # Two full intervals is a gap under the default tolerance and not under a looser one, so the
    # tolerance really is 1.5 rather than something wider.
    two_intervals = [
        make_obs(timestamp="2026-06-01T00:00:00Z"),
        make_obs(timestamp="2026-06-01T02:00:00Z"),
    ]
    assert len(qc.detect_gaps(two_intervals, 3600.0)) == 1
    assert qc.detect_gaps(two_intervals, 3600.0, tolerance=2.5) == []


def test_detect_gaps_names_the_series_and_reports_worst_first() -> None:
    obs = _hourly("node-01", [0, 2, 6])  # a two-hour gap, then a four-hour one
    gaps = qc.detect_gaps(obs, 3600.0)
    assert [g.seconds for g in gaps] == [14400.0, 7200.0]  # longest outage first
    assert gaps[0] == qc.Gap(
        node_id="node-01",
        parameter="temp_c",
        start="2026-06-01T02:00:00Z",
        end="2026-06-01T06:00:00Z",
        seconds=14400.0,
    )


def test_a_steady_ramp_is_not_a_spike() -> None:
    # The spike test compares against the median of *both* neighbours. Judged against either one
    # alone, the middle of a 10-30-50 ramp looks like a 20-degree departure; against both, it is
    # exactly where it belongs.
    assert [o.qc for o in qc.apply(_series([10.0, 30.0, 50.0]))] == ["ok", "ok", "ok"]


def test_a_departure_exactly_at_the_threshold_is_not_a_spike() -> None:
    # The per-parameter thresholds are deliberately conservative, and the bar is "further than",
    # so a reading exactly one threshold away from its neighbours keeps its clean verdict.
    assert [o.qc for o in qc.apply(_series([25.0, 33.0, 25.0]))] == ["ok", "ok", "ok"]  # 8.0 degC
    assert [o.qc for o in qc.apply(_series([25.0, 33.1, 25.0]))] == ["ok", "spike", "ok"]


def test_the_first_and_last_reading_of_a_series_are_never_spikes() -> None:
    # An end reading has only one neighbour, so there is no local median to judge it against and
    # it keeps its verdict. Scanning past the ends would wrap around and compare it to the far
    # end of the series instead.
    flagged = [o.qc for o in qc.apply(_series([20.0, 20.0, 20.0, 20.0, 20.0, 40.0]))]
    assert flagged == ["ok", "ok", "ok", "ok", "spike", "ok"]


def test_every_interior_reading_is_examined_for_a_spike() -> None:
    # Both ends of the interior are scanned: a spike immediately after the first reading and one
    # immediately before the last are found, not skipped as if they were end readings.
    assert [o.qc for o in qc.apply(_series([25.0, 40.0, 25.0, 25.0, 25.0]))] == [
        "ok",
        "spike",
        "ok",
        "ok",
        "ok",
    ]
    assert [o.qc for o in qc.apply(_series([25.0, 25.0, 25.0, 40.0, 25.0]))] == [
        "ok",
        "ok",
        "ok",
        "spike",
        "ok",
    ]


def test_an_already_flagged_reading_does_not_stop_the_spike_scan() -> None:
    # A reading that already failed the range check is skipped, not treated as the end of the
    # series: a genuine spike later in the same series still gets found.
    series = _series([80.0, 25.0, 25.0, 40.0, 25.0])  # 80 degC is out of range
    assert [o.qc for o in qc.apply(series)] == ["range", "ok", "ok", "spike", "ok"]


def test_twin_pairing_skips_a_long_unmatched_lead_on_either_side() -> None:
    # The merge walk has to be able to discard a long run from one side before it reaches the
    # overlap. Ten unmatched leading readings on twin-b, then one real pair.
    obs = [
        make_obs(
            node_id="twin-b",
            timestamp=f"2026-06-01T{h:02d}:00:00Z",
            parameter="pm25_ugm3",
            unit="ug/m3",
            value=1.0,
        )
        for h in range(10)
    ]
    obs.append(
        make_obs(
            node_id="twin-b",
            timestamp="2026-06-01T10:00:00Z",
            parameter="pm25_ugm3",
            unit="ug/m3",
            value=12.0,
        )
    )
    obs.append(
        make_obs(
            node_id="twin-a",
            timestamp="2026-06-01T10:00:00Z",
            parameter="pm25_ugm3",
            unit="ug/m3",
            value=10.0,
        )
    )
    [result] = qc.twin_agreement(obs, [_TWIN_WINDOW])
    assert result.n_pairs == 1
    assert result.residual_spread == 0.0

    # The mirror case: twin-a is the side with the unmatched lead.
    mirrored = [
        make_obs(
            node_id="twin-a" if o.node_id == "twin-b" else "twin-b",
            timestamp=o.timestamp,
            parameter=o.parameter,
            unit=o.unit,
            value=o.value,
        )
        for o in obs
    ]
    [mirror_result] = qc.twin_agreement(mirrored, [_TWIN_WINDOW])
    assert mirror_result.n_pairs == 1
