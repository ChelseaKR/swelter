<!-- Generated 2026-06-17 by a synthetic 12-persona think-aloud panel against the live demo.
     This is synthetic research (LLM personas exercising the real site/CLI/API/docs), not a
     substitute for testing with real community members — but every issue cites real code. -->

# swelter Dashboard — Synthetic User Research Report

## 1. Executive Summary

We ran a 12-persona synthetic think-aloud study against the live swelter dashboard, CLI, firmware, and API to learn whether a community heat & air-quality tool actually serves its mission: helping residents — especially vulnerable ones — understand local conditions, while staying scientifically honest. The study reveals a tool with an **exceptional, auditable data and trust foundation** sitting underneath a **public-facing layer that fails its primary residents.**

**Top takeaways:**

1. **The honesty engine is real and earns trust — but only experts ever see it.** Three independent technical personas (Dr. Chen, Alex the skeptic, Priya the reporter) *re-derived the published calibration registry byte-for-byte*. Calibrated-vs-raw separation, per-observation uncertainty, and the "we don't tell you you're safe" framing are genuine and verifiable. This is rarer and better than almost any community-sensor project. **However**, the published uncertainty/error bars **never reach the dashboard** — they live only in the CSV/API. The careful science is invisible to the people the map is for.

2. **Residents cannot find their own block, and the tool never answers their one question.** Every resident persona (Maria, Rosa, Eleanor, Tanya) hit the same wall: locations are anonymous "Cell 1…Cell 18" with no street/neighborhood names and no search or "near me." Combined with the absence of any plain-language "what does this mean / what should I do" bridge, **four of four residents either failed or only partially completed their core task.**

3. **Three competing number systems under one category word break comprehension.** Markers show a raw µg/m³ value, the table shows "AQI 59 — Moderate," and the legend shows "Moderate — 9 to 35" (µg/m³). Five personas independently froze on this exact contradiction. The math is correct; the *presentation* is not.

4. **A documentation-vs-reality gap quietly undermines the trust pitch.** Heat index is documented as calibrated but is **100% raw/provisional** (and shows physically impossible values up to 67 °C / 153 °F); NO2 is fully documented but **absent from all data**; the README advertises calibration "v2/v3" versions **that do not exist**; firmware's headline heat-index example is **off by 1.3 °C** versus the code. Every technical persona independently flagged these as trust-eroding overreach.

5. **Accessibility scaffolding is genuinely strong; mobile/i18n/elder paths are not.** The screen-reader experience (James) is "the real thing, not ARIA theatre" — but the time slider announces a meaningless bucket index. Spanish chrome is excellent (Rosa), but the **data itself reverts to English** ("Moderate", "Cell 1", "13:00 UTC"). Celsius-only readings make heat unusable for US residents and the policymaker.

The encouraging finding: **almost every blocker is in the presentation layer, not the data layer.** The hard part — trustworthy, reproducible science — is done.

---

## 2. Method & Panel

This was a **synthetic think-aloud panel**: 12 personas spanning swelter's real use cases, each given a realistic device context and a concrete goal, "thinking aloud" as they worked through tasks against the live demo (`127.0.0.1:8091`), the repo docs, the CLI, the firmware, and the API. Technical personas inspected source (`app.js`, `models.py`, `aggregate.py`, `calibrate.py`, `server.py`, firmware) and re-ran the pipeline; resident personas worked entirely through the UI on their stated devices.

| Persona | Role / context | What they did |
|---|---|---|
| **Maria, 34** | Parent, old Android, slow data, Spanish | Open on phone, switch to Spanish, find her block, decide if her kid can play outside |
| **Rosa, 52** | Spanish-monolingual, mid Android | Switch to Español, read her block's reading in the table/list/map |
| **James, 41** | Blind, NVDA + VoiceOver expert | Navigate by landmarks/headings/tablist, read via List & Table, operate slider, sort, export, audit semantics |
| **Eleanor, 78** | Low vision, hand tremor, low digital literacy, tablet @200% | Find her area, decide if it's safe to walk, understand the jargon |
| **Devon, 39** | Collective lead / network steward | Run `qc`, check node health, read governance/precision/ownership, test "right to leave," gauge maintenance |
| **Sam, 27** | Maker, soldering-comfortable | Build & flash a node, verify privacy claims in code, run end-to-end ingest |
| **Priya, 35** | Reporter on a heat story | Pull CSV, distinguish calibrated/provisional, find citable methodology, fact-check, cite heat data |
| **Dr. Chen** | Environmental-health researcher | Pull full history, assess SensorThings conformance, reproduce calibration, check uncertainty propagation |
| **Councilmember Ortiz, 58** | Policymaker, 60s at a podium | Name hottest blocks/worst air out loud, find a citable source, check Spanish parity |
| **Alex, 49** | Ex-regulatory scientist, sensor skeptic | Audit AQI math, averaging window, provisional handling, claims-vs-implementation |
| **Wei, 31** | Developer, API integration target | Test every endpoint, pagination, OData conformance, CORS, error handling, provenance |
| **Tanya, 36** | Anxious parent of asthmatic 7-yo, iPhone | Decide if her sensitive kid can go outside; check heat; try Spanish |

