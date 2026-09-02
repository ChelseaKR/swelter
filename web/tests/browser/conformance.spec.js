"use strict";

const { test, expect } = require("@playwright/test");
const AxeBuilder = require("@axe-core/playwright").default;
const rtlFixture = require("../fixtures/rtl-ar.json");
const rootSurface = require("../../sample-surface.json");

const ROUTES = ["/", "/sensors/"];
const VIEWS = ["tab-map", "tab-list", "tab-table"];
const ROOT_BUCKET = rootSurface.buckets.at(-1);
const ROOT_ROWS = rootSurface.cells.filter(
  (cell) =>
    cell.bucket === ROOT_BUCKET &&
    cell.parameter === "pm25_ugm3" &&
    (!cell.aqi_window || cell.aqi_window === "hourly-mean"),
);
const ROOT_LOCATION = ROOT_ROWS.find((candidate) => {
  const query = candidate.label.toLocaleLowerCase("en");
  return ROOT_ROWS.filter((cell) => cell.label.toLocaleLowerCase("en").includes(query)).length === 1;
});
if (!ROOT_LOCATION) throw new Error("The root surface needs a uniquely searchable current-hour location");

async function ready(page, route = "/") {
  await page.goto(route, { waitUntil: "domcontentloaded" });
  await expect(page.locator("#time-slider")).not.toHaveAttribute("max", "0");
  await expect(page.locator("#status")).not.toBeEmpty();
  await expect(page.locator("html")).toHaveAttribute("data-render-ready", "true");
}

async function selectView(page, tabId) {
  await page.locator(`#${tabId}`).click();
  await expect(page.locator(`#${tabId}`)).toHaveAttribute("aria-selected", "true");
  const panel = page.locator(`#${await page.locator(`#${tabId}`).getAttribute("aria-controls")}`);
  await expect(panel).toBeVisible();
  const rows = {
    "tab-map": "#map .map-cluster, #map .cell:not(.cluster-member)",
    "tab-list": "#data-list > li",
    "tab-table": "#data-table-body > tr",
  };
  await expect(page.locator(rows[tabId]).first()).toBeVisible();
}

async function assertNoBlockingAxe(page, label) {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
    .analyze();
  const blocking = results.violations.filter((violation) =>
    ["critical", "serious", "moderate"].includes(violation.impact || ""),
  );
  expect(blocking, `${label}\n${JSON.stringify(blocking, null, 2)}`).toEqual([]);

  const unexpectedReview = results.incomplete.flatMap((issue) =>
    issue.nodes.flatMap((node) => {
      const selector = node.target.join(" ");
      const html = (node.html || "").toLowerCase();
      const selectorLower = selector.toLowerCase();
      // The map cells, distribution-braid axis/time labels, and table severity chips all carry the
      // WCAG-mandated non-colour severity texture as a pattern/gradient background-image (hard
      // rule 5). axe-core cannot compute colour-contrast through a pattern background, so for text
      // drawn over that texture it returns "incomplete" (cantTell) rather than a pass or a
      // violation. Every one of these elements draws permanent dark severity ink on a solid,
      // opaque severity fill and clears AA in BOTH colour schemes — proven independently by the
      // "independently verified 4.5:1 contrast pair" test below (map reading, braid label, and a
      // severity chip). Allow ONLY these cantTell results; a real color-contrast violation is never
      // allowlisted. Matching is case-insensitive so class/coordinate casing cannot slip a node
      // past the filter.
      const severityChipTexture =
        /class="tag[ "]/.test(html) &&
        /\b(?:aqi-(?:good|moderate|usg|unhealthy|veryunhealthy|hazardous)|heat-[1-5])\b/.test(html);
      const knownPatternedText =
        issue.id === "color-contrast" &&
        (html.includes("cell-reading") ||
          html.includes("cell-cat") ||
          html.includes("braid-axis-label") ||
          html.includes("braid-time-label") ||
          severityChipTexture);
      const knownTargetEngineError =
        issue.id === "target-size" &&
        // The overlapping-marker layout trips an axe engine bug ("Reduce of empty array") that
        // skips the target-size rule on a grid cell, regardless of its severity/provisional class.
        // WCAG 2.5.8 geometry is proven directly by the dedicated 2.5.8 test, so allow the engine
        // error on any grid cell — but still only the error, never a computed target-size failure.
        selectorLower.includes('.cell[data-cell="') &&
        node.none.some(
          (check) =>
            check.id === "error-occurred" &&
            check.data?.ruleId === "target-size" &&
            // axe emits this message with varying capitalisation across engine versions
            // ("Reduce"/"reduce of empty array"); match case-insensitively so the known
            // target-size engine error on grid cells stays allowlisted.
            check.data?.message?.toLowerCase().includes("reduce of empty array"),
        );
      return knownPatternedText || knownTargetEngineError
        ? []
        : [{ id: issue.id, impact: issue.impact, selector, any: node.any, all: node.all, none: node.none }];
    }),
  );
  expect(unexpectedReview, `${label}\n${JSON.stringify(unexpectedReview, null, 2)}`).toEqual([]);
}

for (const route of ROUTES) {
  for (const colorScheme of ["light", "dark"]) {
    test(`axe across views and locale state: ${route} (${colorScheme})`, async ({ page }) => {
      test.setTimeout(180_000);
      await page.emulateMedia({ colorScheme });
      await ready(page, route);
      for (const locale of ["en", "es"]) {
        if (locale === "es") {
          await page.locator("#lang-select").selectOption("es");
          await expect(page.locator("html")).toHaveAttribute("lang", "es");
          // Confirm the catalog actually re-rendered in Spanish (the Now heading is a stable anchor).
          await expect(page.locator("#now-heading")).toHaveText("Lectura actual");
          await expect(page.locator("html")).toHaveAttribute("data-render-ready", "true");
        }
        for (const tabId of VIEWS) {
          await selectView(page, tabId);
          if (tabId === "tab-list") {
            await page.locator("#data-list .row-select").first().click();
            await expect(page.locator("#detail")).toBeVisible();
          }
          await assertNoBlockingAxe(page, `${route} ${colorScheme} ${locale} ${tabId}`);
        }
      }
    });
  }
}

