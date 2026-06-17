"""The store's idempotency, filtering, and raw/derived separation."""

from __future__ import annotations

from swelter.models import RAW
from swelter.store import SqliteStore

from .conftest import make_obs


def test_write_is_idempotent(store: SqliteStore) -> None:
    batch = [make_obs(), make_obs(parameter="humidity_pct", unit="%", value=50.0)]
    first = store.write(batch)
    assert (first.written, first.duplicates) == (2, 0)
    second = store.write(batch)  # replaying the same stream never double-counts
    assert (second.written, second.duplicates) == (0, 2)
    assert store.count() == 2


def test_read_filters(store: SqliteStore) -> None:
    store.write(
        [
            make_obs(parameter="temp_c"),
            make_obs(parameter="pm25_ugm3", unit="ug/m3", value=10.0),
            make_obs(node_id="node-02", parameter="temp_c"),
        ]
    )
    assert len(store.read(parameter="temp_c")) == 2
    assert len(store.read(node_id="node-01")) == 2
    assert store.read(node_id="missing") == []
    assert store.node_ids() == ["node-01", "node-02"]


def test_time_filter(store: SqliteStore) -> None:
    store.write(
        [
            make_obs(timestamp="2026-06-01T00:00:00Z"),
            make_obs(timestamp="2026-06-02T00:00:00Z"),
        ]
    )
    assert len(store.read(since="2026-06-01T12:00:00Z")) == 1
    assert len(store.read(until="2026-06-01T12:00:00Z")) == 1


def test_drop_calibrated_keeps_immutable_raw(store: SqliteStore) -> None:
    raw = make_obs()
    store.write([raw, raw.calibrated("temp_c.enclosure-offset.node-01", 24.0, 0.5)])
    assert store.count() == 2
    assert store.drop_calibrated() == 1
    remaining = store.read()
    assert len(remaining) == 1
    assert remaining[0].calibration == RAW