**Task success at a glance:** Failed — Maria, Eleanor. Partial — Rosa, Priya, Ortiz, Wei, Tanya. Completed — James, Devon, Sam, Dr. Chen, Alex. (Note: technical "completed" often means "I got the data despite the issues," not "the experience was good.")

---

## 3. Severity-Ranked Findings (Cross-Cutting)

| # | Theme | Severity | Personas affected | Evidence | Recommendation |
|---|---|---|---|---|---|
| F1 | **No "find my block" — cells are anonymous "Cell N" / bare lat,lon with no street/neighborhood and no search or "near me"** | **Critical** | Maria, Eleanor, Tanya, Ortiz, James (wishlist), Devon (reader-side) | `app.js` labels rows `Cell ${cellIndex}`; `cell_id` is e.g. `38.574605,-121.491604`; no geocode/search in `index.html`; `network.yaml` carries a node `label` that never reaches the dashboard | Surface the per-node human label (cross-street/neighborhood) from `network.yaml` through `surface.json` into map/table/list; add address search or "use my location" |
| F2 | **No plain-language interpretation or "what to do" — tool never bridges number → decision** | **Critical** | Maria, Eleanor, Tanya, (Ortiz, Rosa partial) | Footer only says "does not tell anyone they are safe → docs/calibration.md"; grep of `web/` for play/outside/children/limit/sensitive returns no guidance; only the legend label "Unhealthy for sensitive groups" exists | Add short, **sourced** per-category guidance ("Moderate: children with asthma may want shorter outdoor time — US EPA/CDC"). Context-with-source is *not* a safety promise — it's what the audit (A6) already claims is intended |
| F3 | **Three competing number scales under one word** — marker µg/m³, table "AQI 59", legend "Moderate — 9 to 35" (µg/m³), unexplained | **Critical** | Maria, Rosa, Eleanor, Tanya, Alex, (Ortiz) | `app.js` renders `AQI ${row.aqi} — ${category}`; legend `aqi-moderate` = "Moderate — 9 to 35" (µg/m³); marker shows `Math.round(mean)`. Math is correct (12.6 µg/m³ → AQI ~57) but the side-by-side is contradictory to a lay reader | Lead with **one** consumer scale (AQI) + the category word; make legend/marker/table speak the same scale; add a tap "what is AQI?" in EN/ES |
| F4 | **Provisional cells still wear an authoritative AQI value & category** — contradicts "never as fact" | **Critical** | Alex, Ortiz, Tanya, (Maria, Eleanor) | `aggregate.py` computes `pm25_aqi(mean)` regardless of provisional; 72/72 provisional PM2.5 cells carry non-null AQI; worst-air cell AQI 74 is provisional | Null/suppress AQI value & named category on provisional cells, or render "AQI not available — uncalibrated"; visually demote provisional |
| F5 | **Published uncertainty never reaches the UI** — error bars exist only in CSV/API, contradicting README & footer | **High** | Maria, James, Priya, Dr. Chen, Ortiz, Alex, Wei | `surface.json` cell keys lack `uncertainty`; CSV/registry carry it (13,704 calibrated rows populated); README ("shows AQI categories with their confidence") and footer ("a published uncertainty") overstate the UI | Propagate `residual_std` through `aggregate.py` into `surface.json`; render "31.0 °C ± 0.5" / "AQI 59 ±…" in table/list and map aria-label |
| F6 | **Data not localized in Spanish mode** — category word, "Cell", and UTC time stay English | **High** | Rosa, Maria, (Tanya, Ortiz noted parity of chrome) | `app.js` prints `row.category` ("Moderate") verbatim though `es.json` has `aqi-moderate`; "Cell N" hardcoded under "Celda" header; `fmtBucket()` emits "13:00 UTC" | Map API category → existing `es.json` keys; add `cell-label`/`Celda {n}`; localize time via `Intl.DateTimeFormat` |
| F7 | **Celsius-only temperature/heat index** — unusable for US residents & podium | **High** | Eleanor, Tanya, Maria(implied), Ortiz | `UNITS` maps `temp_c`/`heat_index_c` to "°C"; no toggle; live values 30–36 °C shown as bare "36" | Locale-default to °F for US deployments and/or add a clear °F/°C toggle; show the unit on the marker |
| F8 | **Doc-vs-data overreach: heat_index documented as calibrated but 100% raw/provisional**, with physically impossible values (up to 67 °C / 153 °F) | **High** | Priya, Dr. Chen, Alex, Tanya, Ortiz, Eleanor | `calibration.md`/`api.md` list `heat_index_c → enclosure-offset`; `grep -c heat_index corrections.yaml = 0`; surface max 67.26 °C; `models.py` range bound allows up to 80 °C | State plainly heat_index is published raw/provisional, **or** derive it from already-calibrated temp+humidity; tighten the plausibility ceiling toward a realistic NWS max |
| F9 | **Time slider's accessible value is a dimensionless bucket index (0…N), not the hour; two live regions double-announce on every move** | **High** | James (residents indirectly via UTC) | `index.html` slider has no `aria-valuetext`; `app.js` sets `slider.value` to integer index; both `#time-readout` (aria-live) and `#status` (role=status) fire per keypress | Set `aria-valuetext = fmtBucket(bucket)` each render; drop the timestamp from `#status` or debounce so it announces once |
| F10 | **No at-a-glance "worst/your-area-right-now" summary; table sorts ascending first** (worst lands at bottom) | **High** | Ortiz, Tanya, Maria, Eleanor | `app.js wireSort()` resets `sortDir` to ascending on a new key; no headline element exists | Add a one-line headline ("Worst confirmed air right now: [block], AQI N") and default value sort to worst-first |
| F11 | **`swelter qc` counts gaps but never lists them, and shows a degraded node (node-07) as healthy** | **High** | Devon, (Priya, Dr. Chen used qc) | `cli.py` prints only `len(gaps)`; node-07 = 1665 obs vs 1925 peers (260 missing) yet "online, 0.0% flagged"; README example literally says "node-07 offline" | Print each gap (node/param/start→end/duration); add an expected-vs-actual completeness column and a "degraded" status |
| F12 | **README/api.md drift: invented "v2/v3" calibration versions; doc coords & obs counts mismatch live demo** | **High** | Dr. Chen, Alex, Priya, Sam(heat ex.) | README "PM2.5 correction v3; temp enclosure-offset v2" — registry ids are `parameter.method.node`, no vN; README 41,902 vs live 48,094; api.md node-01 coords differ | Regenerate example blocks from the live demo or mark illustrative; fix README heat example to 35.23 and pin with a test |
| F13 | **SensorThings layer over-promises: `@iot.count` = page size not total; no pagination; `$top/$filter/$orderby` ignored; advertised Locations/Datastreams navlinks 404** | **High** | Wei, Dr. Chen | `$top=2` → 1000 rows; no `nextLink`; `/v1.1/Datastreams` 404; conformance lists `req/request-data` | Implement `nextLink`+`$skip`+true `@iot.count`, honor or drop OData options & the conformance claim, implement-or-remove advertised collections |
| F14 | **AQI computed from 24-hour EPA breakpoints applied to hourly (n=1) means, no NowCast, no disclosure** | **High** | Alex, (Dr. Chen, Priya implicitly) | `models.py` table is "24-hour averages"; `aggregate.py` builds `interval='hour'`, n=1; no caveat anywhere in `web/` | Implement NowCast-style weighting, or explicitly label values "hourly/instantaneous AQI (not 24-hour)" in legend, UI, and `surface.json` |
| F15 | **"Provisional" reads as "we're guessing/unreliable" to lay users — raises anxiety, lowers trust** | **High** | Maria, Eleanor, Tanya, (Rosa) | 6/18 PM2.5 cells provisional; all heat cells provisional; `provisional-note` uses "not-yet-confirmed, never as fact" | Warmer point-of-use wording ("early reading — still being double-checked") + a one-tap plain explanation; visually separate provisional from confirmed |
| F16 | **Heavy data payload on phones** — page fetches full 72h surface (~1.1 MB) to show one current moment | **High** | Maria | `/api/surface.json?hours=72` = 1,103,380 bytes; shell ~25 KB; `loadData()` always requests 72h | Default to a "latest snapshot" payload; lazy-load history on slider use; gzip the surface response |
| F17 | **Map is the default & hardest view; List/Table (easier for touch/tremor/SR) under-promoted; tiny crowded markers** | **Medium** | Eleanor, Maria, Tanya, (James prefers List) | Map tab selected by default; `.cell` font 0.72rem, min-width 2.6rem; overlapping markers at 360px | Default phones/touch to List; enlarge & space markers; prominent "read as a simple list" button |
| F18 | **CSV `calibration` column overloads "raw" + a version-id; no explicit provisional/status boolean** | **Medium** | Priya, Dr. Chen, Wei | `export.csv` col is either `raw` or `temp_c.enclosure-offset.node-01`; status only inferable | Add an explicit `provisional`/`status` boolean column to CSV & a field to `surface.json` |
| F19 | **Reference firmware as-shipped reads nothing** — both sensor drivers are unbound stubs with no linked known-good driver | **Medium** | Sam | `sampler.py` `Sht31.read()`/`PmSensor.read()` raise "driver not bound"; README sells "build & watch readings land" | Ship/link a working SHT31 driver + SDS011/PMS5003 frame parser, or a loud README warning up front |
| F20 | **Spanish calibration/trust explainer is English-only; footer steers everyone to engineer docs** | **Medium** | Rosa, Tanya, Eleanor, Maria | `es.json` footer points to `docs/calibration.md`; only English version exists; `/DATA-LICENSE` 404s (Priya) | Provide a Spanish in-page trust summary; serve a resident-facing "how to read this" link, not a repo path; serve DATA-LICENSE/LICENSE at stable URLs |
| F21 | **API rough edges:** HTML/Python-leak error bodies, OPTIONS preflight → 501, oldest-first ordering, raw+calibrated duplicate rows per timestamp, inconsistent `top` validation | **Medium** | Wei | `top=abc` → 400 HTML w/ Python text; OPTIONS → 501; `top` returns earliest; two rows per timestamp; `top=0`/`-5` → 200 empty | JSON error bodies; OPTIONS 204 w/ CORS headers; a "latest N"/desc option; document dedupe (prefer calibrated); uniform validation |
| F22 | **Slider ships min=max=0; not disabled on no-data; sort-by-Cell sorts hidden lat/lon not display index; sort actions not announced; tabpanel not focused on activation** | **Low** | James | `index.html` min/max 0/0; `wireSort` updates `aria-sort` silently; sort key `cell_id` ≠ displayed `Cell N` | `aria-disabled` on empty; sort by display index; announce "Sorted by Value, ascending, 16 rows"; `tabindex=-1` + focus the panel |

