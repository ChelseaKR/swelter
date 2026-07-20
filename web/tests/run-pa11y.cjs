"use strict";

const { spawn } = require("node:child_process");
const path = require("node:path");

const WEB = path.resolve(__dirname, "..");
const server = spawn(process.execPath, ["tests/static-server.cjs"], { cwd: WEB, stdio: "inherit" });

async function waitForServer() {
  for (let attempt = 0; attempt < 100; attempt += 1) {
    try {
      const response = await fetch("http://127.0.0.1:4173/");
      if (response.ok) return;
    } catch {
      // The child is still starting.
    }
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw new Error("static test server did not start");
}

async function main() {
  try {
    await waitForServer();
    const cli = path.join(WEB, "node_modules", ".bin", "pa11y-ci");
    const audit = spawn(cli, ["--config", ".pa11yci.cjs"], { cwd: WEB, stdio: "inherit" });
    const code = await new Promise((resolve) => audit.on("exit", resolve));
    process.exitCode = code ?? 1;
  } finally {
    server.kill("SIGTERM");
  }
}

main().catch((error) => {
  console.error(error);
  server.kill("SIGTERM");
  process.exitCode = 1;
});
