// Unit tests for `web/app.js`'s pure, function-scoped dashboard logic (FIX-07): unit conversion,
// category ordering, trend/contrast lines, and `t()` fallback. Run with `node --test` (see
// `package.json`); loads app.js unmodified via `tests/harness.js`, never a copy or a rewrite.

"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { loadApp } = require("./harness.js");

// A fresh vm-loaded app.js per test — cheap, and avoids one test's mutation of the shared `state`
// object leaking into the next (the same isolation `beforeEach` would give, made explicit here so
// each `test()` block stays a single, readable unit).
async function freshApp() {
  return loadApp();
}

test("heatTier — NWS heat-index tiers from a Celsius value", async () => {
  const app = await freshApp();
  assert.equal(app.heatTier(20), "None");
  assert.equal(app.heatTier(26.7), "Caution");
  assert.equal(app.heatTier(32.2), "Extreme Caution");
  assert.equal(app.heatTier(39.4), "Danger");
  assert.equal(app.heatTier(51.1), "Extreme Danger");
  assert.equal(app.heatTier(60), "Extreme Danger");
  // Band floors are inclusive; just under a floor stays in the tier below.
  assert.equal(app.heatTier(39.39), "Extreme Caution");
});

test("heatClass — map shading bins on the Celsius mean regardless of display unit", async () => {
  const app = await freshApp();
  assert.equal(app.heatClass(10), "heat-1");
  assert.equal(app.heatClass(24), "heat-2");
  assert.equal(app.heatClass(28), "heat-3");
  assert.equal(app.heatClass(32), "heat-4");
  assert.equal(app.heatClass(40), "heat-5");
});

test("round1 — rounds to one decimal place", async () => {
  const app = await freshApp();
  assert.equal(app.round1(1.24), 1.2);
  assert.equal(app.round1(1.25), 1.3);
  assert.equal(app.round1(-1.25), -1.2); // Math.round rounds -1.25*10=-12.5 toward +Infinity
  assert.equal(app.round1(0), 0);
});

test("convert — Celsius-based parameters convert to Fahrenheit only when the unit toggle is F", async () => {
  const app = await freshApp();
  app.state.parameter = "temp_c";

  app.state.unit = "C";
  assert.equal(app.convert(0), 0);

  app.state.unit = "F";
  assert.equal(app.convert(0), 32);
  assert.equal(app.convert(100), 212);
  assert.equal(app.convert(20), 68);
});

test("convert — non-temperature parameters are never converted", async () => {
  const app = await freshApp();
  app.state.parameter = "pm25_ugm3";
  app.state.unit = "F"; // the toggle is temperature-only; must not leak into µg/m³
  assert.equal(app.convert(12.345), 12.345);
});

test("fmtValue / fmtUncertainty — value and its published 1-sigma uncertainty share one conversion", async () => {
  const app = await freshApp();
  app.state.parameter = "temp_c";
  app.state.unit = "F";
  assert.equal(app.fmtValue(20), "68 °F");
  assert.equal(app.fmtUncertainty(1.0), " ± 1.8"); // 1.0 C -> 1.8 F, scaled not offset
  assert.equal(app.fmtUncertainty(null), "");

  app.state.unit = "C";
  assert.equal(app.fmtValue(20), "20 °C");

  app.state.parameter = "pm25_ugm3";
  assert.equal(app.fmtValue(12.34), "12.3 µg/m³");
});

test("unitLabel — base unit per parameter, temperature respects the toggle", async () => {
  const app = await freshApp();
  app.state.parameter = "pm25_ugm3";
  assert.equal(app.unitLabel(), "µg/m³");
  app.state.parameter = "no2_ppb";
  assert.equal(app.unitLabel(), "ppb");
  app.state.parameter = "temp_c";
  app.state.unit = "C";
  assert.equal(app.unitLabel(), "°C");
  app.state.unit = "F";
  assert.equal(app.unitLabel(), "°F");
});

test("t() — falls back to the raw key when no strings are loaded (harness loads none)", async () => {
  const app = await freshApp();
  assert.equal(app.t("cat-good"), "cat-good");
  assert.equal(app.t("some-key-that-does-not-exist"), "some-key-that-does-not-exist");
});

test("t() — prefers a loaded string over the raw-key fallback", async () => {
  const app = await freshApp();
  app.state.strings = { "cat-good": "Good (es)" };
  assert.equal(app.t("cat-good"), "Good (es)");
});

test("t() — MessageFormat 2 selects plural forms and localizes the count", async () => {
  const app = await freshApp();
  app.document.documentElement.lang = "en";
  app.state.strings = {
    items: ".input {$n :number}\n.match $n\none {{{$n} reading}}\n* {{{$n} readings}}",
  };
  assert.equal(app.t("items", { n: 1 }), "1 reading");
  assert.equal(app.t("items", { n: 2 }), "2 readings");

  app.document.documentElement.lang = "es";
  app.state.strings = {
    items: ".input {$n :number}\n.match $n\none {{{$n} lectura}}\n* {{{$n} lecturas}}",
  };
  assert.equal(app.t("items", { n: 1 }), "1 lectura");
  assert.equal(app.t("items", { n: 2 }), "2 lecturas");
});

test("formatNumber — uses the document locale for grouping and decimal separators", async () => {
  const app = await freshApp();
  app.document.documentElement.lang = "en";
  assert.equal(app.formatNumber(12345.6, { maximumFractionDigits: 1 }), "12,345.6");
  app.document.documentElement.lang = "es";
  assert.equal(app.formatNumber(12345.6, { maximumFractionDigits: 1 }), "12.345,6");
});

test("localeDirection — recognizes RTL language tags while keeping shipped locales LTR", async () => {
  const app = await freshApp();
  assert.equal(app.localeDirection("en-US"), "ltr");
  assert.equal(app.localeDirection("es-MX"), "ltr");
  assert.equal(app.localeDirection("ar"), "rtl");
  assert.equal(app.localeDirection("he-IL"), "rtl");
});

test("localizeDocumentMetadata — preserves Pages metadata on catalogue failure", async () => {
  const app = await freshApp();
  app.document.title = "Source-aware Pages title";
  app.state.strings = {};
  app.localizeDocumentMetadata();
  assert.equal(app.document.title, "Source-aware Pages title");
});

test("localizeDocumentMetadata — prefers the loaded source-specific translation", async () => {
  const app = await freshApp();
  app.state.demo = { source: { id: "openaq" } };
  app.state.strings = {
    "document-title": "Generic title",
    "document-title-openaq": "OpenAQ source title",
  };
  app.localizeDocumentMetadata();
  assert.equal(app.document.title, "OpenAQ source title");
});

test("loadStrings — the latest language request wins an out-of-order race", async () => {
  const app = await freshApp();
  const pending = new Map();
  app.fetch = (url) =>
    new Promise((resolve) => {
      pending.set(url, resolve);
    });
  const spanish = app.loadStrings("es");
  const english = app.loadStrings("en");
  pending.get("i18n/en.json")({ ok: true, json: async () => ({ language: "English" }) });
  assert.equal(await english, true);
  pending.get("i18n/es.json")({ ok: true, json: async () => ({ language: "Español" }) });
  assert.equal(await spanish, false);
  assert.equal(app.state.strings.language, "English");
  assert.equal(app.document.documentElement.lang, "en");
  assert.equal(app.document.documentElement.dir, "ltr");
});