---

## 4. Journey Pain-Points by Stage

### Discover (open / orient / find me)
- **Stalls hardest here.** Maria & Eleanor never get past "which Cell is mine?" (**F1**). Eleanor faces *too many forks first* — pick a Measurement, understand an Hour slider, pick Map/Table/List — before any answer (**F17**).
- Maria stalls on **load weight** (~1.1 MB on slow data, **F16**) before she even sees the map.
- The map is the default but the **worst** view for touch/tremor/low-vision/SR users (Eleanor, Tanya, James) — none are guided to List/Table (**F17**).
- Rosa discovers the language switch instantly (a win) but then discovers the *data* isn't translated (**F6**).

### Understand (read the number / what does it mean)
- **The comprehension graveyard.** The 3-scale contradiction (**F3**) froze Maria, Rosa, Eleanor, Tanya, Alex. "AQI 60 — is that a good grade or bad?" (Eleanor). "59 isn't between 9 and 35" (Tanya).
- Jargon at point-of-use with no plain definition: PM2.5, µg/m³, AQI, "provisional" (Eleanor, Maria). Celsius-only heat (**F7**) reads as *cool* to Eleanor — "36? that sounds cool, but it's blazing outside."
- "Provisional" is misread as "unreliable," and it's stamped on the **scariest** numbers (Tanya, Maria, Eleanor) (**F15**). UTC time leaves residents unsure if a reading is "now or last night" (Maria, Rosa).

