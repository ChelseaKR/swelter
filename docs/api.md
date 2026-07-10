# swelter API reference

The swelter HTTP surface is **read-only**. It only ever answers `GET` (and `OPTIONS`); any write
(`POST`/`PUT`/`PATCH`/`DELETE`) returns `405` with a JSON body. There is no write path to expose, and
no account or API key. CORS is open (`Access-Control-Allow-Origin: *`) because the data is open.

The observation **data is CC0** (CC0-1.0 Public Domain Dedication; see `DATA-LICENSE`) — for a
network's own nodes. You can copy, modify, redistribute, and build on it, including commercially,
without asking. Attribution is not required but appreciated: "Environmental data from the swelter
community sensing network." The swelter source code is licensed separately under Apache-2.0 (see
`LICENSE`).

**Mixed stores (native + fetched third-party data).** The store itself is source-agnostic: it has
no license field, and a store can hold a network's own CC0 observations, readings fetched from a
third-party source (`swelter fetch`), or both. CC0 is true only for a network's own observations.
A fetched source keeps its own terms. Open-Meteo serves its API data under CC BY 4.0;
Sensor.Community labels its database contents ODC-DbCL-1.0. OpenAQ is an aggregator, not a blanket
CC BY dataset: every v3 location includes original-provider license and attribution metadata, and
OpenAQ's Terms require users to follow those varying provider terms. `export.py` does **not** infer
or track which rows came from where, so it cannot safely emit a single license for a store that mixes sources. The `--license`
(and `--attribution`) flags on `swelter export`, and the matching keyword arguments on
`export.to_json()` / `to_csv()` / `summarize()`, let the caller state the license explicitly at
export time; the default remains CC0-1.0 so a network's own store is unchanged. **If you run `swelter
fetch` into a store that already holds other observations, export that store per source** (e.g. one
store per fetch, as the Pages workflow does) rather than trusting a single export to get a mixed
store's license right — nothing today prevents `swelter export` from mislabeling a mixed store, so
that discipline is on the operator, not (yet) enforced by the store.

**Keep the terms attached downstream.** The `/sensors/` export names Sensor.Community's DbCL v1.0
contents terms and links to the official license. OpenAQ exports need the license and attribution
ledger from each returned location; a generic “OpenAQ” credit does not replace the original-source
requirements. Keep each source's rows distinguishable and review the linked upstream terms before
redistributing or combining a fetched dataset. The Pages workflow uses separate accumulated stores
for OpenAQ, CAMS, and Sensor.Community so a fallback cannot silently relabel yesterday's rows.

The server is the standard library's `http.server`, single-threaded and stateless: it reads the
store and answers. It is scale-to-zero friendly and runs as well on a Raspberry-Pi-class host with
no cloud at all. Responses set `Cache-Control: public, max-age=60`.

Author: Chelsea Kelly-Reif. Year: 2026.

## Endpoints at a glance

| Path | Returns |
| --- | --- |
| `/health` | Liveness and observation count |
| `/v1.1` | SensorThings service document |
| `/v1.1/Things` | Nodes, with published (grid-snapped) locations |
| `/v1.1/Locations` | The published cell centres |
| `/v1.1/Datastreams` | One stream per (node, parameter) |
| `/v1.1/ObservedProperties` | The parameters a node may report |
| `/v1.1/Observations` | Readings (filterable, paginated) |
| `/api/surface.geojson` | Latest gridded heat/AQI surface as GeoJSON |
| `/api/surface.json?hours=N` | Flat per-cell/hour/parameter records |
| `/api/health.json` | Per-node liveness/quality summary (coverage) |
| `/api/alerts.json` | Neighborhood heat/AQI alerts (areas past a danger threshold) |
| `/api/alerts.xml` | The same alerts as a subscribable Atom 1.0 feed (`?area=<id>` to narrow) |
| `/api/cooling-centers.geojson` | Curated cooling-center overlay (validated FeatureCollection) |
| `/export.csv` | Flat CSV dump (filterable) |
| `/export.json` | Flat JSON dump (filterable) |
| `/LICENSE`, `/DATA-LICENSE`, `/NOTICE` | The repo-root license/notice files, as `text/plain` |
| `web/` static | The dashboard (default `index.html`) |

Base URL in examples: `http://localhost:8000`. Start the server with `swelter serve` (or `swelter
demo --serve` to replay the recorded week first). The examples below are real (lightly trimmed)
responses from `swelter demo`, so the coordinates, labels, counts, and values are representative of
the demo network.

### Conventions across every endpoint

- **Trailing slashes are normalised** — `/v1.1/Things/` and `/v1.1/Things` are the same route.
- **`OPTIONS` returns `204`** with `Access-Control-Allow-Origin: *`,
  `Access-Control-Allow-Methods: GET, OPTIONS`, and `Access-Control-Allow-Headers: *` — a CORS
  preflight succeeds without a separate config.
- **Responses gzip** when the client sends `Accept-Encoding: gzip`, the body is over 1 KB, and the
  content type is text/JSON/CSV/JS/XML/SVG; the response then carries `Content-Encoding: gzip` and
  `Vary: Accept-Encoding`.
- **Errors are JSON**: `{"error": "...", "status": <code>}` with `Content-Type: application/json`.
  A non-numeric `top`/`skip`/`hours` or a bad timestamp is `400`; an unknown path is `404`; a write
  method is `405`.

```
$ curl -X POST http://localhost:8000/v1.1/Observations
{"error": "swelter's public API is read-only", "status": 405}

