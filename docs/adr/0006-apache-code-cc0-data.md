# ADR 0006: License code under Apache-2.0 and observations under CC0-1.0

- Status: Superseded by 0024
- Date: 2026-06-16
- Deciders: Chelsea Kelly-Reif

## Context

Software and environmental observations answer different reuse questions. The code needs a
permissive license with an explicit patent grant; community measurements should remain portable
without an account, key, or attribution requirement. At the time of this decision, the project
treated its observation stream as first-party community data and did not distinguish fetched
third-party records.

## Decision

License swelter source code under Apache-2.0 and dedicate the observation data under CC0-1.0.
Carry the split through the repository license files, export metadata, and human-readable summaries.

## Consequences

Code contributors work under Apache-2.0 while observation reusers receive a frictionless CC0
dedication. CC0 is irreversible and does not require downstream credit. The decision did not account
for upstream provider terms on later live-source adapters; ADR 0024 supersedes it for that reason.
