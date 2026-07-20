# ADR 0024: Preserve source-specific data terms through every release surface

- Status: Accepted
- Date: 2026-07-16
- Deciders: Chelsea Kelly-Reif

## Context

The live adapters fetch OpenAQ, Copernicus CAMS through Open-Meteo, and Sensor.Community data.
Those records retain provider or upstream terms that a repository-level CC0 dedication cannot
erase. ADR 0006 was valid only for project-authored synthetic data and first-party community
observations that the publishing collective has authority to dedicate.

## Decision

Keep Apache-2.0 for swelter source code. Apply CC0-1.0 only to project-authored synthetic data and
authorized first-party observations. Record a fetched store's source, license, license URL, and
attribution beside the store; propagate those terms through exports, snapshots, published sites,
data cards, and citations.

Make `source` part of the observation, SQLite primary key, content hash, API deduplication key, and
public observation id. A pre-contract store is upgraded transactionally: infer only strict known
legacy source markers, reject conflicts or row loss, then recompute the integrity chain before
commit. This source-qualified identity supersedes the four-field key recorded in ADR 0001.

OpenAQ publication is fail-closed: every exported `oaq-*` location must be covered by the retained
per-location `source-license-ledger.json`, including historical locations in an accumulating store.
Overrides may not replace fetched-source terms with a different license or attribution. Stores from
different sources may not be accumulated together.

## Consequences

Reusers receive accurate, source-bound rights evidence instead of a blanket dedication. Snapshot,
export, server, and static-publication paths must resolve the same store metadata and stop when the
required ledger is absent or incomplete. Operators must review provider changes and keep historical
ledger entries with historical observations. The extra provenance is deliberate release data, not
optional documentation.
