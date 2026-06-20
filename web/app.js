// swelter dashboard logic — framework-free, no dependencies.
//
// One data source (the aggregated surface) drives three equal views: a plain List (default), a
// sortable Table, and a schematic Map. The map is never the only way in. Readings lead with the
// AQI + a named category for PM2.5; severity is announced in text; provisional (uncalibrated)
// locations are rendered neutrally and never wear a confirmed category. Locations are named, the time
// and category are localized, temperature can be shown in °F, and a sourced health-context line
// bridges the number to a decision without ever promising personal safety.

const PARAM_BASE_UNIT = {
  temp_c: "C",
  heat_index_c: "C",
  pm25_ugm3: "ug",
  pm10_ugm3: "ug",
  no2_ppb: "ppb",
};

// Parameter → its i18n label key, for the plain-language network brief.
const PARAM_I18N = {
  pm25_ugm3: "param-pm25",
  exposure: "param-exposure",
  temp_c: "param-temp",
  heat_index_c: "param-hi",
  pm10_ugm3: "param-pm10",
};

const AQI_CLASS = {
  Good: "aqi-good",
  Moderate: "aqi-moderate",
  "Unhealthy for Sensitive Groups": "aqi-usg",
  Unhealthy: "aqi-unhealthy",
  "Very Unhealthy": "aqi-veryunhealthy",
  Hazardous: "aqi-hazardous",
};

const CAT_SLUG = {
  Good: "good",
  Moderate: "moderate",
  "Unhealthy for Sensitive Groups": "usg",
  Unhealthy: "unhealthy",
  "Very Unhealthy": "vu",
  Hazardous: "haz",
};

// Combined heat-and-air exposure (ADR 0009): severity is carried by the level NAME in text, never
// by color alone, so exposure markers/tags stay visually neutral and rely on these labels.
const EXP_SLUG = {
  Minimal: "minimal",
  Low: "low",
  Elevated: "elevated",
  High: "high",
  Extreme: "extreme",
};

const HEAT_SLUG = {
  None: "none",
  Caution: "caution",
  "Extreme Caution": "xcaution",
  Danger: "danger",
  "Extreme Danger": "xdanger",
};

// Ordinal concern levels (mirror models.py) so the detail panel can pick the dominant hazard for
// combined exposure. Higher = more concerning for every surface parameter.
const HEAT_LEVEL = { None: 0, Caution: 1, "Extreme Caution": 2, Danger: 3, "Extreme Danger": 4 };
const AIR_LEVEL = {
  Good: 0,
  Moderate: 1,
  "Unhealthy for Sensitive Groups": 2,
  Unhealthy: 3,
  "Very Unhealthy": 4,
  Hazardous: 4,
};

// NWS heat-index tier from a Celsius value (mirrors models.heat_index_category thresholds), so a
// plain heat-index reading can show its tier and guidance without a round-trip to the server.
const HEAT_BANDS = [
  [51.1, "Extreme Danger"],
  [39.4, "Danger"],
  [32.2, "Extreme Caution"],
  [26.7, "Caution"],
];
function heatTier(c) {
  for (const [floor, name] of HEAT_BANDS) if (c >= floor) return name;
  return "None";
}

// Map shading scale (cool → hot) for temperature / heat-index markers, binned on the Celsius mean
// regardless of the °F/°C display. The marker's number carries the exact value; this only makes the
// heat island legible at a glance, and provisional cells never get a colour.
const HEAT_SCALE = [
  [36, "heat-5"],
  [32, "heat-4"],
  [28, "heat-3"],
  [24, "heat-2"],
];
function heatClass(c) {
  for (const [floor, cls] of HEAT_SCALE) if (c >= floor) return cls;
  return "heat-1";
}

// Severity order (best → worst) for the network "at a glance" breakdown and its worst pick.
const AQI_ORDER = [
  "Good",
  "Moderate",
  "Unhealthy for Sensitive Groups",
  "Unhealthy",
  "Very Unhealthy",
  "Hazardous",
];
const EXP_ORDER = ["Minimal", "Low", "Elevated", "High", "Extreme"];
// Heat-index tiers a resident can watch for (skips "None" — you don't set an alert for "no elevated
// heat"). The index into this array is what a heat-index watch stores, mirroring heatTier().
const HEAT_ORDER = ["Caution", "Extreme Caution", "Danger", "Extreme Danger"];
// Category measurements share the same logic: a level picked from an ordered list. Plain numbers
// (temperature, PM10) are watched by a numeric value instead.
const CATEGORY_ORDER = { pm25_ugm3: AQI_ORDER, exposure: EXP_ORDER, heat_index_c: HEAT_ORDER };

const state = {
  cells: [],
  buckets: [],
  cellIndex: new Map(),
  parameter: "pm25_ugm3",
  bucketIdx: 0,
  unit: "F",
  textStep: 0, // index into TEXT_STEPS; 0 = default size
  contrast: false, // high-contrast theme on/off
  sortKey: "value",
  sortDir: -1, // worst-first by default
  selected: null,
  compareCell: null, // a second location pinned for side-by-side comparison (equity view)
  search: "",
  strings: {},
  historyLoaded: false,
  health: null, // node-health summary from /api/health.json (or the baked sample), once loaded
  basemap: null, // optional geographic outline (e.g. California) drawn behind the markers
  mapView: { zoom: 1, x: 0, y: 0 }, // pan (px) + zoom of the map canvas; 1 = fit, no pan
  pendingFocus: null, // a cell to center on once the map becomes visible/measurable
  projSig: "", // signature of the last map projection; a change (no basemap) refits the view
};

// Personal alert thresholds: on-device only (localStorage, like the other prefs), no account, no
// server, no PII — a watch holds only the public cell id, the parameter, and a level. While the page
// is open, a watched location whose current-hour reading meets/exceeds its level surfaces in the
// Alerts banner; if the reader has granted browser-notification permission and turned notifications
// on, an under→over crossing fires one notification. `firing` tracks which watch keys are currently
// over, so a notification fires once per crossing and never spams already-over watches on load.
const firing = new Set();
let notifyOn = false; // has the reader asked for on-device notifications this session?

const MAX_ZOOM = 14;
const reduceMotionMQL = window.matchMedia("(prefers-reduced-motion: reduce)");
let mapW = 0; // cached #map pixel size — measured on show/resize, never read per frame
let mapH = 0;
let mapVisible = false; // is the Map tab currently shown?
let mapDirty = true; // does the (lazy) map need a rebuild before it is shown?
let lastK = 1; // last --k written; a pure pan must not rewrite it (would repaint every marker)
let mapDidDrag = false; // a pan/pinch moved past threshold → suppress the trailing marker click
let mapWasMultiTouch = false; // a 2-finger gesture happened → suppress a stray tap-select
let mapRafPending = false; // a transform write is already queued for the next frame
let mapRafAnimate = false;

const $ = (sel) => document.querySelector(sel);

// Remember a returning resident's choices — language, units, and the last location they viewed — so
// they land where they left off (and in their language; an equity win for non-English readers).
// All wrapped: storage can throw in private mode or when blocked, and preferences just won't persist.
const PREFS_KEY = "swelter.prefs";

function loadPrefs() {
  try {
    return JSON.parse(localStorage.getItem(PREFS_KEY) || "{}") || {};
  } catch {
    return {};
  }
}

function savePref(key, value) {
  try {
    const prefs = loadPrefs();
    prefs[key] = value;
    localStorage.setItem(PREFS_KEY, JSON.stringify(prefs));
  } catch {
    /* storage unavailable — non-fatal, preferences simply don't persist */
  }
}

// English text shipped in the HTML is the per-key fallback, captured before any swap.
const I18N_DEFAULTS = new Map(
  [...document.querySelectorAll("[data-i18n]")].map((el) => [
    el.getAttribute("data-i18n"),
    el.textContent,
  ]),
);

function t(key) {
  return state.strings[key] ?? I18N_DEFAULTS.get(key) ?? key;
}

async function loadStrings(lang) {
  try {
    const res = await fetch(`i18n/${lang}.json`);
    if (!res.ok) throw new Error("missing");
    state.strings = await res.json();
    document.documentElement.lang = lang; // only claim the language if its strings loaded
  } catch {
    state.strings = {};
  }
  for (const el of document.querySelectorAll("[data-i18n]")) {
    const key = el.getAttribute("data-i18n");
    el.textContent = state.strings[key] ?? I18N_DEFAULTS.get(key) ?? el.textContent;
  }
  for (const el of document.querySelectorAll("[data-i18n-attr]")) {
    const [attr, key] = el.getAttribute("data-i18n-attr").split(":");
    if (state.strings[key]) el.setAttribute(attr, state.strings[key]);
  }
}

async function fetchSurface(url) {
  try {
    const res = await fetch(url);
    if (!res.ok) return null;
    const doc = await res.json();
    return doc && doc.cells ? doc : null;
  } catch {
    return null;
  }
}

// Optional geographic basemap (e.g. California county outlines). If basemap.geojson sits next to
// the page, the map draws it behind the markers; if not (404/parse error), the map stays a plain
// schematic. Flattened to rings + a bbox once, so render stays cheap.
async function loadBasemap() {
  try {
    const res = await fetch("basemap.geojson");
    if (!res.ok) return;
    const gj = await res.json();
    const rings = [];
    let minLon = Infinity;
    let minLat = Infinity;
    let maxLon = -Infinity;
    let maxLat = -Infinity;
    const addRing = (ring) => {
      const r = [];
      for (const pt of ring) {
        const lon = +pt[0];
        const lat = +pt[1];
        if (!Number.isFinite(lon) || !Number.isFinite(lat)) continue;
        if (lon < minLon) minLon = lon;
        if (lon > maxLon) maxLon = lon;
        if (lat < minLat) minLat = lat;
        if (lat > maxLat) maxLat = lat;
        r.push([lon, lat]);
      }
      if (r.length > 2) rings.push(r);
    };
    for (const f of gj.features || []) {
      const g = f.geometry || {};
      if (g.type === "Polygon") g.coordinates.forEach(addRing);
      else if (g.type === "MultiPolygon") g.coordinates.forEach((p) => p.forEach(addRing));
    }
    if (rings.length) state.basemap = { rings, bbox: [minLon, minLat, maxLon, maxLat] };
  } catch {
    /* no basemap — the map falls back to its schematic plot */
  }
}

function setData(doc) {
  state.cells = doc.cells || [];
  state.buckets = doc.buckets || [...new Set(state.cells.map((c) => c.bucket))].sort();
  indexCells();
  state.bucketIdx = Math.max(0, state.buckets.length - 1);
  const slider = $("#time-slider");
  slider.max = String(Math.max(0, state.buckets.length - 1));
  slider.value = String(state.bucketIdx);
  slider.setAttribute("aria-disabled", state.buckets.length <= 1 ? "true" : "false");
  const src = $("#data-source");
  if (src) src.textContent = doc.attribution ? `Data: ${doc.attribution}` : "";
}

function indexCells() {
  const ids = [...new Set(state.cells.map((c) => c.cell_id))].sort();
  state.cellIndex = new Map(ids.map((id, i) => [id, i + 1]));
}

// -- formatting --------------------------------------------------------------

function placeName(row) {
  return row.label || `${t("cell-word")} ${state.cellIndex.get(row.cell_id)}`;
}

