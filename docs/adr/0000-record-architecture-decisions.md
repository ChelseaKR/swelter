# ADR 0000: Record architecture decisions in a durable, reviewable log

- Status: Accepted
- Date: 2026-07-16
- Deciders: Chelsea Kelly-Reif

## Context

swelter has load-bearing decisions across data integrity, privacy, accessibility, deployment, and
community ownership. Those decisions need a stable source of record that a reviewer can discover,
compare with the implementation, and supersede without erasing history. The original
docs/decisions/ log used a useful house format but lacked the metadata and section structure
required by the portfolio documentation standard, and ADR 0013 had been assigned twice.

## Decision

Use docs/adr/NNNN-kebab-title.md for architecture decisions. Every record carries Status,
Date, and Deciders, followed by Context, Decision, and Consequences. Accepted records are
not rewritten to hide a later reversal; a new record declares what it supersedes. The legacy
docs/decisions/ directory remains in place for link durability, but all new records and links use
docs/adr/.

Keep the accumulation/cache record as ADR 0013 and renumber the historical context-layer record to
ADR 0023. This resolves the collision while minimizing ambiguity in deployed workflow commentary.

## Consequences

The log is machine-checkable and easier to review, and old URLs continue to resolve. During the
migration, the same historical content exists at legacy and current paths; maintainers must treat
docs/adr/ as authoritative. References that named the context-layer decision as ADR 0013 need to
move to ADR 0023 when their owning files are next touched.
