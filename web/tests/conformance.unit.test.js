// Fast, deterministic authoring gates for the framework-free dashboard. Browser behavior lives in
// tests/browser; this file catches catalog, copy, direction, token, and byte-budget drift without
// starting a browser engine.

"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const WEB = path.join(__dirname, "..");
const read = (name) => fs.readFileSync(path.join(WEB, name), "utf8");
const catalog = (locale) => JSON.parse(read(`i18n/${locale}.json`));

function placeholders(value) {
  return [...new Set([...value.matchAll(/\{\$([A-Za-z][A-Za-z0-9_-]*)\b/g)].map((match) => match[1]))].sort();
}

test("catalogs are canonical MF2 with exact key and placeholder parity", async () => {
  const { MessageFormat, parseMessage, validate } = await import("messageformat");
  const en = catalog("en");
  const es = catalog("es");
  assert.deepEqual(Object.keys(es).sort(), Object.keys(en).sort());
  for (const key of Object.keys(en)) {
    validate(parseMessage(en[key]));
    validate(parseMessage(es[key]));
    new MessageFormat("en", en[key], { bidiIsolation: "default" });
    new MessageFormat("es", es[key], { bidiIsolation: "default" });
    assert.doesNotMatch(en[key], /\{[A-Za-z][A-Za-z0-9_-]*(?:\}|,)/);
    assert.doesNotMatch(es[key], /\{[A-Za-z][A-Za-z0-9_-]*(?:\}|,)/);
    assert.deepEqual(placeholders(es[key]), placeholders(en[key]), `placeholder drift: ${key}`);
  }
});

test("count messages use MF2 matchers, never suffix keys or parenthetical plurals", () => {
  const pluralBases = [
    "braid-provisional-excluded",
    "overview-provisional-excluded",
    "spark-provisional-excluded",
    "prov-readings",
    "history-all-provisional",
    "history-provisional-excluded",
    "aa-count",
    "settings-has",
  ];
  for (const locale of ["en", "es"]) {
    const messages = catalog(locale);
    const joined = Object.values(messages).join("\n");
    assert.doesNotMatch(joined, /\((?:s|es|as|os)\)/i, `${locale} contains a fake plural`);
    for (const base of pluralBases) {
      assert.match(messages[base], /^\.input \{\$n :number\}\n\.match \$n\n/, `${locale}: ${base} is not an MF2 matcher`);
      assert.match(messages[base], /\none \{\{/, `${locale}: ${base} has no one variant`);
      assert.match(messages[base], /\n\* \{\{/, `${locale}: ${base} has no catch-all variant`);
      assert.equal(Object.hasOwn(messages, `${base}-one`), false);
      assert.equal(Object.hasOwn(messages, `${base}-other`), false);
    }
  }
});

test("every English catalog prose entry stays at the checked Grade-8 scope", () => {
  // The exact readability calculation is Python/textstat in the repository gate. This companion
  // assertion prevents accidental opt-outs: public English remains a string catalog, and no
  // per-key skip/ignore metadata can silently narrow that gate.
  const en = catalog("en");
  for (const [key, value] of Object.entries(en)) {
    assert.equal(typeof value, "string", `${key} must remain extractable public copy`);
    assert.ok(value.trim(), `${key} must not be empty`);
  }
  assert.equal(Object.hasOwn(en, "reading-level-ignore"), false);
});

test("HTML public words are catalog-marked or a small language-neutral token", () => {
  const html = read("index.html");
  const allowed = new Set([
    "swelter", "English", "Español", "°F", "°C", "A−", "A+", "l", "t", "m", "/",
  ]);
  const voidTags = new Set(["area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"]);
  const stack = [];
  const unmarked = [];
  const tokens = html.match(/<!--[\s\S]*?-->|<![^>]*>|<[^>]+>|[^<]+/g) || [];
  for (const token of tokens) {
    if (token.startsWith("<!--") || token.startsWith("<!")) continue;
    if (token.startsWith("</")) {
      stack.pop();
      continue;
    }
    if (token.startsWith("<")) {
      const match = token.match(/^<\s*([a-z0-9-]+)/i);
      if (!match) continue;
      const tag = match[1].toLowerCase();
      const localized = /\bdata-i18n(?:-attr)?\s*=/.test(token) || stack.some((item) => item.localized);
      if (!voidTags.has(tag) && !/\/\s*>$/.test(token)) stack.push({ tag, localized });
      continue;
    }
    const text = token.replace(/\s+/g, " ").trim();
    if (!text || !/[A-Za-zÁ-ÿ]/.test(text)) continue;
    const context = stack.at(-1);
    if (context?.tag === "script" || context?.tag === "style" || context?.localized) continue;
    if (!allowed.has(text)) unmarked.push(text);
  }
  assert.deepEqual(unmarked, [], `uncataloged HTML copy: ${unmarked.join(" | ")}`);
});

test("alert actions stay outside the dedicated atomic live-status node", () => {
  const html = read("index.html");
  const section = html.match(/<section id="alerts"[\s\S]*?<\/section>/)?.[0] || "";
  assert.ok(section, "alerts section is missing");
  assert.doesNotMatch(section.match(/^<section[^>]*>/)?.[0] || "", /\brole="status"|\baria-live=/);
  assert.match(
    section,
    /<p id="alerts-status"[^>]*role="status"[^>]*aria-live="polite"[^>]*aria-atomic="true"[^>]*><\/p>/,
  );
  assert.ok(section.indexOf('id="alerts-status"') < section.indexOf('id="alerts-list"'));

  const source = read("app.js");
  assert.match(source, /status\.textContent !== nextAnnouncement/);
});

test("JavaScript has no literal natural-language text written into UI sinks", () => {
  const source = read("app.js").replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/.*$/gm, "");
  const literalSink = /(?:textContent|innerText|ariaLabel|title)\s*=\s*(["'`])([A-Za-z][^\n]*?\s+[A-Za-z][^\n]*?)\1/g;
  assert.deepEqual(
    [...source.matchAll(literalSink)].map((match) => match[0]),
    [],
    "natural-language UI text belongs in i18n catalogs",
  );
});

test("observatory.css is the only token owner and semantic colors do not drift", () => {
  const base = read("styles.css");
  const observatory = read("observatory.css");
  assert.doesNotMatch(base, /^\s*--[a-z0-9-]+\s*:/im, "styles.css must consume, not own, tokens");

  const required = [
    "bg", "fg", "muted", "surface", "border", "accent", "focus",
    "aqi-good-bg", "aqi-moderate-bg", "aqi-usg-bg", "aqi-unhealthy-bg",
    "aqi-very-unhealthy-bg", "aqi-hazardous-bg",
    "heat-1-bg", "heat-2-bg", "heat-3-bg", "heat-4-bg", "heat-5-bg",
  ];
  for (const name of required) {
    assert.match(observatory, new RegExp(`--${name}\\s*:`), `missing token --${name}`);
  }

  const semanticHex = [
    "#d7f0d0", "#f2e9b8", "#f6cf9b", "#ef9a9a", "#cf93c8", "#c79a9a",
    "#dbe9f2", "#e6edcb", "#f4e3b0", "#f2c197", "#e89887",
  ];
  const allCss = `${base}\n${observatory}`.toLowerCase();
  for (const color of semanticHex) {
    assert.equal(allCss.split(color).length - 1, 1, `${color} must have one token definition`);
  }
});

test("layout CSS is direction-neutral and sliders expose a 24px target", () => {
  const css = `${read("styles.css")}\n${read("observatory.css")}`;
  const physical = /\b(?:margin|padding|border)-(?:left|right)\b|\b(?:left|right)\s*:|text-align\s*:\s*(?:left|right)/g;
  assert.deepEqual([...css.matchAll(physical)].map((match) => match[0]), []);
  assert.match(css, /input\[type="range"\][\s\S]*?min-height:\s*1\.75rem/);
  assert.match(css, /::-webkit-slider-thumb[\s\S]*?width:\s*1\.5rem[\s\S]*?height:\s*1\.5rem/);
  assert.match(css, /::-moz-range-thumb[\s\S]*?width:\s*1\.5rem[\s\S]*?height:\s*1\.5rem/);
});

test("critical static assets stay inside the low-bandwidth byte budget", () => {
  const sizes = Object.fromEntries(
    ["index.html", "i18n-runtime.mjs", "app.js", "styles.css", "observatory.css"].map((name) => [
      name,
      fs.statSync(path.join(WEB, name)).size,
    ]),
  );
  assert.ok(sizes["index.html"] <= 50 * 1024, `index.html is ${sizes["index.html"]} bytes`);
  assert.ok(sizes["app.js"] <= 190 * 1024, `app.js is ${sizes["app.js"]} bytes`);
  assert.ok(sizes["styles.css"] + sizes["observatory.css"] <= 80 * 1024, "CSS exceeds 80 KiB");
  assert.ok(Object.values(sizes).reduce((sum, value) => sum + value, 0) <= 320 * 1024);

  const runtimeRoot = path.join(WEB, "vendor", "messageformat");
  const runtimeBytes = fs
    .readdirSync(runtimeRoot, { recursive: true, withFileTypes: true })
    .filter((entry) => entry.isFile() && entry.name.endsWith(".js"))
    .reduce((sum, entry) => sum + fs.statSync(path.join(entry.parentPath, entry.name)).size, 0);
  assert.ok(runtimeBytes <= 180 * 1024, `MessageFormat 2 runtime is ${runtimeBytes} bytes`);
  assert.ok(Object.values(sizes).reduce((sum, value) => sum + value, runtimeBytes) <= 500 * 1024);
});

test("MessageFormat 2 runtime is exact and integrity-locked", () => {
  const packageJson = JSON.parse(read("package.json"));
  const lock = JSON.parse(read("package-lock.json"));
  assert.deepEqual(packageJson.dependencies, { messageformat: "4.0.0" });
  assert.equal(lock.packages[""].dependencies.messageformat, "4.0.0");
  assert.deepEqual(lock.packages["node_modules/messageformat"], {
    version: "4.0.0",
    resolved: "https://registry.npmjs.org/messageformat/-/messageformat-4.0.0.tgz",
    integrity: "sha512-XKmJ/ffTWToWOlHJzt85ZChQgVGC0LHzNWuNK8zuYpNySsB0nIEmytOdSAOW9ETKtkajAUJf520m5gFHHnrTYg==",
    license: "Apache-2.0",
    engines: { node: "^20.19 || ^22.12 || >=24" },
  });
});

test("Node tooling is pinned to the supported Node 22 LTS floor", () => {
  const packageJson = JSON.parse(read("package.json"));
  assert.equal(read(".nvmrc").trim(), "22.12.0");
  assert.equal(packageJson.engines.node, ">=22.12.0 <23");
});

// Owner decision, 2026-09-18: the Spanish ships labeled machine-translated. These fail if a
// machine-translated catalog can be shown without the notice, or the notice stops being first in
// the page body, loses either language, or loses its way to the English.
test("the machine-translation notice is first in <main>, in both languages, with the way to the English", () => {
  const html = read("index.html");
  const main = html.match(/<main\b[^>]*>([\s\S]*?)<\/main>/)?.[1] || "";
  assert.ok(main, "index.html has no <main>");
  const firstElement = main.replace(/<!--[\s\S]*?-->/g, "").match(/<([a-z0-9-]+)\b[^>]*>/i)?.[0] || "";
  assert.match(firstElement, /\bid="mt-notice"/, "the notice must be the first element in <main>");
  assert.match(firstElement, /\bclass="mt-notice"/);
  assert.match(firstElement, /\bdata-machine-translation-notice\b/);
  assert.doesNotMatch(firstElement, /\bhidden\b/, "styles.css decides visibility; a hidden attribute would override it");

  const notice = main.match(/<div id="mt-notice"[\s\S]*?<\/div>/)?.[0] || "";
  assert.match(notice, /<p lang="es" data-i18n="mt-notice-es">/);
  assert.match(notice, /<p lang="en" data-i18n="mt-notice-en">/);
  assert.match(notice, /<span lang="es" data-i18n="mt-notice-switch-es">/);
  assert.match(notice, /<span lang="en" data-i18n="mt-notice-switch-en">/);
  assert.match(html, /<select id="lang-select"[^>]*>[\s\S]*?<option value="en">English<\/option>/, "the menu the notice points to offers English");
});

test("the Spanish catalog renders the notice's Spanish half in Spanish and its English half in English", () => {
  // The notice shows only while es.json is active, so es.json is what a reader sees: both halves,
  // each in its own language. en.json holds the English source of every key, as it does for all
  // keys, which is also what keeps the reading-level gate scoring English as English.
  const es = catalog("es");
  assert.match(es["mt-notice-es"], /^Traducción automática, sin revisión humana\./);
  assert.match(es["mt-notice-en"], /^Machine-translated, not reviewed by a person\./);
  assert.match(es["mt-notice-switch-es"], /^Consulte la versión en inglés/);
  assert.match(es["mt-notice-switch-en"], /^See the English version/);
  const en = catalog("en");
  for (const key of ["mt-notice-es", "mt-notice-en"]) {
    assert.match(en[key], /^Machine-translated, not reviewed by a person\./, key);
  }
});

test("the notice is hidden by default and shown for every non-English catalog", () => {
  const css = read("styles.css");
  const base = css.match(/(?:^|\n)\.mt-notice\s*\{([^}]*)\}/)?.[1] || "";
  assert.match(base, /display:\s*none/, "English (and a page before any catalog loads) must not show it");
  const shown = [...css.matchAll(/html\[lang="([^"]+)"\]\s+\.mt-notice\s*\{([^}]*)\}/g)]
    .filter((match) => /display:\s*block/.test(match[2]))
    .map((match) => match[1]);
  const catalogs = fs
    .readdirSync(path.join(WEB, "i18n"))
    .filter((name) => /^[a-z]{2,3}(?:-[A-Za-z0-9]+)*\.json$/.test(name))
    .map((name) => name.replace(/\.json$/, ""));
  assert.ok(catalogs.includes("es"), "the Spanish catalog is missing, so this proves nothing");
  for (const locale of catalogs) {
    if (locale === "en") continue;
    assert.ok(shown.includes(locale), `${locale} can be shown without the machine-translation notice`);
  }
  assert.ok(!shown.includes("en"), "English is the reference, not a machine translation");

  // The rule keys on <html lang>, so it holds only while loadStrings() keeps setting it.
  assert.match(read("app.js"), /document\.documentElement\.lang = lang;/);
});
