"use strict";

const fs = require("node:fs");
const http = require("node:http");
const path = require("node:path");
const zlib = require("node:zlib");

const ROOT = path.resolve(__dirname, "..");
const PORT = Number(process.env.SWELTER_TEST_PORT || 4173);
const TYPES = {
  ".css": "text/css; charset=utf-8",
  ".geojson": "application/geo+json",
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".png": "image/png",
  ".svg": "image/svg+xml",
  ".webmanifest": "application/manifest+json",
  ".xml": "application/atom+xml; charset=utf-8",
};
const COMPRESSIBLE = new Set([".css", ".geojson", ".html", ".js", ".json", ".svg", ".webmanifest", ".xml"]);

const sample = JSON.parse(fs.readFileSync(path.join(ROOT, "sample-surface.json"), "utf8"));

function testDemo(
  source,
  attribution,
  parameters = [...new Set(sample.cells.map((cell) => cell.parameter))],
) {
  return Buffer.from(JSON.stringify({
    schema_version: 1,
    runtime: "static",
    source,
    surface: { parameters },
    attribution,
  }));
}

const PRIMARY_DEMO = testDemo({
  id: "synthetic",
  name: { en: "Synthetic demonstration", es: "Demostración sintética" },
  attribution: {
    en: "Synthetic demonstration data — no real sensors.",
    es: "Datos sintéticos de demostración; no son sensores reales.",
  },
  geography: {
    en: "Statewide California preview",
    es: "Vista previa estatal de California",
  },
  calibration: {
    en: "Mixed confirmed and provisional demonstration records.",
    es: "Registros de demostración confirmados y provisionales.",
  },
  uncertainty: {
    en: "Published uncertainty is shown with each record.",
    es: "La incertidumbre publicada se muestra con cada registro.",
  },
  location: {
    en: "Public California place centroids; readings remain synthetic.",
    es: "Centroides de lugares públicos de California; las lecturas siguen siendo sintéticas.",
  },
  tagline: {
    en: "A fast, local audit of the complete observatory.",
    es: "Una auditoría local rápida del observatorio completo.",
  },
  navigation_label: { en: "Demonstration", es: "Demostración" },
  license: {
    summary: { en: "Public-domain demonstration data.", es: "Datos de demostración de dominio público." },
    links: [],
  },
}, sample.attribution);

const SENSOR_ATTRIBUTION =
  "Sensor.Community route fixture — community low-cost sensors, ODC-DbCL-1.0.";
const SENSOR_PARAMETERS = ["pm25_ugm3", "pm10_ugm3", "temp_c"];
const SENSOR_DEMO = testDemo({
  id: "sensor-community",
  name: { en: "Sensor.Community low-cost sensors", es: "Sensores de bajo costo de Sensor.Community" },
  attribution: {
    en: SENSOR_ATTRIBUTION,
    es: "Datos de prueba de Sensor.Community; sensores comunitarios de bajo costo, ODC-DbCL-1.0.",
  },
  geography: { en: "Stuttgart, Germany", es: "Stuttgart, Alemania" },
  calibration: {
    en: "Upstream readings; not calibrated by swelter and shown as provisional.",
    es: "Lecturas externas; swelter no las calibró y se muestran como provisionales.",
  },
  uncertainty: {
    en: "No swelter uncertainty estimate is attached.",
    es: "No se adjunta una estimación de incertidumbre de swelter.",
  },
  location: {
    en: "Public Sensor.Community coordinates near Stuttgart.",
    es: "Coordenadas públicas de Sensor.Community cerca de Stuttgart.",
  },
  tagline: {
    en: "Community air-sensor evidence near Stuttgart.",
    es: "Datos de sensores comunitarios de aire cerca de Stuttgart.",
  },
  navigation_label: { en: "Stuttgart sensors", es: "Sensores de Stuttgart" },
  license: {
    summary: {
      en: "Database contents licensed under ODC-DbCL-1.0.",
      es: "Contenido de la base de datos bajo ODC-DbCL-1.0.",
    },
    links: [{
      href: "https://sensor.community/en/",
      label: { en: "Sensor.Community", es: "Sensor.Community" },
    }],
  },
}, SENSOR_ATTRIBUTION, SENSOR_PARAMETERS);

const sensorSample = {
  ...sample,
  attribution: SENSOR_ATTRIBUTION,
  cells: sample.cells
    .filter((cell) => SENSOR_PARAMETERS.includes(cell.parameter))
    .map((cell) => {
      const nodeNumber = Number(String(cell.nodes?.[0] || "").match(/\d+$/)?.[0]) || 1;
      const index = nodeNumber - 1;
      const lat = 48.7758 + (Math.floor(index / 15) - 4.5) * 0.002;
      const lon = 9.1829 + ((index % 15) - 7) * 0.002;
      return {
        ...cell,
        cell_id: `${lat.toFixed(6)},${lon.toFixed(6)}`,
        label: `Stuttgart sensor ${String(nodeNumber).padStart(3, "0")}`,
        lat,
        lon,
        nodes: (cell.nodes || []).map((node) => `sc-${node}`),
        provisional: true,
        uncertainty: null,
        mean_member_sigma: null,
        uncertainty_note: null,
      };
    }),
};
const SENSOR_SAMPLE = Buffer.from(JSON.stringify(sensorSample));
const SENSOR_SAMPLE_GZIP = zlib.gzipSync(SENSOR_SAMPLE);