function localCategory(category) {
  const slug = CAT_SLUG[category];
  return slug ? t(`cat-${slug}`) : category;
}

function localExposure(level) {
  const slug = EXP_SLUG[level];
  return slug ? t(`exp-${slug}`) : level;
}

function localHeat(tier) {
  const slug = HEAT_SLUG[tier];
  return slug ? t(`heat-${slug}`) : tier;
}

function isExposure() {
  return state.parameter === "exposure";
}

function unitLabel() {
  const base = PARAM_BASE_UNIT[state.parameter];
  if (base === "C") return state.unit === "F" ? "°F" : "°C";
  if (base === "ug") return "µg/m³";
  return "ppb";
}

function convert(mean) {
  if (PARAM_BASE_UNIT[state.parameter] === "C" && state.unit === "F") return (mean * 9) / 5 + 32;
  return mean;
}

function round1(x) {
  return Math.round(x * 10) / 10;
}

function fmtValue(mean) {
  return `${round1(convert(mean))} ${unitLabel()}`;
}

function fmtUncertainty(u) {
  if (u == null) return "";
  const scaled = PARAM_BASE_UNIT[state.parameter] === "C" && state.unit === "F" ? (u * 9) / 5 : u;
  return ` ± ${round1(scaled)}`;
}

function fmtBucket(bucket) {
  if (!bucket) return "—";
  try {
    return new Intl.DateTimeFormat(document.documentElement.lang || "en", {
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
    }).format(new Date(bucket));
  } catch {
    return bucket.replace("T", " ").replace(":00Z", " UTC");
  }
}

function exposureReading(row) {
  // The level name carries severity in text; "~" marks a provisional (unconfirmed) level (F4).
  return row.provisional ? `~${localExposure(row.category)}` : localExposure(row.category);
}

function describe(row) {
  const place = placeName(row);
  if (isExposure()) {
    const comp = row.compound ? ` — ${t("exp-compound")}` : "";
    const ctx = [];
    if (row.heat_category) ctx.push(`${t("exp-heat")}: ${localHeat(row.heat_category)}`);
    if (row.air_category) ctx.push(`${t("exp-air")}: ${localCategory(row.air_category)}`);
    const detail = ctx.length ? ` (${ctx.join(", ")})` : "";
    const prov = row.provisional ? ` (${t("state-provisional")})` : "";
    return `${place}: ${exposureReading(row)}${comp}${detail}${prov}`;
  }
  if (state.parameter === "pm25_ugm3") {
    const aqi = row.provisional ? `~AQI ${row.aqi}` : `AQI ${row.aqi}`;
    // Provisional cells never assert a named category as fact (F4).
    const cat = row.provisional ? ` (${t("state-provisional")})` : `, ${localCategory(row.category)}`;
    return `${place}: ${aqi}${cat}, ${Math.round(row.mean)} µg/m³`;
  }
  const prov = row.provisional ? ` (${t("state-provisional")})` : "";
  return `${place}: ${fmtValue(row.mean)}${fmtUncertainty(row.uncertainty)}${prov}`;
}

function guidanceFor(category) {
  const slug = CAT_SLUG[category];
  return slug ? t(`guide-${slug}`) : "";
}

// The "show your work" trust view: calibration state, published uncertainty, the method and the
// reference monitor a confirmed value was fitted against, and how many readings stand behind it.
// A weather app gives one number; swelter shows whether to believe it and why.
function provenanceText(row) {
  const parts = [];
  if (row.provisional) {
    parts.push(t("prov-provisional"));
  } else {
    parts.push(t("prov-confirmed"));
    if (!isExposure() && row.uncertainty != null) {
      const u =
        PARAM_BASE_UNIT[state.parameter] === "C" && state.unit === "F"
          ? (row.uncertainty * 9) / 5
          : row.uncertainty;
      parts.push(t("prov-uncertainty").replace("{u}", round1(u)).replace("{unit}", unitLabel()));
    }
    if (row.method && row.reference) {
      parts.push(t("prov-method").replace("{method}", row.method).replace("{reference}", row.reference));
    }
  }
  if (isExposure()) parts.push(t("prov-derived"));
  parts.push(t("prov-readings").replace("{n}", row.n));
  return parts.join(" ");
}

// A ready-to-paste, plain-language summary of this location: the reading, how it compares, the
// trend, its calibration state, an open-data attribution, and the shareable link. Closes the
// data-to-action gap — something an advocate can drop into an email, a flyer, or testimony.
function briefText(row) {
  const lines = [`${placeName(row)} — ${fmtBucket(currentBucket())}`];
  lines.push(describe(row).split(": ").slice(1).join(": "));
  const c = contrastLine(row);
  if (c) lines.push(c);
  const tr = trendLine(row);
  if (tr) lines.push(tr);
  lines.push(provenanceText(row));
  lines.push(t("brief-source"));
  lines.push(location.href);
  return lines.join("\n");
}

// A plain-language summary of the WHOLE network right now — the measurement and hour, the confirmed
// vs provisional counts, sensor coverage and health, the spread, the single worst confirmed location,
// and how current the data is — with open-data attribution and the shareable link. The data-to-action
// bridge for a reporter or advocate who needs the big picture in words, not a screenshot. It reuses
// exactly the lines the overview already shows, so the copy matches the screen.
function networkBriefText() {
  const param = t(PARAM_I18N[state.parameter] || "parameter");
  const lines = [
    t("brief-network-title").replace("{param}", param).replace("{time}", fmtBucket(currentBucket())),
    $("#overview-counts").textContent,
    $("#overview-coverage").textContent,
    $("#overview-health").textContent,
    $("#overview-spread").textContent,
    $("#overview-worst").textContent,
    $("#overview-fresh").textContent,
    t("brief-source"),
    location.href,
  ];
  return lines.filter((line) => line && line.trim()).join("\n");
}

// A download link to the raw CC0 readings behind a location, filtered to one of its nodes. Served
// by `swelter serve`; the node id is the only identifier and is already public in the API.
function downloadLink(node, text) {
  const a = document.createElement("a");
  a.href = `export.csv?node=${encodeURIComponent(node)}`;
  a.textContent = text;
  a.setAttribute("download", "");
  return a;
}

function renderDownload(row) {
  const dl = $("#download-cell");
  dl.textContent = "";
  const nodes = row.nodes || [];
  if (nodes.length === 1) {
    dl.appendChild(downloadLink(nodes[0], t("download-cell")));
  } else if (nodes.length > 1) {
    dl.appendChild(document.createTextNode(t("download-cell-multi") + " "));
    nodes.forEach((n, i) => {
      dl.appendChild(downloadLink(n, n));
      if (i < nodes.length - 1) dl.appendChild(document.createTextNode(", "));
    });
  }
}

function heatGuidanceFor(tier) {
  const slug = HEAT_SLUG[tier];
  return slug && slug !== "none" ? t(`heat-guide-${slug}`) : "";
}

// E2: "What to do now" — the EPA/NWS guidance for the dominant hazard, turned into a short list of
// concrete protective steps a resident can act on. It pairs with R2 (no false safety): the calmest
// tier never says "you're safe", only that no special precautions are needed *right now* and that
// conditions change — and it stays silent on a provisional cell, where "calm" can't be asserted.
const HEAT_ACTIONS = {
  Caution: ["act-heat-water", "act-heat-shade"],
  "Extreme Caution": ["act-heat-water", "act-heat-shade", "act-heat-easy", "act-heat-neighbors"],
  Danger: ["act-heat-cool", "act-heat-signs", "act-heat-neighbors"],
  "Extreme Danger": ["act-heat-ac", "act-heat-emergency", "act-heat-neighbors"],
};
const AIR_ACTIONS = {
  Moderate: ["act-air-sensitive"],
  "Unhealthy for Sensitive Groups": ["act-air-groups", "act-air-inhaler"],
  Unhealthy: ["act-air-cutback", "act-air-windows", "act-air-mask"],
  "Very Unhealthy": ["act-air-indoors", "act-air-windows", "act-air-mask"],
  Hazardous: ["act-air-indoors", "act-air-windows", "act-air-mask"],
};

// The i18n keys for the action card, for the dominant hazard — mirrors the guidance logic above so
// the steps match whichever side (heat or air) is driving the level. Returns null for parameters
// that carry no hazard guidance (temperature/humidity/PM10 on their own), and null on a provisional
// cell whose only message would be the calm line — we never assert "calm" on an unconfirmed reading.
function actionKeysFor(row) {
  let keys = null;
  if (state.parameter === "pm25_ugm3") {
    keys = AIR_ACTIONS[row.category] || null;
  } else if (state.parameter === "heat_index_c") {
    keys = HEAT_ACTIONS[heatTier(row.mean)] || null;
  } else if (isExposure()) {
    const heatDominant = (HEAT_LEVEL[row.heat_category] ?? 0) > (AIR_LEVEL[row.air_category] ?? 0);
    keys = heatDominant
      ? HEAT_ACTIONS[row.heat_category] || null
      : AIR_ACTIONS[row.air_category] || null;
  } else {
    return null;
  }
  if (keys) return keys;
  return row.provisional ? null : ["act-calm"];
}

function renderActions(row) {
  const card = $("#action-card");
  const keys = actionKeysFor(row);
  if (!keys) {
    card.hidden = true;
    return;
  }
  const list = $("#action-list");
  list.textContent = "";
  for (const key of keys) {
    const li = document.createElement("li");
    li.textContent = t(key);
    list.appendChild(li);
  }
  // The "not medical advice" note only reads sensibly beside protective steps, not the calm line.
  $(".action-note").hidden = keys.length === 1 && keys[0] === "act-calm";
  card.hidden = false;
}

// -- selection / current rows ------------------------------------------------

function currentBucket() {
  return state.buckets[state.bucketIdx];
}

function current() {
  const bucket = currentBucket();
  let rows = state.cells.filter((c) => c.parameter === state.parameter && c.bucket === bucket);
  if (state.search) {
    const q = state.search.toLowerCase();
    rows = rows.filter((r) => placeName(r).toLowerCase().includes(q));
  }
  const k = state.sortKey;
  rows = [...rows].sort((a, b) => {
    if (k === "label") return placeName(a).localeCompare(placeName(b)) * state.sortDir;
    return (a.mean - b.mean) * state.sortDir; // value sort by display magnitude
  });
  return rows;
}

function pm25RowsNow() {
  const bucket = currentBucket();
  return state.cells.filter((c) => c.parameter === "pm25_ugm3" && c.bucket === bucket);
}

// Every location reporting the active parameter in the selected hour — the network-wide peer set a
// generic weather app can't show, because it has one regional value, not a map of them.
function peersNow(row) {
  return state.cells.filter((c) => c.parameter === state.parameter && c.bucket === row.bucket);
}

