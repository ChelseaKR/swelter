# Large-scale fixes (FIX-01 … FIX-13)

Date: 2026-07-01. Each item is net-new relative to `docs/ROADMAP.md` (incl. Phase 5) and
`docs/RESEARCH-ROADMAP.md` (R1–R11 / E1–E12); overlaps are cited and exceeded, not repeated.
Effort tiers: S ≈ a day · M ≈ 2–4 days · L ≈ 1–2 weeks · XL ≈ multi-week. Grounding for every item
is in [`01-deep-dive.md`](01-deep-dive.md).

---

## FIX-01 — Build the authenticated node write path the docs already claim

**Pitch.** Turn "the write path is authenticated per node" (README, audit F/STRIDE) from prose
into code: a minimal operator-side ingest listener with per-node keyed authentication.

**Why it matters.** This is the single largest docs-vs-code gap. Today ingest is file/CLI only
(`src/swelter/ingest.py`; `server.py` is GET-only), so the spoofing defence the security audit
cites does not exist in software — a real deployment would improvise it. For stewards (B-group
personas) it is the difference between a network they can actually run and a demo.

**Shape of the work.** A separate `swelter ingest-serve` listener (never merged into the public
read server — keep the read/write trust boundaries in different processes): HTTP POST of the
existing wide payload (`ingest._readings` already tolerates envelopes), authenticated by per-node
HMAC over `(node_id, timestamp, body)` with keys held in an operator-local file *outside*
`network.yaml` (keys must never enter the published config). Reuse `ingest.ingest()` +
quarantine unchanged; add an auth-failure quarantine reason. Firmware side: implement the
`Transport` seam in `firmware/src/store_and_forward.py` against it. ADR for key issuance/rotation
by the collective (a governance decision per `docs/governance.md`).

**Effort.** L. **Risks/dependencies.** Crypto-adjacent code needs a security review pass (gate
list in 04); must not add any person-bearing field (hard rule 1 — node key ids are node ids). The
alternative, if deferred: re-scope README/audit language honestly. Doing neither is the one wrong
option.

**Excellent looks like.** A node can be spoofed in a test only by holding its key; auth failures
land in `quarantine.jsonl` with a reason; STRIDE row "Spoofing" cites a test, not a sentence;
`make verify` covers the listener end-to-end offline.

---

## FIX-02 — Event-aware QC so real emergencies can't be flagged off the map

**Pitch.** Redesign spike/flatline QC so a wildfire-smoke front or a genuinely calm 0.0 µg/m³
stretch is never mislabeled and — critically — a QC-rejected value degrades to *visible
provisional*, not to absence.

**Why it matters.** `aggregate.py` drops QC-rejected values entirely (line ~231), while
`qc._SPIKE_THRESHOLD` (150 µg/m³ vs neighbour median) and `FLATLINE_RUN = 6` are hardcoded
heuristics. The worst hour of a smoke event is exactly when a flagged-then-dropped cell would
blank the map for the residents who most need it. This is a correctness risk to the mission, not a
tuning nicety.

**Shape of the work.** (a) Split QC verdicts into "physically impossible" (`range` — still never
mapped) vs "suspicious" (`spike`/`flatline` — mapped as provisional with the verdict carried into
cell properties, legend, and exports); adjust `models.QC_REJECTED` consumers (`aggregate.py`,
`qc.node_health`) and the dashboard legend accordingly. (b) Make thresholds per-network config
(`network.yaml: qc:` block parsed in `config.py`) with the current values as documented defaults.
(c) Corroboration logic: a "spike" seen simultaneously by ≥2 nodes in adjacent cells is an event,
not a fault. (d) Exempt low-value flatlines (PM at sensor noise floor) or scale flatline detection
by variance. Tests replaying a synthetic smoke-front and a calm-week fixture through
`scripts/gen_demo_data.py`.

**Effort.** L. **Risks/dependencies.** Threshold semantics should be sanity-checked against
published low-cost-sensor QC literature (SME gate); changes surface JSON shape → coordinate with
FIX-07 contract tests. Feeds EXP-13 (multi-hazard modes).

**Excellent looks like.** The smoke-front fixture keeps every affected cell visible (provisional,
labeled) through the event; the calm fixture produces zero false flatlines; thresholds are diffable
config with an ADR.

---

## FIX-03 — Calibration lifecycle: expiry, drift surveillance, honest fit statistics

