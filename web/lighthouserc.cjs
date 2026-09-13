"use strict";

module.exports = {
  ci: {
    collect: {
      startServerCommand: "node tests/static-server.cjs",
      startServerReadyPattern: "swelter test server:",
      startServerReadyTimeout: 30_000,
      url: ["http://127.0.0.1:4173/", "http://127.0.0.1:4173/sensors/"],
      // Three runs per route, and the assertion reads their median (see `assert` below). One run on
      // a shared GitHub-hosted runner decided merges on scheduler noise: over 137 retained
      // `a11y-advisory` runs, total-blocking-time on `/` was p50 54 ms / max 202 ms and on
      // `/sensors/` p50 52 ms / max 257.5 ms, so a 200 ms budget failed two runs whose diffs could
      // not have moved it (#266). A real regression moves all three runs; runner noise rarely
      // moves two of them.
      numberOfRuns: 3,
      settings: {
        chromeFlags: "--headless --no-sandbox --disable-dev-shm-usage",
        onlyCategories: ["accessibility", "performance", "best-practices"],
      },
    },
    assert: {
      // Pinned, never inherited. LHCI 0.15.1 defaults `aggregationMethod` to "optimistic", which for
      // a `max*` assertion reads the BEST of the runs: `numberOfRuns: 3` under that default would
      // make every budget below strictly easier to pass while the file still says 200 ms. Median
      // keeps each budget exactly as strict as it reads. `web/tests/lighthouserc.unit.test.js`
      // fails if this key is removed or any assertion overrides it.
      aggregationMethod: "median",
      assertions: {
        "categories:accessibility": ["error", { minScore: 0.9 }],
        "categories:performance": ["error", { minScore: 0.9 }],
        "categories:best-practices": ["error", { minScore: 0.9 }],
        "largest-contentful-paint": ["error", { maxNumericValue: 2500 }],
        "cumulative-layout-shift": ["error", { maxNumericValue: 0.1 }],
        "total-blocking-time": ["error", { maxNumericValue: 200 }],
        "total-byte-weight": ["error", { maxNumericValue: 2_500_000 }],
        "dom-size": ["error", { maxNumericValue: 1_500 }],
        "uses-long-cache-ttl": "off",
        "service-worker": "off",
        "installable-manifest": "off",
      },
    },
    upload: { target: "filesystem", outputDir: ".lighthouseci" },
  },
};