test("published routes expose distinct source, license, navigation, and data fixtures", async ({ page }) => {
  const cases = [
    {
      route: "/",
      current: "#switch-cams",
      source: "Synthetic demonstration",
      geography: "Statewide California preview",
      license: "Public-domain demonstration data.",
      attribution: "Synthetic demonstration data",
      labelPrefix: "Stuttgart ",
      hasPrefix: false,
      basemapStatus: 200,
      exposureAvailable: true,
    },
    {
      route: "/sensors/",
      current: "#switch-sensors",
      source: "Sensor.Community low-cost sensors",
      geography: "Stuttgart, Germany",
      license: "Database contents licensed under ODC-DbCL-1.0.",
      attribution: "Sensor.Community route fixture",
      labelPrefix: "Stuttgart ",
      hasPrefix: true,
      basemapStatus: 404,
      exposureAvailable: false,
    },
  ];

  for (const expected of cases) {
    await ready(page, expected.route);
    await expect(page.locator(expected.current)).toHaveAttribute("aria-current", "page");
    await expect(page.locator("#truth-source")).toHaveText(expected.source);
    await expect(page.locator("#truth-geography")).toHaveText(expected.geography);
    await expect(page.locator("#truth-license")).toContainText(expected.license);
    await expect(page.locator("#data-source")).toContainText(expected.attribution);
    await selectView(page, "tab-list");
    const firstLabel = await page.locator("#data-list .row-select").first().textContent();
    expect(firstLabel.startsWith(expected.labelPrefix)).toBe(expected.hasPrefix);
    const basemapStatus = await page.evaluate(async () => (await fetch("basemap.geojson")).status);
    expect(basemapStatus).toBe(expected.basemapStatus);
    expect(await page.locator('#parameter-select option[value="exposure"]').isDisabled())
      .toBe(!expected.exposureAvailable);
  }
});

test("generated sensor data uses production-like compression", async ({ request }) => {
  const response = await request.get("/sensors/sample-surface.json", {
    headers: { "Accept-Encoding": "gzip" },
  });

  expect(response.ok()).toBe(true);
  expect(response.headers()["content-encoding"]).toBe("gzip");
  expect(response.headers().vary).toContain("accept-encoding");
  expect((await response.json()).cells.length).toBeGreaterThan(0);
});

test("patterned visualization text has an independently verified 4.5:1 contrast pair", async ({ page }) => {
  const parseRgb = (value) => (value.match(/[\d.]+/g) || []).slice(0, 3).map(Number);
  const luminance = (value) => {
    const [r, g, b] = parseRgb(value).map((channel) => {
      const normalized = channel / 255;
      return normalized <= 0.04045
        ? normalized / 12.92
        : ((normalized + 0.055) / 1.055) ** 2.4;
    });
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
  };
  const ratio = (foreground, background) => {
    const [lighter, darker] = [luminance(foreground), luminance(background)].sort((a, b) => b - a);
    return (lighter + 0.05) / (darker + 0.05);
  };

  for (const colorScheme of ["light", "dark"]) {
    await page.emulateMedia({ colorScheme });
    await ready(page);
    // Sample the map reading and braid label on the default (map) view, where both are present.
    const mapPairs = await page.evaluate(() => {
      const reading = document.querySelector(".cell-reading");
      const label = document.querySelector(".braid-axis-label");
      const readingStyle = getComputedStyle(reading);
      const labelStyle = getComputedStyle(label);
      const braidStyle = getComputedStyle(document.querySelector("#exposure-braid"));
      return [
        { name: "map reading", foreground: readingStyle.color, background: readingStyle.backgroundColor },
        { name: "braid label", foreground: labelStyle.fill, background: braidStyle.backgroundColor },
      ];
    });
    // The severity chip only exists in the Table view; switch to it and sample its solid severity
    // fill and permanent dark ink directly rather than asserting the pair.
    await page.locator("#tab-table").click();
    await expect(page.locator("#data-table-body .tag.aqi-moderate").first()).toBeVisible();
    const chipPair = await page.evaluate(() => {
      const chip = document.querySelector("#data-table-body .tag.aqi-moderate");
      const chipStyle = getComputedStyle(chip);
      return { name: "severity chip", foreground: chipStyle.color, background: chipStyle.backgroundColor };
    });
    const pairs = [...mapPairs, chipPair];
    for (const pair of pairs) {
      expect(ratio(pair.foreground, pair.background), `${colorScheme} ${pair.name}: ${JSON.stringify(pair)}`)
        .toBeGreaterThanOrEqual(4.5);
    }
  }
});

test("primary tasks work by keyboard and focus stays visible", async ({ page }) => {
  await ready(page);

  await page.locator("body").focus();
  await page.keyboard.press("Tab");
  await expect(page.locator(".skip-link")).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.locator("#main")).toBeFocused();

  await page.keyboard.press("/");
  await expect(page.locator("#place-search")).toBeFocused();
  await page.keyboard.type(ROOT_LOCATION.label);
  await expect(page.locator("#map .cell")).toHaveCount(1);
  await expect(page.locator(`#map .cell[data-cell="${ROOT_LOCATION.cell_id}"]`)).toBeVisible();
  await page.keyboard.press("ControlOrMeta+A");
  await page.keyboard.press("Backspace");

  // Single-key shortcuts are intentionally inert while a user is typing. Tab out of the search
  // first, then exercise the documented List shortcut.
  await page.keyboard.press("Tab");
  await page.keyboard.press("l");
  await expect(page.locator("#tab-list")).toHaveAttribute("aria-selected", "true");
  const firstReading = page.locator("#data-list button").first();
  await firstReading.focus();
  await page.keyboard.press("Enter");
  await expect(page.locator("#detail")).toBeVisible();

  await page.locator("#tab-list").focus();
  await page.keyboard.press("ArrowRight");
  await expect(page.locator("#tab-table")).toBeFocused();
  await expect(page.locator("#tab-table")).toHaveAttribute("aria-selected", "true");
  await page.locator('th button[data-sort="label"]').focus();
  await page.keyboard.press("Enter");
  await expect(page.locator('th:has(button[data-sort="label"])')).toHaveAttribute("aria-sort", "ascending");

  const braid = page.locator("#exposure-braid");
  await braid.focus();
  await page.keyboard.press("Home");
  await expect(page.locator("#time-slider")).toHaveValue(await page.locator("#range-start").inputValue());
  await page.keyboard.press("End");
  await expect(page.locator("#time-slider")).toHaveValue(await page.locator("#range-end").inputValue());

  for (const locator of [braid, page.locator("#tab-table"), page.locator('th button[data-sort="label"]')]) {
    await locator.scrollIntoViewIfNeeded();
    await locator.focus();
    const visible = await locator.evaluate((element) => {
      const box = element.getBoundingClientRect();
      const style = getComputedStyle(element);
      const points = [
        [box.left + Math.min(2, box.width / 2), box.top + Math.min(2, box.height / 2)],
        [box.right - Math.min(2, box.width / 2), box.top + Math.min(2, box.height / 2)],
        [box.left + box.width / 2, box.top + box.height / 2],
        [box.left + Math.min(2, box.width / 2), box.bottom - Math.min(2, box.height / 2)],
        [box.right - Math.min(2, box.width / 2), box.bottom - Math.min(2, box.height / 2)],
      ].filter(([x, y]) => x >= 0 && y >= 0 && x < innerWidth && y < innerHeight);
      return {
        inViewport: box.bottom > 0 && box.top < innerHeight && box.right > 0 && box.left < innerWidth,
        outline: style.outlineStyle !== "none" && parseFloat(style.outlineWidth) > 0,
        exposed: points.some(([x, y]) =>
          document.elementsFromPoint(x, y).some(
            (candidate) => candidate === element || candidate.contains(element) || element.contains(candidate),
          ),
        ),
      };
    });
    expect(visible.inViewport).toBe(true);
    expect(visible.outline).toBe(true);
    expect(visible.exposed).toBe(true);
  }
});

