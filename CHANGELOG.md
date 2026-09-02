# Changelog

All notable changes to swelter are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the public API/data schema follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html) as scoped in
[`docs/VERSIONING.md`](docs/VERSIONING.md).

## [Unreleased]

### Added

- **The planner is discoverable. It was live and crawlable with no canonical, no social
  metadata and no sitemap entry.** `/planner/` was added to the pa11y URL list and to nothing
  else, so every discovery surface missed it: `KNOWN_ROUTES` gates `canonical_url`, the `page`
  subcommand and `write_sitemap` alike, and all three of them reach only source-aware data
  routes. `web/` is uploaded whole, so the page deployed and served fine while sharing a link
  to it previewed as a bare URL.

  `pages_seo.py` gains `STATIC_ROUTES` and `write_static_page_metadata` for a published route
  that is not a data surface. The planner reads no readings, so it gets a canonical, icons,
  `robots`, Open Graph and a Twitter card, and deliberately **no JSON-LD**: the only graph this
  project emits is a `Dataset` describing readings and their licence, and a page that publishes
  none must not claim one. It also keeps the title and description it already ships with rather
  than having them rewritten, because a static page's copy is truthful in source, whereas a data
  surface's is only truthful once the deployed fallback is known. Nothing new is written about
  what the planner does; the card repeats the page.

  The sitemap is now derived from the route list rather than maintained beside it, so the next
  route cannot be added to one and forgotten by the other, and `make seo` validates the planner
  template as well as the dashboard's.

  Observed failing four ways: `/planner/` dropped from the published routes; the planner
  canonicalised to the bare `chelseakr.github.io` origin, which is a different site and one all
  six project sites on that origin would claim; the `Dataset` graph attached to the planner; and
  the planner template stripped of its marker block, which fails `make seo` with exit 2.

  Unchanged and recorded rather than "fixed": there is still no `robots.txt`. `check_template`
  fails the build if one appears under `web/`, because a crawler reads `/robots.txt` only at the
  origin root and this project repository cannot publish `https://chelseakr.github.io/robots.txt`.
  Page-level `robots` metadata remains the crawl control, as that check already says.

- **Purpose-first project planner.** A no-account decision guide at `/planner/` asks six bounded,
  non-personal questions and recommends public data, a governance or stewardship pause, a bounded
  pilot, or staged operation. “Do not deploy” is a first-class outcome; raw readings cannot unlock
  expansion without a calibration path. Plans are calculated in the browser and can be copied or
  printed without storing or transmitting answers ([ADR 0042](docs/adr/0042-purpose-first-project-planner.md)).
