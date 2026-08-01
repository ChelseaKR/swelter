"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const WEB = path.join(__dirname, "..");
const MANIFEST = path.join(WEB, "i18n", "messages.manifest.json");
const EXPECTED_RUNTIME_VERSION = "4.0.0";
const read = (name) => fs.readFileSync(path.join(WEB, name), "utf8");
const catalog = (locale) => JSON.parse(read(`i18n/${locale}.json`));

// These families are selected through a map, template key, or a state-dependent expression in
// app.js. Every other key must be statically extractable from a t()/sourceTerm() call or HTML
// data-i18n marker; this bounded allowlist prevents an unreferenced catalog entry from hiding as
// an unspecified "dynamic" message.
const DYNAMIC_KEY_PATTERN = new RegExp(
  "^(?:(?:document-title|meta-description)-(?:openaq|openmeteo|sensor-community|synthetic)|" +
    "(?:cat|guide|exp|heat|heat-guide|cool-type)-[a-z0-9-]+|" +
    "(?:act|context|trend|yesterday|compare|prov|legend-title|distribution|health-stat|dir|cooling)-[a-z0-9-]+)$",
);

const PLURAL_KEYS = [
  "braid-provisional-excluded",
  "overview-provisional-excluded",
  "spark-provisional-excluded",
  "prov-readings",
  "history-all-provisional",
  "history-provisional-excluded",
  "aa-count",
  "settings-has",
];

function firstArgument(callSource, openParen) {
  let depth = 0;
  let quote = null;
  let escaped = false;
  for (let index = openParen + 1; index < callSource.length; index += 1) {
    const character = callSource[index];
    if (quote) {
      if (escaped) escaped = false;
      else if (character === "\\") escaped = true;
      else if (character === quote) quote = null;
      continue;
    }
    if (character === '"' || character === "'" || character === "`") {
      quote = character;
      continue;
    }
    if (character === "(" || character === "[" || character === "{") depth += 1;
    else if (character === ")" || character === "]" || character === "}") {
      if (depth === 0 && character === ")") return callSource.slice(openParen + 1, index);
      depth -= 1;
    } else if (character === "," && depth === 0) {
      return callSource.slice(openParen + 1, index);
    }
  }
  throw new Error("unterminated t() call while extracting messages");
}