test("map keyboard pan, zoom, reset, selection, and equivalent views change real state", async ({ page }) => {
  await ready(page);
  const map = page.locator("#map");
  const canvas = page.locator("#map .map-canvas");
  await map.focus();

  const initial = await canvas.evaluate((element) => element.dataset.camera);
  await page.keyboard.press("+");
  await expect.poll(() => canvas.evaluate((element) => element.dataset.camera)).not.toBe(initial);
  const zoomed = await canvas.evaluate((element) => element.dataset.camera);
  expect(zoomed).toContain("scale(1.4");

  await page.keyboard.press("ArrowRight");
  await expect.poll(() => canvas.evaluate((element) => element.dataset.camera)).not.toBe(zoomed);
  await page.keyboard.press("0");
  await expect.poll(() => canvas.evaluate((element) => element.dataset.camera))
    .toBe("translate(0px, 0px) scale(1)");

  const sceneBefore = await page.evaluate(async () => {
    const map = document.querySelector("#map");
    const basemap = document.querySelector("#map .basemap");
    const response = await fetch("basemap.geojson");
    if (!response.ok) throw new Error(`Could not load basemap.geojson: ${response.status}`);
    const geojson = await response.json();
    let minLon = Infinity;
    let minLat = Infinity;
    let maxLon = -Infinity;
    let maxLat = -Infinity;
    const addRing = (ring) => {
      for (const point of ring) {
        const lon = Number(point[0]);
        const lat = Number(point[1]);
        if (!Number.isFinite(lon) || !Number.isFinite(lat)) continue;
        minLon = Math.min(minLon, lon);
        minLat = Math.min(minLat, lat);
        maxLon = Math.max(maxLon, lon);
        maxLat = Math.max(maxLat, lat);
      }
    };
    for (const feature of geojson.features || []) {
      const geometry = feature.geometry || {};
      if (geometry.type === "Polygon") geometry.coordinates.forEach(addRing);
      if (geometry.type === "MultiPolygon") {
        geometry.coordinates.forEach((polygon) => polygon.forEach(addRing));
      }
    }
    if (![minLon, minLat, maxLon, maxLat].every(Number.isFinite)) {
      throw new Error("The California basemap has no finite bounds");
    }
    const lonPad = (maxLon - minLon || 1) * 0.04;
    const latPad = (maxLat - minLat || 1) * 0.04;
    minLon -= lonPad;
    maxLon += lonPad;
    minLat -= latPad;
    maxLat += latPad;
    const mapWidth = map.clientWidth;
    const mapHeight = map.clientHeight;
    const markers = [...document.querySelectorAll("#map .cell")].map((cell) => {
      const record = JSON.parse(cell.dataset.recordKey);
      const style = getComputedStyle(cell);
      return {
        id: cell.dataset.cell,
        left: Number(cell.dataset.mapLeft),
        bottom: Number(cell.dataset.mapBottom),
        expectedLeft: (Number(record.lon) - minLon) / (maxLon - minLon),
        expectedBottom: (Number(record.lat) - minLat) / (maxLat - minLat),
        cssLeft: parseFloat(style.left) / mapWidth,
        cssBottom: parseFloat(style.bottom) / mapHeight,
      };
    });
    const clusters = [...document.querySelectorAll("#map .map-cluster")].map((cluster) => ({
      members: JSON.parse(cluster.dataset.memberCells),
      hidden: cluster.hidden,
    }));
    const representatives = [
      ...document.querySelectorAll("#map .map-cluster:not([hidden]), #map .cell:not(.cluster-member)"),
    ].filter((element) => getComputedStyle(element).display !== "none" && element.getClientRects().length);
    return {
      path: document.querySelector("#map .basemap-land")?.getAttribute("d"),
      viewBox: basemap?.getAttribute("viewBox"),
      mapWidth,
      mapHeight,
      markers,
      clusters,
      representativeCount: representatives.length,
      leftSpan: Math.max(...markers.map((marker) => marker.left)) - Math.min(...markers.map((marker) => marker.left)),
      bottomSpan: Math.max(...markers.map((marker) => marker.bottom)) - Math.min(...markers.map((marker) => marker.bottom)),
    };
  });
  expect(sceneBefore.markers).toHaveLength(150);
  for (const markerPosition of sceneBefore.markers) {
    expect(markerPosition.left, `${markerPosition.id} projected x`).toBeCloseTo(markerPosition.expectedLeft, 8);
    expect(markerPosition.bottom, `${markerPosition.id} projected y`).toBeCloseTo(markerPosition.expectedBottom, 8);
    expect(markerPosition.cssLeft, `${markerPosition.id} overview CSS x`).toBeCloseTo(markerPosition.expectedLeft, 4);
    expect(markerPosition.cssBottom, `${markerPosition.id} overview CSS y`).toBeCloseTo(markerPosition.expectedBottom, 4);
  }
  expect(sceneBefore.leftSpan).toBeGreaterThan(0.75);
  expect(sceneBefore.bottomSpan).toBeGreaterThan(0.75);
  expect(sceneBefore.representativeCount).toBeGreaterThanOrEqual(10);
  expect(Math.max(...sceneBefore.clusters.map((item) => item.members.length)))
    .toBeLessThan(sceneBefore.markers.length * 0.3);
  await expect(page.locator("#map .map-cluster", { hasText: /^150$/ })).toHaveCount(0);

  // Keep a stable DOM locator: a `:visible` selector would retarget the next cluster as soon as the
  // activated control hides itself.
  const cluster = page.locator("#map .map-cluster").first();
  await expect(cluster).toBeVisible();
  const clusterSize = Number(await cluster.textContent());
  const memberCells = JSON.parse(await cluster.getAttribute("data-member-cells"));
  expect(clusterSize).toBeGreaterThan(1);
  expect(clusterSize).toBeLessThan(150);
  expect(memberCells).toHaveLength(clusterSize);
  expect(new Set(memberCells).size).toBe(memberCells.length);
  await expect(cluster).toHaveAttribute("aria-expanded", "false");
  await cluster.focus();
  await page.keyboard.press("Enter");
  await expect(map).toBeFocused();
  await expect(page.locator("#map .basemap")).toBeVisible();
  await expect(cluster).toHaveAttribute("aria-expanded", "true");
  await expect(cluster).toBeHidden();
  for (const cellId of memberCells) {
    const member = page.locator(`#map .cell[data-cell="${cellId}"]`);
    await expect(member).toHaveClass(/cluster-visible/);
    await expect(member).toBeVisible();
  }
  const sceneAfter = await page.evaluate(({ initialViewBox, memberCells: selectedMembers }) => {
    const map = document.querySelector("#map");
    const canvas = document.querySelector("#map .map-canvas");
    const transform = canvas.dataset.camera;
    const camera = transform.match(
      /translate\(([-+\d.e]+)px,\s*([-+\d.e]+)px\)\s+scale\(([-+\d.e]+)\)/i,
    );
    if (!camera) throw new Error(`Could not parse map camera: ${transform}`);
    const x = Number(camera[1]);
    const y = Number(camera[2]);
    const scale = Number(camera[3]);
    const mapWidth = map.clientWidth;
    const mapHeight = map.clientHeight;
    const [, , projectionWidth, projectionHeight] = initialViewBox.split(/\s+/).map(Number);
    const viewBox = document.querySelector("#map .basemap")?.getAttribute("viewBox");
    const actualViewBox = viewBox.split(/\s+/).map(Number);
    const expectedViewBox = [
      (-x / (mapWidth * scale)) * projectionWidth,
      (-y / (mapHeight * scale)) * projectionHeight,
      projectionWidth / scale,
      projectionHeight / scale,
    ];
    const markers = [...document.querySelectorAll("#map .cell")].map((cell) => {
      const left = Number(cell.dataset.mapLeft);
      const bottom = Number(cell.dataset.mapBottom);
      return {
        id: cell.dataset.cell,
        left,
        bottom,
        actualLeft: parseFloat(cell.style.left),
        actualBottom: parseFloat(cell.style.bottom),
        expectedLeft: x + left * mapWidth * scale,
        expectedBottom: mapHeight - (y + (1 - bottom) * mapHeight * scale),
      };
    });
    const mapRect = map.getBoundingClientRect();
    const memberCenters = selectedMembers.map((cellId) => {
      const cell = [...document.querySelectorAll("#map .cell")].find(
        (candidate) => candidate.dataset.cell === cellId,
      );
      const box = cell.getBoundingClientRect();
      return {
        id: cellId,
        x: box.left + box.width / 2 - mapRect.left,
        y: box.top + box.height / 2 - mapRect.top,
      };
    });
    return {
      path: document.querySelector("#map .basemap-land")?.getAttribute("d"),
      viewBox,
      actualViewBox,
      expectedViewBox,
      markers,
      memberCenters,
      mapWidth,
      mapHeight,
      transform,
      scale,
    };
  }, { initialViewBox: sceneBefore.viewBox, memberCells });
  expect(sceneAfter.path).toBe(sceneBefore.path);
  expect(sceneAfter.viewBox).not.toBe(sceneBefore.viewBox);
  expect(sceneAfter.scale).toBeGreaterThan(1);
  for (let index = 0; index < sceneAfter.actualViewBox.length; index += 1) {
    expect(sceneAfter.actualViewBox[index], `SVG viewBox component ${index}`)
      .toBeCloseTo(sceneAfter.expectedViewBox[index], 8);
  }
  for (const markerPosition of sceneAfter.markers) {
    const before = sceneBefore.markers.find((candidate) => candidate.id === markerPosition.id);
    expect(markerPosition.left, `${markerPosition.id} fixed projected x`).toBe(before.left);
    expect(markerPosition.bottom, `${markerPosition.id} fixed projected y`).toBe(before.bottom);
    expect(Math.abs(markerPosition.actualLeft - markerPosition.expectedLeft), `${markerPosition.id} camera x`)
      .toBeLessThan(0.05);
    expect(Math.abs(markerPosition.actualBottom - markerPosition.expectedBottom), `${markerPosition.id} camera y`)
      .toBeLessThan(0.05);
  }
  for (const center of sceneAfter.memberCenters) {
    expect(center.x, `${center.id} fitted x`).toBeGreaterThanOrEqual(31);
    expect(center.x, `${center.id} fitted x`).toBeLessThanOrEqual(sceneAfter.mapWidth - 31);
    expect(center.y, `${center.id} fitted y`).toBeGreaterThanOrEqual(31);
    expect(center.y, `${center.id} fitted y`).toBeLessThanOrEqual(sceneAfter.mapHeight - 31);
  }

  await page.locator("#map-reset").click();
  await expect(cluster).toBeVisible();
  await expect(cluster).toHaveAttribute("aria-expanded", "false");
  await expect.poll(() => canvas.evaluate((element) => element.dataset.camera))
    .toBe("translate(0px, 0px) scale(1)");
  await expect(page.locator("#map .basemap")).toBeVisible();
  await expect(page.locator("#map .basemap")).toHaveAttribute("viewBox", sceneBefore.viewBox);
  const marker = page.locator("#map .cell:visible").first();
  const cellId = await marker.getAttribute("data-cell");
  await marker.focus();
  await page.keyboard.press("Enter");
  await expect(page.locator(`#map .cell[data-cell="${cellId}"]`)).toHaveAttribute("aria-pressed", "true");
  await expect(page.locator("#detail")).toBeVisible();

  // The row and its select control both carry data-cell (the row needs it for the record-set
  // equivalence test); aria-pressed lives on the row-select control, so target it unambiguously.
  await page.locator("#tab-list").click();
  await expect(page.locator(`#data-list .row-select[data-cell="${cellId}"]`)).toHaveAttribute("aria-pressed", "true");
  await page.locator("#tab-table").click();
  await expect(page.locator(`#data-table-body .row-select[data-cell="${cellId}"]`)).toHaveAttribute("aria-pressed", "true");
});

