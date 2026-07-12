# Evidence pack: what a reviewer can verify, and where

This is the verification companion to [`FUNDER-EVIDENCE-PACK.md`](FUNDER-EVIDENCE-PACK.md). That
document makes the case — the need, the demand, the funding path. This one is the checklist behind
it: every engineering claim a grant reviewer might want to confirm, stated plainly, with the exact
place in this repository or its CI where the claim is enforced or disproven. Nothing here is
aspirational unless it is labeled as such; where a control is advisory, missing, or a known gap,
the gap is stated in the same sentence as the claim.

Author: Chelsea Kelly-Reif, 2026. swelter is an independent personal open-source project,
unaffiliated with any employer or client; see [`../NOTICE`](../NOTICE). The README is the source
of truth and its hard rules bind everything here.

Last verified: 2026-07-10, against `origin/main` (commit `ef2dfe6`) and the live GitHub
repository settings and Actions runs of the same date. Recheck cadence: each release, and
whenever a CI workflow, Make target, or repository ruleset changes; at minimum quarterly, and
always before attaching this pack to a proposal.

---

## What the tool is, and who it is for

swelter is a community-owned network of low-cost heat and air-quality sensors plus the pipeline
that makes their readings trustworthy: ingestion with quarantine, QC flagging, per-node
calibration against reference monitors, gridded aggregation, and a framework-free accessible
dashboard (map, sortable table, and plain list as three equal views). It is built for frontline
neighborhoods that live the heat-and-air exposure and rarely hold the data, and for the hosting
collective that owns siting, location precision, and governance. Observation data is CC0; code is
Apache-2.0; there is no account, no key, and no hosted dependency required to use or leave it.

A reviewer can see it working without hardware two ways:

- **Live demo, real data:** <https://chelseakr.github.io/swelter/> — refreshed daily by the
  `demo` workflow in `.github/workflows/pages.yml` (cron `30 13 * * *`), serving real
  Copernicus-CAMS air quality and heat for California cities and, at `/sensors/`, real
  Sensor.Community low-cost sensors (Stuttgart). Both are labeled with their source and shown
  provisional where uncalibrated — the honest posture, not a bug.
- **Local, deterministic:** `uv sync && make demo` replays a recorded synthetic fixture through
  the identical pipeline and serves the dashboard at `http://127.0.0.1:8000`. The dashboard
  labels the fixture as synthetic.

## The enforced quality gates (actual CI jobs, not policy prose)

CI is `.github/workflows/ci.yml` plus three companion workflows. The merge-blocking gate is one
command, `make verify`, run identically in CI and locally so the two cannot drift.

| CI job (workflow) | What it runs | Blocking? |
|---|---|---|
| `checks` (ci.yml) | `make verify` = fmt-check (ruff format), lint (ruff: E, F, I, UP, B, SIM, C901≤10, bandit S), typecheck (`mypy --strict` over src + tests), a11y (12 structural WCAG checks), i18n (4 gate scripts), hygiene (no bare TODO/FIXME; coded suppressions only), version-check, test (pytest with 90% branch-coverage floor); then a `uv build` packaging sanity check | Yes |
| `security` (ci.yml) | pip-audit on the locked runtime tree (one documented waiver: PYSEC-2026-597, a dev-only transitive dep, rationale in the workflow comment), gitleaks secret scan, Semgrep SAST (pinned 1.168.0, no suppression), zizmor workflow audit (pinned 1.16.3, `--min-severity=high`) | Yes |
| `firmware` (ci.yml) | byte-compiles the MicroPython node firmware and runs the hardware-free firmware tests on CPython | Yes |
| `a11y-advisory` (ci.yml) | pa11y/axe real-browser pass over the built dashboard | **No — advisory** (`continue-on-error: true`); the blocking accessibility gate is the structural one in `checks` |
| `analyze (python)` and `analyze (actions)` (codeql.yml) | CodeQL on the Python code and on the workflow YAML itself; every push/PR plus a weekly cron | Yes |
| `trufflehog` (trufflehog.yml) | weekly full-history verified-secret sweep (cron), complementing the per-push gitleaks diff scan | Scheduled; verified finding fails the run |
| `build` (release.yml) | at every `v*` tag: re-runs `make verify` at the tag, builds sdist + wheel, generates SLSA-style build-provenance attestation, cosign-signs (keyless Sigstore), attaches all of it to the GitHub Release | Yes, at release |

