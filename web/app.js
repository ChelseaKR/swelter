// swelter dashboard logic — framework-free, with one pinned MessageFormat runtime dependency.
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
  wbgt_c: "C",
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
  wbgt_c: "param-wbgt",
  pm10_ugm3: "param-pm10",
};

// Parameters whose value is an *estimate*, not a direct or calibrated measurement — the caveat
// word must travel with every rendered value (R5), never live only in the legend or the label.
const ESTIMATED_PARAMS = new Set(["wbgt_c"]);

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
  interval: "hour",
  cellIndex: new Map(),
  seriesIndex: new Map(), // parameter + location -> chronologically ordered rows for linked history
  parameter: "pm25_ugm3",
  bucketIdx: 0,
  rangeStart: 0, // inclusive bucket index for the linked history window
  rangeEnd: 0, // inclusive bucket index for the linked history window
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
  areaAlerts: null, // the generated neighborhood-alerts feed (from /api/alerts.json or the baked copy)
  alertsXmlUrl: "", // resolved URL of the Atom feed, for the "copy feed link" subscribe button
  alertsLive: false, // did the feed come from the live API (so ?area= filtering works)?
  areaSelected: "", // the area_id the neighborhood-alerts panel is filtered to ("" = whole network)
  areaSelectKey: "", // signature of the area <select> contents, so it is rebuilt only when needed
  coolingCenters: null, // the curated cooling-center overlay dataset (validated FeatureCollection)
  coolingMeta: null, // the cooling-center dataset's provenance metadata
  coolingVisible: false, // is the cooling-center overlay drawn on the map?
  demo: null, // build-generated truth contract for a static deployment; absent on a live server
  attribution: "", // attribution from the surface currently driving every view
};

// Personal alert thresholds: on-device only (localStorage, like the other prefs), no account, no
// server, no PII — a watch holds only the public cell id, the parameter, and a level. While the page
// is open, a watched location whose current-hour reading meets/exceeds its level surfaces in the
// Alerts banner; if the reader has granted browser-notification permission and turned notifications
// on, an under→over crossing fires one notification. `firing` tracks which watch keys are currently
// over, so a notification fires once per crossing and never spams already-over watches on load.
const firing = new Set();
let notifyOn = false; // has the reader asked for on-device notifications this session?

// A statewide projection needs a deep camera range to reach neighborhood-scale readings without
// replacing the geography. The Sacramento demonstration footprint is about 1/250 of California's
// width, so a conventional 10–20x cap would make the overview cluster impossible to inspect.
const MAX_ZOOM = 512;
const reduceMotionMQL = window.matchMedia("(prefers-reduced-motion: reduce)");
let mapW = 0; // cached #map pixel size — measured on show/resize, never read per frame
let mapH = 0;
let markerFractions = new Map(); // cell_id → geographic {left, bottom} from the last renderMap
let mapVisible = false; // is the Map tab currently shown?
let mapDirty = true; // does the (lazy) map need a rebuild before it is shown?
let lastK = 1; // last zoom applied; cluster visibility changes only when this value changes
let mapDidDrag = false; // a pan/pinch moved past threshold → suppress the trailing marker click
let mapWasMultiTouch = false; // a 2-finger gesture happened → suppress a stray tap-select
let mapRafPending = false; // a transform write is already queued for the next frame
let mapRafAnimate = false;
let mapResizePending = false;
let mapClusterGroups = []; // overview cluster DOM + the camera zoom at which its members are legible
let mapPositionedElements = []; // marker/overlay DOM paired with fixed projected fractions
let mapProj = null; // the fixed projection currently shared by geography and reading positions
let mapLayoutW = 0; // dimensions/text scale used to build the current overview groups
let mapLayoutH = 0;
let mapLayoutTextStep = 0;

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

function activeLocale() {
  const locale = document.documentElement.lang;
  return typeof locale === "string" && locale ? locale : "en";
}

const messageFormatCache = new Map();

function messageFormatConstructor() {
  const MessageFormat = globalThis.SwelterMessageFormat;
  if (typeof MessageFormat !== "function") {
    throw new Error("MessageFormat 2 runtime is unavailable; run `npm run build:i18n`");
  }
  return MessageFormat;
}

function formatterFor(locale, source) {
  const cacheKey = `${locale}\u0000${source}`;
  if (!messageFormatCache.has(cacheKey)) {
    const MessageFormat = messageFormatConstructor();
    messageFormatCache.set(
      cacheKey,
      new MessageFormat(locale, source, { bidiIsolation: "default" }),
    );
  }
  return messageFormatCache.get(cacheKey);
}

function formatMessageSource(source, values = {}) {
  return String(formatterFor(activeLocale(), source).format(values));
}

function t(key, values = {}) {
  const source = state.strings[key] ?? I18N_DEFAULTS.get(key) ?? key;
  return formatMessageSource(source, values);
}

function validateMessageCatalog(locale, strings) {
  if (!strings || typeof strings !== "object" || Array.isArray(strings)) {
    throw new TypeError("message catalog must be an object");
  }
  for (const [key, source] of Object.entries(strings)) {
    if (typeof source !== "string" || !source.trim()) {
      throw new TypeError(`message ${key} must be a non-empty string`);
    }
    formatterFor(locale, source);
  }
}

function formatNumber(value, options = {}) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return String(value);
  try {
    return new Intl.NumberFormat(activeLocale(), options).format(numeric);
  } catch {
    return String(numeric);
  }
}

const RTL_LANGUAGES = new Set(["ar", "fa", "he", "ps", "ur"]);
function localeDirection(tag) {
  try {
    return RTL_LANGUAGES.has(new Intl.Locale(tag).language) ? "rtl" : "ltr";
  } catch {
    return "ltr";
  }
}

let stringRequestId = 0;

async function loadStrings(lang) {
  const requestId = ++stringRequestId;
  let strings;
  try {
    const res = await fetch(`i18n/${lang}.json`);
    if (!res.ok) throw new Error("missing");
    strings = await res.json();
    validateMessageCatalog(lang, strings);
  } catch {
    // Keep the last complete catalogue and its matching document language. A failed language swap
    // must never produce English fallback text inside a document still claiming Spanish (or vice versa).
    return false;
  }
  if (requestId !== stringRequestId) return false; // a newer selection already won the race
  state.strings = strings;
  document.documentElement.lang = lang;
  document.documentElement.dir = localeDirection(lang);
  for (const el of document.querySelectorAll("[data-i18n]")) {
    const key = el.getAttribute("data-i18n");
    el.textContent = t(key);
  }
  for (const el of document.querySelectorAll("[data-i18n-attr]")) {
    const [attr, key] = el.getAttribute("data-i18n-attr").split(":");
    if (state.strings[key]) el.setAttribute(attr, t(key));
  }
  return true;
}

// The Pages build replaces the template metadata with source-specific English and deliberately
// removes its runtime i18n attributes. Preserve that SEO truth on the first English paint, but once
// a resident chooses Spanish (including a saved preference), localize the visible browser title and
// description along with the rest of the document.
function localizedMetadataValue(key) {
  const sourceId = state.demo?.source?.id;
  const resolvedKey = sourceId && state.strings[`${key}-${sourceId}`] ? `${key}-${sourceId}` : key;
  return state.strings[resolvedKey] ? t(resolvedKey) : null;
}

function localizeDocumentMetadata() {
  // Never feed `t()`'s raw-key fallback into browser chrome. A failed catalogue request should
  // preserve the source-aware metadata generated by the Pages build, not replace it with a key.
  const title = localizedMetadataValue("document-title");
  if (title) document.title = title;
  const descriptionText = localizedMetadataValue("meta-description");
  const description = document.querySelector('meta[name="description"]');
  if (description && descriptionText) description.setAttribute("content", descriptionText);
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
  state.interval = doc.interval || "hour";
  state.attribution = doc.attribution || state.demo?.attribution || "";
  syncStaticParameters();
  indexCells();
  state.bucketIdx = Math.max(0, state.buckets.length - 1);
  resetHistoryRange();
  const slider = $("#time-slider");
  slider.max = String(Math.max(0, state.buckets.length - 1));
  slider.value = String(state.bucketIdx);
  slider.setAttribute("aria-disabled", state.buckets.length <= 1 ? "true" : "false");
  renderDemoContract();
}

const INTERVAL_MS = {
  minute: 60 * 1000,
  hour: 60 * 60 * 1000,
  day: 24 * 60 * 60 * 1000,
};

function intervalMilliseconds(interval = state.interval) {
  const normalized = String(interval || "hour").trim().toLowerCase();
  if (INTERVAL_MS[normalized]) return INTERVAL_MS[normalized];
  const match = normalized.match(/^(\d+(?:\.\d+)?)\s*(m|min|minute|h|hr|hour|d|day)s?$/);
  if (!match) return INTERVAL_MS.hour;
  const multiplier = match[2].startsWith("m")
    ? INTERVAL_MS.minute
    : match[2].startsWith("d")
      ? INTERVAL_MS.day
      : INTERVAL_MS.hour;
  return Number(match[1]) * multiplier;
}

function timestampMilliseconds(value) {
  const raw =
    typeof value === "string"
      ? value
      : value?.timestamp ?? value?.bucket ?? value?.row?.bucket ?? null;
  const parsed = raw == null ? NaN : new Date(raw).getTime();
  return Number.isFinite(parsed) ? parsed : null;
}

function expectedSlotsBetween(start, end, interval = state.interval) {
  const first = timestampMilliseconds(start);
  const last = timestampMilliseconds(end);
  const step = intervalMilliseconds(interval);
  if (first == null || last == null || last < first || !Number.isFinite(step) || step <= 0) return 0;
  return Math.floor((last - first + step * 0.01) / step) + 1;
}

function expectedSlotsInRange() {
  if (!state.buckets.length) return 0;
  return (
    expectedSlotsBetween(
      state.buckets[state.rangeStart],
      state.buckets[state.rangeEnd],
      state.interval,
    ) ||
    Math.max(0, state.rangeEnd - state.rangeStart + 1)
  );
}

// Start with the newest 24 published observations. Sparse feeds may therefore span more than 24
// hours; timestamp-aware segmenting and expected-slot counts below still expose every elapsed gap.
function resetHistoryRange() {
  const end = Math.max(0, state.buckets.length - 1);
  state.rangeEnd = end;
  state.rangeStart = Math.max(0, end - 23);
}

function isStaticDeployment() {
  return state.demo?.runtime === "static";
}

// A contract carries resident-facing facts in every shipped language. Keep source names, geography,
// and caveats out of an English-only build string while retaining English as a safe fallback.
function contractText(value) {
  if (typeof value === "string") return value;
  if (!value || typeof value !== "object") return "";
  const lang = document.documentElement.lang === "es" ? "es" : "en";
  return value[lang] || value.en || "";
}

function sourceTerm(key, fallbackKey, values = {}) {
  const source = contractText(state.demo?.source?.terminology?.[key]);
  return source ? formatMessageSource(source, values) : t(fallbackKey, values);
}

function appendContractLinks(el, links, { trailingSeparator = false } = {}) {
  const usable = Array.isArray(links) ? links : [];
  usable.forEach((link, i) => {
    if (i) el.append(document.createTextNode(" · "));
    const a = document.createElement("a");
    a.href = link.href;
    a.textContent = contractText(link.label);
    el.append(a);
  });
  if (trailingSeparator && usable.length) el.append(document.createTextNode(" · "));
}

// Render the source contract in a text-first card and repeat its reuse terms in the footer. Values
// are inserted with textContent/DOM nodes (never innerHTML), and every fact shown visually is in the
// same accessible reading order for screen-reader and keyboard users.
function renderDemoContract() {
  const contract = state.demo;
  const source = contract?.source;
  const attribution = source
    ? contractText(source.attribution)
    : state.attribution || contract?.attribution || "";
  const dataSource = $("#data-source");
  dataSource.textContent = attribution ? t("data-attribution", { attribution }) : "";
  if (!source) return;

  const truth = $("#dataset-truth");
  truth.hidden = false;
  $("#truth-source").textContent = contractText(source.name);
  $("#truth-geography").textContent = contractText(source.geography);
  $("#truth-status").textContent = contractText(source.calibration);

  const license = source.license || {};
  const licenseEl = $("#truth-license");
  licenseEl.replaceChildren(document.createTextNode(contractText(license.summary)));
  if (Array.isArray(license.links) && license.links.length) {
    licenseEl.append(document.createTextNode(" "));
    appendContractLinks(licenseEl, license.links);
  }

  const fallback = $("#truth-fallback");
  const fallbackMessage = contractText(contract.fallback?.message);
  fallback.textContent = fallbackMessage;
  fallback.hidden = !fallbackMessage;

  const tagline = $(".tagline");
  if (tagline) tagline.textContent = contractText(source.tagline);
  const activeSource = document.querySelector('.source-switch [aria-current="page"]');
  if (activeSource) activeSource.textContent = contractText(source.navigation_label);

  const licenseSummary = contractText(license.summary);
  $("#trust-summary").textContent = `${contractText(source.calibration)} ${t("trust-safety")}`;
  $("#method-calibration").textContent = contractText(source.calibration);
  $("#method-uncertainty").textContent = contractText(source.uncertainty);
  $("#method-location").textContent = contractText(source.location);
  $("#method-open").textContent = licenseSummary;
  $("#footer-data").textContent = licenseSummary;
  const footerLinks = $("#footer-license-links");
  footerLinks.replaceChildren();
  appendContractLinks(footerLinks, license.links, { trailingSeparator: true });
}

// The generated contract derives this list from the baked surface. Intersect it with the surface
// actually loaded before hiding controls, so even a corrupt/stale artifact cannot offer a measure
// with no rows. The live server remains dynamic and keeps its complete control set.
function syncStaticParameters() {
  if (!isStaticDeployment()) return;
  const declared = new Set(state.demo?.surface?.parameters || []);
  const present = new Set(state.cells.map((cell) => cell.parameter));
  const available = new Set(
    [...declared].filter((parameter) => present.has(parameter) && PARAM_I18N[parameter]),
  );
  const select = $("#parameter-select");
  for (const option of select.options) {
    const show = available.has(option.value);
    option.hidden = !show;
    option.disabled = !show;
  }
  if (!available.size || available.has(state.parameter)) return;
  state.parameter = available.has("pm25_ugm3") ? "pm25_ugm3" : [...available][0];
  select.value = state.parameter;
}

function indexCells() {
  const ids = [...new Set(state.cells.map((c) => c.cell_id))].sort();
  state.cellIndex = new Map(ids.map((id, i) => [id, i + 1]));
  const bucketOrder = new Map(state.buckets.map((bucket, i) => [bucket, i]));
  state.seriesIndex = new Map();
  for (const row of state.cells) {
    if (!isDisplayVariant(row, row.parameter)) continue;
    const key = `${row.parameter}\u0000${row.cell_id}`;
    if (!state.seriesIndex.has(key)) state.seriesIndex.set(key, []);
    state.seriesIndex.get(key).push(row);
  }
  for (const rows of state.seriesIndex.values()) {
    rows.sort((a, b) => (bucketOrder.get(a.bucket) ?? -1) - (bucketOrder.get(b.bucket) ?? -1));
  }
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
  const value = `${formatNumber(round1(convert(mean)), { maximumFractionDigits: 1 })} ${unitLabel()}`;
  // The "estimated" caveat is glued to the value itself, not left to the label or the legend
  // (R5) — it survives copy-paste into a brief, an alert line, or a table cell.
  return ESTIMATED_PARAMS.has(state.parameter) ? t("estimated-value", { value }) : value;
}