function staticMessageKeys() {
  const html = read("index.html");
  const javascript = read("app.js");
  const keys = new Set();
  for (const match of html.matchAll(/\bdata-i18n\s*=\s*["']([^"']+)["']/g)) keys.add(match[1]);
  for (const match of html.matchAll(/\bdata-i18n-attr\s*=\s*["'][^:"']+:([^"']+)["']/g)) {
    keys.add(match[1]);
  }
  for (const call of javascript.matchAll(/\bt\s*\(/g)) {
    const argument = firstArgument(javascript, call.index + call[0].lastIndexOf("("));
    for (const literal of argument.matchAll(/(?:^|[^\\])(["'])([^"'\\]+)\1/g)) keys.add(literal[2]);
  }
  for (const match of javascript.matchAll(
    /\bsourceTerm\(\s*["'][^"']+["']\s*,\s*["']([^"']+)["']/g,
  )) {
    keys.add(match[1]);
  }
  return [...keys].sort();
}

function argumentNames(message) {
  return [...new Set([...message.matchAll(/\{\$([A-Za-z][A-Za-z0-9_-]*)\b/g)].map((match) => match[1]))].sort();
}

function generatedManifest() {
  const en = catalog("en");
  const staticKeys = staticMessageKeys();
  const known = new Set(staticKeys);
  const dynamicKeys = Object.keys(en).filter((key) => !known.has(key)).sort();
  const unbounded = dynamicKeys.filter((key) => !DYNAMIC_KEY_PATTERN.test(key));
  assert.deepEqual(unbounded, [], `unreferenced messages need an explicit dynamic family: ${unbounded.join(", ")}`);
  return {
    schemaVersion: 1,
    syntax: `Unicode MessageFormat 2 (messageformat ${EXPECTED_RUNTIME_VERSION})`,
    sourceLocale: "en",
    staticKeys,
    dynamicKeys,
  };
}

function validateSource(locale, key, source, MessageFormat, parseMessage, validate) {
  assert.equal(typeof source, "string", `${locale}:${key} is not a string`);
  assert.ok(source.trim(), `${locale}:${key} is empty`);
  const model = parseMessage(source);
  validate(model);
  new MessageFormat(locale, source, { bidiIsolation: "default" });
  assert.doesNotMatch(
    source,
    /\{[A-Za-z][A-Za-z0-9_-]*(?:\}|,)/,
    `${locale}:${key} contains legacy ICU MessageFormat 1 syntax`,
  );
}

function checkCatalogs(MessageFormat, parseMessage, validate) {
  const en = catalog("en");
  const es = catalog("es");
  assert.deepEqual(Object.keys(es).sort(), Object.keys(en).sort(), "catalog key parity");
  for (const key of Object.keys(en)) {
    validateSource("en", key, en[key], MessageFormat, parseMessage, validate);
    validateSource("es", key, es[key], MessageFormat, parseMessage, validate);
    assert.deepEqual(argumentNames(es[key]), argumentNames(en[key]), `argument drift: ${key}`);
  }
  for (const locale of ["en", "es"]) {
    const messages = locale === "en" ? en : es;
    for (const key of PLURAL_KEYS) {
      assert.match(messages[key], /^\.input \{\$n :number\}\n\.match \$n\n/);
      assert.match(messages[key], /\none \{\{/);
      assert.match(messages[key], /\n\* \{\{/);
    }
  }

  const source = read("app.js");
  assert.doesNotMatch(source, /\b(?:pluralMessage|fillIn|isolatedMessageValues)\s*\(/, "bespoke i18n helper returned");
  assert.doesNotMatch(source, /\.replace\(\s*["']\{/, "manual catalog interpolation returned");
  assert.equal(Object.keys(en).some((key) => /-(?:one|other)$/.test(key)), false, "plural suffix keys returned");
}

function relativeFiles(directory, prefix = "") {
  const files = [];
  for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
    const relative = path.join(prefix, entry.name);
    if (entry.isDirectory()) files.push(...relativeFiles(path.join(directory, entry.name), relative));
    else if (entry.isFile()) files.push(relative);
    else throw new Error(`unexpected runtime entry: ${path.join(directory, entry.name)}`);
  }
  return files.sort();
}

function checkVendoredRuntime() {
  const entry = fs.realpathSync(require.resolve("messageformat"));
  const source = path.dirname(entry);
  const packageJson = JSON.parse(
    fs.readFileSync(path.join(path.dirname(source), "package.json"), "utf8"),
  );
  assert.equal(packageJson.name, "messageformat");
  assert.equal(packageJson.version, EXPECTED_RUNTIME_VERSION);
  const destination = path.join(WEB, "vendor", "messageformat");
  const sourceFiles = relativeFiles(source);
  const destinationFiles = relativeFiles(destination).filter(
    (relative) => relative !== "asset-manifest.json",
  );
  assert.deepEqual(destinationFiles, sourceFiles, "run `npm run build:i18n`");
  for (const relative of sourceFiles) {
    assert.deepEqual(
      fs.readFileSync(path.join(destination, relative)),
      fs.readFileSync(path.join(source, relative)),
      `vendored MessageFormat runtime drift: ${relative}`,
    );
  }
  const expectedAssets = sourceFiles
    .filter((relative) => relative.endsWith(".js"))
    .map((relative) => `vendor/messageformat/${relative.split(path.sep).join("/")}`);
  assert.deepEqual(
    JSON.parse(fs.readFileSync(path.join(destination, "asset-manifest.json"), "utf8")),
    expectedAssets,
    "runtime asset manifest drift",
  );
}

async function main() {
  const mode = process.argv[2] || "--check";
  assert.ok(["--check", "--write"].includes(mode), "usage: i18n-extract.cjs --check|--write");
  const { MessageFormat, parseMessage, validate } = await import("messageformat");
  checkCatalogs(MessageFormat, parseMessage, validate);
  checkVendoredRuntime();
  const rendered = `${JSON.stringify(generatedManifest(), null, 2)}\n`;
  if (mode === "--write") fs.writeFileSync(MANIFEST, rendered, "utf8");
  else assert.equal(fs.readFileSync(MANIFEST, "utf8"), rendered, "run `npm run i18n:extract`");
  console.log(`MessageFormat 2 catalogs: ${Object.keys(catalog("en")).length} messages × 2 locales`);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
