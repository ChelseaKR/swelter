"""Intake validates, quarantines the unusable, and never double-counts."""

from __future__ import annotations

from pathlib import Path

from swelter import ingest
from swelter.store import SqliteStore

_GOOD = {
    "node_id": "node-01",
    "timestamp": "2026-06-01T00:00:00Z",
    "temp_c": 25.0,
    "pm25_ugm3": 10.0,
    "mystery_field": "ignored",
}


def test_explode_keeps_known_params_and_drops_unknown() -> None:
    obs, reason = ingest.explode(_GOOD)
    assert reason is None
    assert {o.parameter for o in obs} == {"temp_c", "pm25_ugm3"}
    assert all(o.calibration == "raw" for o in obs)


def test_explode_rejects_missing_node() -> None:
    _, reason = ingest.explode({"timestamp": "2026-06-01T00:00:00Z", "temp_c": 25.0})
    assert reason is not None


def test_explode_rejects_unparseable_timestamp() -> None:
    _, reason = ingest.explode({"node_id": "n", "timestamp": "yesterday", "temp_c": 25.0})
    assert reason is not None


def test_explode_rejects_empty_reading() -> None:
    _, reason = ingest.explode({"node_id": "n", "timestamp": "2026-06-01T00:00:00Z"})
    assert reason == "no recognised parameters"


def test_ingest_quarantines_bad_payloads(store: SqliteStore, tmp_path: Path) -> None:
    quarantine = tmp_path / "q.jsonl"
    result = ingest.ingest(
        [_GOOD, {"timestamp": "2026-06-01T00:00:00Z", "temp_c": 25.0}],
        store,
        quarantine_path=quarantine,
    )
    assert result.accepted_payloads == 1
    assert result.quarantined == 1
    assert quarantine.exists()


def test_ingest_is_idempotent(store: SqliteStore) -> None:
    first = ingest.ingest([_GOOD], store)
    second = ingest.ingest([_GOOD], store)
    assert first.observations_written == 2
    assert second.observations_written == 0


def test_ingest_runs_qc(store: SqliteStore) -> None:
    ingest.ingest(
        [{"node_id": "node-01", "timestamp": "2026-06-01T00:00:00Z", "temp_c": 80.0}], store
    )
    stored = store.read(parameter="temp_c")
    assert stored[0].qc == "range"
