// Test-only harness that loads `web/app.js` — a plain, no-module `<script>` never meant to run
// outside a browser — into a Node `vm` Context so its pure, function-scoped logic (unit
// conversion, category ordering, trend/contrast lines, `t()` fallback: FIX-07) can be unit-tested
// without a browser. `app.js` itself is not modified or copied: this file only supplies the
// minimal DOM/`fetch`/`localStorage` surface the script touches while it *loads* (including the
// unconditional `init()` call at the bottom of the file), so every top-level `function` and
// `const` declaration evaluates cleanly. `init()` then keeps running asynchronously against fake,
// disconnected APIs (fetches resolve `{ok: false}`, elements are inert stubs) — that is expected
// and harmless. `loadApp()` is async and waits one macrotask turn before returning specifically so
// that chain fully settles (resolves or rejects) *before* any test starts asserting, rather than
// leaking pending activity into whichever test happens to be running when it eventually lands
// (which Node's test runner flags as a failure, and rightly so).
//
// `vm.runInContext` gives every script evaluated in the same `Context` a shared top-level lexical
// environment (the same mechanism the Node REPL uses to keep `let`/`const` across separate
// commands), so a second, tiny script run in that context can read back `app.js`'s top-level
// `function`/`const`/`let` bindings (including the mutable `state` object) without app.js ever
// exporting anything.

"use strict";

const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const APP_JS_PATH = path.join(__dirname, "..", "app.js");

// One process-wide guard, installed lazily on first use: `init()` runs unattended in every
// `loadApp()` call, against disconnected fake network/DOM stubs, and nothing in this harness ever
// awaits it — a rejection anywhere in its chain is expected, not a bug in the code under test.
let rejectionGuardInstalled = false;
function ensureRejectionGuardInstalled() {
  if (rejectionGuardInstalled) return;
  rejectionGuardInstalled = true;
  process.on("unhandledRejection", () => {
    /* expected: see file header. */
  });
}

// A single reusable "inert element" stub: every property read that hasn't been explicitly set
// returns another inert stub (so `.classList.add(...)`, `.style.setProperty(...)`,
// `.dataset.foo`, chained accessors, etc. all resolve without throwing), every property write is
// remembered verbatim, and calling it as a function is a no-op. This is deliberately dumb — it
// exists only so `app.js` can load and its top-level `init()` call can run to completion without
// crashing the process, not to model real DOM behaviour.
function inertStub() {
  const target = function stub() {};
  return new Proxy(target, {
    get(obj, prop) {
      if (prop === "then" || prop === Symbol.toPrimitive || prop === Symbol.iterator) {
        return undefined;
      }
      if (!(prop in obj)) obj[prop] = inertStub();
      return obj[prop];
    },
    set(obj, prop, value) {
      obj[prop] = value;
      return true;
    },
    apply() {
      return undefined;
    },
  });
}

function makeDocumentStub() {
  const elements = new Map();
  const elementFor = (selector) => {
    if (!elements.has(selector)) elements.set(selector, inertStub());
    return elements.get(selector);
  };
  return {
    documentElement: inertStub(),
    querySelector: (selector) => elementFor(selector),
    // No `data-i18n`/`data-i18n-attr` nodes in the harness — `I18N_DEFAULTS` (and every other
    // `[...document.querySelectorAll(...)]` spread) ends up an empty, but perfectly iterable, list.
    querySelectorAll: () => [],
    createElement: () => inertStub(),
    createElementNS: () => inertStub(),
    createTextNode: () => inertStub(),
    addEventListener: () => {},
    removeEventListener: () => {},
  };
}

function makeFetchStub() {
  // Every fetch fails closed (`ok: false`) unless a test swaps in its own — `app.js`'s own
  // fetch-failure paths (`fetchSurface`, `loadStrings`, `loadBasemap`) are written to degrade
  // gracefully to that, by design.
  return async () => ({ ok: false, json: async () => ({}) });
}

/**
 * Load `web/app.js` into a fresh, isolated vm Context and return its top-level bindings.
 *
 * @param {object} [options]
 * @param {(url: string) => Promise<{ok: boolean, json: () => Promise<unknown>}>} [options.fetch]
 * @returns {Promise<Record<string, unknown>>} every top-level `function`/`const`/`let` of app.js
 *   that a test might need (see the extraction list below).
 */
async function loadApp(options = {}) {
  ensureRejectionGuardInstalled();
  const source = fs.readFileSync(APP_JS_PATH, "utf8");
  const { MessageFormat } = await import("messageformat");

  const sandbox = {
    document: makeDocumentStub(),
    window: undefined, // filled in below, once `sandbox` itself exists
    navigator: {}, // no `serviceWorker` key -> `"serviceWorker" in navigator` is false, skip that
    localStorage: {
      _data: new Map(),
      getItem(key) {
        return this._data.has(key) ? this._data.get(key) : null;
      },
      setItem(key, value) {
        this._data.set(key, String(value));
      },
      removeItem(key) {
        this._data.delete(key);
      },
    },
    fetch: options.fetch || makeFetchStub(),
    console,
    setTimeout,
    clearTimeout,
    requestAnimationFrame: (cb) => setTimeout(cb, 0),
    cancelAnimationFrame: (id) => clearTimeout(id),
    URL,
    URLSearchParams,
    SwelterMessageFormat: MessageFormat,
  };
  sandbox.window = {
    matchMedia: () => ({
      matches: false,
      addEventListener() {},
      removeEventListener() {},
      addListener() {},
      removeListener() {},
    }),
    location: {
      hash: "",
      search: "",
      pathname: "/",
      href: "http://localhost/",
      origin: "http://localhost",
    },
    history: { replaceState() {}, pushState() {} },
    innerWidth: 1024,
    innerHeight: 768,
    addEventListener: () => {},
    removeEventListener: () => {},
  };
  // Browsers expose `window.location` as the bare global `location` too, and app.js's
  // `briefText()`/`networkBriefText()` read it unqualified — alias it so that resolves.
  sandbox.location = sandbox.window.location;
  sandbox.globalThis = sandbox;

  const context = vm.createContext(sandbox);
  vm.runInContext(source, context, { filename: "web/app.js" });

  // `function` declarations at app.js's top level are already own properties of `sandbox`
  // (verified vm behaviour), so `sandbox.heatTier`, `sandbox.convert`, etc. work as-is. Its
  // top-level `const`/`let` bindings (notably the mutable `state` object unit conversion and the
  // trend/contrast lines read) are *not* auto-attached — pull the ones tests need back out with a
  // second script run in the same Context, which shares app.js's top-level lexical scope (the
  // same mechanism the Node REPL uses to keep `let` across separate commands). This returns the
  // *same* object references app.js's own functions close over, so mutating `state` from a test
  // (e.g. `state.unit = "F"`) is visible to `convert()`/`contrastLine()`/etc.
  const extracted = vm.runInContext(
    "({ state, PARAM_BASE_UNIT, CAT_SLUG, EXP_SLUG, HEAT_SLUG, TREND_EPS })",
    context,
  );
  Object.assign(sandbox, extracted);

  // Give the fire-and-forget `init()` call's promise chain a full macrotask turn to fully settle
  // (every await in it resolves against the stubs above almost immediately; there is no real I/O)
  // before handing control back to the test — see the file header for why this matters.
  await new Promise((resolve) => setTimeout(resolve, 20));

  return sandbox;
}

module.exports = { loadApp };