**Pitch.** Implement the drift tracking the README describes in present tense: corrections age out,
post-deployment divergence is monitored, and the fit statistics stop flattering themselves.

**Why it matters.** `calibrate.py` computes `residual_std` in-sample with an `n` denominator and no
holdout; nothing anywhere checks a correction's age (`window_end` is stored and never consulted) or
watches calibrated-vs-raw divergence after deployment. The literature the research roadmap itself
cites (**[drift]**) says sensors wander within months. A 2025 correction silently applied in 2027
is precise and wrong — the exact failure mode the project exists to prevent.

**Shape of the work.** (a) `Correction` gains a documented validity horizon; `calibrate.apply()`
demotes an expired correction's output to provisional (new calibration-state suffix, e.g.
`…#stale`, so the label travels through store/API/export unchanged in mechanism). (b) In
`qc.health_report`, add per-node correction age + a residual-proxy: rolling spread between
calibrated values and the network/reference context where one exists. (c) In `fit_one`, use
`n − p` degrees of freedom, report a leave-one-out or time-split holdout RMSE alongside in-sample
`residual_std`, and require a minimum n well above 3 for publishable corrections (configurable).
Registry schema bump + regenerated `data/demo/corrections.yaml` in the same PR with an ADR (the
byte-for-byte replay test is the guard rail, per `CLAUDE.md`).

**Effort.** L. **Risks/dependencies.** Touches the reproducibility contract — must regenerate
committed registry deliberately. Distinct from research-roadmap R4 (heat-index trustworthiness)
and E4 (calibration with *no* reference); pairs with EXP-02 (automated reference feeds) and
EXP-05 (steward console). Statistical design deserves an SME sanity check.

**Excellent looks like.** No calibrated value is ever published from a correction older than its
horizon without a visible stale flag; the registry publishes holdout error, not just in-sample;
`docs/calibration.md` matches the code (audit D7).

---

## FIX-04 — Statistically sound uncertainty through aggregation, and a NowCast option

**Pitch.** Make published cell uncertainty a defensible standard error, give the exposure layer an
uncertainty statement, and offer EPA NowCast as a computed alternative rather than only a caveat.

**Why it matters.** `aggregate.py:261` publishes the *mean* of member 1σ values as cell
uncertainty (wrong aggregation of independent-ish errors); `_exposure_cells` sets
`uncertainty=None`; AQI uses an hourly mean against 24-hour breakpoints. Research-roadmap R5 makes
the caveat travel; this fix makes the *number* right — the deeper cut for the researcher/skeptic
audiences (E1-res, D2) whose trust is the moat (ROADMAP 5.2).

**Shape of the work.** In `aggregate.aggregate()`: cell σ = combined standard error
(σ_pooled/√n with a documented within-cell correlation caveat), publish both per-value mean σ and
cell-mean σ under distinct names so no consumer silently reinterprets; add a NowCast computation in
`models.py` beside `pm25_aqi()` (needs ≥3 recent hours — emit only when the store has them) surfaced
as `aqi_window: "nowcast"` variants in surface/API/exports; exposure cells state which component
bounds them. Update `docs/api.md` + the R11 data dictionary when that lands.

**Effort.** M. **Risks/dependencies.** Consumer-visible schema additions → FIX-07 contract tests
and R11 sequencing. Formulas cite EPA documentation; keep the non-regulatory framing.

**Excellent looks like.** A statistician reading `/api/surface.json` can reproduce every published
σ from the export; NowCast and hourly-mean AQI never masquerade as each other in any surface.

---

## FIX-05 — License provenance: stop exporting third-party data as CC0

**Status: done.** `LICENSE` constants added next to each source's `ATTRIBUTION`
(`sources/openaq.py`, `sources/sensor_community.py`, `sources/openmeteo.py`); `export.py` gained
`DEFAULT_LICENSE = "CC0-1.0"` and `license`/`attribution` kwargs on `to_json()`, `to_csv()` (as
standards-compliant per-row `data_license` / `data_attribution` columns), and `summarize()`; the CLI's `export`
subcommand grew `--license`/`--attribution` flags (default CC0-1.0) and `fetch` now reports the
real fetched source's license in its summary banner; `pages.yml` computes the license per branch of
its fallback chain and writes it into each surface's `DATA-LICENSE` instead of always copying the
repo's CC0 one; `docs/api.md` documents the mixed-store and upstream-provider cases. The
`Observation` model and store schema are untouched — license is threaded as an export-time
parameter, not a stored field. See `roadmap/fix-05-license-provenance-stop-exporting`.