test("loadStrings — a failed swap retains the prior catalogue and document language", async () => {
  const app = await freshApp();
  app.state.strings = { language: "Español" };
  app.document.documentElement.lang = "es";
  app.fetch = async () => ({ ok: false, json: async () => ({}) });
  assert.equal(await app.loadStrings("en"), false);
  assert.equal(app.state.strings.language, "Español");
  assert.equal(app.document.documentElement.lang, "es");
});

test("localCategory / localExposure / localHeat — map a known label to its i18n key", async () => {
  const app = await freshApp();
  app.state.strings = {
    "cat-good": "Good",
    "exp-elevated": "Elevated",
    "heat-danger": "Danger",
  };
  assert.equal(app.localCategory("Good"), "Good");
  assert.equal(app.localExposure("Elevated"), "Elevated");
  assert.equal(app.localHeat("Danger"), "Danger");
  // An unmapped/unknown label passes through unchanged rather than throwing.
  assert.equal(app.localCategory("Not A Real Category"), "Not A Real Category");
});

test("guidanceFor / heatGuidanceFor — resolve to the i18n guidance key for a known category", async () => {
  const app = await freshApp();
  assert.equal(app.guidanceFor("Good"), "guide-good");
  assert.equal(app.guidanceFor("Hazardous"), "guide-haz");
  assert.equal(app.guidanceFor("not a category"), "");
  assert.equal(app.heatGuidanceFor("Danger"), "heat-guide-danger");
  // "None" maps to the "none" slug, which is deliberately silent (no guidance for calm conditions).
  assert.equal(app.heatGuidanceFor("None"), "");
});

test("describe — plain-language reading line, confirmed vs provisional framing", async () => {
  const app = await freshApp();
  app.state.cells = [{ cell_id: "c1", bucket: "2026-06-01T00:00:00Z" }];
  app.indexCells();
  app.state.parameter = "pm25_ugm3";

  // No i18n strings are loaded in this harness (by design — see t()'s own tests), so `t()` falls
  // back to the raw key; "cell-word" and "state-provisional" below are that fallback, not English
  // prose. `placeName()`'s numbering comes from `indexCells()` (1-based, sorted cell_id order).
  const confirmed = { cell_id: "c1", mean: 12, aqi: 45, category: "Good", provisional: false };
  assert.match(app.describe(confirmed), /^cell-word 1: AQI 45, /);
  assert.doesNotMatch(app.describe(confirmed), /state-provisional/);

  const provisional = { ...confirmed, provisional: true };
  assert.match(app.describe(provisional), /^cell-word 1: ~AQI 45 \(state-provisional\)/);
});

test("MessageFormat 2 substitutes values literally and isolates mixed-direction text", async () => {
  const app = await freshApp();
  app.state.strings = { greeting: "hi {$place}!" };
  assert.equal(app.t("greeting", { place: "Cedar & 4th$&Ave" }), "hi ⁨Cedar & 4th$&Ave⁩!");
  assert.equal(app.t("greeting", { place: "weird$`prefix" }), "hi ⁨weird$`prefix⁩!");
  assert.equal(app.t("greeting", { place: "trail$$ing" }), "hi ⁨trail$$ing⁩!");

  app.document.documentElement.lang = "ar";
  app.document.documentElement.dir = "rtl";
  app.state.strings = { greeting: "الموقع: {$place}." };
  assert.equal(app.t("greeting", { place: "Oak & 4th — محطة" }), "الموقع: ⁨Oak & 4th — محطة⁩.");
});

test("readingText — strips only the place-name prefix, even when the label itself contains ': '", async () => {
  const app = await freshApp();
  app.state.cells = [{ cell_id: "c1", bucket: "2026-06-01T00:00:00Z" }];
  app.indexCells();
  app.state.parameter = "pm25_ugm3";

  const row = {
    cell_id: "c1",
    label: "Ward 3: Uptown", // a host-chosen label that itself contains the "place: reading" separator
    mean: 12,
    aqi: 45,
    category: "Good",
    provisional: false,
  };
  // A naive `describe(row).split(": ").slice(1).join(": ")` would drop only up to the *first*
  // ": " and leak "Uptown" (the second half of the label) into the reading text.
  assert.equal(app.readingText(row), app.describe(row).slice(`${row.label}: `.length));
  assert.doesNotMatch(app.readingText(row), /^Uptown:/);
});

test("compareDiff — category parameters compare ordinal severity, never raw numbers", async () => {
  const app = await freshApp();
  app.state.cells = [
    { cell_id: "a", bucket: "2026-06-01T00:00:00Z" },
    { cell_id: "b", bucket: "2026-06-01T00:00:00Z" },
  ];
  app.indexCells();
  app.state.parameter = "pm25_ugm3";

  const worse = { cell_id: "a", category: "Unhealthy", provisional: false };
  const better = { cell_id: "b", category: "Good", provisional: false };
  assert.equal(app.compareDiff(worse, better), "compare-worse");
  assert.equal(app.compareDiff(better, worse), "compare-better");
  assert.equal(app.compareDiff(worse, worse), "compare-same");
});

test("compareDiff — numeric (temperature) parameters compare converted values and flag provisional", async () => {
  const app = await freshApp();
  app.state.cells = [
    { cell_id: "a", bucket: "2026-06-01T00:00:00Z" },
    { cell_id: "b", bucket: "2026-06-01T00:00:00Z" },
  ];
  app.indexCells();
  app.state.parameter = "temp_c";
  app.state.unit = "C";

  const hot = { cell_id: "a", mean: 30, provisional: false };
  const cool = { cell_id: "b", mean: 20, provisional: true };
  const line = app.compareDiff(hot, cool);
  assert.match(line, /^compare-hotter/);
  assert.match(line, /compare-provisional$/); // either side provisional -> the comparison is flagged rough
});

test("watchCrossed — category watches compare ordinal position, never raw numbers", async () => {
  const app = await freshApp();
  const row = { parameter: "pm25_ugm3", category: "Unhealthy", mean: 200 };
  assert.equal(app.watchCrossed(row, { kind: "cat", idx: 2 }), true); // Unhealthy is index 3
  assert.equal(app.watchCrossed(row, { kind: "cat", idx: 5 }), false);
  assert.equal(app.watchCrossed(row, { kind: "num", value: 10 }), false); // wrong watch kind
});

test("watchCrossed — heat-index watches derive the tier from the mean, not a stored category", async () => {
  const app = await freshApp();
  const row = { parameter: "heat_index_c", mean: 40, category: null };
  assert.equal(app.watchCrossed(row, { kind: "cat", idx: 2 }), true); // 40C -> "Danger" -> index 2
  assert.equal(app.watchCrossed(row, { kind: "cat", idx: 3 }), false);
});

test("watchCrossed — numeric parameters compare in base units, unaffected by the display toggle", async () => {
  const app = await freshApp();
  app.state.unit = "F"; // must not change the verdict — the watch value is stored in base units
  const row = { parameter: "no2_ppb", mean: 55 };
  assert.equal(app.watchCrossed(row, { kind: "num", value: 50 }), true);
  assert.equal(app.watchCrossed(row, { kind: "num", value: 60 }), false);
});