function fmtUncertainty(u) {
  if (u == null) return "";
  const scaled = PARAM_BASE_UNIT[state.parameter] === "C" && state.unit === "F" ? (u * 9) / 5 : u;
  return ` ± ${formatNumber(round1(scaled), { maximumFractionDigits: 1 })}`;
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

// A cell is provisional for one of two reasons a resident must be able to tell apart: it is only
// *uncalibrated* (an early reading, no reference fit yet), or it is *flagged* — automatic quality
// control judged the value suspicious (a spike or a flatline) and it is shown provisional instead of
// dropped, so a smoke front is never blanked off the map (ADR 0029). `qc_flags` is the array of
// suspicious verdicts the surface carries; empty or absent means not flagged.
function qcFlagged(row) {
  return Array.isArray(row.qc_flags) && row.qc_flags.length > 0;
}

// The short status word glued to a provisional reading so the caveat travels with the value (R5)
// and never lives only in the legend: "flagged" wording when QC marked it suspicious, else the plain
// provisional wording.
function provisionalTag(row) {
  return qcFlagged(row) ? t("state-flagged") : t("state-provisional");
}

function describe(row) {
  const place = placeName(row);
  if (isExposure()) {
    const comp = row.compound ? ` — ${t("exp-compound")}` : "";
    const ctx = [];
    if (row.heat_category) ctx.push(`${t("exp-heat")}: ${localHeat(row.heat_category)}`);
    if (row.air_category) ctx.push(`${t("exp-air")}: ${localCategory(row.air_category)}`);
    const detail = ctx.length ? ` (${ctx.join(", ")})` : "";
    const prov = row.provisional ? ` (${provisionalTag(row)})` : "";
    return `${place}: ${exposureReading(row)}${comp}${detail}${prov}`;
  }
  if (state.parameter === "pm25_ugm3") {
    const aqiNumber = formatNumber(row.aqi, { maximumFractionDigits: 0 });
    const aqi = row.provisional ? `~AQI ${aqiNumber}` : `AQI ${aqiNumber}`;
    // Provisional cells never assert a named category as fact (F4).
    const cat = row.provisional ? ` (${provisionalTag(row)})` : `, ${localCategory(row.category)}`;
    return `${place}: ${aqi}${cat}, ${formatNumber(Math.round(row.mean))} µg/m³`;
  }
  const prov = row.provisional ? ` (${provisionalTag(row)})` : "";
  return `${place}: ${fmtValue(row.mean)}${fmtUncertainty(row.uncertainty)}${prov}`;
}

// The reading part of `describe(row)`, with the leading "place: " stripped by prefix length —
// not by splitting on ": ", which breaks when the place name/label itself contains ": " (e.g. a
// host-chosen label like "Ward 3: Uptown"): a naive split matches every ": " in the string, not
// just the one separating place from reading, and leaks part of the label into the "reading" text.
function readingText(row) {
  const prefix = `${placeName(row)}: `;
  const full = describe(row);
  return full.startsWith(prefix) ? full.slice(prefix.length) : full;
}

// Stable, locale-aware evidence that Map/List/Table were rendered from the same complete record.
// Browser conformance tests compare this key across representations and separately compare visible
// labels/readings. Keeping the raw fields here catches a view that silently drops uncertainty,
// provisional state, time, or category even when its human-readable layout is intentionally different.
function representationKey(row) {
  return JSON.stringify({
    ...row,
    label: placeName(row),
    description: describe(row),
  });
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
    parts.push(sourceTerm("non_provisional_explanation", "prov-confirmed"));
    if (!isExposure() && row.uncertainty != null) {
      const u =
        PARAM_BASE_UNIT[state.parameter] === "C" && state.unit === "F"
          ? (row.uncertainty * 9) / 5
          : row.uncertainty;
      parts.push(t("prov-uncertainty", {
        u: formatNumber(round1(u), { maximumFractionDigits: 1 }),
        unit: unitLabel(),
      }));
    } else if (!isExposure() && row.uncertainty_note) {
      // Confirmed, but with no error bar: say why instead of saying nothing, so a missing number
      // is never read as "nothing to report" (ADR 0035, invariant 4).
      parts.push(row.uncertainty_note);
    }
    if (row.method && row.reference) {
      parts.push(t("prov-method", { method: row.method, reference: row.reference }));
    }
  }
  if (isExposure()) parts.push(t("prov-derived"));
  parts.push(t("prov-readings", { n: row.n }));
  return parts.join(" ");
}

// Structured "show your work" panel: the same lineage facts as provenanceText(), but as labeled
// rows (verdict, calibration state, uncertainty, method, reference monitor, readings) instead of
// one joined sentence, so the trust layer reads as a first-class dashboard panel, not a footnote.
function renderProvenance(row) {
  const dl = $("#provenance-body");
  dl.textContent = "";
  const addRow = (labelKey, value, lang = null) => {
    const dt = document.createElement("dt");
    dt.textContent = t(labelKey);
    const dd = document.createElement("dd");
    dd.textContent = value;
    if (lang) dd.lang = lang;
    dl.appendChild(dt);
    dl.appendChild(dd);
  };

  addRow(
    "prov-verdict-label",
    row.provisional
      ? t("prov-verdict-provisional")
      : sourceTerm("non_provisional_label", "prov-verdict-confirmed"),
  );

  // A provisional cell that is *flagged* gets an extra, plain-language row so a resident sees why it
  // is provisional (QC judged it suspicious) rather than only that it is (ADR 0029, invariant 4).
  if (qcFlagged(row)) {
    addRow("prov-qc-label", t("qc-flagged-note"));
  }

  if (!row.provisional) {
    if (!isExposure() && row.uncertainty != null) {
      const u =
        PARAM_BASE_UNIT[state.parameter] === "C" && state.unit === "F"
          ? (row.uncertainty * 9) / 5
          : row.uncertainty;
      addRow(
        "prov-uncertainty-label",
        t("prov-uncertainty", {
          u: formatNumber(round1(u), { maximumFractionDigits: 1 }),
          unit: unitLabel(),
        }),
      );
    } else if (!isExposure() && row.uncertainty_note) {
      // Same rule as provenanceText(): a confirmed cell with no number states its reason.
      addRow("prov-uncertainty-label", row.uncertainty_note, "en");
    }
    if (row.method && row.reference) {
      addRow("prov-calibration-label", row.method);
      addRow("prov-reference-label", row.reference);
    }
  }
  if (isExposure()) {
    addRow("prov-derived-label", t("prov-derived"));
    if (row.uncertainty_note) {
      addRow("prov-uncertainty-label", row.uncertainty_note, "en");
    }
  }
  addRow("prov-readings-label", formatNumber(row.n));
}

// A ready-to-paste, plain-language summary of this location: the reading, how it compares, the
// trend, its calibration state, an open-data attribution, and the shareable link. Closes the
// data-to-action gap — something an advocate can drop into an email, a flyer, or testimony.
function briefSourceText() {
  const source = state.demo?.source;
  if (!source) return t("brief-source");
  const attribution = t("data-attribution", { attribution: contractText(source.attribution) });
  return `${attribution} ${contractText(source.license?.summary)}`;
}

function briefText(row) {
  const lines = [`${placeName(row)} — ${fmtBucket(currentBucket())}`];
  lines.push(readingText(row));
  const c = contrastLine(row);
  if (c) lines.push(c);
  const tr = trendLine(row);
  if (tr) lines.push(tr);
  lines.push(provenanceText(row));
  lines.push(briefSourceText());
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
    t("brief-network-title", { param, time: fmtBucket(currentBucket()) }),
    $("#overview-counts").textContent,
    $("#overview-coverage").textContent,
    $("#overview-health").textContent,
    $("#overview-spread").textContent,
    $("#overview-worst").textContent,
    $("#overview-fresh").textContent,
    briefSourceText(),
    location.href,
  ];
  return lines.filter((line) => line && line.trim()).join("\n");
}

// A download link to the source-licensed readings behind a location, filtered to one of its nodes.
// Served by `swelter serve`; the node id is the only identifier and is already public in the API.
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

// -- share card (caveat baked into the pixels, not overlaid HTML) -----------
//
// E11: a screenshot of the page can be cropped to just the number. This draws a self-contained
// PNG instead — the reading, the measurement + hour, the "hourly mean, not 24-hour average"
// window caveat, and (when the cell is unconfirmed) a visible provisional band — all rendered as
// canvas pixels, so the context travels with the image no matter how it's cropped or shared
// (ADR 0016). It reuses the same reading text the list/detail view already shows (`describe`), so
// the exported number always matches the screen.

const SHARE_CARD_WIDTH = 1000;
const SHARE_CARD_HEIGHT = 620;

// The reading part of `describe(row)`, with the leading "place: " stripped — the same
// `readingText` helper `briefText` already uses to separate place from reading.
function shareCardReading(row) {
  return readingText(row);
}

// Simple greedy word-wrap for the canvas 2D text API, which has no native wrapping. Returns the
// y coordinate just past the last line drawn, so callers can stack the next block beneath it.
function wrapCanvasText(ctx, text, x, y, maxWidth, lineHeight) {
  const words = text.split(" ");
  let line = "";
  let cy = y;
  for (const word of words) {
    const test = line ? `${line} ${word}` : word;
    if (line && ctx.measureText(test).width > maxWidth) {
      ctx.fillText(line, x, cy);
      line = word;
      cy += lineHeight;
    } else {
      line = test;
    }
  }
  if (line) ctx.fillText(line, x, cy);
  return cy + lineHeight;
}

// Draws the currently selected location to an offscreen canvas. Always light-on-white regardless
// of the page's theme/contrast setting, since the image is meant to stand alone once shared.
function buildShareCanvas(row) {
  const canvas = document.createElement("canvas");
  canvas.width = SHARE_CARD_WIDTH;
  canvas.height = SHARE_CARD_HEIGHT;
  const ctx = canvas.getContext("2d");
  const pad = 56;
  const textWidth = canvas.width - pad * 2;

  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  ctx.fillStyle = "#0f172a";
  ctx.font = "600 22px system-ui, -apple-system, sans-serif";
  ctx.fillText("swelter", pad, pad);

  let y = pad + 72;
  ctx.font = "700 44px system-ui, -apple-system, sans-serif";
  ctx.fillStyle = "#0f172a";
  y = wrapCanvasText(ctx, placeName(row), pad, y, textWidth, 50);

  y += 12;
  ctx.font = "400 22px system-ui, -apple-system, sans-serif";
  ctx.fillStyle = "#475569";
  const paramLabel = t(PARAM_I18N[state.parameter] || "parameter");
  ctx.fillText(`${paramLabel} — ${fmtBucket(currentBucket())}`, pad, y);

  y += 58;
  ctx.font = "700 52px system-ui, -apple-system, sans-serif";
  ctx.fillStyle = "#0f172a";
  y = wrapCanvasText(ctx, shareCardReading(row), pad, y, textWidth, 58);

  y += 20;
  ctx.font = "italic 400 20px system-ui, -apple-system, sans-serif";
  ctx.fillStyle = "#475569";
  y = wrapCanvasText(ctx, t("share-card-window"), pad, y, textWidth, 26);

  // The provisional band: baked into the image, same "~" convention as the on-page reading, so a
  // cropped screenshot still carries the "not yet calibrated" context (F4).
  if (row.provisional) {
    y += 16;
    const bandX = pad - 16;
    const bandWidth = canvas.width - bandX * 2;
    const bandHeight = 60;
    ctx.fillStyle = "#fef3c7";
    ctx.fillRect(bandX, y, bandWidth, bandHeight);
    ctx.strokeStyle = "#b45309";
    ctx.lineWidth = 2;
    ctx.strokeRect(bandX, y, bandWidth, bandHeight);
    ctx.fillStyle = "#92400e";
    ctx.font = "700 22px system-ui, -apple-system, sans-serif";
    ctx.fillText(`~ ${t("share-card-provisional")}`, pad, y + bandHeight / 2 + 7);
  }

  ctx.font = "400 16px system-ui, -apple-system, sans-serif";
  ctx.fillStyle = "#64748b";
  ctx.fillText(t("brief-source"), pad, canvas.height - pad + 8);

  return canvas;
}

// Triggers a PNG download of the share card — the same object-URL + temporary `<a download>`
// pattern the rest of the app uses for exports, revoked once the click has fired.
function saveShareCard(row) {
  const canvas = buildShareCanvas(row);
  canvas.toBlob((blob) => {
    if (!blob) {
      $("#status").textContent = t("share-card-fail");
      return;
    }
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    const slug = placeName(row).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
    a.download = `swelter-${slug || "location"}.png`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    $("#status").textContent = t("share-card-done");
  }, "image/png");
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
    const heatLevel = HEAT_LEVEL[row.heat_category] ?? 0;
    const airLevel = AIR_LEVEL[row.air_category] ?? 0;
    const joint = row.compound || (heatLevel === airLevel && heatLevel >= 2);
    if (joint) {
      keys = [
        ...(HEAT_ACTIONS[row.heat_category] || []),
        ...(AIR_ACTIONS[row.air_category] || []),
      ];
      keys = [...new Set(keys)];
      if (!keys.length) keys = null;
    } else {
      keys =
        heatLevel > airLevel
          ? HEAT_ACTIONS[row.heat_category] || null
          : AIR_ACTIONS[row.air_category] || null;
    }
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

// PM2.5 payloads can carry both the documented hourly-mean view and a NowCast for the same place
// and timestamp. The dashboard's legend and guidance explicitly describe the hourly mean, so every
// linked representation selects that variant and never double-counts a location. Older payloads
// without `aqi_window` remain compatible.
function isDisplayVariant(row, parameter = state.parameter) {
  return parameter !== "pm25_ugm3" || !row.aqi_window || row.aqi_window === "hourly-mean";
}

function currentBucket() {
  return state.buckets[state.bucketIdx];
}

const CURRENT_OBSERVATION_MAX_AGE_MINUTES = 180;

function latestBucket() {
  return state.buckets[state.buckets.length - 1] || null;
}

function observationAgeMinutes(bucket) {
  const time = timestampMilliseconds(bucket);
  return time == null ? Infinity : Math.max(0, (Date.now() - time) / INTERVAL_MS.minute);
}

function isLatestBucket(bucket = currentBucket()) {
  return Boolean(bucket) && bucket === latestBucket();
}

function isFreshObservation(bucket = currentBucket()) {
  return isLatestBucket(bucket) && observationAgeMinutes(bucket) <= CURRENT_OBSERVATION_MAX_AGE_MINUTES;
}

function temporalContextText(bucket = currentBucket()) {
  if (!bucket) return "";
  if (!isLatestBucket(bucket)) {
    return t("observation-historical", { time: fmtBucket(bucket) });
  }
  if (!isFreshObservation(bucket)) {
    return t("observation-stale", { time: fmtBucket(bucket) });
  }
  return "";
}

function current() {
  const bucket = currentBucket();
  let rows = state.cells.filter(
    (c) =>
      c.parameter === state.parameter && c.bucket === bucket && isDisplayVariant(c, state.parameter),
  );
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
  return state.cells.filter(
    (c) => c.parameter === "pm25_ugm3" && c.bucket === bucket && isDisplayVariant(c, "pm25_ugm3"),
  );
}

// Every location reporting the active parameter in the selected hour — the network-wide peer set a
// generic weather app can't show, because it has one regional value, not a map of them.
function peersNow(row) {
  return state.cells.filter(
    (c) =>
      c.parameter === state.parameter &&
      c.bucket === row.bucket &&
      isDisplayVariant(c, state.parameter),
  );
}

// "How does my block compare right now?" — the urban-heat-island / air-inequity signal a regional
// weather app can't give. Reported as an honest, tie-safe count (how many locations are worse) plus
// the gap from the network median — never a percentile, which ties would overstate.
function contrastLine(row) {
  // Calibration-state cohorts are never mixed in a rank/median. A provisional location compares
  // only with provisional peers and the resulting sentence is explicitly marked rough.
  const peers = peersNow(row).filter((peer) => Boolean(peer.provisional) === Boolean(row.provisional));
  if (peers.length < 3) return ""; // not meaningful with only a couple of locations
  const vals = peers.map((p) => p.mean);
  const higher = vals.filter((v) => v > row.mean).length; // strictly worse/hotter than this one
  const heatLike = state.parameter === "temp_c" || state.parameter === "heat_index_c";
  let text;
  if (higher === 0) {
    text = t(heatLike ? "context-top-hot" : "context-top-bad");
  } else {
    text = t(heatLike ? "context-rank-hot" : "context-rank-bad", {
      n: formatNumber(higher),
      total: formatNumber(peers.length),
    });
  }
  if (!isExposure()) {
    const sorted = [...vals].sort((a, b) => a - b);
    const n = sorted.length;
    const median = n % 2 ? sorted[(n - 1) / 2] : (sorted[n / 2 - 1] + sorted[n / 2]) / 2;
    const d = round1(convert(row.mean) - convert(median));
    if (Math.abs(d) >= 0.1) {
      text +=
        " " +
        t("context-median", {
          delta: formatDifference(d),
          unit: "",
          dir: d > 0 ? t("context-above") : t("context-below"),
        });
    }
  }
  return row.provisional ? `${text} ${t("compare-provisional")}` : text;
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
    if (
      c.cell_id !== row.cell_id ||
      c.parameter !== state.parameter ||
      !isDisplayVariant(c, state.parameter)
    )
      continue;
    const d = Math.abs(new Date(c.bucket).getTime() - target);
    if (d < bestD) {
      bestD = d;
      best = c;
    }
  }
  if (!best || bestD > 90 * 60 * 1000) return ""; // no comparable reading ~24 h ago
  if (Boolean(best.provisional) !== Boolean(row.provisional)) return "";
  let line;
  if (state.parameter === "pm25_ugm3" || isExposure()) {
    const order = isExposure() ? EXP_ORDER : AQI_ORDER;
    const cmp = order.indexOf(row.category) - order.indexOf(best.category);
    line = t(cmp > 0 ? "yesterday-worse" : cmp < 0 ? "yesterday-better" : "yesterday-same");
  } else {
    const d = round1(convert(row.mean) - convert(best.mean));
    line =
      Math.abs(d) < 0.1
        ? t("yesterday-same")
        : t(d > 0 ? "yesterday-higher" : "yesterday-lower", {
            d: formatDifference(d),
            unit: "",
          });
  }
  return row.provisional ? `${line} ${t("compare-provisional")}` : line;
}

// Per-parameter "steady" band, so small wiggles don't read as a trend.
const TREND_EPS = {
  exposure: 0.5,
  temp_c: 0.5,
  heat_index_c: 0.5,
  wbgt_c: 0.5,
  pm25_ugm3: 1,
  pm10_ugm3: 2,
  no2_ppb: 2,
};

