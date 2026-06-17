# Security Policy

_Last verified: 2026-06-16. Recheck cadence: each release, or on any change to the write path._

## Reporting a vulnerability

Please report suspected vulnerabilities privately, not in a public issue. Use GitHub's **Report a
vulnerability** button under the repository's **Security** tab (Private Vulnerability Reporting),
which opens a confidential advisory with the maintainer, Chelsea Kelly-Reif. If that is unavailable,
open a minimal public issue that says only "security report — please open a private channel" and
nothing more, and wait to be contacted.

Please include what you found, how to reproduce it, and the impact you expect. You will get an
acknowledgement, and a fix or a written explanation of why something is working as intended. There
is no bounty; this is an independent volunteer project, and credit is given to reporters who want it.

## What the attack surface actually is

swelter's design keeps the blast radius small on purpose:

- **The public API is read-only.** The server (`swelter serve`) answers `GET` only; writes are
  refused with `405`. There is no public mutation path to exploit.
- **The data carries no personal information.** Observations are aggregate environmental
  measurements (temperature, humidity, particulate matter, derived heat/air indices). The schema has
  no field that can hold a person, no device-as-tracker identifier, and no precise coordinate — node
  locations are grid-snapped before publication unless a host opts in (see `docs/governance.md`).
  A data breach therefore exposes public-domain (CC0) environmental readings, not people.
- **The write path is the sensitive one.** Ingestion accepts readings from nodes and must be
  authenticated per node so a stranger cannot inject fabricated observations. Treat the ingest
  endpoint and any node credential as the assets worth protecting. Malformed payloads are quarantined,
  never ingested.

The most meaningful integrity risks are (a) forged or tampered observations and (b) a calibration
that silently misleads. These are mitigated by immutable, content-hashed observations (an edit is a
new record), the calibrated-vs-raw labeling that is never silently mixed, and the reproducible
calibration registry anyone can re-derive and check.

## Supply chain and build integrity

- One runtime dependency (PyYAML); everything else is the Python standard library. A small
  dependency surface is a security property.
- Dependencies are pinned via `uv.lock`; updates land through reviewed Dependabot PRs.
- CI runs `pip-audit` (known-vulnerable dependencies), `gitleaks` (committed secrets), and CodeQL
  (static analysis) on every change.
- Releases are built with `uv build` and published with SLSA-style provenance / signed artifacts
  (see `.github/workflows/release.yml`). Firmware over-the-air updates are signed and staged.

## Supported versions

swelter is pre-1.0 (0.1.x). Security fixes are made on the `main` branch and in the latest tagged
release. Pin a release and watch the repository for advisories.