### Act / Decide (is it safe? what do I do?)
- **The mission gap.** No resident can complete this. The page explicitly won't say it's safe and offers **no bridge** to a decision (**F2**). Tanya: "I came here precisely to find out if it's safe. So now what?" Maria falls back to "look out the window and guess, like I always do."
- For the **policymaker**, Act = "name the worst block at the podium." He stalls on no place names (**F1**), ascending sort (**F10**), and — fatally — the worst cell and *all heat* being provisional (**F4/F8**), so he has no calibrated fact to state.

### Leave with the data / Operate
- **Strongest stage for experts.** Priya/Dr. Chen/Ortiz pull CC0 CSV with no account and reproduce calibration byte-for-byte. But Priya hits the **DATA-LICENSE 404** following the citation trail, can't get on-screen error bars (**F5**), and can't responsibly cite heat (**F8**).
- **Dr. Chen / Alex / Wei** must abandon the aggregated surface (no uncertainty, n=1) and the `/v1.1` SensorThings layer (**F13**), falling back to per-observation `/export.*` and `/api/surface.json`.
- **Devon (operate)** runs `qc` instantly but it under-reports exactly the failure a steward exists to catch (**F11**); governance/ownership/precision are the best he's seen.
- **Sam (build)** completes end-to-end ingest with verified privacy-by-construction, but the reference firmware reads nothing as-shipped (**F19**) and the headline heat example is wrong (**F12**).

