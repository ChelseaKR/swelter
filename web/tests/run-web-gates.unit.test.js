// The web gate runner's own contract (#282): every named gate reports on every run.

"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");
const test = require("node:test");

const { gateProblems, runGates } = require("./run-web-gates.cjs");
const pkg = require(path.join(__dirname, "..", "package.json"));

const SCRIPTS = { first: "x", second: "x", third: "x", fourth: "x" };
const quiet = { log: () => {}, error: () => {} };

test("a failure in the first gate does not hide the verdicts behind it", () => {
  // The defect, at its narrowest: with `&&`, `second`..`fourth` would never have been asked.
  const asked = [];
  const outcome = runGates(["first", "second", "third", "fourth"], {
    scripts: SCRIPTS,
    run: (gate) => {
      asked.push(gate);
      return gate === "first" ? 1 : 0;
    },
    ...quiet,
  });
  assert.deepEqual(asked, ["first", "second", "third", "fourth"]);
  assert.deepEqual(
    outcome.results.map(({ gate, passed }) => [gate, passed]),
    [
      ["first", false],
      ["second", true],
      ["third", true],
      ["fourth", true],
    ],
  );
  assert.equal(outcome.status, 1, "running every gate is not tolerating failure");
});

test("a failure late in the list is reported and still fails the run", () => {
  const outcome = runGates(["first", "second"], {
    scripts: SCRIPTS,
    run: (gate) => (gate === "second" ? 7 : 0),
    ...quiet,
  });
  assert.equal(outcome.status, 1);
  assert.deepEqual(outcome.results[1], { gate: "second", code: 7, passed: false });
});

test("a gate whose exit status could not be read is a failure, not a pass", () => {
  // spawnSync reports `status: null` for a child killed by a signal, e.g. a runner timeout.
  const outcome = runGates(["first"], { scripts: SCRIPTS, run: () => null, ...quiet });
  assert.equal(outcome.status, 1);
  assert.equal(outcome.results[0].passed, false);
});

test("every gate passing is the only way to exit 0", () => {
  const outcome = runGates(["first", "second"], { scripts: SCRIPTS, run: () => 0, ...quiet });
  assert.equal(outcome.status, 0);
});

test("an empty, unknown, or repeated gate list is refused before anything runs", () => {
  let ran = false;
  const run = () => {
    ran = true;
    return 0;
  };
  assert.equal(runGates([], { scripts: SCRIPTS, run, ...quiet }).status, 2);
  assert.equal(runGates(["first", "typo"], { scripts: SCRIPTS, run, ...quiet }).status, 2);
  assert.equal(runGates(["first", "first"], { scripts: SCRIPTS, run, ...quiet }).status, 2);
  assert.equal(ran, false, "a refused list must not half-run");
  assert.match(gateProblems([], SCRIPTS)[0], /zero gates is not a result/);
});

test("no browser-gate script chains checks with &&", () => {
  for (const name of ["test:a11y", "test:lighthouse", "test:performance-baseline", "verify"]) {
    assert.ok(pkg.scripts[name], `package.json has no ${name}`);
    assert.doesNotMatch(pkg.scripts[name], /&&/, `${name} chains checks: ${pkg.scripts[name]}`);
  }
});

test("test:a11y runs all four browser gates through the runner, and they all exist", () => {
  const match = /^node tests\/run-web-gates\.cjs (.+)$/.exec(pkg.scripts["test:a11y"]);
  assert.ok(match, `test:a11y does not go through the runner: ${pkg.scripts["test:a11y"]}`);
  const gates = match[1].split(/\s+/);
  assert.deepEqual(gates, [
    "test:browser",
    "test:pa11y",
    "test:lighthouse",
    "test:performance-baseline",
  ]);
  assert.deepEqual(gateProblems(gates, pkg.scripts), []);
});

test("verify runs the unit contract and the same four browser gates", () => {
  const match = /^node tests\/run-web-gates\.cjs (.+)$/.exec(pkg.scripts.verify);
  assert.ok(match, `verify does not go through the runner: ${pkg.scripts.verify}`);
  const gates = match[1].split(/\s+/);
  assert.deepEqual(gates, [
    "test:unit",
    "test:browser",
    "test:pa11y",
    "test:lighthouse",
    "test:performance-baseline",
  ]);
  assert.deepEqual(gateProblems(gates, pkg.scripts), []);
});