// "Is it getting worse or clearing on my block?" — direction over the last few hours, from the same
// time series the slider reads. Needs the loaded history; silent until it's there.
function trendLine(row) {
  if (!state.historyLoaded || state.bucketIdx < 1) return "";
  const back = Math.min(3, state.bucketIdx);
  const past = state.buckets[state.bucketIdx - back];
  const prev = state.cells.find(
    (c) =>
      c.cell_id === row.cell_id &&
      c.parameter === state.parameter &&
      c.bucket === past &&
      isDisplayVariant(c, state.parameter),
  );
  if (!prev) return "";
  if (Boolean(prev.provisional) !== Boolean(row.provisional)) return "";
  const d = row.mean - prev.mean;
  const eps = TREND_EPS[state.parameter] ?? 0.5;
  const key = d > eps ? "trend-rising" : d < -eps ? "trend-falling" : "trend-steady";
  const arrow = d > eps ? "↑" : d < -eps ? "↓" : "→";
  const rowTime = timestampMilliseconds(row.bucket);
  const previousTime = timestampMilliseconds(prev.bucket);
  const elapsedHours =
    rowTime != null && previousTime != null
      ? Math.max(1, Math.round(Math.abs(rowTime - previousTime) / INTERVAL_MS.hour))
      : back;
  const line = `${arrow} ${t(key, { h: formatNumber(elapsedHours) })}`;
  return row.provisional ? `${line} ${t("compare-provisional")}` : line;
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
  // No color band: guidance thresholds for estimated WBGT are SME-gated (ADR 0012), so it gets
  // its own "shown by value" block with its own caveat text, not the generic pollutant one.
  wbgt_c: "wbgt",
};
const LEGEND_TITLE = {
  pm25_ugm3: "legend-title-pm25",
  temp_c: "legend-title-temp",
  heat_index_c: "legend-title-hi",
  exposure: "legend-title-exposure",
  pm10_ugm3: "legend-title-pm10",
  no2_ppb: "legend-title-no2",
  wbgt_c: "legend-title-wbgt",
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
  const temporalContext = temporalContextText(currentBucket());
  if (!confirmed.length) {
    el.textContent = [temporalContext, sourceTerm("headline_none", "headline-none")]
      .filter(Boolean)
      .join(" ");
    return;
  }
  const worst = confirmed.reduce((a, b) => (b.aqi > a.aqi ? b : a));
  const lead = sourceTerm("headline_worst", "headline-worst", {
    place: placeName(worst),
    aqi: formatNumber(worst.aqi, { maximumFractionDigits: 0 }),
    category: localCategory(worst.category),
    level: localCategory(worst.category),
  });
  el.textContent = [
    temporalContext,
    lead,
    temporalContext ? t("guidance-associated") : "",
    guidanceFor(worst.category),
  ]
    .filter(Boolean)
    .join(" ");
}

// Every location reporting the active parameter this hour — the network, not the search-filtered view.
function overviewRows() {
  const bucket = currentBucket();
  return state.cells.filter(
    (c) =>
      c.parameter === state.parameter && c.bucket === bucket && isDisplayVariant(c, state.parameter),
  );
}

// -- linked observatory ------------------------------------------------------

// A chart magnitude is explicit about its parameter and unit so the Now card and linked views can
// compare rows without temporarily mutating global state. Exposure remains ordinal; every other
// measure uses the published mean, converted only for the resident's display preference.
function magnitudeFor(row, parameter = state.parameter, unit = state.unit) {
  if (!row) return NaN;
  if (parameter === "exposure") {
    const level = EXP_ORDER.indexOf(row.category);
    return level >= 0 ? level : Number(row.mean);
  }
  const value = Number(row.mean);
  if (!Number.isFinite(value)) return NaN;
  return PARAM_BASE_UNIT[parameter] === "C" && unit === "F" ? (value * 9) / 5 + 32 : value;
}

function magnitudeUncertainty(row, parameter = state.parameter, unit = state.unit) {
  if (!row || row.provisional || row.uncertainty == null || parameter === "exposure") return null;
  const value = Number(row.uncertainty);
  if (!Number.isFinite(value) || value < 0) return null;
  return PARAM_BASE_UNIT[parameter] === "C" && unit === "F" ? (value * 9) / 5 : value;
}

function formatMagnitude(value) {
  if (state.parameter === "exposure") {
    const i = Math.max(0, Math.min(EXP_ORDER.length - 1, Math.round(value)));
    return localExposure(EXP_ORDER[i]);
  }
  const formatted = `${round1(value)} ${unitLabel()}`;
  return ESTIMATED_PARAMS.has(state.parameter)
    ? t("estimated-value", { value: formatted })
    : formatted;
}

function formatDifference(value) {
  return formatMagnitude(Math.abs(value));
}

function unitContextLabel() {
  return ESTIMATED_PARAMS.has(state.parameter)
    ? `${unitLabel()} · ${t("estimated-short")}`
    : unitLabel();
}

function focusRow(rows) {
  const network = overviewRows();
  if (state.selected) return network.find((row) => row.cell_id === state.selected) || null;
  const candidates = state.search ? rows : network;
  if (!candidates.length) return null;
  return candidates.reduce((worst, row) =>
    magnitudeFor(row) > magnitudeFor(worst) ? row : worst,
  );
}

function referenceRowFor(cellId) {
  const series = state.seriesIndex.get(`${state.parameter}\u0000${cellId}`) || [];
  return series[series.length - 1] || null;
}

function selectedGapText(row) {
  const reading = t("now-no-reading", { time: fmtBucket(currentBucket()) });
  return row ? `${placeName(row)} — ${reading} ${t("now-gap")}` : `${reading} ${t("now-gap")}`;
}

function guidanceForRow(row) {
  if (!row) return "";
  if (state.parameter === "pm25_ugm3") return guidanceFor(row.category);
  if (state.parameter === "heat_index_c") return heatGuidanceFor(heatTier(row.mean));
  if (isExposure()) {
    const heatLevel = HEAT_LEVEL[row.heat_category] ?? 0;
    const airLevel = AIR_LEVEL[row.air_category] ?? 0;
    const joint = row.compound || (heatLevel === airLevel && heatLevel >= 2);
    if (joint) {
      return [...new Set([heatGuidanceFor(row.heat_category), guidanceFor(row.air_category)])]
        .filter(Boolean)
        .join(" ");
    }
    return heatLevel > airLevel
      ? heatGuidanceFor(row.heat_category)
      : guidanceFor(row.air_category);
  }
  return "";
}

function guidanceSourceForRow(row) {
  if (!row) return "";
  if (state.parameter === "heat_index_c") return t("guide-source-heat");
  if (state.parameter === "pm25_ugm3") return t("guide-source");
  if (isExposure()) {
    const heatLevel = HEAT_LEVEL[row.heat_category] ?? 0;
    const airLevel = AIR_LEVEL[row.air_category] ?? 0;
    if (row.compound || (heatLevel === airLevel && heatLevel >= 2)) return t("guide-source-both");
    return heatLevel > airLevel ? t("guide-source-heat") : t("guide-source");
  }
  return "";
}

function renderNow(rows) {
  const row = focusRow(rows);
  const card = $(".now-primary");
  const open = $("#now-open-evidence");
  const missingSelected =
    !row && state.selected
      ? referenceRowFor(state.selected) || state.cells.find((cell) => cell.cell_id === state.selected)
      : null;
  if (missingSelected) {
    $("#now-mode").textContent = t("now-selected-focus");
    $("#now-place").textContent = placeName(missingSelected);
    $("#now-reading").textContent = t("now-no-reading", { time: fmtBucket(currentBucket()) });
    $("#now-trust").textContent = t("now-no-current");
    $("#now-freshness").textContent = fmtBucket(currentBucket());
    if (card) card.removeAttribute("data-provisional");
    if (card) card.removeAttribute("data-flagged");
    if (open) open.setAttribute("data-cell", state.selected);
    return missingSelected;
  }
  if (!row) {
    $("#now-mode").textContent = t(state.search ? "now-search-focus" : "now-network-focus");
    $("#now-place").textContent = "—";
    $("#now-reading").textContent = t(state.search ? "now-search-empty" : "now-empty");
    $("#now-trust").textContent = "—";
    $("#now-freshness").textContent = "—";
    if (card) card.removeAttribute("data-provisional");
    if (card) card.removeAttribute("data-flagged");
    if (open) open.removeAttribute("data-cell");
    return null;
  }

  const isSelected = row.cell_id === state.selected;
  $("#now-mode").textContent = t(
    isSelected ? "now-selected-focus" : state.search ? "now-search-focus" : "now-network-focus",
  );
  $("#now-place").textContent = placeName(row);
  $("#now-reading").textContent = readingText(row);
  $("#now-trust").textContent = row.provisional
    ? provisionalTag(row)
    : sourceTerm("non_provisional_label", "state-calibrated");
  $("#now-freshness").textContent = `${fmtBucket(row.bucket)} · ${ageText(row.bucket)}`;
  if (card) card.setAttribute("data-provisional", String(row.provisional));
  if (card) card.setAttribute("data-flagged", String(qcFlagged(row)));
  if (open) open.setAttribute("data-cell", row.cell_id);
  return row;
}

function clampIndex(value, max) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return 0;
  return Math.max(0, Math.min(Math.max(0, max), Math.round(parsed)));
}

// Keep two native range controls from crossing. The edge being manipulated wins, which makes the
// behavior predictable for keyboard users as well as pointer users.
function normalizeHistoryRange(start, end, max, changed = "end") {
  let first = clampIndex(start, max);
  let last = clampIndex(end, max);
  if (first > last) {
    if (changed === "start") last = first;
    else first = last;
  }
  return [first, last];
}

function includeBucketInRange(index) {
  const max = Math.max(0, state.buckets.length - 1);
  const width = Math.max(0, state.rangeEnd - state.rangeStart);
  if (index < state.rangeStart) {
    state.rangeStart = index;
    state.rangeEnd = Math.min(max, index + width);
  } else if (index > state.rangeEnd) {
    state.rangeEnd = index;
    state.rangeStart = Math.max(0, index - width);
  }
}

function setBucketIndex(index, { pause = false } = {}) {
  if (!state.buckets.length) return;
  if (pause) stopPlay();
  state.bucketIdx = clampIndex(index, state.buckets.length - 1);
  includeBucketInRange(state.bucketIdx);
  rememberCurrentBucket();
  const slider = $("#time-slider");
  if (slider) slider.value = String(state.bucketIdx);
  updateHash();
  render();
}

function setHistoryRange(start, end, changed) {
  if (!state.buckets.length) return;
  stopPlay();
  const previousBucket = state.bucketIdx;
  [state.rangeStart, state.rangeEnd] = normalizeHistoryRange(
    start,
    end,
    state.buckets.length - 1,
    changed,
  );
  if (state.bucketIdx < state.rangeStart) state.bucketIdx = state.rangeStart;
  if (state.bucketIdx > state.rangeEnd) state.bucketIdx = state.rangeEnd;
  if (state.bucketIdx !== previousBucket) rememberCurrentBucket();
  const slider = $("#time-slider");
  if (slider) slider.value = String(state.bucketIdx);
  const bucketChanged = state.bucketIdx !== previousBucket;
  if (bucketChanged) {
    updateHash();
    render();
  } else {
    renderHistoryWindowOnly();
  }
  return bucketChanged;
}

function renderRangeControls() {
  const start = $("#range-start");
  const end = $("#range-end");
  const readout = $("#range-readout");
  if (!start || !end || !readout) return;
  const max = Math.max(0, state.buckets.length - 1);
  start.max = String(max);
  end.max = String(max);
  start.value = String(state.rangeStart);
  end.value = String(state.rangeEnd);
  start.disabled = max === 0;
  end.disabled = max === 0;
  const startText = fmtBucket(state.buckets[state.rangeStart]);
  const endText = fmtBucket(state.buckets[state.rangeEnd]);
  start.setAttribute("aria-valuetext", startText);
  end.setAttribute("aria-valuetext", endText);
  readout.textContent = t("range-readout", { start: startText, end: endText });
}

function pointTimestamp(point) {
  return timestampMilliseconds(point) ?? timestampMilliseconds(state.buckets[point?.index]);
}

function seriesSegments(points, interval = state.interval) {
  const sorted = [...points].sort((a, b) => {
    const aTime = pointTimestamp(a);
    const bTime = pointTimestamp(b);
    if (aTime != null && bTime != null) return aTime - bTime;
    return a.index - b.index;
  });
  const step = intervalMilliseconds(interval);
  const segments = [];
  for (const point of sorted) {
    const currentSegment = segments[segments.length - 1];
    const previous = currentSegment?.[currentSegment.length - 1];
    const previousTime = pointTimestamp(previous);
    const pointTime = pointTimestamp(point);
    const adjacentByTime =
      previousTime != null &&
      pointTime != null &&
      Math.abs(pointTime - previousTime - step) <= Math.max(1000, step * 0.01);
    const adjacentByIndex =
      (previousTime == null || pointTime == null) && point.index === previous?.index + 1;
    if (!previous || (!adjacentByTime && !adjacentByIndex)) {
      segments.push([point]);
    } else {
      currentSegment.push(point);
    }
  }
  return segments;
}

function rangeStats(points, expectedSlots, ordinal = state.parameter === "exposure") {
  const values = points.map((point) => point.value).filter(Number.isFinite).sort((a, b) => a - b);
  if (!values.length) return null;
  const middle = Math.floor(values.length / 2);
  // An ordinal midpoint is not an observed category. Use the conservative observed upper middle
  // for an even exposure sample; numeric parameters retain the conventional arithmetic midpoint.
  const median = ordinal
    ? values[Math.floor(values.length / 2)]
    : values.length % 2
      ? values[middle]
      : (values[middle - 1] + values[middle]) / 2;
  const occupiedSlots = new Set(
    points.map((point) => pointTimestamp(point) ?? `index:${point.index}`),
  ).size;
  return {
    count: values.length,
    min: values[0],
    median,
    max: values[values.length - 1],
    provisional: points.filter((point) => point.row.provisional).length,
    gaps: Math.max(0, expectedSlots - occupiedSlots),
  };
}

function seriesPointsFor(cellId) {
  if (!cellId) return [];
  const rows = state.seriesIndex.get(`${state.parameter}\u0000${cellId}`) || [];
  const bucketOrder = new Map(state.buckets.map((bucket, i) => [bucket, i]));
  return rows
    .map((row) => {
      const index = bucketOrder.get(row.bucket);
      return {
        row,
        index,
        timestamp: timestampMilliseconds(row.bucket),
        value: magnitudeFor(row),
        uncertainty: magnitudeUncertainty(row),
      };
    })
    .filter(
      (point) =>
        point.index >= state.rangeStart &&
        point.index <= state.rangeEnd &&
        Number.isFinite(point.value),
    );
}

function renderHistoryWindowOnly() {
  renderRangeControls();
  const row = focusRow(current()) || (state.selected ? referenceRowFor(state.selected) : null);
  renderExposureBraid(row);
}

function seriesPath(segment, x, y, step = false) {
  if (!segment.length) return "";
  let d = `M${x(segment[0].index)},${y(segment[0].value)}`;
  for (let i = 1; i < segment.length; i += 1) {
    const previous = segment[i - 1];
    const point = segment[i];
    if (step) d += ` L${x(point.index)},${y(previous.value)} L${x(point.index)},${y(point.value)}`;
    else d += ` L${x(point.index)},${y(point.value)}`;
  }
  return d;
}

function selectedExposureNote(points) {
  return points.find((point) => point.index === state.bucketIdx)?.row?.uncertainty_note || "";
}

function braidEvidenceNote(row, points) {
  if (state.parameter === "exposure") {
    const note = selectedExposureNote(points);
    return note ? t("braid-exposure-note", { note }) : t("braid-no-band");
  }
  return points.some((point) => point.uncertainty != null)
    ? t("braid-se-note")
    : t("braid-no-band");
}

function renderBraidEvidenceNote(element, row, points) {
  if (!element) return;
  element.textContent = braidEvidenceNote(row, points);
}

function braidSelectionText() {
  const row = focusRow(current());
  if (row) {
    return t("braid-selected-status", {
      place: placeName(row),
      time: fmtBucket(row.bucket),
      reading: readingText(row),
    });
  }
  if (state.selected) {
    const reference =
      referenceRowFor(state.selected) ||
      state.cells.find((cell) => cell.cell_id === state.selected);
    if (reference) {
      return t("braid-selected-gap", {
        place: placeName(reference),
        time: fmtBucket(currentBucket()),
      });
    }
  }
  return t("braid-selected-empty", { time: fmtBucket(currentBucket()) });
}

function announceBraidSelection() {
  const status = $("#braid-status");
  if (status) status.textContent = braidSelectionText();
}