// "How does my block compare right now?" — the urban-heat-island / air-inequity signal a regional
// weather app can't give. Reported as an honest, tie-safe count (how many locations are worse) plus
// the gap from the network median — never a percentile, which ties would overstate.
function contrastLine(row) {
  const peers = peersNow(row);
  if (peers.length < 3) return ""; // not meaningful with only a couple of locations
  const vals = peers.map((p) => p.mean);
  const higher = vals.filter((v) => v > row.mean).length; // strictly worse/hotter than this one
  const heatLike = state.parameter === "temp_c" || state.parameter === "heat_index_c";
  let text;
  if (higher === 0) {
    text = t(heatLike ? "context-top-hot" : "context-top-bad");
  } else {
    text = t(heatLike ? "context-rank-hot" : "context-rank-bad")
      .replace("{n}", higher)
      .replace("{total}", peers.length);
  }
  if (!isExposure()) {
    const sorted = [...vals].sort((a, b) => a - b);
    const n = sorted.length;
    const median = n % 2 ? sorted[(n - 1) / 2] : (sorted[n / 2 - 1] + sorted[n / 2]) / 2;
    const d = round1(convert(row.mean) - convert(median));
    if (Math.abs(d) >= 0.1) {
      text +=
        " " +
        t("context-median")
          .replace("{delta}", Math.abs(d))
          .replace("{unit}", unitLabel())
          .replace("{dir}", d > 0 ? t("context-above") : t("context-below"));
    }
  }
  return text;
}

// "Is today worse than yesterday on my block?" — compare this location's reading to the same hour
// ~24 h earlier (nearest within 90 min), from the loaded history. Day-over-day context the
// short-term trend can't give, and a single regional weather value never could per location.
function dayChangeLine(row) {
  if (!state.historyLoaded) return "";
  const target = new Date(currentBucket()).getTime() - 24 * 3600 * 1000;
  let best = null;
  let bestD = Infinity;
  for (const c of state.cells) {
    if (c.cell_id !== row.cell_id || c.parameter !== state.parameter) continue;
    const d = Math.abs(new Date(c.bucket).getTime() - target);
    if (d < bestD) {
      bestD = d;
      best = c;
    }
  }
  if (!best || bestD > 90 * 60 * 1000) return ""; // no comparable reading ~24 h ago
  if (state.parameter === "pm25_ugm3" || isExposure()) {
    const order = isExposure() ? EXP_ORDER : AQI_ORDER;
    const cmp = order.indexOf(row.category) - order.indexOf(best.category);
    return t(cmp > 0 ? "yesterday-worse" : cmp < 0 ? "yesterday-better" : "yesterday-same");
  }
  const d = round1(convert(row.mean) - convert(best.mean));
  if (Math.abs(d) < 0.1) return t("yesterday-same");
  return t(d > 0 ? "yesterday-higher" : "yesterday-lower")
    .replace("{d}", Math.abs(d))
    .replace("{unit}", unitLabel());
}

// Per-parameter "steady" band, so small wiggles don't read as a trend.
const TREND_EPS = { exposure: 0.5, temp_c: 0.5, heat_index_c: 0.5, pm25_ugm3: 1, pm10_ugm3: 2, no2_ppb: 2 };

// "Is it getting worse or clearing on my block?" — direction over the last few hours, from the same
// time series the slider reads. Needs the loaded history; silent until it's there.
function trendLine(row) {
  if (!state.historyLoaded || state.bucketIdx < 1) return "";
  const back = Math.min(3, state.bucketIdx);
  const past = state.buckets[state.bucketIdx - back];
  const prev = state.cells.find(
    (c) => c.cell_id === row.cell_id && c.parameter === state.parameter && c.bucket === past,
  );
  if (!prev) return "";
  const d = row.mean - prev.mean;
  const eps = TREND_EPS[state.parameter] ?? 0.5;
  const key = d > eps ? "trend-rising" : d < -eps ? "trend-falling" : "trend-steady";
  const arrow = d > eps ? "↑" : d < -eps ? "↓" : "→";
  return `${arrow} ${t(key).replace("{h}", back)}`;
}

// -- rendering ---------------------------------------------------------------

// The legend adapts to the active measurement so the marker colours are interpretable: PM2.5 shows
// the AQI categories, temperature/heat index the cool→hot swatches, exposure the Minimal→Extreme
// levels, and PM10/NO2 a plain "shown by value" note. Each block is prebuilt in the HTML and keyed
// by data-legend; this swaps the visible one and retitles the heading. Severity is always carried by
// the level NAME in text (and a swatch/pattern), never by colour alone.
const LEGEND_BLOCK = {
  pm25_ugm3: "pm25",
  temp_c: "temp",
  heat_index_c: "temp",
  exposure: "exposure",
  pm10_ugm3: "value",
  no2_ppb: "value",
};
const LEGEND_TITLE = {
  pm25_ugm3: "legend-title-pm25",
  temp_c: "legend-title-temp",
  heat_index_c: "legend-title-hi",
  exposure: "legend-title-exposure",
  pm10_ugm3: "legend-title-pm10",
  no2_ppb: "legend-title-no2",
};

function updateLegend() {
  const active = LEGEND_BLOCK[state.parameter] || "value";
  for (const block of document.querySelectorAll(".legend-block")) {
    block.hidden = block.getAttribute("data-legend") !== active;
  }
  const heading = $("#legend-heading");
  if (heading) {
    const key = LEGEND_TITLE[state.parameter] || "legend-title-pm25";
    heading.textContent = t(key);
  }
}

function renderHeadline() {
  const confirmed = pm25RowsNow().filter((r) => !r.provisional);
  const el = $("#headline");
  if (!confirmed.length) {
    el.textContent = t("headline-none");
    return;
  }
  const worst = confirmed.reduce((a, b) => (b.aqi > a.aqi ? b : a));
  const lead = t("headline-worst")
    .replace("{place}", placeName(worst))
    .replace("{aqi}", String(worst.aqi))
    .replace("{category}", localCategory(worst.category));
  el.textContent = `${lead} ${guidanceFor(worst.category)}`;
}

// Every location reporting the active parameter this hour — the network, not the search-filtered view.
function overviewRows() {
  const bucket = currentBucket();
  return state.cells.filter((c) => c.parameter === state.parameter && c.bucket === bucket);
}

// Node health (from /api/health.json, or the baked sample on the static site): the network's
// sensors broken down by status — ok, degraded (backfilled sparsely or flagging a lot), offline.
// The operator's "is my network healthy?" line, from the same QC the pipeline already runs.
function healthLine() {
  const s = state.health && state.health.summary;
  if (!s || !s.total) return "";
  return t("health-status")
    .replace("{ok}", s.ok || 0)
    .replace("{degraded}", s.degraded || 0)
    .replace("{offline}", s.offline || 0);
}

async function loadHealth() {
  const doc = (await fetchJson("api/health.json")) || (await fetchJson("sample-health.json"));
  if (doc && doc.summary) {
    state.health = doc;
    renderOverview();
  }
}

async function fetchJson(url) {
  try {
    const res = await fetch(url);
    return res.ok ? await res.json() : null;
  } catch {
    return null;
  }
}

// Sensor coverage: how many of the network's known sensors are actually reporting this hour. "Known"
// is every node seen anywhere in the loaded history; "now" is those reporting in the current hour. A
// gap (e.g. a node offline) shows honestly — the coverage-equity question the audits care about.
function coverageLine() {
  const bucket = currentBucket();
  const known = new Set();
  const now = new Set();
  for (const c of state.cells) {
    for (const node of c.nodes || []) {
      known.add(node);
      if (c.bucket === bucket) now.add(node);
    }
  }
  if (!known.size) return "";
  return t("coverage").replace("{now}", now.size).replace("{total}", known.size);
}

// How current the data actually is — the newest hour in the network and its age, with an honest
// "this network may be behind" note when it's stale. A community/scale-to-zero network can lag, and
// saying so plainly is the trustworthy thing a generic weather app's "live" badge won't.
function freshnessLine() {
  if (!state.buckets.length) return "";
  const latest = state.buckets[state.buckets.length - 1];
  const ageMin = Math.max(0, Math.round((Date.now() - new Date(latest).getTime()) / 60000));
  let age;
  if (ageMin < 60) age = t("fresh-min").replace("{m}", ageMin);
  else if (ageMin < 2880) age = t("fresh-hr").replace("{h}", Math.round(ageMin / 60));
  else age = t("fresh-day").replace("{d}", Math.round(ageMin / 1440));
  let line = t("fresh-latest").replace("{time}", fmtBucket(latest)).replace("{age}", age);
  if (ageMin > 180) line += " " + t("fresh-stale");
  return line;
}

// A reading's age in plain words from an ISO timestamp — minutes, hours, or days ago.
function ageText(iso) {
  const ageMin = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
  if (ageMin < 60) return t("fresh-min").replace("{m}", ageMin);
  if (ageMin < 2880) return t("fresh-hr").replace("{h}", Math.round(ageMin / 60));
  return t("fresh-day").replace("{d}", Math.round(ageMin / 1440));
}

// Per-node health for the host: the overview line gives the ok/degraded/offline counts; this names
// the sensors that need attention (offline first, then degraded), with completeness and when each
// was last seen. node_id is the only, already-public identifier — no PII. When every node is fine it
// says so plainly. The list answers a host's "which sensor do I go check?" the aggregate can't.
function renderHealthDetail() {
  const wrap = $("#health-detail");
  const list = $("#health-list");
  if (!wrap || !list) return;
  const nodes = (state.health && state.health.nodes) || [];
  if (!nodes.length) {
    wrap.hidden = true;
    return;
  }
  wrap.hidden = false;
  list.textContent = "";
  const rank = { offline: 0, degraded: 1 };
  const attention = nodes
    .filter((n) => n.status === "offline" || n.status === "degraded")
    .sort((a, b) => (rank[a.status] - rank[b.status]) || a.completeness - b.completeness);
  if (!attention.length) {
    const li = document.createElement("li");
    li.textContent = t("health-all-ok").replace("{n}", String(nodes.length));
    list.appendChild(li);
    return;
  }
  for (const n of attention) {
    const li = document.createElement("li");
    li.textContent = t("health-node")
      .replace("{node}", n.node_id)
      .replace("{status}", t(n.status === "offline" ? "health-stat-offline" : "health-stat-degraded"))
      .replace("{pct}", String(Math.round((n.completeness || 0) * 100)))
      .replace("{age}", n.last_seen ? ageText(n.last_seen) : "—");
    list.appendChild(li);
  }
}

function worstButton(row, label) {
  const b = document.createElement("button");
  b.type = "button";
  b.className = "linklike";
  b.textContent = label;
  b.addEventListener("click", () => select(row.cell_id, true));
  return b;
}

