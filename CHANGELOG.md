# Changelog

All notable changes to swelter are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the public API/data schema follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html) as scoped in
[`docs/VERSIONING.md`](docs/VERSIONING.md).

## [Unreleased]

### Added

- **Purpose-first project planner.** A no-account decision guide at `/planner/` asks six bounded,
  non-personal questions and recommends public data, a governance or stewardship pause, a bounded
  pilot, or staged operation. “Do not deploy” is a first-class outcome; raw readings cannot unlock
  expansion without a calibration path. Plans are calculated in the browser and can be copied or
  printed without storing or transmitting answers ([ADR 0044](docs/adr/0044-purpose-first-project-planner.md)).
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
