"""EXP-02: reference-monitor co-location pairing (pure/offline) and the AirNow reference mapping.

Everything here is deterministic and offline. The live AirNow fetch is deliberately not exercised —
its tested contract is the pure ``airnow.parse_series`` mapping — so these tests never touch the
network. The pairing/resampling rule and its timestamp-tolerance edges are the core coverage.
"""

from __future__ import annotations

import json
from pathlib import Path

from swelter import calibrate, colocate
from swelter.calibrate import TrainingPair
from swelter.colocate import Sample
from swelter.models import RAW, SOURCE_NATIVE, Observation
from swelter.sources import airnow
from swelter.store import SqliteStore, store_paths

FIXTURES = Path(__file__).resolve().parent / "fixtures"
MONITOR = "060670010"


def _airnow_readings() -> list[airnow.ReferenceReading]:
    payload = json.loads((FIXTURES / "airnow_pm25_sample.json").read_text(encoding="utf-8"))
    return airnow.parse_series(payload)


def _node_samples() -> list[Sample]:
    samples: list[Sample] = []
    for line in (FIXTURES / "node_pm25_sample.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            samples.append(Sample(row["timestamp"], float(row["raw"])))
    return samples


# -- AirNow reference mapping (pure) -----------------------------------------


def test_airnow_parse_series_keeps_pm25_and_carries_the_aqs_site_id() -> None:
    readings = _airnow_readings()
    # Only the two PM2.5 rows survive: the OZONE row and the -999 missing sentinel are dropped.
    assert [(r.timestamp, r.value) for r in readings] == [
        ("2026-06-01T00:00:00Z", 14.0),
        ("2026-06-01T01:00:00Z", 18.0),
    ]
    assert {r.monitor_id for r in readings} == {MONITOR}
    assert {r.parameter for r in readings} == {"pm25_ugm3"}
    assert {r.unit for r in readings} == {"ug/m3"}


def test_airnow_parse_series_normalizes_hour_only_utc_stamps() -> None:
    readings = airnow.parse_series(
        [
            {
                "Parameter": "PM2.5",
                "Unit": "UG/M3",
                "Value": 9.5,
                "UTC": "2026-06-01T13",
                "FullAQSCode": MONITOR,
            }
        ]
    )
    assert readings[0].timestamp == "2026-06-01T13:00:00Z"


def test_airnow_parse_series_skips_incomplete_or_sentinel_rows() -> None:
    readings = airnow.parse_series(
        [
            {"Parameter": "PM2.5", "Unit": "UG/M3", "Value": 10.0, "UTC": "2026-06-01T00"},  # no id
            {"Parameter": "PM2.5", "Unit": "UG/M3", "UTC": "2026-06-01T00", "FullAQSCode": MONITOR},
            {"Parameter": "PM2.5", "Value": -999.0, "UTC": "2026-06-01T00", "FullAQSCode": MONITOR},
            "not-a-row",
        ]
    )
    assert readings == []


# -- pairing / resampling (pure) ---------------------------------------------


def test_pair_reference_matches_nearest_within_tolerance() -> None:
    pairs = colocate.pair_reference(
        "node-01",
        "pm25_ugm3",
        _node_samples(),
        colocate.reference_samples(_airnow_readings()),
        monitor=MONITOR,
    )
    # One pair per hourly reference reading, each to the on-the-hour node sample.
    assert [(p.timestamp, p.raw, p.reference) for p in pairs] == [
        ("2026-06-01T00:00:00Z", 22.0, 14.0),
        ("2026-06-01T01:00:00Z", 30.0, 18.0),
    ]
    assert {p.monitor for p in pairs} == {MONITOR}


def test_pair_reference_picks_the_closest_of_several_node_samples() -> None:
    node = [Sample("2026-06-01T00:00:00Z", 20.0), Sample("2026-06-01T00:05:00Z", 21.0)]
    reference = [Sample("2026-06-01T00:02:00Z", 15.0)]  # 120 s from :00, 180 s from :05
    pairs = colocate.pair_reference("node-01", "pm25_ugm3", node, reference)
    assert len(pairs) == 1
    assert pairs[0].timestamp == "2026-06-01T00:00:00Z"
    assert pairs[0].raw == 20.0


def test_pair_reference_ties_resolve_to_the_earlier_node_sample() -> None:
    node = [Sample("2026-06-01T00:00:00Z", 20.0), Sample("2026-06-01T00:10:00Z", 40.0)]
    reference = [Sample("2026-06-01T00:05:00Z", 15.0)]  # equidistant (300 s) from both
    pairs = colocate.pair_reference("node-01", "pm25_ugm3", node, reference)
    assert pairs[0].timestamp == "2026-06-01T00:00:00Z"
    assert pairs[0].raw == 20.0


def test_pair_reference_drops_a_reference_with_no_node_sample_in_window() -> None:
    node = [Sample("2026-06-01T00:00:00Z", 20.0)]
    reference = [
        Sample("2026-06-01T00:20:00Z", 15.0),  # 1200 s away — inside the default 1800 s tolerance
        Sample("2026-06-01T02:00:00Z", 16.0),  # 7200 s away — outside, so no pair
    ]
    pairs = colocate.pair_reference("node-01", "pm25_ugm3", node, reference)
    assert [p.reference for p in pairs] == [15.0]


def test_pair_reference_respects_a_tighter_tolerance() -> None:
    node = [Sample("2026-06-01T00:00:00Z", 20.0)]
    reference = [Sample("2026-06-01T00:20:00Z", 15.0)]  # 1200 s away
    assert colocate.pair_reference("node-01", "pm25_ugm3", node, reference, tolerance_s=600.0) == []


def test_pair_reference_attaches_humidity_by_node_timestamp() -> None:
    node = [Sample("2026-06-01T00:00:00Z", 22.0), Sample("2026-06-01T01:00:00Z", 30.0)]
    reference = [Sample("2026-06-01T00:00:00Z", 14.0), Sample("2026-06-01T01:00:00Z", 18.0)]
    humidity = {"2026-06-01T00:00:00Z": 61.0}  # only the first node instant has humidity
    pairs = colocate.pair_reference(
        "node-01", "pm25_ugm3", node, reference, humidity=humidity, monitor=MONITOR
    )
    assert pairs[0].humidity == 61.0
    assert pairs[1].humidity is None


# -- round-trip and provenance flow into the fit -----------------------------


def test_training_pair_row_round_trips_through_read_colocation(tmp_path: Path) -> None:
    pairs = colocate.pair_reference(
        "node-01",
        "pm25_ugm3",
        _node_samples(),
        colocate.reference_samples(_airnow_readings()),
        humidity={"2026-06-01T00:00:00Z": 61.0},
        monitor=MONITOR,
    )
    path = tmp_path / "colocation.jsonl"
    path.write_text(
        "\n".join(json.dumps(colocate.training_pair_to_row(p)) for p in pairs) + "\n",
        encoding="utf-8",
    )
    loaded = calibrate.read_colocation(path)
    assert [p.monitor for p in loaded] == [MONITOR, MONITOR]
    assert loaded[0].humidity == 61.0
    assert loaded[1].humidity is None  # omitted key round-trips back to None, not 0.0


def test_fit_uses_monitor_aqs_id_as_correction_reference() -> None:
    pairs = [
        TrainingPair(
            "node-01", "temp_c", f"2026-06-01T0{i}:00:00Z", 20.0 + i, 21.0 + i, monitor=MONITOR
        )
        for i in range(4)
    ]
    registry = calibrate.fit(pairs)
    correction = registry.get("node-01", "temp_c")
    assert correction is not None
    assert correction.reference == MONITOR


def test_fit_without_a_monitor_keeps_the_generic_reference_label() -> None:
    pairs = [
        TrainingPair("node-01", "temp_c", f"2026-06-01T0{i}:00:00Z", 20.0 + i, 21.0 + i)
        for i in range(4)
    ]
    correction = calibrate.fit(pairs).get("node-01", "temp_c")
    assert correction is not None
    assert correction.reference == "reference-monitor"


# -- CLI end to end, offline against the committed fixtures -------------------


def test_colocate_cli_emits_training_pairs_from_fixture(tmp_path: Path) -> None:
    from swelter.cli import main

    store_dir = tmp_path / "store"
    store_dir.mkdir()
    with SqliteStore(store_paths(store_dir)["db"]) as store:
        store.write(
            Observation(
                "node-01",
                s.timestamp,
                "pm25_ugm3",
                s.value,
                "ug/m3",
                source=SOURCE_NATIVE,
                calibration=RAW,
            )
            for s in _node_samples()
        )
    out = tmp_path / "pairs.jsonl"
    code = main(
        [
            "colocate",
            "--node",
            "node-01",
            "--monitor",
            MONITOR,
            "--window",
            "2026-06-01T00:00:00Z..2026-06-01T02:00:00Z",
            "--reference-fixture",
            str(FIXTURES / "airnow_pm25_sample.json"),
            "--store",
            str(store_dir),
            "--out",
            str(out),
        ]
    )
    assert code == 0
    rows = [
        json.loads(line) for line in out.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    assert [(r["raw"], r["reference"], r["monitor"]) for r in rows] == [
        (22.0, 14.0, MONITOR),
        (30.0, 18.0, MONITOR),
    ]
