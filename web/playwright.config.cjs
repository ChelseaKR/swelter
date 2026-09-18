"use strict";

const { defineConfig, devices } = require("@playwright/test");

module.exports = defineConfig({
  testDir: "./tests/browser",
  testMatch: "**/*.spec.js",
  timeout: 45_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  // A test that failed and then passed on the retry above is reported `flaky`,
  // and Playwright exits 0 on flaky unless told otherwise — so without this the
  // retry would not absorb an intermittent failure, it would hide one: a race
  // or an unawaited promise in a browser spec would read as a green
  // `a11y-advisory` check and leave nothing behind but a log line. The retry
  // still runs and `trace: "retain-on-failure"` still keeps the failed
  // attempt's trace; only the verdict changes. Locally there is no retry, so a
  // flake is already a failure there. See #281.
  failOnFlakyTests: Boolean(process.env.CI),
  reporter: process.env.CI
    ? [
        ["line"],
        ["json", { outputFile: "test-results/playwright/results.json" }],
        ["junit", { outputFile: "test-results/playwright/results.xml" }],
        ["html", { open: "never", outputFolder: "test-results/html" }],
      ]
    : "line",
  use: {
    ...devices["Desktop Chrome"],
    baseURL: "http://127.0.0.1:4173",
    colorScheme: "light",
    locale: "en-US",
    serviceWorkers: "block",
    trace: "retain-on-failure",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
    { name: "firefox", use: { ...devices["Desktop Firefox"] } },
    { name: "webkit", use: { ...devices["Desktop Safari"] } },
  ],
  webServer: {
    command: "node tests/static-server.cjs",
    url: "http://127.0.0.1:4173/",
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
  outputDir: "test-results/playwright",
});
