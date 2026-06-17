# swelter API reference

The swelter HTTP surface is **read-only**. It only ever answers `GET` (and `OPTIONS`); any write
(`POST`/`PUT`/`PATCH`/`DELETE`) returns `405` with a JSON body. There is no write path to expose, and
no account or API key. CORS is open (`Access-Control-Allow-Origin: *`) because the data is open.

The observation **data is CC0** (CC0-1.0 Public Domain Dedication; see `DATA-LICENSE`). You can
copy, modify, redistribute, and build on it, including commercially, without asking. Attribution is
not required but appreciated: "Environmental data from the swelter community sensing network." The
swelter source code is licensed separately under Apache-2.0 (see `LICENSE`).

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
  "@iot.count": 18,
  "value": [
    {
      "@iot.id": "node-01",
      "name": "Riverside & 5th",
      "description": "Community heat/air-quality sensor node",
      "properties": {"location_precision": "coarse", "label": "Riverside & 5th"},
      "Locations": [
        {
          "name": "Riverside & 5th (published cell)",
          "encodingType": "application/geo+json",
          "location": {"type": "Point", "coordinates": [-121.508516, 38.574605]}
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
  "@iot.count": 18,
  "value": [
    {
      "@iot.id": "node-01-loc",
      "name": "Riverside & 5th (published cell)",
      "encodingType": "application/geo+json",
      "location": {"type": "Point", "coordinates": [-121.508516, 38.574605]}
    }
  ]
}
```

### `GET /v1.1/Datastreams`

One `Datastream` per `(node, parameter)` pair — the SensorThings link between a `Thing` and an
`ObservedProperty`. The demo network's 18 nodes × 6 parameters yield 108 streams. Each carries its
unit of measurement and navigation links to its Thing and ObservedProperty.

```json
{
  "@iot.count": 108,
  "value": [
    {
      "@iot.id": "node-01:temp_c",
      "name": "Riverside & 5th — temp_c",
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
  "@iot.count": 385,
  "value": [
    {
      "@iot.id": "node-01|2026-06-01T00:00:00Z|temp_c|temp_c.enclosure-offset.node-01",
      "phenomenonTime": "2026-06-01T00:00:00Z",
      "result": 24.883378,
      "resultQuality": {"qc": "ok", "uncertainty": 0.480814, "trustworthy": true},
      "parameters": {
        "node_id": "node-01",
        "parameter": "temp_c",
        "unit": "degC",
        "calibration": "temp_c.enclosure-offset.node-01"
      }
    }
  ],
  "@iot.nextLink": "http://localhost:8000/v1.1/Observations?$skip=2&$top=2"
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
  → "temp_c.enclosure-offset.node-01" → {"qc": "ok", "uncertainty": 0.480814, "trustworthy": true}
```

Example (page through PM2.5 for one node, 500 at a time):

```
GET /v1.1/Observations?parameter=pm25_ugm3&node=node-07&since=2026-06-10T00:00:00Z&$top=500&$skip=0
```

## Surface endpoints

Gridded hourly rollups of the readings. A cell's mean is taken over **calibrated, QC-clean** values
when any exist; a cell with only raw or flagged readings is still shown but marked `provisional`.
PM2.5 cells carry their US-EPA AQI value and category.

### `GET /api/surface.geojson`

The latest snapshot: one GeoJSON point feature per published grid cell, its properties carrying each
parameter's most recent hourly value. Served as `Content-Type: application/geo+json`. Coordinates are
`[lon, lat]`.

Each feature carries the cell's host-assigned `label`, a top-level `provisional` flag (true if *any*
parameter in the cell is provisional), and, per parameter, the value plus a `{param}_provisional`
flag and — when the value is calibrated — a `{param}_uncertainty` (mean 1-sigma in the parameter's
unit). PM2.5 cells add `pm25_aqi`, `aqi_category`, and `aqi_window` (always `"hourly-mean"`).

```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "geometry": {"type": "Point", "coordinates": [-121.491604, 38.574605]},
      "properties": {
        "cell_id": "38.574605,-121.491604",
        "label": "Alkali Flat",
        "bucket": "2026-06-17T00:00:00Z",
        "provisional": true,
        "temp_c": 27.152,
        "temp_c_uncertainty": 0.779,
        "temp_c_provisional": false,
        "heat_index_c": 30.21,
        "heat_index_c_provisional": true,
        "pm25_ugm3": 13.863,
        "pm25_ugm3_uncertainty": 1.316,
        "pm25_ugm3_provisional": false,
        "pm25_aqi": 60,
        "aqi_category": "Moderate",
        "aqi_window": "hourly-mean",
        "pm10_ugm3": 25.637,
        "pm10_ugm3_uncertainty": 1.843,
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
and the mean 1-sigma `uncertainty` (null when the cell is provisional). PM2.5 records also carry
`aqi`, `category`, and `aqi_window` (`"hourly-mean"`); `aqi`/`category`/`aqi_window` are absent or
null for other parameters.

```json
{
  "interval": "hour",
  "buckets": ["2026-06-16T23:00:00Z", "2026-06-17T00:00:00Z"],
  "cells": [
    {
      "cell_id": "38.574605,-121.491604",
      "label": "Alkali Flat",
      "lat": 38.574605,
      "lon": -121.491604,
      "parameter": "pm25_ugm3",
      "bucket": "2026-06-16T23:00:00Z",
      "mean": 13.656,
      "n": 1,
      "provisional": false,
      "uncertainty": 1.316,
      "aqi": 59,
      "category": "Moderate",
      "aqi_window": "hourly-mean"
    },
    {
      "cell_id": "38.574605,-121.491604",
      "label": "Alkali Flat",
      "lat": 38.574605,
      "lon": -121.491604,
      "parameter": "temp_c",
      "bucket": "2026-06-16T23:00:00Z",
      "mean": 28.7,
      "n": 1,
      "provisional": false,
      "uncertainty": 0.779,
      "aqi": null,
      "category": null
    }
  ]
}
```

`aqi`, `category`, and `aqi_window` are non-null / present only for `pm25_ugm3` records.

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

`text/csv; charset=utf-8`. Columns, in this fixed order (note the final `trustworthy` column):

```
node_id,timestamp,parameter,value,unit,calibration,qc,uncertainty,trustworthy
node-01,2026-06-01T00:00:00Z,temp_c,24.92,degC,raw,ok,,False
node-01,2026-06-01T00:00:00Z,temp_c,24.883378,degC,temp_c.enclosure-offset.node-01,ok,0.480814,True
```

`trustworthy` is `True` only for a calibrated, QC-clean reading; a `raw` row leaves `uncertainty`
empty and reads `False`. (Text cells that begin with a spreadsheet formula character are neutralised
on export, so a self-reported `node_id` can't smuggle a formula into a spreadsheet.)

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
      "value": 24.92,
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
      "value": 24.883378,
      "unit": "degC",
      "calibration": "temp_c.enclosure-offset.node-01",
      "qc": "ok",
      "uncertainty": 0.480814,
      "trustworthy": true
    }
  ]
}
```

Example:

```
GET /export.csv?since=2026-06-01T00:00:00Z&until=2026-06-17T00:00:00Z&node=node-07&parameter=pm25_ugm3
```

## `GET /health`

Liveness and the current observation count. (`/healthz` is an alias.)

```json
{"status": "ok", "observations": 48094}
```

## `swelter qc` (CLI)

Not an HTTP endpoint, but the companion read of the same data: per-node health and the data gaps,
straight from the store. `swelter qc --store <dir>` prints a human summary — each node's status
(`offline` / `degraded` / `ok`), its observation count, completeness, and flagged fraction, plus the
longest gaps. A node reads `degraded` when its completeness drops below 95% or it flags more than
10% of readings, and `offline` when it has been silent past three reporting intervals.

```
swelter: 18 nodes (1 degraded/offline), 5 gaps over interval 3600s
  gap  node-07/temp_c  2026-06-09T23:00:00Z → 2026-06-12T04:00:00Z  (3180 min)
   node-01  OK          1925 obs    100.0% complete    1.5% flagged
```

Add `--json` for the machine-readable form — a `nodes` list and a `gaps` list — for dashboards and CI:

```json
{
  "nodes": [
    {
      "node_id": "node-01",
      "status": "ok",
      "observations": 1925,
      "completeness": 1.0,
      "flagged_fraction": 0.015,
      "online": true,
      "last_seen": "2026-06-17T00:00:00Z"
    }
  ],
  "gaps": [
    {
      "node_id": "node-07",
      "parameter": "heat_index_c",
      "start": "2026-06-09T23:00:00Z",
      "end": "2026-06-12T04:00:00Z",
      "minutes": 3180
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

Last verified: 2026-06-17. Recheck cadence: review when the API surface, the export shape, or the
`PARAMETERS` registry change, and at least annually (the AQI applies US-EPA 2024 PM2.5 breakpoints
to the cell's hourly mean — `aqi_window: "hourly-mean"`, not the official 24-hour AQI; recheck on
each EPA revision).
