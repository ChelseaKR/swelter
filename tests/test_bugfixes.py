"""Regression tests for defects found in the codebase-wide bug review.

Each test pins a specific confirmed bug so it cannot silently return.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from swelter import aggregate, calibrate, export, ingest, qc
from swelter.calibrate import CorrectionRegistry, TrainingPair
from swelter.config import NetworkConfig, NodeConfig
from swelter.models import Observation, pm25_aqi
from swelter.store import SqliteStore

from .conftest import make_obs

# --- models: PM2.5 AQI breakpoint gaps and NaN -----------------------------------------------


@pytest.mark.parametrize("conc", [9.05, 35.45, 55.45, 125.45, 225.45])
def test_pm25_aqi_breakpoint_gaps_are_not_hazardous(conc: float) -> None:
    """A clean mean landing between EPA bands must not be reported as top-of-scale Hazardous."""
    aqi, category = pm25_aqi(conc)
    assert category != "Hazardous"
    assert aqi < 500


def test_pm25_aqi_rejects_nan() -> None:
    with pytest.raises(ValueError):
        pm25_aqi(float("nan"))


# --- ingest: non-finite values and malformed lines ------------------------------------------


def test_ingest_quarantines_payloads_with_only_nonfinite(store: SqliteStore) -> None:
    result = ingest.ingest(
        [
            {"node_id": "n1", "timestamp": "2026-06-01T00:00:00Z", "temp_c": float("nan")},
            {"node_id": "n1", "timestamp": "2026-06-01T01:00:00Z", "temp_c": float("inf")},
        ],
        store,
    )
    assert store.count() == 0  # neither silently stored nor mislabeled a duplicate
    assert result.quarantined == 2


def test_ingest_keeps_finite_drops_nonfinite(store: SqliteStore) -> None:
    ingest.ingest(
        [
            {
                "node_id": "n1",
                "timestamp": "2026-06-01T00:00:00Z",
                "temp_c": 25.0,
                "pm25_ugm3": float("inf"),
            }
        ],
        store,
    )
    stored = store.read()
    assert len(stored) == 1
    assert stored[0].parameter == "temp_c"


def test_malformed_jsonl_line_is_quarantined_not_fatal(store: SqliteStore, tmp_path: Path) -> None:
    source = tmp_path / "in.jsonl"
    source.write_text(
        '{"node_id":"n1","timestamp":"2026-06-01T00:00:00Z","temp_c":25.0}\n'
        "{ this is not json\n"
        '{"node_id":"n2","timestamp":"2026-06-01T00:00:00Z","temp_c":26.0}\n',
        encoding="utf-8",
    )
    result = ingest.ingest_file(source, store, quarantine_path=tmp_path / "q.jsonl")
    assert result.accepted_payloads == 2  # both valid lines survive the one corrupt line
    assert result.quarantined == 1
    assert store.count() == 2


# --- qc: spike contamination -----------------------------------------------------------------


def test_spike_not_contaminated_by_range_fault() -> None:
    series = [
        make_obs(timestamp=f"2026-06-01T{i:02d}:00:00Z", value=v)
        for i, v in enumerate([22.0, 22.0, -100.0, 22.0, 22.0])
    ]
    flagged = {o.timestamp: o.qc for o in qc.apply(series)}
    assert flagged["2026-06-01T02:00:00Z"] == "range"  # the real fault
    assert flagged["2026-06-01T01:00:00Z"] == "ok"  # valid neighbours not mislabeled as spikes
    assert flagged["2026-06-01T03:00:00Z"] == "ok"


# --- calibrate: humidity handling and singular groups ----------------------------------------


def _pm_pairs() -> list[TrainingPair]:
    rows = [(2.0, 40.0), (4.0, 55.0), (6.0, 60.0), (8.0, 45.0), (10.0, 70.0), (12.0, 50.0)]
    return [
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


def test_pm_correction_skipped_without_cotimed_humidity() -> None:
    registry = CorrectionRegistry()
    registry.add(calibrate.fit_one("node-01", "pm25_ugm3", _pm_pairs(), "ref"))
    out = calibrate.apply([make_obs(parameter="pm25_ugm3", unit="ug/m3", value=40.0)], registry)
    assert all(not o.is_calibrated for o in out)  # must not publish a humidity-less PM value


def test_pm_correction_applies_with_humidity() -> None:
    registry = CorrectionRegistry()
    registry.add(calibrate.fit_one("node-01", "pm25_ugm3", _pm_pairs(), "ref"))
    obs = [
        make_obs(parameter="pm25_ugm3", unit="ug/m3", value=40.0),
        make_obs(parameter="humidity_pct", unit="%", value=70.0),
    ]
    assert any(o.is_calibrated for o in calibrate.apply(obs, registry))


def test_humidity_index_excludes_qc_rejected() -> None:
    rejected = make_obs(parameter="humidity_pct", unit="%", value=999.0, qc="range")
    assert calibrate.humidity_index([rejected]) == {}


def test_fit_skips_singular_group_without_aborting() -> None:
    singular = [
        TrainingPair("node-A", "pm25_ugm3", f"2026-06-01T{i:02d}:00:00Z", float(i), 10.0, 80.0)
        for i in range(4)
    ]
    valid = [
        TrainingPair("node-B", "temp_c", f"2026-06-01T{i:02d}:00:00Z", float(i), 2.0 * i + 1.0)
        for i in range(4)
    ]
    registry = calibrate.fit(singular + valid)
    assert registry.get("node-B", "temp_c") is not None  # one bad group must not lose the rest
    assert registry.get("node-A", "pm25_ugm3") is None


def test_zero_coefficient_serializes_without_negative_zero(tmp_path: Path) -> None:
    pairs = [
        TrainingPair("n", "temp_c", f"2026-06-01T{i:02d}:00:00Z", float(v), 25.0)
        for i, v in enumerate([20, 22, 24])
    ]
    registry = CorrectionRegistry()
    registry.add(calibrate.fit_one("n", "temp_c", pairs, "ref"))
    path = tmp_path / "c.yaml"
    registry.to_yaml(path)
    assert "-0.0" not in path.read_text(encoding="utf-8")


# --- store: timestamp normalization ----------------------------------------------------------


def test_read_normalizes_noncanonical_timestamp(store: SqliteStore) -> None:
    store.write(
        [
            make_obs(timestamp="2026-06-02T12:00:00Z"),
            make_obs(timestamp="2026-06-03T12:00:00Z"),
        ]
    )
    # An offset form of the same instant must still include the boundary row.
    assert len(store.read(until="2026-06-02T12:00:00+00:00")) == 1
    assert len(store.read(since="2026-06-02T12:00:00+00:00")) == 2


# --- export: CSV injection and valid JSON ----------------------------------------------------


def test_csv_formula_injection_neutralized() -> None:
    line = export.to_csv([make_obs(node_id="=HYPERLINK(1)")]).strip().splitlines()[1]
    assert line.startswith("'=HYPERLINK")  # prefixed so a spreadsheet treats it as literal text


def test_to_json_stays_valid_for_nonfinite_value() -> None:
    obs = Observation(
        node_id="n1",
        timestamp="2026-06-01T00:00:00Z",
        parameter="temp_c",
        value=float("inf"),
        unit="degC",
    )
    doc = json.loads(export.to_json([obs]))  # must parse under a strict JSON loader
    assert doc["observations"][0]["value"] is None


# --- user-research fixes: plausibility ceiling and the map honesty rule --------------------


def test_heat_index_plausibility_ceiling_flags_impossible() -> None:
    flagged = qc.apply([make_obs(parameter="heat_index_c", value=67.0)])
    assert flagged[0].qc == "range"  # ~153 °F is beyond the NWS ceiling — flag it


def test_aggregate_excludes_qc_rejected_from_the_map() -> None:
    config = NetworkConfig(
        grid_resolution_m=150.0,
        nodes=(NodeConfig(node_id="node-01", lat=38.58, lon=-121.49, location="precise"),),
    )
    rejected = make_obs(
        node_id="node-01", parameter="pm25_ugm3", unit="ug/m3", value=12.0, qc="range"
    )
    # A cell whose only reading is QC-rejected must not appear on the map — not even provisionally.
    assert aggregate.aggregate([rejected], config).cells == ()
