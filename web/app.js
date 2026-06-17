// swelter dashboard logic — framework-free, no dependencies.
//
// One data source (the aggregated surface) drives three equal views: a plain List (default), a
// sortable Table, and a schematic Map. The map is never the only way in. Readings lead with the
// AQI + a named category for PM2.5; severity is announced in text; provisional (uncalibrated)
// blocks are rendered neutrally and never wear a confirmed category. Blocks are named, the time
// and category are localized, temperature can be shown in °F, and a sourced health-context line
// bridges the number to a decision without ever promising personal safety.

const PARAM_BASE_UNIT = {
  temp_c: "C",
  heat_index_c: "C",
  pm25_ugm3: "ug",
  pm10_ugm3: "ug",
  no2_ppb: "ppb",
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

const state = {
  cells: [],
  buckets: [],
  cellIndex: new Map(),
  parameter: "pm25_ugm3",
  bucketIdx: 0,
  unit: "F",
  sortKey: "value",
  sortDir: -1, // worst-first by default
  selected: null,
  search: "",
  strings: {},
  historyLoaded: false,
};

const $ = (sel) => document.querySelector(sel);

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

function setData(doc) {
  state.cells = doc.cells || [];
  state.buckets = doc.buckets || [...new Set(state.cells.map((c) => c.bucket))].sort();
  indexCells();
  state.bucketIdx = Math.max(0, state.buckets.length - 1);
  const slider = $("#time-slider");
  slider.max = String(Math.max(0, state.buckets.length - 1));
  slider.value = String(state.bucketIdx);
  slider.setAttribute("aria-disabled", state.buckets.length <= 1 ? "true" : "false");
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

function describe(row) {
  const place = placeName(row);
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

// -- rendering ---------------------------------------------------------------

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

    tr.appendChild(td(`${fmtValue(row.mean)}${fmtUncertainty(row.uncertainty)}`));

    const aqi = document.createElement("td");
    if (state.parameter === "pm25_ugm3" && row.category) {
      const tag = document.createElement("span");
      tag.className = `tag ${row.provisional ? "" : AQI_CLASS[row.category] || ""}`;
      tag.textContent = row.provisional
        ? `~AQI ${row.aqi}`
        : `AQI ${row.aqi} — ${localCategory(row.category)}`;
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

function renderMap(rows) {
  const map = $("#map");
  map.textContent = "";
  map.classList.toggle("dense", rows.length > 50); // shrink markers on a dense network
  if (!rows.length) return;
  const lats = rows.map((r) => r.lat);
  const lons = rows.map((r) => r.lon);
  const [minLat, maxLat, minLon, maxLon] = [
    Math.min(...lats),
    Math.max(...lats),
    Math.min(...lons),
    Math.max(...lons),
  ];
  const span = (v, lo, hi) => (hi === lo ? 0.5 : (v - lo) / (hi - lo));
  for (const row of rows) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "cell";
    btn.dataset.cell = row.cell_id;
    // Provisional cells stay neutral — they never wear a confirmed AQI color (F4).
    if (!row.provisional && state.parameter === "pm25_ugm3" && AQI_CLASS[row.category]) {
      btn.classList.add(AQI_CLASS[row.category]);
    }
    if (row.provisional) btn.classList.add("provisional");
    if (row.cell_id === state.selected) btn.classList.add("selected");
    btn.style.left = `${(0.06 + 0.88 * span(row.lon, minLon, maxLon)) * 100}%`;
    btn.style.bottom = `${(0.08 + 0.84 * span(row.lat, minLat, maxLat)) * 100}%`;
    btn.setAttribute("aria-label", describe(row));
    const value = document.createElement("span");
    value.textContent =
      state.parameter === "pm25_ugm3" ? `${row.aqi}` : `${Math.round(convert(row.mean))}`;
    btn.appendChild(value);
    const cat = document.createElement("span");
    cat.className = "cell-cat";
    cat.textContent =
      state.parameter === "pm25_ugm3"
        ? row.provisional
          ? t("state-provisional")
          : localCategory(row.category)
        : unitLabel();
    btn.appendChild(cat);
    btn.addEventListener("click", () => select(row.cell_id));
    map.appendChild(btn);
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
  const guidance = state.parameter === "pm25_ugm3" ? guidanceFor(row.category) : "";
  $("#detail-guidance").textContent = guidance;
  $(".guidance-source").hidden = !guidance;
}

function render() {
  const bucket = currentBucket();
  $("#time-readout").textContent = fmtBucket(bucket);
  const slider = $("#time-slider");
  if (slider) slider.setAttribute("aria-valuetext", fmtBucket(bucket));
  const rows = current();
  $("#status").textContent = t("status").replace("{n}", rows.length);
  renderHeadline();
  renderList(rows);
  renderTable(rows);
  renderMap(rows);
  renderDetail();
}

function select(cellId) {
  state.selected = cellId;
  render();
  const sel = document.querySelector(`[role="tabpanel"]:not([hidden]) [data-cell="${cellId}"]`);
  if (sel) sel.scrollIntoView({ block: "nearest" });
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
  render();
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
        select(best.cell_id);
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
    render();
  });
  $("#time-slider").addEventListener("input", (e) => {
    state.bucketIdx = Number(e.target.value);
    render();
  });
  $("#lang-select").addEventListener("change", async (e) => {
    await loadStrings(e.target.value);
    render();
  });
  $("#unit-f").addEventListener("click", () => setUnit("F"));
  $("#unit-c").addEventListener("click", () => setUnit("C"));
  $("#locate").addEventListener("click", locate);
  $("#place-search").addEventListener("input", (e) => {
    state.search = e.target.value;
    render();
  });
}

function smallScreen() {
  return window.matchMedia("(max-width: 40rem)").matches;
}

async function init() {
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker
      .register("sw.js")
      .then((reg) => reg.update())
      .catch(() => {});
  }
  await loadStrings("en");
  wireTabs();
  wireSort();
  wireControls();
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
  setData(snapshot);
  render();

  const full = await fetchSurface("api/surface.json?hours=72");
  if (full) {
    state.historyLoaded = true;
    setData(full);
    render();
  }
}

init();
