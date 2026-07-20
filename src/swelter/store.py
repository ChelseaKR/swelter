"""Time-series store: an append-only, content-hashed, Datasette-openable observation log.

The store is deliberately a *folder you can copy*. The default backend is a single SQLite
database — ``observations.db`` — that Datasette opens directly, beside a ``quarantine.jsonl``
of payloads that failed validation. There is no cluster and no proprietary database, because
a community group has to be able to run, back up, and walk away with this on a single board
computer.

Two properties the rest of the system leans on:

* **Idempotent.** ``write`` is ``INSERT OR IGNORE`` on the observation key, so replaying the
  same stream — a node backfilling after an outage, a re-run of ``make demo`` — never
  double-counts. Re-ingesting is always safe.
* **Append-only.** Raw observations are written once and carry a ``content_hash``. An edit is
  a new record, never an overwrite, so the raw log is immutable evidence and every derived
  surface (calibrated values, aggregates) can be rebuilt from it.

The :class:`Store` protocol is the seam: a Parquet/Arrow backend can implement the same five
methods and drop in without touching ingest, calibrate, aggregate, or the API.
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .models import (
    RAW,
    SOURCE_NATIVE,
    SOURCE_OPENAQ,
    SOURCE_OPENMETEO,
    SOURCE_SENSOR_COMMUNITY,
    Observation,
    format_timestamp,
    parse_timestamp,
)


@dataclass(frozen=True)
class WriteResult:
    """Outcome of a write: how many rows were new versus already present."""

    written: int
    duplicates: int

    @property
    def total(self) -> int:
        return self.written + self.duplicates


class Store(Protocol):
    """The storage seam. Any backend implementing this is a drop-in replacement."""

    def write(self, observations: Iterable[Observation]) -> WriteResult: ...

    def read(
        self,
        *,
        parameter: str | None = None,
        node_id: str | None = None,
        calibration: str | None = None,
        since: str | None = None,
        until: str | None = None,
    ) -> list[Observation]: ...

    def all(self) -> Iterator[Observation]: ...

    def node_ids(self) -> list[str]: ...

    def count(self) -> int: ...

    def close(self) -> None: ...


_TABLE_COLUMNS = """
    node_id      TEXT    NOT NULL,
    timestamp    TEXT    NOT NULL,
    parameter    TEXT    NOT NULL,
    value        REAL    NOT NULL,
    unit         TEXT    NOT NULL,
    source       TEXT    NOT NULL DEFAULT 'native',
    calibration  TEXT    NOT NULL,
    qc           TEXT    NOT NULL,
    uncertainty  REAL,
    content_hash TEXT    NOT NULL,
    PRIMARY KEY (node_id, timestamp, parameter, source, calibration)