**Pitch.** Per-source license metadata that travels with observations, so exports of fetched
OpenAQ (provider-specific terms) / Sensor.Community (ODC-DbCL-1.0) data stop inheriting the
hardcoded CC0 banner.

**Why it matters.** `export.py` hardcodes `"license": "CC0-1.0"` (line 79) and
`DATA_LICENSE_LINE`; `pages.yml` copies the CC0 `DATA-LICENSE` beside `export.csv` built from
third-party sources. This is a live licensing error on the public demo and a candor problem for
a project whose brand is provenance. CC0 is true only for community-network observations.

**Shape of the work.** Add a source/license registry (per source adapter constant); thread a
`license`/`attribution` field through `ServerContext` and the export/baking paths
(`cli._write_web_sample` already carries `attribution` — extend the pattern to `_export`,
`export.to_json/to_csv` headers, and the Pages workflow's DATA-LICENSE handling: write a
per-surface `data-license.txt` naming the actual terms). Keep CC0 as the default for native
network stores. Document the mixed-store case (fetched + native) honestly in `docs/api.md`.

**Effort.** M (S for the export surface, M with the Pages workflow and docs).
**Risks/dependencies.** None technical; small legal-review gate on the exact attribution wording.
OpenAQ's per-location provider-license interaction with downstream reuse deserves one careful
paragraph and a provenance ledger before its mixed-provider export can claim full compliance.

**Excellent looks like.** Every export artifact names the license of what is actually in it; the
live demo's `/sensors/` page never claims CC0 over Sensor.Community data; a test asserts the
license field varies by source.

---

## FIX-06 — Bilingual machine-readable surfaces: the alerts feed speaks Spanish

**Status: done.** A server-side gettext catalog (`src/swelter/locales/alerts.pot`, complete EN/ES
PO files, compiled MO files, and `MACHINE_TRANSLATED = True` in `src/swelter/i18n_alerts.py`) backs
`Alert.headline(lang)` / `headline_es`, `alerts.json`'s `headline_es` + `note_es` +
`"translation": "machine"`, and `AlertFeed.to_atom(lang="es")`. `cli._write_web_alerts` and
`server.py`'s `/api/alerts.es.xml` route both bake/serve the Spanish Atom feed (`xml:lang="es"`,
`hreflang` alternate link, a `<generator>` machine-translation note); the dashboard's subscribe UI
links to it (`web/i18n` `aa-es-feed` / `aa-es-feed-note`, kept at EN/ES parity).
`scripts/gettext_catalog_check.py` re-extracts the Python messages, gates key/placeholder parity and
non-empty translations, and byte-checks both compiled MO catalogs; dashboard parity remains in
`scripts/i18n_parity.py`.

**Pitch.** Extend EN/ES parity past the dashboard catalogs into the generated artifacts —
`alerts.json` headlines, the Atom feed, health/coverage notes — via per-language feed variants.

**Why it matters.** `alerts.Alert.headline()` is documented as English-only; `web/alerts.xml` is
the exact artifact a Spanish-first resident (persona A3) would subscribe to in a feed reader. The
i18n gates (G1/G3/G6/G12, `Makefile` target `i18n`) currently guarantee parity only for
`web/i18n/*.json`. Research-roadmap R1/R2/R3 cover dashboard guidance strings and catalog gates;
this fix covers the *feed and JSON note strings* those items don't touch — the language-justice
obligation (**[language]**) applies to syndication too.

**Shape of the work.** Headline/note templates live in the canonical server-side gettext catalog
(this fulfills the "Python emits localized strings → gettext/PO gates" clause and aligns with the
portfolio-wide dict→gettext Phase 1);
emit `alerts.es.xml`/`alerts.json` with `headline` + `headline_es` (or `?lang=` on the live
routes and dual baked files in `cli._write_web_alerts`); `hreflang`-style feed links in the
dashboard's subscribe UI. `scripts/gettext_catalog_check.py` owns extraction and compiled-catalog
verification.

**Effort.** M. **Risks/dependencies.** Translation quality needs the native-ES reviewer the i18n
migration memo already flags as an open role — machine-drafted ES goes out only labeled as such,
or waits (honesty gate). Coordinates with R1's guidance-string work to avoid double templates.