test("activeAlerts — historical slider positions never arm a personal alert", async () => {
  const app = await freshApp();
  const historical = new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString();
  const latest = new Date(Date.now() - 30 * 60 * 1000).toISOString();
  app.setData({
    buckets: [historical, latest],
    cells: [
      { cell_id: "c1", label: "Cedar", parameter: "temp_c", bucket: historical, mean: 40 },
      { cell_id: "c1", label: "Cedar", parameter: "temp_c", bucket: latest, mean: 20 },
    ],
  });
  app.state.parameter = "temp_c";
  app.state.bucketIdx = 0;
  app.saveWatch("c1|temp_c", { kind: "num", value: 30 });
  assert.equal(app.activeAlerts().length, 0);

  app.state.cells.find((row) => row.bucket === latest).mean = 40;
  const alerts = app.activeAlerts();
  assert.equal(alerts.length, 1);
  assert.equal(alerts[0].row.bucket, latest);
  assert.equal(app.state.bucketIdx, 0); // evaluation never moves the evidence cursor
});

test("temporalContextText — historical and stale observations are explicitly non-current", async () => {
  const app = await freshApp();
  const historical = "2025-01-01T00:00:00Z";
  const staleLatest = "2025-01-02T00:00:00Z";
  app.state.buckets = [historical, staleLatest];
  app.state.strings = {
    "observation-historical": "Historical {$time} — not current.",
    "observation-stale": "Stale {$time} — not current.",
  };
  app.state.bucketIdx = 0;
  assert.match(app.temporalContextText(), /^Historical .*not current\.$/);
  app.state.bucketIdx = 1;
  assert.match(app.temporalContextText(), /^Stale .*not current\.$/);
  assert.equal(app.isFreshObservation(), false);
});

test("contrastLine — needs at least 3 peers to say anything", async () => {
  const app = await freshApp();
  app.state.parameter = "pm25_ugm3";
  app.state.cells = [
    { cell_id: "a", bucket: "h1", parameter: "pm25_ugm3", mean: 10 },
    { cell_id: "b", bucket: "h1", parameter: "pm25_ugm3", mean: 20 },
  ];
  assert.equal(app.contrastLine({ cell_id: "a", bucket: "h1", mean: 10 }), "");
});

test("contrastLine — the network-wide top reading says so without a rank count", async () => {
  const app = await freshApp();
  app.state.parameter = "pm25_ugm3";
  app.state.cells = [
    { cell_id: "a", bucket: "h1", parameter: "pm25_ugm3", mean: 50 },
    { cell_id: "b", bucket: "h1", parameter: "pm25_ugm3", mean: 20 },
    { cell_id: "c", bucket: "h1", parameter: "pm25_ugm3", mean: 10 },
  ];
  const line = app.contrastLine({ cell_id: "a", bucket: "h1", mean: 50 });
  assert.match(line, /^context-top-bad/);
});

test("contrastLine — otherwise reports a tie-safe count of strictly-worse peers", async () => {
  const app = await freshApp();
  app.state.parameter = "pm25_ugm3";
  app.state.cells = [
    { cell_id: "a", bucket: "h1", parameter: "pm25_ugm3", mean: 20 },
    { cell_id: "b", bucket: "h1", parameter: "pm25_ugm3", mean: 50 },
    { cell_id: "c", bucket: "h1", parameter: "pm25_ugm3", mean: 10 },
  ];
  const line = app.contrastLine({ cell_id: "a", bucket: "h1", mean: 20 });
  assert.match(line, /^context-rank-bad/);
});

test("contrastLine — provisional outliers cannot distort a confirmed cohort", async () => {
  const app = await freshApp();
  app.state.parameter = "temp_c";
  app.state.cells = [
    { cell_id: "a", bucket: "h1", parameter: "temp_c", mean: 20, provisional: false },
    { cell_id: "b", bucket: "h1", parameter: "temp_c", mean: 15, provisional: false },
    { cell_id: "c", bucket: "h1", parameter: "temp_c", mean: 10, provisional: false },
    { cell_id: "raw", bucket: "h1", parameter: "temp_c", mean: 100, provisional: true },
  ];
  const line = app.contrastLine(app.state.cells[0]);
  assert.match(line, /^context-top-hot/);
  assert.doesNotMatch(line, /context-rank-hot/);
});

test("trendLine — silent until history is loaded", async () => {
  const app = await freshApp();
  app.state.historyLoaded = false;
  assert.equal(app.trendLine({ cell_id: "a", mean: 10 }), "");
});

test("trendLine — rising/falling/steady against the reading a few buckets back", async () => {
  const app = await freshApp();
  app.state.historyLoaded = true;
  app.state.parameter = "pm25_ugm3"; // TREND_EPS = 1
  app.state.buckets = ["h0", "h1", "h2", "h3"];
  app.state.bucketIdx = 3;
  app.state.cells = [{ cell_id: "a", parameter: "pm25_ugm3", bucket: "h0", mean: 10 }];

  assert.match(app.trendLine({ cell_id: "a", mean: 20 }), /^↑ trend-rising/);
  assert.match(app.trendLine({ cell_id: "a", mean: 0 }), /^↓ trend-falling/);
  assert.match(app.trendLine({ cell_id: "a", mean: 10.5 }), /^→ trend-steady/);
});

test("trendLine — names elapsed clock hours when published observations are sparse", async () => {
  const app = await freshApp();
  app.state.historyLoaded = true;
  app.state.parameter = "pm25_ugm3";
  app.state.strings = { "trend-rising": "Rising over {$h} h" };
  app.state.buckets = [
    "2026-06-01T00:00:00Z",
    "2026-06-01T02:00:00Z",
    "2026-06-01T04:00:00Z",
    "2026-06-01T06:00:00Z",
  ];
  app.state.bucketIdx = 3;
  app.state.cells = [
    {
      cell_id: "a",
      parameter: "pm25_ugm3",
      bucket: "2026-06-01T00:00:00Z",
      mean: 10,
    },
  ];
  assert.equal(
    app.trendLine({
      cell_id: "a",
      parameter: "pm25_ugm3",
      bucket: "2026-06-01T06:00:00Z",
      mean: 20,
    }),
    "↑ Rising over ⁨6⁩ h",
  );
});

test("trendLine / dayChangeLine — cross-calibration comparisons stay silent", async () => {
  const app = await freshApp();
  app.state.historyLoaded = true;
  app.state.parameter = "temp_c";
  const prior = "2026-06-01T12:00:00Z";
  const current = "2026-06-02T12:00:00Z";
  app.state.buckets = [prior, current];
  app.state.bucketIdx = 1;
  app.state.cells = [
    { cell_id: "a", parameter: "temp_c", bucket: prior, mean: 20, provisional: true },
  ];
  const row = { cell_id: "a", parameter: "temp_c", bucket: current, mean: 25, provisional: false };
  assert.equal(app.trendLine(row), "");
  assert.equal(app.dayChangeLine(row), "");
});

test("dayChangeLine — needs a reading within 90 minutes of ~24h ago", async () => {
  const app = await freshApp();
  app.state.historyLoaded = true;
  app.state.parameter = "temp_c";
  app.state.unit = "C";
  const now = "2026-06-02T12:00:00Z";
  // dayChangeLine reads "now" from currentBucket() (state.buckets[state.bucketIdx]), not from the
  // row argument — line up both so "the selected hour" and "the row's hour" agree, as render()
  // always keeps them.
  app.state.buckets = [now];
  app.state.bucketIdx = 0;
  app.state.cells = [
    { cell_id: "a", parameter: "temp_c", bucket: "2026-06-01T12:00:00Z", mean: 20 }, // exactly 24h ago
  ];
  const row = { cell_id: "a", bucket: now, mean: 25 };
  assert.match(app.dayChangeLine(row), /^yesterday-higher/);
});

