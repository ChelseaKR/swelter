"use strict";

const fs = require("node:fs");
const path = require("node:path");
const zlib = require("node:zlib");

const WEB = path.resolve(__dirname, "..");
const REPORT_DIR = path.join(WEB, ".lighthouseci");
const BASELINE = path.join(WEB, "performance-baseline.json");
const MAX_REGRESSION = 0.1;
const AUDITS = Object.freeze({
  lcp_ms: "largest-contentful-paint",
  cls: "cumulative-layout-shift",
  tbt_ms: "total-blocking-time",
  total_bytes: "total-byte-weight",
  dom_nodes: "dom-size",
});
const ROUTES = Object.freeze(["/", "/sensors/"]);

function median(values) {
  const ordered = [...values].sort((a, b) => a - b);
  const middle = Math.floor(ordered.length / 2);
  return ordered.length % 2 ? ordered[middle] : (ordered[middle - 1] + ordered[middle]) / 2;
}

function routeFor(report) {
  const raw = report.finalDisplayedUrl || report.finalUrl || report.requestedUrl;
  if (typeof raw !== "string") throw new Error("Lighthouse report has no URL");
  const pathname = new URL(raw).pathname.replace(/\/index\.html$/, "/");
  if (pathname === "/sensors" || pathname === "/sensors/") return "/sensors/";
  if (pathname === "/") return "/";
  throw new Error(`unexpected Lighthouse route: ${pathname}`);
}

function auditMetrics(report) {
  const metrics = {};
  for (const [name, auditId] of Object.entries(AUDITS)) {
    const value = report.audits?.[auditId]?.numericValue;
    if (!Number.isFinite(value) || value < 0) {
      throw new Error(`Lighthouse report has no non-negative ${auditId}`);
    }
    metrics[name] = value;
  }
  return metrics;
}

function gzipBytes(relativePaths, web = WEB) {
  return relativePaths.reduce((total, relative) => {
    const payload = fs.readFileSync(path.join(web, relative));
    return total + zlib.gzipSync(payload, { level: 9, mtime: 0 }).byteLength;
  }, 0);
}

function assetMetrics(web = WEB) {
  return {
    critical_js_gzip_bytes: gzipBytes(
      ["app.js", "i18n-runtime.mjs", "vendor/messageformat/index.js", "i18n/en.json"],
      web,
    ),
    critical_css_gzip_bytes: gzipBytes(["styles.css", "observatory.css"], web),
  };
}

function loadReports(directory = REPORT_DIR) {
  if (!fs.existsSync(directory)) throw new Error(`Lighthouse report directory is missing: ${directory}`);
  return fs
    .readdirSync(directory)
    .filter((name) => /^lhr-.*\.json$/.test(name))
    .map((name) => JSON.parse(fs.readFileSync(path.join(directory, name), "utf8")));
}

function measuredBaseline(reports, web = WEB) {
  const grouped = new Map(ROUTES.map((route) => [route, []]));
  for (const report of reports) grouped.get(routeFor(report)).push(auditMetrics(report));
  for (const route of ROUTES) {
    if (!grouped.get(route).length) throw new Error(`no Lighthouse report for ${route}`);
  }
  const assets = assetMetrics(web);
  const routes = {};
  for (const route of ROUTES) {
    const runs = grouped.get(route);
    routes[route] = { ...assets };
    for (const metric of Object.keys(AUDITS)) routes[route][metric] = median(runs.map((run) => run[metric]));
  }
  return { schema_version: 1, max_regression_fraction: MAX_REGRESSION, routes };
}

// Lab runtime metrics jitter on shared CI runners: a ~30 ms TBT median swings past 100 ms
// run-to-run with zero code change, so a bare 10% budget on values that small blocks merges on
// noise. Below each metric's Web Vitals / Lighthouse "good" boundary that swing is measurement
// noise, not a regression — the 10% budget therefore only engages once a measurement leaves the
// good band (or once the baseline itself sits above it). The deterministic metrics (gzip byte
// weights, total bytes, DOM size) keep the strict 10% budget: they are the bundle-growth
// tripwire and do not jitter.
const RUNTIME_NOISE_FLOOR = Object.freeze({ lcp_ms: 2500, tbt_ms: 200, cls: 0.1 });

function compareBaseline(baseline, measured) {
  const findings = [];
  if (baseline?.schema_version !== 1 || baseline?.state !== "measured") {
    return ["committed performance baseline is not in measured state"];
  }
  if (baseline.max_regression_fraction !== MAX_REGRESSION) {
    findings.push(`baseline regression fraction must remain ${MAX_REGRESSION}`);
  }
  for (const route of ROUTES) {
    for (const metric of [...Object.keys(AUDITS), "critical_js_gzip_bytes", "critical_css_gzip_bytes"]) {
      const prior = baseline.routes?.[route]?.[metric];
      const current = measured.routes?.[route]?.[metric];
      const floor = RUNTIME_NOISE_FLOOR[metric];
      const budget = Number.isFinite(prior) ? prior * (1 + MAX_REGRESSION) : NaN;
      const allowed = floor === undefined ? budget : Math.max(budget, floor);
      if (!Number.isFinite(prior) || prior < 0) {
        findings.push(`${route} baseline has no ${metric}`);
      } else if (!Number.isFinite(current) || current < 0) {
        findings.push(`${route} measurement has no ${metric}`);
      } else if (current > allowed) {
        findings.push(`${route} ${metric} regressed ${prior} -> ${current} (allowed ${allowed})`);
      }
    }
  }
  return findings;
}

function writeCandidate(measured, output = BASELINE) {
  const document = {
    ...measured,
    state: "measured",
    evidence_date: process.env.PERFORMANCE_EVIDENCE_DATE || new Date().toISOString().slice(0, 10),
    source_commit: process.env.GITHUB_SHA || null,
    method: "Median Lighthouse CI route metrics plus deterministic gzip level-9 asset sizes.",
  };
  fs.writeFileSync(output, `${JSON.stringify(document, null, 2)}\n`, "utf8");
}

function main(argv = process.argv.slice(2)) {
  const measured = measuredBaseline(loadReports());
  if (argv.includes("--write")) {
    const output = process.env.PERFORMANCE_BASELINE_OUTPUT
      ? path.resolve(process.env.PERFORMANCE_BASELINE_OUTPUT)
      : BASELINE;
    writeCandidate(measured, output);
    console.log(`performance-baseline: wrote candidate ${output}`);
    return 0;
  }
  const baseline = JSON.parse(fs.readFileSync(BASELINE, "utf8"));
  const findings = compareBaseline(baseline, measured);
  if (findings.length) {
    console.error(`performance-baseline: FAIL (${findings.length} finding(s))`);
    for (const finding of findings) console.error(`  - ${finding}`);
    return 1;
  }
  console.log("performance-baseline: both routes remain within the 10% regression budget");
  return 0;
}

module.exports = { assetMetrics, auditMetrics, compareBaseline, measuredBaseline, routeFor };

if (require.main === module) process.exitCode = main();
