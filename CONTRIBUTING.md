# Contributing to swelter

swelter is an independent open-source project by Chelsea Kelly-Reif. Code contributions are
Apache-2.0. Data contributions and fetched data retain the rights described in
[`DATA-LICENSE`](DATA-LICENSE); do not assume every observation is CC0.

Start with the [product rules](README.md#non-negotiable-product-rules), the
[standards conformance ledger](README.md#standards-conformance),
[`DEFINITION_OF_DONE.md`](DEFINITION_OF_DONE.md), and the
[acceptance-test map](docs/ACCEPTANCE-TEST-MAP.md). Environmental data can be precise and still be
wrong, so provenance, provisional state, uncertainty, and source terms are part of correctness.
The portfolio `STANDARDS/` set is vendored and pinned under
[`docs/standards/`](docs/standards/README.md); project-specific values and findings stay in this
repository's own docs.

## Set up

Requirements: Python 3.12+, [uv](https://docs.astral.sh/uv/), and Node.js for web tests.

```console
git clone https://github.com/ChelseaKR/swelter.git
cd swelter
uv sync
uvx pre-commit@4.6.0 install
make verify
make web-test
```

`make demo` rebuilds and serves the deterministic synthetic example. Run `make help` for focused
targets. Do not activate a hand-built environment in CI; `uv.lock` is the dependency source used by
the repository.

## Shape the change before coding

- State the user outcome and observable acceptance criteria.
- Name the affected ISO/IEC 25010 quality characteristics in the PR template.
- Map criteria to tests and human review in `docs/ACCEPTANCE-TEST-MAP.md` when the behavior is new.
- Add an ADR under `docs/adr/NNNN-kebab-title.md` when changing a load-bearing design choice. Use
  the metadata and sections in [ADR 0000](docs/adr/0000-record-architecture-decisions.md).
- Update `CHANGELOG.md` under `Unreleased` for user-visible behavior.
- Update source data cards and licensing when a source, field, attribution, or publication contract
  changes.

Keep each PR focused. Use conventional commit subjects such as `feat:`, `fix:`, `docs:`, `test:`,
`refactor:`, `chore:`, or `ci:`. Explain the decision and risk, not a file-by-file diary.

## Required verification

`make verify` is the local reproduction of the complete merge gate:

- format and lint, including security and complexity rules;
- strict type checking;
- structural accessibility checks;
- UTF-8, BCP-47, EN/ES parity, and CLDR pin checks;
- SEO, hygiene, version, offline standards-pin, acceptance-map, DORA-evidence,
  documentation-figure, and log-safety checks as configured;
- the branch-coverage-gated Python test suite.

`make web-test` remains the focused JavaScript unit/contract command while iterating. CI also runs
the repository's upstream standards-authenticity, browser, dependency, secret, workflow,
static-analysis, build, and release-readiness jobs. Scheduled CI also retains a complete rolling
DORA evidence artifact. Read the Makefile and workflow files for the authoritative job set;
documentation must not freeze a count that changes whenever a gate is added.

A green automated gate is necessary, not sufficient. The PR template names human reviews that apply
to interaction changes, assistive technology, bilingual copy, data/source rights, security, and
responsible technology. Never check a manual attestation based only on an automated result.

## Invariants reviewers enforce

### Data and calibration

- Raw observations are append-only and remain distinct from every calibrated derivative.
- A reading without an applicable correction remains `raw` and its surface remains provisional.
- QC, calibration version, uncertainty, source, time window, and caveats survive storage, aggregate,
  API, export, alert, and share paths.
- Correction-registry changes remain reproducible from their recorded co-location data.

### Location and privacy

- Public node coordinates pass through the configured privacy grid unless the host explicitly opts
  into precision.
- Browser geolocation remains explicit and in-memory; raw device coordinates are not retained.
- No schema, interface, or firmware feature is added to identify a person, scan nearby devices, or
  collect audio/video.

### Accessibility and language

- Map, table, and list remain equivalent ways to reach the same outcome.
- Every visualization retains a text/data equivalent, keyboard operation, visible focus, reduced
  motion, and non-color status cues.
- English and Spanish keys change together. Independent language review is a human task, not a key-
  parity inference.
- Update the ACR when behavior or conformance evidence changes; do not claim a fresh NVDA or VoiceOver
  pass unless a named reviewer actually performed it.

### Licensing and portability

- First-party data may be CC0 only with the publishing collective's authority.
- Third-party terms and attribution travel with exports and static publication. OpenAQ publication
  requires its `source-license-ledger.json`; missing rights metadata fails closed.
- No export or read path moves behind an account or proprietary hosted dependency.

## Pull-request completion

Complete the repository PR template, including rollback/recovery, observability, documentation,
responsible-technology impact, and reviewer attestations.

Sign every commit under the Developer Certificate of Origin (DCO):

```console
git commit -s -m "fix: preserve source attribution in exports"
```

The sign-off certifies the contribution under the repository's terms; it is separate from cryptographic
commit signing. Do not rewrite or remove another contributor's sign-off.

Before requesting review:

```console
make verify
make web-test
git diff --check
```

Record any test you could not run and why. Release-only evidence follows
[`DEFINITION_OF_DONE.md`](DEFINITION_OF_DONE.md) and the release checklist; normal PRs must not claim
that a tag, package, signature, provenance artifact, deployment, or rollback was exercised when it was
not.

## Reporting problems

Open a GitHub issue for normal defects and documentation gaps. Use the private reporting path in
[`SECURITY.md`](SECURITY.md) for suspected vulnerabilities or sensitive location/data exposure.

Last verified: 2026-07-16. Recheck cadence: every release and whenever the toolchain, merge gate,
license boundary, or product rules change.