test("dayChangeLine — no comparable reading ~24h ago stays silent", async () => {
  const app = await freshApp();
  app.state.historyLoaded = true;
  app.state.parameter = "temp_c";
  const now = "2026-06-02T12:00:00Z";
  app.state.buckets = [now];
  app.state.bucketIdx = 0;
  app.state.cells = [
    { cell_id: "a", parameter: "temp_c", bucket: "2026-05-01T12:00:00Z", mean: 20 },
  ];
  const row = { cell_id: "a", bucket: now, mean: 25 };
  assert.equal(app.dayChangeLine(row), "");
});

test("ageText — minutes / hours / days bands", async () => {
  const app = await freshApp();
  const now = Date.now();
  assert.match(app.ageText(new Date(now - 5 * 60000).toISOString()), /^fresh-min$/);
  assert.match(app.ageText(new Date(now - 3 * 3600000).toISOString()), /^fresh-hr$/);
  assert.match(app.ageText(new Date(now - 5 * 86400000).toISOString()), /^fresh-day$/);
});

test("fmtBucket — a real BCP-47 locale formats through Intl; an invalid one falls back honestly", async () => {
  const app = await freshApp();
  assert.equal(app.fmtBucket(""), "—");

  app.document.documentElement.lang = "en-US";
  assert.match(app.fmtBucket("2026-06-01T14:30:00Z"), /Jun/);

  app.document.documentElement.lang = "not a real locale tag!!";
  assert.equal(app.fmtBucket("2026-06-01T14:30:00Z"), "2026-06-01 14:30 UTC");
});

test("parseHash — a malformed percent-encoding in one key must not throw or blank the page", async () => {
  const app = await freshApp();
  // A share link truncated or mangled by a copy/paste, email client, or hand edit can leave an
  // invalid percent-encoding (a lone "%", or a cut-off UTF-8 sequence) in the fragment.
  // decodeURIComponent() throws a URIError on all of these; parseHash() runs inside init() before
  // the first render, so an uncaught throw here used to blank the whole dashboard.
  app.location.hash = "#p=temp_c&l=abc%&t=2026-06-01T00%3A00%3A00Z";
  const parsed = app.parseHash();
  assert.equal(parsed.p, "temp_c"); // a well-formed key still parses …
  assert.equal(parsed.t, "2026-06-01T00:00:00Z");
  assert.equal(parsed.l, undefined); // … the malformed one is just skipped, not fatal
});

test("normalizeHistoryRange — clamps indices and lets the manipulated edge win", async () => {
  const app = await freshApp();
  assert.deepEqual([...app.normalizeHistoryRange(-4, 99, 23, "end")], [0, 23]);
  assert.deepEqual([...app.normalizeHistoryRange(12, 5, 23, "start")], [12, 12]);
  assert.deepEqual([...app.normalizeHistoryRange(12, 5, 23, "end")], [5, 5]);
});

test("resetHistoryRange — keeps 24 published observations while timestamps expose sparse hours", async () => {
  const app = await freshApp();
  const start = Date.parse("2026-06-01T00:00:00Z");
  app.state.interval = "hour";
  app.state.buckets = Array.from({ length: 30 }, (_, index) =>
    new Date(start + index * 2 * 60 * 60 * 1000).toISOString(),
  );
  app.resetHistoryRange();
  assert.equal(app.state.rangeStart, 6);
  assert.equal(app.state.rangeEnd, 29);
  assert.equal(app.expectedSlotsInRange(), 47);
});

test("seriesSegments — missing buckets stay visible as gaps", async () => {
  const app = await freshApp();
  const segments = app.seriesSegments([
    { index: 0 },
    { index: 1 },
    { index: 4 },
    { index: 5 },
    { index: 9 },
  ]);
  // `seriesSegments()` comes from the vm harness, so compare serialized structure across realms.
  assert.equal(
    JSON.stringify(segments.map((segment) => segment.map((point) => point.index))),
    JSON.stringify([[0, 1], [4, 5], [9]]),
  );
});

test("seriesSegments / rangeStats — elapsed timestamp gaps survive compact bucket indices", async () => {
  const app = await freshApp();
  app.state.interval = "hour";
  const points = [
    {
      index: 0,
      timestamp: Date.parse("2026-06-01T00:00:00Z"),
      value: 10,
      row: { provisional: false },
    },
    {
      index: 1,
      timestamp: Date.parse("2026-06-01T02:00:00Z"),
      value: 20,
      row: { provisional: false },
    },
  ];
  const segments = app.seriesSegments(points);
  assert.equal(
    JSON.stringify(segments.map((segment) => segment.map((point) => point.index))),
    JSON.stringify([[0], [1]]),
  );
  const expected = app.expectedSlotsBetween(
    "2026-06-01T00:00:00Z",
    "2026-06-01T02:00:00Z",
  );
  assert.equal(expected, 3);
  assert.equal(app.rangeStats(points, expected).gaps, 1);
});

test("rangeStats — reports median, provisional support, and missing hours", async () => {
  const app = await freshApp();
  const stats = app.rangeStats(
    [
      { index: 0, value: 10, row: { provisional: false } },
      { index: 2, value: 30, row: { provisional: true } },
      { index: 3, value: 20, row: { provisional: false } },
    ],
    4,
  );
  assert.equal(stats.count, 3);
  assert.equal(stats.min, 10);
  assert.equal(stats.median, 20);
  assert.equal(stats.max, 30);
  assert.equal(stats.provisional, 1);
  assert.equal(stats.gaps, 1);
});

test("rangeStats — an even ordinal sample uses a conservative observed upper median", async () => {
  const app = await freshApp();
  app.state.parameter = "exposure";
  const stats = app.rangeStats(
    [
      { index: 0, value: 1, row: { provisional: false } },
      { index: 1, value: 2, row: { provisional: false } },
    ],
    2,
  );
  assert.equal(stats.median, 2);
  assert.ok([1, 2].includes(stats.median));
});

test("seriesPath — ordinal exposure changes category with a step-after path", async () => {
  const app = await freshApp();
  const path = app.seriesPath(
    [
      { index: 0, value: 1 },
      { index: 1, value: 2 },
    ],
    (index) => index * 10,
    (value) => value * 10,
    true,
  );
  assert.equal(path, "M0,10 L10,10 L10,20");
});

test("nearestSeriesIndex — pointer position snaps by elapsed time, not array position", async () => {
  const app = await freshApp();
  app.state.interval = "hour";
  app.state.buckets = [
    "2026-06-01T00:00:00Z",
    "2026-06-01T01:00:00Z",
    "2026-06-01T02:00:00Z",
  ];
  app.state.rangeStart = 0;
  app.state.rangeEnd = 2;
  const points = [
    { index: 0, timestamp: Date.parse(app.state.buckets[0]) },
    { index: 2, timestamp: Date.parse(app.state.buckets[2]) },
  ];
  assert.equal(app.nearestSeriesIndex(points, 0.1), 0);
  assert.equal(app.nearestSeriesIndex(points, 0.75), 2);
});