function nearestSeriesIndex(points, fraction) {
  if (!points.length) return null;
  const position = Math.max(0, Math.min(1, Number(fraction) || 0));
  const startTime = timestampMilliseconds(state.buckets[state.rangeStart]);
  const endTime = timestampMilliseconds(state.buckets[state.rangeEnd]);
  if (startTime != null && endTime != null && endTime > startTime) {
    const target = startTime + (endTime - startTime) * position;
    return points.reduce((nearest, point) => {
      const pointTime = pointTimestamp(point);
      const nearestTime = pointTimestamp(nearest);
      if (pointTime == null) return nearest;
      if (nearestTime == null || Math.abs(pointTime - target) < Math.abs(nearestTime - target)) {
        return point;
      }
      return nearest;
    }, points[0]).index;
  }
  const target = state.rangeStart + (state.rangeEnd - state.rangeStart) * position;
  return points.reduce(
    (nearest, point) =>
      Math.abs(point.index - target) < Math.abs(nearest.index - target) ? point : nearest,
    points[0],
  ).index;
}

const SVG_NS = "http://www.w3.org/2000/svg";
const BRAID_WIDTH = 800;
const BRAID_PLOT_LEFT = 58;
const BRAID_PLOT_RIGHT = 18;
function svgNode(name, attributes = {}) {
  const node = document.createElementNS(SVG_NS, name);
  for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, String(value));
  return node;
}

function renderExposureBraid(row) {
  const host = $("#exposure-braid");
  const summaryEl = $("#braid-summary");
  const methodNote = $("#braid-method-note");
  if (!host || !summaryEl) return;
  // The HTML owns the accessible name/description relationship via aria-labelledby/describedby.
  // Remove the legacy dynamic aria-label so it cannot override that richer structure.
  host.removeAttribute("aria-label");
  host.replaceChildren();
  const publishedPoints = seriesPointsFor(row?.cell_id);
  const {
    series: points,
    allProvisional,
    excludedProvisional,
  } = calibratedEvidenceSeries(publishedPoints);
  const expected = expectedSlotsInRange();
  const stats = rangeStats(points, expected);
  if (!row || !stats) {
    const empty = document.createElement("p");
    empty.className = "viz-empty";
    empty.textContent = t("braid-empty");
    host.appendChild(empty);
    summaryEl.textContent = "";
    if (methodNote) methodNote.textContent = "";
    return;
  }

  const width = BRAID_WIDTH;
  const height = 250;
  const margin = { top: 22, right: BRAID_PLOT_RIGHT, bottom: 34, left: BRAID_PLOT_LEFT };
  const plotW = width - margin.left - margin.right;
  const plotH = height - margin.top - margin.bottom;
  const uncertaintyBounds = points.flatMap((point) =>
    point.uncertainty == null
      ? []
      : [point.value - point.uncertainty, point.value + point.uncertainty],
  );
  const domainValues = points.map((point) => point.value).concat(uncertaintyBounds);
  let min = Math.min(...domainValues);
  let max = Math.max(...domainValues);
  if (state.parameter === "exposure") {
    min = 0;
    max = EXP_ORDER.length - 1;
  } else if (min === max) {
    const pad = Math.max(1, Math.abs(min) * 0.05);
    min -= pad;
    max += pad;
  }
  const startTime = timestampMilliseconds(state.buckets[state.rangeStart]);
  const endTime = timestampMilliseconds(state.buckets[state.rangeEnd]);
  const indexSpan = Math.max(1, state.rangeEnd - state.rangeStart);
  const x = (index) => {
    const time = timestampMilliseconds(state.buckets[index]);
    if (startTime != null && endTime != null && time != null && endTime > startTime) {
      return margin.left + ((time - startTime) / (endTime - startTime)) * plotW;
    }
    return margin.left + ((index - state.rangeStart) / indexSpan) * plotW;
  };
  const y = (value) => margin.top + ((max - value) / Math.max(0.0001, max - min)) * plotH;

  const svg = svgNode("svg", {
    class: "braid-svg",
    viewBox: `0 0 ${width} ${height}`,
    "aria-hidden": "true",
    focusable: "false",
  });
  const defs = svgNode("defs");
  const pattern = svgNode("pattern", {
    id: "braid-provisional-pattern",
    width: 8,
    height: 8,
    patternUnits: "userSpaceOnUse",
    patternTransform: "rotate(45)",
  });
  pattern.appendChild(svgNode("rect", { width: 8, height: 8, class: "braid-pattern-bg" }));
  pattern.appendChild(svgNode("line", { x1: 0, y1: 0, x2: 0, y2: 8, class: "braid-pattern-line" }));
  defs.appendChild(pattern);
  svg.appendChild(defs);

  const axisValues =
    state.parameter === "exposure"
      ? EXP_ORDER.map((_, index) => index)
      : Array.from({ length: 4 }, (_, index) => min + ((max - min) * index) / 3);
  for (const value of axisValues) {
    const lineY = y(value);
    svg.appendChild(
      svgNode("line", {
        x1: margin.left,
        x2: width - margin.right,
        y1: lineY,
        y2: lineY,
        class: "braid-gridline",
      }),
    );
    const label = svgNode("text", { x: margin.left - 8, y: lineY + 4, class: "braid-axis-label" });
    label.textContent = formatMagnitude(value);
    svg.appendChild(label);
  }

  const bandPoints = points.filter((point) => point.uncertainty != null);
  for (const segment of seriesSegments(bandPoints)) {
    if (segment.length < 2) continue;
    const upper = segment.map((point) => `${x(point.index)},${y(point.value + point.uncertainty)}`);
    const lower = [...segment]
      .reverse()
      .map((point) => `${x(point.index)},${y(point.value - point.uncertainty)}`);
    svg.appendChild(
      svgNode("polygon", { points: upper.concat(lower).join(" "), class: "braid-uncertainty" }),
    );
  }

  for (const segment of seriesSegments(points)) {
    if (segment.length < 2) continue;
    const d = seriesPath(segment, x, y, state.parameter === "exposure");
    svg.appendChild(svgNode("path", { d, class: "braid-line" }));
  }

  if (state.bucketIdx >= state.rangeStart && state.bucketIdx <= state.rangeEnd) {
    svg.appendChild(
      svgNode("line", {
        x1: x(state.bucketIdx),
        x2: x(state.bucketIdx),
        y1: margin.top,
        y2: height - margin.bottom,
        class: "braid-cursor",
      }),
    );
  }

  for (const point of points) {
    svg.appendChild(
      svgNode("circle", {
        cx: x(point.index),
        cy: y(point.value),
        r: 16,
        class: "braid-hit-target",
        fill: "transparent",
        "pointer-events": "all",
        "data-bucket-index": point.index,
      }),
    );
    const circle = svgNode("circle", {
      cx: x(point.index),
      cy: y(point.value),
      r: point.index === state.bucketIdx ? 7 : 4.5,
      class: [
        "braid-point",
        point.row.provisional ? "provisional" : "confirmed",
        point.index === state.bucketIdx ? "active" : "",
      ]
        .filter(Boolean)
        .join(" "),
      "data-bucket-index": point.index,
    });
    const title = svgNode("title");
    title.textContent = `${fmtBucket(point.row.bucket)} — ${readingText(point.row)}`;
    circle.appendChild(title);
    svg.appendChild(circle);
  }

  const startLabel = svgNode("text", {
    x: margin.left,
    y: height - 8,
    class: "braid-time-label",
  });
  startLabel.textContent = fmtBucket(state.buckets[state.rangeStart]);
  svg.appendChild(startLabel);
  const endLabel = svgNode("text", {
    x: width - margin.right,
    y: height - 8,
    class: "braid-time-label end",
  });
  endLabel.textContent = fmtBucket(state.buckets[state.rangeEnd]);
  svg.appendChild(endLabel);
  host.appendChild(svg);

  let summary = t("braid-summary", {
    place: placeName(row),
    n: formatNumber(stats.count),
    start: fmtBucket(state.buckets[state.rangeStart]),
    end: fmtBucket(state.buckets[state.rangeEnd]),
    min: formatMagnitude(stats.min),
    median: formatMagnitude(stats.median),
    max: formatMagnitude(stats.max),
    provisional: formatNumber(stats.provisional),
    gaps: formatNumber(stats.gaps),
  });
  if (allProvisional) {
    summary += ` ${t("braid-all-provisional")}`;
  } else if (excludedProvisional) {
    summary += ` ${t("braid-provisional-excluded", { n: excludedProvisional })}`;
  }
  summaryEl.textContent = summary;
  renderBraidEvidenceNote(methodNote, row, publishedPoints);
}

function distributionEntries(rows) {
  const order = (a, b) => {
    const difference = magnitudeFor(b) - magnitudeFor(a);
    if (difference) return difference;
    if (state.parameter === "exposure" && Boolean(a.compound) !== Boolean(b.compound)) {
      return Number(Boolean(b.compound)) - Number(Boolean(a.compound));
    }
    return placeName(a).localeCompare(placeName(b));
  };
  const publishedNetwork = overviewRows()
    .filter((row) => Number.isFinite(magnitudeFor(row)))
    .sort(order);
  const {
    series: network,
    allProvisional,
    excludedProvisional,
  } = calibratedEvidenceSeries(publishedNetwork);
  const candidates = (state.search
    ? rows.filter((row) => Boolean(row.provisional) === allProvisional)
    : network
  )
    .filter((row) => Number.isFinite(magnitudeFor(row)))
    .sort(order);
  const shown = candidates.slice(0, 10);
  const selected = network.find((row) => row.cell_id === state.selected);
  const selectedIsOutlier =
    Boolean(selected) && !shown.some((row) => row.cell_id === selected.cell_id);
  if (selectedIsOutlier) shown.push(selected);
  const entries = shown.map((row) => {
    const magnitude = magnitudeFor(row);
    return {
      row,
      // Competition ranking: equal readings share a rank, and the next rank skips accordingly.
      rank: 1 + network.filter((peer) => magnitudeFor(peer) > magnitude).length,
      position: network.indexOf(row) + 1,
      selectedOutlier: selectedIsOutlier && row.cell_id === selected?.cell_id,
    };
  });
  const values = network.map((row) => magnitudeFor(row));
  return {
    entries,
    networkCount: network.length,
    min: values.length ? Math.min(...values) : NaN,
    max: values.length ? Math.max(...values) : NaN,
    allProvisional,
    excludedProvisional,
  };
}

function distributionPercent(value, distribution) {
  if (state.parameter === "exposure") {
    const level = Math.max(0, Math.min(EXP_ORDER.length - 1, Math.round(value)));
    return 18 + (level / (EXP_ORDER.length - 1)) * 82;
  }
  // Pollutants have a meaningful zero baseline. Temperature-like measurements use the selected
  // observation's network range; the adjacent note tells readers that printed values and ranks are
  // authoritative so bar geometry is never mistaken for an absolute threshold scale.
  const zeroBased = ["pm25_ugm3", "pm10_ugm3", "no2_ppb"].includes(state.parameter);
  const min = zeroBased ? 0 : distribution.min;
  if (distribution.max === min) return distribution.max === 0 ? 0 : 100;
  return Math.max(0, Math.min(100, ((value - min) / (distribution.max - min)) * 100));
}

function renderDistribution(rows) {
  const list = $("#distribution-viz");
  if (!list) return;
  const focusedCell = document.activeElement?.closest?.(".distribution-row")?.dataset?.cell || null;
  list.replaceChildren();
  const distribution = distributionEntries(rows);
  const key = $("#distribution-key");
  if (key) {
    key.textContent = t(
      distribution.allProvisional
        ? state.search
          ? "distribution-search-key-provisional"
          : "distribution-key-provisional"
        : state.search
          ? "distribution-search-key"
          : "distribution-key",
    );
  }
  if (!distribution.entries.length) {
    const empty = document.createElement("li");
    empty.className = "viz-empty";
    empty.textContent = t(
      state.search && distribution.excludedProvisional
        ? "distribution-search-empty-confirmed"
        : state.search
          ? "distribution-search-empty"
          : "distribution-empty",
    );
    list.appendChild(empty);
    return;
  }

  let restoreFocus = null;
  for (const { row, rank, position, selectedOutlier } of distribution.entries) {
    const value = magnitudeFor(row);
    const pct = distributionPercent(value, distribution);
    const li = document.createElement("li");
    li.className = [
      row.provisional ? "provisional" : "confirmed",
      selectedOutlier ? "selected-outlier" : "",
    ]
      .filter(Boolean)
      .join(" ");
    li.value = position;
    li.setAttribute("aria-posinset", String(position));
    li.setAttribute("aria-setsize", String(distribution.networkCount));
    const button = document.createElement("button");
    button.type = "button";
    button.className = "distribution-row";
    button.dataset.cell = row.cell_id;
    button.setAttribute("aria-pressed", String(row.cell_id === state.selected));
    const rankLabel = document.createElement("span");
    rankLabel.className = "distribution-rank";
    rankLabel.textContent = `#${formatNumber(rank)}`;
    const label = document.createElement("span");
    label.className = "distribution-label";
    label.textContent = placeName(row);
    const reading = document.createElement("span");
    reading.className = "distribution-reading";
    reading.textContent = readingText(row);
    const track = document.createElement("span");
    track.className = "distribution-track";
    track.setAttribute("aria-hidden", "true");
    const bar = document.createElement("span");
    bar.className = "distribution-bar";
    bar.style.width = `${pct}%`;
    track.appendChild(bar);
    button.append(rankLabel, label, reading, track);
    button.addEventListener("click", () => select(row.cell_id, true));
    if (row.cell_id === focusedCell) restoreFocus = button;
    li.appendChild(button);
    list.appendChild(li);
  }
  restoreFocus?.focus({ preventScroll: true });
}

// `row` is the focus row already resolved by the synchronous `renderNow` in `render()`; the deferred
// workspace reuses it for the braid instead of repainting the Now card a second time.
function renderObservatory(rows, row) {
  renderRangeControls();
  renderExposureBraid(row);
  renderDistribution(rows);
  const workspace = document.querySelector(".workspace-shell");
  if (workspace) workspace.dataset.inspector = state.selected ? "active" : "empty";
  const emptyInspector = $("#inspector-empty");
  if (emptyInspector) emptyInspector.hidden = !!state.selected;
}

// Node health (from /api/health.json, or the baked sample on the static site): the network's
// sensors broken down by status — ok, degraded (backfilled sparsely or flagging a lot), offline.
// The operator's "is my network healthy?" line, from the same QC the pipeline already runs.
function healthLine() {
  const s = state.health && state.health.summary;
  if (!s || !s.total) return "";
  const observedAt = state.health.latest || latestBucket();
  let line = t("health-status", {
    ok: formatNumber(s.ok || 0),
    degraded: formatNumber(s.degraded || 0),
    offline: formatNumber(s.offline || 0),
    time: fmtBucket(observedAt),
  });
  if (observationAgeMinutes(observedAt) > CURRENT_OBSERVATION_MAX_AGE_MINUTES) {
    line += ` ${t("health-stale")}`;
  }
  return line;
}

async function loadHealth() {
  const doc = isStaticDeployment()
    ? await fetchJson("sample-health.json")
    : (await fetchJson("api/health.json")) || (await fetchJson("sample-health.json"));
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

async function loadDemoContract() {
  const doc = await fetchJson("demo.json");
  if (
    doc?.schema_version !== 1 ||
    doc.runtime !== "static" ||
    !doc.source ||
    !Array.isArray(doc.surface?.parameters)
  ) {
    return null;
  }
  return doc;
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
  return t("coverage", { now: formatNumber(now.size), total: formatNumber(known.size) });
}

// How current the data actually is — the newest hour in the network and its age, with an honest
// "this network may be behind" note when it's stale. A community/scale-to-zero network can lag, and
// saying so plainly is the trustworthy thing a generic weather app's "live" badge won't.
function freshnessLine() {
  if (!state.buckets.length) return "";
  const latest = state.buckets[state.buckets.length - 1];
  const ageMin = Math.max(0, Math.round((Date.now() - new Date(latest).getTime()) / 60000));
  let age;
  if (ageMin < 60) age = t("fresh-min", { m: formatNumber(ageMin) });
  else if (ageMin < 2880)
    age = t("fresh-hr", { h: formatNumber(Math.round(ageMin / 60)) });
  else age = t("fresh-day", { d: formatNumber(Math.round(ageMin / 1440)) });
  let line = t("fresh-latest", { time: fmtBucket(latest), age });
  if (ageMin > 180) line += " " + t("fresh-stale");
  return line;
}

// A reading's age in plain words from an ISO timestamp — minutes, hours, or days ago.
function ageText(iso) {
  const ageMin = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
  if (ageMin < 60) return t("fresh-min", { m: formatNumber(ageMin) });
  if (ageMin < 2880) return t("fresh-hr", { h: formatNumber(Math.round(ageMin / 60)) });
  return t("fresh-day", { d: formatNumber(Math.round(ageMin / 1440)) });
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
    li.textContent = t("health-all-ok", { n: formatNumber(nodes.length) });
    list.appendChild(li);
    return;
  }
  for (const n of attention) {
    const li = document.createElement("li");
    li.textContent = t("health-node", {
      node: n.node_id,
      status: t(n.status === "offline" ? "health-stat-offline" : "health-stat-degraded"),
      pct: formatNumber(Math.round((n.completeness || 0) * 100)),
      age: n.last_seen ? ageText(n.last_seen) : "—",
    });
    list.appendChild(li);
  }
}

function worstButton(row, label) {
  const b = document.createElement("button");
  b.type = "button";
  b.className = "linklike";
  b.dataset.cell = row.cell_id;
  b.textContent = label;
  b.addEventListener("click", () => select(row.cell_id, true));
  return b;
}

