# ADR 0025: Add pinned structured logging without changing the stdlib server architecture

- Status: Accepted
- Date: 2026-07-16
- Deciders: Chelsea Kelly-Reif
- Supersedes: the dependency-count statements in ADRs 0001 and 0005

## Context

The portfolio observability standard requires opt-in structured JSON diagnostics and a defensive
PII-in-logs gate even for a Tier-C local CLI. Hand-rolling JSON serialization around the standard
library logger would duplicate redaction and rendering behavior that needs stable, testable output.
The earlier architecture records accurately chose SQLite and a standard-library HTTP server, but
their claim that PyYAML would remain the only direct Python dependency no longer describes the
required observability surface.

## Decision

Keep PyYAML for operator configuration and add exactly one direct observability dependency:
`structlog==26.1.0`. `swelter.obs` uses its deterministic JSON renderer behind the existing standard
library logging API. Logging remains opt-in; the public HTTP server is still
`http.server.HTTPServer`, not a framework. The lockfile resolves the complete graph, release builds
use that lock, and static gates reject person-shaped fields, credentials, IP addresses, and exact
coordinate pairs.

## Consequences

The Python package now has two direct runtime dependencies rather than one. This adds a dependency
update and vulnerability-review obligation, but does not add a daemon, hosted service, web
framework, telemetry collector, or network egress. ADRs 0001 and 0005 remain authoritative for the
store and server choices; only their dependency-count statements are superseded.
