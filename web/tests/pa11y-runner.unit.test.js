// The Pa11y runner's own contract. `npm run test:a11y` reports "N/N pages passed", and both
// halves of that fraction come from the same config object — so an emptied `urls` list read as
// "0/0 pages passed" and exited 0: a green accessibility gate that loaded no page and produced
// no findings for anything downstream to notice.

"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const runner = require("./run-pa11y.cjs");
const config = require(path.join(__dirname, "..", ".pa11yci.cjs"));

test("an empty URL list is refused, not reported as 0/0 pages passed", () => {
  const problems = runner.configProblems({ urls: [] });
  assert.equal(problems.length, 1);
  assert.match(problems[0], /a run over zero pages is not an accessibility result/);
  assert.deepEqual(runner.configProblems({}), problems);
  assert.deepEqual(runner.configProblems({ urls: undefined }), problems);
});

test("a config that drops a published route is refused", () => {
  const problems = runner.configProblems({
    urls: ["http://127.0.0.1:4173/", "http://127.0.0.1:4173/sensors/"],
  });
  assert.deepEqual(problems, ["Pa11y config does not cover published route /planner/"]);
});

test("the published route set is derived from the tree, not a second hand-kept list", () => {
  // A page added under web/ must not escape the accessibility gate merely because nobody
  // updated a constant. Only /sensors/, which the deploy and the test server synthesize from
  // the root shell, has to be named.
  const routes = runner.publishedRoutes();
  assert.deepEqual(routes, ["/", "/planner/", "/sensors/"]);
  assert.deepEqual(runner.SYNTHESIZED_ROUTES, ["/sensors/"]);
});

test("the committed Pa11y config covers every published route", () => {
  assert.deepEqual(runner.configProblems(config), []);
  assert.ok(config.urls.length >= runner.publishedRoutes().length);
});

test("a Pa11y issue whose severity cannot be read is not silently cleared", () => {
  // `issue.typeCode ?? LEVEL_CODES[issue.type]` yields undefined for an unrecognized type, and
  // `Number.isFinite(undefined)` is false — so the issue used to fall through as non-blocking,
  // reading exactly like a clean page.
  assert.throws(
    () => runner.blocksAtLevel({ type: "unrecognized", code: "X" }, "error"),
    /no readable severity/,
  );
});

test("severity thresholds still block and clear the issues they are meant to", () => {
  assert.equal(runner.blocksAtLevel({ typeCode: 1, type: "error" }, "error"), true);
  assert.equal(runner.blocksAtLevel({ typeCode: 2, type: "warning" }, "error"), false);
  assert.equal(runner.blocksAtLevel({ typeCode: 2, type: "warning" }, "warning"), true);
  assert.equal(runner.blocksAtLevel({ typeCode: 1, type: "error" }, "none"), false);
  assert.throws(() => runner.blocksAtLevel({ typeCode: 1 }, "bogus"), /unsupported Pa11y failure/);
});
