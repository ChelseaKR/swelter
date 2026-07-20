"use strict";

const fs = require("node:fs");
const path = require("node:path");

const WEB = path.join(__dirname, "..");
const EXPECTED_VERSION = "4.0.0-11";
const entry = fs.realpathSync(require.resolve("messageformat"));
const source = path.dirname(entry);
const packageRoot = path.dirname(source);
const packageJson = JSON.parse(fs.readFileSync(path.join(packageRoot, "package.json"), "utf8"));

if (packageJson.name !== "messageformat" || packageJson.version !== EXPECTED_VERSION) {
  throw new Error(
    `messageformat ${packageJson.version ?? "unknown"} does not match ${EXPECTED_VERSION}`,
  );
}
if (path.basename(entry) !== "index.js" || path.basename(source) !== "lib") {
  throw new Error(`unexpected messageformat package layout: ${entry}`);
}

const destination = path.join(WEB, "vendor", "messageformat");
fs.rmSync(destination, { recursive: true, force: true });
fs.mkdirSync(path.dirname(destination), { recursive: true });
fs.cpSync(source, destination, { recursive: true, dereference: true });

function javascriptFiles(directory, prefix = "") {
  const files = [];
  for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
    const relative = path.join(prefix, entry.name);
    if (entry.isDirectory()) files.push(...javascriptFiles(path.join(directory, entry.name), relative));
    else if (entry.isFile() && entry.name.endsWith(".js")) {
      files.push(`vendor/messageformat/${relative.split(path.sep).join("/")}`);
    }
  }
  return files.sort();
}

fs.writeFileSync(
  path.join(destination, "asset-manifest.json"),
  `${JSON.stringify(javascriptFiles(destination), null, 2)}\n`,
  "utf8",
);

console.log(
  `MessageFormat 2 runtime ${packageJson.version}: ${path.relative(WEB, destination)}`,
);