function overviewStatisticRows(rows) {
  const confirmed = rows.filter((row) => !row.provisional);
  return confirmed.length ? confirmed : rows;
}

// "Right now across the network" — the shape of the whole network for the current measurement and
// hour: how many confirmed vs provisional, the spread (a category breakdown, or low/typical/high for
// a number), and the single worst confirmed location. The big-picture view officials and reporters
// want, beside the per-location detail residents use.
function renderOverview() {
  const panel = $("#overview");
  const focusedCell = document.activeElement?.closest?.("#overview-worst button")?.dataset?.cell;
  const rows = overviewRows();
  if (!rows.length) {
    panel.hidden = true;
    return;
  }
  panel.hidden = false;
  $("#overview-heading").textContent = t("overview-heading-at", {
    time: fmtBucket(currentBucket()),
  });
  const confirmed = rows.filter((r) => !r.provisional);
  $("#overview-counts").textContent = sourceTerm("overview_counts", "overview-counts", {
    n: formatNumber(rows.length),
    confirmed: formatNumber(confirmed.length),
    yes: formatNumber(confirmed.length),
    provisional: formatNumber(rows.length - confirmed.length),
    rough: formatNumber(rows.length - confirmed.length),
  });

  $("#overview-coverage").textContent = coverageLine();
  $("#overview-health").textContent = healthLine();
  renderHealthDetail();
  $("#overview-fresh").textContent = freshnessLine();
  const spread = $("#overview-spread");
  const worstEl = $("#overview-worst");
  worstEl.textContent = "";
  let restoreFocus = null;

  if (state.parameter === "pm25_ugm3" || isExposure()) {
    const order = isExposure() ? EXP_ORDER : AQI_ORDER;
    const localize = isExposure() ? localExposure : localCategory;
    const counts = new Map();
    for (const r of confirmed) counts.set(r.category, (counts.get(r.category) || 0) + 1);
    const parts = order.filter((c) => counts.get(c)).map((c) => `${localize(c)} ${counts.get(c)}`);
    spread.textContent = parts.length
      ? parts.join(" · ")
      : sourceTerm("overview_none", "overview-none-confirmed");
    if (confirmed.length) {
      const worst = confirmed.reduce((a, b) =>
        order.indexOf(b.category) > order.indexOf(a.category) ? b : a,
      );
      worstEl.appendChild(
        document.createTextNode(sourceTerm("overview_worst_label", "overview-worst-label") + " "),
      );
      const button = worstButton(worst, `${placeName(worst)} — ${localize(worst.category)}`);
      worstEl.appendChild(button);
      if (worst.cell_id === focusedCell) restoreFocus = button;
    }
  } else {
    // Numeric aggregates use confirmed rows whenever any exist; provisional outliers cannot
    // silently change the displayed range or "worst" location.
    const statisticRows = overviewStatisticRows(rows);
    const vals = statisticRows.map((r) => r.mean).sort((a, b) => a - b);
    const n = vals.length;
    const median = n % 2 ? vals[(n - 1) / 2] : (vals[n / 2 - 1] + vals[n / 2]) / 2;
    const spreadText = t("overview-spread", {
      min: formatNumber(round1(convert(vals[0])), { maximumFractionDigits: 1 }),
      median: formatNumber(round1(convert(median)), { maximumFractionDigits: 1 }),
      max: formatNumber(round1(convert(vals[n - 1])), { maximumFractionDigits: 1 }),
      unit: unitLabel(),
    });
    // The composite min/median/max line has no single "value" to glue the caveat to — attach it
    // once, to the whole line, so the estimate is never read as a direct measurement (R5).
    let numericSpread = ESTIMATED_PARAMS.has(state.parameter)
      ? t("estimated-value", { value: spreadText })
      : spreadText;
    if (!confirmed.length) numericSpread += ` ${t("overview-all-provisional-stats")}`;
    else if (confirmed.length < rows.length) {
      numericSpread += ` ${t("overview-provisional-excluded", {
        n: rows.length - confirmed.length,
      })}`;
    }
    spread.textContent = numericSpread;
    const worst = statisticRows.reduce((a, b) => (b.mean > a.mean ? b : a));
    worstEl.appendChild(
      document.createTextNode(
        (confirmed.length
          ? sourceTerm("overview_worst_label", "overview-worst-label")
          : t("overview-worst-provisional-label")) + " ",
      ),
    );
    const button = worstButton(worst, `${placeName(worst)} — ${readingText(worst)}`);
    worstEl.appendChild(button);
    if (worst.cell_id === focusedCell) restoreFocus = button;
  }
  restoreFocus?.focus({ preventScroll: true });
}

function renderList(rows) {
  const list = $("#data-list");
  const focusedCell = document.activeElement?.closest?.("#data-list .row-select")?.dataset?.cell;
  list.textContent = "";
  let restoreFocus = null;
  for (const row of rows) {
    const li = document.createElement("li");
    li.dataset.cell = row.cell_id;
    li.dataset.recordKey = representationKey(row);
    if (row.cell_id === state.selected) li.classList.add("selected");
    const place = document.createElement("button");
    place.type = "button";
    place.className = "place linklike row-select";
    place.dataset.cell = row.cell_id;
    place.setAttribute("aria-pressed", String(row.cell_id === state.selected));
    place.textContent = placeName(row);
    const reading = document.createElement("span");
    reading.className = "reading";
    reading.textContent = readingText(row);
    li.append(place, reading);
    li.addEventListener("click", () => select(row.cell_id));
    if (row.cell_id === focusedCell) restoreFocus = place;
    list.appendChild(li);
  }
  restoreFocus?.focus({ preventScroll: true });
}

function renderTable(rows) {
  const body = $("#data-table-body");
  const focusedCell = document.activeElement?.closest?.("#data-table-body .row-select")?.dataset?.cell;
  body.textContent = "";
  let restoreFocus = null;
  for (const row of rows) {
    const tr = document.createElement("tr");
    tr.dataset.cell = row.cell_id;
    tr.dataset.recordKey = representationKey(row);
    if (row.cell_id === state.selected) tr.classList.add("selected");

    const place = document.createElement("th");
    place.scope = "row";
    const placeButton = document.createElement("button");
    placeButton.type = "button";
    placeButton.className = "linklike row-select";
    placeButton.dataset.cell = row.cell_id;
    placeButton.setAttribute("aria-pressed", String(row.cell_id === state.selected));
    placeButton.textContent = placeName(row);
    place.appendChild(placeButton);
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
    const flagged = qcFlagged(row);
    tag.className = `tag ${row.provisional ? "provisional" : ""}${flagged ? " flagged" : ""}`.trim();
    tag.textContent = row.provisional
      ? provisionalTag(row)
      : sourceTerm("non_provisional_label", "state-calibrated");
    stateCell.appendChild(tag);
    tr.appendChild(stateCell);

    tr.addEventListener("click", () => select(row.cell_id));
    if (row.cell_id === focusedCell) restoreFocus = placeButton;
    body.appendChild(tr);
  }
  restoreFocus?.focus({ preventScroll: true });
}

function td(text) {
  const cell = document.createElement("td");
  cell.textContent = text;
  return cell;
}

// Equirectangular projection over a bounding box, with a cos(latitude) longitude scale so the
// shape isn't stretched east-west. If a basemap exists, every camera state uses that same fixed
// geographic projection; interaction changes only the canvas transform. Routes without a basemap
// retain the data-fit fallback.
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
  return {
    minLon,
    minLat,
    maxLon,
    maxLat,
    kx,
    W: (maxLon - minLon) * kx,
    H: maxLat - minLat,
    basemap: Boolean(bm),
  };
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
  if (proj.basemap) {
    return { left: span(row.lon, proj.minLon, proj.maxLon), bottom: span(row.lat, proj.minLat, proj.maxLat) };
  }
  return {
    left: 0.06 + 0.88 * span(row.lon, proj.minLon, proj.maxLon),
    bottom: 0.08 + 0.84 * span(row.lat, proj.minLat, proj.maxLat),
  };
}

// The cooling-center overlay: a distinct snowflake glyph per center, positioned with the same
// projection as the readings. Decorative on the map (aria-hidden) — the accessible equivalent is the
// always-present cooling-center list — but each carries a title so a sighted pointer user gets a name.
function addCoolingOverlay(canvas, proj) {
  for (const c of state.coolingCenters) {
    if (!Number.isFinite(c.lat) || !Number.isFinite(c.lon)) continue;
    const pos = markerPos(c, proj);
    const left = Math.min(1, Math.max(0, pos.left));
    const bottom = Math.min(1, Math.max(0, pos.bottom));
    const mark = document.createElement("span");
    mark.className = "cool-center";
    mark.setAttribute("aria-hidden", "true");
    mark.title = c.name;
    mark.textContent = "❄";
    mark.style.left = `${left * 100}%`;
    mark.style.bottom = `${bottom * 100}%`;
    mark.dataset.mapLeft = String(left);
    mark.dataset.mapBottom = String(bottom);
    mapPositionedElements.push({ element: mark, position: { left, bottom } });
    canvas.appendChild(mark);
  }
}

const MAP_CLUSTER_REVEAL_ZOOM = 2.25;
const MAP_CLUSTER_FIT_PADDING = 32;

// Group nearby positions into overview clusters without removing any reading from the DOM. Each
// member still renders as a complete `.cell` for Map/List/Table outcome equivalence; CSS collapses
// clustered members only at the statewide overview, then reveals them once the reader zooms in.
// Dense overviews use screen-pixel bins; smaller sets merge only controls that would overlap. A
// cluster is anchored to the member nearest its center, so coastal groups cannot land in the ocean.
function markerClusters(
  layout,
  width,
  height,
  enabled = true,
  textScale = 1,
  coarse = true,
  baseSeparationX = 50,
  baseSeparationY = baseSeparationX,
) {
  if (!enabled || !width || !height || layout.length < 2) {
    return layout.map((position, index) => ({ indices: [index], position }));
  }
  // Keep the statewide view intentionally coarse: one screen should communicate coverage and
  // concentration, not ask the reader to parse dozens of same-weight controls. The first cluster
  // activation zooms far enough that every underlying reading is restored.
  let groups;
  if (coarse) {
    const binSize = Math.max(96, Math.min(120, width / 7.5));
    const bins = new Map();
    for (let index = 0; index < layout.length; index += 1) {
      const position = layout[index];
      const key = `${Math.floor((position.left * width) / binSize)}:${Math.floor(
        ((1 - position.bottom) * height) / binSize,
      )}`;
      if (!bins.has(key)) bins.set(key, { indices: [] });
      bins.get(key).indices.push(index);
    }
    groups = [...bins.values()];
  } else {
    groups = layout.map((_position, index) => ({ indices: [index] }));
  }
  const anchorFor = (group) => {
    const center = group.indices.reduce(
      (total, index) => ({
        x: total.x + layout[index].left * width,
        y: total.y + (1 - layout[index].bottom) * height,
      }),
      { x: 0, y: 0 },
    );
    center.x /= group.indices.length;
    center.y /= group.indices.length;
    return group.indices.reduce((best, index) => {
      const dx = layout[index].left * width - center.x;
      const dy = (1 - layout[index].bottom) * height - center.y;
      const distance = dx * dx + dy * dy;
      return distance < best.distance ? { index, distance } : best;
    }, { index: group.indices[0], distance: Number.POSITIVE_INFINITY }).index;
  };

  // Merge overlapping representatives after binning. At 130% text, a cluster target is 62.4px;
  // 50px × scale leaves a small gap. Axis-aligned checks cover the whole target, not just its circle.
  const scale = Number.isFinite(textScale) && textScale > 0 ? textScale : 1;
  const requiredX = baseSeparationX * scale;
  const requiredY = baseSeparationY * scale;
  while (groups.length > 1) {
    const anchors = groups.map(anchorFor);
    let overlap = null;
    for (let left = 0; left < groups.length - 1; left += 1) {
      const a = layout[anchors[left]];
      for (let right = left + 1; right < groups.length; right += 1) {
        const b = layout[anchors[right]];
        const dx = Math.abs(a.left - b.left) * width;
        const dy = Math.abs(a.bottom - b.bottom) * height;
        if (dx >= requiredX || dy >= requiredY) continue;
        const distance = Math.max(dx / requiredX, dy / requiredY);
        if (!overlap || distance < overlap.distance) overlap = { left, right, distance };
      }
    }
    if (!overlap) break;
    groups[overlap.left].indices.push(...groups[overlap.right].indices);
    groups[overlap.left].indices.sort((a, b) => a - b);
    groups.splice(overlap.right, 1);
  }

  return groups.map((group) => ({
    indices: group.indices,
    position: layout[anchorFor(group)],
  }));
}

// Fit projected member positions by moving the camera over the existing canvas. The returned view
// does not mutate the positions or projection. The full group remains in view; compact markers and
// per-group clustering handle density without turning a close pair into an extreme, context-free
// zoom that hides the rest of the network.
function fitMapBounds(
  positions,
  width,
  height,
  padding = MAP_CLUSTER_FIT_PADDING,
) {
  const points = positions.filter(
    (position) => Number.isFinite(position?.left) && Number.isFinite(position?.bottom),
  );
  if (!points.length || !Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0) {
    return { zoom: 1, x: 0, y: 0 };
  }
  const left = Math.min(...points.map((position) => position.left));
  const right = Math.max(...points.map((position) => position.left));
  const bottom = Math.min(...points.map((position) => position.bottom));
  const top = Math.max(...points.map((position) => position.bottom));
  const safePadding = Math.max(0, Math.min(padding, width / 2 - 1, height / 2 - 1));
  const spanX = (right - left) * width;
  const spanY = (top - bottom) * height;
  const fitX = spanX > 0 ? (width - 2 * safePadding) / spanX : MAX_ZOOM;
  const fitY = spanY > 0 ? (height - 2 * safePadding) / spanY : MAX_ZOOM;

  const zoom = Math.min(
    MAX_ZOOM,
    Math.max(MAP_CLUSTER_REVEAL_ZOOM + 0.75, Math.min(fitX, fitY)),
  );
  const centerLeft = (left + right) / 2;
  const centerBottom = (bottom + top) / 2;
  const unclampedX = width / 2 - centerLeft * width * zoom;
  const unclampedY = height / 2 - (1 - centerBottom) * height * zoom;
  return {
    zoom,
    x: Math.min(0, Math.max(width * (1 - zoom), unclampedX)),
    y: Math.min(0, Math.max(height * (1 - zoom), unclampedY)),
  };
}

