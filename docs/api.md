# swelter API reference

The swelter HTTP surface is **read-only**. It only ever answers `GET`; any write
(`POST`/`PUT`/`PATCH`/`DELETE`) returns `405`. There is no write path to expose, and no account or
API key. CORS is open (`Access-Control-Allow-Origin: *`) because the data is open.

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
| `/v1.1/ObservedProperties` | The parameters a node may report |
| `/v1.1/Observations` | Readings (filterable) |
| `/api/surface.geojson` | Latest gridded heat/AQI surface as GeoJSON |
| `/api/surface.json?hours=N` | Flat per-cell/hour/parameter records |
| `/export.csv` | Flat CSV dump (filterable) |
| `/export.json` | Flat JSON dump (filterable) |
| `web/` static | The dashboard (default `index.html`) |

Base URL in examples: `http://localhost:8000`. Start the server with `swelter serve` (or `swelter
demo --serve` to replay the recorded week first).

## SensorThings 1.1 subset

A subset of the OGC SensorThings API 1.1, mapped to swelter's model: **Things are nodes**,
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
`coarse` or `precise`.

```json
{
  "@iot.count": 18,
  "value": [
    {
      "@iot.id": "node-01",
      "name": "Node 01",
      "description": "Community heat/air-quality sensor node",
      "properties": {"location_precision": "coarse"},
      "Locations": [
        {
          "name": "node-01 (published cell)",
          "encodingType": "application/geo+json",
          "location": {"type": "Point", "coordinates": [-121.509361, 38.575057]}
        }
      ],
      "Locations@iot.navigationLink": "http://localhost:8000/v1.1/Things(node-01)/Locations"
    }
  ]
}
```

Coordinates are `[lon, lat]`, GeoJSON order.

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
— travels in `parameters`; the QC verdict and the 1-sigma uncertainty travel in `resultQuality`.

Query parameters:

| Param | Meaning | Default |
| --- | --- | --- |
| `parameter` | Filter to one observed property (e.g. `pm25_ugm3`) | all |
| `node` | Filter to one node id (e.g. `node-07`) | all |
| `since` | Inclusive lower bound, ISO-8601 UTC (`...Z`) | none |
| `until` | Inclusive upper bound, ISO-8601 UTC (`...Z`) | none |
| `top` | Max records returned | `1000` |

```json
{
  "@iot.count": 1,
  "value": [
    {
      "@iot.id": "node-01|2026-06-04T12:00:00Z|temp_c|temp_c.enclosure-offset.node-01",
      "phenomenonTime": "2026-06-04T12:00:00Z",
      "result": 34.71,
      "resultQuality": {"qc": "ok", "uncertainty": 0.42},
      "parameters": {
        "node_id": "node-01",
        "parameter": "temp_c",
        "unit": "degC",
        "calibration": "temp_c.enclosure-offset.node-01"
      }
    }
  ]
}
```

`calibration` is either `raw` or a correction version id of the form
`{parameter}.{method}.{node_id}`. A raw reading carries `calibration: "raw"` and a null
`uncertainty`; it is shown provisional. Calibrated and raw are always distinguishable here.

Example:

```
GET /v1.1/Observations?parameter=pm25_ugm3&node=node-07&since=2026-06-10T00:00:00Z&top=500
```

## Surface endpoints

Gridded hourly rollups of the readings. A cell's mean is taken over **calibrated, QC-clean** values
when any exist; a cell with only raw or flagged readings is still shown but marked `provisional`.
PM2.5 cells carry their US-EPA AQI value and category.

### `GET /api/surface.geojson`

The latest snapshot: one GeoJSON point feature per published grid cell, its properties carrying each
parameter's most recent hourly value. Coordinates are `[lon, lat]`.

```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "geometry": {"type": "Point", "coordinates": [-121.5094, 38.5751]},
      "properties": {
        "cell_id": "38.575057,-121.509361",
        "bucket": "2026-06-16T18:00:00Z",
        "provisional": false,
        "temp_c": 33.9,
        "heat_index_c": 36.2,
        "pm25_ugm3": 12.4,
        "pm25_aqi": 53,
        "aqi_category": "Moderate",
        "pm10_ugm3": 21.8,
        "no2_ppb": 9.1
      }
    }
  ]
}
```

### `GET /api/surface.json?hours=N`

Flat per-(cell, hour, parameter) records, trimmed to the most recent `N` hourly buckets to keep the
payload small. This is what the dashboard's time slider reads.

| Param | Meaning | Default |
| --- | --- | --- |
| `hours` | Number of most-recent hourly buckets to include | `48` |

```json
{
  "interval": "hour",
  "buckets": ["2026-06-16T17:00:00Z", "2026-06-16T18:00:00Z"],
  "cells": [
    {
      "cell_id": "38.575057,-121.509361",
      "lat": 38.575057,
      "lon": -121.509361,
      "parameter": "pm25_ugm3",
      "bucket": "2026-06-16T18:00:00Z",
      "mean": 12.43,
      "n": 1,
      "provisional": false,
      "aqi": 53,
      "category": "Moderate"
    }
  ]
}
```

`aqi` and `category` are non-null only for `pm25_ugm3` records.

## Export endpoints

Flat dumps for a resident, a reporter, or a researcher. Both accept the same filters as
`/v1.1/Observations`. Every row carries the value's provenance — `calibration` version, `qc` verdict,
and `uncertainty` — so a value's trustworthiness leaves with it.

| Param | Meaning | Default |
| --- | --- | --- |
| `since` | Inclusive lower bound, ISO-8601 UTC (`...Z`) | none |
| `until` | Inclusive upper bound, ISO-8601 UTC (`...Z`) | none |
| `node` | Filter to one node id | all |
| `parameter` | Filter to one observed property | all |

### `GET /export.csv`

`text/csv; charset=utf-8`. Columns, in this fixed order:

```
node_id,timestamp,parameter,value,unit,calibration,qc,uncertainty
node-01,2026-06-04T12:00:00Z,temp_c,34.71,degC,temp_c.enclosure-offset.node-01,ok,0.42
node-13,2026-06-04T12:00:00Z,pm25_ugm3,8.90,ug/m3,raw,ok,
```

### `GET /export.json`

`application/json`. A `license` field names the dedication; `observations` is the row list.

```json
{
  "license": "CC0-1.0",
  "observations": [
    {
      "node_id": "node-01",
      "timestamp": "2026-06-04T12:00:00Z",
      "parameter": "temp_c",
      "value": 34.71,
      "unit": "degC",
      "calibration": "temp_c.enclosure-offset.node-01",
      "qc": "ok",
      "uncertainty": 0.42
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
{"status": "ok", "observations": 41902}
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
counts inflate in humid air. Surface cells for this parameter carry an EPA AQI value and category
(US-EPA 2024 24-hour breakpoints). Valid range 0 to 1000 ug/m3.

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
below 26.7 degC the air temperature is returned unchanged. Computed on the node when available, else
derived. Calibrated via the enclosure-offset family
(`heat_index_c.enclosure-offset.{node_id}`). Valid range −40 to 80 degC.

---

Last verified: 2026-06-16. Recheck cadence: review when the API surface, the export shape, or the
`PARAMETERS` registry change, and at least annually (the AQI uses US-EPA 2024 24-hour PM2.5
breakpoints; recheck on each EPA revision).