$ curl 'http://localhost:8000/v1.1/Observations?$top=abc'
{"error": "bad request: invalid literal for int() with base 10: 'abc'", "status": 400}

$ curl http://localhost:8000/nope
{"error": "not found", "status": 404}
```

### License and notice routes

`GET /LICENSE`, `GET /DATA-LICENSE`, and `GET /NOTICE` serve the repo-root files as
`text/plain; charset=utf-8`, so the dashboard footer's citation trail resolves under `swelter serve`
without bundling copies into `web/`. (`LICENSE` is Apache-2.0 for the code; `DATA-LICENSE` is the
CC0-1.0 dedication for the observations; `NOTICE` is the attribution notice.)

## SensorThings 1.1 subset

A subset of the OGC SensorThings API 1.1, mapped to swelter's model: **Things are nodes**,
**Locations are published cell centres**, **Datastreams are (node, parameter) streams**,
**ObservedProperties are parameters**, **Observations are readings**. The service document
advertises `serverSettings.readOnly: true`, so a client knows up front there is no write path.

### `GET /v1.1`

The entry point: the collections a client can follow.

```json
{
  "serverSettings": {
    "conformance": [
      "http://www.opengis.net/spec/iot_sensing/1.1/req/datamodel",
      "http://www.opengis.net/spec/iot_sensing/1.1/req/request-data"
    ],
    "readOnly": true
  },
  "value": [
    {"name": "Things", "url": "http://localhost:8000/v1.1/Things"},
    {"name": "Locations", "url": "http://localhost:8000/v1.1/Locations"},
    {"name": "Datastreams", "url": "http://localhost:8000/v1.1/Datastreams"},
    {"name": "Observations", "url": "http://localhost:8000/v1.1/Observations"},
    {"name": "ObservedProperties", "url": "http://localhost:8000/v1.1/ObservedProperties"}
  ]
}
```

### `GET /v1.1/Things`

Nodes as SensorThings `Things`. Each carries its **published** location only — coordinates snapped
to the coarse grid (default ~150 m) unless the host opted the node into `precise`. The precise
location is never required and never served unless opted in. `properties.location_precision` is
`coarse` or `precise`; `properties.label` and `name` carry the host-assigned block name (falling
back to the node id when unnamed).

```json
{
  "@iot.count": 150,
  "value": [
    {
      "@iot.id": "node-01",
      "name": "Elm & 3rd",
      "description": "Community heat/air-quality sensor node",
      "properties": {"location_precision": "coarse", "label": "Elm & 3rd"},
      "Locations": [
        {
          "name": "Elm & 3rd (published cell)",
          "encodingType": "application/geo+json",
          "location": {"type": "Point", "coordinates": [-121.515433, 38.567867]}
        }
      ],
      "Locations@iot.navigationLink": "http://localhost:8000/v1.1/Things(node-01)/Locations"
    }
  ]
}
```

Coordinates are `[lon, lat]`, GeoJSON order.

### `GET /v1.1/Locations`

The published (grid-snapped) cell centres as standalone SensorThings `Locations` — one per node
that has a published location, with the same coordinates the matching `Thing` carries. Useful for a
map client that wants the locations collection without walking each Thing.

```json
{
  "@iot.count": 150,
  "value": [
    {
      "@iot.id": "node-01-loc",
      "name": "Elm & 3rd (published cell)",
      "encodingType": "application/geo+json",
      "location": {"type": "Point", "coordinates": [-121.515433, 38.567867]}
    }
  ]
}
```

### `GET /v1.1/Datastreams`

One `Datastream` per `(node, parameter)` pair — the SensorThings link between a `Thing` and an
`ObservedProperty`. The demo network's 150 nodes × 6 parameters yield 900 streams. Each carries its
unit of measurement and navigation links to its Thing and ObservedProperty.

```json
{
  "@iot.count": 900,
  "value": [
    {
      "@iot.id": "node-01:temp_c",
      "name": "Elm & 3rd — temp_c",
      "unitOfMeasurement": {
        "name": "temp_c",
        "symbol": "degC",
        "definition": "https://github.com/ChelseaKR/swelter/blob/main/docs/api.md#temp_c"
      },
      "observationType": "http://www.opengis.net/def/observationType/OGC-OM/2.0/OM_Measurement",
      "Thing@iot.navigationLink": "http://localhost:8000/v1.1/Things(node-01)",
      "ObservedProperty@iot.navigationLink": "http://localhost:8000/v1.1/ObservedProperties(temp_c)"
    }
  ]
}
```

### `GET /v1.1/ObservedProperties`

The parameters a node may report. Each `definition` deep-links into the "Observed properties"
section of this file.

```json
{
  "@iot.count": 6,
  "value": [
    {
      "@iot.id": "temp_c",
      "name": "temp_c",
      "definition": "https://github.com/ChelseaKR/swelter/blob/main/docs/api.md#temp_c",
      "properties": {"unit": "degC"}
    }
  ]
}
```

### `GET /v1.1/Observations`

Readings as SensorThings `Observations`. Provenance — node, parameter, unit, and calibration version
— travels in `parameters`; the QC verdict, the 1-sigma `uncertainty`, and an explicit `trustworthy`
flag travel in `resultQuality`.

Query parameters:

| Param | Meaning | Default |
| --- | --- | --- |
| `parameter` | Filter to one observed property (e.g. `pm25_ugm3`) | all |
| `node` | Filter to one node id (e.g. `node-07`) | all |
| `since` | Inclusive lower bound, ISO-8601 UTC (`...Z`) | none |
| `until` | Inclusive upper bound, ISO-8601 UTC (`...Z`) | none |
| `$top` / `top` | Page size (max records returned) | `1000` |
| `$skip` / `skip` | Records to skip before the page | `0` |
| `order` / `$orderby` | `desc` (or `phenomenonTime desc`) returns latest-first, so `top` gives the most recent N | `asc` (stored order) |
| `dedupe` | `false` to keep both raw and calibrated rows | dedupe on |

**Pagination.** `@iot.count` is the **true total** matching the filter (not the page length), and
the response carries an `@iot.nextLink` whenever more rows remain. The OData-style `$top`/`$skip` and
the bare `top`/`skip` are both accepted (the OData spelling matches a generic SensorThings client).

**Dedupe.** By default the results are deduped to one row per `(node, timestamp, parameter)`,
**preferring the calibrated value** over the raw one — so a generic client sees the best available
reading once. Pass `dedupe=false` to keep both the raw *and* the calibrated rows (this roughly
doubles `@iot.count` for a node/parameter that is calibrated).

```json
{
  "@iot.count": 169,
  "value": [
    {
      "@iot.id": "node-01|2026-06-01T00:00:00Z|temp_c|temp_c.enclosure-offset.node-01",
      "phenomenonTime": "2026-06-01T00:00:00Z",
      "result": 24.935811,
      "resultQuality": {"qc": "ok", "uncertainty": 0.476025, "trustworthy": true},
      "parameters": {
        "node_id": "node-01",
        "parameter": "temp_c",
        "unit": "degC",
        "calibration": "temp_c.enclosure-offset.node-01"
      }
    }
  ],
  "@iot.nextLink": "http://localhost:8000/v1.1/Observations?$skip=1&$top=1"
}
```

`calibration` is either `raw` or a correction version id of the form
`{parameter}.{method}.{node_id}`. A raw reading carries `calibration: "raw"`, a null `uncertainty`,
and `trustworthy: false`; it is shown provisional. A calibrated, QC-clean reading is `trustworthy:
true`. Calibrated and raw are always distinguishable here.

With `dedupe=false` the raw row appears alongside the calibrated one, distinguished by `calibration`
and `trustworthy`:

```
GET /v1.1/Observations?parameter=temp_c&node=node-01&dedupe=false
  → "raw"  → {"qc": "ok", "uncertainty": null, "trustworthy": false}
  → "temp_c.enclosure-offset.node-01" → {"qc": "ok", "uncertainty": 0.476025, "trustworthy": true}