**Excellent looks like.** A resident whose reader is subscribed to the ES feed gets Spanish
headlines with identical data; the parity gate fails CI if a feed key exists in EN only.

---

## FIX-07 — Test the dashboard: a JS harness and a Python↔JS surface contract

**Pitch.** Put the 2,642-line `web/app.js` under test: unit tests for its pure logic, a JSON-schema
contract shared with the Python emitters, and a promoted (blocking) browser smoke.

**Why it matters.** The dashboard is the primary resident surface and the repo's largest untested
body of code; the Python suite (~205 tests) never executes a line of it, and the only browser check
(`ci.yml` `a11y-advisory`) is allowed to fail. Regressions in `describe()`, `convert()`,
`trendLine()`, or locale fallback would ship silently today.

**Shape of the work.** (a) Extract-and-test: `app.js`'s pure functions (unit conversion,
category ordering, trend/contrast lines, `t()` fallback) are already function-scoped — add a
`web/package.json` + `node --test` (or vitest) run as a new CI job; keep the no-framework browser
architecture and vendor the generated MessageFormat runtime so the page makes no package-network
request. (b) Author JSON Schemas for `sample-surface.json`,
`sample-health.json`, `alerts.json` and validate them from *both* sides: a Python test validates
emitter output, a JS test validates fixture parsing — the schema is the contract FIX-04/FIX-02
changes then evolve deliberately. (c) Promote a minimal Playwright/pa11y smoke (page loads, three
views render, language switch works) from advisory to blocking with pinned versions.

**Effort.** L. **Risks/dependencies.** Adds a locked Node test/build toolchain and a pinned
MessageFormat package whose generated ESM runtime is vendored into the static artifact. The browser
still makes no package-network request. `CLAUDE.md` historically forbade agent modification of
`web/`; this work landed through the maintainer-authorized portfolio sweep.

**Excellent looks like.** A deliberate surface-schema change fails two tests (Python emitter + JS
consumer) until both sides move; dashboard logic coverage is measured; the browser smoke is
merge-blocking and quick (<2 min).

---

## FIX-08 — Server survivability on a Pi during a heat wave

**Pitch.** Request timeouts, a materialized surface cache, and conditional GETs so the
single-threaded server can't be stalled by one slow client or ground down by recomputation at
peak demand.

**Why it matters.** `server.py` builds a plain `HTTPServer` with no socket timeout — a single
slow-loris connection blocks everything (DoS row in audit F underestimates this) — and every
surface/alerts request re-aggregates the entire store (`ctx.store.all()`). Peak load coincides
with peak need: a heat emergency.

**Shape of the work.** Set `Handler.timeout` and wrap reads defensively; cache the aggregated
`Surface` keyed on store file mtime/row count (invalidate on change; the store is append-only so
this is cheap and correct); precompute gzip for the big three payloads; add
`ETag`/`If-None-Match` (content hash of the cached artifact) so the 60 s `Cache-Control` gains
304s. Keep single-threaded SQLite discipline documented in ADR 0005 — this is caching, not
concurrency.

**Effort.** M. **Risks/dependencies.** Cache invalidation must respect `swelter rebuild`
(`drop_calibrated()` changes rows without growing them — key on `total_changes`/mtime, not count
alone). Pairs with FIX-09; partially subsumed for static deployments by EXP-04.

**Excellent looks like.** A stalled client cannot delay other requests beyond the timeout; steady-
state surface requests are O(cache hit); load test on Pi-class hardware documented with numbers in
`docs/ARCHITECTURE.md`.

---

## FIX-09 — A store that survives its second summer

**Pitch.** Incremental hourly rollups persisted in SQLite, windowed store reads, and a documented
retention/archival policy, so a season of 5-minute data from 150 nodes stays fast and copyable.

**Why it matters.** All aggregation is whole-history in memory (`aggregate.aggregate` over
`store.all()`); `store.read()` materializes full lists; nothing partitions or ages data. At the
README's own example scale (177k observations/week) a year is ~9M rows re-scanned per request
(pre-FIX-08) and re-aggregated per pipeline run. The "folder you can copy" property is the thing
to preserve while making growth survivable.

**Shape of the work.** Add a derived `rollups` table (cell/hour/parameter, calibrated and
provisional lanes) maintained incrementally at ingest/calibrate time and rebuilt by
`swelter rebuild`; make `aggregate` read rollups with a raw-scan fallback; add
`Store.read_window()` streaming variants; write the retention ADR (raw is immutable evidence —
archive by month into sibling `observations-YYYY-MM.db` files that Datasette still opens; never
delete). Supersede `docs/adr/0001-sqlite-and-files-store.md` with a follow-on ADR rather than
editing history.