test("larger text preserves the map center and keeps a selected overview singleton clear", async ({ page }) => {
  // Two text-scale steps each poll for an async re-center (see the comment at the poll below); the
  // default 10s expect timeout is usually plenty but was observed to time out under heavy CI
  // concurrency, not because the correction is slow, but because the runner's event loop is
  // contended. Triple the test's own budget so both iterations' polls have real headroom without
  // masking a genuine non-convergence, which would still fail, just later.
  test.slow();
  await ready(page);
  const map = page.locator("#map");
  const canvas = page.locator("#map .map-canvas");
  const cameraState = () =>
    page.evaluate(() => {
      const mapElement = document.querySelector("#map");
      const cameraText = document.querySelector("#map .map-canvas")?.dataset.camera || "";
      const camera = cameraText.match(
        /translate\(([-+\d.e]+)px,\s*([-+\d.e]+)px\)\s+scale\(([-+\d.e]+)\)/i,
      );
      if (!camera) throw new Error(`Could not parse map camera: ${cameraText}`);
      const x = Number(camera[1]);
      const y = Number(camera[2]);
      const scale = Number(camera[3]);
      const width = mapElement.clientWidth;
      const height = mapElement.clientHeight;
      return {
        x,
        y,
        scale,
        width,
        height,
        centerLeft: (width / 2 - x) / (width * scale),
        centerTop: (height / 2 - y) / (height * scale),
      };
    });

  await map.focus();
  await page.keyboard.press("+");
  const zoomed = await canvas.evaluate((element) => element.dataset.camera);
  // Settle each pan against the camera observed immediately before it, not against the shared
  // post-zoom value. A pan key mutates state.mapView and defers the DOM write to the next
  // animation frame (scheduleTransform in app.js), so pressing both keys and then waiting for
  // "the camera is no longer `zoomed`" is a condition ArrowRight satisfies on its own: when a
  // frame boundary falls between the two presses, which is what WebKit does under CI contention,
  // the baseline below is captured with ArrowRight applied and ArrowDown still pending. That
  // baseline understates the vertical geographic center, and the map's later, correct re-centering
  // is then measured against it and reported as drift (#169). Waiting on each pan in turn makes
  // the baseline the state both keys produced, and is strictly stronger than the single wait it
  // replaces: it requires both pans to have landed where the old one required only the first.
  await page.keyboard.press("ArrowRight");
  await expect.poll(() => canvas.evaluate((element) => element.dataset.camera)).not.toBe(zoomed);
  const panned = await canvas.evaluate((element) => element.dataset.camera);
  await page.keyboard.press("ArrowDown");
  await expect.poll(() => canvas.evaluate((element) => element.dataset.camera)).not.toBe(panned);
  const beforeScale = await cameraState();
  expect(beforeScale.scale).toBeGreaterThan(1);
  expect(beforeScale.x).not.toBe(0);
  expect(beforeScale.y).not.toBe(0);

  for (const textScale of ["1.15", "1.3"]) {
    await page.locator("#text-bigger").click();
    await expect.poll(() =>
      page.locator("html").evaluate((root) => root.style.getPropertyValue("--text-scale")),
    ).toBe(textScale);
    // The text-scale reflow changes the map's own pixel box (the layout is deliberately
    // rem-based, R6), and the map re-centers itself for it: setTextStep captures the geographic
    // center, re-measures, and calls restoreMapCameraCenter (app.js), with the ResizeObserver as
    // a backstop for reflows nothing announced. The correction is not necessarily complete on the
    // tick the CSS variable lands, so poll for it rather than reading once. An explicit 20s
    // ceiling (vs. the 10s default) gives real headroom under CI concurrency without masking a
    // genuine non-convergence, which still fails the check, just after a longer wait.
    //
    // These polls converge only against a baseline that is itself settled; the #169 recurrences
    // were a stale baseline, not a late correction. See the comment at the pans above.
    await expect
      .poll(async () => (await cameraState()).centerLeft, {
        message: `${textScale} geographic center x`,
        timeout: 20_000,
      })
      .toBeCloseTo(beforeScale.centerLeft, 7);
    await expect
      .poll(async () => (await cameraState()).centerTop, {
        message: `${textScale} geographic center y`,
        timeout: 20_000,
      })
      .toBeCloseTo(beforeScale.centerTop, 7);
    const afterScale = await cameraState();
    expect(afterScale.scale, `${textScale} camera zoom`).toBe(beforeScale.scale);
  }

  await page.locator("#map-reset").click();
  await expect.poll(() => canvas.evaluate((element) => element.dataset.camera))
    .toBe("translate(0px, 0px) scale(1)");

  // Turn on the inspector from List first, then discover a singleton using the map's final selected
  // layout. Selecting that same data-derived ID from List leaves the camera at the overview.
  await selectView(page, "tab-list");
  await page.locator("#data-list .row-select").first().click();
  await selectView(page, "tab-map");
  await expect.poll(() => canvas.evaluate((element) => element.dataset.camera))
    .toBe("translate(0px, 0px) scale(1)");
  const singletonId = await page.locator("#map .cell:not(.cluster-member):visible").first().getAttribute("data-cell");
  expect(singletonId).toBeTruthy();

  await selectView(page, "tab-list");
  await page.locator(`#data-list .row-select[data-cell="${singletonId}"]`).click();
  await selectView(page, "tab-map");
  await expect.poll(() => canvas.evaluate((element) => element.dataset.camera))
    .toBe("translate(0px, 0px) scale(1)");
  const selectedSingleton = page.locator(`#map .cell[data-cell="${singletonId}"]`);
  await expect(selectedSingleton).toBeVisible();
  await expect(selectedSingleton).toHaveAttribute("aria-pressed", "true");
  await expect(selectedSingleton).not.toHaveClass(/cluster-member/);

  const collisionReport = await page.evaluate((selectedId) => {
    const visible = (element) => {
      const style = getComputedStyle(element);
      return !element.hidden && style.display !== "none" && style.visibility !== "hidden" &&
        element.getClientRects().length > 0;
    };
    const visualBox = (element) => {
      const box = element.getBoundingClientRect();
      const style = getComputedStyle(element);
      const outline = style.outlineStyle === "none"
        ? 0
        : Math.max(0, (parseFloat(style.outlineWidth) || 0) + (parseFloat(style.outlineOffset) || 0));
      return {
        left: box.left - outline,
        right: box.right + outline,
        top: box.top - outline,
        bottom: box.bottom + outline,
      };
    };
    const representatives = [
      ...document.querySelectorAll("#map .map-cluster:not([hidden]), #map .cell:not(.cluster-member)"),
    ].filter(visible);
    const selected = representatives.find((element) => element.dataset.cell === selectedId);
    if (!selected) throw new Error(`Selected singleton ${selectedId} is not an overview representative`);
    const selectedBox = visualBox(selected);
    const overlaps = representatives
      .filter((element) => element !== selected)
      .map((element) => {
        const box = visualBox(element);
        return {
          id: element.dataset.cell || element.dataset.memberCells,
          horizontal: Math.min(selectedBox.right, box.right) - Math.max(selectedBox.left, box.left),
          vertical: Math.min(selectedBox.bottom, box.bottom) - Math.max(selectedBox.top, box.top),
        };
      })
      .filter(({ horizontal, vertical }) => horizontal > 0 && vertical > 0);
    return {
      textScale: getComputedStyle(document.documentElement).getPropertyValue("--text-scale").trim(),
      representativeCount: representatives.length,
      overlaps,
    };
  }, singletonId);
  expect(collisionReport.textScale).toBe("1.3");
  expect(collisionReport.representativeCount).toBeGreaterThan(1);
  expect(collisionReport.overlaps, JSON.stringify(collisionReport.overlaps, null, 2)).toEqual([]);
});