```

Example (page through PM2.5 for one node, 500 at a time):

```
GET /v1.1/Observations?parameter=pm25_ugm3&node=node-07&since=2026-06-06T00:00:00Z&$top=500&$skip=0
```

## Surface endpoints

Gridded hourly rollups of the readings. A cell's mean is taken over **calibrated, QC-clean** values
when any exist; a cell with only raw or flagged readings is still shown but marked `provisional`.
PM2.5 cells carry their US-EPA AQI value and category.

A derived **`exposure`** layer combines the heat index and the PM2.5 AQI into one level per cell and
hour (ADR 0009). It appears only where a cell has both a heat-index and a PM2.5 reading for that
hour, is `provisional` whenever either component is, and never blends the two into a fabricated
number — its `mean` is the ordinal level `0`–`4` (`category` is the matching name `Minimal`, `Low`,
`Elevated`, `High`, `Extreme`), taken as the **higher** of the heat and air concern. It adds
`heat_category` (the NWS heat-index tier), `air_category` (the PM2.5 AQI category), and a `compound`
flag (true when heat *and* air are each at least the mid tier). It is decision-support, not a
validated health index, and never a claim that conditions are safe.

### `GET /api/surface.geojson`

The latest snapshot: one GeoJSON point feature per published grid cell, its properties carrying each
parameter's most recent hourly value. Served as `Content-Type: application/geo+json`. Coordinates are
`[lon, lat]`.

Each feature carries the cell's host-assigned `label`, a top-level `provisional` flag (true if *any*
parameter in the cell is provisional), and, per parameter, the value plus a `{param}_provisional`
flag and — when the value is calibrated — a `{param}_uncertainty` (mean 1-sigma in the parameter's
unit), a `{param}_method` (the calibration method), and a `{param}_reference` (the monitor it was
fitted against). PM2.5 cells add `pm25_aqi`, `aqi_category`, and `aqi_window` (always
`"hourly-mean"`). A cell
with both a heat-index and a PM2.5 value adds the derived `exposure` level plus `exposure_level`,
`exposure_category`, `exposure_heat`, `exposure_air`, and `compound`.

```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "geometry": {"type": "Point", "coordinates": [-121.515433, 38.567867]},
      "properties": {
        "cell_id": "38.567867,-121.515433",
        "label": "Elm & 3rd",
        "bucket": "2026-06-08T00:00:00Z",
        "provisional": true,
        "temp_c": 27.345,
        "temp_c_uncertainty": 0.476,
        "temp_c_provisional": false,
        "heat_index_c": 29.87,
        "heat_index_c_provisional": true,
        "pm25_ugm3": 14.159,
        "pm25_ugm3_uncertainty": 0.9,
        "pm25_ugm3_provisional": false,
        "pm25_aqi": 60,
        "aqi_category": "Moderate",
        "aqi_window": "hourly-mean",
        "pm10_ugm3": 29.168,
        "pm10_ugm3_uncertainty": 1.609,
        "pm10_ugm3_provisional": false
      }
    }
  ]
}
```

Note `heat_index_c` is published raw/provisional, so it has a `_provisional: true` flag and no
`_uncertainty` — while the calibrated `temp_c`, `pm25_ugm3`, and `pm10_ugm3` in the same cell carry
their uncertainty and read `_provisional: false`. The top-level `provisional` is therefore `true`
here because the heat-index value is provisional.

### `GET /api/surface.json?hours=N`

Flat per-(cell, hour, parameter) records, trimmed to the most recent `N` hourly buckets to keep the
payload small. This is what the dashboard's time slider reads.

| Param | Meaning | Default |
| --- | --- | --- |
| `hours` | Number of most-recent hourly buckets to include | `48` |

Each record carries the cell's `label`, the rolled-up `mean`, the count `n`, a `provisional` flag,
and the mean 1-sigma `uncertainty` (null when the cell is provisional). A confirmed record also
carries `method` (the calibration method, e.g. `epa-humidity`) and `reference` (the monitor it was
fitted against); both are omitted on provisional records — the "show your work" provenance the
dashboard surfaces per location. Every record also carries `nodes`, the published node id(s) in the
cell, so a reader can pull the raw readings behind it (e.g. `GET /export.csv?node=<id>`). PM2.5
records also carry
`aqi`, `category`, and `aqi_window` (`"hourly-mean"`); `aqi`/`category`/`aqi_window` are absent or
null for other parameters. `exposure` records set `category` to the level name and add
`heat_category`, `air_category`, and `compound` (see Surface endpoints, above):

```json
{
  "cell_id": "38.567867,-121.515433",
  "label": "Elm & 3rd",
  "lat": 38.567867,
  "lon": -121.515433,
  "parameter": "exposure",
  "bucket": "2026-06-07T23:00:00Z",
  "mean": 2.0,
  "n": 1,
  "provisional": false,
  "uncertainty": null,
  "aqi": null,
  "category": "Elevated",
  "heat_category": "Extreme Caution",
  "air_category": "Unhealthy for Sensitive Groups",
  "compound": true
}
```

```json
{
  "interval": "hour",
  "buckets": ["2026-06-07T23:00:00Z", "2026-06-08T00:00:00Z"],
  "cells": [
    {
      "cell_id": "38.567867,-121.515433",
      "label": "Elm & 3rd",
      "lat": 38.567867,
      "lon": -121.515433,
      "parameter": "pm25_ugm3",
      "bucket": "2026-06-07T23:00:00Z",
      "mean": 13.875,
      "n": 1,
      "provisional": false,
      "uncertainty": 0.9,
      "aqi": 60,
      "category": "Moderate",
      "aqi_window": "hourly-mean"
    },
    {
      "cell_id": "38.567867,-121.515433",
      "label": "Elm & 3rd",
      "lat": 38.567867,
      "lon": -121.515433,
      "parameter": "temp_c",
      "bucket": "2026-06-07T23:00:00Z",
      "mean": 27.908,
      "n": 1,
      "provisional": false,
      "uncertainty": 0.476,
      "aqi": null,
      "category": null
    }
  ]
}
```

`aqi`, `category`, and `aqi_window` are non-null / present only for `pm25_ugm3` records.

### `GET /api/health.json`

The network's sensor health, from the same QC the pipeline runs on the raw stream — what the
dashboard's coverage panel and `swelter qc` both read. `summary` counts nodes by status; each node
carries its status (`ok` / `degraded` / `offline`), observation count, completeness, flagged
fraction, liveness, and last-seen time; `gaps` lists the longest reporting gaps. Computed over raw
readings with an hourly expected interval.

```json
{
  "interval_s": 3600.0,
  "latest": "2026-06-08T00:00:00Z",
  "summary": {"total": 150, "ok": 149, "degraded": 1, "offline": 0},
  "nodes": [
    {
      "node_id": "node-07",
      "status": "degraded",
      "observations": 600,
      "completeness": 0.86,
      "flagged_fraction": 0.0,
      "online": true,
      "last_seen": "2026-06-08T00:00:00Z"
    }
  ],
  "gaps": [
    {
      "node_id": "node-07",
      "parameter": "heat_index_c",
      "start": "2026-06-03T23:00:00Z",
      "end": "2026-06-06T00:00:00Z",
      "minutes": 2940
    }
  ]
}
```

A node reads `degraded` when its completeness drops below 95% or it flags more than 10% of readings,
and `offline` when it has been silent past three reporting intervals. The dashboard also ships a
baked `sample-health.json` so the static (server-less) deployment shows coverage too.

### `GET /api/alerts.json` and `GET /api/alerts.xml`

The neighborhood heat/AQI alerts feed: every published cell whose latest-hour reading has crossed a
documented danger floor (US-EPA AQI 101, US-NWS heat-index "Danger", or exposure "High"). The JSON
form carries the active `thresholds`, a data-derived `generated` time, and an `alerts` array; the XML
form is a standards **Atom 1.0** feed (a GeoRSS point per entry) so a resident subscribes in any
RSS/Atom reader. `?area=<area_id>` narrows either form to one published cell. Floors are overridable
per network via `alert_thresholds` in `network.yaml`. Alerts carry only public, aggregate fields — a
cell id, centroid, area label, node ids, and the reading — and provisional readings are flagged, not
hidden. Full reference: [`docs/alerts.md`](alerts.md). `swelter demo`/`fetch` bake `alerts.json` +
`alerts.xml` for the static site.

### `GET /api/cooling-centers.geojson`

A curated, provenance-bearing overlay of public places to cool down (libraries, community/senior
centers, cooled public buildings), as a GeoJSON FeatureCollection with set-level `metadata` (license,
attribution, source, `last_verified`, count). It is validated on load — every feature needs a name and
an in-range Point, and properties are held to a public-field allowlist — and is separately licensed
civic data, **not** part of the CC0 observation stream. An unconfigured server returns a valid empty
FeatureCollection. See [ADR 0011](decisions/0011-cooling-center-overlay.md).

## Export endpoints

Flat dumps for a resident, a reporter, or a researcher. Both accept the same filters as
`/v1.1/Observations`. Every row carries the value's provenance — `calibration` version, `qc` verdict,
`uncertainty`, and an explicit `trustworthy` flag — so a value's trustworthiness leaves with it. The
export is **not** deduped: a calibrated node emits both its `raw` and its calibrated row, so a
downloader can see what was measured and what was corrected.

| Param | Meaning | Default |
| --- | --- | --- |
| `since` | Inclusive lower bound, ISO-8601 UTC (`...Z`) | none |
| `until` | Inclusive upper bound, ISO-8601 UTC (`...Z`) | none |
| `node` | Filter to one node id | all |
| `parameter` | Filter to one observed property | all |

### `GET /export.csv`

`text/csv; charset=utf-8`. Columns, in this fixed order (the final two provenance columns keep a
downloaded or filtered subset's source terms attached to every row):

```
node_id,timestamp,parameter,value,unit,calibration,qc,uncertainty,trustworthy,data_license,data_attribution
node-01,2026-06-01T00:00:00Z,temp_c,24.96,degC,raw,ok,,False,CC0-1.0,
node-01,2026-06-01T00:00:00Z,temp_c,24.935811,degC,temp_c.enclosure-offset.node-01,ok,0.476025,True,CC0-1.0,
```

`trustworthy` is `True` only for a calibrated, QC-clean reading; a `raw` row leaves `uncertainty`
empty and reads `False`. `data_license` and `data_attribution` come from the export invocation; the
default is CC0 for a network's native store, while fetched third-party stores must pass their actual
source terms. (Text cells that begin with a spreadsheet formula character are neutralised on export,
so a self-reported `node_id` can't smuggle a formula into a spreadsheet.)

### `GET /export.json`

`application/json`. A `license` field names the dedication; `observations` is the row list, each
row carrying the same fields as the CSV columns.

```json
{
  "license": "CC0-1.0",
  "observations": [
    {
      "node_id": "node-01",
      "timestamp": "2026-06-01T00:00:00Z",
      "parameter": "temp_c",
      "value": 24.96,
      "unit": "degC",
      "calibration": "raw",
      "qc": "ok",
      "uncertainty": null,
      "trustworthy": false
    },
    {
      "node_id": "node-01",
      "timestamp": "2026-06-01T00:00:00Z",
      "parameter": "temp_c",
      "value": 24.935811,
      "unit": "degC",
      "calibration": "temp_c.enclosure-offset.node-01",
      "qc": "ok",
      "uncertainty": 0.476025,
      "trustworthy": true
    }
  ]
}
```

Example:

```
GET /export.csv?since=2026-06-01T00:00:00Z&until=2026-06-08T00:00:00Z&node=node-07&parameter=pm25_ugm3
```

## `GET /health`

Liveness and the current observation count. (`/healthz` is an alias.)

```json
{"status": "ok", "observations": 177050}
```

## `swelter qc` (CLI)

Not an HTTP endpoint, but the companion read of the same data: per-node health and the data gaps,
straight from the store. `swelter qc --store <dir>` prints a human summary — each node's status
(`offline` / `degraded` / `ok`), its observation count, completeness, and flagged fraction, plus the
longest gaps. A node reads `degraded` when its completeness drops below 95% or it flags more than
10% of readings, and `offline` when it has been silent past three reporting intervals.

```
swelter: 150 nodes (1 degraded/offline), 5 gaps over interval 3600s
  gap  node-07/temp_c  2026-06-03T23:00:00Z → 2026-06-06T00:00:00Z  (2940 min)
   node-01  OK           845 obs    100.0% complete    0.0% flagged
