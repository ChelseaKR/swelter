# ADR 0006: License the code Apache-2.0 and the observations CC0-1.0

> **Legacy historical text.** The authoritative record is
> [`docs/adr/0006`](../adr/0006-apache-code-cc0-data.md), superseded by
> [`docs/adr/0024`](../adr/0024-preserve-source-specific-data-terms.md). CC0 applies only to
> project-authored synthetic or authorized first-party observations; third-party terms remain
> binding.

Date: 2026-06-16. Status: accepted.

## Decision

The code is licensed Apache-2.0 (`LICENSE`); the environmental observations are
dedicated to the public domain under CC0-1.0 (`DATA-LICENSE`). `NOTICE` carries
the copyright line and the project's independence statement. The split is wired
through the system, not just stated in two files: `export.to_json()` stamps
`"license": "CC0-1.0"` on every dump, `export.summarize()` prints the
`CC0-1.0 (observations) · see DATA-LICENSE` banner, and `DATA-LICENSE` names the
covered artifacts explicitly — the SQLite/Parquet store, the CSV and JSON
exports, the SensorThings responses, and the aggregated surfaces. The data
license applies to the observations regardless of which store backend or export
format produced them.

## Why

Code and data answer to different licenses because they answer different
questions. Apache-2.0 on the code gives adopters a permissive license with an
explicit patent grant and a `NOTICE`/attribution mechanism, which is what a
hosting collective and downstream reusers want from software they will run and
modify. CC0-1.0 on the observations removes every barrier — no attribution
requirement, no share-alike, no account or key — so a resident, a reporter, or a
researcher can use the measurements, including commercially, without asking, and
the data stays maximally portable (ADR 0007, and the first-class export in
`export.py`). Putting the data into the public domain also sidesteps the murky
question of copyright in factual environmental measurements rather than asserting
a claim over facts. The observations are aggregate measurements only — they
contain no personal information and no field capable of locating a person — so
there is nothing in the data that a permissive dedication could expose. We
rejected a single license for both (a code license like Apache fits data poorly,
and a share-alike data license like ODbL would add friction to reuse we want to
be frictionless) and CC-BY for the data (attribution is a barrier for the
casual reuse this project exists to enable).

## Known weakness / Consequences

Two licenses means contributors and reusers must understand which covers what: a
patch touches Apache-2.0 code, while the readings they publish are CC0. CC0 waives
attribution, so downstream users are not obliged to credit the network or its
hosts — that is the intended trade for frictionless reuse, but it means
provenance travels only because it is baked into each exported row (calibration
version, QC verdict, uncertainty), not because the license compels it. Because
CC0 is a one-way dedication of the observations, it cannot be walked back for data
already released. The independence statement in `NOTICE` is load-bearing and must
stay accurate as the project's ownership evolves toward the hosting collective.
