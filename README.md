# swelter

Community-owned heat and air-quality sensing, with calibration records and an accessible public map
and data explorer.

[![CI](https://github.com/ChelseaKR/swelter/actions/workflows/ci.yml/badge.svg)](https://github.com/ChelseaKR/swelter/actions/workflows/ci.yml)
[![code: Apache-2.0](https://img.shields.io/badge/code-Apache--2.0-blue.svg)](LICENSE)
[![data terms: source-specific](https://img.shields.io/badge/data%20terms-source--specific-5b5bd6.svg)](DATA-LICENSE)
[![accessibility: WCAG 2.2 AA target](https://img.shields.io/badge/accessibility-WCAG%202.2%20AA-176b3a.svg)](docs/accessibility/ACR.md)

**[Open the live California map](https://chelseakr.github.io/swelter/)** ·
[Second route (`/sensors/`)](https://chelseakr.github.io/swelter/sensors/)

**What the live map is showing right now: Copernicus CAMS atmospheric model output for 337
California places, via Open-Meteo — not physical sensors.** The pipeline is built for a physical
sensor network and supports two real physical-sensor sources; one of them, Sensor.Community, now
reaches the `/sensors/` route, while the main map still falls back to model output. See
[What the deployed site actually shows](#what-the-deployed-site-actually-shows) for which
source is live on each route, why, and where each artifact states its own terms.

**Status:** Beta — maintained pre-1.0 reference implementation.

swelter turns environmental readings into a public record that shows its work. The pipeline
validates and quarantines payloads, keeps raw observations immutable, applies versioned calibration
corrections, and publishes uncertainty, QC, time-window, source, and calibration state with every
surface. The interface shows a **Current reading** and a **Readings** workspace. History, location
distribution, and evidence details sit alongside equivalent map, table, and list representations.

This is an independent, pre-1.0 reference implementation by Chelsea Kelly-Reif. It is not a medical
device, regulatory monitor, emergency-alert service, or government system. It contains no employer,
client, or proprietary material.

## What is built

- **Trustworthy ingestion:** a separate HMAC-authenticated node write listener validates freshness,
  node identity, schema, and range before the append-only SQLite store accepts a reading. Refused or
  malformed payloads are quarantined.
- **Calibration as evidence:** per-node corrections are fitted from recorded co-location windows and
  stored as versioned YAML. Raw and calibrated rows remain distinct; uncalibrated data stays visibly
  provisional.
- **Readings with evidence:** Current reading summarizes the selected place; Readings links history,
  location distribution, evidence details, a map, a sortable table, and a plain list. Missing buckets
  remain gaps, and uncertainty and provisional state stay attached to each value.
- **Open interfaces:** CSV and JSON exports, static publication, citable snapshots, and a read-only OGC
  SensorThings 1.1 subset. The default store is one copyable SQLite-and-files directory.
- **Community portability:** copy `network.yaml` to register another network. No hosted account or
  vendor service is required for the core pipeline.
- **Bilingual, accessible delivery:** English and Spanish catalogs are parity-gated. Structural and
  real-browser checks run in CI; current manual NVDA/VoiceOver and independent Spanish signoff remain
  explicitly tracked in [issue #106](https://github.com/ChelseaKR/swelter/issues/106).

## Try it locally

Requirements: Python 3.12+, [uv](https://docs.astral.sh/uv/), and Node.js for the web test job.

```console
git clone https://github.com/ChelseaKR/swelter.git
cd swelter
uv sync
make verify
make demo
```

`make demo` deterministically rebuilds the synthetic worked example and serves the dashboard at
`http://127.0.0.1:8000`. `make verify` reproduces the complete local merge gate, including the web
contract; `make web-test` remains the focused JavaScript command used while iterating.

## Install a release

swelter is **not on PyPI**, and that is a declared, gate-enforced state rather than an oversight:
`docs/audits/release-publishing-gap.json` records the PyPI channel as
`pending_external_configuration`, and `release.yml`'s preflight fails if that file ever claims
otherwise without the trusted-publisher configuration actually existing. GitHub Releases are the
canonical distribution channel. There is no `pip install swelter` to run, and this README will not
print one until there is.

Two release-preflight gates are open today and both block a published release: the PyPI gap above
(`release_artifacts.py validate-publishing-gap` exits non-zero on purpose while Trusted Publishing
is unconfigured) and the eight human release-review attestations in
`docs/audits/release-review-attestations.json`, which are all still `pending` and which only named
human reviewers can clear. Until those are resolved, `release.yml` cannot finish, so **no GitHub
Release exists yet**.

Installing from an annotated tag does not depend on either of them. Once `v0.2.0` is tagged, the
operator CLI installs straight from the tag:

```console
uvx --from git+https://github.com/ChelseaKR/swelter@v0.2.0 swelter --help
uvx --from git+https://github.com/ChelseaKR/swelter@v0.2.0 swelter init --config my-network.yaml \
  --name "My neighborhood heat and air network"
```

When the release workflow can finish, it attaches a signed, attested wheel and sdist — the same
artifacts — plus `swelter-observatory-<version>.tgz`, the built dashboard, to the GitHub Release.

The wheel carries the Spanish and English alert catalogs and the California boundary geometry, so
the operator path — `swelter init`, `doctor`, `ingest`, `qc`, `calibrate`, `aggregate`, `publish`,
`serve` against **your own** `network.yaml` and store — runs from the wheel alone with no extra
data files.

The **`swelter demo` subcommand is the exception**: it replays `data/demo/observations.jsonl`,
which is committed at the repository root and is deliberately not packaged, so it needs a clone
(or the sdist) rather than a wheel. `swelter init` names `swelter demo --serve` only where that
data is actually present; from a wheel-only install it names `swelter doctor` as the next step and
says to clone the repository and run `make demo` for the demo. `swelter demo` run without the data
refuses in one line with the same directions, rather than deleting the demo store and raising
(#226).

Useful commands:

```console
uv run swelter init --config my-network.yaml --name "My neighborhood heat and air network"
uv run swelter doctor --config my-network.yaml
uv run swelter fetch --source openmeteo --store store
uv run swelter fetch --source sensor-community --store store
uv run swelter fetch --source openaq --api-key "$OPENAQ_API_KEY" --store store
uv run swelter publish --store store --web dist
uv run swelter serve --store store
uv run swelter snapshot --store store --out dist/snapshot
```

Run `uv run swelter --help` before relying on an example in automation; pre-1.0 command and schema
changes follow [`docs/VERSIONING.md`](docs/VERSIONING.md) and are called out in the changelog.

## Data sources and rights

The code is Apache-2.0. Data terms are source-specific; the repository does not relabel third-party
measurements as CC0.

| Source | Kind | Publication posture |
|---|---|---|
| Community-operated swelter nodes | Physical measurements | CC0 only when the publishing collective has authority to dedicate them |
| Synthetic demo | Project-authored fixture | CC0-1.0 |
| OpenAQ | Aggregated physical-monitor data | Per-location provider terms and attribution in `source-license-ledger.json`; publication fails closed without the ledger |
| Copernicus CAMS via Open-Meteo | Modelled/reanalysis air quality and weather | Upstream attribution and license retained; not swelter-calibrated |
| Sensor.Community | Community low-cost sensors | Sensor.Community attribution and database terms retained; readings remain provisional until calibrated |

Read [`DATA-LICENSE`](DATA-LICENSE) for the legal boundary and [`docs/data-cards/`](docs/data-cards/README.md)
for provenance, limitations, refresh, and quality notes. Context layers and cooling-center data have
their own source records and are not silently swept into the observation license.

### What the deployed site actually shows

That table is the set of sources the pipeline *supports*. It is not what the two published routes are
serving, and the difference matters enough to state plainly: **the main map at
[chelseakr.github.io/swelter](https://chelseakr.github.io/swelter/) today is atmospheric model
output, not a physical sensor reading; `/sensors/` carries real Sensor.Community readings,
uncalibrated and provisional.**

The daily `demo` workflow tries the sources in order and publishes the first that succeeds. As of
**2026-08-29**, checked against each route's own machine-readable artifacts (`demo.json` and the
`rights` envelope inside `sample-surface.json`):

| Route | Intended source | What is published | Why |
|---|---|---|---|
| `/` | OpenAQ — dense real physical monitors across California | **Copernicus CAMS via Open-Meteo**, 337 California places, hourly | The OpenAQ fetch fails closed with `OpenAQ readings have no publishable per-location license ledger`. swelter will not publish readings whose provider terms it cannot name, so the run falls through to CAMS. One cause is now proven and fixed — the ledger builder emitted entries its own validator refuses, so a single unlicensable location voided the whole state — but that fix is not yet confirmed against the live API to be the *only* cause; tracked in [issue #179](https://github.com/ChelseaKR/swelter/issues/179) |
| `/sensors/` | Sensor.Community — community low-cost sensors near Stuttgart | **Real Sensor.Community readings** — uncalibrated, shown provisional, ODC-DbCL-1.0 attribution retained | The cached fetch store predated a provenance requirement and the fetch refused on every run, with no way to recover; [ADR 0044](docs/adr/0044-an-unattributable-store-is-discarded-not-refused-forever.md) discards an unattributable store instead of refusing forever, and the route has carried real readings since a scheduled run picked that up — its `demo.json` and `rights` envelope name the source and terms |

CAMS is model/reanalysis output on a grid. The published points are real California city centroids
snapped to model cells, so the map must not be read as block-level measurement, as a sensor at each
point, or as a swelter-calibrated value — see
[`docs/data-cards/openmeteo-cams.md`](docs/data-cards/openmeteo-cams.md).

This table is a snapshot and can go stale. Each deploy states its own terms in machine-readable form
and those never can: `demo.json` (the source-truth contract, built from the fetch output and checked
against the surface before publish), the `rights` envelope inside `sample-surface.json`, and the
route's generated `DATA-LICENSE`. When this README and the artifact disagree, the artifact is right.

## Architecture

```text
sensor / source adapters
        │
        ├─ authenticated write: swelter ingest-serve
        ▼
validate → quarantine or append raw observation → QC → calibrate → aggregate
        │                                              │
        └──────── copyable SQLite + files store ──────┘
                                                       │
                           ┌───────────────────────────┴────────────────────┐
                           ▼                                                ▼
                 read-only local server                         static publish artifact
              SensorThings · CSV · JSON                    Pages/CDN · source/license ledger
                           └───────────────────────────┬────────────────────┘
                                                       ▼
                    Current reading · Readings · map · table · list · export
```

The current store is SQLite plus generated files; a Parquet/Arrow backend is only an extension seam,
not a shipped implementation. The public server is GET-only and intentionally separate from the
authenticated ingest listener. GitHub Pages is a static deployment, so its freshness is the timestamp
shown by the latest successful publication rather than a live sensor-stream guarantee.

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md), the
[`docs/adr/`](docs/adr/README.md) decision log, and the
[`docs/ACCEPTANCE-TEST-MAP.md`](docs/ACCEPTANCE-TEST-MAP.md) for design and verification detail.

## Non-negotiable product rules

1. **Measure environments, not people.** No microphone, camera, client scanning, account, or field
   intended to identify a person. Browser geolocation is explicit, used in memory to find a nearby
   public cell, and not retained as a raw coordinate.
2. **Hosts control location precision.** Public node coordinates are grid-snapped by default;
   publishing a precise node location requires explicit host consent.
3. **Never blur raw and calibrated.** Every reading exposes calibration and QC state. A value without
   a valid correction remains provisional.
4. **Caveats travel with values.** Source, time window, uncertainty, missingness, and estimated/model
   status remain visible in the UI, exports, alerts, and share artifacts.
5. **Portability includes rights accuracy.** First-class export is required, and every export retains
   the terms and attribution that actually bind its source.
6. **A map is never the only way in.** The same filtered data and outcomes remain available through
   semantic table/list views and keyboard-operable controls.

## Quality and review

[`DEFINITION_OF_DONE.md`](DEFINITION_OF_DONE.md) separates deterministic automation, human review,
and release-only evidence. The PR template requires acceptance criteria, ISO/IEC 25010 quality
characteristics, responsible-tech impact, source-license impact, rollback, and reviewer attestations.
No automated result is presented as proof that a human completed assistive-technology or translation
review.

The current DORA-style baseline and reproduction queries are in [`docs/DORA.md`](docs/DORA.md).
Operational recovery is in [`docs/runbooks/operations.md`](docs/runbooks/operations.md); security
reporting is in [`SECURITY.md`](SECURITY.md).

## Standards Conformance

This ledger uses the repository-standard two-column schema and was swept on **2026-07-31**. An
`Applies` state means the relevant automated, review, release, documentation, or operational evidence
is linked from the repository. Open work is never hidden inside a passing state.

| Standard | State |
|---|---|
| Quality & Metrics | Applies — gap tracked in [#109](https://github.com/ChelseaKR/swelter/issues/109) |
| Code Quality | Applies — gap tracked in [#107](https://github.com/ChelseaKR/swelter/issues/107) |
| Security & Supply-Chain | Applies |
| CI/CD | Applies — gap tracked in [#105](https://github.com/ChelseaKR/swelter/issues/105) |
| Release & Versioning | Applies — gap tracked in [#108](https://github.com/ChelseaKR/swelter/issues/108) |
| Accessibility | Applies — gap tracked in [#106](https://github.com/ChelseaKR/swelter/issues/106) |
| Observability | Applies |
| Internationalization | Applies — gap tracked in [#106](https://github.com/ChelseaKR/swelter/issues/106) |
| AI Development Measurement | Applies — gap tracked in [#109](https://github.com/ChelseaKR/swelter/issues/109) |
| AI Evaluation | N/A — no prompt, retrieval, trained/foundation model, or model-version surface |
| Data Governance | Applies |
| Documentation | Applies |
| Incident Response | Applies |
| Performance | Applies |
| Responsible-Tech Framework | Applies — gap tracked in [#106](https://github.com/ChelseaKR/swelter/issues/106) |

For observability, the deployed artifact uses the static-site tier; the optional CLI/self-hosted
server uses structured operational logs; real-user monitoring is intentionally N/A because the
reference site collects no client telemetry. The intentionally excluded merge/production-governance
finding is isolated in #105 and is not claimed as remediated here.

The CI/CD row stays a tracked gap, and the branch ruleset it refers to is now committed as
[`.github/rulesets/main.json`](.github/rulesets/README.md) rather than existing only as a repository
setting no commit records. The captured file is what makes the gap legible: six checks are required
to merge, and `web-tests` — which runs the target the [roadmap](docs/ROADMAP.md) metrics ledger names
as the AUTO gate for the web interaction contract — is not among them, which is the "strict required
checks including web-tests" item #105 already tracks. `tests/test_ruleset.py` holds the file to the workflows, so a new pull-request job cannot be
added without either becoming a required check or being declared, with a reason, as one that is not.
Committing the ruleset is evidence of intent, not proof of enforcement: `bypass_actors` is recorded
faithfully, and it says the repository-admin role can bypass every rule.

## Project documentation

- [Contributing](CONTRIBUTING.md) · [definition of done](DEFINITION_OF_DONE.md) ·
  [changelog](CHANGELOG.md) · [security](SECURITY.md)
- [Architecture](docs/ARCHITECTURE.md) · [ADRs](docs/adr/README.md) ·
  [roadmap](docs/ROADMAP.md) · [multiyear plan](docs/MULTIYEAR-PLAN.md) · [API](docs/api.md)
- [Responsible-technology audits](docs/RESPONSIBLE-TECH-AUDITS.md) ·
  [DPIA](docs/audits/privacy-dpia.md) · [threat model](docs/audits/threat-model.md) ·
  [residual-risk register](docs/audits/residual-risk-register.md)
- [Accessibility conformance report](docs/accessibility/ACR.md) ·
  [internationalization](docs/I18N.md) · [source data cards](docs/data-cards/README.md)
- [Standards pin](docs/STANDARDS-PIN.md) · [evidence pack](docs/evidence-pack.md) ·
  [citation and archival](docs/citability.md)

Copyright 2026 Chelsea Kelly-Reif. Code: Apache-2.0. Data: see `DATA-LICENSE`.

## Support

This is independent, unpaid work. If it has been useful to you, you can
<a href='https://ko-fi.com/T6T6GMYTU' target='_blank'><img height='36' style='border:0px;height:36px;' src='https://storage.ko-fi.com/cdn/kofi6.png?v=6' border='0' alt='Buy Me a Coffee at ko-fi.com' /></a>
