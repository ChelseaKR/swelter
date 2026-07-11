# Deep dive — current state as actually read

Date: 2026-07-01. Basis: full read of `src/swelter/`, `web/`, `firmware/src/`, `scripts/`,
`tests/`, `.github/workflows/`, `infra/cdk/`, and `docs/` at commit `3db161a` (working tree clean).

## What swelter is, in one paragraph

A community-owned heat and air-quality sensing stack: ESP32-class nodes
(`firmware/src/main.py`, `sampler.py`, a genuinely careful flash-backed store-and-forward buffer in
`firmware/src/store_and_forward.py`) feed a one-way pipeline — `ingest.py` (validate/explode/
quarantine) → `store.py` (append-only SQLite keyed `(node_id, timestamp, parameter, calibration)`,
`INSERT OR IGNORE`) → `calibrate.py` (pure-Python OLS against co-located reference monitors,
versioned YAML registry, byte-for-byte reproducible at 6 dp) → `qc.py` (range/spike/flatline
labels, gap detection, node health, coverage-equity) → `aggregate.py` (published-grid hourly
rollups, calibrated-preferred, provisional-labeled, plus the derived compound `exposure` layer of
ADR 0009) → `server.py`/`api.py` (stdlib GET-only HTTP: SensorThings 1.1 subset, GeoJSON surface,
alerts feed, cooling centers, CSV/JSON export) → a framework-free bilingual WCAG 2.2 AA dashboard
(`web/index.html` + 2,642-line `web/app.js`, EN/ES catalogs in `web/i18n/`). Three real-data
adapters (`sources/openaq.py`, `sources/openmeteo.py`, `sources/sensor_community.py` over a shared
retrying `sources/_http.py`) drive a daily-refreshed GitHub Pages live demo
(`.github/workflows/pages.yml`). Users: frontline residents (including Spanish-first,
screen-reader, and elderly users), the hosting collective's stewards, health officials,
researchers/journalists, and funders — the roster `docs/USER-RESEARCH.md` formalizes.

## What is genuinely strong

- **The trust invariants are structural, not aspirational.** `calibration` is never empty
  (`models.py`), calibrated and raw are distinct store rows, `aggregate.py` never averages them
  together, and `calibrate.apply()` refuses to apply a humidity-aware PM correction when co-timed
  humidity is missing rather than silently zeroing the term (`calibrate.py:366-370`). This is the
  rare codebase where the README's ethics claims mostly compile.
- **Privacy as a single code path.** `config.public_location()` is the only coordinate source
  downstream code reads; `snap_to_grid()` is deterministic; `label_concerns()` (`config.py`)
  heuristically warns on address/phone/email-shaped node labels. The DPIA threat model matches the
  code.
- **Reproducibility discipline.** Fixed-precision coefficients with `-0.0` collapse
  (`calibrate._round`), deterministic demo data, data-derived (not wall-clock) alert-feed
  timestamps (`alerts.py`), and `make rebuild` from immutable raw.
- **The gate is real.** `make verify` = fmt + ruff + mypy-strict + 12-check structural a11y + four
  mechanical i18n gates + pytest with `--cov-fail-under=90` branch coverage; CI mirrors it exactly
  and adds pip-audit, gitleaks, CodeQL, firmware byte-compile + tests, and an advisory real-browser
  pa11y pass. ~205 test functions across `tests/` (217 collected nodes per the pytest cache).
