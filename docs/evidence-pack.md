# swelter evidence pack

This is the reviewer index for the `0.2.0` release candidate. It links claims to reproducible evidence
and names limits that remain open. It is not a substitute for the exact merge-commit CI run or the
tagged release artifacts.

Owner: Chelsea Kelly-Reif. Evidence date: 2026-07-16. Recheck cadence: every release, every material
incident, and whenever workflows, rulesets, sources, trust boundaries, or standards pins change.

## Product claim and scope

swelter is an open-source reference implementation for community heat and air-quality measurement,
calibration provenance, accessible exploration, and portable publication. It does not claim to be a
regulatory monitor, medical device, individualized safety service, emergency-alert system, validated
community deployment, or government system.

The live reference site publishes fetched provider/model data with visible source and freshness. The
deterministic local demo is synthetic. Low-cost sensor readings without an applicable reference
correction remain provisional. Data rights are source-specific; only project-authored or authorized
first-party observations are covered by the repository's CC0 dedication.

## Evidence index

| Claim | Primary evidence | Verification path | Known limit |
|---|---|---|---|
| Raw observations are immutable and calibrated values remain distinct | `store.py`, `models.py`, `calibrate.py`, ADR 0001/0002 | Store, rebuild, calibration, aggregate, API, and export tests; `swelter verify-archive` | Filesystem owner can replace store and local evidence together |
| Public location is coarse by default | `config.public_location`, aggregate/API paths, ADR 0003 | Location/config/context/source adapter tests | Sparse cells can still reveal approximate siting; precision opt-in is irreversible for downloaded copies |
| Node writes are authenticated and separate from public reads | `ingest_server.py`, firmware signing, `server.py` | Ingest-server/firmware/CLI tests plus threat model | Compromised node key can sign plausible false readings |
| Source and license claims travel with publication | `DATA-LICENSE`, `docs/data-cards/`, source adapters, publisher | Source truth/license/manifest tests; inspect generated data-license and `source-license-ledger.json` | Provider terms/metadata can change; data steward recheck required |
| Observatory exposes linked analytical views without a map-only path | `web/index.html`, `app.js`, `observatory.css`, ADR 0004 | Web unit/contract tests, browser checks, structural a11y gate | Current NVDA/VoiceOver signoff remains issue #106 |
| English and Spanish catalogs remain mechanically aligned | `web/i18n/en.json`, `web/i18n/es.json`, `docs/I18N.md` | UTF-8, BCP-47, key-parity, and CLDR-pin gates | Independent Spanish clarity review remains issue #106 |
| Static publication identifies source/freshness and excludes unsafe fixtures | `swelter publish`, Pages workflow, generated manifest/source truth | Publisher/SEO/source tests and post-deploy smoke | Pages/repository governance exception remains issue #105 |
| Archive/data releases are citable and verifiable | `snapshot.py`, `integrity.py`, `docs/citability.md` | Snapshot/integrity/version tests; compare hashes and citation metadata | No DOI or public `v0.2.0` release exists until owner publishes them |
| Quality/security/release work is reproducible | Make targets and workflow files | `make verify`, `make web-test`, CI/security/release jobs on exact ref | GitHub-hosted runner and third-party Actions remain trust roots |
| Responsible-technology review covers current boundaries | `docs/RESPONSIBLE-TECH-AUDITS.md` and linked artifacts | Review data flow, DPIA, threat/fairness/ethics scans, residual risks | No real partner/user validation; manual signoffs are not inferred |

## Reproduce the candidate locally

```console
uv sync --locked
make verify
make web-test
git diff --check
uv run swelter demo
uv run swelter verify-archive --store store/demo --write
```

Focused artifacts:

```console
uv run swelter publish --store store/demo --web /tmp/swelter-publish
uv run swelter snapshot --store store/demo --out /tmp/swelter-snapshot
```

Use an explicit temporary directory, inspect `publish-manifest.json`, source truth, data-license text,
and any required source-license ledger, then remove the temporary artifacts. The synthetic demo does
not prove live-provider availability or licensing; provider publication has its own adapter and
workflow tests.

The authoritative current command/job list is the Makefile and `.github/workflows/`. This evidence
pack intentionally does not copy test, file, dependency, or Action counts that become stale without
changing the underlying claim.

## Delivery evidence

[`DORA.md`](DORA.md) is generated from retained Actions and incident-issue JSON with exact query
metadata and an input digest. The earlier aggregate-only numbers were retired because their row-level
query output was not retained; the committed snapshot therefore says **unavailable** instead of
reverse-engineering apparently precise evidence. Scheduled CI now produces a complete rolling
evidence artifact for maintainer review and later commitment.

Release evidence is intentionally pending until an annotated `v0.2.0` tag exists. A complete release
record must include:

- exact tag/commit and dated changelog/CFF version parity;
- exact-tag verification and package build;
- checksums, SBOM, one Cosign v3 `*.sigstore.json` verification bundle per asset, and build
  provenance;
- consumer installation/CLI verification from the published artifact;
- GitHub Release URL and static deployment run URL;
- primary-path smoke result and rollback/recovery evidence.

Do not convert planned workflow behavior into evidence that the release occurred.

## Standards and review evidence

- [Definition of done](../DEFINITION_OF_DONE.md) — AUTO, REVIEW, and RELEASE gates.
- [Acceptance-test map](ACCEPTANCE-TEST-MAP.md) — executable one-to-one
  feature/criterion/test-symbol/review/ISO mapping.
- [Standards pin](STANDARDS-PIN.md) — offline byte integrity plus CI authentication against the
  canonical v2.0.0 release, tag, commit, and blobs.
- [Architecture decisions](adr/README.md) — MADR-compatible source of record with legacy links kept.
- [Source data cards](data-cards/README.md) — purpose, provenance, limitations, rights, and refresh.
- [Responsible-technology audit](RESPONSIBLE-TECH-AUDITS.md) — current A–F review in the four-question
  framework.
- [Accessibility conformance report](accessibility/ACR.md) — automated/manual evidence boundaries.
- [Operations runbook](runbooks/operations.md) — containment, rollback, and recovery.

## Open, honestly bounded findings

1. [#105](https://github.com/ChelseaKR/swelter/issues/105): intentionally excluded repository and
   production-environment governance work. The current controls are documented; no stronger PR,
   approval, signed-commit, linear-history, strict-check, environment-reviewer, or Pages-cache claim is
   made here.
2. [#106](https://github.com/ChelseaKR/swelter/issues/106): current NVDA/VoiceOver and independent
   Spanish release signoff. Automation and the older baseline are not described as a current human
   pass.
3. [#107](https://github.com/ChelseaKR/swelter/issues/107): suppression retirement and code-quality
   follow-up. Suppressions remain coded and visible while they are retired.
4. Real partner/community research has not occurred. Synthetic/persona research helps generate
   hypotheses but does not establish demand, usability, comprehension parity, or equitable outcomes.
5. Signed/staged firmware OTA and a Parquet/Arrow store are future seams, not shipped capabilities.

These limits are part of the evidence. Removing them without closing the underlying condition would
make the pack less conformant, not more complete.
