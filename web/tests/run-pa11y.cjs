"use strict";

const { spawn } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");
const pa11y = require("pa11y");

const WEB = path.resolve(__dirname, "..");
const CONFIG = require(path.join(WEB, ".pa11yci.cjs"));
const REPORT = path.join(WEB, "test-results", "pa11y", "results.json");
const LEVEL_CODES = Object.freeze({ error: 1, warning: 2, notice: 3, none: 0 });

// `/sensors/` has no directory of its own: the deploy builds it, and `tests/static-server.cjs`
// synthesizes it from the root shell with Sensor.Community fixtures. It is the one route that
// has to be named here. Every other route is derived from the tree below, so adding a page does
// not silently escape the accessibility gate just because a second hand-maintained list was not
// updated with it.
const SYNTHESIZED_ROUTES = Object.freeze(["/sensors/"]);
const NOT_ROUTES = new Set(["node_modules", "test-results", "vendor"]);

// Every route this repository publishes. A Pa11y run that skipped one of them is not the
// accessibility evidence the `a11y-advisory` job claims to produce, so the config is checked
// against this set rather than trusted to be whatever it happens to say.
function publishedRoutes(web = WEB) {
  const routes = new Set(SYNTHESIZED_ROUTES);
  if (fs.existsSync(path.join(web, "index.html"))) routes.add("/");
  for (const entry of fs.readdirSync(web, { withFileTypes: true })) {
    if (!entry.isDirectory() || entry.name.startsWith(".") || NOT_ROUTES.has(entry.name)) continue;
    if (fs.existsSync(path.join(web, entry.name, "index.html"))) routes.add(`/${entry.name}/`);
  }
  return [...routes].sort();
}

function blocksAtLevel(issue, level) {
  const threshold = LEVEL_CODES[level];
  if (threshold === undefined) throw new Error(`unsupported Pa11y failure level: ${level}`);
  const issueCode = issue.typeCode ?? LEVEL_CODES[issue.type];
  // An issue whose severity this runner cannot interpret used to fall through as non-blocking:
  // `Number.isFinite(undefined)` is false, so an unrecognized `type` with no `typeCode` read
  // exactly like a clean page. A severity we cannot read is not a severity we can clear.
  if (!Number.isFinite(issueCode)) {
    throw new Error(`Pa11y issue has no readable severity: ${JSON.stringify(issue)}`);
  }
  return threshold > 0 && issueCode <= threshold;
}

// The runner's success line is "N/N pages passed". With an empty `urls` list that reads
// "0/0 pages passed" and exits 0 -- a green accessibility gate that loaded no page. Nothing
// downstream would notice, because a Pa11y run over nothing produces no findings.
function configProblems(config, requiredRoutes = publishedRoutes()) {
  const urls = Array.isArray(config && config.urls) ? config.urls : [];
  if (urls.length === 0) {
    return ["Pa11y config lists no URLs; a run over zero pages is not an accessibility result"];
  }
  const paths = new Set(
    urls.map((url) => {
      try {
        return new URL(url).pathname;
      } catch {
        return url;
      }
    }),
  );
  return requiredRoutes
    .filter((route) => !paths.has(route))
    .map((route) => `Pa11y config does not cover published route ${route}`);
}

async function waitForServer() {
  for (let attempt = 0; attempt < 100; attempt += 1) {
    try {
      const response = await fetch("http://127.0.0.1:4173/");
      if (response.ok) return;
    } catch {
      // The child is still starting.
    }
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw new Error("static test server did not start");
}

async function main() {
  const problems = configProblems(CONFIG);
  if (problems.length) {
    for (const problem of problems) console.error(`Pa11y: ${problem}`);
    process.exitCode = 2;
    return;
  }

  const server = spawn(process.execPath, ["tests/static-server.cjs"], {
    cwd: WEB,
    stdio: "inherit",
  });
  try {
    await waitForServer();
    const { reporters: _reporters, level = "error", ...options } = CONFIG.defaults;
    const report = { total: CONFIG.urls.length, passes: 0, errors: 0, results: {} };

    for (const url of CONFIG.urls) {
      const result = await pa11y(url, options);
      const issues = result.issues || [];
      const blocking = issues.filter((issue) => blocksAtLevel(issue, level));
      report.results[result.pageUrl || url] = issues;
      if (blocking.length === 0) {
        report.passes += 1;
        console.log(`PASS ${url}`);
        continue;
      }

      report.errors += blocking.length;
      console.error(`FAIL ${url} (${blocking.length} blocking issue${blocking.length === 1 ? "" : "s"})`);
      for (const issue of blocking) {
        console.error(`  ${issue.code}: ${issue.message} (${issue.selector})`);
      }
    }

    fs.mkdirSync(path.dirname(REPORT), { recursive: true });
    fs.writeFileSync(REPORT, JSON.stringify(report), "utf8");
    console.log(`Pa11y: ${report.passes}/${report.total} pages passed`);
    if (report.errors > 0) process.exitCode = 2;
  } finally {
    server.kill("SIGTERM");
  }
}

module.exports = { SYNTHESIZED_ROUTES, blocksAtLevel, configProblems, publishedRoutes };

if (require.main === module) {
  main().catch((error) => {
    console.error(error);
    process.exitCode = 1;
  });
}
