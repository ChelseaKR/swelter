// The JS side of the Python↔JS surface contract (FIX-07): validates the same committed dashboard
// fixtures, against the same shared schemas in `../../schemas/`, that
// `tests/test_schema_contract.py` validates from the Python emitter side. A deliberate field
// change on either side (e.g. `aggregate.CellReading.as_record` or `web/app.js`'s `setData()`)
// must edit the schema and both tests in the same PR — that is the point of a contract: it fails
// loud on exactly one side changing quietly.

"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const Ajv = require("ajv/dist/2020"); // draft 2020-12, matching the schemas' $schema
const addFormats = require("ajv-formats");

const WEB = path.join(__dirname, "..");
const SCHEMAS = path.join(WEB, "..", "schemas");

function readJson(...parts) {
  return JSON.parse(fs.readFileSync(path.join(...parts), "utf8"));
}

function validatorFor(schemaName) {
  const ajv = new Ajv({ allErrors: true, strict: true });
  addFormats(ajv);
  const schema = readJson(SCHEMAS, schemaName);
  return { validate: ajv.compile(schema), schema };
}

function assertValid(validate, payload, label) {
  const ok = validate(payload);
  assert.ok(ok, `${label} failed schema validation:\n${JSON.stringify(validate.errors, null, 2)}`);
}

test("schemas/sample-surface.schema.json is itself valid draft 2020-12", () => {
  const { schema } = validatorFor("sample-surface.schema.json");
  const ajv = new Ajv({ strict: true });
  addFormats(ajv);
  assert.doesNotThrow(() => ajv.compile(schema));
});

test("web/sample-surface.json (the dashboard's offline fallback) matches the schema", () => {
  const { validate } = validatorFor("sample-surface.schema.json");
  const payload = readJson(WEB, "sample-surface.json");
  assertValid(validate, payload, "web/sample-surface.json");
  assert.ok(payload.cells.length > 0, "fixture should exercise at least one cell record");
});

test("web/sample-health.json matches the schema", () => {
  const { validate } = validatorFor("sample-health.schema.json");
  const payload = readJson(WEB, "sample-health.json");
  assertValid(validate, payload, "web/sample-health.json");
});

test("web/alerts.json matches the schema", () => {
  const { validate } = validatorFor("alerts.schema.json");
  const payload = readJson(WEB, "alerts.json");
  assertValid(validate, payload, "web/alerts.json");
});

test("a surface payload missing a required top-level field fails validation", () => {
  const { validate } = validatorFor("sample-surface.schema.json");
  const payload = readJson(WEB, "sample-surface.json");
  delete payload.buckets;
  assert.equal(validate(payload), false, "schema should reject a payload missing `buckets`");
});

test("a cell record with the wrong type for `provisional` fails validation", () => {
  const { validate } = validatorFor("sample-surface.schema.json");
  const payload = readJson(WEB, "sample-surface.json");
  payload.cells[0].provisional = "yes"; // must be boolean, not string
  assert.equal(validate(payload), false, "schema should reject a non-boolean `provisional`");
});

// -- setData() actually parses what the schema says is valid -------------------------------------
// This is the other half of the contract: the schema is a *description* of what app.js consumes,
// not just of what Python emits. Load app.js (via the harness used by app.unit.test.js), feed it a
// schema-valid surface payload, and confirm the functions that read `state.cells` behave sanely on
// every field shape the schema allows (nullable `uncertainty`/`aqi`/`category`, an `exposure` cell
// with its extra fields, optional `nodes`).
const { loadApp } = require("./harness.js");

test("setData() accepts a schema-valid surface payload end to end", async () => {
  const app = await loadApp();
  const payload = readJson(WEB, "sample-surface.json");
  const { validate } = validatorFor("sample-surface.schema.json");
  assertValid(validate, payload, "web/sample-surface.json");

  app.setData(payload);
  assert.equal(app.state.cells.length, payload.cells.length);
  assert.deepEqual(app.state.buckets, payload.buckets);
  assert.ok(app.state.cellIndex.size > 0, "indexCells() should have populated cellIndex");

  // Exercise a formatting function over every cell in the real fixture — this is exactly the
  // "the JS side actually parses it" half of the contract, not just a shape check.
  app.state.parameter = payload.cells[0].parameter;
  for (const cell of payload.cells) {
    assert.doesNotThrow(() => app.describe(cell), `describe() should not throw on ${cell.cell_id}`);
  }
});
