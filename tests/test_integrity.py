"""Archive integrity: row-hash re-verification and the chained daily digest (FIX-13).

Covers: a clean store round-trips with zero mismatches; a row mutated outside the append-only
write path is caught (both at the library level and through `swelter verify-archive`'s exit
code); `digests.jsonl` / the head chain are byte-for-byte reproducible across two runs on the
same fixture; and changing one day's data changes every chain value after it.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from swelter import integrity, qc
from swelter.cli import main
from swelter.store import SqliteStore, open_store, store_paths

from .conftest import make_obs


def _seed(store: SqliteStore) -> None:
    store.write(
        [
            make_obs(node_id="node-01", timestamp="2026-06-01T00:00:00Z", value=25.0),
            make_obs(node_id="node-01", timestamp="2026-06-01T01:00:00Z", value=26.0),
            make_obs(node_id="node-02", timestamp="2026-06-02T00:00:00Z", value=27.0),
        ]
    )


# -- verify_rows ---------------------------------------------------------------


def test_verify_rows_clean_store_has_no_mismatches(store: SqliteStore) -> None:
    _seed(store)
    assert integrity.verify_rows(store) == []


def test_verify_rows_detects_a_row_mutated_outside_the_write_path(store: SqliteStore) -> None:
    _seed(store)
    # Mutate a stored value directly via sqlite, bypassing `write()` entirely — the persisted
    # content_hash is now stale for that row, which is exactly what verify_rows must catch.
    conn = sqlite3.connect(str(store.path))
    conn.execute(
        "UPDATE observations SET value = 999.0 WHERE node_id = 'node-01' "
        "AND timestamp = '2026-06-01T00:00:00Z'"
    )
    conn.commit()
    conn.close()

    mismatches = integrity.verify_rows(store)
    assert len(mismatches) == 1
    m = mismatches[0]
    assert (m.node_id, m.timestamp, m.parameter) == ("node-01", "2026-06-01T00:00:00Z", "temp_c")
    assert m.expected != m.actual


# -- daily_digests / chaining ---------------------------------------------------


def test_daily_digests_group_by_utc_day(store: SqliteStore) -> None:
    _seed(store)
    digests = integrity.daily_digests(store)
    assert [d.date for d in digests] == ["2026-06-01", "2026-06-02"]
    assert [d.row_count for d in digests] == [2, 1]
    assert sum(d.row_count for d in digests) == 3


def test_chain_changes_when_an_earlier_days_data_changes(tmp_path: Path) -> None:
    db_a = SqliteStore(tmp_path / "a.db")
    db_a.write(
        [
            make_obs(timestamp="2026-06-01T00:00:00Z", value=25.0),
            make_obs(timestamp="2026-06-02T00:00:00Z", value=27.0),
        ]
    )
    head_a = integrity.daily_digests(db_a)[-1].chain
    db_a.close()

    db_b = SqliteStore(tmp_path / "b.db")
    db_b.write(
        [
            make_obs(timestamp="2026-06-01T00:00:00Z", value=25.1),  # earlier day differs
            make_obs(timestamp="2026-06-02T00:00:00Z", value=27.0),
        ]
    )
    head_b = integrity.daily_digests(db_b)[-1].chain
    db_b.close()

    assert head_a != head_b


def test_empty_store_has_no_digests(store: SqliteStore) -> None:
    assert integrity.daily_digests(store) == []


# -- write_digests / read_head --------------------------------------------------


def test_write_digests_is_byte_for_byte_reproducible(tmp_path: Path) -> None:
    store_dir = tmp_path / "store"
    seed_db = SqliteStore(store_paths(store_dir)["db"])
    _seed(seed_db)
    seed_db.close()

    with open_store(store_dir) as db1:
        path1 = integrity.write_digests(store_dir, integrity.daily_digests(db1))
    first_bytes = path1.read_bytes()

    with open_store(store_dir) as db2:
        path2 = integrity.write_digests(store_dir, integrity.daily_digests(db2))
    second_bytes = path2.read_bytes()

    assert first_bytes == second_bytes
    assert first_bytes.endswith(b"\n")
    assert b"\r" not in first_bytes  # LF only


def test_write_digests_layout(tmp_path: Path) -> None:
    store_dir = tmp_path / "store"
    seed_db = SqliteStore(store_paths(store_dir)["db"])
    _seed(seed_db)
    seed_db.close()

    with open_store(store_dir) as db:
        digests = integrity.daily_digests(db)
        path = integrity.write_digests(store_dir, digests)

    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == len(digests) + 1  # one line per day, plus the head record
    day_records = [json.loads(line) for line in lines[:-1]]
    assert [r["date"] for r in day_records] == [d.date for d in digests]
    head_record = json.loads(lines[-1])
    assert head_record["head"] == digests[-1].chain
    assert head_record["last_day"] == digests[-1].date
    assert head_record["days"] == len(digests)


def test_read_head_round_trips(tmp_path: Path) -> None:
    store_dir = tmp_path / "store"
    seed_db = SqliteStore(store_paths(store_dir)["db"])
    _seed(seed_db)
    seed_db.close()

    with open_store(store_dir) as db:
        digests = integrity.daily_digests(db)
    integrity.write_digests(store_dir, digests)

    head = integrity.read_head(store_dir)
    assert head is not None
    assert head["head"] == digests[-1].chain
    assert head["last_day"] == digests[-1].date
    assert head["days"] == len(digests)


def test_read_head_is_none_when_no_digests_file(tmp_path: Path) -> None:
    assert integrity.read_head(tmp_path / "nowhere") is None


def test_read_head_is_none_on_malformed_file(tmp_path: Path) -> None:
    store_dir = tmp_path / "store"
    paths = store_paths(store_dir)
    paths["dir"].mkdir(parents=True)
    paths["digests"].write_text("not json\n", encoding="utf-8")
    assert integrity.read_head(store_dir) is None


def test_read_head_is_none_on_blank_file(tmp_path: Path) -> None:
    store_dir = tmp_path / "store"
    paths = store_paths(store_dir)
    paths["dir"].mkdir(parents=True)
    paths["digests"].write_text("\n\n", encoding="utf-8")
    assert integrity.read_head(store_dir) is None


# -- CLI: swelter verify-archive -------------------------------------------------


def test_cli_verify_archive_round_trip(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    store_dir = tmp_path / "store"
    seed_db = SqliteStore(store_paths(store_dir)["db"])
    _seed(seed_db)
    seed_db.close()

    rc = main(["verify-archive", "--store", str(store_dir), "--write"])
    assert rc == 0
    err = capsys.readouterr().err
    assert "OK" in err
    assert (store_dir / "digests.jsonl").is_file()


def test_cli_verify_archive_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    store_dir = tmp_path / "store"
    seed_db = SqliteStore(store_paths(store_dir)["db"])
    _seed(seed_db)
    seed_db.close()

    rc = main(["verify-archive", "--store", str(store_dir), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["mismatches"] == []
    assert payload["rows_checked"] == 3
    assert payload["head"]


def test_cli_verify_archive_detects_tamper_and_exits_nonzero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store_dir = tmp_path / "store"
    db_path = store_paths(store_dir)["db"]
    seed_db = SqliteStore(db_path)
    _seed(seed_db)
    seed_db.close()

    conn = sqlite3.connect(str(db_path))
    conn.execute("UPDATE observations SET value = 999.0 WHERE node_id = 'node-01'")
    conn.commit()
    conn.close()

    rc = main(["verify-archive", "--store", str(store_dir), "--write"])
    assert rc == 1
    err = capsys.readouterr().err
    assert "FAILED" in err
    assert "MISMATCH" in err
    # A known-corrupted archive must not get a fresh, misleadingly clean digest published over it.
    assert not (store_dir / "digests.jsonl").is_file()


def test_cli_verify_archive_empty_store(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    store_dir = tmp_path / "store"
    SqliteStore(store_paths(store_dir)["db"]).close()  # create an empty store
    rc = main(["verify-archive", "--store", str(store_dir), "--write"])
    assert rc == 0
    err = capsys.readouterr().err
    assert "OK" in err
    assert "0 row(s)" in err


# -- qc.health_report integrity block --------------------------------------------


def test_health_report_integrity_unavailable_before_verify(tmp_path: Path) -> None:
    store_dir = tmp_path / "store"
    seed_db = SqliteStore(store_paths(store_dir)["db"])
    _seed(seed_db)
    obs = list(seed_db.all())
    seed_db.close()

    report = qc.health_report(obs, store_dir=store_dir)
    assert report["integrity"] == {"available": False}


def test_health_report_integrity_reads_published_digests(tmp_path: Path) -> None:
    store_dir = tmp_path / "store"
    seed_db = SqliteStore(store_paths(store_dir)["db"])
    _seed(seed_db)
    obs = list(seed_db.all())
    seed_db.close()

    with open_store(store_dir) as db:
        digests = integrity.daily_digests(db)
        integrity.write_digests(store_dir, digests)

    report = qc.health_report(obs, store_dir=store_dir)
    block = report["integrity"]
    assert isinstance(block, dict)
    assert block["available"] is True
    assert block["head"] == digests[-1].chain
    assert block["last_verified_day"] == digests[-1].date


def test_health_report_without_store_dir_has_no_integrity_key(store: SqliteStore) -> None:
    _seed(store)
    report = qc.health_report(list(store.all()))
    assert "integrity" not in report
