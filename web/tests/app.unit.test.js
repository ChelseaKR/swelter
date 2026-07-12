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