- **A fallback source now announces itself in the deploy run, not just the log ([#180](https://github.com/ChelseaKR/swelter/issues/180)).**
  The `demo` workflow's source ladder (OpenAQ → CAMS → synthetic for page 1; Sensor.Community →
  page 1's artifact for `/sensors/`) is a supported, non-error outcome by design (ADR 0034), so the
  run exits 0 and stays green whether or not a route reached its first-choice source. That is
  correct for a transient outage and wrong for a persistent one: both physical-sensor routes were
  dark simultaneously for at least four days (2026-08-16 to 2026-08-19) and every run in that window
  reported success, with nothing but a workflow log recording it. Each route now emits a
  `::warning::` GitHub Actions annotation, visible in the run summary, whenever the source that won
  is not the route's declared first choice — generated from which fallback branch actually ran,
  not a separately maintained flag, so the claim cannot drift from the code that makes it. This is
  a visibility floor, not the trend-tracking sketched in #180 (comparing the last N runs to flag a
  persistent pattern); that remains a possible follow-up.
- **`range_note` in the published data dictionary.** Each entry in `/api/schema.json`'s `parameters`
  block now carries a `range_note` beside `valid_min`/`valid_max`: a string when the bound needs
  explaining, `null` when it does not. A bound says which values swelter will treat as measurements,
  so a surprising one has a reason a consumer should not have to guess at —
  `humidity_pct.valid_min` is `2.0` rather than `0.0` because a dead capacitive probe reports
  exactly `0.0` or `1.0` %RH (ADR 0043). Additive and generated from `models.PARAMETERS` like the
  rest of the dictionary, so it cannot drift from the bounds the pipeline runs on;
  `DATA_SCHEMA_VERSION` stays at 2.
- **Event chronicle generator.** `swelter chronicle --from <ISO> --to <ISO>` composes the aggregated
  surface, `qc.detect_gaps`, and `qc.coverage_equity` into a citable post-event Markdown chronicle:
  Danger/Extreme-Danger and compound-exposure cell-hours per published cell, the calibrated-vs-
  provisional coverage share carried in the headline, and an always-present "what the network could
  not see" section. Descriptive counts only — no health-outcome attribution and no neighborhood
  ranking ([ADR 0027](docs/adr/0027-event-chronicle.md)).
- **Calibration-drift surveillance in the health report (FIX-03, safe subset).** `qc.health_report`
  gains an optional `calibration` block — present only when a correction registry is supplied —
  driven by a new pure helper `qc.correction_ages`. For each fitted correction it reports the
  version, its co-location `window_end`, the age in days against the latest observation, and an
  `aging` flag once the age passes a documented drift horizon (default 365 days, cited to the
  `docs/RESEARCH-ROADMAP.md` **[drift]** literature). Surfaced on `/api/health.json`, in `swelter qc`
  (JSON plus a summary line), and threaded through `swelter status`; documented in the Python↔JS
  health schema. Descriptive and read-only: it finally consults `window_end` (stored since Phase 2,
  never read until now) but changes no calibrated value, demotes nothing to provisional, and is never
  a ranking of neighborhoods (hard rule #3). `calibrate.apply()` and `data/demo/corrections.yaml` are
  untouched, so the byte-for-byte calibration replay is unaffected
  ([ADR 0028](docs/adr/0028-calibration-drift-surveillance.md)).
- **Event-aware QC on every surface (F-22).** A suspicious spike or flatline reading is now shown
  visible, provisional, and *flagged* instead of dropped, so the worst hour of a real smoke front or
  pollution excursion is never blanked off the map for the residents who most need it. Each cell's
  `qc_flags` travel to every surface — the surface record and map GeoJSON, the CSV/JSON export, the
  `/api/schema.json` data dictionary, and the dashboard legend, table, evidence panel, and Now view —
  so a cell that is provisional *because it looked suspicious* reads distinctly from one that is
  merely uncalibrated. Physically impossible (`range`) and absent (`missing`) values stay unmapped;
  no value is ever promoted to calibrated
  ([ADR 0029](docs/adr/0029-event-aware-qc-visible-provisional.md)).

### Changed

- **`make verify` is green end to end again: OSV-Scanner is pinned at 2.5.1.** `security-osv`
  asserts the installed binary matches `OSV_SCANNER_VERSION` before it scans anything, and the pin
  had drifted to a build no longer current, so the gate failed at its own version assertion for
  anyone with a present-day install. That failure is environmental, it says nothing about the
  dependency graph, and a red that everyone learns to read as benign is a red nobody reads.

  Checked before bumping rather than after: 2.5.1 scans the same two lockfiles (`uv.lock`, 50
  packages; `web/package-lock.json`, 318 packages) and reports **no issues**, so the older pin was
  not concealing a finding. `osv-scanner.toml` still ignores nothing, so every advisory either
  version reports still fails the gate. The binary is checksum-verified in CI and at release; the
  new `sha256` is `f9f25499a2c8cc367b3af45df2ea7eeca7fbccceab9c35079968f4b3652194be`, taken from
  the upstream `osv-scanner_SHA256SUMS` for `v2.5.1` and confirmed against the downloaded artifact.
  Break-tested: a deliberately wrong `OSV_SCANNER_VERSION` fails `make security-osv` with exit 2,
  and the correct one passes with exit 0.
- **The published site says what data it is actually showing.** The README led with a live-map link
  and a source table describing what the pipeline *supports*; it said nothing about which source was
  reaching the deployment. Since at least 2026-08-16 that has been Copernicus CAMS **model** output
  on both routes — OpenAQ failing its per-location license-ledger check
  ([#179](https://github.com/ChelseaKR/swelter/issues/179)) and Sensor.Community refusing on the
  cached store above. The per-artifact rights evidence (`demo.json`, the `rights` envelope, the
  generated `DATA-LICENSE`) was honest about CAMS throughout; the repository prose was not. The
  README now opens by naming what the map is showing and carries a dated
  "What the deployed site actually shows" table, and the CAMS and Sensor.Community data cards record
  the same. Nothing about the published artifacts changed — only the claims made about them.
- **The two large history slices are written as compact JSON.** `surface-24h.json` and
  `surface-7d.json` carry one record per (place, hour, parameter) and are fetched and parsed by the
  dashboard, never read by a person; `indent=2` spent **49,202,251 bytes (32.2%)** of the
  152,665,280-byte `surface-7d.json` published on 2026-08-19 on whitespace. Measured after:
  **103,463,029 bytes**, gzipped 3,119,358 → 2,642,447. The payload shape is unchanged, so no
  consumer contract moved, and every smaller artifact stays indented. This is a mitigation, not a
  fix — 103 MB is still too much to hand a browser, and `export.csv` (314,470,584 bytes, growing
  ~15 MB/day with no bound) is the larger problem — see
  [#181](https://github.com/ChelseaKR/swelter/issues/181).
- **The suppression hygiene gate now ratchets (CQ-34/CQ-35, [#107](https://github.com/ChelseaKR/swelter/issues/107)).**
  `scripts/hygiene_check.py` already required every `noqa`/`type: ignore`/`nosemgrep` to be coded
  and issue-linked, which makes a suppression *legible* but does nothing to make it *temporary* —
  the inventory could grow without limit while the gate stayed green. It now counts tracked
  suppressions against a committed `SUPPRESSION_CEILING` and fails both when the count rises (a new
  suppression costs a visible, reviewable edit) and when it falls without the ceiling being lowered
  (a ceiling left high hands the retirement straight back). The gate prints the per-file inventory
  so #107 has something concrete to review. One waiver retired in the same change: the
  `python37-compatibility-importlib2` Semgrep waiver in `sources/_california_boundary.py` moved to
  the line above the import, which fits the line-length limit and so no longer needs its companion
  `E501` `noqa`. 30 tracked suppressions to 29.
- **MessageFormat 2 runtime graduated to the stable `messageformat@4.0.0` release.** The dashboard
  vendored the `4.0.0-11` prerelease only because no networked install could resolve the stable
  tarball; that upgrade trigger, documented in [`docs/I18N.md`](docs/I18N.md), has now fired. The npm
  lock, the generated `web/vendor/messageformat/` runtime, the i18n manifest syntax stamp, and the
  runtime-exactness assertions in the install generator, extraction check, and JavaScript
  conformance suite all move to `4.0.0`. The vendoring decision in
  [ADR 0026](docs/adr/0026-vendored-messageformat-runtime.md) is unchanged; only the pinned version
  differs. No catalog, message, or placeholder changed.
- **Statewide geographic map and minimalist observatory ([PR #130](https://github.com/ChelseaKR/swelter/pull/130)).**
  The default California view now places every reading with one basemap-aligned geographic
  projection. Nearby readings collapse into numbered overview groups anchored to real places;
  choosing a group moves and zooms the camera without changing any coordinate. The full record set
  remains available in the Map DOM and in the equivalent List and Table. The surrounding interface
  was reduced to a basic, space-efficient visual system with less repeated instructional copy. See
  [ADR 0033](docs/adr/0033-statewide-geographic-map-clustering.md).
- **Fast static first paint without discarding history ([PR #130](https://github.com/ChelseaKR/swelter/pull/130)).**
  `sample-surface.json` now contains only the newest bucket used for the initial render, while
  `surface-24h.json` and `surface-7d.json` retain their complete publication windows and the browser
  enriches the linked history views in the background. The canonical 150-node synthetic demo keeps
  its compact calibration fixture in the store but publishes a deterministic statewide California
  preview at validated public place centroids; custom community networks are never remapped.
- **Source-aware static fallback corrections.**
  The CAMS/Open-Meteo demo contract now matches the route's provisional upstream-model posture, and
  a California fallback on `/sensors/` retains the state basemap instead of publishing California
  readings over an empty canvas. Route source, geography, terminology, and reuse terms continue to
  come from the source contract that actually won the Pages build.
- **Repository presentation and contributor metadata.** The package now reports its Beta status and
  live project site, contributor templates preserve source-specific data rights, and the existing
  sun app icon now carries through to the basic California-map social card and social metadata.
- **Frontend performance baseline ([PR #130](https://github.com/ChelseaKR/swelter/pull/130)).**
  Snapshot, source-contract, catalogue, and basemap requests start in parallel; the initial map waits
  for the already-running basemap request so readings and geography align on first render. Both
  published routes pass the committed Lighthouse regression budget with measured LCP at or below
  2.5 seconds.
- **Browser accessibility gate.** The Playwright conformance suite allowlists only patterned-severity
  `color-contrast` *incomplete* results (map cells, braid labels, and severity chips) and the known
  axe `target-size` engine error on grid cells — never a real violation — and independently verifies a
  severity chip's 4.5:1 contrast pair. Cross-browser and copy-drift test fixes track the current
  Spanish catalog, preserve published labels in record-set comparisons, target pressable selection
  controls, exclude disabled controls from focus-exposure checks, and accept Firefox's
  `translate(0px)` reset serialisation. See
  [`docs/audits/accessibility-report.md`](docs/audits/accessibility-report.md).
- **Data schema version 2 (was 1).** The observation export gains a `qc_flags` field: an array in the
  JSON export and a new `qc_flags` column in `/export.csv`. Because adding a CSV column is a break for
  positional parsers under [`docs/VERSIONING.md`](docs/VERSIONING.md), `data_schema_version` moves to
  `2`. Consumers that read the CSV by column name, or the JSON by key, are unaffected.
- **Sensor-twin "cross-checked" precision tier (EXP-09, F-25).** `qc.twin_agreement` now derives a
  three-state drift smoke-alarm per twin window — `cross-checked` (co-located low-cost twins agree
  within a documented spread bar), `diverged` (they drifted apart — investigate), or
  `insufficient-data` — surfaced in `qc.health_report`'s `twin_agreement` block, `swelter qc`, and
  `/api/health.json`. The bar is a per-parameter default (`qc.TWIN_AGREEMENT_THRESHOLD`) overridable
  per pair via a new optional `twin_windows[].agreement_threshold`. It bounds **precision, never
  accuracy**: cross-checked ≠ calibrated, the verdict is QC/health metadata only, and no observation
  value, calibration version, or provisional status is ever changed by it (hard rule #3). See
  [ADR 0030](docs/adr/0030-sensor-twin-crosschecked-tier.md) and
  [`docs/calibration.md`](docs/calibration.md).
- **Multi-hazard packs and a cold pack (EXP-13).** The alert layer's danger floors are now a
  versioned, cited **hazard pack** (`src/swelter/hazard_packs.py`) a network selects with
  `hazard_pack:` in `network.yaml`, instead of code. Heat is the default and unchanged — a config
  that names no pack produces identical output. A new **cold pack** ships alongside it: a
  `wind_chill_c` parameter (the documented NWS/Environment-Canada metric wind-chill index, honestly
  labelled an approximation, added to `models.PARAMETERS` with QC bounds and a spike threshold) and
  the NWS Wind Chill Chart's cited −28.3 °C / −19 °F 30-minute frostbite floor, wired through the
  alerts feed in English and machine-drafted Spanish. Enabling cold is config alone; every pack
  floor carries a public-source citation, and `swelter doctor` validates the pack id and its
  override keys. See [ADR 0031](docs/adr/0031-multi-hazard-packs.md) and F-26.
- **Reference-monitor co-location (EXP-02).** `swelter colocate --node … --monitor … --window …`
  assembles calibration training pairs automatically from stored raw node data and a regulatory
  reference series, matching each hourly reference reading to the nearest node sample within a
  documented tolerance (the pairing/resampling logic is a pure, offline function). A new
  `sources/airnow.py` adapter pulls US EPA AirNow / AQS reference PM2.5 — its own public-domain-plus-
  attribution terms retained, never relabelled, and its runtime API key redacted from any failure
  message — and the monitor's AQS site id flows into `Correction.reference`. See
  [`docs/adr/0032-reference-monitor-adapter.md`](docs/adr/0032-reference-monitor-adapter.md) and the
  [AirNow data card](docs/data-cards/airnow.md).

### Fixed

- **One unlicensable OpenAQ location no longer voids every other location in California.**
  `build_license_ledger` and `validate_license_ledger` disagreed. The builder emitted an entry
  for any location OpenAQ named a license for, including ones naming neither a provider nor an
  attribution to credit; the ledger normalizer refuses exactly that entry — and normalization is
  all-or-nothing, so a single such location made every *other* California location's terms
  unpublishable. The `demo` workflow has fallen through to Copernicus CAMS on every run since
  2026-08-16 (#179).

  The builder now validates each candidate against the same normalizer the ledger will later be
  checked by, and excludes the location it cannot describe — by id, by name, and with the rule
  that refused it — instead of emitting an entry that voids the document. The fail-closed posture
  is unchanged and deliberately not relaxed: an unlicensed location is still never fetched and
  never published. What changes is the blast radius, from statewide to that one location.

  Three further shapes the live API can return, each of which used to black out the state, now
  exclude one location apiece: a validity boundary sent as a timestamp rather than a plain date,
  a license whose canonical source URL is not HTTPS, and validity that ends before it starts.
  Upstream whitespace around a provider or location name is trimmed rather than treated as a
  reason to refuse; a location listing the same license twice collapses rather than tripping the
  duplicate-identity rule.

  **This is a proven cause, not a confirmed complete one.** It is reproduced by unit test from
  metadata shapes the v3 API can return, but the live refusal has not been reproduced against
  `GET /v3/locations` with the key, which this session does not have. #179 stays open on that
  evidence, per its own checklist.

- **A refused ledger says which rule refused it.** `license_ledger_gaps` answered
  `ledger is malformed or missing required fields` for every structural cause there is — wrong
  document shape, wrong schema version, no entries at all, one bad field on one entry out of
  hundreds. That is the message the deployment has printed unchanged since #187 added it, and it
  named nothing an operator could act on. The normalizer now returns its reason rather than
  swallowing it, so a refusal reads `entry for location 2178 is unusable: OpenAQ ledger URLs must
  be absolute credential-free HTTPS URLs`. The `fetch` refusal additionally states how many
  California locations were licensed and how many were excluded, so "the ledger is empty" is
  distinguishable from "the ledger covers the wrong dates".

- **The committed fallback surface no longer understates single-member heat-index error bars.**
  `web/sample-surface.json` — the dashboard's committed offline fallback, served by `web/app.js`
  and cached by `web/sw.js` — was last regenerated before #142 corrected the derived heat-index
  uncertainty by the local |dHI/dT|. Eleven single-member `heat_index_c` cells therefore kept
  pre-fix error bars 0.28 to 0.6 °C smaller than what the current pipeline computes from the same
  committed recorded week (for example `0.942` where a fresh replay computes `1.54`); every `mean`
  was untouched. The schema-contract test could not notice, because the stale file and the fresh
  file both satisfy the schema. The artifact is regenerated, and a new `make demo-artifacts` gate
  in `verify-core` now replays the committed demo into a throwaway directory and byte-compares
  every git-tracked file the replay writes — refusing an empty comparison set — so a committed
  generated artifact can no longer drift silently from the computation it stands in for. The
  test suite itself had been rewriting these artifacts in place on every run
  (`test_demo_pipeline_calibrates_and_aggregates` omitted `--web`, whose default is the
  repository's own `web/`), which regenerated the correct values on every gate run, threw the
  comparison away, and silently repaired the drift on any machine that ran the tests; that test
  now writes to a temporary directory, so no gate mutates the tracked tree.
- **The WebKit map-center check was failing on its own reference point, not on the map.** The
  merge-blocking `a11y-advisory` gate went red on WebKit for two unrelated pull requests (#211,
  #212), one of which touches no `web/` file, with the same numbers issue #169 recorded in July:
  `Expected: 0.5`, `Received: 0.5456412596987678`. The map was never wrong. The trace from run
  33266336949 shows the box going 540x626 to 585x678 CSS pixels and the camera going
  `translate(-148px, -165.2px) scale(1.4)` to
  `translate(-160.33333333333331px, -178.9226837060703px) scale(1.4)`, which is exactly
  `-148 * 585/540` and `-165.2 * 678/626`: the geographic center held to sixteen digits in both
  axes, through a WCAG 1.4.4 text-scale reflow.

  What drifted was the baseline. The test zooms, pans `ArrowRight` then `ArrowDown`, and records
  the pre-reflow camera to compare against. A pan key mutates `state.mapView` and defers the DOM
  write to the next animation frame (`scheduleTransform`), and the wait before the recording was
  "the camera is no longer the post-zoom value" — a condition `ArrowRight` meets by itself. When a
  frame boundary falls between the two presses, which is what WebKit does once the runner is
  contended, the baseline was taken with `ArrowDown` still pending, and the reported 0.0456412596987678
  of drift is just `40 / (626 * 1.4)`, that one deferred 40-pixel pan. The horizontal assertion
  passed throughout because `ArrowRight` was in the baseline.

  Each pan is now settled against the camera observed immediately before it. That is stricter than
  the wait it replaces, which required only the first of the two pans to have landed. The
  `toBeCloseTo(..., 7)` tolerance is untouched, as are the polls, `test.slow()`, and the 20s
  ceilings, so a genuine non-convergence still fails; nothing was excluded, skipped, or loosened.
  Reproduced deterministically on local WebKit by holding the `ArrowDown` keydown until after the
  baseline read, which reproduces the CI failure to every digit, and confirmed to pass under the
  same injection once each pan is settled.

  The two earlier diagnoses in `docs/audits/accessibility-report.md` both blamed a late
  `ResizeObserver` correction in `web/app.js` and are corrected there rather than deleted. The
  2026-08-21 experiment that "confirmed" that reading — delaying `requestAnimationFrame` and
  watching the failure reappear — was in fact delaying the pan render, so it reproduced this
  mechanism and was read as the other one.
- **The core-safety mutation gate now measures something.** Every scheduled run since the gate was
  added reported `mutation: 0.00% (0 killed / 1718 total)`: `tests/test_calibrate.py`'s cross-check
  against `scripts/gen_demo_data.py` imports `scripts` from the repository root, mutmut's `mutants/`
  sandbox copies only `source_paths` and the selected tests, and the resulting
  `ModuleNotFoundError` was scored as a collection failure — zero killed — before any mutant ran.
  `also_copy = ["scripts/"]` makes the sandbox match the real layout. With the harness working, the
  first honest reading of `calibrate`/`models`/`qc` was **77.76%** against the 80% floor, plus two
  mutants of the twin-pairing walk that hung until the runner timed them out (the report treats a
  timeout as an incomplete state, never as a kill, so the gate could not have passed on score
  alone). The floor is unchanged at 80. Closing the gap added unit tests for the parts of the three
  core modules the selected tests never reached — `models.wind_chill_c` and `wind_chill_category`
  had no test in `tests/test_models.py` at all, and `qc`'s `integrity` block none in
  `tests/test_qc.py` — and pinned the published JSON contracts of `health_report`,
  `coverage_equity`, and `calibration_block`: their exact key sets, and their caveats verbatim,
  since those travel with the numbers under hard rule #4. The score is now **91.16% (1568/1720),
  with no incomplete states**.
- **The twin-pairing merge walk cannot hang.** `qc._pair_by_nearest_timestamp` walked two sorted
  series with a `while` loop whose termination depended entirely on both pointers advancing. Every
  pass consumes at least one reading, so the walk can never need more passes than the two series
  hold between them; that bound is now written out instead of left implicit in the pointer
  arithmetic. A pointer that stopped advancing now returns a checkably wrong answer rather than
  hanging `/api/health.json` forever, which is the worse of the two failures. Pairing behavior is
  unchanged.
- **Six surviving calibration mutants killed, without touching the mutation floor.** The
  core-safety mutation gate mutates `calibrate.py`, `models.py` and `qc.py` against four selected
  test files, and a mutant it cannot see is a behavior nothing asserts. Six were reachable and
  unkilled in `calibrate.py`: the `{"version": 1}` registry schema envelope, `to_yaml`'s
  `sort_keys=False` and `default_flow_style=False` (a registry that reorders on every dump is not
  reproducible), `_round`'s `+ 0.0` negative-zero collapse (the thing that keeps a re-fit on
  another machine byte-identical), and `_solve`'s partial-pivot row swap and its `1e-12` singular
  threshold. The last three were covered only by `tests/test_bugfixes.py`, which is outside the
  mutation selection, so the gate could never count them. `tests/test_calibrate.py` gains ten
  assertions written against exact values rather than tolerances, including a comparison of the
  fitted registry against the committed YAML *as parsed* — the existing reproducibility test runs
  both sides through `to_dict()`, so a renamed key is renamed on both sides and survives. Tests
  only; no source, no threshold, and no floor changes.
- **The dashboard's offline fallback surface no longer understates its heat-index error bars.**
  `web/sample-surface.json` is the committed artifact the dashboard falls back to when no live
  surface is reachable, and it is generated by replaying the recorded demo week through the real
  pipeline. [#142](https://github.com/ChelseaKR/swelter/pull/142) changed how the derived heat
  index propagates its uncertainty — scaling the temperature correction's `residual_std` by the
  local Rothfusz slope `|dHI/dT|` instead of carrying it forward unscaled — but the fixture was not
  rebuilt with it, so the committed copy kept quoting the older, tighter numbers. Regenerated with
  `swelter demo --web web`: 11 of 1050 cells change, all `heat_index_c`, and only `uncertainty` and
  `mean_member_sigma`. Every changed value widens, by 1.48x to 1.75x, consistent with a slope
  floored at 1.0 and running 2 to 2.5 in the Danger band. No mean, category, provisional flag, or
  QC flag moves. The stale fixture was the same understatement #142 fixed in the code, left behind
  in the artifact residents actually see when they are offline.
- **A Danger day and a Danger hour now state what they rest on ([#199](https://github.com/ChelseaKR/swelter/issues/199)).**
  `exposure_brief.count_danger_days` and the event chronicle's per-cell tally both decided "Danger"
  from `cell.mean` alone, through the same `alerts.crossing` test the live alerts feed uses, and
  neither looked at `cell.provisional` or `cell.qc_flags`. A single QC-flagged spike — the
  pipeline's own "do not trust this as a measurement" verdict — became a full Danger day or Danger
  hour in a record built for organizers and health departments, with nothing on the page saying the
  evidence behind it was flagged or uncalibrated. The alerts feed had honoured this all along
  (`Alert.provisional`, rendered in the headline); the two share artifacts had not.
  `DangerDayCount` now carries `danger_days_provisional` and `danger_days_qc_flagged`, and
  `CellChronicle` carries `danger_hours_provisional` and `danger_hours_qc_flagged` — how much of
  the count rests only on readings the pipeline does not vouch for. Both splits render everywhere
  the count does: the brief's lines and JSON record, the chronicle headline, its per-cell table,
  its always-present "what the network could not see" section, and the `swelter chronicle` summary
  line. The crossing itself is unchanged: a flagged reading is still counted, because dropping it
  would blank exactly the hours ADR 0029 exists to keep visible. The evidence line is rendered at
  zero too, so a well-evidenced count and a shaky one never read the same
  ([ADR 0046](docs/adr/0046-a-danger-count-states-what-it-rests-on.md)).

- **The derived heat index's error bar now widens with the Rothfusz slope, instead of quietly
  understating it.** `calibrate.apply()` carried the temperature correction's `residual_std`
  forward *unscaled* as the derived `heat_index_c` 1-sigma. First-order error propagation says
  `σ_HI = |∂HI/∂T| · σ_T`, and the local Rothfusz slope is roughly 2–2.5 in the hot-humid Danger
  band — so the published error bar was too tight by more than 2× exactly where the stakes are
  highest. The slope is now computed at the calibrated temperature (a same-side difference
  quotient, so the 26.7 °C branch discontinuity cannot inflate it) and floored at 1.0, so a
  derived error bar is never claimed *tighter* than the temperature's own; below the regression
  floor, where heat index is the air temperature unchanged, the slope is exactly 1. Humidity's own
  uncertainty remains unmodeled (uncalibrated in this network), stated at the propagation site.
  Restores the stranded follow-up PR #80 omitted, per ADR 0014's propagation posture.
- **A printed card now says *why* a value is provisional.** `swelter cards` renders one door-flyer
  per published cell for residents with no screen and no connection — the surface with the least
  recourse. Its provenance line offered a two-way choice, `confirmed` or `provisional`, so a
  reading QC had flagged as an implausible spike or a flatline printed as plain `provisional`,
  indistinguishable from an ordinary reading that simply has no correction fitted yet. That is the
  exact distinction [ADR 0029](docs/adr/0029-event-aware-qc-visible-provisional.md) exists to keep,
  and the surface record, the CSV/JSON export, the data dictionary and the dashboard all carry it.
  `state-flagged` (`provisional, flagged` / `provisional, marcada`) was already in both shipped
  catalogs and already loaded by `cards.load_strings`; the card never asked for it. `_CellReadings`
  now carries `qc_flagged` and `_render_provenance` renders the same three states as every other
  surface, with a print-safe weight difference rather than colour alone.
- **Five merge-blocking gates could pass over an empty corpus.** The repository had already fixed
  this shape twice (`workflow_policy_check`, `reading_level_check`); these are the rest of it. Each
  printed a universal claim and returned 0 when the set it was claiming about was empty:
  `log_safety_check` (`production log calls are structured and PII-safe` with nothing scanned — the
  corpus is `git ls-files '*.py'` filtered by `SCAN_DIRS`, so renaming `src/` emptied it silently);
  `acceptance_map_check` (`PASS (0 shipped features; paths, symbols, roadmap, ISO 25010:2023
  verified)` for an empty table, since every per-row rule and one-to-one coverage of an empty
  inventory are vacuously satisfied); `adr_immutability_check` (`PASS (0 Accepted base ADR(s)
  unchanged)`, reachable because `git ls-tree` exits 0 with empty output for a path absent at the
  base while `_ADR_PATH` hard-codes `docs/adr/`); `i18n_parity` (two empty catalogs reported as at
  key parity); and `web/tests/run-pa11y.cjs` (`Pa11y: 0/0 pages passed`, exit 0, for an empty URL
  list). All five now refuse, and each states the size of the corpus it did cover. The Pa11y runner
  additionally checks its URL list against the published routes, and no longer treats an issue
  whose severity it cannot read as non-blocking.
- **`make verify-package` could go green over a wheel with no SBOM.** `make sbom` generated one
  CycloneDX BOM per artifact in a shell `for` loop, whose exit status is the last iteration's — so a
  failed BOM for the wheel was swallowed whenever the sdist succeeded. `make sbom-validate` then
  validated `dist/*.cdx.json`, a glob that simply did not include the file that was never written,
  and reported success over the sdist alone. The loop now runs under `set -e`, and `sbom-validate`
  asserts one BOM beside each built artifact before validating any of them.
- **A workflow-policy exemption outlived what it excused.** `_PROTECTED_VERSION_ANNOTATIONS` held a
  governance exception keyed to `pages.yml`'s `actions/cache@0057852…` pinned `# v4`. That pin left
  the workflow at the v4.3.0 → v6.1.0 bump and the entry stayed: a hole cut in a security gate,
  matched by no `uses:` line, reachable by nothing and reported by nothing — so nobody could learn
  it was closable, and a future pin reproducing the same tuple would have been waved through on a
  decision no one made. The entry is retired and `stale_exemptions` now checks the table against the
  workflows on every run.
- **The DORA gate's PASS line said nothing about how much it checked.** `dora-evidence: PASS (check)`
  was printed identically for a full retained window and for the committed state, which has zero
  records, zero computed metrics, and `collection.complete: false` — so `_complete_metrics`, where
  every DORA threshold in the script lives, is never entered. That emptiness is real and tracked in
  [#109](https://github.com/ChelseaKR/swelter/issues/109); what was wrong is that a reader could not
  tell the two runs apart from the gate's own output. It now reports records, metrics computed, and
  collection state.
- **The publishing-gap validator's findings made no observable difference.** Both branches of
  `validate-publishing-gap` printed the same shape of `[FAIL]` and exited 1, so a corrupted or
  semantically wrong `release-publishing-gap.json` read exactly like the healthy tracked gap and
  every assertion in `validate_publishing_gap` was decorative. The release is still blocked either
  way — that is correct — but the two reasons now read differently. Its "must not be conflated with
  #105" rule was a bare `"105" in text` substring test that could not tell an issue reference from
  any other occurrence of three digits; it now matches a reference.
- **The docs-figures test-count rule warned forever about a correct state.** CLAUDE.md's own rule is
  "never put a test count in prose unless a check regenerates it", and the count this rule was
  written for was deleted under that rule — after which the rule reported `could not find a
  '(N tests, all green)' line` on every run, and ran a `pytest --collect-only` subprocess whose
  result was then discarded. An advisory channel that is always amber reports nothing. Absence of
  the claim is now a pass that says so, and the collection runs only when there is a claim to
  compare against.
- **One fewer tracked static-analysis suppression ([#107](https://github.com/ChelseaKR/swelter/issues/107)).**
  ruff 0.16.3 narrowed `S310`'s detection so it no longer flags `urllib.request.Request(...)`
  construction itself — only the actual `urlopen()` network call still needs the suppression —
  making the `# noqa: S310` on `scripts/standards_pin_check.py`'s `Request(...)` line genuinely
  unused (`RUF100`). Removed it and lowered `SUPPRESSION_CEILING` from 27 to 26 to lock the
  retirement in, per `hygiene_check.py`'s own ratchet rule.
- **The coverage floor and the dependency-lock audit now enforce what they claim to.** The 90%
  branch-coverage floor previously existed only as `--cov-fail-under` on the `make test` command
  line, so any path that reached `coverage report` another way (direct `pytest`/`coverage` use)
  carried no floor at all; `fail_under = 90` now also lives in `[tool.coverage.report]`, so the
  policy has one source of truth. `security-pip` exported the dependency graph with
  `uv export --frozen`, which writes out whatever `uv.lock` says and exits 0 even when the lock has
  drifted from `pyproject.toml` — auditing the wrong set of pins and still passing; `--locked`
  fails closed on that drift instead. Both changes are no-ops today (the lock is in sync, coverage
  already clears 90%) and become real gates the next time either isn't true.
- **A dead humidity probe published an estimated WBGT that read as a safe day.** A capacitive probe
  whose readout fails reports its scale floor, and the values it lands on — exactly `0.0` and exactly
  `1.0` %RH — were *inside* the published range `[0.0, 100.0]`, so `range_flag` returned `ok`,
  aggregation mapped them, and ADR 0041's input guard passed them into a derived heat index and
  estimated shade WBGT. Because the wet-bulb term is monotone in humidity, the error was always in
  the under-warning direction. Measured live on 2026-08-19 across 1,066 Sensor.Community sensors:
  **26 of 460 humidity readings (5.65%) were sentinels** — 25 at exactly `1.0` (DHT22), one at
  exactly `0.0` (BME280) — and each published a WBGT 6–14 °C below the same temperature at a
  plausible humidity. The worst was a sensor reporting 46.2 °C, which published an estimated WBGT of
  **26.13 instead of ~40.05**: a 46 °C afternoon presented as an ordinary warm day, on a surface
  whose purpose is helping someone decide whether it is safe to be outside. `humidity_pct.valid_min`
  is now **2.0**, so both sentinels are flagged `range`, are never mapped, and derive nothing; the
  raw rows still travel and still count as node-trouble evidence. The floor was checked against the
  real distribution, not just the sentinels: model output over desert California genuinely reaches
  single-digit %RH, and the published store's 166,478 humidity rows decay smoothly through that band
  (458 at 7 %RH, 322 at 6, 213 at 5, 103 at 4, 21 at 3, 3 at 2, 1 at 1), so a 2.0 floor reclassifies
  **one** of them — 0.0006% — against 5.65% of a physical-sensor feed's readings caught. A dead probe
  spikes on one value with a gap above it; real dry air decays. `qc.apply` is not retroactive, so
  that single stored `1.0` row keeps its old `ok` verdict until its store is rebuilt. This resolves
  the case ADR 0041 recorded and deliberately left open
  ([ADR 0043](docs/adr/0043-a-dead-probe-reads-zero-not-dry.md)).
- **`/sensors/` could never recover from a provenance refusal, and had been a copy of page 1 for
  days.** `swelter fetch --accumulate` refused any store holding observations without a
  `source-metadata.json`. Correct — readings whose terms nobody can name must not be published — but
  the Pages workflow restores that store from an `actions/cache` entry on *every* run, so the
  refusal was self-sustaining: the workflow's documented "a cache miss just degrades to a fresh
  fetch" never fired, because it was a cache **hit**. Observed on every `demo` run inspected from
  2026-08-16 to 2026-08-19; the route silently served a byte-identical duplicate of the California
  page while CI stayed green. Absent provenance now discards the unattributable store (and its
  OpenAQ license ledger) and fetches fresh, printing why; *disagreeing* provenance is still a hard
  refusal, unchanged. The cache key moves to `swelter-fetch-store-scope-v3-`
  ([ADR 0044](docs/adr/0044-an-unattributable-store-is-discarded-not-refused-forever.md)).
- **`export.csv` no longer grows unbounded with the accumulating store ([#181](https://github.com/ChelseaKR/swelter/issues/181), [ADR 0045](docs/adr/0045-published-export-is-windowed-the-accumulating-store-is-not.md)).**
  The store behind a live deploy accumulates without a bound by design (ADR 0013), and a static
  `swelter publish` baked the *entire* store into `export.csv` every run — measured at 314,470,584
  bytes and growing ~15 MB/day on 2026-08-19, on a path toward the GitHub Pages 1 GB site limit in
  about a month, while no view the site itself offers ever shows more than 7 days of history.
  `export.csv` is now windowed to the same trailing span `surface-7d.json` already uses (the most
  recent 24×7 distinct hour *buckets* present, not a literal now-minus-N cutoff and not raw
  timestamps — a source reporting faster than hourly, like Sensor.Community's native ~2.5-minute
  cadence, would otherwise undercount the window by counting readings instead of hours), via one
  shared constant so the two artifacts can't drift apart. The complete, unbounded history remains
  available locally via `swelter snapshot`; the live, filterable `/export.csv` route
  (`swelter serve`) is unaffected — only the static Pages artifact is bounded.
- **The OpenAQ license-ledger refusal now says which reading and why
  ([#179](https://github.com/ChelseaKR/swelter/issues/179)).** `validate_license_ledger` returned a
  bare `bool`, so every refusal printed the identical, unactionable
  `"OpenAQ readings have no publishable per-location license ledger"` regardless of whether one
  location out of 250 was missing terms or all of them, and regardless of whether a location was
  never licensed at all versus licensed under an entry that doesn't cover this reading's date. A new
  `license_ledger_gaps` names each distinct gap ("location 2 (oaq-2): no license entry at all" vs.
  "location 1 (oaq-1) at 2026-06-02T00:00:00Z: 1 entry present, none covers this reading's date"),
  de-duplicated so a single dead location's many readings collapse to one line; `fetch`'s
  `SourceError` now prints the first five. **This does not close #179** — the root cause (why OpenAQ
  v3 currently returns nothing the ledger can match) is still unconfirmed against the live API, which
  needs the repo's `OPENAQ_API_KEY` secret to reproduce. It makes the next run's refusal legible
  enough to diagnose that root cause instead of re-reading the same six words for the sixth time.
- **A broken sensor's arithmetic could reach the map as a clean heat reading.** All three real
  source adapters derived heat index and estimated shade WBGT whenever both inputs were *present*,
  never checking whether they were *plausible*. A temperature or humidity outside its published range
  is `QC_RANGE` → `QC_UNMAPPABLE`, so the pipeline never places it on a cell "even provisionally"
  (ADR 0029) — but the metric derived from that same rejected number frequently landed back inside
  the derived parameter's own range, where nothing downstream could tell it from a real reading, and
  was published unflagged. Measured: a rejected `-41 °C` yielded a mapped `wbgt_c` of `-39.48`; a
  rejected `110 %RH` at 35 °C yielded a mapped `36.16`; a rejected `80 °C` yielded a mapped `53.11`.
  The whole band `temp_c ∈ [-61.72, -40.01]`, everything from just past +60 °C to roughly +85 °C at
  low humidity, and effectively all humidity above 100 %RH leaked a mappable value. This is live
  input, not a hypothetical: on two Sensor.Community area fetches on 2026-08-18, 13 of 272
  temperature readings (4.78%) were impossible values near -145 °C from faulted probes. Derivation
  now happens in one place, `models.derive_heat_metrics`, which derives nothing unless both inputs
  are in range and drops a derived value that falls outside its own range; the raw inputs still
  travel and are still flagged, because QC labels a reading rather than deleting it
  ([ADR 0041](docs/adr/0041-a-derived-reading-is-only-as-real-as-its-inputs.md)).
- **The live map, alerts feed and Atom feed were publishing a CAMS forecast hour as the current
  reading ([#168](https://github.com/ChelseaKR/swelter/issues/168)).** Open-Meteo returns elapsed and
  forecast hours in one array, and `openmeteo.to_observations` emitted an `Observation` for every
  entry with no comparison against any reference instant, so hours that had not happened entered the
  store as ordinary readings. Because "now" is the newest bucket present (ADR 0035), they *became*
  now: on 2026-08-15 the published `data_hour` was nine hours ahead of the deploy that wrote it, and
  `alerts.json` carried 17 heat-index **Danger** alerts stamped `2026-08-15T23:00:00Z` — read at
  14:40Z. The caveats that travel say how a number was produced, never that the hour it describes
  has not happened. `to_observations` now takes a `now` reference instant, defaulting to the wall
  clock, and drops every later hour; `fetch` resolves it once and logs it, so one statewide run
  clips against one instant. `forecast_days` stays 1 because that is how today's already-elapsed
  hours are returned ([ADR 0039](docs/adr/0039-a-forecast-hour-is-not-an-observation.md)).
- **The host-consent warning fired hundreds of times per deploy on public city centroids
  ([#166](https://github.com/ChelseaKR/swelter/issues/166)).** `openmeteo.network_doc` wrote
  `location: precise` for every place it fetched — with a comment on the same line saying they are
  public centroids, not private homes — because the schema had one spelling for "publish this
  coordinate exactly" and no way to say whether anyone lives there. So `consent_concerns` asked for
  a governance-log consent entry for `san-diego`, `redding`, `crescent-city` and the rest of the
  statewide list, once per place, twice per deploy, forever. A new `location: public-place` kind
  publishes the exact coordinate and carries no host, so the consent check has nothing to ask; a
  `public-place` node that records a `consent_ref` is now a hard configuration error, and
  `swelter node-preview` still states the exact-coordinate disclosure in as many words. The
  Sensor.Community adapter deliberately stays `precise`
  ([ADR 0040](docs/adr/0040-a-public-place-is-not-a-host.md)).
- **Two gates that could not fail.** `make workflow-policy` globbed `.github/workflows/*.yml`
  only, so a workflow committed as `.yaml` — which GitHub runs identically — was invisible to it:
  an unpinned action, `|| true`, `continue-on-error: true`, a missing `permissions:` block and a
  credential-persisting checkout all passed, and the gate still printed that *every* Action is
  SHA-pinned and fail-closed. It now enumerates both suffixes, reports how many workflows it
  scanned, and fails when it finds none, because a universal claim about an empty set is not a
  pass. `make reading-level` had the same shape from the other end: with nothing in `en.json`
  long enough to score it printed `[PASS] all 0 scored strings are at or below grade 8` — the same
  green a real pass prints — so any change that emptied the corpus would have retired the gate in
  silence. Scoring nothing is now a failure that says so.
- **Every gate runs on every commit, whatever the gates before it did.** `verify`,
  `verify-core` and `verify-security` were prerequisite lists, and make stops one of those at the
  first failure. An unpatched HIGH advisory in the dashboard accessibility toolchain
  (GHSA-jmr9-qjv8-65gv in `extract-zip`, no fixed release) failed `security-osv`, so
  `security-node`, `security-secrets`, `security-semgrep` and `security-workflows` never ran —
  the secret scan, the blocking SAST gate and the workflow policy check silently stopped
  executing, and the SARIF upload step then failed for want of a file semgrep never wrote. The
  CI security job had the same shape, one failing step ending the job. `scripts/run_gates.sh`
  now runs every gate in a set, prints each one's own PASS/FAIL and exits non-zero if any
  failed, and each CI gate step carries `if: ${{ !cancelled() }}` so it starts regardless of
  what the step before it did. A failed step still fails the job: this changes what runs, not
  what passes.
- **A dependency-advisory exception mechanism, with nothing in it.** `waivers.yml` is the single
  dated, owned, expiring record of any accepted dependency finding, and `osv-scanner.toml` may
  ignore only ids that have a live waiver naming `osv-scanner` with the same date -- `make
  security-waivers` fails if the two files disagree, so adding an id to the scanner's ignore list
  on its own breaks the build instead of silencing anything.
  `scripts/dependency_advisory_gate.py` matches an advisory on id, package and severity together,
  so a new advisory, a second advisory in the same package, or the same advisory escalated in
  severity all still fail. The registry ships **empty**: GHSA-jmr9-qjv8-65gv was going to be its
  first entry, and `extract-zip` left the dependency graph instead, so the exception was retired
  with the finding rather than left to outlive it. An empty registry is the correct resting state
  -- every advisory the scanners report fails the gate. `tests/test_dependency_advisory_gate.py`
  pins the boundary against `tests/fixtures/waivers/`, a synthetic waiver for a package and an
  advisory that do not exist, so the mechanism stays tested while nothing is waived, and pins the
  empty resting state of the committed files directly.
- **A correction version id now names the fit that produced it ([#149](https://github.com/ChelseaKR/swelter/issues/149)).**
  `version` was a pure function of `(parameter, method, node_id)` — no window, no date, no
  coefficient digest — so two corrections fit from genuinely different co-location evidence, 10 °C
  apart in what they publish for the same raw reading, shared one identifier, one store primary key,
  and one `calibration` value in every export. Two datasets downloaded a year apart both said
  `temp_c.enclosure-offset.node-01` and both said `trustworthy: true`; the audit trail existed only
  in the git history of `corrections.yaml`, which does not travel with the data. The id is now
  `{parameter}.{method}.{node_id}@{window_end}-{digest}` (e.g.
  `temp_c.enclosure-offset.node-01@20260602T230000Z-36672bc8`), where the suffix is the compact end
  of the fit's co-location window plus a SHA-256 digest over its predictors, coefficients, intercept,
  `residual_std`, `r2`, `n`, `reference`, window, and sensor model. A derived heat index carries the
  fit id of the *temperature* correction it was computed from. Everything before `@` is unchanged and
  the fit id contains no dot, so the two positional readers (`aggregate`'s published `method`,
  `export`'s correction family) are unaffected
  ([ADR 0038](docs/adr/0038-a-correction-version-that-names-its-fit.md)).

  **Breaking, as `docs/VERSIONING.md` already declared a version-id format change to be.** The
  committed `data/demo/corrections.yaml` is regenerated — every coefficient, error, window, and `n`
  in it is byte-identical; only the ids gained their suffix. Stored `calibration` values change, so
  calibrated rows' `content_hash` changes; raw rows are untouched and `swelter rebuild` re-derives
  the calibrated ones. A consumer that matched a version id exactly against a stored string must
  re-read it after a re-fit, which is the point.

- **`swelter demo` reported corrections it attempted, not corrections it wrote
  ([#149](https://github.com/ChelseaKR/swelter/issues/149)).** `cmd_demo`'s run manifest and stdout
  line used `len(calibrated)` — rows *attempted* — while `cmd_calibrate` correctly reported
  `written.written` — rows *inserted*. A run whose writes were partly ignored would have claimed
  full effect. Both now report rows written.
- **The demo generator's copies of `heat_index_c`/`wbgt_c` are now checked against `models`
  ([#149](https://github.com/ChelseaKR/swelter/issues/149)).** `calibrate`'s docstring says `apply`
  uses "the same NWS Rothfusz function the demo generator uses"; it is a verbatim copy, and no test
  asserted the two agree. The copy is kept deliberately — an independent implementation is what
  makes the committed fixture evidence rather than a restatement of the code under test — and a new
  test asserts the two agree across a 70-point temperature/humidity grid, so "the same function" is
  a verified claim instead of a comment.
- **The synthetic co-location fixture's limit is now stated where it is claimed
  ([#149](https://github.com/ChelseaKR/swelter/issues/149)).** `read_colocation`'s docstring called
  the committed file "the recorded evidence a calibration is fit from … auditable by anyone", but
  `scripts/gen_demo_data.py` draws each co-location `raw` independently of the observation published
  for the same node and instant, so only 0.5% of committed pairs match the stored reading. The fit
  is reproducible from the file either way (a CI gate proves it); what it does not support is
  cross-checking against `observations.jsonl`, the way a real deployment's evidence would. Said
  plainly in the docstring, at the generator, and in the synthetic-demo data card. Making the pairs
  reuse the observation stream's own draws would regenerate every value in the fixture and every
  worked example that quotes one, so it stays its own change.
- **A missing 1-sigma no longer shrinks the published error bar ([#147](https://github.com/ChelseaKR/swelter/issues/147)).**
  `aggregate._bucket_observations` read a calibrated member's absent uncertainty as `0.0`, so an
  *unknown* 1-sigma entered the cell's arithmetic as a **perfect instrument**: adding one member
  with an unknown sigma to a cell whose known member had 0.8 halved `mean_member_sigma` to 0.4 and
  pulled the cell standard error to 0.400, below the 0.800 of the one member actually measured —
  the error bar tightening because swelter knew *less*, on a cell still published
  `provisional: false`. A new `aggregate.combine_member_sigmas` is now the one place member sigmas
  are combined: any unknown sigma means the cell publishes **no** numeric `uncertainty` or
  `mean_member_sigma` at all, plus an `uncertainty_note` saying how many were unknown; an explicit
  `is not None` test replaces `any(uncs)`, so a genuine `0.0` (a fit whose residual standard
  deviation rounded to zero) stays `0.0` instead of being published as unknown. `Observation` now
  refuses a calibrated row with no uncertainty at construction — the boundary every writer, adapter,
  import path, and store read passes through — and `store._row_to_obs` re-raises naming the row and
  the remedy (`swelter rebuild`) rather than repairing a row it cannot stand behind. `uncertainty_note`
  is no longer exposure-only: any cell publishing a null uncertainty carries its reason to the
  record, the map GeoJSON, and the dashboard's provenance panel
  ([ADR 0037](docs/adr/0037-absence-is-never-published-as-a-number.md)).
- **A NowCast PM2.5 record now states that it has no error bar ([#147](https://github.com/ChelseaKR/swelter/issues/147)).**
  Every NowCast cell shipped `uncertainty: null` with no note — 100 of them stamped
  `provisional: false` in the committed `web/sample-surface.json` — which made the reading a person
  is most likely to act on (the one that tracks a smoke plume) the one that shipped as fact with
  nothing attached. NowCast cells now carry an `uncertainty_note` saying the blend has no derivable
  combined sigma and pointing at the hourly-mean record for the same bucket, which does carry one.
  They stay `provisional: false`: they are derived from calibrated hourly means, so calling them
  provisional would say "uncalibrated", which is not true. `docs/api.md` documents this.
- **The published data dictionary no longer advertises a QC verdict nothing writes ([#147](https://github.com/ChelseaKR/swelter/issues/147)).**
  `qc: "missing"` is defined in `models.py` and published in `/api/schema.json`, and no code path in
  the repository ever sets it — a consumer writing `if row.qc == "missing"` got dead code and a
  false sense that gaps arrive in-band. Each published verdict now carries an `emitted` flag
  (`missing` is `false`), computed from the new `models.QC_EMITTED`, and the verdict's description
  says where absence actually lives: the absence of a row, plus the separately reported `gaps`. The
  constant is kept so `QC_UNMAPPABLE` still rejects the verdict if an ingest path ever sends one.

- **Sensor.Community readings, dark since 2026-06-19, and the silence that hid it.** swelter sent no
  `User-Agent`; the network declines an anonymous client with `HTTP 200` and a JSON error document
  rather than a 4xx, that document is itself a list, and `fetch` coerced it to an empty result. Seven
  weeks of live surfaces served CAMS model data with zero physical community sensors while the daily
  refresh ran green and the CLI reported the network as "sparse outside Europe". Every request now
  identifies swelter (`sources/_http.USER_AGENT`), and a new shared `sources/_http.expect_records`
  boundary refuses to read a non-record payload as records: an empty area stays a quiet, legitimate
  `[]`, but a refusal raises `SourceError` quoting what actually arrived. The CLI now reports what it
  observed instead of naming a cause it has not established. First run after the fix: 1,718
  observations from 615 live nodes ([ADR 0034](docs/adr/0034-a-refused-fetch-is-not-an-empty-area.md),
  [#146](https://github.com/ChelseaKR/swelter/issues/146)). The refresh workflow still swallows an
  empty result, which is tracked in that issue and not closed here.
- **A dead node can no longer keep broadcasting a stale Danger alert ([#148](https://github.com/ChelseaKR/swelter/issues/148)).**
  `alerts.build_feed` scanned `Surface.latest_by_cell()` with no bound on how old "latest" was, so a
  node that stopped reporting kept its last reading's alert active in every subsequent feed, stamped
  `provisional: false`, inside a feed whose own "updated" timestamp was current — while `web/app.js`'s
  map correctly dropped it as stale. `build_feed` now only raises an alert for a cell/parameter whose
  latest reading's bucket equals the surface's newest bucket (`Surface.newest_bucket()`, a new method
  also now shared by the static web-snapshot and publish-manifest code that already computed this
  value inline), the same reference instant the map's `latestBucket()` uses — so the feed and the map
  agree by construction. No wall clock is introduced;
  `test_feed_timestamp_is_data_derived_not_wallclock` still holds
  ([ADR 0035](docs/adr/0035-alerts-bound-to-the-surfaces-newest-bucket.md)).
- **An area that stops reporting is now published as an explicit "no current reading", not dropped
  into silence ([#148](https://github.com/ChelseaKR/swelter/issues/148)).** Suppressing the dead
  node's stale crossing (above) left the feed saying nothing at all about that block, and in an
  alerts feed nothing reads as an all-clear — the same "standing all-clear" failure #148 identified
  as the worse half, now applied to every dark cell. `alerts.build_feed` publishes a `stale` array
  beside `alerts`: one record per cell/parameter whose latest reading predates the feed's bucket,
  carrying `status: "no-current-reading"`, `last_bucket`, `hours_since_last_reading` (`null`, never
  `0`, when the gap's size is not computable), `withdrawn`, and a plain-language headline saying
  swelter cannot tell whether that block is dangerous now. It deliberately carries **no** `value`,
  `severity`, `unit`, or `aqi`: the last reading is not a measurement of now. In Atom each record is
  an entry tagged `<category term="no-current-reading"/>`, published under the same `<id>` as the
  alert it supersedes and stamped with the feed's own `<updated>`, so a subscriber's reader replaces
  a standing Danger headline with the withdrawal instead of leaving it as the last word on that
  block. `AlertFeed.for_area` narrows `stale` too, `schemas/alerts.schema.json` requires
  `stale`/`stale_count`, and the dashboard's neighborhood-alerts panel names the unseen areas in its
  status line and lists them without a value or a "go to this reading" button
  ([ADR 0036](docs/adr/0036-published-absence-for-areas-that-stop-reporting.md)).
- **Dense maps no longer trade geographic truth for target spacing.** The former collision relaxation
  moved readings away from their projected coordinates and could make a compact network appear to
  cover empty parts of California. Overview clustering now preserves every geographic position,
  anchors each group control to a mapped member, keeps representative controls clear at normal and
  enlarged text sizes, and reveals the underlying reading controls after camera zoom. List and Table
  continue to expose every reading without requiring map interaction.
- **`/sensors/` layout stability (WCAG-adjacent, CLS).** The resident-facing Now card filled from short
  HTML placeholders a frame late, shoving the blocks below it (Lighthouse CLS 0.133). Its answer,
  temporal line, guidance, and status now reserve their heights, the card paints in the first
  synchronous render pass, and the boot fetches run in parallel; measured CLS drops to <0.06 on
  `/sensors/` and stays <0.02 on `/`.
- **Dark-mode severity-chip contrast.** The table's AQI/heat severity chips inherited the scheme
  foreground (near-white in dark mode) over their light severity fill — a genuine contrast failure the
  chips' pattern was hiding from the contrast scanner. They now use the permanent dark `--severity-ink`
  like the map cells, clearing AA in both colour schemes.
- **Verifiable selected-row contrast.** The selected List/Table row highlight is a flat, computable
  tint instead of a gradient, so a contrast scanner can read every reading in the selected row.
- **Reflow at 320px.** The `#method` legend and dataset card no longer stay side by side below the
  mobile breakpoint (a class-selector specificity gap left `.legend`/`.dataset-truth` pinned), so the
  13rem legend columns no longer overflow a 320px viewport (WCAG 1.4.10).
- **Skip link visible on focus.** The skip link uses fixed positioning and reveals instantly (no slide
  transition), so it is exposed at the viewport top when focused regardless of scroll.

### Security

- **Dropped the unfixable `extract-zip` symlink-traversal advisory out of the dependency graph.**
  GHSA-jmr9-qjv8-65gv / CVE-2026-56876 (CVSS 8.6) affects every published `extract-zip` release
  through `2.0.1`, which is also the latest; there is no version to upgrade to. It reached the
  dashboard toolchain transitively as `pa11y` to `puppeteer` to `@puppeteer/browsers@2.13.2`.
  `@puppeteer/browsers@3.0.2` replaced its zip handling and no longer depends on `extract-zip` at
  all, so the lock now pins that package to `^3.0.2` through an `overrides` entry rather than
  waiving the finding. Dev-toolchain only; no runtime or published artifact contains either package.

The dated `0.1.0` section is prepared release metadata; it does not assert that a Git tag or GitHub
Release exists. Publication completes only after the annotated `v0.1.0` tag passes the release
workflow.

## [0.1.0] - 2026-07-16

First public reference release: a community-operated sensing pipeline, calibration evidence model,
accessible bilingual observatory, open read/export surfaces, and portfolio-standard operational and
responsible-technology evidence.

### Added

- **Now + Explore observatory.** A resident-first current-conditions view and an analytical workspace
  with linked native-SVG history, location distribution, evidence inspector, map, sortable table, and
  plain list. Missing buckets render as gaps; uncertainty, provisional state, source, freshness, and
  time-window caveats travel with each representation ([ADR 0004](docs/adr/0004-framework-free-accessible-dashboard.md)).
- **Environmental pipeline.** Idempotent ingest, quarantine, range/spike/flatline QC, gap and health
  reporting, immutable raw rows, versioned calibration corrections, gridded aggregation, compound
  heat/air exposure, estimated-WBGT labelling, and deterministic demo/rebuild paths.
- **Authenticated node write boundary.** A separate HMAC-SHA256 ingest listener with per-node keys,
  freshness/replay checks, impersonation refusal, key rotation, and quarantine for authentication
  failures. The public server remains GET-only.
- **Open read and publication surfaces.** CSV/JSON, a read-only OGC SensorThings 1.1 subset,
  static-site publication with a content manifest, citable data snapshots, alerts in JSON/Atom, and
  source-aware exports.
- **Live-source adapters.** OpenAQ, Copernicus CAMS/weather through Open-Meteo, and Sensor.Community,
  plus deterministic synthetic data. California OpenAQ discovery is boundary-filtered before caps
  or publication ([ADR 0022](docs/adr/0022-california-boundary-filter.md)).
- **Source-license provenance.** Source data cards, source-specific attribution/terms, and a fail-
  closed OpenAQ `source-license-ledger.json` publication contract. First-party/project-authored CC0
  no longer overwrites third-party rights ([ADR 0024](docs/adr/0024-preserve-source-specific-data-terms.md)).
- **Action and context layers.** Neighborhood danger-threshold alert feeds, provenance-bearing
  cooling-center data with accessible list parity, tree-canopy context, and a descriptive exposure
  brief with sourced AC-access and historical-redlining context. Illustrative fixtures are barred
  from production publication.
- **Accessibility and language gates.** Equivalent map/table/list outcomes, keyboard and reduced-
  motion behavior, non-color severity, English/Spanish parity, BCP-47/UTF-8/CLDR checks, structural
  WCAG checks, and real-browser CI. Current manual assistive-technology and independent Spanish
  release signoff remains tracked in issue #106 rather than inferred from automation.
- **Operational evidence.** A definition of done, acceptance-test map, DORA baseline, MADR-compatible
  decision log, source data cards, DPIA, data-flow inventory, threat model, fairness and ethics scans,
  residual-risk register, standards-pin evidence, and incident/recovery runbooks.
- **Quality and supply-chain gates.** Strict typing, formatting/lint/security/complexity checks,
  branch coverage, Python and web suites, documentation/standards drift checks, dependency and secret
  scanning, workflow analysis, release artifact signing/provenance, and consumer verification.

### Changed

- Reframed the project around a traceable measurement-to-claim path and community portability instead
  of treating the map as the product.
- Made SQLite plus generated files the explicit shipped store; Parquet/Arrow remains an unimplemented
  protocol extension.
- Made observation identity source-qualified and added a fail-closed transactional migration for
  pre-contract stores, including collision checks and atomic integrity-chain regeneration
  ([ADR 0024](docs/adr/0024-preserve-source-specific-data-terms.md)).
- Added pinned structured logging and a deterministic vendored MessageFormat build while retaining
  the standard-library server and framework-free browser architecture
  ([ADR 0025](docs/adr/0025-pinned-structured-logging.md),
  [ADR 0026](docs/adr/0026-vendored-messageformat-runtime.md)).
- Moved the authoritative architecture decision log from the legacy house-format `docs/decisions/`
  paths to `docs/adr/` while preserving old URLs. The historical context-layer collision moved from
  ADR 0013 to ADR 0023; accumulation/cache remains ADR 0013.
- Replaced blanket observation-data CC0 wording with a rights boundary that distinguishes authorized
  first-party, synthetic, fetched-provider, and context/reference data.

### Fixed

- Prevented raw and calibrated observations from being silently mixed in aggregation and publication.
- Prevented OpenAQ bounding-box spillover from being described as California and ensured retained
  locations use the normal public privacy grid.
- Prevented illustrative cooling-center/context fixtures and incomplete OpenAQ rights metadata from
  entering production artifacts.
- Added timeout, cache-invalidation, conditional-request, and stale-publication behavior to the
  read/static paths while preserving the single-reader design.
- Removed stale test counts, false current Parquet/latency/OTA claims, duplicated changelog sections,
  and unsupported manual accessibility/translation assertions from release-facing documentation.

### Security

- Added authenticated ingest, strict read/write separation, dependency/workflow/secret/static
  analysis, log-safety checks, least-privilege workflow defaults, signed release artifacts, build
  provenance, SBOM generation, and documented rollback/incident paths.
- Documented browser geolocation, local preference storage, service-worker/static caches, source
  adapters, GitHub Actions caches, precise node coordinates, and generated publication artifacts as
  explicit trust boundaries.
- The repository/Pages governance exception intentionally excluded from this remediation remains
  tracked in [issue #105](https://github.com/ChelseaKR/swelter/issues/105).

[Unreleased]: https://github.com/ChelseaKR/swelter/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/ChelseaKR/swelter/releases/tag/v0.1.0