"""

_CREATE_TABLE = f"CREATE TABLE observations ({_TABLE_COLUMNS})"
_CREATE_TABLE_IF_MISSING = f"CREATE TABLE IF NOT EXISTS observations ({_TABLE_COLUMNS})"
_CREATE_INDEXES = (
    "CREATE INDEX IF NOT EXISTS ix_obs_param ON observations (parameter, timestamp)",
    "CREATE INDEX IF NOT EXISTS ix_obs_node ON observations (node_id, timestamp)",
)
_EXPECTED_PRIMARY_KEY = ("node_id", "timestamp", "parameter", "source", "calibration")
_LEGACY_TABLE = "observations_before_source_identity"
_RENAME_LEGACY_TABLE = "ALTER TABLE observations RENAME TO observations_before_source_identity"
_DROP_LEGACY_TABLE = "DROP TABLE observations_before_source_identity"
_LEGACY_OPENAQ_NODE = re.compile(r"oaq-\d+\Z")
_LEGACY_SENSOR_COMMUNITY_NODE = re.compile(r"sc-\d+\Z")

_COLUMNS = (
    "node_id, timestamp, parameter, value, unit, source, calibration, qc, uncertainty, content_hash"
)


class SqliteStore:
    """SQLite-backed :class:`Store`. The file it writes is the whole archive."""

    def __init__(self, db_path: str | Path) -> None:
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False so the read-only server can answer from its own thread;
        # the server is single-threaded (see swelter.server) so access stays serialised.
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        try:
            self._conn.execute(_CREATE_TABLE_IF_MISSING)
            for statement in _CREATE_INDEXES:
                self._conn.execute(statement)
            self._conn.commit()
            if self._source_identity_migration_required():
                self._migrate_source_identity_with_integrity_chain()
        except Exception:
            self._conn.rollback()
            self._conn.close()
            raise

    def _table_info(self) -> list[sqlite3.Row]:
        return self._conn.execute("PRAGMA table_info(observations)").fetchall()

    def _source_identity_migration_required(self) -> bool:
        info = self._table_info()
        columns = {str(row["name"]) for row in info}
        primary_key = tuple(
            name
            for _position, name in sorted(
                (int(row["pk"]), str(row["name"])) for row in info if int(row["pk"])
            )
        )
        return "source" not in columns or primary_key != _EXPECTED_PRIMARY_KEY

    def _migrate_source_identity_with_integrity_chain(self) -> None:
        """Migrate rows and any published digest chain as one recoverable operation."""
        digest_path = self.path.parent / "digests.jsonl"
        digest_existed = digest_path.is_file()
        digest_before = digest_path.read_bytes() if digest_existed else None
        digest_touched = False
        try:
            self._conn.execute("BEGIN IMMEDIATE")
            migrated = self._migrate_source_identity()
            if migrated and digest_existed:
                # Local import avoids a module cycle: integrity imports SqliteStore for typing and
                # traversal, while migration needs its canonical digest serialization at runtime.
                from . import integrity

                digest_touched = True
                integrity.write_digests(self.path.parent, integrity.daily_digests(self))
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            if digest_touched and digest_before is not None:
                digest_path.write_bytes(digest_before)
            raise

    def _migrate_source_identity(self) -> bool:
        """Rebuild old tables without lossy updates or ambiguous prefix matching.

        Pre-source stores overloaded node ids and the ``copernicus-cams`` calibration marker with
        provenance. Rebuilding lets CAMS become a raw Open-Meteo row while a native raw row with
        the same node/time/parameter remains distinct under the source-inclusive primary key.
        """
        info = self._table_info()
        columns = {str(row["name"]) for row in info}
        primary_key = tuple(
            name
            for _position, name in sorted(
                (int(row["pk"]), str(row["name"])) for row in info if int(row["pk"])
            )
        )
        if "source" in columns and primary_key == _EXPECTED_PRIMARY_KEY:
            return False

        has_source = "source" in columns
        select_legacy_rows = (
            "SELECT node_id, timestamp, parameter, value, unit, source, calibration, qc, "
            "uncertainty FROM observations"
            if has_source
            else "SELECT node_id, timestamp, parameter, value, unit, calibration, qc, "
            "uncertainty FROM observations"
        )
        rows = self._conn.execute(select_legacy_rows).fetchall()
        migrated: list[Observation] = []
        for row in rows:
            node_id = str(row["node_id"])
            calibration = str(row["calibration"])
            source = str(row["source"]) if has_source else SOURCE_NATIVE
            if calibration == "copernicus-cams":
                if not has_source or source in (SOURCE_NATIVE, SOURCE_OPENMETEO):
                    source = SOURCE_OPENMETEO
                    calibration = RAW
                else:
                    raise ValueError(
                        "legacy CAMS calibration conflicts with explicit observation source"
                    )
            elif not has_source and _LEGACY_OPENAQ_NODE.fullmatch(node_id):
                source = SOURCE_OPENAQ
            elif not has_source and _LEGACY_SENSOR_COMMUNITY_NODE.fullmatch(node_id):
                source = SOURCE_SENSOR_COMMUNITY
            uncertainty = row["uncertainty"]
            migrated.append(
                Observation(
                    node_id=node_id,
                    timestamp=str(row["timestamp"]),
                    parameter=str(row["parameter"]),
                    value=float(row["value"]),
                    unit=str(row["unit"]),
                    source=source,
                    calibration=calibration,
                    qc=str(row["qc"]),
                    uncertainty=None if uncertainty is None else float(uncertainty),
                )
            )

        existing_legacy = self._conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (_LEGACY_TABLE,)
        ).fetchone()
        if existing_legacy is not None:
            raise sqlite3.OperationalError(f"stale migration table exists: {_LEGACY_TABLE}")
        self._conn.execute(_RENAME_LEGACY_TABLE)
        self._conn.execute(_CREATE_TABLE)
        self._conn.executemany(
            "INSERT INTO observations "
            "(node_id, timestamp, parameter, value, unit, source, calibration, qc, uncertainty, "
            "content_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    observation.node_id,
                    observation.timestamp,
                    observation.parameter,
                    observation.value,
                    observation.unit,
                    observation.source,
                    observation.calibration,
                    observation.qc,
                    observation.uncertainty,
                    observation.content_hash(),
                )
                for observation in migrated
            ],
        )
        inserted = int(self._conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0])
        if inserted != len(rows):
            raise sqlite3.IntegrityError(
                f"source identity migration retained {inserted} of {len(rows)} rows"
            )
        self._conn.execute(_DROP_LEGACY_TABLE)
        for statement in _CREATE_INDEXES:
            self._conn.execute(statement)
        return True

    def write(self, observations: Iterable[Observation]) -> WriteResult:
        rows = [
            (
                o.node_id,
                o.timestamp,
                o.parameter,
                o.value,
                o.unit,
                o.source,
                o.calibration,
                o.qc,
                o.uncertainty,
                o.content_hash(),
            )
            for o in observations
        ]
        if not rows:
            return WriteResult(0, 0)
        before = self._total_changes()
        # `_COLUMNS` is a fixed module-level constant, not user input; row values are bound via `?`.
        self._conn.executemany(
            "INSERT OR IGNORE INTO observations "
            "(node_id, timestamp, parameter, value, unit, source, calibration, qc, uncertainty, "
            "content_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        self._conn.commit()
        written = self._total_changes() - before
        return WriteResult(written=written, duplicates=len(rows) - written)

    def read(
        self,
        *,
        parameter: str | None = None,
        node_id: str | None = None,
        calibration: str | None = None,
        since: str | None = None,
        until: str | None = None,
    ) -> list[Observation]:
        clauses: list[str] = []
        params: list[str] = []
        if parameter is not None:
            clauses.append("parameter = ?")
            params.append(parameter)
        if node_id is not None:
            clauses.append("node_id = ?")
            params.append(node_id)
        if calibration is not None:
            clauses.append("calibration = ?")
            params.append(calibration)
        # Compare instants, not raw strings: the stored column is canonical ...Z, so a valid
        # but non-canonical bound (an offset, fractional seconds) must be normalised first or
        # SQLite's lexical TEXT comparison would silently drop or include the wrong rows.
        if since is not None:
            clauses.append("timestamp >= ?")
            params.append(format_timestamp(parse_timestamp(since)))
        if until is not None:
            clauses.append("timestamp <= ?")
            params.append(format_timestamp(parse_timestamp(until)))
        # `clauses` are fixed column-name strings from the enumerated kwargs above (never user
        # text); every value is bound via `?` in `params`. `_COLUMNS` is a fixed constant too.
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"SELECT {_COLUMNS} FROM observations{where} ORDER BY node_id, parameter, timestamp"  # noqa: S608 (#107)
        # This is stdlib sqlite3 (no SQLAlchemy in this project at all); `sql` is built from fixed
        # column/clause strings above, never user text, and every value is bound via `?`.
        # nosemgrep: sqlalchemy-execute-raw-query (#107)
        cur = self._conn.execute(sql, params)
        return [_row_to_obs(row) for row in cur.fetchall()]

    def all(self) -> Iterator[Observation]:
        # This is a fixed, parameter-free sqlite3 query (not SQLAlchemy or caller-provided SQL).
        # nosemgrep: sqlalchemy-execute-raw-query (#107)
        cur = self._conn.execute(
            "SELECT node_id, timestamp, parameter, value, unit, source, calibration, qc, "
            "uncertainty, content_hash FROM observations ORDER BY node_id, parameter, timestamp"
        )
        for row in cur:
            yield _row_to_obs(row)

    def iter_rows(self) -> Iterator[tuple[Observation, str]]:
        """Every stored row as ``(reconstructed Observation, stored content_hash)``.

        For integrity verification (:mod:`swelter.integrity`): unlike :meth:`all`, the persisted
        hash rides along instead of being dropped, so a caller can recompute
        ``obs.content_hash()`` and compare without a second query. Ordered by UTC day first (the
        timestamp column is canonical ``YYYY-MM-DDTHH:MM:SSZ``, so a lexical prefix sort is a
        correct day sort with no parsing), then by the same node_id/parameter/timestamp order as
        :meth:`all` — deterministic, and lets a caller fold hashes into daily digests in one pass
        without buffering the whole store.
        """
        # This is a fixed, parameter-free sqlite3 query (not SQLAlchemy or caller-provided SQL).
        # nosemgrep: sqlalchemy-execute-raw-query (#107)
        cur = self._conn.execute(
            "SELECT node_id, timestamp, parameter, value, unit, source, calibration, qc, "
            "uncertainty, content_hash FROM observations ORDER BY substr(timestamp, 1, 10), "
            "node_id, parameter, timestamp"
        )
        for row in cur:
            yield _row_to_obs(row), str(row["content_hash"])

    def latest_raw(self) -> list[Observation]:
        """Every immutable raw observation — the source the rest is rebuilt from."""
        return self.read(calibration=RAW)

    def node_ids(self) -> list[str]:
        cur = self._conn.execute("SELECT DISTINCT node_id FROM observations ORDER BY node_id")
        return [str(row["node_id"]) for row in cur.fetchall()]

    def count(self) -> int:
        cur = self._conn.execute("SELECT COUNT(*) AS n FROM observations")
        return int(cur.fetchone()["n"])

    def data_version(self) -> int:
        """SQLite's cross-connection change counter for this database file.

        Unlike ``connection_change_count()`` (this connection's own write count, silent about
        writes made by any other connection), ``PRAGMA data_version`` bumps whenever another
        connection commits a change to the file — including a same-row-count rewrite. It does
        not bump for writes made by this connection, so cache fingerprints need both counters.
        """
        return int(self._conn.execute("PRAGMA data_version").fetchone()[0])

    def connection_change_count(self) -> int:
        """Number of rows changed by statements run through this connection.

        SQLite's ``total_changes`` catches same-connection rewrites that leave ``count()``
        unchanged. It complements, rather than replaces, ``data_version()`` because it cannot
        see writes committed through another connection.
        """
        return int(self._conn.total_changes)

    def drop_calibrated(self) -> int:
        """Remove all derived (non-raw) rows, leaving the immutable raw log. For rebuild."""
        before = self._total_changes()
        self._conn.execute("DELETE FROM observations WHERE calibration != ?", (RAW,))
        self._conn.commit()
        return self._total_changes() - before

    def close(self) -> None:
        self._conn.close()

    def _total_changes(self) -> int:
        return self.connection_change_count()

    def __enter__(self) -> SqliteStore:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def _row_to_obs(row: sqlite3.Row) -> Observation:
    uncertainty = row["uncertainty"]
    return Observation(
        node_id=str(row["node_id"]),
        timestamp=str(row["timestamp"]),
        parameter=str(row["parameter"]),
        value=float(row["value"]),
        unit=str(row["unit"]),
        source=str(row["source"]),
        calibration=str(row["calibration"]),
        qc=str(row["qc"]),
        uncertainty=None if uncertainty is None else float(uncertainty),
    )


def store_paths(store_dir: str | Path) -> dict[str, Path]:
    """Canonical file layout inside a store directory."""
    base = Path(store_dir)
    return {
        "dir": base,
        "db": base / "observations.db",
        "quarantine": base / "quarantine.jsonl",
        "aggregate": base / "aggregate.geojson",
        "registry": base / "corrections.yaml",
        "digests": base / "digests.jsonl",
    }


def open_store(store_dir: str | Path) -> SqliteStore:
    """Open (creating if needed) the default SQLite store under ``store_dir``."""
    return SqliteStore(store_paths(store_dir)["db"])