---

## 5. What Works Well (Don't Lose This)

- **Reproducible, auditable calibration.** Priya, Dr. Chen, and Alex each **re-ran `swelter calibrate` and reproduced the registry byte-for-byte / MD5-identical** (`8c8b3b18…`). "That is exactly the 'check rather than trust' promise delivered." (Dr. Chen). The math is correct (Alex recomputed AQI by hand; pm25_aqi handles EPA truncation & band gaps correctly).
- **Calibrated-vs-raw is never silently mixed** across store, CSV, API, and UI; provenance (`parameter.method.node`) travels with every value (Devon, Dr. Chen, Wei, Sam).
- **The "we don't tell you you're safe" guardrail** is the right posture and *builds* credibility with experts and even the anxious parent ("made me believe they're not lying to me" — Tanya; "earns my trust more than a green number ever would" — James).
- **Accessibility is the real thing, not theatre** (James): real landmarks, one h1, sectioned h2s incl. a visually-hidden "Controls", a genuine `tablist` with roving tabindex + arrow keys, a semantic table (caption, `scope=col/row`, working `aria-sort`), a List view as a true non-visual map equivalent, provisional state in **words not just color**, visible focus everywhere, honors reduce-motion. An honest ACR/VPAT that self-marks cognitive load as only "Partially Supports."
- **Spanish chrome is excellent** — natural, instant, no reload; legend categories, provisional note, and the safety framing read like real translation, 33/33 keys (Rosa, Maria, Ortiz, Tanya).
- **No account, no login, no cookie wall, no tracking, no location request** — "I could just open it and look" (Maria, Tanya).
- **Open data is frictionless & citable** — CC0 with a ready attribution line, filterable CSV/JSON, no key (Priya, Ortiz, James, Dr. Chen).
- **Governance & ownership are the best seen** (Devon): written for a block club, "right to leave," CC0 data + Apache code, coarse-by-default location precision **enforced in the API** (not just promised), honest about CC0 permanence. Realistic, low maintenance burden.
- **Privacy-by-construction is verifiable in code** (Sam): grepping the firmware finds *zero* mic/camera/BT/GPS drivers — the schema has no field that could locate a person. Idempotent store-and-forward behaved exactly as documented.
- **Clean read-only API shape** where it's flat: `/api/surface.json`, `/export.*`, 405 on writes, 60s caching, CORS on GETs, stable composite `@iot.id` (Wei).

---

## 6. Accessibility, Language & Mobile Findings

**Accessibility (screen reader — James, low-vision/tremor — Eleanor, asthma parent @large-text — Tanya):**
- *Strong base, one sharp failure:* the **time slider announces "slider, 7"** — a bucket index, not the hour — and **double-announces** via two live regions on every move (**F9**). This is the single a11y fix that gates James's recommendation. Fix: `aria-valuetext = fmtBucket(bucket)`, one announcement per change.
- Smaller SR rough edges (**F22**): sort changes are silent; sort-by-Cell uses the hidden lat/lon; slider isn't disabled when there's no data; tabpanel isn't focused on activation.
- For **tremor/low-vision**: markers are technically ≥24px but well below comfortable; List/Table are easier but under-promoted (**F17**). Zoom-to-200% reflow is clean (Eleanor) — keep it.
- Text-in-words for severity/provisional (not color-only) is a genuine win — preserve it when adding guidance.

**Language (Rosa, Maria, Ortiz, Tanya):**
- Chrome localization is excellent; **the data is not** (**F6**): category word ("Moderate"), "Cell N", and "13:00 UTC" stay English/UTC in Español. "Half-Spanish data and two unexplained scales is not enough to feel sure." (Rosa).
- The trust/calibration explainer the Spanish footer links to is **English-only** (**F20**); "AQI" isn't localized to "ICA."
- **Parity caveat:** because Spanish parity is otherwise complete, **any new health guidance (F2) must ship in both bundles at once**, or the gap is duplicated (Tanya).