function renderMap(rows) {
  const map = $("#map");
  const wrap = map.closest(".map-wrap");
  const focusedCell = document.activeElement?.closest?.("#map .cell")?.dataset?.cell;
  map.textContent = "";
  map.classList.remove("markers-expanded");
  mapClusterGroups = [];
  mapPositionedElements = [];
  map.classList.toggle("dense", rows.length > 50); // shrink markers on a dense network
  if (!rows.length) {
    mapProj = null;
    return;
  }
  const proj = mapProjection(rows);
  mapProj = proj;
  // Without a basemap the projection is fit to the current rows, so a changed extent (a search
  // filter, a different parameter's coverage) would silently re-anchor a held zoom onto new ground.
  // Refit when that signature changes so the view never drifts onto unrelated geography.
  const sig = `${proj.basemap ? "bm" : "data"}:${proj.minLon},${proj.minLat},${proj.maxLon},${proj.maxLat}`;
  if (!proj.basemap && sig !== state.projSig) state.mapView = { zoom: 1, x: 0, y: 0 };
  state.projSig = sig;
  if (proj.basemap) {
    // Match the whole map wrapper to the projection so the outline is not stretched and its control
    // toolbar stays attached to the actual map instead of an empty full-width gutter.
    const projectedMaxWidth = `${((proj.W / proj.H) * 42).toFixed(2)}rem`;
    map.style.aspectRatio = `${proj.W} / ${proj.H}`;
    map.style.height = "auto";
    map.style.maxWidth = "none";
    map.style.marginInline = "0";
    map.style.minHeight = "0"; // let the aspect-ratio drive height; don't stretch on narrow screens
    if (wrap) {
      wrap.classList.add("statewide-map");
      wrap.style.setProperty("--statewide-map-width", projectedMaxWidth);
      wrap.style.removeProperty("max-width");
      wrap.style.marginInline = "auto";
    }
  } else {
    map.style.removeProperty("aspect-ratio");
    map.style.removeProperty("height");
    map.style.removeProperty("max-width");
    map.style.removeProperty("margin-inline");
    map.style.removeProperty("min-height");
    if (wrap) {
      wrap.classList.remove("statewide-map");
      wrap.style.removeProperty("--statewide-map-width");
      wrap.style.removeProperty("max-width");
      wrap.style.removeProperty("margin-inline");
    }
  }
  const canvas = document.createElement("div");
  canvas.className = "map-canvas";
  if (proj.basemap) canvas.appendChild(buildBasemap(proj));
  // Keep every reading on its projected coordinate. The former collision layout made a dense
  // Sacramento network appear to cover California by pushing markers into empty parts of the state.
  // Clustering now handles the statewide overview; opening the cluster zooms to the real local grid.
  const layout = rows.map((row) => markerPos(row, proj));
  mapLayoutW = map.clientWidth;
  mapLayoutH = map.clientHeight;
  mapLayoutTextStep = state.textStep;
  const clusters = markerClusters(
    layout,
    mapLayoutW,
    mapLayoutH,
    rows.length > 1,
    TEXT_STEPS[state.textStep],
    rows.length > 50,
    rows.length > 50 ? 50 : 90,
    rows.length > 50 ? 50 : 42,
  );
  const clusteredIndices = new Set(
    clusters.filter((cluster) => cluster.indices.length > 1).flatMap((cluster) => cluster.indices),
  );
  markerFractions = new Map();
  const cellButtons = [];
  let restoreFocus = null;
  for (let index = 0; index < rows.length; index += 1) {
    const row = rows[index];
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "cell";
    btn.dataset.cell = row.cell_id;
    btn.dataset.recordKey = representationKey(row);
    btn.setAttribute("aria-pressed", String(row.cell_id === state.selected));
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
    if (clusteredIndices.has(index)) btn.classList.add("cluster-member");
    const pos = layout[index];
    markerFractions.set(row.cell_id, pos);
    btn.style.left = `${pos.left * 100}%`;
    btn.style.bottom = `${pos.bottom * 100}%`;
    btn.dataset.mapLeft = String(pos.left);
    btn.dataset.mapBottom = String(pos.bottom);
    btn.setAttribute("aria-label", describe(row));
    const value = document.createElement("span");
    value.classList.add("cell-reading");
    value.textContent =
      state.parameter === "pm25_ugm3"
        ? `${row.aqi}`
        : isExposure()
          ? formatMagnitude(magnitudeFor(row))
          : ESTIMATED_PARAMS.has(state.parameter)
            ? formatMagnitude(magnitudeFor(row))
            : formatNumber(Math.round(convert(row.mean)));
    if (ESTIMATED_PARAMS.has(state.parameter)) value.classList.add("map-estimated");
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
            : ""
          : ESTIMATED_PARAMS.has(state.parameter)
            ? row.provisional
              ? t("state-provisional")
              : ""
            : unitLabel();
    btn.appendChild(cat);
    btn.addEventListener("click", () => {
      if (mapDidDrag || mapWasMultiTouch) return; // don't let a pan/pinch end as a marker select
      select(row.cell_id, true); // a marker tap focuses the map on that cell
    });
    if (row.cell_id === focusedCell) restoreFocus = btn;
    cellButtons.push(btn);
    mapPositionedElements.push({ element: btn, position: pos });
    canvas.appendChild(btn);
  }
  for (const cluster of clusters) {
    if (cluster.indices.length < 2) continue;
    const members = cluster.indices.map((index) => rows[index]);
    const magnitudes = members
      .map((row) => (state.parameter === "pm25_ugm3" ? Number(row.aqi) : magnitudeFor(row)))
      .filter(Number.isFinite)
      .sort((a, b) => a - b);
    const clusterButton = document.createElement("button");
    clusterButton.type = "button";
    clusterButton.className = "map-cluster";
    clusterButton.style.left = `${cluster.position.left * 100}%`;
    clusterButton.style.bottom = `${cluster.position.bottom * 100}%`;
    clusterButton.dataset.mapLeft = String(cluster.position.left);
    clusterButton.dataset.mapBottom = String(cluster.position.bottom);
    clusterButton.dataset.memberCells = JSON.stringify(
      cluster.indices.map((index) => rows[index].cell_id),
    );
    clusterButton.textContent = t("map-cluster-short", { n: cluster.indices.length });
    const low = magnitudes[0];
    const high = magnitudes[magnitudes.length - 1];
    const formatClusterValue = (value) =>
      state.parameter === "pm25_ugm3"
        ? `AQI ${formatNumber(Math.round(value))}`
        : formatMagnitude(value);
    clusterButton.setAttribute(
      "aria-label",
      t("map-cluster-label", {
        n: cluster.indices.length,
        low: formatClusterValue(low),
        high: formatClusterValue(high),
      }),
    );
    clusterButton.addEventListener("click", () => {
      if (mapDidDrag || mapWasMultiTouch) return;
      zoomToMapBounds(cluster.indices.map((index) => layout[index]), true);
      map.focus({ preventScroll: true });
    });
    mapPositionedElements.push({ element: clusterButton, position: cluster.position });
    canvas.appendChild(clusterButton);
    const view = fitMapBounds(
      cluster.indices.map((index) => layout[index]),
      map.clientWidth,
      map.clientHeight,
    );
    mapClusterGroups.push({
      button: clusterButton,
      members: cluster.indices.map((index) => cellButtons[index]),
      revealZoom: view.zoom,
    });
  }
  if (state.coolingVisible && state.coolingCenters) addCoolingOverlay(canvas, proj);
  lastK = -1; // force cluster visibility to sync onto the fresh canvas
  map.appendChild(canvas);
  applyMapTransform(false);
  if (state.pendingFocus) {
    const focus = state.pendingFocus;
    state.pendingFocus = null;
    zoomToCell(focus, false);
  }
  restoreFocus?.focus({ preventScroll: true });
}

// -- map zoom & pan ----------------------------------------------------------

function measureMap() {
  const map = $("#map");
  if (map && map.clientWidth) {
    mapW = map.clientWidth;
    mapH = map.clientHeight;
  }
}

function mapCameraCenter() {
  const view = state.mapView;
  return {
    left: mapW ? (mapW / 2 - view.x) / (mapW * view.zoom) : 0.5,
    top: mapH ? (mapH / 2 - view.y) / (mapH * view.zoom) : 0.5,
  };
}

function restoreMapCameraCenter(center) {
  const view = state.mapView;
  view.x = mapW / 2 - center.left * mapW * view.zoom;
  view.y = mapH / 2 - center.top * mapH * view.zoom;
}

function clampMapView() {
  const v = state.mapView;
  v.zoom = Math.min(MAX_ZOOM, Math.max(1, v.zoom));
  // Keep the scaled canvas covering the viewport so the map can never be lost off-screen. Uses the
  // cached size (measured on show/resize) so this hot path never forces a synchronous reflow.
  v.x = Math.min(0, Math.max(mapW * (1 - v.zoom), v.x));
  v.y = Math.min(0, Math.max(mapH * (1 - v.zoom), v.y));
}

function cameraViewBox(proj, view) {
  const width = proj.W / view.zoom;
  const height = proj.H / view.zoom;
  const x = (-view.x / (mapW * view.zoom)) * proj.W;
  const y = (-view.y / (mapH * view.zoom)) * proj.H;
  return `${x} ${y} ${width} ${height}`;
}

