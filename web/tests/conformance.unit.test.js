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
  assert.deepEqual(unmarked, [], `uncatalogued HTML copy: ${unmarked.join(" | ")}`);
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
  assert.deepEqual(packageJson.dependencies, { messageformat: "4.0.0-11" });
  assert.equal(lock.packages[""].dependencies.messageformat, "4.0.0-11");
  assert.deepEqual(lock.packages["node_modules/messageformat"], {
    version: "4.0.0-11",
    resolved: "https://registry.npmjs.org/messageformat/-/messageformat-4.0.0-11.tgz",
    integrity: "sha512-8OZN4+rgXmsRkkjcVGAZtdp91a4USScLHr5fiQrAgIhQGWEY3Ii+VMCfsrw4sWVAwsbTzPIckOtVRKOiv7WPLg==",
    license: "Apache-2.0",
  });
});

test("Node tooling is pinned to the supported Node 22 LTS floor", () => {
  const packageJson = JSON.parse(read("package.json"));
  assert.equal(read(".nvmrc").trim(), "22.12.0");
  assert.equal(packageJson.engines.node, ">=22.12.0 <23");
});
