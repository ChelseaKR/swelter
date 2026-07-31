#!/usr/bin/env node

/** Render the source SVG for swelter's deterministic social preview. */

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const BASEMAP = path.join(ROOT, "web", "basemap.geojson");
const OUTPUT = path.join(ROOT, "web", "social-card.svg");

const WIDTH = 1280;
const HEIGHT = 640;
const MAP_BOX = { left: 706, top: 48, width: 502, height: 544 };
const COLORS = {
  background: "#f4f6f7",
  foreground: "#182126",
  muted: "#5b6870",
  border: "#cbd3d8",
  accent: "#176785",
  land: "#e4ebe7",
  mapLine: "#73847c",
};

function coordinateRings(geometry) {
  if (geometry.type === "Polygon") return geometry.coordinates;
  if (geometry.type === "MultiPolygon") return geometry.coordinates.flat();
  throw new Error(`unsupported basemap geometry: ${geometry.type}`);
}

function allCoordinates(featureCollection) {
  return featureCollection.features.flatMap((feature) =>
    coordinateRings(feature.geometry).flat(),
  );
}

function projection(featureCollection) {
  const coordinates = allCoordinates(featureCollection);
  const lons = coordinates.map(([lon]) => lon);
  const lats = coordinates.map(([, lat]) => lat);
  const minLon = Math.min(...lons);
  const maxLon = Math.max(...lons);
  const minLat = Math.min(...lats);
  const maxLat = Math.max(...lats);
  const cosLat = Math.cos((((minLat + maxLat) / 2) * Math.PI) / 180);
  const projectedWidth = (maxLon - minLon) * cosLat;
  const projectedHeight = maxLat - minLat;
  const scale = Math.min(MAP_BOX.width / projectedWidth, MAP_BOX.height / projectedHeight);
  const drawnWidth = projectedWidth * scale;
  const drawnHeight = projectedHeight * scale;
  const offsetX = MAP_BOX.left + (MAP_BOX.width - drawnWidth) / 2;
  const offsetY = MAP_BOX.top + (MAP_BOX.height - drawnHeight) / 2;

  return ([lon, lat]) => [
    offsetX + (lon - minLon) * cosLat * scale,
    offsetY + (maxLat - lat) * scale,
  ];
}

function ringPath(ring, project) {
  return ring
    .map((point, index) => {
      const [x, y] = project(point);
      return `${index === 0 ? "M" : "L"}${x.toFixed(2)} ${y.toFixed(2)}`;
    })
    .join(" ") + " Z";
}

function featurePath(feature, project) {
  return coordinateRings(feature.geometry)
    .map((ring) => ringPath(ring, project))
    .join(" ");
}

const basemap = JSON.parse(fs.readFileSync(BASEMAP, "utf8"));
const project = projection(basemap);
const countyPaths = basemap.features
  .map(
    (feature) =>
      `<path d="${featurePath(feature, project)}" fill="${COLORS.land}" ` +
      `stroke="${COLORS.mapLine}" stroke-width="1.15" vector-effect="non-scaling-stroke" />`,
  )
  .join("\n      ");
const [cellX, cellY] = project([-121.4944, 38.5816]);

const svg = `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="${WIDTH}" height="${HEIGHT}" viewBox="0 0 ${WIDTH} ${HEIGHT}" role="img" aria-labelledby="title description">
  <title id="title">swelter social preview</title>
  <desc id="description">The swelter name beside a quiet California county map with one measured grid cell.</desc>
  <rect width="${WIDTH}" height="${HEIGHT}" fill="${COLORS.background}" />
  <line x1="640" y1="48" x2="640" y2="592" stroke="${COLORS.border}" stroke-width="1" />

  <g aria-hidden="true" transform="translate(72 68) scale(0.125)">
    <rect width="512" height="512" rx="96" fill="#7b2d26" />
    <circle cx="256" cy="232" r="92" fill="#f2c14e" />
    <g stroke="#f2c14e" stroke-width="22" stroke-linecap="round">
      <line x1="256" y1="60" x2="256" y2="104" />
      <line x1="256" y1="360" x2="256" y2="404" />
      <line x1="84" y1="232" x2="128" y2="232" />
      <line x1="384" y1="232" x2="428" y2="232" />
      <line x1="134" y1="110" x2="165" y2="141" />
      <line x1="347" y1="323" x2="378" y2="354" />
      <line x1="378" y1="110" x2="347" y2="141" />
      <line x1="165" y1="323" x2="134" y2="354" />
    </g>
    <path d="M150 432 q40 -44 80 0 q40 44 80 0 q40 -44 80 0" fill="none" stroke="#fbf7f2" stroke-width="20" stroke-linecap="round" />
  </g>

  <text x="72" y="224" fill="${COLORS.foreground}" font-family="system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif" font-size="82" font-weight="650" letter-spacing="-3">swelter</text>
  <text x="72" y="282" fill="${COLORS.foreground}" font-family="system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif" font-size="29" font-weight="500">Community heat and air sensing</text>
  <line x1="72" y1="342" x2="548" y2="342" stroke="${COLORS.border}" stroke-width="1" />
  <text x="72" y="390" fill="${COLORS.muted}" font-family="system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif" font-size="22">Source, calibration, and limits stay</text>
  <text x="72" y="422" fill="${COLORS.muted}" font-family="system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif" font-size="22">with every reading.</text>
  <text x="72" y="558" fill="${COLORS.muted}" font-family="ui-monospace, 'SFMono-Regular', Consolas, monospace" font-size="16">github.com/ChelseaKR/swelter</text>

  <g aria-hidden="true">
      ${countyPaths}
    <rect x="${(cellX - 8).toFixed(2)}" y="${(cellY - 8).toFixed(2)}" width="16" height="16" fill="${COLORS.accent}" stroke="${COLORS.background}" stroke-width="3" />
  </g>
</svg>
`;

fs.writeFileSync(OUTPUT, svg, "utf8");
console.log(`wrote ${path.relative(ROOT, OUTPUT)}`);