function applyMapTransform(animate) {
  if (!mapVisible) return; // tab hidden / unmeasurable — the transform is applied when it is shown
  const canvas = $("#map .map-canvas");
  if (!canvas) return;
  if (!mapW || !mapH) measureMap();
  clampMapView();
  const v = state.mapView;
  const map = $("#map");
  canvas.classList.toggle("animate", !!animate && !reduceMotionMQL.matches);
  if (v.zoom !== lastK) {
    let expandedGroups = 0;
    for (const group of mapClusterGroups) {
      const expanded = v.zoom >= group.revealZoom;
      group.button.hidden = expanded;
      group.button.setAttribute("aria-expanded", String(expanded));
      for (const member of group.members) member.classList.toggle("cluster-visible", expanded);
      if (expanded) expandedGroups += 1;
    }
    map?.classList.toggle("markers-expanded", expandedGroups > 0);
    lastK = v.zoom;
  }
  const camera = `translate(${v.x}px, ${v.y}px) scale(${v.zoom})`;
  canvas.dataset.camera = camera;
  // Transforming an SVG root by ~200x magnifies county strokes into hundred-pixel bands in Chromium,
  // while transforming the whole canvas paint-culls fixed-size descendants in multiple engines.
  // Change the SVG camera through its viewBox and place each target in screen pixels instead. Both
  // are derived from the same fixed projection, so geography and readings remain exactly aligned.
  const basemap = canvas.querySelector(".basemap");
  if (basemap && mapProj) basemap.setAttribute("viewBox", cameraViewBox(mapProj, v));
  for (const { element, position } of mapPositionedElements) {
    const screenX = v.x + position.left * mapW * v.zoom;
    const screenY = v.y + (1 - position.bottom) * mapH * v.zoom;
    element.style.left = `${screenX}px`;
    element.style.bottom = `${mapH - screenY}px`;
  }
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

function zoomToMapBounds(positions, animate) {
  if (!mapVisible || !mapW) return;
  state.mapView = fitMapBounds(positions, mapW, mapH);
  applyMapTransform(animate);
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
  // Center on the marker's geographic position; fall back to a fresh projection if the cache is cold.
  const pos = markerFractions.get(cellId) || markerPos(row, mapProjection(rows));
  const cluster = mapClusterGroups.find((group) =>
    group.members.some((member) => member.dataset.cell === cellId),
  );
  const k = Math.min(MAX_ZOOM, Math.max(state.mapView.zoom, cluster?.revealZoom || 6));
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
    pointers.set(e.pointerId, local(e));
    mapDidDrag = false;
    if (pointers.size === 1) {
      mapWasMultiTouch = false;
      startDrag(pointers.get(e.pointerId));
      map.classList.add("dragging");
    } else if (pointers.size === 2) {
      mapWasMultiTouch = true;
      // A tap must retain its button target so native click activation reaches markers and clusters.
      // Capture only once the gesture is unambiguously a pinch (or, below, a drag).
      for (const pointerId of pointers.keys()) {
        try {
          map.setPointerCapture(pointerId);
        } catch {
          /* A browser may have already ended one pointer between the two events. */
        }
      }
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
      if (Math.abs(dx) + Math.abs(dy) > 4) {
        mapDidDrag = true;
        if (!map.hasPointerCapture(e.pointerId)) {
          try {
            map.setPointerCapture(e.pointerId);
          } catch {
            /* Pointer capture is an enhancement; document-level pointer delivery may already own it. */
          }
        }
      }
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
    // Rebuild overview groups when the map box changes size (including responsive reflow). Their
    // hit targets stay a fixed physical size while geographic distances shrink, so merely moving
    // the old groups would let controls overlap after a resize.
    new ResizeObserver(() => {
      if (!mapVisible || mapResizePending) return;
      mapResizePending = true;
      requestAnimationFrame(() => {
        mapResizePending = false;
        const center = mapCameraCenter();
        measureMap();
        const geometryChanged =
          Math.abs(mapW - mapLayoutW) > 1 ||
          Math.abs(mapH - mapLayoutH) > 1 ||
          state.textStep !== mapLayoutTextStep;
        if (geometryChanged && current().length) {
          restoreMapCameraCenter(center);
          renderMap(current());
        } else {
          applyMapTransform(false);
        }
      });
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

function sparkSeries(row, limit = 24) {
  const selectedTime = timestampMilliseconds(currentBucket());
  return state.cells
    .filter((cell) => {
      if (
        cell.cell_id !== row.cell_id ||
        cell.parameter !== state.parameter ||
        !isDisplayVariant(cell, state.parameter)
      )
        return false;
      const time = timestampMilliseconds(cell.bucket);
      return time != null && (selectedTime == null || time <= selectedTime);
    })
    .sort((a, b) => timestampMilliseconds(a.bucket) - timestampMilliseconds(b.bucket))
    .slice(-limit);
}

function calibratedEvidenceSeries(published) {
  const isProvisional = (item) => Boolean(item?.row?.provisional ?? item?.provisional);
  const confirmed = published.filter((item) => !isProvisional(item));
  return {
    series: confirmed.length ? confirmed : published,
    allProvisional: confirmed.length === 0,
    excludedProvisional: confirmed.length ? published.length - confirmed.length : 0,
  };
}

function sparkSegmentPath(segment, pointCoordinates, step = false) {
  const first = pointCoordinates(segment[0]);
  let d = `M${first.x.toFixed(1)},${first.y.toFixed(1)}`;
  for (let index = 1; index < segment.length; index += 1) {
    const previous = pointCoordinates(segment[index - 1]);
    const point = pointCoordinates(segment[index]);
    if (step) d += ` L${point.x.toFixed(1)},${previous.y.toFixed(1)}`;
    d += ` L${point.x.toFixed(1)},${point.y.toFixed(1)}`;
  }
  return d;
}

// A tiny sparkline of this location's latest published observations at or before the selected
// bucket. The SVG is decorative; its accessible label states count, time span, low, and high.
function renderSpark(row) {
  const el = $("#detail-spark");
  el.textContent = "";
  el.removeAttribute("role");
  el.removeAttribute("aria-label");
  if (!state.historyLoaded) return;
  const published = sparkSeries(row);
  // Never combine calibrated and raw points into one unqualified line. Prefer confirmed evidence;
  // if none exists, retain the provisional shape but mark it rough in both style and accessible text.
  const { series, allProvisional, excludedProvisional } = calibratedEvidenceSeries(published);
  if (series.length < 3) return;
  const vals = series.map((c) => convert(c.mean));
  const min = Math.min(...vals);
  const max = Math.max(...vals);
  const span = max - min || 1;
  const W = 132;
  const H = 30;
  const pad = 3;
  const firstTime = timestampMilliseconds(series[0].bucket);
  const lastTime = timestampMilliseconds(series[series.length - 1].bucket);
  const timeSpan = Math.max(1, lastTime - firstTime);
  const plotted = series.map((seriesRow, i) => ({
    row: seriesRow,
    index: i,
    timestamp: timestampMilliseconds(seriesRow.bucket),
    value: vals[i],
  }));
  const pointCoordinates = (point) => {
    const x = pad + ((point.timestamp - firstTime) / timeSpan) * (W - 2 * pad);
    const y = H - pad - ((point.value - min) / span) * (H - 2 * pad);
    return { x, y };
  };
  const pointText = (point) => {
    const { x, y } = pointCoordinates(point);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  };
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.setAttribute("class", "spark-svg");
  if (allProvisional) svg.classList.add("provisional");
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("focusable", "false");
  for (const segment of seriesSegments(plotted)) {
    if (segment.length < 2) continue;
    const path = document.createElementNS(ns, "path");
    path.setAttribute(
      "d",
      sparkSegmentPath(segment, pointCoordinates, state.parameter === "exposure"),
    );
    path.setAttribute("fill", "none");
    path.setAttribute("stroke", "currentColor");
    path.setAttribute("stroke-width", "1.5");
    svg.appendChild(path);
  }
  for (const point of plotted) {
    const [cx, cy] = pointText(point).split(",");
    const dot = document.createElementNS(ns, "circle");
    dot.setAttribute("cx", cx);
    dot.setAttribute("cy", cy);
    dot.setAttribute("r", "1.5");
    dot.setAttribute("fill", "currentColor");
    svg.appendChild(dot);
  }
  el.appendChild(svg);
  el.setAttribute("role", "img");
  let label = t("spark-label", {
    n: formatNumber(series.length),
    start: fmtBucket(series[0].bucket),
    end: fmtBucket(series[series.length - 1].bucket),
    low: formatMagnitude(min),
    high: formatMagnitude(max),
    unit: "",
  });
  if (allProvisional) {
    label += ` ${t("spark-all-provisional")}`;
  } else if (excludedProvisional) {
    label += ` ${t("spark-provisional-excluded", { n: excludedProvisional })}`;
  }
  el.setAttribute("aria-label", label);
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
    line = t(key, { a: an, b: bn });
  } else {
    const heatLike = state.parameter === "temp_c" || state.parameter === "heat_index_c";
    const d = round1(convert(a.mean) - convert(b.mean));
    if (Math.abs(d) < 0.1) {
      line = t("compare-same", { a: an, b: bn });
    } else {
      const key = d > 0 ? (heatLike ? "compare-hotter" : "compare-higher") : heatLike ? "compare-cooler" : "compare-lower";
      line = t(key, { a: an, b: bn, d: formatDifference(d), unit: "" });
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
  let line = t("alert-line", {
    place: placeName(row),
    param,
    reading: watchReadingText(row),
    threshold: watchThresholdText(row.parameter, watch),
    time: fmtBucket(row.bucket),
  });
  if (row.provisional) line += " " + t("alert-provisional");
  if (!isFreshObservation(row.bucket)) line += " " + t("alert-stale");
  return line;
}

// Every watched location whose newest published reading is at/over its level. The slider is an
// evidence browser; historical scrubbing must never arm, clear, or fire a time-sensitive alert.
function activeAlerts() {
  const watches = loadWatches();
  const bucket = latestBucket();
  const out = [];
  for (const [key, watch] of Object.entries(watches)) {
    const sep = key.lastIndexOf("|");
    if (sep < 0) continue;
    const cellId = key.slice(0, sep);
    const parameter = key.slice(sep + 1);
    const row = state.cells.find(
      (c) =>
        c.cell_id === cellId &&
        c.parameter === parameter &&
        c.bucket === bucket &&
        isDisplayVariant(c, parameter),
    );
    if (row && watchCrossed(row, watch)) out.push({ key, row, watch });
  }
  return out;
}

function showAlertObservation(cellId, parameter, bucket) {
  const exact = state.cells.some(
    (row) =>
      row.cell_id === cellId &&
      row.parameter === parameter &&
      row.bucket === bucket &&
      isDisplayVariant(row, parameter),
  );
  if (!exact) {
    const status = $("#area-alerts-status") || $("#status");
    if (status) {
      status.textContent = t("alert-observation-unavailable", { time: fmtBucket(bucket) });
    }
    return false;
  }
  stopPlay();
  if (VALID_PARAMS.has(parameter)) {
    state.parameter = parameter;
    const parameterSelect = $("#parameter-select");
    if (parameterSelect) parameterSelect.value = parameter;
  }
  const bucketIndex = state.buckets.indexOf(bucket);
  if (bucketIndex >= 0) {
    state.bucketIdx = bucketIndex;
    includeBucketInRange(bucketIndex);
    const slider = $("#time-slider");
    if (slider) slider.value = String(bucketIndex);
    rememberCurrentBucket();
  }
  select(cellId, true);
  return true;
}

// The Alerts banner: every watched location that is at/over its level right now, in plain language,
// with a button that selects it. It only ever reports crossings — it never says "you're safe" when
// under (R: no false safety), it just shows nothing. Hidden when there are no alerts.
function renderAlerts() {
  const section = $("#alerts");
  const list = $("#alerts-list");
  const status = $("#alerts-status");
  if (!section || !list) return;
  const focusedKey = document.activeElement?.closest?.("#alerts-list button")?.dataset?.alertKey;
  const alerts = activeAlerts();
  list.textContent = "";
  if (!alerts.length) {
    section.hidden = true;
    if (status?.textContent) status.textContent = "";
    return;
  }
  section.hidden = false;
  let restoreFocus = null;
  const announcement = [];
  for (const { key, row, watch } of alerts) {
    const li = document.createElement("li");
    const text = document.createElement("span");
    text.className = "alert-text";
    const line = alertText(row, watch);
    text.textContent = line;
    announcement.push(line);
    const go = document.createElement("button");
    go.type = "button";
    go.className = "linklike";
    go.dataset.alertKey = key;
    go.textContent = t("alert-go");
    go.addEventListener("click", () => {
      showAlertObservation(row.cell_id, row.parameter, row.bucket);
      [...list.querySelectorAll("button")].find(
        (button) => button.dataset.alertKey === key,
      )?.focus({ preventScroll: true });
    });
    if (key === focusedKey) restoreFocus = go;
    li.append(text, document.createTextNode(" "), go);
    list.appendChild(li);
  }
  const nextAnnouncement = announcement.join(" ");
  if (status && status.textContent !== nextAnnouncement) status.textContent = nextAnnouncement;
  restoreFocus?.focus({ preventScroll: true });
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
    isFreshObservation(latestBucket()) &&
    "Notification" in window &&
    Notification.permission === "granted";
  for (const { key, row, watch } of alerts) {
    if (firing.has(key)) continue; // already firing — don't re-notify until it clears
    if (!canNotify) continue;
    firing.add(key);
    try {
      const body = t("notify-body", {
        reading: watchReadingText(row),
        threshold: watchThresholdText(row.parameter, watch),
        time: fmtBucket(row.bucket),
      });
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

// -- neighborhood alerts (the generated, subscribable feed) ------------------
//
// Distinct from the personal "watch" above: this is the public, network-wide feed of areas that have
// crossed a documented danger threshold (EPA AQI 101 / NWS Danger / exposure High). It loads from the
// live API when served, or the baked alerts.json on the static site, and offers a per-area Atom feed
// link so a resident subscribes to their neighborhood in any ordinary RSS/Atom reader — no account.
async function loadAreaAlerts() {
  const live = isStaticDeployment() ? null : await fetchJson("api/alerts.json");
  const feed = live || (await fetchJson("alerts.json"));
  if (!feed || !Array.isArray(feed.alerts)) return;
  state.areaAlerts = feed;
  state.alertsLive = !!live;
  // The Atom feed sits beside whichever JSON we loaded; resolve it to an absolute, shareable URL.
  state.alertsXmlUrl = new URL(live ? "api/alerts.xml" : "alerts.xml", location.href).href;
  // The Spanish Atom feed (machine-translated, see swelter.i18n_alerts) sits right beside it.
  const esFeedLink = $("#aa-es-feed-link");
  if (esFeedLink) {
    esFeedLink.href = live ? "api/alerts.es.xml" : "alerts.es.xml";
  }
  $("#area-alerts").hidden = false;
  renderAreaAlerts();
}

// Localize one alert's severity word using the same maps the rest of the UI uses.
function alertSeverityText(alert) {
  if (alert.parameter === "pm25_ugm3") return localCategory(alert.severity);
  if (alert.parameter === "heat_index_c") return localHeat(alert.severity);
  if (alert.parameter === "exposure") return localExposure(alert.severity);
  return alert.severity;
}

function alertSentence(alert) {
  const sev = alertSeverityText(alert);
  if (alert.parameter === "pm25_ugm3") {
    return t("aa-air", {
      area: alert.area,
      sev,
      aqi: formatNumber(alert.aqi, { maximumFractionDigits: 0 }),
      time: fmtBucket(alert.bucket),
    });
  }
  if (alert.parameter === "heat_index_c") {
    return t("aa-heat", { area: alert.area, sev, time: fmtBucket(alert.bucket) });
  }
  return t("aa-exposure", { area: alert.area, sev, time: fmtBucket(alert.bucket) });
}

// Build the area <select> from every published cell (so a resident can pick their block and copy its
// feed even on a calm day), rebuilt only when the cell set changes so a held selection survives.
function buildAreaSelect() {
  const sel = $("#area-select");
  if (!sel) return;
  const ids = [...new Set(state.cells.map((c) => c.cell_id))].sort();
  const key = ids.join("|");
  const whole0 = sel.querySelector('option[value=""]');
  if (key === state.areaSelectKey && whole0) {
    whole0.textContent = t("aa-whole-network"); // keep the first option localized on a language swap
    return;
  }
  state.areaSelectKey = key;
  const byId = new Map(state.cells.map((c) => [c.cell_id, c]));
  sel.textContent = "";
  const whole = document.createElement("option");
  whole.value = "";
  whole.textContent = t("aa-whole-network");
  sel.appendChild(whole);
  for (const id of ids) {
    const opt = document.createElement("option");
    opt.value = id;
    opt.textContent = placeName(byId.get(id));
    sel.appendChild(opt);
  }
  sel.value = state.areaSelected;
  if (sel.value !== state.areaSelected) state.areaSelected = sel.value; // selection was filtered out
}

function areaAlertStatus(feed, scoped) {
  const publishedAt = feed.generated || scoped[0]?.bucket || "";
  const stale = observationAgeMinutes(publishedAt) > CURRENT_OBSERVATION_MAX_AGE_MINUTES;
  const line = scoped.length
    ? t("aa-count", { n: scoped.length, time: fmtBucket(publishedAt) })
    : t("aa-none", { time: fmtBucket(publishedAt) });
  return stale ? `${line} ${t("aa-stale")}` : line;
}

function renderAreaAlerts() {
  const feed = state.areaAlerts;
  if (!feed) return;
  buildAreaSelect();
  const list = $("#area-alerts-list");
  const status = $("#area-alerts-status");
  const focusedKey = document.activeElement?.closest?.("#area-alerts-list button")?.dataset?.alertKey;
  list.textContent = "";
  const scoped = state.areaSelected
    ? feed.alerts.filter((a) => a.area_id === state.areaSelected)
    : feed.alerts;
  status.textContent = areaAlertStatus(feed, scoped);
  let restoreFocus = null;
  for (const alert of scoped) {
    const li = document.createElement("li");
    li.className = "aa-item";
    if (alert.provisional) li.classList.add("provisional");
    const text = document.createElement("span");
    text.className = "aa-text";
    text.textContent = alertSentence(alert);
    li.appendChild(text);
    if (alert.provisional) {
      const prov = document.createElement("span");
      prov.className = "aa-prov";
      prov.textContent = ` ${t("aa-prov")}`;
      li.appendChild(prov);
    }
    const go = document.createElement("button");
    go.type = "button";
    go.className = "aa-go";
    const alertKey =
      alert.id || `${alert.area_id}|${alert.parameter}|${alert.bucket}|${alert.severity}`;
    go.dataset.alertKey = alertKey;
    go.textContent = t("aa-go");
    go.addEventListener("click", () => {
      if (!showAlertObservation(alert.area_id, alert.parameter, alert.bucket)) return;
      setView("tab-list");
      const selectedButton = [...document.querySelectorAll("#panel-list .row-select")].find(
        (button) => button.dataset.cell === alert.area_id,
      );
      selectedButton?.focus({ preventScroll: true });
    });
    if (alertKey === focusedKey) restoreFocus = go;
    li.appendChild(go);
    list.appendChild(li);
  }
  restoreFocus?.focus({ preventScroll: true });
}

function areaFeedUrl() {
  if (!state.alertsXmlUrl) return "";
  // Per-area filtering is a query the live API honors; the static feed is whole-network only.
  if (state.areaSelected && state.alertsLive) {
    return `${state.alertsXmlUrl}?area=${encodeURIComponent(state.areaSelected)}`;
  }
  return state.alertsXmlUrl;
}

// -- cooling-center overlay --------------------------------------------------
//
// A curated, provenance-bearing dataset of public places to cool down. The list is the accessible
// equivalent (always rendered when the section is shown); the map overlay is a visual enhancement on
// top, toggled on demand. Loaded from the live API or the baked file; absent → the section stays hidden.
async function loadCoolingCenters() {
  const doc = isStaticDeployment()
    ? await fetchJson("cooling-centers.geojson")
    : (await fetchJson("api/cooling-centers.geojson")) ||
      (await fetchJson("cooling-centers.geojson"));
  if (!doc || !Array.isArray(doc.features) || !doc.features.length) return;
  state.coolingCenters = doc.features
    .filter((f) => f.geometry && Array.isArray(f.geometry.coordinates))
    .map((f) => ({
      lon: +f.geometry.coordinates[0],
      lat: +f.geometry.coordinates[1],
      ...f.properties,
    }));
  state.coolingMeta = doc.metadata || {};
  $("#cooling-centers").hidden = false;
  renderCoolingCenters();
}

function coolingTypeLabel(type) {
  const key = `cool-type-${type}`;
  const text = t(key);
  return text === key ? type : text;
}

function renderCoolingCenters() {
  const centers = state.coolingCenters;
  if (!centers) return;
  const list = $("#cooling-list");
  list.textContent = "";
  // If a location is selected, sort by distance and annotate it — turns the list into "nearest cool
  // place to where I am looking", the equity-relevant question on a hot day.
  const sel = current().find((r) => r.cell_id === state.selected);
  const withDist = centers.map((c) => ({
    c,
    km: sel ? haversine(sel.lat, sel.lon, c.lat, c.lon) : null,
  }));
  if (sel) withDist.sort((a, b) => a.km - b.km);
  for (const { c, km } of withDist) {
    const li = document.createElement("li");
    li.className = "cool-item";
    const name = document.createElement("strong");
    name.textContent = c.name;
    li.appendChild(name);
    const meta = document.createElement("span");
    meta.className = "cool-meta";
    const bits = [coolingTypeLabel(c.type || "public")];
    if (c.address) bits.push(c.address);
    if (c.hours) bits.push(t("cool-hours", { hours: c.hours }));
    bits.push(c.air_conditioned === false ? t("cool-no-ac") : t("cool-ac"));
    bits.push(c.accessible === false ? t("cool-not-accessible") : t("cool-accessible"));
    if (km != null)
      bits.push(
        t("cool-distance", {
          km: formatNumber(km, { minimumFractionDigits: 1, maximumFractionDigits: 1 }),
        }),
      );
    meta.textContent = ` — ${bits.join(" · ")}`;
    li.appendChild(meta);
    if (c.notes) {
      const note = document.createElement("span");
      note.className = "cool-note";
      note.textContent = ` ${c.notes}`;
      li.appendChild(note);
    }
    list.appendChild(li);
  }
  const meta = state.coolingMeta || {};
  $("#cooling-source").textContent = t("cooling-source", {
    attribution: meta.attribution || meta.source || "",
    date: meta.last_verified || "—",
  });
}

function toggleCooling() {
  state.coolingVisible = !state.coolingVisible;
  const btn = $("#cooling-toggle");
  btn.setAttribute("aria-pressed", String(state.coolingVisible));
  btn.textContent = t(state.coolingVisible ? "cooling-hide" : "cooling-show");
  // Re-render the map so the overlay appears/disappears; announce the change for screen readers.
  if (mapVisible) renderMap(current());
  else mapDirty = true;
  $("#display-status").textContent = t(state.coolingVisible ? "cooling-shown" : "cooling-hidden");
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
      opt.textContent = t("watch-at-or-worse", { level: localize(name) });
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
    unit.textContent = unitContextLabel();
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
  const selectedTime = timestampMilliseconds(currentBucket());
  const byDay = new Map();
  for (const c of state.cells) {
    if (
      c.cell_id !== row.cell_id ||
      c.parameter !== state.parameter ||
      !isDisplayVariant(c, state.parameter)
    )
      continue;
    const d = new Date(c.bucket);
    if (!Number.isFinite(d.getTime()) || (selectedTime != null && d.getTime() > selectedTime)) {
      continue;
    }
    const key = `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
    let day = byDay.get(key);
    if (!day) {
      day = {
        t: d.getTime(),
        label: fmtDay(d),
        vals: [],
        cats: [],
        provisionalVals: [],
        provisionalCats: [],
        provisionalCount: 0,
      };
      byDay.set(key, day);
    }
    const vals = c.provisional ? day.provisionalVals : day.vals;
    const cats = c.provisional ? day.provisionalCats : day.cats;
    if (c.provisional) day.provisionalCount += 1;
    if (typeof c.mean === "number") vals.push(c.mean);
    if (c.category) cats.push(c.category);
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
    const useProvisional = !day.vals.length && !day.cats.length;
    const summaryVals = useProvisional ? day.provisionalVals : day.vals;
    const summaryCats = useProvisional ? day.provisionalCats : day.cats;
    if (categorical && summaryCats.length) {
      const worst = summaryCats.reduce((a, b) => (order.indexOf(b) > order.indexOf(a) ? b : a));
      li.textContent = t("history-worst", { day: day.label, cat: localize(worst) });
    } else if (summaryVals.length) {
      const hi = formatMagnitude(convert(Math.max(...summaryVals)));
      const lo = formatMagnitude(convert(Math.min(...summaryVals)));
      li.textContent = t("history-highlow", { day: day.label, high: hi, low: lo, unit: "" });
    } else {
      continue;
    }
    const provisionalCount = day.provisionalCount;
    if (useProvisional) {
      li.textContent += ` ${t("history-all-provisional", { n: provisionalCount })}`;
    } else if (provisionalCount) {
      li.textContent += ` ${t("history-provisional-excluded", { n: provisionalCount })}`;
    }
    list.appendChild(li);
  }
}

function renderDetail() {
  const panel = $("#detail");
  const empty = $("#inspector-empty");
  if (!state.selected) {
    panel.hidden = true;
    if (empty) {
      empty.hidden = false;
      empty.textContent = t("inspector-empty");
    }
    return;
  }
  const row = current().find((r) => r.cell_id === state.selected);
  if (!row) {
    panel.hidden = true;
    if (empty) {
      const reference =
        referenceRowFor(state.selected) || state.cells.find((cell) => cell.cell_id === state.selected);
      empty.hidden = false;
      empty.textContent = selectedGapText(reference);
    }
    return;
  }
  panel.hidden = false;
  if (empty) empty.hidden = true;
  $("#detail-heading").textContent = placeName(row);
  $("#detail-body").textContent = describe(row);
  renderSpark(row);
  const temporalContext = temporalContextText(row.bucket);
  $("#detail-context").textContent = [temporalContext, contrastLine(row)].filter(Boolean).join(" ");
  $("#detail-trend").textContent = trendLine(row);
  $("#detail-yesterday").textContent = dayChangeLine(row);
  renderHistory(row);
  // Guidance follows the dominant hazard. A compound/tied elevated exposure carries BOTH heat and
  // air guidance rather than silently discarding one side of a joint event.
  const guidance = guidanceForRow(row);
  $("#detail-guidance").textContent = [
    temporalContext ? t("guidance-associated") : "",
    guidance,
  ]
    .filter(Boolean)
    .join(" ");
  $("#action-heading").textContent = t(
    temporalContext ? "act-heading-associated" : "act-heading",
  );
  const src = $(".guidance-source");
  src.textContent = guidanceSourceForRow(row);
  src.hidden = !guidance;
  renderActions(row);
  renderProvenance(row);
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
    setBucketIndex((state.bucketIdx + 1) % state.buckets.length);
  }, 1100);
  syncPlay();
}

function togglePlay() {
  if (isPlaying()) stopPlay();
  else startPlay();
}

let renderRevision = 0;
function render() {
  const revision = ++renderRevision;
  const bucket = currentBucket();
  $("#time-readout").textContent = fmtBucket(bucket);
  const slider = $("#time-slider");
  if (slider) slider.setAttribute("aria-valuetext", fmtBucket(bucket));
  const rows = current();
  $("#status").textContent = t("status", { n: formatNumber(rows.length) });
  renderHeadline();
  // Paint the resident-facing "now" answer synchronously, before the deferred evidence workspace. It
  // is the above-the-fold Largest Contentful element, so filling it here (rather than a frame later)
  // both lands its final height in the first layout — no late reflow / cumulative layout shift — and
  // improves LCP. The deferred workspace reuses this focus row for the braid rather than repainting it.
  const focusRow = renderNow(rows);
  updateLegend();
  $("#main")?.setAttribute("aria-busy", "true");
  document.documentElement.removeAttribute("data-render-ready");

  // Let the resident-facing answer above the fold paint before mounting the dense linked evidence
  // workspace. A second animation frame guarantees one paint opportunity without an arbitrary timer.
  requestAnimationFrame(() =>
    requestAnimationFrame(() => {
      if (revision !== renderRevision) return;
      updateAlerts();
      renderAreaAlerts();
      renderCoolingCenters();
      renderSettingsState();
      renderOverview();
      renderObservatory(rows, focusRow);
      renderActiveRepresentation(rows);
      renderDetail();
      syncPlay();
      $("#main")?.setAttribute("aria-busy", "false");
      document.documentElement.setAttribute("data-render-ready", "true");
    }),
  );
}

// Map, List, and Table are equivalent routes through the same readings, not three surfaces a reader
// needs at once. Keep only the active representation in the DOM. This cuts the initial node count by
// well over half on a 150-location network while preserving every row when its tab is selected.
function renderActiveRepresentation(rows) {
  const active = document.querySelector('[role="tab"][aria-selected="true"]')?.id || "tab-map";
  const list = $("#data-list");
  const table = $("#data-table-body");
  const map = $("#map");

  if (active === "tab-list") renderList(rows);
  else list?.replaceChildren();

  if (active === "tab-table") renderTable(rows);
  else table?.replaceChildren();

  mapVisible = active === "tab-map";
  if (mapVisible) {
    renderMap(rows);
    mapDirty = false;
  } else {
    map?.replaceChildren();
    mapDirty = true;
  }
}

// focusMap=true centers the map on the pick (a map marker tap, geolocation, or a search hit). A
// plain List/Table row click leaves the map where it is so browsing never yanks a hidden map around.
function select(cellId, focusMap = false) {
  if (cellId !== state.selected) $("#watch-status").textContent = ""; // a new pick clears stale feedback
  state.selected = cellId;
  // Selecting can change the inspector grid and therefore the map's measured width. Remember the
  // requested focus so the newly rendered map refits the location using its final dimensions; the
  // immediate zoom below keeps the interaction responsive in the meantime.
  if (focusMap) state.pendingFocus = cellId;
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
    if (eq > 0) {
      try {
        out[part.slice(0, eq)] = decodeURIComponent(part.slice(eq + 1));
      } catch {
        // A malformed/truncated percent-encoding in a copied, emailed, or hand-edited share link
        // must not throw here: this runs in init() before the first render, so an uncaught
        // URIError would blank the whole dashboard instead of just this one hash key.
      }
    }
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

// A slow history fetch must not reset a cursor the reader moved after the fast snapshot painted.
// Keep the latest interactive bucket in the same pending view used after data replacement. The
// initial deep-link timestamp remains untouched until an interaction occurs, so a timestamp absent
// from the one-hour snapshot can still resolve when the seven-day surface arrives.
function rememberCurrentBucket() {
  const bucket = currentBucket();
  if (bucket) pendingView.t = bucket;
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
      includeBucketInRange(idx);
      const slider = $("#time-slider");
      if (slider) slider.value = String(idx);
      render();
    }
  }
  if (!state.selected) {
    const id = pendingView.l || loadPrefs().cell;
    if (id && state.cells.some((c) => c.cell_id === id)) {
      select(id, true);
      if (pendingView.l === id) delete pendingView.l;
    }
  }
  // Restore a comparison partner: a shared #c= wins, else the one this browser last compared.
  if (!state.compareCell) {
    const partner = pendingView.c || loadPrefs().compare;
    if (partner && state.cells.some((c) => c.cell_id === partner)) {
      state.compareCell = partner;
      if (pendingView.c === partner) delete pendingView.c;
      if (state.selected) renderDetail();
    }
  }
  updateHash(); // make the address bar reflect the resolved view, so the share link is correct
}

function clearPendingLocationView() {
  delete pendingView.l;
  delete pendingView.c;
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
    ? t("settings-has", { n })
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
  $("#shortcuts-toggle") && ($("#shortcuts-toggle").checked = true); // back to the default (on)
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
  }
  mapVisible = tabId === "tab-map";
  if (!mapVisible) renderActiveRepresentation(current());
  if (mapVisible) {
    $("#data-list")?.replaceChildren();
    $("#data-table-body")?.replaceChildren();
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
        next.focus();
      }
    });
  });
}

function wirePrintTable() {
  window.addEventListener("beforeprint", () => renderTable(current()));
  window.addEventListener("afterprint", () => {
    if (document.querySelector('[role="tab"][aria-selected="true"]')?.id !== "tab-table") {
      $("#data-table-body")?.replaceChildren();
    }
  });
}

function scrollToSection(sectionId, { focus = false } = {}) {
  const section = document.getElementById(sectionId);
  section?.scrollIntoView({ block: "start" });
  if (focus) section?.focus({ preventScroll: true });
}

// In-page navigation must not replace the shareable p/t/l/c application fragment. Scroll under JS
// control and leave the current state hash intact.
function wireSectionNavigation() {
  const links = [
    ...document.querySelectorAll('.observatory-nav a[href^="#"]'),
    ...document.querySelectorAll('.skip-link[href^="#"]'),
  ];
  for (const link of links) {
    link.addEventListener("click", (event) => {
      const sectionId = link.getAttribute("href")?.slice(1);
      if (!sectionId || !document.getElementById(sectionId)) return;
      event.preventDefault();
      scrollToSection(sectionId, { focus: link.classList?.contains?.("skip-link") });
    });
  }
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
      $("#status").textContent = t("sort-announce", {
        col: button.textContent,
        dir: t(`dir-${dir}`),
      });
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
    status.textContent = t("text-size-set", {
      n: formatNumber(i + 1),
      max: formatNumber(TEXT_STEPS.length),
    });
  }
}

function setTextStep(step) {
  const center = mapVisible ? mapCameraCenter() : null;
  applyTextScale(step);
  savePref("textStep", state.textStep);
  if (mapVisible && current().length) {
    measureMap();
    restoreMapCameraCenter(center);
    renderMap(current());
  } else {
    mapDirty = true;
  }
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
        $("#status").textContent = t("locate-found", { place: placeName(best) });
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

function wireObservatory() {
  const start = $("#range-start");
  const end = $("#range-end");
  start?.addEventListener("input", () => setHistoryRange(start.value, end.value, "start"));
  end?.addEventListener("input", () => setHistoryRange(start.value, end.value, "end"));
  $("#range-reset")?.addEventListener("click", () => {
    stopPlay();
    const previousBucket = state.bucketIdx;
    resetHistoryRange();
    state.bucketIdx = state.rangeEnd;
    rememberCurrentBucket();
    const slider = $("#time-slider");
    if (slider) slider.value = String(state.bucketIdx);
    if (state.bucketIdx !== previousBucket) {
      updateHash();
      render();
    } else {
      renderHistoryWindowOnly();
    }
  });

  $("#now-open-evidence")?.addEventListener("click", (event) => {
    event.preventDefault();
    const cellId = event.currentTarget.getAttribute("data-cell");
    if (cellId) select(cellId, true);
    scrollToSection("explore");
  });

  const braid = $("#exposure-braid");
  braid?.addEventListener("click", (event) => {
    const point = event.target?.closest?.("[data-bucket-index]");
    if (point) {
      setBucketIndex(point.getAttribute("data-bucket-index"), { pause: true });
      announceBraidSelection();
      return;
    }
    const svg = event.target?.closest?.("svg");
    const bounds = svg?.getBoundingClientRect?.();
    if (!svg || !bounds || bounds.width <= 0 || !Number.isFinite(event.clientX)) return;
    const svgFraction = (event.clientX - bounds.left) / bounds.width;
    const plotStart = BRAID_PLOT_LEFT / BRAID_WIDTH;
    const plotWidth = (BRAID_WIDTH - BRAID_PLOT_LEFT - BRAID_PLOT_RIGHT) / BRAID_WIDTH;
    const plotFraction = (svgFraction - plotStart) / plotWidth;
    const row = focusRow(current()) || (state.selected ? referenceRowFor(state.selected) : null);
    const next = nearestSeriesIndex(seriesPointsFor(row?.cell_id), plotFraction);
    if (next != null) {
      setBucketIndex(next, { pause: true });
      announceBraidSelection();
    }
  });
  braid?.addEventListener("keydown", (event) => {
    let next = null;
    if (event.key === "ArrowLeft") next = Math.max(state.rangeStart, state.bucketIdx - 1);
    if (event.key === "ArrowRight") next = Math.min(state.rangeEnd, state.bucketIdx + 1);
    if (event.key === "Home") next = state.rangeStart;
    if (event.key === "End") next = state.rangeEnd;
    if (next != null) {
      event.preventDefault();
      setBucketIndex(next, { pause: true });
      announceBraidSelection();
    }
  });
}

function wireControls() {
  $("#parameter-select").addEventListener("change", (e) => {
    state.parameter = e.target.value;
    updateHash();
    render();
  });
  $("#time-slider").addEventListener("input", (e) => {
    setBucketIndex(Number(e.target.value), { pause: true });
  });
  $("#time-play").addEventListener("click", togglePlay);
  $("#lang-select").addEventListener("change", async (e) => {
    const requested = e.target.value;
    if (!(await loadStrings(requested))) {
      e.target.value = document.documentElement.lang || "en";
      return;
    }
    savePref("lang", requested);
    localizeDocumentMetadata();
    renderDemoContract();
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
  $("#area-select")?.addEventListener("change", (e) => {
    state.areaSelected = e.target.value;
    renderAreaAlerts();
    $("#aa-copy-status").textContent = "";
  });
  $("#aa-copy-feed")?.addEventListener("click", async () => {
    const url = areaFeedUrl();
    try {
      await navigator.clipboard.writeText(url);
      $("#aa-copy-status").textContent = t("aa-copied");
    } catch {
      $("#aa-copy-status").textContent = t("aa-copy-fail");
    }
  });
  $("#cooling-toggle")?.addEventListener("click", toggleCooling);
  $("#text-smaller")?.addEventListener("click", () => setTextStep(state.textStep - 1));
  $("#text-bigger")?.addEventListener("click", () => setTextStep(state.textStep + 1));
  $("#contrast-toggle")?.addEventListener("click", () => setContrast(!state.contrast));
  $("#settings-clear")?.addEventListener("click", clearSettings);
  $("#settings")?.addEventListener("toggle", renderSettingsState); // refresh the count when opened
  $("#locate").addEventListener("click", locate);
  $("#place-search").addEventListener("input", (e) => {
    state.search = e.target.value;
    if (state.search) {
      clearPendingLocationView();
      state.selected = null;
      state.compareCell = null;
      savePref("cell", null);
      savePref("compare", null);
      updateHash();
    }
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
  const shareCard = $("#share-card");
  if (shareCard)
    shareCard.addEventListener("click", () => {
      const row = current().find((r) => r.cell_id === state.selected);
      if (!row) return;
      saveShareCard(row);
    });
}

function smallScreen() {
  return window.matchMedia("(max-width: 40rem)").matches;
}

// Honesty about connectivity: this dashboard is a PWA and keeps working from cache, so when the
// device drops offline it still shows the last readings it loaded — say so plainly rather than let a
// reader trust possibly-stale numbers as live. navigator.onLine flips the banner; the network's own
// freshness line still reports how old the data is.
function updateOnline() {
  const el = $("#offline");
  if (el) el.hidden = navigator.onLine !== false;
}

function wireOnline() {
  window.addEventListener("online", updateOnline);
  window.addEventListener("offline", updateOnline);
  updateOnline();
}

// Keyboard shortcuts for the power user: switch views (l/t/m) and jump to search (/). Single-key
// shortcuts must be defeatable to satisfy WCAG 2.1.4, so they are on by default but can be turned off
// in the footer (persisted), and they never fire while typing in a field or with a modifier held.
function shortcutsEnabled() {
  return loadPrefs().shortcuts !== false; // default on
}

function setShortcuts(on) {
  savePref("shortcuts", !!on);
  const cb = $("#shortcuts-toggle");
  if (cb) cb.checked = !!on;
}

function wireShortcuts() {
  const cb = $("#shortcuts-toggle");
  if (cb) {
    cb.checked = shortcutsEnabled();
    cb.addEventListener("change", () => setShortcuts(cb.checked));
  }
  document.addEventListener("keydown", (e) => {
    if (!shortcutsEnabled() || e.metaKey || e.ctrlKey || e.altKey) return;
    const el = e.target;
    const tag = (el.tagName || "").toLowerCase();
    if (tag === "input" || tag === "select" || tag === "textarea" || el.isContentEditable) return;
    switch (e.key) {
      case "l":
        setView("tab-list");
        break;
      case "t":
        setView("tab-table");
        break;
      case "m":
        setView("tab-map");
        break;
      case "/":
        e.preventDefault();
        $("#place-search")?.focus();
        break;
      default:
        return;
    }
  });
}

// The live demo deploys a primary route plus a community-sensor route. The build-generated contract
// supplies the active route's actual source label after fallback selection; this function owns only
// base-path-agnostic links and current-page semantics (works under /swelter/).
function wireSourceSwitch() {
  const cams = $("#switch-cams");
  const sensors = $("#switch-sensors");
  if (!cams || !sensors) return;
  const onSensors = location.pathname.replace(/\/+$/, "").endsWith("/sensors");
  cams.setAttribute("href", onSensors ? "../" : "./");
  sensors.setAttribute("href", onSensors ? "./" : "sensors/");
  (onSensors ? sensors : cams).setAttribute("aria-current", "page");
  renderDemoContract();
}

async function init() {
  const prefs = loadPrefs();
  const startLang = prefs.lang === "es" ? "es" : "en"; // restore the reader's language
  // Start the independent boot fetches together so the largest-contentful-paint is not gated by a
  // chain of sequential round-trips: the demo contract, string catalogue, and basemap have no
  // interdependency. The surface snapshot waits only for the demo probe, which decides its URL — a
  // live server must not eat a speculative fetch of the static fallback. Static builds publish
  // demo.json; a live server does not — one positive capability check replaces five guaranteed 404s
  // against nonexistent /api/* routes.
  const demoReady = loadDemoContract();
  const stringsReady = loadStrings(startLang);
  const basemapReady = loadBasemap();
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker
      .register("sw.js")
      .then((reg) => reg.update())
      .catch(() => {});
  }
  state.demo = await demoReady;
  // Fast first paint from a 1-hour snapshot, then enrich with history in the background (F16).
  const snapshotReady = isStaticDeployment()
    ? fetchSurface("sample-surface.json")
    : (async () =>
        (await fetchSurface("api/surface.json?hours=1")) ||
        (await fetchSurface("sample-surface.json")))();
  const stringsLoaded = await stringsReady;
  const effectiveLang = stringsLoaded ? startLang : document.documentElement.lang || "en";
  if (stringsLoaded && startLang !== "en") localizeDocumentMetadata();
  const langSel = $("#lang-select");
  if (langSel) langSel.value = effectiveLang;
  if (prefs.unit === "C" || prefs.unit === "F") {
    state.unit = prefs.unit;
    $("#unit-f").setAttribute("aria-pressed", String(state.unit === "F"));
    $("#unit-c").setAttribute("aria-pressed", String(state.unit === "C"));
  }
  applyTextScale(Number(prefs.textStep) || 0); // restore saved text size (no status announce at boot)
  $("#display-status").textContent = "";
  setContrast(prefs.contrast === true);
  wireTabs();
  wirePrintTable();
  wireSectionNavigation();
  wireSort();
  wireObservatory();
  wireControls();
  wireWatch();
  wireSourceSwitch();
  wireOnline();
  wireShortcuts();
  wireMap();
  // Phones/touch keep the low-friction List; larger screens open the linked map-first workspace.
  setView(smallScreen() ? "tab-list" : "tab-map");
  // Await the snapshot and basemap (both already in flight) before the first render, so the map box
  // is sized to the statewide geography on first paint with no late reflow.
  const snapshot = await snapshotReady;
  await basemapReady;
  if (!snapshot) {
    $("#status").textContent = t("no-data");
    $("#time-slider").setAttribute("aria-disabled", "true");
    return;
  }
  applyHashParameter(); // open on the shared measurement before the first paint
  setData(snapshot);
  state.historyLoaded = isStaticDeployment() && state.buckets.length > 1;
  render();
  restoreView();

  loadHealth();
  loadAreaAlerts();
  loadCoolingCenters();

  const full = isStaticDeployment()
    ? await fetchSurface("surface-7d.json")
    : await fetchSurface("api/surface.json?hours=168");
  if (full) {
    state.historyLoaded = true;
    setData(full);
    render();
    restoreView();
  }
}

init();