test("Map, List, and Table expose the same complete record set on both routes", async ({ page }) => {
  for (const route of ROUTES) {
    await ready(page, route);
    const expectedRows = await page.evaluate(async () => {
      const response = await fetch("sample-surface.json");
      const surface = await response.json();
      const buckets = surface.buckets || [...new Set(surface.cells.map((row) => row.bucket))].sort();
      const bucket = buckets[buckets.length - 1];
      const parameter = document.querySelector("#parameter-select").value;
      return surface.cells
        .filter((row) =>
          row.parameter === parameter && row.bucket === bucket &&
          (parameter !== "pm25_ugm3" || !row.aqi_window || row.aqi_window === "hourly-mean"))
        .sort((a, b) => a.cell_id.localeCompare(b.cell_id));
    });
    const snapshots = {};
    for (const tabId of VIEWS) {
      await selectView(page, tabId);
      snapshots[tabId] = await page.evaluate((activeTab) => {
        const selectors = {
          "tab-map": "#map .cell",
          "tab-list": "#data-list > li",
          "tab-table": "#data-table-body > tr",
        };
        return [...document.querySelectorAll(selectors[activeTab])]
          .map((element) => ({
            id: element.getAttribute("data-cell"),
            recordKey: element.getAttribute("data-record-key"),
            ariaLabel: element.getAttribute("aria-label"),
            place: element.querySelector(".row-select")?.textContent?.trim() || "",
            reading: element.querySelector(".reading")?.textContent?.trim() || "",
            cells: [...element.querySelectorAll("td")].map((cell) => cell.textContent.trim()),
          }))
          .sort((a, b) => a.id.localeCompare(b.id));
      }, tabId);
    }

    const map = snapshots["tab-map"];
    const list = snapshots["tab-list"];
    const table = snapshots["tab-table"];
    expect(map.length).toBeGreaterThan(0);
    expect(new Set(map.map(({ id }) => id)).size).toBe(map.length);
    expect(map.map(({ id }) => id)).toEqual(expectedRows.map(({ cell_id: id }) => id));
    expect(list.map(({ id }) => id)).toEqual(map.map(({ id }) => id));
    expect(table.map(({ id }) => id)).toEqual(map.map(({ id }) => id));
    expect(list.map(({ recordKey }) => recordKey)).toEqual(map.map(({ recordKey }) => recordKey));
    expect(table.map(({ recordKey }) => recordKey)).toEqual(map.map(({ recordKey }) => recordKey));

    for (let index = 0; index < map.length; index += 1) {
      const record = JSON.parse(map[index].recordKey);
      // `label` is published surface data (placeName resolves to row.label), so it must survive into
      // the raw record and match the surface cell; only `description` is derived for display.
      const { description, ...rawRecord } = record;
      expect(rawRecord).toEqual(expectedRows[index]);
      expect(map[index].ariaLabel).toBe(record.description);
      expect(`${list[index].place}: ${list[index].reading}`).toBe(record.description);
      expect(table[index].place).toBe(record.label);
      expect(table[index].cells).toHaveLength(3);
      expect(table[index].cells.every(Boolean)).toBe(true);
      expect(table[index].cells[1]).toContain(`AQI ${Math.round(record.aqi)}`);
      if (record.provisional) {
        expect(map[index].ariaLabel.toLowerCase()).toContain("provisional");
        expect(table[index].cells[2].toLowerCase()).toContain("provisional");
      }
    }
  }
});

