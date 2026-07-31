"use strict";

const { spawn } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");
const pa11y = require("pa11y");

const WEB = path.resolve(__dirname, "..");
const CONFIG = require(path.join(WEB, ".pa11yci.cjs"));
const REPORT = path.join(WEB, "test-results", "pa11y", "results.json");
const LEVEL_CODES = Object.freeze({ error: 1, warning: 2, notice: 3, none: 0 });
const server = spawn(process.execPath, ["tests/static-server.cjs"], { cwd: WEB, stdio: "inherit" });

function blocksAtLevel(issue, level) {
  const threshold = LEVEL_CODES[level];
  if (threshold === undefined) throw new Error(`unsupported Pa11y failure level: ${level}`);
  const issueCode = issue.typeCode ?? LEVEL_CODES[issue.type];
  return threshold > 0 && Number.isFinite(issueCode) && issueCode <= threshold;
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

main().catch((error) => {
  console.error(error);
  server.kill("SIGTERM");
  process.exitCode = 1;
});
