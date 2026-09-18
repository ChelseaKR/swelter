"use strict";

// Run every named web gate, report each one's own verdict, and fail at the end if any failed.
//
// Why this exists (#282). `test:a11y` was `test:browser && test:pa11y && test:lighthouse`, and
// `test:lighthouse` was itself `run-lighthouse && performance-baseline --check`. A shell `&&` stops
// at the first failure, so every check behind a failed one reported nothing for that run -- and a
// check that did not run looks exactly like a check that passed. Measured on 2026-09-11: Lighthouse
// failed on runner noise, the page-weight check never ran, a re-run passed Lighthouse, and only
// then did the byte check fail deterministically (`/ total_bytes regressed 194513 -> 221077`).
//
// These gates are independent of each other's verdicts. The one real dependency is on an artifact:
// `performance-baseline.cjs --check` reads the reports Lighthouse CI writes during `collect`, which
// happens before LHCI asserts, and it already refuses loudly when they are absent. So running it
// after a failed Lighthouse assertion is the point, not a hazard.
//
// This is `scripts/run_gates.sh` for the dashboard: nothing is suppressed, and nothing hides behind
// anything else's result.

const { spawnSync } = require("node:child_process");
const path = require("node:path");

const WEB = path.resolve(__dirname, "..");
const NPM = process.platform === "win32" ? "npm.cmd" : "npm";

function gateProblems(gates, scripts) {
  if (!Array.isArray(gates) || gates.length === 0) {
    return ["no gates named: a run over zero gates is not a result"];
  }
  const problems = [];
  for (const gate of gates) {
    if (!Object.hasOwn(scripts ?? {}, gate)) problems.push(`no npm script named ${gate}`);
  }
  const repeated = [...new Set(gates.filter((gate, index) => gates.indexOf(gate) !== index))];
  if (repeated.length) problems.push(`gate named more than once: ${repeated.join(", ")}`);
  return problems;
}

function npmRun(gate) {
  const result = spawnSync(NPM, ["run", gate], { cwd: WEB, stdio: "inherit" });
  if (result.error) {
    console.error(result.error);
    return null;
  }
  return result.status;
}

// A gate that exited 0 passed. Anything else -- a non-zero code, a spawn error, or a child killed by
// a signal, which reports `status: null` -- failed. An exit status nobody could read is not a pass.
function runGates(gates, { scripts, run = npmRun, log = console.log, error = console.error } = {}) {
  const problems = gateProblems(gates, scripts);
  if (problems.length) {
    for (const problem of problems) error(`web-gates: ${problem}`);
    return { status: 2, results: [] };
  }
  const results = [];
  for (const gate of gates) {
    log(`\n== npm run ${gate} ==`);
    const code = run(gate);
    const passed = code === 0;
    results.push({ gate, code, passed });
    log(`== ${gate}: ${passed ? "PASS" : `FAIL (exit ${code === null ? "unknown" : code})`} ==`);
  }
  const failed = results.filter((result) => !result.passed).map((result) => result.gate);
  log("");
  if (failed.length) {
    error(`web-gates: FAILED ${failed.length} of ${gates.length}: ${failed.join(", ")}`);
    return { status: 1, results };
  }
  log(`web-gates: all ${gates.length} passed: ${gates.join(", ")}`);
  return { status: 0, results };
}

module.exports = { gateProblems, runGates };

if (require.main === module) {
  const { scripts } = require(path.join(WEB, "package.json"));
  process.exitCode = runGates(process.argv.slice(2), { scripts }).status;
}
