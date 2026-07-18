"use strict";

const { test, expect } = require("@playwright/test");
const AxeBuilder = require("@axe-core/playwright").default;
const rtlFixture = require("../fixtures/rtl-ar.json");

const ROUTES = ["/", "/sensors/"];
const VIEWS = ["tab-map", "tab-list", "tab-table"];

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
    "tab-map": "#map .cell",
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
      const html = node.html || "";
      const knownPatternedText =
        issue.id === "color-contrast" &&
        (html.includes("cell-reading") ||
          html.includes("braid-axis-label") ||
          html.includes("braid-time-label"));
      const knownTargetEngineError =
        issue.id === "target-size" &&
        selector.startsWith('.provisional.cell[data-cell="') &&
        node.none.some(
          (check) =>
            check.id === "error-occurred" &&
            check.data?.ruleId === "target-size" &&
            check.data?.message?.includes("Reduce of empty array"),
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
          await expect(page.locator("#now-heading")).toHaveText("Ahora");
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
      geography: "Demonstration grid",
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
    const pairs = await page.evaluate(() => {
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
  await page.keyboard.type("Laurel");
  await expect(page.locator("#status")).toContainText("1");
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

  const initial = await canvas.evaluate((element) => element.style.transform);
  await page.keyboard.press("+");
  await expect.poll(() => canvas.evaluate((element) => element.style.transform)).not.toBe(initial);
  const zoomed = await canvas.evaluate((element) => element.style.transform);
  expect(zoomed).toContain("scale(1.4");

  await page.keyboard.press("ArrowRight");
  await expect.poll(() => canvas.evaluate((element) => element.style.transform)).not.toBe(zoomed);
  await page.keyboard.press("0");
  await expect.poll(() => canvas.evaluate((element) => element.style.transform))
    .toContain("translate(0px, 0px) scale(1)");

  const marker = page.locator("#map .cell").first();
  const cellId = await marker.getAttribute("data-cell");
  await marker.focus();
  await page.keyboard.press("Enter");
  await expect(marker).toHaveAttribute("aria-pressed", "true");
  await expect(page.locator("#detail")).toBeVisible();

  await page.locator("#tab-list").click();
  await expect(page.locator(`#data-list [data-cell="${cellId}"]`)).toHaveAttribute("aria-pressed", "true");
  await page.locator("#tab-table").click();
  await expect(page.locator(`#data-table-body [data-cell="${cellId}"]`)).toHaveAttribute("aria-pressed", "true");
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
      const { label, description, ...rawRecord } = record;
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
    const targets = page.locator(
      'a[href]:visible, button:visible, input:visible, select:visible, textarea:visible, summary:visible, [tabindex]:not([tabindex="-1"]):visible',
    );
    for (let index = 0; index < await targets.count(); index += 1) {
      const target = targets.nth(index);
      await target.scrollIntoViewIfNeeded();
      // Put the active browser engine in keyboard modality so traversal exercises :focus-visible.
      await page.keyboard.press("Tab");
      await target.focus();
      const result = await target.evaluate((element) => {
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
        return {
          exposed,
          indicator,
          target: element.id || element.getAttribute("data-cell") || element.textContent?.trim().slice(0, 60),
          box: { x: box.x, y: box.y, width: box.width, height: box.height },
        };
      });
      if (!result.exposed || !result.indicator) failures.push({ tabId, ...result });
    }
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