test("sparkSeries / dailyHistory — historical selection excludes future and duplicate variants", async () => {
  const app = await freshApp();
  const t0 = "2026-06-01T00:00:00Z";
  const t1 = "2026-06-02T02:00:00Z";
  const t2 = "2026-06-03T04:00:00Z";
  const future = "2026-06-04T06:00:00Z";
  const row = (bucket, mean, aqiWindow = "hourly-mean") => ({
    cell_id: "c1",
    label: "Cedar",
    parameter: "pm25_ugm3",
    bucket,
    mean,
    aqi_window: aqiWindow,
  });
  app.setData({
    interval: "hour",
    buckets: [t0, t1, t2, future],
    cells: [row(t0, 10), row(t1, 20), row(t2, 30), row(t2, 80, "nowcast"), row(future, 40)],
  });
  app.state.parameter = "pm25_ugm3";
  app.state.bucketIdx = 2;
  const sparkBuckets = app.sparkSeries({ cell_id: "c1" }).map((item) => item.bucket);
  assert.equal(JSON.stringify(sparkBuckets), JSON.stringify([t0, t1, t2]));
  const days = app.dailyHistory({ cell_id: "c1" });
  assert.equal(days.length, 3);
  assert.equal(days.some((day) => day.vals.includes(40)), false);
  assert.equal(days.some((day) => day.vals.includes(80)), false);
});

test("calibratedEvidenceSeries / overviewStatisticRows — confirmed evidence excludes raw outliers", async () => {
  const app = await freshApp();
  const confirmed = { mean: 20, provisional: false };
  const raw = { mean: 200, provisional: true };
  const evidence = app.calibratedEvidenceSeries([confirmed, raw]);
  assert.equal(JSON.stringify(evidence.series), JSON.stringify([confirmed]));
  assert.equal(evidence.excludedProvisional, 1);
  assert.equal(evidence.allProvisional, false);
  assert.equal(JSON.stringify(app.overviewStatisticRows([confirmed, raw])), JSON.stringify([confirmed]));
  assert.equal(JSON.stringify(app.overviewStatisticRows([raw])), JSON.stringify([raw]));

  const confirmedPoint = { value: 2, row: { provisional: false } };
  const rawPoint = { value: 99, row: { provisional: true } };
  const qualifiedPoints = app.calibratedEvidenceSeries([confirmedPoint, rawPoint]);
  assert.equal(JSON.stringify(qualifiedPoints.series), JSON.stringify([confirmedPoint]));
  assert.equal(qualifiedPoints.excludedProvisional, 1);
});

test("dailyHistory — mixed days keep provisional evidence out of confirmed summaries", async () => {
  const app = await freshApp();
  const bucket = "2026-06-01T12:00:00Z";
  app.setData({
    buckets: [bucket],
    cells: [
      { cell_id: "c1", parameter: "temp_c", bucket, mean: 20, provisional: false },
      {
        cell_id: "c1",
        parameter: "temp_c",
        bucket: "2026-06-01T13:00:00Z",
        mean: 200,
        provisional: true,
      },
    ],
  });
  // Include both rows in the selected evidence horizon without making the provisional value future.
  app.state.buckets = ["2026-06-01T13:00:00Z"];
  app.state.bucketIdx = 0;
  app.state.parameter = "temp_c";
  const day = app.dailyHistory({ cell_id: "c1" })[0];
  assert.equal(JSON.stringify(day.vals), JSON.stringify([20]));
  assert.equal(JSON.stringify(day.provisionalVals), JSON.stringify([200]));
  assert.equal(day.provisionalCount, 1);
});

test("area alert copy — zero-alert stale feeds name their publication time and staleness", async () => {
  const app = await freshApp();
  app.state.strings = {
    "aa-none": "No published alerts as of {$time}.",
    "aa-stale": "Feed is stale.",
  };
  const line = app.areaAlertStatus({ generated: "2025-01-01T00:00:00Z" }, []);
  assert.match(line, /No published alerts as of/);
  assert.match(line, /Feed is stale\./);
  assert.doesNotMatch(line, /right now/i);
});

test("showAlertObservation — an absent feed bucket never opens an unrelated observation", async () => {
  const app = await freshApp();
  const loaded = "2026-06-02T00:00:00Z";
  const missing = "2026-06-01T00:00:00Z";
  app.setData({
    buckets: [loaded],
    cells: [{ cell_id: "c1", parameter: "temp_c", bucket: loaded, mean: 20 }],
  });
  app.state.parameter = "temp_c";
  app.state.selected = null;
  app.state.strings = {
    "alert-observation-unavailable": "Observation {$time} is unavailable.",
  };
  assert.equal(app.showAlertObservation("c1", "temp_c", missing), false);
  assert.equal(app.currentBucket(), loaded);
  assert.equal(app.state.selected, null);
  assert.match(app.document.querySelector("#area-alerts-status").textContent, /unavailable/);
});

test("PM2.5 linked views keep the hourly mean and exclude a same-hour NowCast variant", async () => {
  const app = await freshApp();
  const bucket = "2026-06-01T00:00:00Z";
  app.setData({
    interval: "hour",
    buckets: [bucket],
    cells: [
      {
        cell_id: "c1",
        label: "Cedar",
        parameter: "pm25_ugm3",
        bucket,
        mean: 12,
        aqi: 50,
        category: "Good",
        aqi_window: "hourly-mean",
      },
      {
        cell_id: "c1",
        label: "Cedar",
        parameter: "pm25_ugm3",
        bucket,
        mean: 30,
        aqi: 89,
        category: "Moderate",
        aqi_window: "nowcast",
      },
    ],
  });
  app.state.parameter = "pm25_ugm3";
  assert.equal(
    JSON.stringify(app.current().map((row) => row.aqi_window)),
    JSON.stringify(["hourly-mean"]),
  );
  assert.equal(
    JSON.stringify(app.seriesPointsFor("c1").map((point) => point.row.aqi_window)),
    JSON.stringify(["hourly-mean"]),
  );
});

test("renderDetail — a selected place with no current observation is an explicit gap", async () => {
  const app = await freshApp();
  const oldBucket = "2026-06-01T00:00:00Z";
  const currentBucket = "2026-06-01T01:00:00Z";
  app.setData({
    interval: "hour",
    buckets: [oldBucket, currentBucket],
    cells: [
      {
        cell_id: "chosen",
        label: "Cedar & 4th",
        parameter: "temp_c",
        bucket: oldBucket,
        mean: 28,
      },
      {
        cell_id: "other",
        label: "Market",
        parameter: "temp_c",
        bucket: currentBucket,
        mean: 30,
      },
    ],
  });
  app.state.parameter = "temp_c";
  app.state.selected = "chosen";
  app.state.strings = {
    "inspector-empty": "Select a place.",
    "now-no-reading": "No reading at {$time}.",
    "now-gap": "The gap is preserved.",
  };
  assert.equal(app.focusRow(app.current()), null);
  app.renderDetail();
  const message = app.document.querySelector("#inspector-empty").textContent;
  assert.match(message, /Cedar & 4th/);
  assert.match(message, /No reading at/);
  assert.match(message, /gap is preserved/);
  assert.notEqual(message, "Select a place.");
});

test("renderNow — keeps a selected place's identity when it never reports the active parameter", async () => {
  const app = await freshApp();
  const bucket = "2026-06-01T00:00:00Z";
  app.setData({
    buckets: [bucket],
    cells: [
      { cell_id: "chosen", label: "Cedar & 4th", parameter: "pm25_ugm3", bucket, mean: 12 },
      { cell_id: "other", label: "Market", parameter: "temp_c", bucket, mean: 30 },
    ],
  });
  app.state.parameter = "temp_c";
  app.state.selected = "chosen";
  app.state.strings = {
    "now-selected-focus": "Selected location",
    "now-no-reading": "No reading at {$time}.",
    "now-gap": "The gap is preserved.",
    "now-no-current": "No current observation",
  };
  app.renderNow(app.current());
  assert.equal(app.document.querySelector("#now-place").textContent, "Cedar & 4th");
  assert.match(app.document.querySelector("#now-reading").textContent, /No reading at/);
});

