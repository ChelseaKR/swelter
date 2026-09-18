// Unit tests for `web/analytics.js` (ADR 0055). The loader runs unmodified in a Node `vm` context
// against a stubbed window, navigator, document and localStorage, so these tests check what it does,
// not only what its source says. The negative controls at the end break the loader in one place,
// assert the break actually landed in the source they run, and then assert the harness notices: a
// sabotage that silently no-ops would otherwise read as a pass.

"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const WEB = path.join(__dirname, "..");
const SOURCE = fs.readFileSync(path.join(WEB, "analytics.js"), "utf8");
const ID = "G-CMSGSNGC9P";
const ID_LINE = `var GA4_ID = "${ID}";`;
const KEY = "swelter.analytics-opt-out";
const PRODUCTION = "https://chelseakr.github.io/swelter/#p=temperature&t=2026-07-16T14%3A00%3A00Z&l=cell-12";
const CONSENT_REQUIRED = [
  "AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "ES", "FI", "FR", "GR", "HR", "HU",
  "IE", "IT", "LT", "LU", "LV", "MT", "NL", "PL", "PT", "RO", "SE", "SI", "SK",
  "IS", "LI", "NO", "GB", "CH",
];

function run({
  source = SOURCE,
  url = PRODUCTION,
  referrer = "",
  gpc,
  dnt,
  windowDnt,
  msDnt,
  storage = {},
  storageThrows = false,
} = {}) {
  const appended = [];
  const data = new Map(Object.entries(storage));
  const store = {
    getItem: (key) => (data.has(key) ? data.get(key) : null),
    setItem: (key, value) => {
      if (storageThrows === "on-write") throw new Error("QuotaExceededError");
      data.set(key, String(value));
    },
    removeItem: (key) => {
      if (storageThrows === "on-write") throw new Error("QuotaExceededError");
      data.delete(key);
    },
  };
  const location = new URL(url);
  const navigator = { globalPrivacyControl: gpc, doNotTrack: dnt, msDoNotTrack: msDnt };
  const window = {
    navigator,
    doNotTrack: windowDnt,
    location: {
      protocol: location.protocol,
      hostname: location.hostname,
      pathname: location.pathname,
      origin: location.origin,
      href: location.href,
      search: location.search,
      hash: location.hash,
    },
  };
  Object.defineProperty(window, "localStorage", {
    get() {
      if (storageThrows === true) throw new Error("SecurityError");
      return store;
    },
  });
  const document = {
    referrer,
    head: { appendChild: (element) => appended.push(element) },
    documentElement: { appendChild: (element) => appended.push(element) },
    createElement: (tag) => ({ tagName: tag.toUpperCase() }),
  };
  vm.runInNewContext(source, { window, navigator, document, URL, Date }, { filename: "analytics.js" });
  return {
    window,
    data,
    appended,
    loaded: window.dataLayer !== undefined || appended.length > 0,
    // A JSON round trip moves the vm realm's objects into this one, so deepEqual compares values
    // rather than prototypes. The Date pushed with "js" becomes a string, which is all it needs.
    pushed: window.dataLayer
      ? JSON.parse(JSON.stringify(window.dataLayer.map((args) => Array.from(args))))
      : null,
  };
}

function sabotaged(marker, replacement) {
  assert.equal(SOURCE.split(marker).length - 1, 1, `sabotage marker must occur exactly once: ${marker}`);
  const changed = SOURCE.replace(marker, replacement);
  assert.notEqual(changed, SOURCE, "the sabotage did not change the source");
  return changed;
}

test("analytics: production loads gtag once with the consent defaults and a stripped config", () => {
  const result = run({ referrer: "https://www.google.com/search?q=heat+map+sacramento" });
  assert.equal(result.appended.length, 1);
  assert.equal(result.appended[0].tagName, "SCRIPT");
  assert.equal(result.appended[0].async, true);
  assert.equal(result.appended[0].src, `https://www.googletagmanager.com/gtag/js?id=${ID}`);

  const ads = { ad_storage: "denied", ad_user_data: "denied", ad_personalization: "denied" };
  assert.deepEqual(result.pushed[0], [
    "consent",
    "default",
    { ...ads, analytics_storage: "denied", region: CONSENT_REQUIRED },
  ]);
  assert.deepEqual(result.pushed[1], ["consent", "default", { ...ads, analytics_storage: "granted" }]);
  assert.equal(result.pushed[2][0], "js");
  assert.deepEqual(result.pushed[3], [
    "config",
    ID,
    {
      allow_google_signals: false,
      allow_ad_personalization_signals: false,
      // Origin and path only: the fragment names the selected cell and time.
      page_location: "https://chelseakr.github.io/swelter/",
      page_referrer: "https://www.google.com/",
    },
  ]);
  assert.equal(result.pushed.length, 4);
  assert.equal(new Set(CONSENT_REQUIRED).size, 32);
});

