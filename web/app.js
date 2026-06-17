// swelter dashboard logic — framework-free, no dependencies.
//
// One data source (the aggregated surface) drives three equal views: a schematic map, a
// sortable table, and a plain list. The map is never the only way in — the table and list
// hold the identical dataset for any reader the map does not serve. Severity is announced in
// text; the time slider announces its value via an aria-live output.

const UNITS = {
  pm25_ugm3: "µg/m³",
  pm10_ugm3: "µg/m³",
  temp_c: "°C",
  heat_index_c: "°C",
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

const state = {
  cells: [],
  buckets: [],
  cellIndex: new Map(), // cell_id -> display number
  parameter: "pm25_ugm3",
  bucketIdx: 0,
  sortKey: null,
  sortDir: 1,
  strings: {},
};

const $ = (sel) => document.querySelector(sel);

async function loadStrings(lang) {
  try {
    const res = await fetch(`i18n/${lang}.json`);
    if (!res.ok) throw new Error("missing");
    state.strings = await res.json();
  } catch {
    state.strings = {};
  }
  document.documentElement.lang = lang;
  for (const el of document.querySelectorAll("[data-i18n]")) {
    const key = el.getAttribute("data-i18n");
    if (state.strings[key]) el.textContent = state.strings[key];
  }
}

async function loadData() {
  for (const url of ["api/surface.json?hours=72", "sample-surface.json"]) {
    try {
      const res = await fetch(url);
      if (!res.ok) continue;
      const doc = await res.json();
      state.cells = doc.cells || [];
      state.buckets = doc.buckets || [...new Set(state.cells.map((c) => c.bucket))].sort();
      return true;
    } catch {
      /* try the next source */
    }
  }
  return false;
}

function indexCells() {
  const ids = [...new Set(state.cells.map((c) => c.cell_id))].sort();
  state.cellIndex = new Map(ids.map((id, i) => [id, i + 1]));
}

function current() {
  const bucket = state.buckets[state.bucketIdx];
  let rows = state.cells.filter((c) => c.parameter === state.parameter && c.bucket === bucket);
  if (state.sortKey) {
    const k = state.sortKey;
    rows = [...rows].sort((a, b) => (a[k] > b[k] ? 1 : a[k] < b[k] ? -1 : 0) * state.sortDir);
  }
  return { bucket, rows };
}

function fmtBucket(bucket) {
  return bucket ? bucket.replace("T", " ").replace(":00Z", " UTC") : "—";
}

function unit() {
  return UNITS[state.parameter] || "";
}

function describe(row) {
  const num = `Cell ${state.cellIndex.get(row.cell_id)}`;
  let text = `${num}: ${row.mean} ${unit()}`;
  if (row.parameter === "pm25_ugm3" && row.category) {
    text += `, AQI ${row.aqi}, ${row.category}`;
  }
  if (row.provisional) text += " (provisional)";
  return text;
}

function renderMap(rows) {
  const map = $("#map");
  map.textContent = "";
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
    if (row.parameter === "pm25_ugm3" && AQI_CLASS[row.category]) {
      btn.classList.add(AQI_CLASS[row.category]);
    }
    if (row.provisional) btn.classList.add("provisional");
    btn.style.left = `${(0.06 + 0.88 * span(row.lon, minLon, maxLon)) * 100}%`;
    btn.style.bottom = `${(0.08 + 0.84 * span(row.lat, minLat, maxLat)) * 100}%`;
    btn.setAttribute("aria-label", describe(row));
    const value = document.createElement("span");
    value.textContent = `${Math.round(row.mean)}`;
    btn.appendChild(value);
    if (row.parameter === "pm25_ugm3" && row.category) {
      const cat = document.createElement("span");
      cat.className = "cell-cat";
      cat.textContent = row.category.split(" ")[0];
      btn.appendChild(cat);
    }
    map.appendChild(btn);
  }
}

