"use strict";

const { spawn } = require("node:child_process");
const path = require("node:path");
const { chromium } = require("playwright");

const WEB = path.resolve(__dirname, "..");
const cli = path.join(WEB, "node_modules", ".bin", "lhci");

const audit = spawn(cli, ["autorun", "--config", "lighthouserc.cjs"], {
  cwd: WEB,
  env: { ...process.env, CHROME_PATH: chromium.executablePath() },
  stdio: "inherit",
});

audit.on("exit", (code) => {
  process.exitCode = code ?? 1;
});

audit.on("error", (error) => {
  console.error(error);
  process.exitCode = 1;
});