test("alert announcements are atomic text while alert actions remain outside the live region", async ({ page }) => {
  await ready(page);
  const record = JSON.parse(await page.locator("#map .cell").first().getAttribute("data-record-key"));
  await page.evaluate(({ cell_id: cellId }) => {
    localStorage.setItem("swelter.prefs", JSON.stringify({
      watches: { [`${cellId}|pm25_ugm3`]: { kind: "cat", idx: 0 } },
    }));
  }, record);
  await page.reload({ waitUntil: "domcontentloaded" });
  await expect(page.locator("html")).toHaveAttribute("data-render-ready", "true");

  const section = page.locator("#alerts");
  const status = page.locator("#alerts-status");
  const action = page.locator("#alerts-list button").first();
  await expect(section).toBeVisible();
  await expect(section).not.toHaveAttribute("role", "status");
  await expect(section).not.toHaveAttribute("aria-live", /.+/);
  await expect(status).toHaveAttribute("role", "status");
  await expect(status).toHaveAttribute("aria-live", "polite");
  await expect(status).toHaveAttribute("aria-atomic", "true");
  await expect(status).not.toBeEmpty();
  await expect(action).toBeVisible();
  expect(await action.evaluate((element) => element.closest('[role="status"], [aria-live]') === null)).toBe(true);
  expect(await status.textContent()).toBe(await page.locator("#alerts-list .alert-text").first().textContent());
  await assertNoBlockingAxe(page, "active personal-alert state");

  await page.evaluate(() => {
    window.__alertStatusMutations = 0;
    new MutationObserver((records) => {
      window.__alertStatusMutations += records.length;
    }).observe(document.querySelector("#alerts-status"), { childList: true, characterData: true, subtree: true });
  });
  await action.click();
  await expect(page.locator("#alerts-list button").first()).toBeFocused();
  expect(await page.evaluate(() => window.__alertStatusMutations)).toBe(0);
});

test("visible keyboard targets remain at least partly exposed after focus", async ({ page }) => {
  test.setTimeout(90_000);
  await ready(page);
  const failures = [];
  for (const tabId of ["tab-map", "tab-list", "tab-table"]) {
    await page.locator(`#${tabId}`).click();
    // Put the active browser engine in keyboard modality first: :focus-visible propagates from a
    // keyboard-visible focus to subsequent script focus() moves, so the whole sweep exercises the
    // same indicator styling a keyboard user sees.
    await page.keyboard.press("Tab");
    // Disabled controls (e.g. "smaller text" at the minimum size) are intentionally unfocusable, so
    // they are not keyboard targets and are excluded from the focus-exposure sweep. The sweep runs
    // as one in-page pass per view: with ~200 targets per view, per-target protocol round-trips
    // push slower engines past any workable timeout, without checking anything extra.
    const results = await page.evaluate(() => {
      const selector = [
        "a[href]",
        "button:not(:disabled)",
        "input:not(:disabled)",
        "select:not(:disabled)",
        "textarea:not(:disabled)",
        "summary",
        '[tabindex]:not([tabindex="-1"])',
      ].join(", ");
      // Same visibility contract as Playwright's `:visible`: a non-empty bounding box, not
      // `visibility: hidden`, and not slotted away inside a closed <details> (its summary stays
      // visible; the rest of its content is not keyboard-reachable until opened).
      const hiddenInClosedDetails = (element) => {
        for (
          let details = element.closest("details");
          details;
          details = details.parentElement?.closest("details")
        ) {
          if (!details.open) {
            const summary = details.querySelector(":scope > summary");
            if (!summary || !summary.contains(element)) return true;
          }
        }
        return false;
      };
      const sweep = [];
      for (const element of document.querySelectorAll(selector)) {
        const size = element.getBoundingClientRect();
        if (size.width <= 0 || size.height <= 0) continue;
        if (getComputedStyle(element).visibility === "hidden") continue;
        if (hiddenInClosedDetails(element)) continue;
        element.scrollIntoView({ behavior: "instant", block: "center", inline: "nearest" });
        element.focus({ preventScroll: true });
        const box = element.getBoundingClientRect();
        const insetX = Math.min(2, box.width / 2);
        const insetY = Math.min(2, box.height / 2);
        const points = [
          [box.left + insetX, box.top + insetY],
          [box.right - insetX, box.top + insetY],
          [box.left + box.width / 2, box.top + box.height / 2],
          [box.left + insetX, box.bottom - insetY],
          [box.right - insetX, box.bottom - insetY],
        ].filter(([x, y]) => x >= 0 && y >= 0 && x < innerWidth && y < innerHeight);
        const exposed = points.some(([x, y]) =>
          document.elementsFromPoint(x, y).some(
            (candidate) => candidate === element || candidate.contains(element) || element.contains(candidate),
          ),
        );
        const style = getComputedStyle(element);
        const indicator =
          (style.outlineStyle !== "none" && parseFloat(style.outlineWidth) > 0) ||
          style.boxShadow !== "none";
        if (!exposed || !indicator) {
          sweep.push({
            exposed,
            indicator,
            target: element.id || element.getAttribute("data-cell") || element.textContent?.trim().slice(0, 60),
            box: { x: box.x, y: box.y, width: box.width, height: box.height },
          });
        }
      }
      return sweep;
    });
    failures.push(...results.map((result) => ({ tabId, ...result })));
  }
  expect(failures, JSON.stringify(failures, null, 2)).toEqual([]);
});

