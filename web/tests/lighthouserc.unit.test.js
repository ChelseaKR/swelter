// The Lighthouse CI configuration's own contract (#266).
//
// One Lighthouse run per route on a shared GitHub-hosted runner decided merges on scheduler noise:
// over 137 retained `a11y-advisory` runs, total-blocking-time reached 202 ms on `/` and 257.5 ms
// on `/sensors/` against a 200 ms budget, while the medians were 54 ms and 52 ms. The repair is
// several runs read by their median. The trap is that LHCI's default aggregation is "optimistic",
// which for a `max*` budget reads the BEST run -- so adding runs without pinning the method makes
// every budget easier to pass while the file still states the same number. These tests hold the
// file to the strict reading.

"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");
const test = require("node:test");

const config = require(path.join(__dirname, "..", "lighthouserc.cjs"));

test("assertions aggregate by median, stated explicitly rather than inherited", () => {
  assert.equal(
    config.ci.assert.aggregationMethod,
    "median",
    "LHCI defaults to optimistic, which reads the best run for every max* budget",
  );
});

test("no single assertion overrides the pinned aggregation", () => {
  // LHCI merges assert-level options under each assertion's own options, so one assertion
  // carrying `aggregationMethod: "optimistic"` would quietly loosen that budget alone.
  const overrides = Object.entries(config.ci.assert.assertions)
    .filter(([, value]) => Array.isArray(value) && value[1] && "aggregationMethod" in value[1])
    .filter(([, value]) => value[1].aggregationMethod !== "median")
    .map(([name, value]) => `${name}: ${value[1].aggregationMethod}`);
  assert.deepEqual(overrides, []);
});

test("there are enough runs for a median to outvote one noisy run", () => {
  const runs = config.ci.collect.numberOfRuns;
  assert.ok(Number.isInteger(runs), "numberOfRuns must be an integer");
  assert.ok(runs >= 3, `a median of ${runs} run(s) is decided by a single run`);
  assert.equal(runs % 2, 1, "an even run count makes the median an average of two runs");
});

test("the budgets this change must not have loosened are unchanged", () => {
  const { assertions } = config.ci.assert;
  assert.deepEqual(assertions["total-blocking-time"], ["error", { maxNumericValue: 200 }]);
  assert.deepEqual(assertions["largest-contentful-paint"], ["error", { maxNumericValue: 2500 }]);
  assert.deepEqual(assertions["cumulative-layout-shift"], ["error", { maxNumericValue: 0.1 }]);
  for (const category of ["accessibility", "performance", "best-practices"]) {
    assert.deepEqual(assertions[`categories:${category}`], ["error", { minScore: 0.9 }]);
  }
});