**Mobile (Maria, Tanya, Eleanor on tablet):**
- **Payload is the mobile blocker** — ~1.1 MB to show one moment on a slow plan (**F16**). "The kind of page I'd back out of."
- Default-to-Map is wrong for phones (**F17**); UTC time is meaningless on a phone clock; markers crowd/overlap at 360px.
- *Wins to keep:* small shell, fast first paint, newest hour selected by default, no account/cookie wall.

---

## 7. Trust & Public-Health Framing Findings

The "calibrated vs raw / provisional / published uncertainty / we-don't-tell-you-you're-safe" model is the project's spine. **It lands very differently by audience, and the same honesty that earns expert trust strands residents.**

- **Residents (Maria, Eleanor):** The guardrail reads as *honest but useless.* "Honesty without help doesn't earn my trust either." (Maria). "Provisional" = "you don't really know" lowers trust on the *whole* page; being told repeatedly that things are "not yet confirmed" makes them *nervous, not reassured.* The promised error bars are invisible, so "the careful part is invisible to me."
- **Anxious parent (Tanya):** *High trust in the people, low confidence she can act.* The honesty "made me believe they're not lying" — but the scariest readings (high-AQI cells, 153 °F heat) are all the **provisional** ones, which reads as "the data is shaky exactly when it matters most." She left **more anxious than she arrived.** The guardrail "lands cold" without a "what to do" next step.
- **Reporter (Priya):** *Trust earned the right way* — she re-derived the error bars byte-for-byte. But heat (her story) is 100% provisional, shown without error bars, and the map will plot a 153 °F single reading; she "would NOT cite a heat-index figure off this map." Wants the caveat to **survive a screenshot** and the on-screen ±.
- **Policymaker (Ortiz):** The honesty is *credibility* he can defend publicly ("calibrated against reference monitors, EPA-lineage, open data") — but it **exposes him at the podium**: the worst block and all heat are provisional ("don't state as fact"), and the promised uncertainty isn't on screen. "A strong source for the record, not a podium-ready talking point."
- **Skeptic (Alex):** *The decisive verdict.* "Trustworthy at the data layer and overreaching at the presentation layer — and residents only see the presentation layer." Three breaches of the project's own promises: **provisional cells wear EPA AQI categories** (**F4**); **hourly concentrations run through a 24-hour table with no NowCast/warning** (**F14**); **uncertainty dropped before the screen** (**F5**); plus README claims ("shows AQI categories with their confidence") the UI doesn't keep.

**Synthesis:** The guardrail is correct and must stay. The failure is that it currently *only* says "no" — it withholds without offering sourced context. Pairing the disclaimer with **non-prescriptive, sourced guidance** (F2), **surfacing the uncertainty** (F5), **not stamping AQI on provisional cells** (F4), and **disclosing the hourly-vs-24h window** (F14) would let the honesty *build* resident trust instead of stranding it — without ever promising personal safety.

---

## 8. Prioritized Recommendations

### P0 — Blocking the mission (residents cannot complete their core task / project promises are broken on screen)

