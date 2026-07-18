"use strict";

module.exports = {
  ci: {
    collect: {
      startServerCommand: "node tests/static-server.cjs",
      startServerReadyPattern: "swelter test server:",
      startServerReadyTimeout: 30_000,
      url: ["http://127.0.0.1:4173/", "http://127.0.0.1:4173/sensors/"],
      numberOfRuns: 1,
      settings: {
        chromeFlags: "--headless --no-sandbox --disable-dev-shm-usage",
        onlyCategories: ["accessibility", "performance", "best-practices"],
      },
    },
    assert: {
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