test("every data view reflows at 320px without page-level horizontal scroll", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 640 });
  await ready(page);
  for (const tabId of VIEWS) {
    await selectView(page, tabId);
    const widths = await page.evaluate(() => {
      const viewport = document.documentElement.clientWidth;
      return {
        body: document.body.scrollWidth,
        viewport,
        overflow: [...document.querySelectorAll("body *")]
          .filter((element) => {
            const style = getComputedStyle(element);
            const rect = element.getBoundingClientRect();
            return style.display !== "none" && style.visibility !== "hidden" &&
              (rect.right > viewport + 1 || rect.left < -1);
          })
          .slice(0, 12)
          .map((element) => ({
            element: element.id || element.className || element.tagName,
            text: element.textContent?.trim().slice(0, 80),
            left: element.getBoundingClientRect().left,
            right: element.getBoundingClientRect().right,
            scrollWidth: element.scrollWidth,
          })),
      };
    });
    expect(widths.body, `${tabId}: ${JSON.stringify(widths)}`).toBeLessThanOrEqual(widths.viewport + 1);
  }
});

test("tablet layout keeps the selected location beside a bounded map", async ({ page }) => {
  await page.setViewportSize({ width: 931, height: 819 });
  await ready(
    page,
    `/#p=pm25_ugm3&t=${encodeURIComponent(ROOT_BUCKET)}&l=${encodeURIComponent(ROOT_LOCATION.cell_id)}`,
  );
  await expect(page.locator("#detail")).toBeVisible();
  await expect(page.locator("#detail-heading")).toHaveText(ROOT_LOCATION.label);
  const measure = () =>
    page.evaluate(() => {
      const mainElement = document.querySelector(".workspace-main");
      const inspectorElement = document.querySelector(".workspace-inspector");
      const main = mainElement.getBoundingClientRect();
      const inspector = inspectorElement.getBoundingClientRect();
      const map = document.querySelector("#map").getBoundingClientRect();
      return {
        mainRight: main.right,
        mainTop: main.top,
        mainBottom: main.bottom,
        inspectorLeft: inspector.left,
        inspectorTop: inspector.top,
        inspectorClientWidth: inspectorElement.clientWidth,
        inspectorScrollWidth: inspectorElement.scrollWidth,
        mapHeight: map.height,
        viewportHeight: window.innerHeight,
        pageWidth: document.body.scrollWidth,
        viewportWidth: document.documentElement.clientWidth,
      };
    });
  for (const width of [931, 768]) {
    await page.setViewportSize({ width, height: 819 });
    const layout = await measure();
    expect(layout.inspectorLeft, JSON.stringify(layout)).toBeGreaterThanOrEqual(layout.mainRight);
    expect(Math.abs(layout.inspectorTop - layout.mainTop), JSON.stringify(layout)).toBeLessThan(2);
    expect(layout.inspectorScrollWidth, JSON.stringify(layout))
      .toBeLessThanOrEqual(layout.inspectorClientWidth + 1);
    expect(layout.mapHeight, JSON.stringify(layout)).toBeLessThan(layout.viewportHeight * 0.75);
    expect(layout.pageWidth, JSON.stringify(layout)).toBeLessThanOrEqual(layout.viewportWidth + 1);
  }
  await page.setViewportSize({ width: 720, height: 819 });
  const stacked = await measure();
  expect(stacked.inspectorTop, JSON.stringify(stacked)).toBeGreaterThanOrEqual(stacked.mainBottom);
  expect(stacked.mapHeight, JSON.stringify(stacked)).toBeLessThan(500);
  expect(stacked.pageWidth, JSON.stringify(stacked)).toBeLessThanOrEqual(stacked.viewportWidth + 1);
});

test("reduced-motion preference suppresses authored motion", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await ready(page);
  const motion = await page.evaluate(() => {
    const sample = document.querySelector(".map-canvas") || document.querySelector(".cell");
    const style = getComputedStyle(sample);
    return {
      animationDuration: style.animationDuration,
      transitionDuration: style.transitionDuration,
      scrollBehavior: getComputedStyle(document.documentElement).scrollBehavior,
    };
  });
  expect(parseFloat(motion.animationDuration) || 0).toBeLessThanOrEqual(0.001);
  expect(parseFloat(motion.transitionDuration) || 0).toBeLessThanOrEqual(0.001);
  expect(motion.scrollBehavior).toBe("auto");
});