test("analytics: no place, time, cell, or query string ever reaches the data layer", () => {
  const result = run({
    url: "https://chelseakr.github.io/swelter/sensors/?utm_source=x#p=pm25&l=cell-7&c=cell-9",
    referrer: "https://example.org/private/path?token=1",
  });
  assert.equal(result.pushed[3][2].page_location, "https://chelseakr.github.io/swelter/sensors/");
  assert.equal(result.pushed[3][2].page_referrer, "https://example.org/");
  const serialized = JSON.stringify(result.pushed);
  for (const leak of ["cell-7", "cell-9", "pm25", "utm_source", "token", "/private/"]) {
    assert.equal(serialized.includes(leak), false, `${leak} reached the data layer`);
  }
});

test("analytics: the planner and the /sensors/ route load it too", () => {
  for (const url of [
    "https://chelseakr.github.io/swelter/planner/",
    "https://chelseakr.github.io/swelter/sensors/",
  ]) {
    assert.equal(run({ url }).loaded, true, url);
  }
});

test("analytics: nothing loads off the production host and path, but the control still works", () => {
  for (const url of [
    "http://127.0.0.1:4173/",
    "http://localhost:8000/planner/",
    "http://chelseakr.github.io/swelter/",
    "https://chelseakr.github.io/",
    "https://chelseakr.github.io/other-project/",
    "https://chelseakr.github.io/swelter-fork/",
    "https://heat.example.org/swelter/",
  ]) {
    const result = run({ url });
    assert.equal(result.loaded, false, url);
    assert.equal(result.window.dataLayer, undefined, url);
    assert.equal(typeof result.window.swelterAnalytics, "object", url);
  }
});

test("analytics: Global Privacy Control or Do Not Track stops it before anything loads", () => {
  for (const signal of [
    { gpc: true },
    { dnt: "1" },
    { dnt: "yes" },
    { windowDnt: "1" },
    { msDnt: "1" },
    { gpc: true, dnt: "1" },
  ]) {
    const result = run(signal);
    assert.equal(result.loaded, false, JSON.stringify(signal));
    assert.equal(result.window.swelterAnalytics.blockedBySignal, true, JSON.stringify(signal));
  }
  for (const off of [{ gpc: false }, { dnt: "0" }, { dnt: "unspecified" }, { windowDnt: "0" }]) {
    const result = run(off);
    assert.equal(result.loaded, true, JSON.stringify(off));
    assert.equal(result.window.swelterAnalytics.blockedBySignal, false, JSON.stringify(off));
  }
});

test("analytics: only the exact opt-out flag stops it", () => {
  const out = run({ storage: { [KEY]: "1" } });
  assert.equal(out.loaded, false);
  assert.equal(out.window.swelterAnalytics.isOptedOut(), true);
  for (const storage of [{ [KEY]: "0" }, { [KEY]: "true" }, { "swelter.prefs": '{"lang":"es"}' }]) {
    assert.equal(run({ storage }).loaded, true, JSON.stringify(storage));
  }
});

test("analytics: the opt-out is stored outside swelter.prefs and toggles both ways", () => {
  const result = run({ storage: { "swelter.prefs": "{}" } });
  const api = result.window.swelterAnalytics;
  assert.equal(api.setOptedOut(true), true);
  assert.equal(result.data.get(KEY), "1");
  assert.equal(result.window[`ga-disable-${ID}`], true);
  assert.equal(api.isOptedOut(), true);
  assert.equal(result.data.get("swelter.prefs"), "{}");
  assert.equal(api.setOptedOut(false), true);
  assert.equal(result.data.has(KEY), false);
  assert.equal(result.window[`ga-disable-${ID}`], false);
  assert.equal(api.isOptedOut(), false);
});

test("analytics: blocked storage is reported, and a refused write is not claimed as saved", () => {
  const blocked = run({ storageThrows: true });
  assert.equal(blocked.window.swelterAnalytics.storageAvailable(), false);
  assert.equal(blocked.loaded, true, "GPC/DNT still work; nothing was opted out");

  const refused = run({ storageThrows: "on-write" });
  const api = refused.window.swelterAnalytics;
  assert.equal(api.setOptedOut(true), false);
  assert.equal(api.storageAvailable(), false);
  assert.equal(refused.window[`ga-disable-${ID}`], undefined);
});

