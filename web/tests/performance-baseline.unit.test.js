"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

const { compareBaseline, measuredBaseline, routeFor } = require("./performance-baseline.cjs");

function report(route, factor = 1) {
  return {
    requestedUrl: `http://127.0.0.1:4173${route}`,
    audits: {
      "largest-contentful-paint": { numericValue: 1000 * factor },
      "cumulative-layout-shift": { numericValue: 0.02 * factor },
      "total-blocking-time": { numericValue: 40 * factor },
      "total-byte-weight": { numericValue: 100000 * factor },
      "dom-size": { numericValue: 300 * factor },
    },
  };
}

test("route normalization keeps the two production surfaces distinct", () => {
  assert.equal(routeFor(report("/")), "/");
  assert.equal(routeFor(report("/sensors/index.html")), "/sensors/");
});

test("baseline comparison blocks a deterministic-metric regression over ten percent", () => {
  const measured = {
    schema_version: 1,
    max_regression_fraction: 0.1,
    routes: {
      "/": { lcp_ms: 100, cls: 0.01, tbt_ms: 1, total_bytes: 111000, dom_nodes: 1, critical_js_gzip_bytes: 1, critical_css_gzip_bytes: 1 },
      "/sensors/": { lcp_ms: 100, cls: 0.01, tbt_ms: 1, total_bytes: 100000, dom_nodes: 1, critical_js_gzip_bytes: 1, critical_css_gzip_bytes: 1 },
    },
  };
  const baseline = JSON.parse(JSON.stringify({ ...measured, state: "measured" }));
  baseline.routes["/"].total_bytes = 100000;
  assert.deepEqual(compareBaseline(baseline, measured), [
    "/ total_bytes regressed 100000 -> 111000 (allowed 110000.00000000001)",
  ]);
});

test("runtime-metric jitter inside the Web Vitals good band is not a regression", () => {
  // A ~30 ms TBT median can measure past 100 ms on a shared runner with no code change; while
  // both numbers sit inside the "good" band the gate must not block the merge on runner noise.
  const measured = {
    schema_version: 1,
    max_regression_fraction: 0.1,
    routes: {
      "/": { lcp_ms: 1700, cls: 0.05, tbt_ms: 150, total_bytes: 1, dom_nodes: 1, critical_js_gzip_bytes: 1, critical_css_gzip_bytes: 1 },
      "/sensors/": { lcp_ms: 1500, cls: 0.04, tbt_ms: 80, total_bytes: 1, dom_nodes: 1, critical_js_gzip_bytes: 1, critical_css_gzip_bytes: 1 },
    },
  };
  const baseline = JSON.parse(JSON.stringify({ ...measured, state: "measured" }));
  baseline.routes["/"].tbt_ms = 30;
  baseline.routes["/"].lcp_ms = 1600;
  baseline.routes["/sensors/"].tbt_ms = 31;
  assert.deepEqual(compareBaseline(baseline, measured), []);
});

test("a runtime metric that leaves the good band is still blocked", () => {
  const measured = {
    schema_version: 1,
    max_regression_fraction: 0.1,
    routes: {
      "/": { lcp_ms: 100, cls: 0.01, tbt_ms: 220, total_bytes: 1, dom_nodes: 1, critical_js_gzip_bytes: 1, critical_css_gzip_bytes: 1 },
      "/sensors/": { lcp_ms: 100, cls: 0.01, tbt_ms: 1, total_bytes: 1, dom_nodes: 1, critical_js_gzip_bytes: 1, critical_css_gzip_bytes: 1 },
    },
  };
  const baseline = JSON.parse(JSON.stringify({ ...measured, state: "measured" }));
  baseline.routes["/"].tbt_ms = 30;
  assert.deepEqual(compareBaseline(baseline, measured), ["/ tbt_ms regressed 30 -> 220 (allowed 200)"]);
});

test("candidate requires both route reports", () => {
  assert.throws(() => measuredBaseline([report("/")], process.cwd()), /no Lighthouse report/);
});
