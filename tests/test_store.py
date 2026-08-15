"""The store's idempotency, filtering, and raw/derived separation."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from swelter import integrity
from swelter.models import (
    RAW,
    SOURCE_NATIVE,
    SOURCE_OPENAQ,
    SOURCE_OPENMETEO,
    SOURCE_SENSOR_COMMUNITY,
)
from swelter.store import SqliteStore

from .conftest import make_obs


def test_write_is_idempotent(store: SqliteStore) -> None:
    batch = [make_obs(), make_obs(parameter="humidity_pct", unit="%", value=50.0)]
    first = store.write(batch)
    assert (first.written, first.duplicates) == (2, 0)
    second = store.write(batch)  # replaying the same stream never double-counts
    assert (second.written, second.duplicates) == (0, 2)
    assert store.count() == 2


def test_source_is_part_of_storage_identity(store: SqliteStore) -> None:
    native = make_obs(node_id="shared", source=SOURCE_NATIVE)
    upstream = make_obs(node_id="shared", source=SOURCE_OPENAQ)

    result = store.write([native, upstream])

    assert (result.written, result.duplicates) == (2, 0)
    assert store.count() == 2
    assert native.key() != upstream.key()


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


def test_open_migrates_legacy_source_markers_without_losing_provenance(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.db"
    connection = sqlite3.connect(db_path)
    connection.executescript(
        """
        CREATE TABLE observations (
            node_id TEXT NOT NULL, timestamp TEXT NOT NULL, parameter TEXT NOT NULL,
            value REAL NOT NULL, unit TEXT NOT NULL, calibration TEXT NOT NULL,
            qc TEXT NOT NULL, uncertainty REAL, content_hash TEXT NOT NULL,
            PRIMARY KEY (node_id, timestamp, parameter, calibration)
        );
        """
    )
    rows = (
        ("oaq-1", "2026-06-01T00:00:00Z", "pm25_ugm3", 10.0, "ug/m3", RAW, "ok", None, "old"),
        ("sc-2", "2026-06-01T00:00:00Z", "pm25_ugm3", 11.0, "ug/m3", RAW, "ok", None, "old"),
        (
            "sacramento",
            "2026-06-01T00:00:00Z",
            "pm25_ugm3",
            12.0,
            "ug/m3",
            "copernicus-cams",
            "ok",
            None,
            "old",
        ),
        (
            "sacramento",
            "2026-06-01T00:00:00Z",
            "pm25_ugm3",
            13.0,
            "ug/m3",
            RAW,
            "ok",
            None,
            "old",
        ),
        (
            "oaq-1evil",
            "2026-06-01T00:00:00Z",
            "pm25_ugm3",
            14.0,
            "ug/m3",
            RAW,
            "ok",
            None,
            "old",
        ),
    )
    connection.executemany("INSERT INTO observations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
    connection.commit()
    connection.close()
    digest_path = tmp_path / "digests.jsonl"
    digest_path.write_text('{"head":"stale"}\n', encoding="utf-8")

    with SqliteStore(db_path) as migrated:
        observations = migrated.read()
        assert (
            next(item for item in observations if item.node_id == "oaq-1").source == SOURCE_OPENAQ
        )
        assert (
            next(item for item in observations if item.node_id == "sc-2").source
            == SOURCE_SENSOR_COMMUNITY
        )
        assert (
            next(item for item in observations if item.node_id == "oaq-1evil").source
            == SOURCE_NATIVE
        )
        sacramento = [item for item in observations if item.node_id == "sacramento"]
        assert {(item.source, item.value) for item in sacramento} == {
            (SOURCE_OPENMETEO, 12.0),
            (SOURCE_NATIVE, 13.0),
        }
        cams = next(item for item in sacramento if item.source == SOURCE_OPENMETEO)
        assert cams.calibration == RAW
        assert all(stored_hash == item.content_hash() for item, stored_hash in migrated.iter_rows())
        digests = integrity.daily_digests(migrated)
        head = json.loads(digest_path.read_text(encoding="utf-8").splitlines()[-1])
        assert head == {
            "head": digests[-1].chain,
            "days": len(digests),
            "last_day": digests[-1].date,
        }


def test_open_rebuilds_source_column_store_with_old_primary_key(tmp_path: Path) -> None:
    db_path = tmp_path / "observations.db"
    connection = sqlite3.connect(db_path)
    connection.executescript(
        """
        CREATE TABLE observations (
            node_id TEXT NOT NULL, timestamp TEXT NOT NULL, parameter TEXT NOT NULL,
            value REAL NOT NULL, unit TEXT NOT NULL, source TEXT NOT NULL,
            calibration TEXT NOT NULL, qc TEXT NOT NULL, uncertainty REAL,
            content_hash TEXT NOT NULL,
            PRIMARY KEY (node_id, timestamp, parameter, calibration)
        );
        """
    )
    connection.execute(
        "INSERT INTO observations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "shared",
            "2026-06-01T00:00:00Z",
            "temp_c",
            25.0,
            "degC",
            SOURCE_NATIVE,
            RAW,
            "ok",
            None,
            "old",
        ),
    )
    connection.commit()
    connection.close()

    with SqliteStore(db_path) as migrated:
        result = migrated.write([make_obs(node_id="shared", source=SOURCE_OPENMETEO)])
        assert result.written == 1
        assert migrated.count() == 2

    connection = sqlite3.connect(db_path)
    primary_key = tuple(
        row[1]
        for row in sorted(
            (row for row in connection.execute("PRAGMA table_info(observations)") if row[5]),
            key=lambda row: row[5],
        )
    )
    connection.close()
    assert primary_key == ("node_id", "timestamp", "parameter", "source", "calibration")


def test_a_stored_calibrated_row_with_no_uncertainty_is_refused_not_read_as_zero(
    tmp_path: Path,
) -> None:
    # Issue #147. `calibrate.apply` never wrote a calibrated row without a 1-sigma, but the column
    # is nullable and round-trips faithfully, so an import path or a restored archive could hold
    # one. The old rollup read that absence as 0.0 — a perfect instrument — and published a
    # *narrower* error bar than the evidence supported. The store now refuses the row and says how
    # to re-derive it, instead of quietly handing the pipeline a value it cannot stand behind.
    db_path = tmp_path / "obs.db"
    with SqliteStore(db_path) as fresh:
        fresh.write([make_obs()])
    connection = sqlite3.connect(db_path)
    connection.execute(
        "INSERT INTO observations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "node-09",
            "2026-06-01T00:00:00Z",
            "temp_c",
            24.0,
            "degC",
            SOURCE_NATIVE,
            "temp_c.enclosure-offset.node-09",
            "ok",
            None,  # calibrated, but no 1-sigma
            "hash",
        ),
    )
    connection.commit()
    connection.close()

    with pytest.raises(ValueError) as caught, SqliteStore(db_path) as store:
        list(store.all())
    message = str(caught.value)
    assert "node-09" in message  # names the row, so it can be found
    assert "no uncertainty" in message
    assert "swelter rebuild" in message  # and says how to fix it