// "Right now across the network" — the shape of the whole network for the current measurement and
// hour: how many confirmed vs provisional, the spread (a category breakdown, or low/typical/high for
// a number), and the single worst confirmed location. The big-picture view officials and reporters
// want, beside the per-location detail residents use.
function renderOverview() {
  const panel = $("#overview");
  const rows = overviewRows();
  if (!rows.length) {
    panel.hidden = true;
    return;
  }
  panel.hidden = false;
  const confirmed = rows.filter((r) => !r.provisional);
  $("#overview-counts").textContent = t("overview-counts")
    .replace("{n}", rows.length)
    .replace("{confirmed}", confirmed.length)
    .replace("{provisional}", rows.length - confirmed.length);

  $("#overview-coverage").textContent = coverageLine();
  $("#overview-health").textContent = healthLine();
  renderHealthDetail();
  $("#overview-fresh").textContent = freshnessLine();
  const spread = $("#overview-spread");
  const worstEl = $("#overview-worst");
  worstEl.textContent = "";

  if (state.parameter === "pm25_ugm3" || isExposure()) {
    const order = isExposure() ? EXP_ORDER : AQI_ORDER;
    const localize = isExposure() ? localExposure : localCategory;
    const counts = new Map();
    for (const r of confirmed) counts.set(r.category, (counts.get(r.category) || 0) + 1);
    const parts = order.filter((c) => counts.get(c)).map((c) => `${localize(c)} ${counts.get(c)}`);
    spread.textContent = parts.length ? parts.join(" · ") : t("overview-none-confirmed");
    if (confirmed.length) {
      const worst = confirmed.reduce((a, b) =>
        order.indexOf(b.category) > order.indexOf(a.category) ? b : a,
      );
      worstEl.appendChild(document.createTextNode(t("overview-worst-label") + " "));
      worstEl.appendChild(worstButton(worst, `${placeName(worst)} — ${localize(worst.category)}`));
    }
  } else {
    const vals = rows.map((r) => r.mean).sort((a, b) => a - b);
    const n = vals.length;
    const median = n % 2 ? vals[(n - 1) / 2] : (vals[n / 2 - 1] + vals[n / 2]) / 2;
    spread.textContent = t("overview-spread")
      .replace("{min}", round1(convert(vals[0])))
      .replace("{median}", round1(convert(median)))
      .replace("{max}", round1(convert(vals[n - 1])))
      .replace("{unit}", unitLabel());
    const worst = rows.reduce((a, b) => (b.mean > a.mean ? b : a));
    worstEl.appendChild(document.createTextNode(t("overview-worst-label") + " "));
    worstEl.appendChild(worstButton(worst, `${placeName(worst)} — ${fmtValue(worst.mean)}`));
  }
}

function renderList(rows) {
  const list = $("#data-list");
  list.textContent = "";
  for (const row of rows) {
    const li = document.createElement("li");
    li.dataset.cell = row.cell_id;
    if (row.cell_id === state.selected) li.classList.add("selected");
    const place = document.createElement("span");
    place.className = "place";
    place.textContent = placeName(row) + " — ";
    const reading = document.createElement("span");
    reading.className = "reading";
    reading.textContent = describe(row).split(": ").slice(1).join(": ");
    li.append(place, reading);
    li.addEventListener("click", () => select(row.cell_id));
    list.appendChild(li);
  }
}

function renderTable(rows) {
  const body = $("#data-table-body");
  body.textContent = "";
  for (const row of rows) {
    const tr = document.createElement("tr");
    tr.dataset.cell = row.cell_id;
    if (row.cell_id === state.selected) tr.classList.add("selected");

    const place = document.createElement("th");
    place.scope = "row";
    place.textContent = placeName(row);
    tr.appendChild(place);

    const readingText = isExposure()
      ? `${exposureReading(row)}${row.compound ? ` — ${t("exp-compound")}` : ""}`
      : `${fmtValue(row.mean)}${fmtUncertainty(row.uncertainty)}`;
    tr.appendChild(td(readingText));

    const aqi = document.createElement("td");
    if (state.parameter === "pm25_ugm3" && row.category) {
      const tag = document.createElement("span");
      tag.className = `tag ${row.provisional ? "" : AQI_CLASS[row.category] || ""}`;
      tag.textContent = row.provisional
        ? `~AQI ${row.aqi}`
        : `AQI ${row.aqi} — ${localCategory(row.category)}`;
      aqi.appendChild(tag);
    } else if (isExposure() && row.air_category) {
      // Exposure: the Air-quality column shows its air component (the level itself is in Reading).
      const tag = document.createElement("span");
      tag.className = `tag ${row.provisional ? "" : AQI_CLASS[row.air_category] || ""}`;
      tag.textContent = localCategory(row.air_category);
      aqi.appendChild(tag);
    } else {
      aqi.textContent = "—";
    }
    tr.appendChild(aqi);

    const stateCell = document.createElement("td");
    const tag = document.createElement("span");
    tag.className = `tag ${row.provisional ? "provisional" : ""}`;
    tag.textContent = row.provisional ? t("state-provisional") : t("state-calibrated");
    stateCell.appendChild(tag);
    tr.appendChild(stateCell);

    tr.addEventListener("click", () => select(row.cell_id));
    body.appendChild(tr);
  }
}

function td(text) {
  const cell = document.createElement("td");
  cell.textContent = text;
  return cell;
}

// Equirectangular projection over a bounding box, with a cos(latitude) longitude scale so the
// shape isn't stretched east-west. When a basemap (e.g. California) is loaded we fit to ITS bbox so
// the geography stays recognizable however few points there are; otherwise we fit to the data.
function mapProjection(rows) {
  const bm = state.basemap;
  let minLon, minLat, maxLon, maxLat;
  if (bm) {
    [minLon, minLat, maxLon, maxLat] = bm.bbox;
  } else {
    const lats = rows.map((r) => r.lat);
    const lons = rows.map((r) => r.lon);
    [minLat, maxLat, minLon, maxLon] = [
      Math.min(...lats),
      Math.max(...lats),
      Math.min(...lons),
      Math.max(...lons),
    ];
  }
  const pad = bm ? 0.04 : 0; // keep the coastline off the edge; data-only fit insets per-marker
  const padLat = (maxLat - minLat || 1) * pad;
  const padLon = (maxLon - minLon || 1) * pad;
  minLat -= padLat;
  maxLat += padLat;
  minLon -= padLon;
  maxLon += padLon;
  const kx = Math.cos((((minLat + maxLat) / 2) * Math.PI) / 180);
  return { minLon, minLat, maxLon, maxLat, kx, W: (maxLon - minLon) * kx, H: maxLat - minLat };
}

// The basemap polygons as one decorative, aria-hidden SVG path behind the markers, projected with
// the same transform so the dots land on the right geography. preserveAspectRatio="none" is safe
// because we set #map's aspect-ratio to W/H, so the viewBox maps 1:1 with no distortion.
function buildBasemap(proj) {
  const NS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("class", "basemap");
  svg.setAttribute("viewBox", `0 0 ${proj.W} ${proj.H}`);
  svg.setAttribute("preserveAspectRatio", "none");
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("focusable", "false");
  let d = "";
  for (const ring of state.basemap.rings) {
    for (let i = 0; i < ring.length; i++) {
      const x = ((ring[i][0] - proj.minLon) * proj.kx).toFixed(2);
      const y = (proj.maxLat - ring[i][1]).toFixed(2);
      d += (i === 0 ? "M" : "L") + x + " " + y;
    }
    d += "Z";
  }
  const path = document.createElementNS(NS, "path");
  path.setAttribute("d", d);
  path.setAttribute("class", "basemap-land");
  svg.appendChild(path);
  return svg;
}

// A marker's position within the canvas, as left/bottom fractions [0,1]. With a basemap we fill the
// projected box edge-to-edge; without one we inset a little so data isn't flush to the border.
function markerPos(row, proj) {
  const span = (v, lo, hi) => (hi === lo ? 0.5 : (v - lo) / (hi - lo));
  if (state.basemap) {
    return { left: span(row.lon, proj.minLon, proj.maxLon), bottom: span(row.lat, proj.minLat, proj.maxLat) };
  }
  return {
    left: 0.06 + 0.88 * span(row.lon, proj.minLon, proj.maxLon),
    bottom: 0.08 + 0.84 * span(row.lat, proj.minLat, proj.maxLat),
  };
}

function renderMap(rows) {
  const map = $("#map");
  map.textContent = "";
  map.classList.toggle("dense", rows.length > 50); // shrink markers on a dense network
  if (!rows.length) return;
  const proj = mapProjection(rows);
  // Without a basemap the projection is fit to the current rows, so a changed extent (a search
  // filter, a different parameter's coverage) would silently re-anchor a held zoom onto new ground.
  // Refit when that signature changes so the view never drifts onto unrelated geography.
  const sig = `${state.basemap ? "bm" : "data"}:${proj.minLon},${proj.minLat},${proj.maxLon},${proj.maxLat}`;
  if (!state.basemap && sig !== state.projSig) state.mapView = { zoom: 1, x: 0, y: 0 };
  state.projSig = sig;
  if (state.basemap) {
    // Match the box to the projection so the outline isn't stretched, and cap its height.
    map.style.aspectRatio = `${proj.W} / ${proj.H}`;
    map.style.maxWidth = `${((proj.W / proj.H) * 34).toFixed(2)}rem`;
    map.style.marginInline = "auto";
    map.style.minHeight = "0"; // let the aspect-ratio drive height; don't stretch on narrow screens
  } else {
    map.style.removeProperty("aspect-ratio");
    map.style.removeProperty("max-width");
    map.style.removeProperty("margin-inline");
    map.style.removeProperty("min-height");
  }
  const canvas = document.createElement("div");
  canvas.className = "map-canvas";
  if (state.basemap) canvas.appendChild(buildBasemap(proj));
  for (const row of rows) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "cell";
    btn.dataset.cell = row.cell_id;
    // Provisional cells stay neutral — they never wear a confirmed AQI color (F4).
    if (!row.provisional && state.parameter === "pm25_ugm3" && AQI_CLASS[row.category]) {
      btn.classList.add(AQI_CLASS[row.category]);
    } else if (
      !row.provisional &&
      (state.parameter === "temp_c" || state.parameter === "heat_index_c")
    ) {
      // Shade the heat map cool→hot so the urban heat island is visible; the number is always
      // shown on the marker, so magnitude is never carried by color alone.
      btn.classList.add(heatClass(row.mean));
    }
    if (row.provisional) btn.classList.add("provisional");
    if (row.cell_id === state.selected) btn.classList.add("selected");
    const pos = markerPos(row, proj);
    btn.style.left = `${pos.left * 100}%`;
    btn.style.bottom = `${pos.bottom * 100}%`;
    btn.setAttribute("aria-label", describe(row));
    const value = document.createElement("span");
    value.textContent =
      state.parameter === "pm25_ugm3"
        ? `${row.aqi}`
        : isExposure()
          ? `${Math.round(row.mean)}`
          : `${Math.round(convert(row.mean))}`;
    btn.appendChild(value);
    const cat = document.createElement("span");
    cat.className = "cell-cat";
    cat.textContent =
      state.parameter === "pm25_ugm3"
        ? row.provisional
          ? t("state-provisional")
          : localCategory(row.category)
        : isExposure()
          ? row.provisional
            ? t("state-provisional")
            : localExposure(row.category)
          : unitLabel();
    btn.appendChild(cat);
    btn.addEventListener("click", () => {
      if (mapDidDrag || mapWasMultiTouch) return; // don't let a pan/pinch end as a marker select
      select(row.cell_id, true); // a marker tap focuses the map on that cell
    });
    canvas.appendChild(btn);
  }
  lastK = -1; // force the next applyMapTransform to (re)write --k onto the fresh canvas
  map.appendChild(canvas);
  applyMapTransform(false);
  if (state.pendingFocus) {
    const focus = state.pendingFocus;
    state.pendingFocus = null;
    zoomToCell(focus, false);
  }
}

// -- map zoom & pan ----------------------------------------------------------

function measureMap() {
  const map = $("#map");
  if (map && map.clientWidth) {
    mapW = map.clientWidth;
    mapH = map.clientHeight;
  }
}

function clampMapView() {
  const v = state.mapView;
  v.zoom = Math.min(MAX_ZOOM, Math.max(1, v.zoom));
  // Keep the scaled canvas covering the viewport so the map can never be lost off-screen. Uses the
  // cached size (measured on show/resize) so this hot path never forces a synchronous reflow.
  v.x = Math.min(0, Math.max(mapW * (1 - v.zoom), v.x));
  v.y = Math.min(0, Math.max(mapH * (1 - v.zoom), v.y));
}