test("current / focusRow — an empty search has no synthetic network focus", async () => {
  const app = await freshApp();
  const bucket = "2026-06-01T00:00:00Z";
  app.setData({
    buckets: [bucket],
    cells: [
      { cell_id: "c1", label: "Cedar", parameter: "temp_c", bucket, mean: 28 },
    ],
  });
  app.state.parameter = "temp_c";
  app.state.search = "does not exist";
  assert.equal(app.current().length, 0);
  assert.equal(app.focusRow(app.current()), null);
});

test("guidanceForRow — compound exposure carries both hazard guidance and sources", async () => {
  const app = await freshApp();
  app.state.parameter = "exposure";
  app.state.strings = {
    "heat-guide-xcaution": "Reduce heat exposure.",
    "guide-usg": "Reduce smoke exposure.",
    "guide-source-both": "NWS heat guidance and EPA air guidance.",
  };
  const row = {
    category: "Elevated",
    heat_category: "Extreme Caution",
    air_category: "Unhealthy for Sensitive Groups",
    compound: true,
  };
  assert.equal(app.guidanceForRow(row), "Reduce heat exposure. Reduce smoke exposure.");
  assert.equal(
    app.guidanceSourceForRow(row),
    "NWS heat guidance and EPA air guidance.",
  );
});

test("braidEvidenceNote — exposure caveats and numeric uncertainty use separate method notes", async () => {
  const app = await freshApp();
  app.state.strings = {
    "braid-exposure-note": "Exposure method: {$note}",
    "braid-se-note": "Band is published one-standard-error uncertainty.",
    "braid-no-band": "No uncertainty band is available.",
  };
  app.state.parameter = "exposure";
  app.state.bucketIdx = 2;
  assert.equal(
    app.braidEvidenceNote(null, [
      { index: 1, row: { uncertainty_note: "An older note." } },
      { index: 2, row: { uncertainty_note: "Ordinal joint hazard." } },
    ]),
    "Exposure method: ⁨Ordinal joint hazard.⁩",
  );
  app.state.bucketIdx = 3;
  assert.equal(
    app.braidEvidenceNote(null, [
      { index: 2, row: { uncertainty_note: "Ordinal joint hazard." } },
    ]),
    "No uncertainty band is available.",
  );
  app.state.parameter = "temp_c";
  assert.equal(
    app.braidEvidenceNote(null, [{ uncertainty: 0.8 }]),
    "Band is published one-standard-error uncertainty.",
  );
  assert.equal(
    app.braidEvidenceNote(null, [{ uncertainty: null }]),
    "No uncertainty band is available.",
  );
});

test("history enrichment preserves a bucket selected after the initial snapshot", async () => {
  const app = await freshApp();
  app.history = app.window.history;
  const t0 = "2026-06-01T00:00:00Z";
  const t1 = "2026-06-01T01:00:00Z";
  const t2 = "2026-06-01T02:00:00Z";
  const row = (bucket, mean) => ({
    cell_id: "c1",
    label: "Cedar",
    parameter: "temp_c",
    bucket,
    mean,
  });
  app.state.parameter = "temp_c";
  app.location.hash = `#p=temp_c&t=${encodeURIComponent(t2)}`;
  app.applyHashParameter();
  app.setData({ buckets: [t0, t1], cells: [row(t0, 20), row(t1, 21)] });
  app.restoreView();
  assert.equal(app.state.bucketIdx, 1); // deep-link hour is not in the fast snapshot

  app.setBucketIndex(0, { pause: true }); // the reader scrubs while full history is in flight
  app.setData({ buckets: [t0, t1, t2], cells: [row(t0, 20), row(t1, 21), row(t2, 22)] });
  app.restoreView();
  assert.equal(app.currentBucket(), t0);
});

test("history enrichment still resolves an initial deep-link absent from the snapshot", async () => {
  const app = await freshApp();
  app.history = app.window.history;
  const t0 = "2026-06-01T00:00:00Z";
  const t1 = "2026-06-01T01:00:00Z";
  const row = (bucket, mean) => ({
    cell_id: "c1",
    label: "Cedar",
    parameter: "temp_c",
    bucket,
    mean,
  });
  app.state.parameter = "temp_c";
  app.location.hash = `#p=temp_c&t=${encodeURIComponent(t0)}`;
  app.applyHashParameter();
  app.setData({ buckets: [t1], cells: [row(t1, 21)] });
  app.restoreView();
  app.setData({ buckets: [t0, t1], cells: [row(t0, 20), row(t1, 21)] });
  app.restoreView();
  assert.equal(app.currentBucket(), t0);
});

test("history enrichment cannot restore a deep-link location cleared by an explicit search", async () => {
  const app = await freshApp();
  app.history = app.window.history;
  const t0 = "2026-06-01T00:00:00Z";
  const t1 = "2026-06-01T01:00:00Z";
  const row = (cellId, bucket, mean) => ({
    cell_id: cellId,
    label: cellId,
    parameter: "temp_c",
    bucket,
    mean,
  });
  app.location.hash = `#p=temp_c&t=${encodeURIComponent(t1)}&l=c1&c=c2`;
  app.applyHashParameter();
  app.setData({ buckets: [t1], cells: [row("c1", t1, 20), row("c2", t1, 21)] });
  app.restoreView();
  assert.equal(app.state.selected, "c1");
  assert.equal(app.state.compareCell, "c2");

  // The user begins a new search before the delayed seven-day payload resolves.
  app.state.search = "new place";
  app.clearPendingLocationView();
  app.state.selected = null;
  app.state.compareCell = null;
  app.savePref("cell", null);
  app.savePref("compare", null);

  app.setData({
    buckets: [t0, t1],
    cells: [row("c1", t0, 19), row("c2", t0, 20), row("c1", t1, 20), row("c2", t1, 21)],
  });
  app.restoreView();
  assert.equal(app.state.selected, null);
  assert.equal(app.state.compareCell, null);
});

test("distributionEntries — retains a selected outlier with its real network rank", async () => {
  const app = await freshApp();
  const bucket = "2026-06-01T00:00:00Z";
  const cells = Array.from({ length: 12 }, (_, index) => ({
    cell_id: `c${index + 1}`,
    label: `Place ${index + 1}`,
    parameter: "temp_c",
    bucket,
    mean: 12 - index,
  }));
  app.setData({ buckets: [bucket], cells });
  app.state.parameter = "temp_c";
  app.state.selected = "c12";
  const distribution = app.distributionEntries(app.current());
  assert.equal(distribution.entries.length, 11);
  assert.equal(distribution.networkCount, 12);
  const selected = distribution.entries.find((entry) => entry.row.cell_id === "c12");
  assert.equal(selected.rank, 12);
  assert.equal(selected.selectedOutlier, true);
});

test("distributionEntries — equal readings share a competition rank", async () => {
  const app = await freshApp();
  const bucket = "2026-06-01T00:00:00Z";
  app.setData({
    buckets: [bucket],
    cells: [
      { cell_id: "a", label: "A", parameter: "temp_c", bucket, mean: 30 },
      { cell_id: "b", label: "B", parameter: "temp_c", bucket, mean: 30 },
      { cell_id: "c", label: "C", parameter: "temp_c", bucket, mean: 20 },
    ],
  });
  app.state.parameter = "temp_c";
  const ranks = app.distributionEntries(app.current()).entries.map(({ rank }) => rank);
  assert.equal(JSON.stringify(ranks), JSON.stringify([1, 1, 3]));
});