| Rec | Addresses | Component/file |
|---|---|---|
| **Add "find my block":** pipe each node's `label` (cross-street/neighborhood) from `network.yaml` → `surface.json` → map/table/list; add address search or "use my location" | F1 | `aggregate.py`, `server.py`, `web/app.js` (`describe`/`renderTable`/`renderMap`), `index.html` |
| **Add sourced plain-language interpretation per category** ("Moderate: children with asthma may want shorter outdoor time — US EPA") in EN **and** ES; pair the disclaimer with a resident "how to read this" link, not `docs/calibration.md` | F2, F20, parity | `web/i18n/en.json`+`es.json`, `index.html` footer, `app.js` |
| **One consumer scale:** lead with AQI + category word; make legend/marker/table speak the same scale; add a tap "what is AQI?" (EN/ES) | F3 | `web/i18n/*.json`, `app.js`, `index.html` legend |
| **Stop labeling provisional cells with AQI categories** — null/suppress AQI & named category on provisional cells (or "AQI not available — uncalibrated"); visually demote | F4, F15 | `aggregate.py` (don't `pm25_aqi(mean)` when provisional), `app.js`, `styles.css` |
| **Surface uncertainty in the UI** — propagate `residual_std` into `surface.json` and render "± value" in table/list and map aria-label (also fixes README/footer overreach) | F5 | `aggregate.py`, `server.py`, `app.js` |
| **Localize the data, not just the chrome** — map API category → `es.json` keys; add `Celda {n}`; localize time to user locale/zone | F6 | `app.js` (`describe`/`renderTable`/`renderMap`/`fmtBucket`), `es.json` |
| **Fix heat index:** publish it honestly as raw/provisional **and** show a clear "no calibrated heat readings yet" banner, **or** derive from calibrated temp+humidity; tighten the plausibility ceiling | F8 | `models.py`, `calibrate.py`, `aggregate.py`, `app.js` |

### P1 — Severely degrades a key segment

| Rec | Addresses | Component/file |
|---|---|---|
| **°F support** (US locale default and/or labeled toggle); show units on markers | F7 | `app.js` `UNITS`, `index.html` |
| **Slider `aria-valuetext = fmtBucket(bucket)`; one announcement per change** (drop timestamp from `#status` or debounce) | F9 | `app.js`, `index.html` |
| **"Worst right now" headline card + worst-first default sort** | F10 | `app.js` (`wireSort` default dir), `index.html` |
| **`swelter qc` should list gaps and flag degraded nodes** (completeness column / "degraded" status); add `--json` | F11 | `cli.py`, `qc.py` |
| **Reconcile docs with live data:** remove/fix "v2/v3" versions, regenerate README/api.md examples, fix firmware heat example to 35.23 (+ a checked-in test) | F12 | `README.md`, `docs/api.md`, `firmware/README.md`, firmware test |
| **API: real `@iot.count` + pagination (`nextLink`/`$skip`); honor or drop OData options & SensorThings conformance; implement-or-remove advertised collections/navlinks** | F13 | `server.py`, `docs/api.md` |
| **Disclose the AQI averaging window** (NowCast, or label values "hourly/instantaneous AQI, not 24-hour") in UI, legend, `surface.json` | F14 | `aggregate.py`, `models.py`, `app.js`, `index.html` |
| **Lighten mobile load:** default to a latest-snapshot payload, lazy-load history, gzip surface | F16 | `app.js` `loadData()`, `server.py` |
| **Default phones/touch to List; promote List/Table; enlarge & space markers** | F17 | `app.js` (default view), `styles.css` |
| **Warmer "provisional" wording + one-tap plain explanation; separate provisional from confirmed visually** | F15 | `web/i18n/*.json`, `app.js`, `styles.css` |

### P2 — Polish, correctness, and developer/researcher experience

| Rec | Addresses | Component/file |
|---|---|---|
| Serve `DATA-LICENSE`/`LICENSE` at stable URLs (or link CC0 legalcode) | F20 | `server.py`, `index.html`/`en.json` |
| Add explicit `provisional`/`status` boolean column to CSV/JSON exports | F18 | `export`/`server.py` |
| Ship/link working SHT31 + SDS011/PMS5003 drivers, or a loud README warning; check in a firmware test; OTA "not implemented" banner; pin MicroPython/esptool notes | F19 | `firmware/src/sampler.py`, `firmware/README.md`, `assembly.md` |
| JSON error bodies; OPTIONS 204 + CORS headers; "latest N"/desc order; document raw+calibrated dedupe; uniform `top` validation; `geo+json` content-type; trailing-slash normalization | F21 | `server.py`, `docs/api.md` |
| SR polish: announce sort, sort by display index, disable slider on no-data, focus tabpanel on activation | F22 | `app.js`, `index.html` |
| Ship the "add your neighborhood in an afternoon" guide + governance-log template; add a public "about this network / coverage / coarse-locations" note | Devon wishlist, F5(reader-side) | `docs/`, `index.html` |
| Expose registry over the API; DOI/versioned snapshot + citation string; "how to cite" methods snippet | Dr. Chen/Priya wishlist | `server.py`, `README.md` |

---

## 9. Representative Verbatim Quotes

- **Maria (parent, Spanish, old phone):** "I'm standing in my kitchen with my kid asking to go out. I don't have time for [a calibration document]." … "I still don't know if she can go outside. I'd probably just look out the window and guess, like I always do."
- **Rosa (Spanish-only):** "¿Por qué dice 'Cell 1'? La columna se llama 'Celda' pero la fila dice 'Cell'. No combinan." … "La parte en español me da confianza, pero los números en inglés y las dos escalas distintas me hacen dudar."
- **James (blind, NVDA):** "'Hour, slider, 7.' Seven what? … The control itself should TELL me '2 PM, June 16' — that's what aria-valuetext is for and it isn't here." … "This is one of the few community dashboards I can fully operate without the map … not ARIA theatre."
- **Eleanor (78, low vision):** "AQI 60, Moderate. Is 60 a good grade or a bad grade? In school 60 was barely passing." … "Down at the very bottom it says this page 'does not tell anyone they are safe.' Well then what is it FOR?"
- **Tanya (asthma parent):** "The heat index says 67. Sixty-seven what? Celsius — that's 153 degrees Fahrenheit?! … Oh, it's 'provisional' too." … "I left more anxious than I arrived."
- **Devon (steward):** "It tells me a number and then makes me go hunting. That's the one thing I actually need at 2 a.m." … "My health tool is blind to my one sick node."
- **Sam (maker):** "The only hits are the comments saying 'no mic/camera/BT.' … it's true by construction, not by promise. That's the most reassuring thing in this whole repo." … "The doc literally says 'agree to the rounding' right above a number that doesn't."
- **Priya (reporter):** "I can re-run their calibration and it matches their published file to the byte. That's the moment I started trusting this." … "If I screenshot [67 °C = 153 °F] for a story I'd be putting the network's flimsiest number on the front page."
- **Dr. Chen (researcher):** "MD5-identical. That is exactly the 'check rather than trust' promise delivered. This is rare." … "Every per-observation value carries a 1-sigma error bar, and then aggregation throws it away."
- **Councilmember Ortiz:** "I can't stand up and say 'Cell 7 is the worst,' nobody knows where Cell 7 is." … "The worst reading is one the system tells me NOT to state as fact."
- **Alex (skeptic):** "Trustworthy at the data layer and overreaching at the presentation layer — and residents only see the presentation layer." … "A named EPA category on data the network admits it can't stand behind is the worst case."
- **Wei (developer):** "It looks like SensorThings but doesn't behave like it." … "I'd build against /api/surface.json and /export.json — those are flat, honest, and predictable."

---

## 10. Usability Scorecard

Scale: 1 (unusable for this user) – 5 (excellent).

| Persona / segment | Score | One-line rationale |
|---|---|---|
| **Maria** — parent, old phone, Spanish | **2 / 5** | Honest and clean, but heavy payload, no block names, 3 fighting numbers, and no answer — fell back to guessing. |
| **Rosa** — Spanish-monolingual | **2 / 5** | Excellent Spanish chrome, but the data she came for stays in English with two unexplained scales. |
| **James** — blind, expert SR | **4 / 5** | Genuinely operable non-visually with real semantics; held back from 5 only by the slider's meaningless value & double-announce. |
| **Eleanor** — 78, low vision/tremor | **1 / 5** | Couldn't find her block, couldn't read Celsius/jargon, no "what to do" — task failed even with help. |
| **Devon** — steward | **4 / 5** | Best-in-class governance/ownership/precision; qc under-reports the one failure a steward exists to catch. |
| **Sam** — maker | **4 / 5** | Privacy-by-construction and end-to-end pipeline genuinely work; unbound drivers + a wrong doc number dent it. |
| **Priya** — reporter | **3.5 / 5** | Model reproducible dataset for PM/temp; heat (her story) uncitable, on-screen ± missing, license link 404. |
| **Dr. Chen** — researcher | **4 / 5** | Calibration is reproducible and sound; must avoid the uncertainty-stripped surface and doc-vs-data schema gaps. |
| **Ortiz** — policymaker | **3 / 5** | Credible, citable source for the record; not podium-ready (no block names, all-provisional heat, no on-screen ±, Celsius). |
| **Alex** — skeptic | **3.5 / 5** (data 5 / UI 2) | Audited the math and it holds; the presentation layer breaks the engine's own promises. |
| **Wei** — developer | **3.5 / 5** | Flat `/api` + `/export` are clean and honest; the branded `/v1.1` SensorThings surface isn't shippable as-is. |
| **Tanya** — anxious asthma parent | **2 / 5** | Trusts their honesty, but no guidance, scary provisional/Celsius heat, and no decision — left more anxious. |
| **Resident segment (overall)** | **1.5 / 5** | The mission audience can't find their block or get a decision; the careful science is invisible to them. |
| **Expert segment (overall)** | **4 / 5** | Reproducible, auditable, well-governed, open — strong via the flat data paths, once doc overreach is reconciled. |

**Bottom line:** swelter has built the hard, rare thing — a reproducible, honest, well-governed data foundation that experts verified by re-deriving it. It has not yet built the easy-sounding, essential thing: a presentation layer that lets a parent find her block, read one clear number, understand what it means, and decide — without ever being told she's "safe." Close the P0 gaps and the mission audience inherits the trust the experts already feel.