function applyMapTransform(animate) {
  if (!mapVisible) return; // tab hidden / unmeasurable — the transform is applied when it is shown
  const canvas = $("#map .map-canvas");
  if (!canvas) return;
  clampMapView();
  const v = state.mapView;
  canvas.classList.toggle("animate", !!animate && !reduceMotionMQL.matches);
  if (v.zoom !== lastK) {
    // Only touch --k on a real zoom change; a pan must not repaint all the counter-scaled markers.
    canvas.style.setProperty("--k", v.zoom);
    lastK = v.zoom;
  }
  canvas.style.transform = `translate(${v.x}px, ${v.y}px) scale(${v.zoom})`;
}

// Coalesce high-frequency input (wheel, drag, pinch) into one transform write per animation frame.
function scheduleTransform(animate) {
  if (animate) mapRafAnimate = true;
  if (mapRafPending) return;
  mapRafPending = true;
  requestAnimationFrame(() => {
    mapRafPending = false;
    const a = mapRafAnimate;
    mapRafAnimate = false;
    applyMapTransform(a);
  });
}

// Zoom by `factor` about a point (sx, sy) in #map-local pixels, keeping that point fixed. Mutates
// state only; the caller writes the DOM (scheduled for gestures, immediate for buttons/keys).
function zoomAt(sx, sy, factor) {
  const v = state.mapView;
  const k = Math.min(MAX_ZOOM, Math.max(1, v.zoom * factor));
  if (k === v.zoom) return;
  const r = k / v.zoom;
  v.x = sx - (sx - v.x) * r;
  v.y = sy - (sy - v.y) * r;
  v.zoom = k;
}

function zoomByButton(factor) {
  zoomAt(mapW / 2, mapH / 2, factor);
  applyMapTransform(true);
}

function resetMapView() {
  state.pendingFocus = null;
  state.mapView = { zoom: 1, x: 0, y: 0 };
  applyMapTransform(true);
}

// Center the map on a cell and zoom in. Defer if the map isn't measurable yet (hidden tab); if the
// target was filtered out (e.g. a search changed), keep a coherent view instead of going blank.
function zoomToCell(cellId, animate) {
  if (!mapVisible || !mapW) {
    state.pendingFocus = cellId;
    return;
  }
  const rows = current();
  const row = rows.find((r) => r.cell_id === cellId);
  if (!row) {
    applyMapTransform(animate);
    return;
  }
  const pos = markerPos(row, mapProjection(rows));
  const k = Math.min(MAX_ZOOM, Math.max(state.mapView.zoom, 6));
  const px = pos.left * mapW; // marker x in canvas px at scale 1
  const py = (1 - pos.bottom) * mapH; // bottom fraction → top-down px
  state.mapView.zoom = k;
  state.mapView.x = mapW / 2 - px * k;
  state.mapView.y = mapH / 2 - py * k;
  applyMapTransform(animate);
}

function wireMap() {
  const map = $("#map");
  if (!map) return;
  const pointers = new Map(); // pointerId → {x, y, cx, cy} (map-local + client coords)
  let drag = null; // {cx, cy, x, y} client coords + pan at drag start
  let pinch = null; // {dist, mx, my} for two-pointer zoom
  const local = (e) => {
    const r = map.getBoundingClientRect();
    return { x: e.clientX - r.left, y: e.clientY - r.top, cx: e.clientX, cy: e.clientY };
  };
  const startDrag = (p) => {
    drag = { cx: p.cx, cy: p.cy, x: state.mapView.x, y: state.mapView.y };
  };

  map.addEventListener(
    "wheel",
    (e) => {
      e.preventDefault();
      const p = local(e);
      zoomAt(p.x, p.y, e.deltaY < 0 ? 1.15 : 1 / 1.15);
      scheduleTransform(false);
    },
    { passive: false },
  );

  map.addEventListener("pointerdown", (e) => {
    map.setPointerCapture(e.pointerId);
    pointers.set(e.pointerId, local(e));
    mapDidDrag = false;
    if (pointers.size === 1) {
      mapWasMultiTouch = false;
      startDrag(pointers.get(e.pointerId));
      map.classList.add("dragging");
    } else if (pointers.size === 2) {
      mapWasMultiTouch = true;
      const [a, b] = [...pointers.values()];
      pinch = { dist: Math.hypot(a.x - b.x, a.y - b.y), mx: (a.x + b.x) / 2, my: (a.y + b.y) / 2 };
      drag = null;
    }
  });

  map.addEventListener("pointermove", (e) => {
    if (!pointers.has(e.pointerId)) return;
    pointers.set(e.pointerId, local(e));
    if (pinch && pointers.size >= 2) {
      const [a, b] = [...pointers.values()];
      const dist = Math.hypot(a.x - b.x, a.y - b.y);
      const mx = (a.x + b.x) / 2;
      const my = (a.y + b.y) / 2;
      // Pan by the midpoint movement, then zoom about the current midpoint — applied once.
      state.mapView.x += mx - pinch.mx;
      state.mapView.y += my - pinch.my;
      if (pinch.dist > 0) zoomAt(mx, my, dist / pinch.dist);
      pinch = { dist, mx, my };
      mapDidDrag = true;
      scheduleTransform(false);
    } else if (drag) {
      const dx = e.clientX - drag.cx;
      const dy = e.clientY - drag.cy;
      if (Math.abs(dx) + Math.abs(dy) > 4) mapDidDrag = true;
      state.mapView.x = drag.x + dx;
      state.mapView.y = drag.y + dy;
      scheduleTransform(false);
    }
  });

  const endPointer = (e) => {
    pointers.delete(e.pointerId);
    if (pointers.size < 2) pinch = null;
    if (pointers.size === 1) {
      // Lifting one finger of a pinch: keep panning with the finger that is still down.
      startDrag([...pointers.values()][0]);
    } else if (pointers.size === 0) {
      drag = null;
      map.classList.remove("dragging");
    }
  };
  map.addEventListener("pointerup", endPointer);
  map.addEventListener("pointercancel", endPointer);
  map.addEventListener("lostpointercapture", endPointer); // OS seized the gesture — don't get stuck

  map.addEventListener("dblclick", (e) => {
    if (mapDidDrag) return; // a double-tap that concluded a pan shouldn't also zoom
    e.preventDefault();
    const p = local(e);
    zoomAt(p.x, p.y, 1.8);
    applyMapTransform(true);
  });

  map.addEventListener("keydown", (e) => {
    const step = 40;
    const v = state.mapView;
    if (e.key === "ArrowLeft") v.x += step;
    else if (e.key === "ArrowRight") v.x -= step;
    else if (e.key === "ArrowUp") v.y += step;
    else if (e.key === "ArrowDown") v.y -= step;
    else if (e.key === "+" || e.key === "=") return void zoomKey(1.4, e);
    else if (e.key === "-" || e.key === "_") return void zoomKey(1 / 1.4, e);
    else if (e.key === "0") return void resetKey(e);
    else return;
    state.pendingFocus = null;
    scheduleTransform(false);
    e.preventDefault();
  });

  // Keep a keyboard-focused marker inside the clipped viewport — overflow:hidden cannot scroll it in.
  map.addEventListener("focusin", (e) => {
    const cell = e.target.closest && e.target.closest(".cell");
    if (!cell) return;
    const mr = map.getBoundingClientRect();
    const cr = cell.getBoundingClientRect();
    const m = 24;
    let dx = 0;
    let dy = 0;
    if (cr.left < mr.left + m) dx = mr.left + m - cr.left;
    else if (cr.right > mr.right - m) dx = mr.right - m - cr.right;
    if (cr.top < mr.top + m) dy = mr.top + m - cr.top;
    else if (cr.bottom > mr.bottom - m) dy = mr.bottom - m - cr.bottom;
    if (dx || dy) {
      state.mapView.x += dx;
      state.mapView.y += dy;
      applyMapTransform(true);
    }
  });

  $("#map-zoom-in").addEventListener("click", () => zoomByButton(1.4));
  $("#map-zoom-out").addEventListener("click", () => zoomByButton(1 / 1.4));
  $("#map-reset").addEventListener("click", resetMapView);

  if (window.ResizeObserver) {
    // Re-measure + reapply when the map box changes size (incl. becoming visible, or a viewport
    // resize) so clamping and centering use the true dimensions without per-frame reads.
    new ResizeObserver(() => {
      if (!mapVisible) return;
      measureMap();
      applyMapTransform(false);
    }).observe(map);
  }
}

function zoomKey(factor, e) {
  state.pendingFocus = null;
  zoomByButton(factor);
  e.preventDefault();
}

function resetKey(e) {
  resetMapView();
  e.preventDefault();
}