test("distributionEntries — provisional outliers never rank inside a confirmed cohort", async () => {
  const app = await freshApp();
  const bucket = "2026-06-01T00:00:00Z";
  app.setData({
    buckets: [bucket],
    cells: [
      { cell_id: "a", label: "A", parameter: "temp_c", bucket, mean: 30, provisional: false },
      { cell_id: "b", label: "B", parameter: "temp_c", bucket, mean: 20, provisional: false },
      { cell_id: "raw", label: "Raw", parameter: "temp_c", bucket, mean: 200, provisional: true },
    ],
  });
  app.state.parameter = "temp_c";
  const qualified = app.distributionEntries(app.current());
  assert.equal(
    JSON.stringify(qualified.entries.map((entry) => entry.row.cell_id)),
    JSON.stringify(["a", "b"]),
  );
  assert.equal(qualified.excludedProvisional, 1);
  assert.equal(qualified.allProvisional, false);

  app.state.cells = app.state.cells.filter((row) => row.provisional);
  app.indexCells();
  const fallback = app.distributionEntries(app.current());
  assert.equal(fallback.entries[0].row.cell_id, "raw");
  assert.equal(fallback.allProvisional, true);
});

test("distributionPercent — pollutant bars use zero while temperature bars use the network range", async () => {
  const app = await freshApp();
  app.state.parameter = "pm25_ugm3";
  assert.equal(app.distributionPercent(10, { min: 8, max: 20 }), 50);
  app.state.parameter = "temp_c";
  assert.equal(app.distributionPercent(15, { min: 10, max: 20 }), 50);
});

test("wireTabs — arrow keys move focus to the new tab, never into its panel", async () => {
  const app = await freshApp();
  const listeners = new Map();
  const makeTab = (id, panelId) => ({
    id,
    tabIndex: 0,
    attributes: new Map([["aria-controls", panelId]]),
    addEventListener(type, handler) {
      listeners.set(`${id}:${type}`, handler);
    },
    getAttribute(name) {
      return this.attributes.get(name);
    },
    setAttribute(name, value) {
      this.attributes.set(name, String(value));
    },
    focus() {
      this.focused = true;
    },
  });
  const tabs = [makeTab("tab-list", "panel-list"), makeTab("tab-table", "panel-table")];
  const panels = {
    "panel-list": { hidden: false },
    "panel-table": { hidden: true },
  };
  app.document.querySelectorAll = (selector) => (selector === '[role="tab"]' ? tabs : []);
  app.document.getElementById = (id) => panels[id] || null;
  app.wireTabs();
  let prevented = false;
  listeners.get("tab-list:keydown")({
    key: "ArrowRight",
    preventDefault() {
      prevented = true;
    },
  });
  assert.equal(prevented, true);
  assert.equal(tabs[1].focused, true);
  assert.equal(panels["panel-table"].hidden, false);
});

test("wireSectionNavigation — in-page scrolling preserves the shareable state hash", async () => {
  const app = await freshApp();
  let clickHandler = null;
  let scrolled = false;
  const link = {
    addEventListener(type, handler) {
      if (type === "click") clickHandler = handler;
    },
    getAttribute(name) {
      return name === "href" ? "#explore" : null;
    },
  };
  const section = {
    scrollIntoView() {
      scrolled = true;
    },
  };
  app.document.querySelectorAll = (selector) =>
    selector === '.observatory-nav a[href^="#"]' ? [link] : [];
  app.document.getElementById = (id) => (id === "explore" ? section : null);
  app.location.hash = "#p=temp_c&t=2026-06-01T00%3A00%3A00Z&l=c1&c=c2";
  app.wireSectionNavigation();
  let prevented = false;
  clickHandler({
    preventDefault() {
      prevented = true;
    },
  });
  assert.equal(prevented, true);
  assert.equal(scrolled, true);
  assert.equal(app.location.hash, "#p=temp_c&t=2026-06-01T00%3A00%3A00Z&l=c1&c=c2");
});

test("wireSectionNavigation — the skip link preserves state and moves focus to main", async () => {
  const app = await freshApp();
  let clickHandler = null;
  let focused = false;
  const skip = {
    classList: { contains: (name) => name === "skip-link" },
    addEventListener(type, handler) {
      if (type === "click") clickHandler = handler;
    },
    getAttribute(name) {
      return name === "href" ? "#main" : null;
    },
  };
  const main = {
    scrollIntoView() {},
    focus() {
      focused = true;
    },
  };
  app.document.querySelectorAll = (selector) =>
    selector === '.skip-link[href^="#"]' ? [skip] : [];
  app.document.getElementById = (id) => (id === "main" ? main : null);
  app.location.hash = "#p=temp_c&t=2026-06-01T00%3A00%3A00Z&l=c1";
  app.wireSectionNavigation();
  let prevented = false;
  clickHandler({
    preventDefault() {
      prevented = true;
    },
  });
  assert.equal(prevented, true);
  assert.equal(focused, true);
  assert.equal(app.location.hash, "#p=temp_c&t=2026-06-01T00%3A00%3A00Z&l=c1");
});

test("wireObservatory — Open evidence suppresses native fragment replacement", async () => {
  const app = await freshApp();
  let clickHandler = null;
  let scrolled = false;
  const originalQuery = app.document.querySelector;
  const cta = {
    addEventListener(type, handler) {
      if (type === "click") clickHandler = handler;
    },
    getAttribute() {
      return null; // no selected cell: isolate the in-page navigation behavior
    },
  };
  app.document.querySelector = (selector) =>
    selector === "#now-open-evidence" ? cta : originalQuery(selector);
  app.document.getElementById = (id) =>
    id === "explore" ? { scrollIntoView() { scrolled = true; } } : null;
  app.location.hash = "#p=temp_c&t=2026-06-01T00%3A00%3A00Z&l=c1";
  app.wireObservatory();
  let prevented = false;
  clickHandler({
    currentTarget: cta,
    preventDefault() {
      prevented = true;
    },
  });
  assert.equal(prevented, true);
  assert.equal(scrolled, true);
  assert.equal(app.location.hash, "#p=temp_c&t=2026-06-01T00%3A00%3A00Z&l=c1");
});

test("magnitudeFor — exposure stays ordinal while temperatures honor display units", async () => {
  const app = await freshApp();
  assert.equal(app.magnitudeFor({ category: "High", mean: 99 }, "exposure", "F"), 3);
  assert.equal(app.magnitudeFor({ mean: 20 }, "temp_c", "C"), 20);
  assert.equal(app.magnitudeFor({ mean: 20 }, "temp_c", "F"), 68);
});

test("semantic chart formatting — exposure ordinals become categories and WBGT stays estimated", async () => {
  const app = await freshApp();
  app.state.strings = {
    "exp-elevated": "Elevated",
    "estimated-value": "{$value} (estimated)",
    "estimated-short": "estimated",
  };

  app.state.parameter = "exposure";
  assert.equal(app.formatMagnitude(2), "Elevated");

  app.state.parameter = "wbgt_c";
  app.state.unit = "C";
  assert.equal(app.formatMagnitude(28.25), "⁨28.3 °C⁩ (estimated)");
  assert.equal(app.formatDifference(-2.25), "⁨2.3 °C⁩ (estimated)");
  assert.equal(app.unitContextLabel(), "°C · estimated");
});