function historyFixture(surface) {
  const latest = surface.buckets.at(-1);
  const earlier = new Date(Date.parse(latest) - 60 * 60 * 1000).toISOString().replace(".000Z", "Z");
  return Buffer.from(JSON.stringify({
    ...surface,
    buckets: [earlier, latest],
    cells: [
      ...surface.cells.map((cell) => ({ ...cell, bucket: earlier })),
      ...surface.cells,
    ],
  }));
}

const PRIMARY_HISTORY = historyFixture(sample);
const PRIMARY_HISTORY_GZIP = zlib.gzipSync(PRIMARY_HISTORY);
const SENSOR_HISTORY = historyFixture(sensorSample);
const SENSOR_HISTORY_GZIP = zlib.gzipSync(SENSOR_HISTORY);

const ROUTE_FIXTURES = {
  primary: { demo: PRIMARY_DEMO, surface: null },
  sensors: { demo: SENSOR_DEMO, surface: SENSOR_SAMPLE },
};

function requestRoute(rawUrl) {
  let pathname;
  try {
    pathname = decodeURIComponent(new URL(rawUrl, "http://127.0.0.1").pathname);
  } catch {
    return null;
  }
  const sensors = /^\/sensors(?=\/|$)/.test(pathname);
  return {
    fixture: sensors ? ROUTE_FIXTURES.sensors : ROUTE_FIXTURES.primary,
    pathname: pathname.replace(/^\/sensors(?=\/|$)/, "") || "/",
    sensors,
  };
}

/*
 * The root and /sensors/ pages share an application shell in production, but not a data/source
 * contract. These route fixtures deliberately model that distinction: root serves the committed
 * synthetic sample and California basemap, while /sensors/ serves a Stuttgart-shaped provisional
 * surface, Sensor.Community attribution/license, and no California-only overlays.
 */

function localPath(rawUrl) {
  const route = requestRoute(rawUrl);
  if (!route) return null;
  let { pathname } = route;
  if (pathname.endsWith("/")) pathname += "index.html";
  const resolved = path.resolve(ROOT, `.${pathname}`);
  return resolved === ROOT || resolved.startsWith(`${ROOT}${path.sep}`) ? resolved : null;
}

const server = http.createServer((request, response) => {
  const rawUrl = request.url || "/";
  const route = requestRoute(rawUrl);
  if (!route) {
    response.writeHead(400, { "content-type": "text/plain; charset=utf-8" });
    response.end("Bad request");
    return;
  }
  const { pathname } = route;

  if (pathname === "/demo.json") {
    response.writeHead(200, {
      "cache-control": "public, max-age=300",
      "content-type": TYPES[".json"],
    });
    response.end(request.method === "HEAD" ? undefined : route.fixture.demo);
    return;
  }
  if (pathname === "/sample-surface.json" && route.fixture.surface) {
    const gzip = request.method !== "HEAD" &&
      /(?:^|,)\s*gzip\s*(?:,|$)/i.test(request.headers["accept-encoding"] || "");
    response.writeHead(200, {
      "cache-control": "public, max-age=300",
      ...(gzip ? { "content-encoding": "gzip", vary: "accept-encoding" } : {}),
      "content-type": TYPES[".json"],
    });
    response.end(request.method === "HEAD" ? undefined : gzip ? SENSOR_SAMPLE_GZIP : route.fixture.surface);
    return;
  }
  if (pathname === "/surface-7d.json") {
    const body = route.sensors ? SENSOR_HISTORY : PRIMARY_HISTORY;
    const compressed = route.sensors ? SENSOR_HISTORY_GZIP : PRIMARY_HISTORY_GZIP;
    const gzip = request.method !== "HEAD" &&
      /(?:^|,)\s*gzip\s*(?:,|$)/i.test(request.headers["accept-encoding"] || "");
    response.writeHead(200, {
      "cache-control": "public, max-age=300",
      ...(gzip ? { "content-encoding": "gzip", vary: "accept-encoding" } : {}),
      "content-type": TYPES[".json"],
    });
    response.end(request.method === "HEAD" ? undefined : gzip ? compressed : body);
    return;
  }

  if (route.sensors && ["/basemap.geojson", "/cooling-centers.geojson"].includes(pathname)) {
    response.writeHead(404, { "content-type": "text/plain; charset=utf-8" });
    response.end("Not found on the Sensor.Community route");
    return;
  }

  const file = pathname === "/favicon.ico" ? path.join(ROOT, "icon.svg") : localPath(rawUrl);
  if (!file || !fs.existsSync(file) || !fs.statSync(file).isFile()) {
    response.writeHead(404, { "content-type": "text/plain; charset=utf-8" });
    response.end("Not found");
    return;
  }
  const extension = path.extname(file);
  const gzip = request.method !== "HEAD" &&
    COMPRESSIBLE.has(extension) &&
    /(?:^|,)\s*gzip\s*(?:,|$)/i.test(request.headers["accept-encoding"] || "");
  response.writeHead(200, {
    "cache-control": "public, max-age=300",
    ...(gzip ? { "content-encoding": "gzip", vary: "accept-encoding" } : {}),
    "content-type": TYPES[path.extname(file)] || "application/octet-stream",
  });
  if (request.method === "HEAD") response.end();
  else if (gzip) fs.createReadStream(file).pipe(zlib.createGzip()).pipe(response);
  else fs.createReadStream(file).pipe(response);
});

server.listen(PORT, "127.0.0.1", () => {
  process.stdout.write(`swelter test server: http://127.0.0.1:${PORT}\n`);
});

for (const signal of ["SIGINT", "SIGTERM"]) {
  process.on(signal, () => server.close(() => process.exit(0)));
}