// A tiny sparkline of this location's last ~24 h for the active parameter — the recent shape at a
// glance, beside the text trend/day-over-day. The SVG is decorative (aria-hidden); the container is
// role="img" with a text label giving the low/high, so screen readers get the same information.
function renderSpark(row) {
  const el = $("#detail-spark");
  el.textContent = "";
  el.removeAttribute("role");
  el.removeAttribute("aria-label");
  if (!state.historyLoaded) return;
  const series = state.cells
    .filter((c) => c.cell_id === row.cell_id && c.parameter === state.parameter)
    .sort((a, b) => a.bucket.localeCompare(b.bucket))
    .slice(-24);
  if (series.length < 3) return;
  const vals = series.map((c) => convert(c.mean));
  const min = Math.min(...vals);
  const max = Math.max(...vals);
  const span = max - min || 1;
  const W = 132;
  const H = 30;
  const pad = 3;
  const points = vals
    .map((v, i) => {
      const x = pad + (i / (vals.length - 1)) * (W - 2 * pad);
      const y = H - pad - ((v - min) / span) * (H - 2 * pad);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.setAttribute("class", "spark-svg");
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("focusable", "false");
  const poly = document.createElementNS(ns, "polyline");
  poly.setAttribute("points", points);
  poly.setAttribute("fill", "none");
  poly.setAttribute("stroke", "currentColor");
  poly.setAttribute("stroke-width", "1.5");
  svg.appendChild(poly);
  el.appendChild(svg);
  const unit = isExposure() ? "" : ` ${unitLabel()}`;
  el.setAttribute("role", "img");
  el.setAttribute(
    "aria-label",
    t("spark-label")
      .replace("{n}", series.length)
      .replace("{low}", round1(min))
      .replace("{high}", round1(max))
      .replace("{unit}", unit),
  );
}

// Equity compare (the core "is my block worse than theirs?" question): pin a second location and
// read the two side by side for the active measurement and hour. Calibrated and raw are never mixed
// silently — each line shows its own reading, and if either is provisional the comparison is marked
// rough rather than asserted. Severity is stated in words, never by color.
function compareDiff(a, b) {
  const an = placeName(a);
  const bn = placeName(b);
  let line;
  if (state.parameter === "pm25_ugm3" || isExposure()) {
    const order = isExposure() ? EXP_ORDER : AQI_ORDER;
    const cmp = order.indexOf(a.category) - order.indexOf(b.category);
    const key = cmp > 0 ? "compare-worse" : cmp < 0 ? "compare-better" : "compare-same";
    line = t(key).replace("{a}", an).replace("{b}", bn);
  } else {
    const heatLike = state.parameter === "temp_c" || state.parameter === "heat_index_c";
    const d = round1(convert(a.mean) - convert(b.mean));
    if (Math.abs(d) < 0.1) {
      line = t("compare-same").replace("{a}", an).replace("{b}", bn);
    } else {
      const key = d > 0 ? (heatLike ? "compare-hotter" : "compare-higher") : heatLike ? "compare-cooler" : "compare-lower";
      line = t(key)
        .replace("{a}", an)
        .replace("{b}", bn)
        .replace("{d}", Math.abs(d))
        .replace("{unit}", unitLabel());
    }
  }
  if (a.provisional || b.provisional) line += " " + t("compare-provisional");
  return line;
}

function renderCompare(rowA) {
  const sel = $("#compare-select");
  const result = $("#compare-result");
  const others = current()
    .filter((r) => r.cell_id !== rowA.cell_id)
    .sort((x, y) => placeName(x).localeCompare(placeName(y)));
  // Rebuild the picker, keeping the current choice if it still exists for this measurement/hour.
  sel.textContent = "";
  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = t("compare-none");
  sel.appendChild(placeholder);
  for (const r of others) {
    const opt = document.createElement("option");
    opt.value = r.cell_id;
    opt.textContent = placeName(r);
    if (r.cell_id === state.compareCell) opt.selected = true;
    sel.appendChild(opt);
  }
  result.textContent = "";
  const b = others.find((r) => r.cell_id === state.compareCell);
  if (!b) return;
  for (const text of [describe(rowA), describe(b), compareDiff(rowA, b)]) {
    const div = document.createElement("div");
    div.textContent = text;
    result.appendChild(div);
  }
}

// -- personal alert thresholds -----------------------------------------------

function watchKey(cellId, parameter) {
  return `${cellId}|${parameter}`;
}

function loadWatches() {
  const w = loadPrefs().watches;
  return w && typeof w === "object" ? w : {};
}

function saveWatch(key, watch) {
  const watches = loadWatches();
  if (watch) watches[key] = watch;
  else delete watches[key];
  savePref("watches", watches);
}

// Does this row's current reading meet/exceed the saved level? Category watches compare ordinal
// positions; numeric watches compare in BASE units, so the °F/°C toggle never changes the verdict.
// A provisional reading can still cross — it is shown, but flagged rough rather than asserted (R: no
// false safety, calibrated/raw never silently mixed).
function watchCrossed(row, watch) {
  const order = CATEGORY_ORDER[row.parameter];
  if (order) {
    if (watch.kind !== "cat") return false;
    const pos = row.parameter === "heat_index_c" ? order.indexOf(heatTier(row.mean)) : order.indexOf(row.category);
    return pos >= 0 && pos >= watch.idx;
  }
  return watch.kind === "num" && row.mean >= watch.value;
}

// The level a watch is set to, in plain words for the active language — a category name or a value
// with its unit (converted for display; the stored value stays in base units).
function watchThresholdText(parameter, watch) {
  if (watch.kind === "cat") {
    const name = (CATEGORY_ORDER[parameter] || [])[watch.idx];
    if (parameter === "exposure") return localExposure(name);
    if (parameter === "heat_index_c") return localHeat(name);
    return localCategory(name);
  }
  const saved = state.parameter; // borrow the formatter for this parameter's unit/conversion
  state.parameter = parameter;
  const text = fmtValue(watch.value);
  state.parameter = saved;
  return text;
}

// The reading itself, in plain words, for an alert line — mirrors describe() but trimmed to the
// number/level and the rough-vs-confirmed flag, so the banner reads like the rest of the page.
function watchReadingText(row) {
  const order = CATEGORY_ORDER[row.parameter];
  if (order) {
    let name;
    if (row.parameter === "exposure") name = localExposure(row.category);
    else if (row.parameter === "heat_index_c") name = localHeat(heatTier(row.mean));
    else name = localCategory(row.category);
    return row.provisional ? `~${name}` : name;
  }
  const saved = state.parameter;
  state.parameter = row.parameter;
  const text = fmtValue(row.mean);
  state.parameter = saved;
  return text;
}

// The full alert sentence for one crossed watch — place, measurement, the reading, and the level the
// reader set. Severity is in WORDS, never color. Provisional readings carry the "rough" caveat so a
// crossing is never asserted as a confirmed category (R: no false safety; calibrated/raw not mixed).
function alertText(row, watch) {
  const param = t(PARAM_I18N[row.parameter] || "parameter");
  let line = t("alert-line")
    .replace("{place}", placeName(row))
    .replace("{param}", param)
    .replace("{reading}", watchReadingText(row))
    .replace("{threshold}", watchThresholdText(row.parameter, watch));
  if (row.provisional) line += " " + t("alert-provisional");
  return line;
}

// Every watched location whose current-hour reading is at/over its level, paired with its row.
function activeAlerts() {
  const watches = loadWatches();
  const bucket = currentBucket();
  const out = [];
  for (const [key, watch] of Object.entries(watches)) {
    const sep = key.lastIndexOf("|");
    if (sep < 0) continue;
    const cellId = key.slice(0, sep);
    const parameter = key.slice(sep + 1);
    const row = state.cells.find(
      (c) => c.cell_id === cellId && c.parameter === parameter && c.bucket === bucket,
    );
    if (row && watchCrossed(row, watch)) out.push({ key, row, watch });
  }
  return out;
}

// The Alerts banner: every watched location that is at/over its level right now, in plain language,
// with a button that selects it. It only ever reports crossings — it never says "you're safe" when
// under (R: no false safety), it just shows nothing. Hidden when there are no alerts.
function renderAlerts() {
  const section = $("#alerts");
  const list = $("#alerts-list");
  if (!section || !list) return;
  const alerts = activeAlerts();
  list.textContent = "";
  if (!alerts.length) {
    section.hidden = true;
    return;
  }
  section.hidden = false;
  for (const { row, watch } of alerts) {
    const li = document.createElement("li");
    const text = document.createElement("span");
    text.className = "alert-text";
    text.textContent = alertText(row, watch);
    const go = document.createElement("button");
    go.type = "button";
    go.className = "linklike";
    go.textContent = t("alert-go");
    go.addEventListener("click", () => select(row.cell_id, true));
    li.append(text, document.createTextNode(" "), go);
    list.appendChild(li);
  }
}

// Fire a browser notification once per under→over crossing this session. `firing` holds the keys
// currently over; a key newly over notifies (if enabled + permission granted), and a key that drops
// back under is cleared so a later re-crossing notifies again. Notifications never fire on load for
// watches that were already over more than once, and the body carries ONLY the place + reading +
// level — no personal data, no background push (which would need a hosted dependency the hard rules
// forbid). Wrapped: a missing/ë throwing Notifications API must never break the page.
function syncNotifications(alerts) {
  const overNow = new Set(alerts.map((a) => a.key));
  for (const key of firing) if (!overNow.has(key)) firing.delete(key); // dropped back under
  const canNotify =
    notifyOn &&
    "Notification" in window &&
    Notification.permission === "granted";
  for (const { key, row, watch } of alerts) {
    if (firing.has(key)) continue; // already firing — don't re-notify until it clears
    firing.add(key);
    if (!canNotify) continue;
    try {
      const body = t("notify-body")
        .replace("{reading}", watchReadingText(row))
        .replace("{threshold}", watchThresholdText(row.parameter, watch));
      new Notification(`swelter — ${placeName(row)}`, { body, tag: key, lang: document.documentElement.lang || "en" });
    } catch {
      /* Notifications API unavailable or blocked — the in-page banner still shows the alert */
    }
  }
}

// Re-evaluate alerts on every render: refresh the banner and fire any new crossings.
function updateAlerts() {
  const alerts = activeAlerts();
  renderAlerts();
  syncNotifications(alerts);
}

// The watch control in the detail panel: a level picker for the active measurement (a category
// <select> for PM2.5/exposure/heat index, a numeric <input> for temperature/PM10), a save/remove
// pair, and an optional "notify on this device" button. It reflects any saved watch for this
// location + measurement so a returning reader sees their setting. Graceful: the notify button hides
// when the Notifications API is absent, and nothing here throws.
function renderWatch(row) {
  const wrap = $("#watch");
  if (!wrap) return;
  const order = CATEGORY_ORDER[state.parameter];
  const sel = $("#watch-threshold");
  const num = $("#watch-number");
  const unit = $("#watch-unit");
  const key = watchKey(row.cell_id, state.parameter);
  const saved = loadWatches()[key] || null;

  if (order) {
    // Category measurements: "at [level] or worse", localized, best→worst.
    sel.hidden = false;
    num.hidden = true;
    sel.textContent = "";
    const localize =
      state.parameter === "exposure"
        ? localExposure
        : state.parameter === "heat_index_c"
          ? localHeat
          : localCategory;
    order.forEach((name, i) => {
      const opt = document.createElement("option");
      opt.value = String(i);
      opt.textContent = t("watch-at-or-worse").replace("{level}", localize(name));
      if (saved && saved.kind === "cat" && saved.idx === i) opt.selected = true;
      sel.appendChild(opt);
    });
    unit.textContent = "";
  } else {
    // Plain numbers: a value in the displayed unit; stored in base units.
    sel.hidden = true;
    num.hidden = false;
    if (saved && saved.kind === "num") num.value = String(round1(convert(saved.value)));
    else if (!num.value) num.value = String(round1(convert(row.mean)));
    unit.textContent = unitLabel();
  }

  $("#watch-clear").hidden = !saved;
  $("#watch-save").textContent = saved ? t("watch-update") : t("watch-save");

  // The notify button only makes sense where the API exists; hide it otherwise (graceful, F).
  const notifyBtn = $("#watch-notify");
  if ("Notification" in window) {
    notifyBtn.hidden = false;
    const granted = Notification.permission === "granted" && notifyOn;
    notifyBtn.textContent = granted ? t("watch-notify-on") : t("watch-notify");
    notifyBtn.disabled = Notification.permission === "denied";
  } else {
    notifyBtn.hidden = true;
  }
}

// Read the control into a stored watch. Category → an index; number → a base-unit value (un-convert
// the displayed value when the reader is on °F). Returns null on an empty/invalid number.
function readWatchControl() {
  const order = CATEGORY_ORDER[state.parameter];
  if (order) {
    const idx = Number($("#watch-threshold").value);
    return Number.isInteger(idx) && idx >= 0 ? { kind: "cat", idx } : null;
  }
  const shown = Number($("#watch-number").value);
  if (!Number.isFinite(shown)) return null;
  // Invert the display conversion so the stored value is always base units (Celsius for temp).
  let value = shown;
  if (PARAM_BASE_UNIT[state.parameter] === "C" && state.unit === "F") value = ((shown - 32) * 5) / 9;
  return { kind: "num", value };
}

function wireWatch() {
  const save = $("#watch-save");
  const clear = $("#watch-clear");
  const notify = $("#watch-notify");
  if (save)
    save.addEventListener("click", () => {
      if (!state.selected) return;
      const watch = readWatchControl();
      if (!watch) {
        $("#watch-status").textContent = t("watch-need-value");
        return;
      }
      const key = watchKey(state.selected, state.parameter);
      // A fresh/changed watch starts un-fired so an immediate crossing still notifies once.
      firing.delete(key);
      saveWatch(key, watch);
      $("#watch-status").textContent = t("watch-set");
      const row = current().find((r) => r.cell_id === state.selected);
      if (row) renderWatch(row);
      updateAlerts();
    });
  if (clear)
    clear.addEventListener("click", () => {
      if (!state.selected) return;
      const key = watchKey(state.selected, state.parameter);
      saveWatch(key, null);
      firing.delete(key);
      $("#watch-status").textContent = t("watch-removed");
      const row = current().find((r) => r.cell_id === state.selected);
      if (row) renderWatch(row);
      updateAlerts();
    });
  if (notify)
    notify.addEventListener("click", async () => {
      if (!("Notification" in window)) return;
      try {
        const perm =
          Notification.permission === "granted"
            ? "granted"
            : await Notification.requestPermission();
        notifyOn = perm === "granted";
        $("#watch-status").textContent = notifyOn ? t("notify-granted") : t("notify-blocked");
      } catch {
        $("#watch-status").textContent = t("notify-blocked");
      }
      const row = current().find((r) => r.cell_id === state.selected);
      if (row) renderWatch(row);
    });
}

// Multi-day history: group this location's readings for the active measurement by local calendar
// day and summarize each — high/low for a number, the worst category for AQI/exposure. The hourly
// sparkline shows within-a-day change; this shows the day-level pattern (which days ran hottest or
// dirtiest here) that a single snapshot can't. Uses whatever history is loaded; silent until there
// are at least two days to compare.
function dailyHistory(row) {
  const lang = document.documentElement.lang || "en";
  const fmtDay = (d) => {
    try {
      return new Intl.DateTimeFormat(lang, { weekday: "short", month: "short", day: "numeric" }).format(d);
    } catch {
      return d.toISOString().slice(0, 10);
    }
  };
  const byDay = new Map();
  for (const c of state.cells) {
    if (c.cell_id !== row.cell_id || c.parameter !== state.parameter) continue;
    const d = new Date(c.bucket);
    const key = `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
    let day = byDay.get(key);
    if (!day) {
      day = { t: d.getTime(), label: fmtDay(d), vals: [], cats: [] };
      byDay.set(key, day);
    }
    if (typeof c.mean === "number") day.vals.push(c.mean);
    if (c.category) day.cats.push(c.category);
  }
  return [...byDay.values()].sort((a, b) => a.t - b.t).slice(-7);
}

function renderHistory(row) {
  const wrap = $("#history");
  const list = $("#history-list");
  if (!wrap || !list) return;
  const days = dailyHistory(row);
  list.textContent = "";
  if (days.length < 2) {
    wrap.hidden = true; // a single day is already covered by the hourly sparkline
    return;
  }
  wrap.hidden = false;
  const categorical = state.parameter === "pm25_ugm3" || isExposure();
  const order = isExposure() ? EXP_ORDER : AQI_ORDER;
  const localize = isExposure() ? localExposure : localCategory;
  for (const day of days) {
    const li = document.createElement("li");
    if (categorical && day.cats.length) {
      const worst = day.cats.reduce((a, b) => (order.indexOf(b) > order.indexOf(a) ? b : a));
      li.textContent = t("history-worst").replace("{day}", day.label).replace("{cat}", localize(worst));
    } else if (day.vals.length) {
      const hi = round1(convert(Math.max(...day.vals)));
      const lo = round1(convert(Math.min(...day.vals)));
      li.textContent = t("history-highlow")
        .replace("{day}", day.label)
        .replace("{high}", hi)
        .replace("{low}", lo)
        .replace("{unit}", unitLabel());
    } else {
      continue;
    }
    list.appendChild(li);
  }
}

function renderDetail() {
  const panel = $("#detail");
  if (!state.selected) {
    panel.hidden = true;
    return;
  }
  const row = current().find((r) => r.cell_id === state.selected);
  if (!row) {
    panel.hidden = true;
    return;
  }
  panel.hidden = false;
  $("#detail-heading").textContent = placeName(row);
  $("#detail-body").textContent = describe(row);
  renderSpark(row);
  $("#detail-context").textContent = contrastLine(row);
  $("#detail-trend").textContent = trendLine(row);
  $("#detail-yesterday").textContent = dayChangeLine(row);
  renderHistory(row);
  // Guidance: EPA air for PM, NWS heat for the heat index, and the DOMINANT hazard for combined
  // exposure — so the advice matches whichever side is driving the level.
  let guidance = "";
  let heatSourced = false;
  if (state.parameter === "pm25_ugm3") {
    guidance = guidanceFor(row.category);
  } else if (state.parameter === "heat_index_c") {
    guidance = heatGuidanceFor(heatTier(row.mean));
    heatSourced = !!guidance;
  } else if (isExposure()) {
    heatSourced = (HEAT_LEVEL[row.heat_category] ?? 0) > (AIR_LEVEL[row.air_category] ?? 0);
    guidance = heatSourced ? heatGuidanceFor(row.heat_category) : guidanceFor(row.air_category);
  }
  $("#detail-guidance").textContent = guidance;
  const src = $(".guidance-source");
  src.textContent = heatSourced ? t("guide-source-heat") : t("guide-source");
  src.hidden = !guidance;
  renderActions(row);
  $("#provenance-body").textContent = provenanceText(row);
  renderCompare(row);
  renderWatch(row);
  renderDownload(row);
}

// Time-lapse: auto-advance the hour slider so you can watch heat build and air change across the
// network — the continuous time series a one-day snapshot can't show. User-started and pausable
// (WCAG 2.2.2), never autoplays; map transitions already honor prefers-reduced-motion.
let playTimer = null;

function isPlaying() {
  return playTimer !== null;
}

function syncPlay() {
  const b = $("#time-play");
  if (!b) return;
  if (state.buckets.length <= 1 && playTimer !== null) {
    clearInterval(playTimer);
    playTimer = null;
  }
  b.disabled = state.buckets.length <= 1;
  b.textContent = isPlaying() ? t("time-pause") : t("time-play");
  b.setAttribute("aria-pressed", String(isPlaying()));
}

function stopPlay() {
  if (playTimer !== null) {
    clearInterval(playTimer);
    playTimer = null;
  }
  syncPlay();
}

function startPlay() {
  if (state.buckets.length <= 1 || isPlaying()) return;
  playTimer = window.setInterval(() => {
    state.bucketIdx = (state.bucketIdx + 1) % state.buckets.length;
    const slider = $("#time-slider");
    if (slider) slider.value = String(state.bucketIdx);
    render();
  }, 1100);
  syncPlay();
}

function togglePlay() {
  if (isPlaying()) stopPlay();
  else startPlay();
}

function render() {
  const bucket = currentBucket();
  $("#time-readout").textContent = fmtBucket(bucket);
  const slider = $("#time-slider");
  if (slider) slider.setAttribute("aria-valuetext", fmtBucket(bucket));
  const rows = current();
  $("#status").textContent = t("status").replace("{n}", rows.length);
  renderHeadline();
  updateLegend();
  updateAlerts();
  renderSettingsState();
  renderOverview();
  renderList(rows);
  renderTable(rows);
  // The map (337 markers + a 2.6k-point SVG path) is the heaviest view; only rebuild it when it is
  // actually visible, otherwise mark it dirty and build lazily when the user opens the Map tab.
  if (mapVisible) renderMap(rows);
  else mapDirty = true;
  renderDetail();
  syncPlay();
}

// focusMap=true centers the map on the pick (a map marker tap, geolocation, or a search hit). A
// plain List/Table row click leaves the map where it is so browsing never yanks a hidden map around.
function select(cellId, focusMap = false) {
  if (cellId !== state.selected) $("#watch-status").textContent = ""; // a new pick clears stale feedback
  state.selected = cellId;
  // A shareable, bookmarkable deep link — the measurement, hour, and location together, something a
  // generic weather app's single regional view can't give.
  if (cellId) {
    savePref("cell", cellId); // remember it for the next visit
  }
  updateHash();
  render();
  if (focusMap) zoomToCell(cellId, true);
  const sel = document.querySelector(`[role="tabpanel"]:not([hidden]) [data-cell="${cellId}"]`);
  if (sel) sel.scrollIntoView({ block: "nearest" });
}

// The URL fragment carries the whole view a reader is looking at — measurement (p), hour (t, the
// bucket's ISO timestamp) and selected location (l) — so a shared or bookmarked link reopens that
// exact snapshot, not just the page. A reporter who copies the network summary gets a link that
// lands on the same measurement and hour they were reading. The legacy `#l=<cell>` form still parses.
const VALID_PARAMS = new Set(Object.keys(PARAM_I18N));

function parseHash() {
  const out = {};
  const raw = location.hash.replace(/^#/, "");
  for (const part of raw.split("&")) {
    const eq = part.indexOf("=");
    if (eq > 0) out[part.slice(0, eq)] = decodeURIComponent(part.slice(eq + 1));
  }
  return out;
}

function updateHash() {
  const parts = [`p=${encodeURIComponent(state.parameter)}`];
  const bucket = currentBucket();
  if (bucket) parts.push(`t=${encodeURIComponent(bucket)}`);
  if (state.selected) parts.push(`l=${encodeURIComponent(state.selected)}`);
  if (state.compareCell) parts.push(`c=${encodeURIComponent(state.compareCell)}`);
  // replaceState keeps the evolving view out of the back-button history.
  history.replaceState(null, "", `#${parts.join("&")}`);
}

// Apply a measurement from the hash (or the saved last view) before the first paint, so the page
// opens on the shared parameter. Bucket and selection wait for data and are applied in restoreView.
let pendingView = {};
function applyHashParameter() {
  pendingView = parseHash();
  if (VALID_PARAMS.has(pendingView.p)) {
    state.parameter = pendingView.p;
    const sel = $("#parameter-select");
    if (sel) sel.value = state.parameter;
  }
}

// Once data is in: land on the shared hour (if that timestamp is present) and the shared/last
// location. An explicit #l= wins; otherwise fall back to the location this browser last viewed.
function restoreView() {
  if (pendingView.t) {
    const idx = state.buckets.indexOf(pendingView.t);
    if (idx >= 0 && idx !== state.bucketIdx) {
      state.bucketIdx = idx;
      const slider = $("#time-slider");
      if (slider) slider.value = String(idx);
      render();
    }
  }
  if (!state.selected) {
    const id = pendingView.l || loadPrefs().cell;
    if (id && state.cells.some((c) => c.cell_id === id)) select(id, true);
  }
  // Restore a comparison partner: a shared #c= wins, else the one this browser last compared.
  if (!state.compareCell) {
    const partner = pendingView.c || loadPrefs().compare;
    if (partner && state.cells.some((c) => c.cell_id === partner)) {
      state.compareCell = partner;
      if (state.selected) renderDetail();
    }
  }
  updateHash(); // make the address bar reflect the resolved view, so the share link is correct
}

// -- saved settings (on-device transparency + control) -----------------------

// Plain statement of what swelter has stored in THIS browser right now — the community-owned, no-
// lock-in promise made checkable. localStorage only; nothing leaves the device.
function renderSettingsState() {
  const el = $("#settings-state");
  if (!el) return;
  const prefs = loadPrefs();
  const n = Object.keys(prefs.watches || {}).length;
  const has = Object.keys(prefs).some((k) => (k === "watches" ? n > 0 : prefs[k] != null));
  el.textContent = has
    ? t("settings-has").replace("{n}", String(n))
    : t("settings-empty");
}

// Forget everything stored on this device and return the UI to defaults, without writing anything
// back — so storage is genuinely empty until the reader makes a new choice. Language is left as it
// reads now (resetting it mid-visit would be jarring); it simply won't persist to the next visit.
function clearSettings() {
  try {
    localStorage.removeItem(PREFS_KEY);
  } catch {
    /* storage unavailable — nothing to clear */
  }
  state.compareCell = null;
  applyTextScale(0); // pure UI reset (does not persist)
  $("#display-status").textContent = "";
  state.contrast = false;
  document.documentElement.removeAttribute("data-contrast");
  $("#contrast-toggle")?.setAttribute("aria-pressed", "false");
  state.unit = "F";
  $("#unit-f")?.setAttribute("aria-pressed", "true");
  $("#unit-c")?.setAttribute("aria-pressed", "false");
  firing.clear(); // drop any armed alert-notification state
  render(); // alerts banner, watch control, and comparison all re-read the now-empty prefs
  renderSettingsState();
  $("#settings-status").textContent = t("settings-cleared");
}

// -- interaction -------------------------------------------------------------

function setView(tabId) {
  for (const tab of document.querySelectorAll('[role="tab"]')) {
    const selected = tab.id === tabId;
    tab.setAttribute("aria-selected", String(selected));
    tab.tabIndex = selected ? 0 : -1;
    const panel = document.getElementById(tab.getAttribute("aria-controls"));
    panel.hidden = !selected;
    if (selected) panel.focus();
  }
  mapVisible = tabId === "tab-map";
  if (mapVisible) {
    // The map is now measurable: build it if it went stale while hidden, then apply the current
    // view (or honor a focus chosen while it was hidden).
    requestAnimationFrame(() => {
      measureMap();
      if (mapDirty) {
        renderMap(current()); // builds the canvas, applies the transform, resolves pendingFocus
        mapDirty = false;
      } else if (state.pendingFocus) {
        const focus = state.pendingFocus;
        state.pendingFocus = null;
        zoomToCell(focus, false);
      } else {
        applyMapTransform(false);
      }
    });
  }
}

function wireTabs() {
  const tabs = [...document.querySelectorAll('[role="tab"]')];
  tabs.forEach((tab, i) => {
    tab.addEventListener("click", () => setView(tab.id));
    tab.addEventListener("keydown", (e) => {
      let next = null;
      if (e.key === "ArrowRight") next = tabs[(i + 1) % tabs.length];
      if (e.key === "ArrowLeft") next = tabs[(i - 1 + tabs.length) % tabs.length];
      if (e.key === "Home") next = tabs[0];
      if (e.key === "End") next = tabs[tabs.length - 1];
      if (next) {
        e.preventDefault();
        setView(next.id);
      }
    });
  });
}

function wireSort() {
  for (const button of document.querySelectorAll("th button[data-sort]")) {
    button.addEventListener("click", () => {
      const key = button.getAttribute("data-sort");
      state.sortDir = state.sortKey === key ? -state.sortDir : key === "value" ? -1 : 1;
      state.sortKey = key;
      for (const th of document.querySelectorAll("th[aria-sort]")) th.setAttribute("aria-sort", "none");
      const dir = state.sortDir === 1 ? "ascending" : "descending";
      button.closest("th").setAttribute("aria-sort", dir);
      render();
      $("#status").textContent = t("sort-announce")
        .replace("{col}", button.textContent)
        .replace("{dir}", t(`dir-${dir}`));
    });
  }
}

function setUnit(unit) {
  state.unit = unit;
  $("#unit-f").setAttribute("aria-pressed", String(unit === "F"));
  $("#unit-c").setAttribute("aria-pressed", String(unit === "C"));
  savePref("unit", unit);
  render();
}

// R6: in-page display controls — text size and high contrast — so a reader who needs larger type or
// stronger contrast gets it here, without hunting through browser or OS settings. Both choices
// persist (with units and language) and ride along to the other source view. The layout is rem-based
// and severity is never carried by color alone, so scaling the root font and swapping the colour
// tokens stays within the WCAG contract.
const TEXT_STEPS = [1, 1.15, 1.3];

function applyTextScale(step) {
  const i = Math.max(0, Math.min(TEXT_STEPS.length - 1, step));
  state.textStep = i;
  document.documentElement.style.setProperty("--text-scale", String(TEXT_STEPS[i]));
  const smaller = $("#text-smaller");
  const bigger = $("#text-bigger");
  if (smaller) smaller.disabled = i === 0;
  if (bigger) bigger.disabled = i === TEXT_STEPS.length - 1;
  const status = $("#display-status");
  if (status) {
    status.textContent = t("text-size-set")
      .replace("{n}", String(i + 1))
      .replace("{max}", String(TEXT_STEPS.length));
  }
}

function setTextStep(step) {
  applyTextScale(step);
  savePref("textStep", state.textStep);
}

function setContrast(on) {
  state.contrast = !!on;
  const root = document.documentElement;
  if (state.contrast) root.setAttribute("data-contrast", "high");
  else root.removeAttribute("data-contrast");
  const btn = $("#contrast-toggle");
  if (btn) btn.setAttribute("aria-pressed", String(state.contrast));
  savePref("contrast", state.contrast);
}

function locate() {
  if (!navigator.geolocation) {
    $("#status").textContent = t("locate-unavailable");
    return;
  }
  navigator.geolocation.getCurrentPosition(
    (pos) => {
      const rows = current();
      if (!rows.length) return;
      let best = null;
      let bestD = Infinity;
      for (const r of rows) {
        const d = haversine(pos.coords.latitude, pos.coords.longitude, r.lat, r.lon);
        if (d < bestD) {
          bestD = d;
          best = r;
        }
      }
      if (best) {
        state.search = "";
        $("#place-search").value = "";
        select(best.cell_id, true); // geolocation → center the map on the nearest location
        $("#status").textContent = t("locate-found").replace("{place}", placeName(best));
      }
    },
    () => {
      $("#status").textContent = t("locate-denied");
    },
  );
}

function haversine(lat1, lon1, lat2, lon2) {
  const r = (d) => (d * Math.PI) / 180;
  const dLat = r(lat2 - lat1);
  const dLon = r(lon2 - lon1);
  const a =
    Math.sin(dLat / 2) ** 2 + Math.cos(r(lat1)) * Math.cos(r(lat2)) * Math.sin(dLon / 2) ** 2;
  return 6371 * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

function wireControls() {
  $("#parameter-select").addEventListener("change", (e) => {
    state.parameter = e.target.value;
    updateHash();
    render();
  });
  $("#time-slider").addEventListener("input", (e) => {
    stopPlay(); // a manual scrub pauses the time-lapse
    state.bucketIdx = Number(e.target.value);
    updateHash();
    render();
  });
  $("#time-play").addEventListener("click", togglePlay);
  $("#lang-select").addEventListener("change", async (e) => {
    savePref("lang", e.target.value);
    await loadStrings(e.target.value);
    render();
  });
  $("#unit-f").addEventListener("click", () => setUnit("F"));
  $("#unit-c").addEventListener("click", () => setUnit("C"));
  $("#compare-select")?.addEventListener("change", (e) => {
    state.compareCell = e.target.value || null;
    savePref("compare", state.compareCell); // remember the comparison for next visit
    updateHash(); // a shared link reopens the comparison too
    const row = current().find((r) => r.cell_id === state.selected);
    if (row) renderCompare(row);
  });
  $("#text-smaller")?.addEventListener("click", () => setTextStep(state.textStep - 1));
  $("#text-bigger")?.addEventListener("click", () => setTextStep(state.textStep + 1));
  $("#contrast-toggle")?.addEventListener("click", () => setContrast(!state.contrast));
  $("#settings-clear")?.addEventListener("click", clearSettings);
  $("#settings")?.addEventListener("toggle", renderSettingsState); // refresh the count when opened
  $("#locate").addEventListener("click", locate);
  $("#place-search").addEventListener("input", (e) => {
    state.search = e.target.value;
    render();
  });
  const copy = $("#copy-link");
  if (copy)
    copy.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(location.href);
        $("#status").textContent = t("copy-done");
      } catch {
        $("#status").textContent = t("copy-fail");
      }
    });
  const summary = $("#copy-summary");
  if (summary)
    summary.addEventListener("click", async () => {
      const row = current().find((r) => r.cell_id === state.selected);
      if (!row) return;
      try {
        await navigator.clipboard.writeText(briefText(row));
        $("#status").textContent = t("brief-done");
      } catch {
        $("#status").textContent = t("copy-fail");
      }
    });
  const net = $("#copy-network");
  if (net)
    net.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(networkBriefText());
        $("#status").textContent = t("brief-network-done");
      } catch {
        $("#status").textContent = t("copy-fail");
      }
    });
}