```

Add `--json` for the machine-readable form — a `nodes` list and a `gaps` list — for dashboards and CI:

```json
{
  "nodes": [
    {
      "node_id": "node-01",
      "status": "ok",
      "observations": 845,
      "completeness": 1.0,
      "flagged_fraction": 0.0,
      "online": true,
      "last_seen": "2026-06-08T00:00:00Z"
    }
  ],
  "gaps": [
    {
      "node_id": "node-07",
      "parameter": "heat_index_c",
      "start": "2026-06-03T23:00:00Z",
      "end": "2026-06-06T00:00:00Z",
      "minutes": 2940
    }
  ]
}
```

## Observed properties

The full set of quantities a node may report. The QC verdict on each reading is one of `ok`,
`range`, `spike`, `flatline`, `missing`; a value that is not calibrated, or whose QC verdict is not
`ok`, is shown provisional. Each calibrated value carries a 1-sigma `uncertainty` in the parameter's
unit.

The headings below are stable anchors so the `ObservedProperties` `definition` links and external
deep links resolve.

## temp_c

Air temperature, unit **degC** (degrees Celsius). The reading the heat-island map is built from.
Low-cost sensors in a dark enclosure in the sun read the box, not the air, so calibrated nodes apply
an enclosure-offset correction (`temp_c.enclosure-offset.{node_id}`, `corrected = a*raw + c`). Valid
range −40 to 60 degC.

## humidity_pct

Relative humidity, unit **%** (percent, 0–100). A diagnostic field: it is an input to the
humidity-aware PM correction and to the heat index, and is not itself drawn on the map surface.
Valid range 0 to 100 %.

## pm25_ugm3

Fine particulate matter (PM2.5), unit **ug/m3** (micrograms per cubic metre). Particles 2.5
micrometres and smaller; the basis for the AQI shown on the map. Calibrated nodes apply a
humidity-aware correction in the US-EPA PurpleAir lineage
(`pm25_ugm3.epa-humidity.{node_id}`, `corrected = a*raw + b*humidity + c`), because optical PM
counts inflate in humid air. Surface cells carry an EPA AQI value and category (US-EPA 2024
breakpoints). The AQI is computed from the cell's **hourly** mean, not a 24-hour average or NowCast —
read it as an hourly indication, not the official 24-hour AQI. Valid range 0 to 1000 ug/m3.

## pm10_ugm3

Coarse particulate matter (PM10), unit **ug/m3** (micrograms per cubic metre). Particles 10
micrometres and smaller (includes PM2.5). Calibrated nodes apply the same humidity-aware correction
family (`pm10_ugm3.epa-humidity.{node_id}`). Valid range 0 to 2000 ug/m3.

## no2_ppb

Nitrogen dioxide, unit **ppb** (parts per billion by volume). A traffic-and-combustion air-quality
indicator, reported by nodes that carry an NO2 sensor. Valid range 0 to 2000 ppb.

## heat_index_c

Heat index ("feels-like" temperature), unit **degC** (degrees Celsius). Combines air temperature and
relative humidity into the apparent temperature a body experiences, via the NWS Rothfusz regression;
below 26.7 degC the air temperature is returned unchanged. Computed on the node from its own
temperature and humidity, so it inherits their raw bias and is **published raw / provisional** — the
demo network co-locates temperature and PM, not the derived heat index, so no `heat_index_c`
correction is fit. Treat it as indicative, not calibrated. Valid range −40 to 60 degC.

---

Last verified: 2026-06-19. Recheck cadence: review when the API surface, the export shape, or the
`PARAMETERS` registry change, and at least annually (the AQI applies US-EPA 2024 PM2.5 breakpoints
to the cell's hourly mean — `aqi_window: "hourly-mean"`, not the official 24-hour AQI; recheck on
each EPA revision).