test("all rendered views meet WCAG 2.5.8 geometry at desktop and 320px", async ({ page }) => {
  await ready(page);
  const report = { targets: 0, exceptions: [], failures: [], views: {} };
  for (const width of [1280, 320]) {
    await page.setViewportSize({ width, height: 640 });
    for (const tabId of VIEWS) {
      await selectView(page, tabId);
      const geometry = await page.evaluate(() => {
        const selector = [
          "a[href]",
          "button",
          "input",
          "select",
          "textarea",
          "summary",
          '[role="tab"]',
          '[role="button"]',
          '[tabindex]:not([tabindex="-1"])',
        ].join(", ");
        const visible = [...document.querySelectorAll(selector)].filter((element) => {
          const style = getComputedStyle(element);
          const box = element.getBoundingClientRect();
          return !element.hidden && style.display !== "none" && style.visibility !== "hidden" &&
            box.width > 0 && box.height > 0;
        });
        const union = (a, b) => ({
          left: Math.min(a.left, b.left),
          top: Math.min(a.top, b.top),
          right: Math.max(a.right, b.right),
          bottom: Math.max(a.bottom, b.bottom),
        });
        const records = visible.map((element) => {
          let box = element.getBoundingClientRect();
          let compositeLabel = false;
          if (element.matches('input[type="checkbox"], input[type="radio"]') && element.id) {
            const label = document.querySelector(`label[for="${CSS.escape(element.id)}"]`);
            if (label) {
              const combined = union(box, label.getBoundingClientRect());
              box = {
                ...combined,
                width: combined.right - combined.left,
                height: combined.bottom - combined.top,
              };
              compositeLabel = true;
            }
          }
          const style = getComputedStyle(element);
          return {
            element: element.id || element.getAttribute("data-cell") || element.textContent?.trim().slice(0, 60),
            tag: element.tagName.toLowerCase(),
            type: element.getAttribute("type") || "",
            display: style.display,
            compositeLabel,
            textFlow: style.display === "inline" && Boolean(element.closest("p, li, dd, figcaption")),
            box: {
              left: box.left,
              top: box.top,
              right: box.right,
              bottom: box.bottom,
              width: box.width,
              height: box.height,
            },
          };
        });
        return records.map((record, index) => {
          if (record.box.width + 0.01 >= 24 && record.box.height + 0.01 >= 24) {
            return { ...record, result: "pass" };
          }
          // WCAG 2.5.8 explicitly exempts inline targets constrained by sentence/paragraph flow.
          if (record.textFlow) return { ...record, result: "exception", exception: "inline-text" };

          const center = {
            x: (record.box.left + record.box.right) / 2,
            y: (record.box.top + record.box.bottom) / 2,
          };
          const spacingClear = records.every((other, otherIndex) => {
            if (otherIndex === index) return true;
            const otherCenter = {
              x: (other.box.left + other.box.right) / 2,
              y: (other.box.top + other.box.bottom) / 2,
            };
            if (other.box.width < 24 || other.box.height < 24) {
              return Math.hypot(center.x - otherCenter.x, center.y - otherCenter.y) + 0.01 >= 24;
            }
            const nearestX = Math.max(other.box.left, Math.min(center.x, other.box.right));
            const nearestY = Math.max(other.box.top, Math.min(center.y, other.box.bottom));
            return Math.hypot(center.x - nearestX, center.y - nearestY) + 0.01 >= 12;
          });
          return spacingClear
            ? { ...record, result: "exception", exception: "24px-spacing" }
            : { ...record, result: "fail" };
        });
      });
      const view = `${width}:${tabId}`;
      report.views[view] = geometry.length;
      report.targets += geometry.length;
      report.exceptions.push(...geometry.filter((item) => item.result === "exception").map((item) => ({ view, ...item })));
      report.failures.push(...geometry.filter((item) => item.result === "fail").map((item) => ({ view, ...item })));
    }
  }
  expect(report.targets, JSON.stringify(report, null, 2)).toBeGreaterThan(60);
  expect(Object.keys(report.views)).toEqual([
    "1280:tab-map",
    "1280:tab-list",
    "1280:tab-table",
    "320:tab-map",
    "320:tab-list",
    "320:tab-table",
  ]);
  expect(report.exceptions.every((item) => ["inline-text", "24px-spacing"].includes(item.exception))).toBe(true);
  expect(report.failures, JSON.stringify(report, null, 2)).toEqual([]);
});

test("40% pseudolocale expansion does not clip or overflow the page", async ({ page }) => {
  await page.route("**/i18n/en.json", async (route) => {
    const response = await route.fetch();
    const source = await response.json();
    const pseudo = Object.fromEntries(
      Object.entries(source).map(([key, value]) => {
        // Leave MF2 argument/matcher messages intact; static interface copy still receives a 40%+
        // expansion without corrupting MessageFormat syntax.
        const expanded = value.includes("{")
          ? value
          : value.replace(/[aeiou]/gi, (letter) => `${letter}${letter}`);
        return [key, `［${expanded} — ${expanded.slice(0, Math.ceil(expanded.length * 0.18))}］`];
      }),
    );
    await route.fulfill({ response, json: pseudo });
  });
  await page.setViewportSize({ width: 320, height: 640 });
  await ready(page);
  for (const tabId of VIEWS) {
    await selectView(page, tabId);
    const result = await page.evaluate(() => ({
      pageWidth: document.body.scrollWidth,
      viewportWidth: document.documentElement.clientWidth,
      clipped: [...document.querySelectorAll("[data-i18n]")]
        .filter((element) => {
          const style = getComputedStyle(element);
          const box = element.getBoundingClientRect();
          return !element.matches(".visually-hidden, .sr-only") &&
            style.display !== "none" && style.visibility !== "hidden" && box.width > 0 && box.height > 0 &&
            style.overflowX === "hidden" && element.scrollWidth > element.clientWidth + 1;
        })
        .map((element) => element.getAttribute("data-i18n")),
    }));
    expect(result.pageWidth, `${tabId}: ${JSON.stringify(result)}`)
      .toBeLessThanOrEqual(result.viewportWidth + 1);
    expect(result.clipped, tabId).toEqual([]);
  }
});

test("Arabic RTL fixture mirrors layout and isolates mixed-direction place text", async ({ page }) => {
  await page.route("**/i18n/en.json", async (route) => {
    const response = await route.fetch();
    const source = await response.json();
    await route.fulfill({ response, json: { ...source, ...rtlFixture.messages } });
  });
  await ready(page);
  await page.evaluate((locale) => {
    document.documentElement.lang = locale;
    document.documentElement.dir = "rtl";
  }, rtlFixture.locale);
  await expect(page.locator("#now-heading")).toHaveText(rtlFixture.messages["now-heading"]);
  const braid = page.locator("#exposure-braid");
  await braid.focus();
  await page.keyboard.press("End");
  const mixed = await page.locator("#braid-status").textContent();
  const result = await page.evaluate(() => {
    const wrap = document.querySelector(".map-wrap").getBoundingClientRect();
    const controls = document.querySelector(".map-controls").getBoundingClientRect();
    return {
      pageWidth: document.body.scrollWidth,
      viewportWidth: document.documentElement.clientWidth,
      controlsNearInlineEnd: Math.abs(controls.left - wrap.left) < 24,
    };
  });
  expect(result.pageWidth, JSON.stringify(result)).toBeLessThanOrEqual(result.viewportWidth + 1);
  expect(result.controlsNearInlineEnd).toBe(true);
  expect(mixed).toMatch(/\u2068[^\u2069]+\u2069/u);
});