function smallScreen() {
  return window.matchMedia("(max-width: 40rem)").matches;
}

// The live demo deploys two pages: "/" (Sacramento, Copernicus CAMS model data) and "/sensors/"
// (Stuttgart, real Sensor.Community low-cost sensors). Both share this file, so resolve the links
// relative to wherever we are and mark the active one — base-path agnostic (works under /swelter/).
function wireSourceSwitch() {
  const cams = $("#switch-cams");
  const sensors = $("#switch-sensors");
  if (!cams || !sensors) return;
  const onSensors = location.pathname.replace(/\/+$/, "").endsWith("/sensors");
  cams.setAttribute("href", onSensors ? "../" : "./");
  sensors.setAttribute("href", onSensors ? "./" : "sensors/");
  (onSensors ? sensors : cams).setAttribute("aria-current", "page");
}

async function init() {
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker
      .register("sw.js")
      .then((reg) => reg.update())
      .catch(() => {});
  }
  const prefs = loadPrefs();
  const startLang = prefs.lang === "es" ? "es" : "en"; // restore the reader's language
  await loadStrings(startLang);
  const langSel = $("#lang-select");
  if (langSel) langSel.value = startLang;
  if (prefs.unit === "C" || prefs.unit === "F") {
    state.unit = prefs.unit;
    $("#unit-f").setAttribute("aria-pressed", String(state.unit === "F"));
    $("#unit-c").setAttribute("aria-pressed", String(state.unit === "C"));
  }
  applyTextScale(Number(prefs.textStep) || 0); // restore saved text size (no status announce at boot)
  $("#display-status").textContent = "";
  setContrast(prefs.contrast === true);
  await loadBasemap();
  wireTabs();
  wireSort();
  wireControls();
  wireWatch();
  wireSourceSwitch();
  wireMap();
  // Phones/touch default to the List view; the map is the hardest view to operate (F17).
  setView(smallScreen() ? "tab-list" : "tab-list");

  // Fast first paint from a 1-hour snapshot, then enrich with history in the background (F16).
  const snapshot =
    (await fetchSurface("api/surface.json?hours=1")) || (await fetchSurface("sample-surface.json"));
  if (!snapshot) {
    $("#status").textContent = t("no-data");
    $("#time-slider").setAttribute("aria-disabled", "true");
    return;
  }
  applyHashParameter(); // open on the shared measurement before the first paint
  setData(snapshot);
  render();
  restoreView();

  loadHealth();

  const full = await fetchSurface("api/surface.json?hours=168");
  if (full) {
    state.historyLoaded = true;
    setData(full);
    render();
    restoreView();
  }
}

init();