function renderTable(rows) {
  const body = $("#data-table-body");
  body.textContent = "";
  for (const row of rows) {
    const tr = document.createElement("tr");
    const cell = document.createElement("th");
    cell.scope = "row";
    cell.textContent = `Cell ${state.cellIndex.get(row.cell_id)}`;
    tr.appendChild(cell);

    tr.appendChild(td(`${row.mean} ${unit()}`));

    const aqi = document.createElement("td");
    if (row.parameter === "pm25_ugm3" && row.category) {
      const tag = document.createElement("span");
      tag.className = `tag ${AQI_CLASS[row.category] || ""}`;
      tag.textContent = `AQI ${row.aqi} — ${row.category}`;
      aqi.appendChild(tag);
    } else {
      aqi.textContent = "—";
    }
    tr.appendChild(aqi);

    const stateCell = document.createElement("td");
    const tag = document.createElement("span");
    tag.className = `tag ${row.provisional ? "provisional" : ""}`;
    tag.textContent = row.provisional
      ? state.strings["state-provisional"] || "provisional"
      : state.strings["state-calibrated"] || "calibrated";
    stateCell.appendChild(tag);
    tr.appendChild(stateCell);

    body.appendChild(tr);
  }
}

function td(text) {
  const cell = document.createElement("td");
  cell.textContent = text;
  return cell;
}

function renderList(rows) {
  const list = $("#data-list");
  list.textContent = "";
  for (const row of rows) {
    const li = document.createElement("li");
    li.textContent = describe(row);
    list.appendChild(li);
  }
}

function render() {
  const { bucket, rows } = current();
  $("#time-readout").textContent = fmtBucket(bucket);
  const tmpl = state.strings["status"] || "{n} cells at {time}";
  $("#status").textContent = tmpl.replace("{n}", rows.length).replace("{time}", fmtBucket(bucket));
  renderMap(rows);
  renderTable(rows);
  renderList(rows);
}

function setView(tabId) {
  const tabs = [...document.querySelectorAll('[role="tab"]')];
  for (const tab of tabs) {
    const selected = tab.id === tabId;
    tab.setAttribute("aria-selected", String(selected));
    tab.tabIndex = selected ? 0 : -1;
    const panel = document.getElementById(tab.getAttribute("aria-controls"));
    panel.hidden = !selected;
  }
}

function wireTabs() {
  const tabs = [...document.querySelectorAll('[role="tab"]')];
  tabs.forEach((tab, i) => {
    tab.addEventListener("click", () => {
      setView(tab.id);
      tab.focus();
    });
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

function wireSort() {
  for (const button of document.querySelectorAll("th button[data-sort]")) {
    button.addEventListener("click", () => {
      const key = button.getAttribute("data-sort");
      state.sortDir = state.sortKey === key ? -state.sortDir : 1;
      state.sortKey = key;
      for (const th of document.querySelectorAll("th[aria-sort]")) {
        th.setAttribute("aria-sort", "none");
      }
      button.closest("th").setAttribute("aria-sort", state.sortDir === 1 ? "ascending" : "descending");
      render();
    });
  }
}

function wireControls() {
  $("#parameter-select").addEventListener("change", (e) => {
    state.parameter = e.target.value;
    render();
  });
  const slider = $("#time-slider");
  slider.addEventListener("input", (e) => {
    state.bucketIdx = Number(e.target.value);
    render();
  });
  $("#lang-select").addEventListener("change", async (e) => {
    await loadStrings(e.target.value);
    render();
  });
}

async function init() {
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("sw.js").catch(() => {});
  }
  await loadStrings("en");
  wireTabs();
  wireSort();
  wireControls();
  const ok = await loadData();
  if (!ok) {
    $("#status").textContent =
      state.strings["no-data"] || "No data yet. Run `swelter demo --serve` or `make demo`.";
    return;
  }
  indexCells();
  state.bucketIdx = Math.max(0, state.buckets.length - 1);
  const slider = $("#time-slider");
  slider.max = String(Math.max(0, state.buckets.length - 1));
  slider.value = String(state.bucketIdx);
  render();
}

init();
