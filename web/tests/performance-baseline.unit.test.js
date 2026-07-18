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

test("baseline comparison blocks any numeric regression over ten percent", () => {
  const measured = {
    schema_version: 1,
    max_regression_fraction: 0.1,
    routes: {
      "/": { lcp_ms: 111, cls: 1, tbt_ms: 1, total_bytes: 1, dom_nodes: 1, critical_js_gzip_bytes: 1, critical_css_gzip_bytes: 1 },
      "/sensors/": { lcp_ms: 100, cls: 1, tbt_ms: 1, total_bytes: 1, dom_nodes: 1, critical_js_gzip_bytes: 1, critical_css_gzip_bytes: 1 },
    },
  };
  const baseline = JSON.parse(JSON.stringify({ ...measured, state: "measured" }));
  baseline.routes["/"].lcp_ms = 100;
  assert.deepEqual(compareBaseline(baseline, measured), ["/ lcp_ms regressed 100 -> 111 (>10%)"]);
});

test("candidate requires both route reports", () => {
  assert.throws(() => measuredBaseline([report("/")], process.cwd()), /no Lighthouse report/);
});
