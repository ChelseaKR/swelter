# Documentation Audit

Last reviewed: 2026-07-08. Base branch: `main`.

This audit records the documentation sweep and remediation loop for this repository. It checks the docs as a system: entry points, root-level process and legal files, project scope, setup and validation notes, safety and privacy posture, architecture and planning docs, local links, and the places where code, tests, workflows, and docs meet.

## Audit Results

| Area | Result | Evidence |
| --- | --- | --- |
| Entry docs | pass | `README.md` present |
| Security/process docs | pass | CONTRIBUTING.md, SECURITY.md, CHANGELOG.md |
| Architecture/planning docs | pass | 2 architecture/interface docs; 9 planning/research docs |
| Safety/privacy/audit docs | pass | 9 safety/privacy/accessibility/audit docs |
| Validation surface | pass | 28 test files; 5 workflow files |
| Local doc links | pass | 228 authored-doc links checked; 0 unresolved |

## Root-Level Documentation Audit

This section covers hand-authored documentation at the repository root and root-adjacent GitHub templates. It is separate from the `docs/` inventory so README, process, legal, release, and project-specific root files do not get hidden inside the larger docs tree.

| Surface | Result | Evidence |
| --- | --- | --- |
| Root README | pass | Present: `README.md` |
| Root process docs | pass | Present: `CONTRIBUTING.md`, `SECURITY.md`, `CHANGELOG.md` |
| Root legal, citation, and conduct docs | pass | Present: `LICENSE`, `NOTICE`, `CITATION.cff`, `CODE_OF_CONDUCT.md` |
| Other root project docs | info | `CLAUDE.md` |
| Root-adjacent GitHub templates | pass | `.github/PULL_REQUEST_TEMPLATE.md`, `.github/CODEOWNERS`, `.github/ISSUE_TEMPLATE/bug_report.md`, `.github/ISSUE_TEMPLATE/feature_request.md` |
| Root/template doc links | pass | 28 root-level/template links checked; 0 unresolved |

Root-level files checked:

- `CHANGELOG.md`
- `CITATION.cff`
- `CLAUDE.md`
- `CODE_OF_CONDUCT.md`
- `CONTRIBUTING.md`
- `LICENSE`
- `NOTICE`
- `README.md`
- `SECURITY.md`

Root-adjacent template files checked:

- `.github/PULL_REQUEST_TEMPLATE.md`
- `.github/CODEOWNERS`
- `.github/ISSUE_TEMPLATE/bug_report.md`
- `.github/ISSUE_TEMPLATE/feature_request.md`

## Remediation In This PR

- Added missing root-level remediation docs found by the audit loop, including legal, conduct, contribution, or security files where absent.
- Added `docs/PROJECT-SCOPE.md` as the plain-language project and boundary map.
- Added this audit record so future doc changes have a dated baseline.
- Added or refreshed the docs index so scope, audit, and primary docs are easy to find.
- Fixed or added root/doc remediation files: `docs/standards/README.md`.

## Repo Surfaces Checked

Package and workspace metadata:

- Python package `swelter` (>=3.12).

Source and operations surfaces seen at the repo root:

- `data/`
- `infra/`
- `Makefile`
- `pyproject.toml`
- `scripts/`
- `src/`
- `tests/`
- `uv.lock`
- `web/`

Workflow files checked:

- `.github/workflows/ci.yml`
- `.github/workflows/codeql.yml`
- `.github/workflows/pages.yml`
- `.github/workflows/release.yml`
- `.github/workflows/trufflehog.yml`

## Documentation Inventory

| Category | Count | Representative files |
| --- | ---: | --- |
| architecture and interfaces | 2 | `docs/ARCHITECTURE.md`, `docs/api.md` |
| entry points and repo process | 12 | `.github/CODEOWNERS`, `.github/ISSUE_TEMPLATE/bug_report.md`, `.github/ISSUE_TEMPLATE/feature_request.md`, `.github/PULL_REQUEST_TEMPLATE.md`, `CHANGELOG.md`, `CITATION.cff`, `CODE_OF_CONDUCT.md`, `CONTRIBUTING.md`, plus 4 more |
| operations and release | 3 | `docs/VERSIONING.md`, `docs/decisions/0002-calibration-as-versioned-data.md`, `docs/decisions/0012-gate-bypass-incident-and-ruleset.md` |
| other docs | 33 | `CLAUDE.md`, `docs/ABOUT-THE-NETWORK.md`, `docs/ADD-YOUR-NEIGHBORHOOD.md`, `docs/FUNDER-EVIDENCE-PACK.md`, `docs/HARDWARE.md`, `docs/I18N.md`, `docs/POSITIONING.md`, `docs/PROJECT-SCOPE.md`, plus 25 more |
| planning and research | 9 | `docs/RESEARCH-ROADMAP.md`, `docs/ROADMAP.md`, `docs/USER-RESEARCH.md`, `docs/ideation/01-deep-dive.md`, `docs/ideation/02-large-scale-fixes.md`, `docs/ideation/03-expansions.md`, `docs/ideation/04-impact-and-sequencing.md`, `docs/ideation/README.md`, plus 1 more |
| safety, privacy, accessibility, and audits | 9 | `docs/AGENCY-COMPLIANCE-PACK.md`, `docs/DOCUMENTATION-AUDIT.md`, `docs/RESPONSIBLE-TECH-AUDITS.md`, `docs/accessibility/ACR.md`, `docs/accessibility/README.md`, `docs/audits/accessibility-report.md`, `docs/audits/bug-review.md`, `docs/audits/methodology.md`, plus 1 more |
| grouped generated/source content | 12 | `docs/standards/` counted as a content group, not listed file by file |

Full hand-authored doc inventory checked by this pass:

- `.github/CODEOWNERS`
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
- `docs/DOCUMENTATION-AUDIT.md`
- `docs/FUNDER-EVIDENCE-PACK.md`
- `docs/HARDWARE.md`
- `docs/I18N.md`
- `docs/POSITIONING.md`
- `docs/PROJECT-SCOPE.md`
- `docs/README.md`
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
- `docs/interop-crosswalk.md`
- `docs/research/user-research-panel.md`
- `firmware/README.md`
- `firmware/hardware/BOM.md`
- `firmware/hardware/assembly.md`
- `infra/README.md`
- `infra/cdk/README.md`
- `infra/cdk/requirements.txt`
- `web/README.md`

Grouped content counts:

- `docs/standards/`: 12 files

## Link Check

- Checked 228 local links in authored Markdown and MDX docs.
- Unresolved authored-doc links after remediation: 0.
- Root-level/template unresolved links after remediation: 0.

Audit scope notes:

- Generated sites, deployed app routes, raw third-party HTML captures, and golden fixture websites were inventoried as product or data surfaces but excluded from authored-doc link failure counts.
- Grouped content directories are counted so they stay visible without making the audit readable without hiding them.

## Validation Notes

- The audit was generated from a clean worktree based on `origin/main` for this PR branch.
- Ran a local relative-link check over hand-authored Markdown and MDX docs.
- Ran an explicit root-level documentation presence and link check for README, process, legal, project, and template docs.
- Ran `git diff --check` across the PR worktrees after remediation.
- Product test suites remain the authority for runtime behavior; this PR changes documentation only.
