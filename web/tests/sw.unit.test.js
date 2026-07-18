"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const WORKER_SOURCE = fs.readFileSync(path.join(__dirname, "..", "sw.js"), "utf8");

function deferred() {
  let resolve;
  const promise = new Promise((resolvePromise) => {
    resolve = resolvePromise;
  });
  return { promise, resolve };
}

function loadWorker({
  scope = "https://example.test/swelter/",
  cached,
  fetchImpl = async () => new Response("network"),
  putImpl = async () => undefined,
} = {}) {
  const listeners = new Map();
  const opened = [];
  const puts = [];
  const added = [];
  let stored = cached;
  const cache = {
    async add() {},
    async addAll(assets) {
      added.push(...assets);
    },
    async match() {
      return stored;
    },
    async put(request, response) {
      puts.push({ request, response });
      await putImpl(request, response);
      stored = response;
    },
  };
  const context = {
    Response,
    URL,
    caches: {
      async delete() {},
      async keys() {
        return [];
      },
      async open(name) {
        opened.push(name);
        return cache;
      },
    },
    encodeURIComponent,
    fetch: fetchImpl,
    self: {
      clients: { claim() {} },
      registration: { scope },
      addEventListener(name, listener) {
        listeners.set(name, listener);
      },
      skipWaiting() {},
    },
  };

  vm.runInNewContext(WORKER_SOURCE, context, { filename: "sw.js" });

  function dispatchFetch(url = `${scope}app.js`) {
    const waits = [];
    let response;
    const request = { method: "GET", url };
    listeners.get("fetch")({
      request,
      respondWith(value) {
        response = Promise.resolve(value);
      },
      waitUntil(value) {
        waits.push(Promise.resolve(value));
      },
    });
    assert.ok(response, "fetch handler must call respondWith");
    return { request, response, waits };
  }

  function dispatchInstall() {
    const waits = [];
    listeners.get("install")({
      waitUntil(value) {
        waits.push(Promise.resolve(value));
      },
    });
    return waits;
  }

  return { added, dispatchFetch, dispatchInstall, opened, puts };
}

test("install precaches the MF2 loader and every generated runtime module", async () => {
  const runtimeAssets = [
    "vendor/messageformat/index.js",
    "vendor/messageformat/messageformat.js",
  ];
  const worker = loadWorker({
    fetchImpl: async (request) => {
      assert.equal(request, "vendor/messageformat/asset-manifest.json");
      return Response.json(runtimeAssets);
    },
  });
  await Promise.all(worker.dispatchInstall());
  assert.ok(worker.added.includes("i18n-runtime.mjs"));
  assert.ok(worker.added.includes("vendor/messageformat/asset-manifest.json"));
  assert.deepEqual(
    worker.added.filter((asset) => runtimeAssets.includes(asset)),
    runtimeAssets,
  );
});

test("cache owner encodes the complete registration pathname", async () => {
  const originRoot = loadWorker({
    scope: "https://example.test/",
    cached: new Response("root"),
    fetchImpl: async () => {
      throw new Error("offline");
    },
  });
  const literalRoot = loadWorker({
    scope: "https://example.test/root/",
    cached: new Response("literal root"),
    fetchImpl: async () => {
      throw new Error("offline");
    },
  });

  const first = originRoot.dispatchFetch();
  const second = literalRoot.dispatchFetch();
  await Promise.all([first.response, second.response, ...first.waits, ...second.waits]);

  assert.equal(originRoot.opened[0], "swelter-shell-%2F::v6");
  assert.equal(literalRoot.opened[0], "swelter-shell-%2Froot%2F::v6");
  assert.notEqual(originRoot.opened[0], literalRoot.opened[0]);
});

test("cache hit responds immediately but waitUntil owns the awaited cache.put", async () => {
  const cached = new Response("cached");
  const putStarted = deferred();
  const putFinished = deferred();
  const worker = loadWorker({
    cached,
    putImpl: async () => {
      putStarted.resolve();
      await putFinished.promise;
    },
  });

  const event = worker.dispatchFetch();
  assert.equal(await event.response, cached);
  assert.equal(event.waits.length, 1);
  await putStarted.promise;

  let lifecycleSettled = false;
  event.waits[0].then(() => {
    lifecycleSettled = true;
  });
  await Promise.resolve();
  assert.equal(lifecycleSettled, false, "worker lifetime must include the pending cache write");

  putFinished.resolve();
  await event.waits[0];
  assert.equal(worker.puts.length, 1);
  assert.equal(lifecycleSettled, true);
});

test("cache miss responds from the same revalidation after cache.put completes", async () => {
  const network = new Response("fresh");
  const putStarted = deferred();
  const putFinished = deferred();
  const worker = loadWorker({
    fetchImpl: async () => network,
    putImpl: async () => {
      putStarted.resolve();
      await putFinished.promise;
    },
  });

  const event = worker.dispatchFetch();
  await putStarted.promise;
  let responseSettled = false;
  event.response.then(() => {
    responseSettled = true;
  });
  await Promise.resolve();
  assert.equal(responseSettled, false, "network response must not outrun its cache write");

  putFinished.resolve();
  assert.equal(await event.response, network);
  assert.equal(worker.puts.length, 1);
});

test("cache write failure does not replace a successful network response with a 503", async () => {
  const network = new Response("fresh");
  const worker = loadWorker({
    fetchImpl: async () => network,
    putImpl: async () => {
      throw new Error("quota exceeded");
    },
  });

  const event = worker.dispatchFetch();
  assert.equal(await event.response, network);
  assert.equal(worker.puts.length, 1);
});

test("live API success is cached for an exact offline repeat", async () => {
  let online = true;
  const worker = loadWorker({
    fetchImpl: async () => {
      if (!online) throw new Error("offline");
      return new Response('{"reading":42}', {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    },
  });
  const url = "https://example.test/swelter/api/surface.json?hours=1";

  const first = await worker.dispatchFetch(url).response;
  assert.equal(await first.text(), '{"reading":42}');
  assert.equal(worker.puts.length, 1);

  online = false;
  const repeated = await worker.dispatchFetch(url).response;
  assert.equal(repeated.status, 200);
  assert.equal(await repeated.text(), '{"reading":42}');
  assert.equal(worker.puts.length, 1, "offline fallback must not rewrite the cached response");
});

test("live API cache-write failure still returns the successful network response", async () => {
  const network = new Response("fresh API");
  const worker = loadWorker({
    fetchImpl: async () => network,
    putImpl: async () => {
      throw new Error("quota exceeded");
    },
  });

  const response = await worker.dispatchFetch(
    "https://example.test/swelter/api/surface.json?hours=1",
  ).response;
  assert.equal(response, network);
  assert.equal(worker.puts.length, 1);
});

test("uncached offline shell request resolves to a defined 503 response", async () => {
  const worker = loadWorker({
    fetchImpl: async () => {
      throw new Error("offline");
    },
  });

  const event = worker.dispatchFetch();
  const response = await event.response;
  assert.equal(response.status, 503);
  assert.equal(await response.text(), "Offline — this asset isn't cached yet.");
});