**Effort.** XL. **Risks/dependencies.** The rollup lane must preserve every trust invariant
(calibrated-preferred, provisional labeling, method/reference provenance strings from
`aggregate.py:214-246`) — property tests comparing rollup output to full recompute are the
acceptance bar. Do after FIX-04 (schema of what a cell publishes) to avoid rolling up twice.

**Excellent looks like.** Rollup-vs-recompute equivalence proven in tests on the demo fixtures; a
simulated year of data serves the surface in interactive time on a Pi; the archive folder remains
a copyable, Datasette-openable set of files.

---

## FIX-10 — Strict config: `swelter doctor` and no silently-ignored safety knobs

**Status: done.** `config.config_concerns()` (errors/warnings against the raw parsed doc) and the
`swelter doctor` subcommand shipped; `serve`/`demo`/`fetch` print warnings on load; unknown
`alert_thresholds` keys are a hard error at `doctor`/load time (ADR 0015). See
`src/swelter/config.py`, `src/swelter/cli.py`, `tests/test_config.py`, `tests/test_cli.py`.

**Pitch.** Validate `network.yaml` loudly — duplicate/empty node ids, unknown keys, and above all
`alert_thresholds` typos that today silently revert danger floors to defaults.

**Why it matters.** `alerts._resolve_thresholds` merges only known keys and drops the rest —
a collective that writes `heat_index: 37` (instead of `heat_index_c`) believes it lowered its
alert floor and did not. That is a silent safety failure in the exact file communities are told to
edit (`docs/ADD-YOUR-NEIGHBORHOOD.md`, Phase 4). `config.parse_config` likewise accepts duplicate
and empty `node_id`s that would merge distinct sensors into one cell identity.

**Shape of the work.** `load_config` gains an errors/warnings pass (unknown top-level and
threshold keys, duplicate/empty ids, out-of-range lat/lon, `location:` values other than
coarse/precise, calibration windows referencing unknown nodes/monitors); a `swelter doctor`
subcommand in `cli.py` prints the report (reusing the `label_concerns()` pattern) and exits
nonzero on errors; `serve`/`demo`/`fetch` print warnings on load. Unknown `alert_thresholds` keys
become a hard error, not a drop.

**Effort.** S/M. **Risks/dependencies.** Must stay lenient where leniency is safety (typo'd
`location` already fails safe to coarse — keep that, but warn). Zero schema changes.

**Excellent looks like.** Every mistake a first-time community editor can plausibly make in
`network.yaml` produces a plain-language, bilingual-ready message naming the line and the fix;
tests cover each rule.

---

## FIX-11 — Minimum honest observability: run manifests and structured logs

**Pitch.** Give the README's "structured logs and metrics" claim a real, dependency-free
implementation: JSON-lines event logs and a per-run pipeline manifest artifact.

