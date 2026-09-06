# swelter agent operating contract

Read [`README.md`](README.md), [`DEFINITION_OF_DONE.md`](DEFINITION_OF_DONE.md), and
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) before changing the repository. swelter is a
community-operated heat and air-quality pipeline plus an accessible public observatory. Its core
value is not a colorful map; it is a traceable path from measurement to claim.

## Non-negotiable invariants

1. **No surveillance.** Do not add people, accounts, device scanning, audio/video, or personal
   identifiers to the schema, firmware, browser, logs, or infrastructure. Browser geolocation is
   explicit, in-memory, and used only to select a nearby published cell.
2. **Location precision belongs to the host.** Coarse grid publication is the default. All new
   coordinate outputs must use the public-location seam; precision is an explicit opt-in.
3. **Raw and calibrated never blur.** Raw rows are immutable. Calibration produces distinct rows
   with a version and uncertainty. Missing correction means provisional, everywhere.
4. **Caveats travel.** Preserve QC, source, license, attribution, freshness, time window, missingness,
   model/estimated status, and uncertainty through storage, surfaces, UI, exports, alerts, and share
   artifacts.
5. **A map is never the only way in.** Map, table, and list remain outcome-equivalent. New
   visualization interactions need keyboard, text/data alternatives, focus, reduced-motion, and
   screen-reader review paths.
6. **Rights are source-specific.** First-party or project-authored data may use CC0 only when swelter
   or the publishing collective has authority. Third-party terms are retained. OpenAQ static
   publication fails closed without `source-license-ledger.json`.
7. **Keep write and read trust boundaries separate.** `ingest_server.py` is the authenticated node
   write path. `server.py` is the public GET-only read surface. Do not expose the former through the
   latter.

## Repository shape

- `src/swelter/`: models, validation/ingest, QC, calibration, aggregation, adapters, exports, API,
  authenticated ingest listener, public server, and CLI.
- `web/`: dependency-light HTML/CSS/ES modules, English/Spanish catalogs, service worker, and web
  tests. Current reading and Readings link history, distribution, evidence, map, table, and list.
- `firmware/`: reference sampling, buffering, and request signing. Signed/staged OTA is not
  implemented; never imply otherwise.
- `data/`: deterministic demo, calibration inputs, and explicitly labelled contextual/reference
  fixtures. Source terms are not inferred from directory placement.
- `infra/`: optional deployment reference. Static publication is a supported shape; a live
  authenticated ingest listener is a separate operator responsibility.
- `docs/adr/`: authoritative architecture-decision log. `docs/decisions/` is legacy link history.
- `docs/data-cards/`, `docs/audits/`, `docs/accessibility/`, and `docs/runbooks/`: provenance,
  conformance, responsible-technology, and operational evidence.

The current local store is a copyable directory centered on SQLite. Parquet/Arrow is only a future
`Store`-protocol extension, not a shipped backend. GitHub Pages publishes static artifacts; do not
describe it as a live ingest service.

## Work sequence

1. Inspect the current branch and preserve unrelated user changes.
2. Write observable acceptance criteria and map them to tests/review in
   [`docs/ACCEPTANCE-TEST-MAP.md`](docs/ACCEPTANCE-TEST-MAP.md).
3. Make the smallest coherent implementation that preserves the invariants.
4. Add or update an ADR for a load-bearing decision. New records use
   `docs/adr/NNNN-kebab-title.md` and the MADR-compatible structure in ADR 0000.
5. Update the changelog, API/schema docs, data cards, ACR, runbook, or audit artifact when the
   corresponding surface changes.
6. Run proportionate focused checks, then the complete gate before handoff.

## Verification

```console
uv sync
make verify
make web-test
git diff --check
```

`make verify` reproduces the complete local merge gate, including the web contract. `make web-test`
is the focused JavaScript command while iterating. Use `make help` and the workflow files for the
authoritative current target/job set; never put a test count in prose unless a check regenerates it.

For interaction changes, also run the available real-browser checks and record manual review
honestly. Automated axe/pa11y, catalog parity, screenshots, or DOM inspection do not prove a current
NVDA, VoiceOver, keyboard-only, magnification/reflow, or independent Spanish review. Issue
[#106](https://github.com/ChelseaKR/swelter/issues/106) tracks the current human signoff gap.

## Documentation and evidence rules

- Lead with outcomes, scope, evidence, and known limits. Remove claims that the implementation does
  not prove.
- External facts include a source, `Last verified` date, owner, and recheck trigger where relevant.
- Link to one source of truth instead of copying volatile counts or workflow details.
- Use the exact two-column standards ledger in the root README. Allowed states are `Applies`,
  `Applies — gap tracked in #…`, and `N/A — reason`.
- The vendored standards are pinned and byte-verified as documented in
  [`docs/STANDARDS-PIN.md`](docs/STANDARDS-PIN.md); do not edit them as local prose.
- Never claim an unperformed review, deployment, rollback, signature, publication, or release.
- Accepted ADR history is preserved. A reversal gets a new superseding ADR.

## Security and release boundaries

Follow [`SECURITY.md`](SECURITY.md) and [`docs/runbooks/operations.md`](docs/runbooks/operations.md).
Treat sensitive location exposure, forged ingest, source/license mismatch, and stale/misleading
publication as incidents. Do not print node keys, request signatures, raw precise coordinates, or
credential-bearing URLs.

The package metadata is preparing the `v0.2.0` release. An annotated `v0.1.0` tag exists, but
no GitHub Release has ever been published and no `v0.2.0` tag exists; do not invent either.
Release completion requires the exact tagged source to pass verification and the generated artifacts,
SBOM, signatures/provenance, consumer verification, deployment, and rollback evidence required by
the release workflow and [`DEFINITION_OF_DONE.md`](DEFINITION_OF_DONE.md).

The intentionally excluded repository/Pages-governance block is tracked in
[#105](https://github.com/ChelseaKR/swelter/issues/105). Do not present it as remediated. Suppression
retirement and code-quality follow-up is tracked in
[#107](https://github.com/ChelseaKR/swelter/issues/107).

Last verified: 2026-07-31. Recheck cadence: every release and whenever architecture, quality gates,
trust boundaries, or product rules change.
