"use strict";

const { chromium } = require("playwright");

module.exports = {
  defaults: {
    reporters: [
      "cli",
      ["json", { fileName: "test-results/pa11y/results.json" }],
    ],
    standard: "WCAG2AA",
    runners: ["axe"],
    level: "error",
    // Axe returns patterned/transformed visualization text as `incomplete` even when its computed
    // foreground/base-background pair passes. Pa11y otherwise promotes those manual-review items
    // to errors. Confirmed violations remain errors; the paired Playwright gate allowlists only
    // those exact review surfaces and independently calculates their contrast ratio.
    levelCapWhenNeedsReview: "warning",
    timeout: 45_000,
    wait: 1_500,
    chromeLaunchConfig: {
      executablePath: chromium.executablePath(),
      args: ["--no-sandbox", "--disable-dev-shm-usage"],
    },
  },
  urls: ["http://127.0.0.1:4173/", "http://127.0.0.1:4173/sensors/"],
};