**Branch protection is now enforced.** After the disclosed 2026-07-02 gate-bypass incident
(ADR 0012), a GitHub ruleset on `main` blocks deletion and non-fast-forward pushes and requires
six status checks (`checks`, `security`, `firmware`, `a11y-advisory`, `analyze (python)`,
`analyze (actions)`) before changes land. Verified 2026-07-10 via
`gh api repos/ChelseaKR/swelter/rules/branches/main`. Two honest limits: the ruleset does not
yet include a require-pull-request rule, and with a single maintainer there is no second
reviewer to require — both are recorded in ADR 0012, not glossed.

Current measured state (local `make verify` run against this commit, 2026-07-10): all gates
green; 306 tests passed; branch coverage above the 90% floor (93% measured).

## Accessibility posture (the real gate, then the aspiration)

- **Merge-blocking, today:** `scripts/a11y_check.py` runs 12 structural checks on the dashboard
  (`html lang`, `<title>`, single `<h1>`, landmarks, skip link, labeled controls, a data-table
  equivalent to the map, `alt` on every image, no positive tabindex, a language switch,
  `prefers-reduced-motion`, visible focus indicator). It runs inside `make verify`, so a failure
  blocks every merge. Run it yourself: `make a11y`.
- **Structural by design:** map, sortable table, and plain list are three equal views of the same
  observations, so the map is never the only way in; AQI and heat severity are conveyed by text
  and pattern, not color alone.
- **Committed conformance report:** a VPAT 2.5 (Rev 508) ACR at
  [`accessibility/ACR.md`](accessibility/ACR.md), plus the audit at
  [`audits/accessibility-report.md`](audits/accessibility-report.md).
- **Advisory, not yet blocking (the honest line):** the real-browser axe pass (`a11y-advisory`
  job) is allowed to fail, and Lighthouse CI is not wired. WCAG 2.2 AA as a whole is the target
  the structural gate under-approximates; the gate proves the 12 structural checks, not full AA.

## Privacy and data posture

- **No PII by construction:** the observation schema (`src/swelter/models.py`) has no field that
  can hold a person; the only identifier is a collective-assigned node ID. README hard rule 1
  makes adding one a review-failing change.
- **Host locations protected:** published coordinates snap to a ~150 m grid via
  `config.public_location()` unless a host explicitly opts into `precise` (hard rule 2). The full
  risk analysis is the DPIA at [`audits/privacy-dpia.md`](audits/privacy-dpia.md).
