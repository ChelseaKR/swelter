// The Playwright config that governs the browser gate must fail the run when a
// test passed only on its retry.
//
// `playwright.config.cjs` retries once in CI. Playwright reports a test that
// failed and then passed on that retry as `flaky`, and exits 0 on flaky unless
// `failOnFlakyTests` is set — the runner's verdict is
// `... || hasFailedTests || config.failOnFlakyTests && hasFlakyTests`. Without
// the key, the retry converts an intermittent failure (a race, an unawaited
// promise) into a green `a11y-advisory` check that records nothing but a log
// line. See #281.
//
// This REQUIRES the config the way Playwright reads it rather than matching its
// text, so a key that is commented out, misspelled, or set to `false` cannot
// satisfy it. It runs here, in the unit suite, because the browser gate that
// uses the config is advisory and this assertion is not: `web-tests` is the job
// that must go red if the policy is dropped.

"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const CONFIG = path.join(__dirname, "..", "playwright.config.cjs");

// Read the config as CI reads it. `retries` and `failOnFlakyTests` are both
// written in terms of process.env.CI, so a local run would otherwise see the
// zero-retry branch and this test would assert nothing about the CI path.
function loadUnderCI() {
  const previous = process.env.CI;
  process.env.CI = "1";
  try {
    delete require.cache[require.resolve(CONFIG)];
    return require(CONFIG);
  } finally {
    if (previous === undefined) delete process.env.CI;
    else process.env.CI = previous;
    delete require.cache[require.resolve(CONFIG)];
  }
}

test("the browser gate fails a CI run when a test passed only on its retry", () => {
  const config = loadUnderCI();

  // Vacuity guard: the assertion below reads keys off `config`, and a missing
  // key reads as `undefined` — so a require that resolved to something other
  // than this config would satisfy it by appearing to have no retries rather
  // than by being safe. `testDir` is checked because this config always sets it
  // and Playwright's own config loader does not synthesize it.
  assert.ok(config, "playwright.config.cjs did not export a config object");
  assert.equal(
    typeof config.testDir,
    "string",
    "playwright.config.cjs no longer sets `testDir`, so this require may not be the config Playwright runs; " +
      "the assertion below would be reading undefined off the wrong object",
  );

  const retries = config.retries ?? 0;
  assert.ok(
    retries === 0 || config.failOnFlakyTests === true,
    `playwright.config.cjs retries ${retries} time(s) in CI but does not set failOnFlakyTests: true, ` +
      "so a test that passes only on its retry reads as green",
  );
});
