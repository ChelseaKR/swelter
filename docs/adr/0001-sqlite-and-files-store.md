# ADR 0001: Store observations in a copyable SQLite-and-files folder, not a database cluster

- Status: Accepted
- Date: 2026-06-16
- Deciders: Chelsea Kelly-Reif
- Observation-identity posture superseded by: ADR 0024
- Dependency-count posture superseded by: ADR 0025

## Context

A hosting collective has to be able to run, back up, and leave with this on a
single board computer, with no operator on call. SQLite is in the Python
standard library (no runtime dependency beyond PyYAML), is a documented
single-file format, and is read directly by Datasette and most analysis tools,
so the archive is openable without this codebase. A copyable folder makes backup
and handover `cp -r`, and makes "leave with your data" the same act as "back up
your data". We rejected a Postgres or other server-backed database (an operator,
a daemon, a port, and a restore runbook the collective would own) and a
document/NoSQL store (no `INSERT OR IGNORE` idempotency, weaker tooling, and no
single file to hand off). Keeping the store behind a `Protocol` means choosing
SQLite now does not foreclose Parquet later.

## Decision

The default store is a folder a community can copy, back up, and walk away with.
`swelter.store.SqliteStore` writes a single `observations.db` SQLite file that
Datasette opens directly, beside three plain-text siblings produced by the rest
of the pipeline: `quarantine.jsonl` (payloads that failed validation),
`aggregate.geojson` (the published surface), and `corrections.yaml` (the
correction registry). `store.store_paths()` is the canonical layout. The raw
table is append-only and content-hashed; `write()` is `INSERT OR IGNORE` on the
key `(node_id, timestamp, parameter, calibration)`, so replaying a stream never
double-counts, and `drop_calibrated()` rebuilds every derived row from the raw
log. `Store` is a `Protocol` with five methods, so a Parquet/Arrow backend can
drop in without touching ingest, calibrate, aggregate, or the API.

## Consequences

SQLite is single-writer: concurrent ingest processes will serialise or contend
on the write lock, so this design assumes one writer (the pipeline) and many
readers. That is exactly why `swelter.server` is single-threaded and read-only,
and why `SqliteStore` opens with `check_same_thread=False` only under that
serialised access. The model does not scale to high-frequency, many-writer
ingestion or to a dataset larger than one host's disk; a network that outgrows a
single board computer would implement a Parquet/Arrow `Store` backend rather
than bolt clustering onto SQLite. Append-only means the raw table only grows;
compaction is out of scope and left to the operator copying or rotating the
folder.