- **Read-only serving, no telemetry:** the server (`src/swelter/server.py`) is GET-only (writes
  get 405); the dashboard has no analytics, no client-side telemetry of any kind (a deliberate
  choice, recorded in the README's observability row).
- **Open and portable:** observations are CC0-1.0 (`DATA-LICENSE`), code Apache-2.0 (`LICENSE`);
  export (CSV, JSON, read-only OGC SensorThings 1.1 subset, Datasette-openable SQLite store) is a
  first-class command, so a collective can leave with everything.

## Internationalization state

English and Spanish ship together. Merge-blocking i18n gates in `make verify` (detail in
[`I18N.md`](I18N.md)): UTF-8 encoding (G1), BCP-47 tag validity (G3/G4), EN/ES key parity with no
empty Spanish values (G6), and a CLDR/ICU pin guard (G12, currently pass-by-delegation because
date formatting uses the browser's `Intl`). Not yet wired, and said so in `I18N.md`: the
hardcoded-string extraction ratchet (G2) and full plural-category coverage (G5). There is no
claim of professional translation review; the catalogs are maintainer-written.

## Reproducibility and data integrity

- **Calibration replays byte-for-byte:** re-running the fit on the committed co-location data
  reproduces `data/demo/corrections.yaml` exactly (pure-Python OLS, coefficients rounded to 6 dp;
  300 corrections across 100 co-located demo nodes at the default demo size). A test in the suite
  diffs the rebuilt registry against the committed file, so this is merge-gated, not asserted.
- **Raw is append-only; derived is rebuildable:** the store key
  `(node_id, timestamp, parameter, calibration)` keeps raw and calibrated rows distinct forever;
  `swelter rebuild` reconstructs every derived record from raw alone.
- **Locked environment:** CI installs with `uv sync --locked`, so the audited and tested
  dependency tree is the shipped one.

## Governance and sustainability (stated honestly)

- **Community ownership is the design, single maintainership is the present fact.** Governance,
  siting, and location-precision decisions rest with a hosting collective by design
  ([`governance.md`](governance.md), README hard rule 5), and nothing in the licenses gives the
  author control over someone else's network. But today the project has one maintainer
  (Chelsea Kelly-Reif), no second reviewer, and no organizational home — the right pairing for a
  grant is a fiscal sponsor or an established community organization as lead applicant, as
  [`FUNDER-EVIDENCE-PACK.md`](FUNDER-EVIDENCE-PACK.md) says.
- **Cheap to keep alive:** one runtime dependency (PyYAML), a static dashboard, a scale-to-zero
  optional server; it runs on a Raspberry-Pi-class host with no cloud.
- **Open-source hygiene is in place:** LICENSE, DATA-LICENSE, NOTICE (independence statement),
  CODE_OF_CONDUCT, CONTRIBUTING, SECURITY (private-advisory reporting), CITATION.cff, semver
  policy ([`VERSIONING.md`](VERSIONING.md)), ADRs in [`decisions/`](decisions/), dated audits in
  [`audits/`](audits/), Renovate for dependency updates.
- **Incidents are disclosed, not buried:** the 2026-07-02 direct-to-main gate bypass is written
  up in ADR 0012 and summarized in the README's standards-conformance section, with the
  compensating controls and the since-enabled ruleset.

## Known gaps (current, deliberate disclosures)

- Real-user validation is absent: the persona panel in [`USER-RESEARCH.md`](USER-RESEARCH.md) is
  synthetic, a hypothesis generator, and no real community partner has deployed swelter.
- No PyPI package or container image is published; distribution is source plus signed release
  artifacts (README, DOC-14).
- The axe/pa11y browser accessibility pass and Lighthouse are advisory-only.
- No mutation testing on `calibrate.py`/`qc.py`; no DORA ledger or per-source data cards yet
  (README standards table).
- The branch ruleset lacks a require-pull-request rule, and single-maintainer review cannot meet
  a two-reviewer bar (ADR 0012).
- The plain-language neighborhood exposure brief with sourced equity context (redlining and
  air-conditioning-access layers) is **in review, not merged** — PR #93 — and is not claimed
  here.

## Verification map: claim → where to check

| Claim | Verify at |
|---|---|
| The full merge gate is green on `main` | CI badge / Actions history for `.github/workflows/ci.yml` on `main`; or clone and run `make verify` |
| Accessibility is merge-gated (12 structural checks) | `scripts/a11y_check.py`; the `a11y` step inside `make verify`; run `make a11y` |
| WCAG/508 conformance documentation exists | [`accessibility/ACR.md`](accessibility/ACR.md) (VPAT 2.5), [`audits/accessibility-report.md`](audits/accessibility-report.md) |
| EN/ES parity is enforced, not aspirational | `scripts/i18n_parity.py` + `tests/test_i18n.py`; gate list in [`I18N.md`](I18N.md) |
| Tests and coverage floor | `Makefile` `test` target (`--cov-fail-under=90`); pytest summary in any `checks` job log |
| Static analysis and typing | `pyproject.toml` (`[tool.ruff]`, `[tool.mypy] strict = true`); `checks` job |
| Supply-chain scanning | `security` job in `ci.yml` (pip-audit, gitleaks, Semgrep, zizmor); `codeql.yml`; `trufflehog.yml` |
| Signed, provenance-attested releases that re-verify at the tag | `.github/workflows/release.yml`; artifacts and attestations on any GitHub Release |
| Branch protection on `main` | `gh api repos/ChelseaKR/swelter/rules/branches/main`; design in [`decisions/0012-gate-bypass-incident-and-ruleset.md`](decisions/0012-gate-bypass-incident-and-ruleset.md) |
| Calibration reproducibility | `data/demo/corrections.yaml` + the registry round-trip test in `tests/`; method in [`calibration.md`](calibration.md) |
| No PII fields; coarse public locations | `src/swelter/models.py`, `config.public_location()` + its tests; [`audits/privacy-dpia.md`](audits/privacy-dpia.md) |
| Open data, open standards egress | `DATA-LICENSE` (CC0), `src/swelter/api.py` (read-only SensorThings 1.1 subset), `swelter export`; [`interop-crosswalk.md`](interop-crosswalk.md) |
| Community governance model | [`governance.md`](governance.md); README hard rule 5 |
| Live demo runs on real, current data | <https://chelseakr.github.io/swelter/> and `.github/workflows/pages.yml` (daily cron) |
| The need and funding landscape, with sources | [`FUNDER-EVIDENCE-PACK.md`](FUNDER-EVIDENCE-PACK.md) (every external fact footnoted and dated) |
| Public-entity accessibility/language-access posture | [`AGENCY-COMPLIANCE-PACK.md`](AGENCY-COMPLIANCE-PACK.md) |