**Why it matters.** `server.py` suppresses request logs with a comment pointing at structured
logging that doesn't exist; pipeline stages report via ad-hoc stderr banners (`cli._err`). A
steward debugging "why is this cell provisional today" at 2 a.m. (the README's own scenario) has
no machine-readable trail. The vendored `docs/standards/OBSERVABILITY-STANDARD.md` presumably
expects more than this repo currently does (unverified against the standard's specifics — read it
when implementing).

**Shape of the work.** A small `swelter/obs.py` (stdlib `logging` with a JSON formatter): counters
per stage (payloads accepted/quarantined, corrections applied/skipped-stale, cells
built/provisional) emitted as one `run-manifest.json` per pipeline invocation into the store
folder (it is already the audit-evidence folder); optional request logging in `server.py` behind a
flag (method, path, status, ms — never client-identifying detail beyond what stdlib exposes; do
not log IPs to honor the no-person-records posture). Wire the manifest into `/api/health.json`.

**Effort.** M. **Risks/dependencies.** Log content must be reviewed against hard rule 1 (no
person-shaped data — that includes IP retention policy stated explicitly). Enables FIX-03 drift
metrics and EXP-05.

**Excellent looks like.** Every published surface can name the run that built it; "why is this
value provisional" is answerable from artifacts alone; a test asserts manifests are deterministic
for the demo replay.

---

## FIX-12 — A docs-figures gate: numbers in prose that CI re-proves

**Pitch.** Mechanically verify the countable claims the docs make (test counts, node counts,
correction counts, route lists) so documentation drift fails CI instead of accumulating.

**Why it matters.** Observed today: `CLAUDE.md` claims 62 tests (~205 exist); `CLAUDE.md` and
`docs/ROADMAP.md` disagree about the demo registry size (36 vs 300 corrections — the
`SWELTER_DEMO_NODES` knob explains it but neither doc says which figure is current); README
carries a duplicated paragraph (lines ~81–92). For a portfolio whose pitch includes "audit-as-
artifact" documentation, drift is a credibility tax. This extends the existing `Last verified:`
convention from dates to *checkable facts*.

**Shape of the work.** `scripts/docs_figures_check.py` in the `verify` chain: a small manifest of
(doc, regex, source-of-truth command) pairs — pytest collect count vs `CLAUDE.md`, registry entry
count vs `data/demo/corrections.yaml`, server route list vs `docs/api.md` table, i18n key count vs
catalogs. Also a plain duplicate-paragraph lint for the README. Fixing the current mismatches
happens in the maintainer's flow (README/`CLAUDE.md` are agent-do-not-modify).

**Effort.** S. **Risks/dependencies.** Keep the manifest tiny and high-signal or it becomes its
own maintenance burden; figures that legitimately float (demo node knob) get ranges or are
excluded with a comment.

**Excellent looks like.** The 62-vs-205 class of drift is structurally impossible; each gated
figure names its source of truth; the gate has never cried wolf (no flaky rules).

---

## FIX-13 — Verifiable integrity: re-check content hashes, chain daily digests

**Status: ✅ Done** (2026-07-03)

Shipped as `swelter verify-archive` (`src/swelter/integrity.py`): `SqliteStore.iter_rows()`
exposes the persisted `content_hash` alongside each reconstructed row; `verify_rows()` recomputes
and compares it per row; `daily_digests()` groups stored hashes by UTC day (sorted, so digest
order does not depend on write order) into one canonical SHA-256 per day, then chains days
oldest-first (`chain = sha256(prev_chain + date + day_digest)`, seeded with the empty string) so
a single-byte mutation anywhere in history changes every chain value after it; `write_digests()`
publishes `digests.jsonl` in the store folder, byte-for-byte reproducible across runs (checked by
`make demo` replay determinism). The CLI recomputes + compares, prints a human or `--json` report,
exits nonzero on any mismatch, and only (re)writes `digests.jsonl` on a clean verify. The current
head and last verified day ride along in `/api/health.json` under `integrity`, read cheaply from
`digests.jsonl` (`qc.health_report`'s `store_dir` parameter) rather than re-hashed per request.
Procedure documented in `docs/ARCHITECTURE.md`; the health field in `docs/api.md`. No signing —
key custody stays a governance question, deferred per the pitch. Tests: `tests/test_integrity.py`
(round-trip, tamper detection at both the library and CLI layer, digest/head determinism,
chain-changes-on-earlier-day-edit).

**Pitch.** Make the stored `content_hash` earn its keep: an integrity-verification command and a
per-day hash chain that makes the archive tamper-*evident*, not just tamper-resistant.

**Why it matters.** `store.py` writes a SHA-256 per row and nothing ever re-reads it; audit F4
("immutable and content-hashed") is enforced only at write time. The misuse the ethics audit
names is *misrepresentation* of the record — a checkable chain turns "trust the folder" into
"verify the folder", which is also the missing substrate for citable snapshots
(research-roadmap E3 gets its verifiable digest from this, rather than duplicating it).

**Shape of the work.** `swelter verify-archive`: recompute per-row hashes against stored values;
compute a canonical daily digest (sorted row hashes per UTC day → one SHA-256) and a chained head
hash written to a `digests.jsonl` in the store folder; document the verification procedure in
`docs/ARCHITECTURE.md`. Publish the current head in `/api/health.json`. No signing yet (key
management is a governance question — defer, honestly, to an ADR).

**Effort.** M. **Risks/dependencies.** Canonicalization must be deterministic across platforms
(reuse `models.content_hash` JSON conventions). Feeds E3 (DOI snapshots) and the funder-evidence
story (E8) without overlapping either.

**Excellent looks like.** Any single-byte mutation of `observations.db` history is detected by a
command a journalist can run; the digest chain is reproduced byte-for-byte by `make demo` replays.
