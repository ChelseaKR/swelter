# Project Scope

Last reviewed: 2026-07-08. Base branch: `main`.

This file is a plain-language map of the project as it exists on `main`. It does not replace the README, roadmap, audit docs, or source comments. It points to them so a reviewer can see the whole shape without reading every file first.

## What This Project Is

Swelter is a community heat and air-exposure network. It combines low-cost observations, calibration, public dashboards, alerts, cooling-center overlays, and governance docs for neighborhood-scale climate evidence.

Package metadata checked in this pass:

- Python package `swelter` for Python `>=3.12`.

## Who It Serves

- Neighborhood groups and advocates tracking heat exposure.
- Funders and civic partners reviewing whether a sensor network can be trusted.
- Maintainers running calibration, dashboards, alerts, and public data releases.

## What It Covers

- Observation data, calibration logic, dashboard surfaces, alerts, and public API docs.
- Hardware, governance, accessibility, versioning, funder, and user-research docs.
- ADRs for storage, calibration, public location handling, dashboard design, exports, alerts, and cooling centers.
- Privacy DPIA, methodology, bug-review, and responsible-tech audit files.
- Tests and workflows around the measurement and web surfaces.

## How It Is Put Together

- src/ holds calibration, ingest, dashboard, alerts, and server code.
- data/ contains demo observations, corrections, colocation, and cooling-center files.
- docs/ contains product, research, standards, governance, API, hardware, and audit material.
- docs/decisions/ records architecture choices.
- tests/ checks computation and public outputs.

Observed source and operations surfaces:

- `Makefile`
- `firmware/`
- `infra/`
- `pyproject.toml`
- `scripts/`
- `src/`
- `web/`

GitHub workflow files checked:

- `.github/workflows/ci.yml`
- `.github/workflows/codeql.yml`
- `.github/workflows/pages.yml`
- `.github/workflows/release.yml`
- `.github/workflows/trufflehog.yml`

## Trust Boundaries

- Sensor data needs calibration and provenance before it is used for claims.
- Public locations are grid-snapped to reduce household-level exposure.
- Alerts and cooling-center overlays need careful language because people may act on them.

## Outside This Scope

- It is not an official weather station network.
- It cannot certify indoor or personal exposure.
- Real deployments need local partners, hardware maintenance, and data-governance ownership.

## Docs And Evidence Checked

This pass checked 64 hand-authored doc or metadata files, 30 test files, and 5 workflow files on `main`. The count excludes vendored provider licenses, dependency folders, generated cache files, and large generated artifact history.

Large content groups were counted rather than listed file by file:

- `docs/standards/`: 12 files

Primary docs checked:

- `.github/ISSUE_TEMPLATE/bug_report.md`
- `.github/ISSUE_TEMPLATE/feature_request.md`
- `.github/PULL_REQUEST_TEMPLATE.md`
- `CHANGELOG.md`
- `CITATION.cff`
- `CLAUDE.md`
- `CODE_OF_CONDUCT.md`
- `CONTRIBUTING.md`
- `LICENSE`
- `NOTICE`
- `README.md`
- `SECURITY.md`
- `docs/ABOUT-THE-NETWORK.md`
- `docs/ADD-YOUR-NEIGHBORHOOD.md`
- `docs/AGENCY-COMPLIANCE-PACK.md`
- `docs/ARCHITECTURE.md`
- `docs/FUNDER-EVIDENCE-PACK.md`
- `docs/HARDWARE.md`
- `docs/I18N.md`
- `docs/POSITIONING.md`
- `docs/RESEARCH-ROADMAP.md`
- `docs/RESPONSIBLE-TECH-AUDITS.md`
- `docs/ROADMAP.md`
- `docs/USER-RESEARCH.md`
- `docs/VERSIONING.md`
- `docs/accessibility/ACR.md`
- `docs/accessibility/README.md`
- `docs/alerts.md`
- `docs/api.md`
- `docs/audits/accessibility-report.md`
- `docs/audits/bug-review.md`
- `docs/audits/methodology.md`
- `docs/audits/privacy-dpia.md`
- `docs/calibration.md`
- `docs/decisions/0001-sqlite-and-files-store.md`
- `docs/decisions/0002-calibration-as-versioned-data.md`
- `docs/decisions/0003-grid-snapped-public-locations.md`
- `docs/decisions/0004-framework-free-accessible-dashboard.md`
- `docs/decisions/0005-read-only-stdlib-server.md`
- `docs/decisions/0006-apache-code-cc0-data.md`
- `docs/decisions/0007-ogc-sensorthings-export.md`
- `docs/decisions/0008-market-position-trust-layer.md`
- `docs/decisions/0009-compound-heat-air-exposure-surface.md`
- `docs/decisions/0010-neighborhood-alerts-feed.md`
- `docs/decisions/0011-cooling-center-overlay.md`
- `docs/decisions/0012-gate-bypass-incident-and-ruleset.md`
- `docs/decisions/0013-accumulating-fetch-store-via-actions-cache.md`
- `docs/decisions/0013-context-layer-overlay.md`
- `docs/decisions/README.md`
- `docs/governance.md`
- `docs/ideation/01-deep-dive.md`
- `docs/ideation/02-large-scale-fixes.md`
- `docs/ideation/03-expansions.md`
- `docs/ideation/04-impact-and-sequencing.md`
- `docs/ideation/README.md`
- Plus 9 more files in the same inventory.

Representative test files checked:

- `firmware/tests/test_store_and_forward.py`
- `tests/__init__.py`
- `tests/conftest.py`
- `tests/test_aggregate.py`
- `tests/test_alerts.py`
- `tests/test_api.py`
- `tests/test_bugfixes.py`
- `tests/test_calibrate.py`
- `tests/test_calibrate_branches.py`
- `tests/test_cli.py`
- `tests/test_cli_flows.py`
- `tests/test_config.py`
- `tests/test_context_layers.py`
- `tests/test_cooling_centers.py`
- `tests/test_crosswalk.py`
- `tests/test_export.py`
- `tests/test_firmware_drivers.py`
- `tests/test_firmware_signing.py`
- `tests/test_i18n.py`
- `tests/test_ingest.py`
- `tests/test_ingest_server.py`
- `tests/test_models.py`
- `tests/test_openaq.py`
- `tests/test_openmeteo.py`
- `tests/test_qc.py`
- `tests/test_roundtrip_interop.py`
- `tests/test_sensor_community.py`
- `tests/test_server.py`
- `tests/test_sources_http.py`
- `tests/test_store.py`

## Validation Notes

For this docs PR, validation means the scope file was generated from the clean `origin/main` worktree, reviewed against repo metadata and docs inventory, and checked with `git diff --check`. Project test suites are still the authority for code behavior, because this PR changes documentation only.