test("sparkSegmentPath — categorical exposure history uses discrete steps", async () => {
  const app = await freshApp();
  const points = [
    { x: 0, y: 10 },
    { x: 5, y: 4 },
    { x: 9, y: 8 },
  ];
  const coordinates = (point) => point;
  assert.equal(
    app.sparkSegmentPath(points, coordinates, true),
    "M0.0,10.0 L5.0,10.0 L5.0,4.0 L9.0,4.0 L9.0,8.0",
  );
  assert.equal(app.sparkSegmentPath(points, coordinates, false), "M0.0,10.0 L5.0,4.0 L9.0,8.0");
});

test("dense map rendering keeps semantic exposure categories visible", () => {
  const fs = require("node:fs");
  const path = require("node:path");
  const source = fs.readFileSync(path.join(__dirname, "..", "app.js"), "utf8");
  assert.match(source, /isExposure\(\)\s*\? formatMagnitude\(magnitudeFor\(row\)\)/);
  assert.doesNotMatch(source, /isExposure\(\)\s*\? `\$\{Math\.round\(row\.mean\)\}`/);
});

test("markerClusters groups only nearby overview positions and preserves every index", async () => {
  const app = await freshApp();
  const layout = [
    { left: 0.1, bottom: 0.9 },
    { left: 0.12, bottom: 0.88 },
    { left: 0.8, bottom: 0.2 },
  ];
  const clusters = app.markerClusters(layout, 800, 600, true);
  assert.deepEqual(
    JSON.parse(JSON.stringify(clusters.map((cluster) => cluster.indices))),
    [[0, 1], [2]],
  );
  assert.deepEqual(
    JSON.parse(JSON.stringify(app.markerClusters(layout, 800, 600, false).map((cluster) => cluster.indices))),
    [[0], [1], [2]],
  );
});

test("markerClusters anchors groups to real places and merges overlapping adjacent-bin controls", async () => {
  const app = await freshApp();
  const width = 800;
  const height = 600;
  const layout = [
    { left: 0.13, bottom: 0.72 },
    { left: 0.14, bottom: 0.72 },
    { left: 0.7, bottom: 0.25 },
  ];
  const clusters = app.markerClusters(layout, width, height, true);

  assert.deepEqual(
    JSON.parse(JSON.stringify(clusters.map((cluster) => cluster.indices))),
    [[0, 1], [2]],
  );
  for (const cluster of clusters) {
    assert.ok(
      cluster.indices.some((index) => layout[index] === cluster.position),
      "each cluster must remain anchored to one of its mapped members",
    );
  }
  for (let left = 0; left < clusters.length - 1; left += 1) {
    for (let right = left + 1; right < clusters.length; right += 1) {
      const dx = (clusters[left].position.left - clusters[right].position.left) * width;
      const dy = (clusters[left].position.bottom - clusters[right].position.bottom) * height;
      assert.ok(Math.hypot(dx, dy) >= 56);
    }
  }
});

test("markerClusters recomputes target clearance for large text and narrow maps", async () => {
  const app = await freshApp();
  const layout = [
    { left: 0.125, bottom: 0.83 },
    { left: 0.1275, bottom: 0.83 },
    { left: 0.2, bottom: 0.83 },
    { left: 0.2025, bottom: 0.83 },
  ];
  assert.equal(app.markerClusters(layout, 800, 600, true, 1).length, 2);
  assert.equal(app.markerClusters(layout, 800, 600, true, 1.3).length, 1);
  assert.equal(app.markerClusters(layout, 580, 600, true, 1).length, 1);
});

test("markerClusters protects nearby targets in a small mapped dataset without coarse grouping", async () => {
  const app = await freshApp();
  const layout = [
    { left: 0.1, bottom: 0.7 },
    { left: 0.15, bottom: 0.7 },
    { left: 0.8, bottom: 0.2 },
  ];
  const clusters = app.markerClusters(layout, 800, 600, true, 1, false, 60);

  assert.deepEqual(
    JSON.parse(JSON.stringify(clusters.map((cluster) => cluster.indices))),
    [[0, 1], [2]],
  );
});

test("fitMapBounds zooms the camera without changing projected marker positions", async () => {
  const app = await freshApp();
  const positions = [
    { left: 0.251, bottom: 0.612 },
    { left: 0.255, bottom: 0.615 },
    { left: 0.253, bottom: 0.613 },
  ];
  const before = JSON.parse(JSON.stringify(positions));
  const width = 800;
  const height = 600;
  const view = app.fitMapBounds(positions, width, height, 50);

  assert.ok(view.zoom > 100, `expected a neighborhood-scale camera, got ${view.zoom}`);
  assert.ok(view.zoom <= 512);
  assert.ok(view.x <= 0 && view.x >= width * (1 - view.zoom));
  assert.ok(view.y <= 0 && view.y >= height * (1 - view.zoom));
  for (const position of positions) {
    const x = view.x + position.left * width * view.zoom;
    const y = view.y + (1 - position.bottom) * height * view.zoom;
    assert.ok(x >= 49 && x <= width - 49, `x=${x}`);
    assert.ok(y >= 49 && y <= height - 49, `y=${y}`);
  }
  assert.deepEqual(JSON.parse(JSON.stringify(positions)), before);
});

test("the California overview keeps one projection while a cluster changes only the camera", () => {
  const fs = require("node:fs");
  const path = require("node:path");
  const source = fs.readFileSync(path.join(__dirname, "..", "app.js"), "utf8");
  assert.match(source, /const layout = rows\.map\(\(row\) => markerPos\(row, proj\)\)/);
  assert.doesNotMatch(source, /const layout = declutterPositions\(/);
  assert.match(source, /const proj = mapProjection\(rows\)/);
  assert.match(
    source,
    /markerClusters\(\s*layout,\s*mapLayoutW,\s*mapLayoutH,\s*rows\.length > 1,/,
  );
  assert.match(source, /zoomToMapBounds\(cluster\.indices\.map/);
  assert.doesNotMatch(source, /mapLocal/);
});

test("braidSelectionText — an unknown saved location degrades to an empty observation status", async () => {
  const app = await freshApp();
  const bucket = "2026-06-01T00:00:00Z";
  app.state.strings = {
    "braid-selected-empty": "{$time}. No location reports this measurement.",
  };
  app.setData({ buckets: [bucket], cells: [] });
  app.state.selected = "missing-location";
  assert.match(app.braidSelectionText(), /No location reports this measurement/);
});

test("sourceTerm — a non-provisional model row keeps upstream terminology", async () => {
  const app = await freshApp();
  app.document.documentElement.lang = "en";
  app.state.demo = {
    source: {
      terminology: {
        non_provisional_label: { en: "Upstream model", es: "Modelo externo" },
      },
    },
  };
  assert.equal(app.sourceTerm("non_provisional_label", "state-calibrated"), "Upstream model");
});

test("linked selectors expose selection state and dynamic action lists restore focus", () => {
  const fs = require("node:fs");
  const path = require("node:path");
  const source = fs.readFileSync(path.join(__dirname, "..", "app.js"), "utf8");
  assert.match(source, /place\.setAttribute\("aria-pressed"/);
  assert.match(source, /placeButton\.setAttribute\("aria-pressed"/);
  assert.match(source, /btn\.setAttribute\("aria-pressed"/);
  assert.match(source, /closest\?\.\("#overview-worst button"\)/);
  assert.match(source, /closest\?\.\("#alerts-list button"\)/);
  assert.match(source, /closest\?\.\("#area-alerts-list button"\)/);
});