test("analytics: an empty or malformed ID loads nothing and publishes no control API", () => {
  for (const value of ["", "UA-12345-1", 'G-ABC"+alert(1)+"', "g-cmsgsngc9p"]) {
    const result = run({ source: sabotaged(ID_LINE, `var GA4_ID = ${JSON.stringify(value)};`) });
    assert.equal(result.loaded, false, value);
    assert.equal(result.window.swelterAnalytics, undefined, value);
  }
});

test("analytics: it announces the control API once it exists, and only with an ID", () => {
  const announce = (source) => {
    const events = [];
    const document = {
      referrer: "",
      head: { appendChild() {} },
      createElement: () => ({}),
      dispatchEvent: (event) => events.push(event.type),
    };
    const window = { navigator: {}, location: new URL("http://127.0.0.1:4173/") };
    vm.runInNewContext(source, { window, navigator: {}, document, URL, Date, Event });
    return { events, api: window.swelterAnalytics };
  };
  const withId = announce(SOURCE);
  assert.deepEqual(withId.events, ["swelter:analytics"]);
  assert.equal(typeof withId.api, "object");
  assert.deepEqual(announce(sabotaged(ID_LINE, 'var GA4_ID = "";')).events, []);
});

test("analytics: every page loads the loader once, and nothing else names Google", () => {
  const dashboard = fs.readFileSync(path.join(WEB, "index.html"), "utf8");
  const planner = fs.readFileSync(path.join(WEB, "planner", "index.html"), "utf8");
  assert.equal(dashboard.split('<script src="analytics.js" defer></script>').length - 1, 1);
  // After app.js, so a deferred loader never delays the dashboard's first render.
  assert.ok(dashboard.indexOf('src="analytics.js"') > dashboard.indexOf('src="app.js"'));
  assert.equal(planner.split('<script src="../analytics.js" defer></script>').length - 1, 1);
  assert.ok(planner.indexOf('src="../analytics.js"') < planner.indexOf('src="planner.js"'));
  for (const name of ["index.html", "app.js", "sw.js", "i18n-runtime.mjs", "planner/index.html", "planner/planner.js"]) {
    const text = fs.readFileSync(path.join(WEB, name), "utf8");
    assert.equal(/googletagmanager|google-analytics|gtag\(/.test(text), false, name);
  }
  assert.equal(SOURCE.split("https://www.googletagmanager.com/gtag/js?id=").length - 1, 1);
  const worker = fs.readFileSync(path.join(WEB, "sw.js"), "utf8");
  assert.match(worker, /\n {2}"analytics\.js",\n/);
});

test("analytics: the privacy copy names the key, the cookie and the retention the loader uses", () => {
  const en = JSON.parse(fs.readFileSync(path.join(WEB, "i18n", "en.json"), "utf8"));
  assert.ok(SOURCE.includes(`var OPT_OUT_KEY = "${KEY}";`));
  assert.match(en["privacy-cookies"], /_ga/);
  assert.match(en["privacy-ads"], /14 months/);
  assert.match(en["privacy-off"], /Global Privacy Control or Do Not Track/);
  assert.match(en["privacy-never"], /never gets your searches, the places you pick/);
  for (const [key, message] of Object.entries(en)) {
    assert.equal(/\bno (?:tracking|analytics)\b/i.test(message), false, key);
  }
});

// -- negative controls ----------------------------------------------------------------------------

test("analytics negative control: each removed guard lets GA load where it must not", () => {
  const cases = [
    ["  if (signal) return;\n", { gpc: true }],
    ["  if (signal) return;\n", { dnt: "1" }],
    ["  if (optedOut()) return;\n", { storage: { [KEY]: "1" } }],
    [
      '  if (loc.protocol !== "https:" || loc.hostname !== PRODUCTION_HOST) return;\n',
      { url: "http://127.0.0.1:4173/swelter/" },
    ],
    [
      "  if (loc.pathname.indexOf(PRODUCTION_PATH) !== 0) return;\n",
      { url: "https://chelseakr.github.io/other-project/" },
    ],
  ];
  for (const [guard, scenario] of cases) {
    assert.equal(run(scenario).loaded, false, `baseline must not load: ${guard.trim()}`);
    assert.equal(
      run({ ...scenario, source: sabotaged(guard, "") }).loaded,
      true,
      `the harness missed a removed guard: ${guard.trim()}`,
    );
  }
});

test("analytics negative control: a full page_location is caught", () => {
  const source = sabotaged("page_location: loc.origin + loc.pathname,", "page_location: loc.href,");
  assert.match(run({ source }).pushed[3][2].page_location, /l=cell-12$/);
});

test("analytics negative control: Google signals turned on is caught", () => {
  const source = sabotaged("allow_google_signals: false,", "allow_google_signals: true,");
  assert.equal(run({ source }).pushed[3][2].allow_google_signals, true);
});