- **Accessibility depth beyond the checkbox**: map/table/list as three equal views, unit toggle,
  text-size and contrast controls, `aria-live` regions, keyboard shortcuts with a defeat toggle,
  honest offline indicator, per-node health detail (`web/index.html`, recent commits #34–#39).

## Structural debt and gaps actually observed

These are observations from the code, cited; the fix/expansion files turn them into proposals.

1. **Docs claim capabilities the code does not have.** README ("the write path is authenticated
   per node") and audit F's STRIDE table assert an authenticated node→ingest boundary, but no
   network ingest endpoint exists anywhere — `ingest.py` is file/CLI-only, `server.py` is GET-only,
   and the firmware's transport is an injected abstraction. Similarly README's drift-tracking claim
   ("a node whose residuals widen past a bound is flagged for service") has no implementing code:
   nothing monitors post-fit residuals or correction age. README also promises "structured logs and
   metrics"; `server.py` disables request logging with a comment pointing at structured logs that
   don't exist, and the pipeline emits only `print`-to-stderr banners (`cli.py:_err`).
2. **License propagation is wrong for fetched data.** `export.py` hardcodes `"license": "CC0-1.0"`
   (line 79) and the CC0 banner line into every export, but `swelter fetch` pulls OpenAQ (CC BY
   4.0) and Sensor.Community (CC BY-SA 4.0) data through the same exporter, and `pages.yml` then
   publishes that `export.csv` beside a copied CC0 `DATA-LICENSE`. Attribution strings exist on the
   dashboard, but the machine-readable export mislabels third-party-licensed observations as CC0.
3. **QC can erase the event it exists to catch.** `aggregate.aggregate()` drops QC-rejected values
   entirely ("never place a QC-rejected value on the map, even as provisional",
   `aggregate.py:231-232`), while `qc._series_flags` flags any point departing >150 µg/m³ from its
   two neighbours as `spike` and any 6 identical consecutive values as `flatline`
   (`qc.py:34-44,77-87`). A sharp wildfire-smoke onset edge or a calm stretch reading a genuine
   0.0 six hours running is plausibly mislabeled — and then vanishes from the map rather than
   showing as provisional. Thresholds are hardcoded, not per-network config.
4. **Statistical looseness under the honesty banner.** `residual_std` is in-sample with an `n`
   (not `n−p`) denominator and no holdout (`calibrate.fit_one`); cell uncertainty is the *mean* of
   member sigmas rather than a standard error (`aggregate.py:261`); the exposure layer publishes no
   uncertainty at all; AQI is computed from an hourly mean against 24-hour breakpoints (labeled via
   `aqi_window`, and research-roadmap R5 propagates the caveat, but no NowCast alternative exists).
5. **Whole-history recomputation per request.** Every `/api/surface.*`, `/api/alerts.*` hit
   re-runs `aggregate.aggregate(ctx.store.all(), …)` over the full store (`server.py:135-158`);
   there is no materialized rollup, no ETag/304, gzip is recomputed per response, and
   `HTTPServer` has no socket timeout — one slow client can stall the single thread exactly during
   a heat-wave traffic spike on a Pi-class host.
6. **The dashboard is the largest untested surface.** `web/app.js` (2,642 lines: i18n, unit
   conversion, trend/contrast lines, briefs, alerts, health rendering) has zero automated tests —
   the suite is Python-only, and the only browser check is the advisory, allowed-to-fail pa11y job.
   There is no schema contract between the Python-emitted surface/health/alerts JSON and what
   `app.js` expects.
7. **English-only machine-readable resident surfaces.** `alerts.Alert.headline()` is documented as
   "a plain-language, English summary line"; the baked `web/alerts.json`/`alerts.xml` and the Atom
   feed a Spanish-first resident would subscribe to are EN-only, despite the EN/ES parity gates on
   the dashboard catalogs. The i18n equity stops at the feed boundary.
8. **Config trusts the operator too much.** `config.parse_config` accepts duplicate or empty
   `node_id`s; `alerts._resolve_thresholds` silently *discards* unknown threshold keys
   (`alerts.py:188-194`), so a typo'd `alert_thresholds:` entry quietly reverts a collective's
   danger floor to the default — a safety-relevant silent failure.
9. **Doc-figure drift.** `CLAUDE.md` says "62 tests"; ~205 exist. `CLAUDE.md` says the demo
   registry is 36 corrections / 12 nodes; `docs/ROADMAP.md` says 300 corrections / 100 co-located
   nodes ("node count is a knob"). README repeats the Sensor.Community bullet verbatim twice
   (README lines ~81–92). Small individually; collectively they erode the "docs are evidence"
   posture. (Per `CLAUDE.md`, README/src/web/tests are do-not-modify from an agent flow — these are
   flagged here, not fixed.)
10. **Snapshot-only live demo.** `cmd_fetch` deletes the store each run (`cli.py:487`), so the
    Pages demo never accumulates history — the time slider on real data covers at most one fetch
    window, and the OpenAQ path collapses to a single stamped hour (`openaq._to_snapshot`). The
    store's idempotent key was *built* for accumulation and is unused for it.
11. **Two API implementations, one real.** `infra/cdk/lambda/handler.py` is an honest stub of the
    server routes; if ever completed it duplicates `server.py` dispatch by hand — a drift seam to
    design away rather than grow.

## Strategic position inside the portfolio

swelter is the portfolio's physical-world/data-pipeline showpiece: it demonstrates
calibration-as-trust, privacy-by-construction, descriptive-not-ranking equity surfaces
(`qc.coverage_equity` and its explicit B4 refusal), bilingual-by-CI, and funder-evidence candor
(`docs/FUNDER-EVIDENCE-PACK.md`) in one repo. It shares the versioned-data + audited-a11y
discipline with the GTFS/fare-policy siblings the README names, and it is the repo where the
portfolio's "honesty as a feature" claim is most load-bearing — which is exactly why the
docs-vs-code gaps above (write-path auth, drift tracking, export licensing) matter more here than
they would elsewhere: this repo's differentiator *is* that its claims check out. The highest-value
next layer is therefore not more features but making the trust story true end-to-end at scale:
close the claimed-but-absent seams, make the statistics as honest as the labels, and let the live
demo accumulate the longitudinal record that the heat-island mission actually needs.
