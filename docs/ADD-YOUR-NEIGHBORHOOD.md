# Add your neighborhood in an afternoon

This is a step-by-step guide for a community group — a tenants' association, a block club, a
community land trust, a mutual-aid network — to stand up its own swelter network. You do not need to
touch the source code. Everything below is editing one file (`network.yaml`) and running a handful
of commands.

You can do the software setup in an afternoon with recorded demo data and no hardware at all. Putting
real sensors on real porches takes longer, but the map, the API, and the dashboard are running and
honest before a single physical node ships — which is the point: you decide the network's shape on
screen first. When you are ready to build physical nodes, the hardware build doc
([`HARDWARE.md`](HARDWARE.md)) covers the bill of materials, wiring, enclosure, siting, and how a
reading gets home through store-and-forward.

Audience: a non-specialist running the collective's laptop. Where a decision belongs to the people,
not the tool, this guide says so and points at [`governance.md`](governance.md).

Author: Chelsea Kelly-Reif. Year: 2026.

## What you need

- A laptop with [`uv`](https://docs.astral.sh/uv/) installed (the project's only prerequisite; it
  manages Python and the dependencies for you).
- A clone of this repository.
- A list of the locations you want to measure, with a rough lat/lon for each (a pin dropped on any map
  is fine — you are going to publish a coarse grid cell, not the exact pin; see step 3).
- At least one **reference monitor** you can co-locate against for a few days: a nearby regulatory
  station (US EPA AQS or AirNow) or a trusted reference-grade instrument. Calibration is what earns
  the data its trust, so this is not optional if you want calibrated readings rather than raw ones.

Before anything else, confirm the toolchain runs end to end on the shipped demo:

```console
$ make demo
```

That replays a recorded downtown week through the whole pipeline and serves the dashboard at
<http://127.0.0.1:8000>. If you see the map, the table, and the list, your machine is ready and you
can move on to your own network.

## Step 1 — Copy `network.yaml`

`network.yaml` at the repo root is the worked example (currently 150 synthetic nodes; its size is
set by the `SWELTER_DEMO_NODES` knob). It is the one file a community edits to become its own
network. Copy it so you keep the example to refer to:

```console
$ cp network.yaml my-network.yaml
```

Open `my-network.yaml` and remove this demo-only presentation directive before making any other
changes:

```yaml
web_preview: statewide-california
```

That directive belongs only to the exact generated synthetic fixture. It substitutes public
California place centroids while baking the fixture's static web preview; it must never reposition a
real or community-authored network. Your map will use the locations under `nodes:`. Remove the
directive whether you edit a copy or `network.yaml` in place, then run
`uv run swelter doctor --config my-network.yaml` before deploying.

Every command below takes `--config my-network.yaml`; if you edit `network.yaml` in place instead,
the commands' defaults pick it up.

Set the network's identity at the top:

```yaml
name: Eastside Cooperative heat & air network
```

## Step 2 — Set the grid resolution and languages

```yaml
grid_resolution_m: 150
languages:
- en
- es
```

- **`grid_resolution_m`** is the size of the published location grid cell, in meters. Every public
  coordinate is snapped to a cell of this size before it leaves the system, so a reader sees the
  area, not the porch. The default `150` answers "is this area hotter than that one" without
  publishing where anyone lives. Changing it is a **collective** decision, not a quiet edit — see
  [`governance.md`](governance.md) §3 (location-precision policy) and §7 (decision process).
- **`languages`** lists the dashboard locales. Ship the languages the people you serve actually
  read. Spanish ships in the example because of who the network serves; these must be real
  translations, not machine output (see `governance.md` §6, the accessibility and language keeper
  role).

## Step 3 — Register your nodes

Replace the `nodes:` list with your locations. Each node is four required fields plus a location
precision:

```yaml
nodes:
- node_id: node-01          # stable, unique id; never a person's name
  label: Cedar & 4th        # the location name residents will see on the map/table/list
  lat: 38.575057            # a coordinate inside the location
  lon: -121.509361
  location: coarse          # coarse (default, recommended) | precise | public-place
```

- **`node_id`** — a short stable handle (`node-01`, `node-02`, …). It is published, so keep it
  generic. It must never encode a person or an address. swelter warns on load if a `node_id` or
  `label` looks like a street address, unit, email, or phone — both are public (hard rule #1).
- **`label`** — the human name for the location. This is the cell label that the dashboard surfaces
  everywhere: the map marker's accessible name, the table row, the list sentence, the location-name
  search, and the "use my location → nearest location" button. Pick a name residents say out loud
  ("Cedar & 4th", "Oak Park Commons"), not a code. When two nodes snap to the same grid cell, their
  labels are joined with `/`, so neighboring names read sensibly together.
- **`lat` / `lon`** — any coordinate inside the location's area. It does not need to be the exact host
  location; for a coarse node only the grid cell it falls in is ever published.
- **`location`** — `coarse` (the default and the safe choice) snaps the published coordinate to the
  grid cell. `precise` publishes the node's real coordinates. **`precise` is a per-node, host opt-in
  that needs the host's recorded consent — see [`governance.md`](governance.md) §4 before you ever
  set it.** Doing nothing leaves a node `coarse`, which is correct for almost every node.
  `public-place` also publishes the exact coordinate, and is only for a location with **no host at
  all** — a city centroid, a model grid cell, a civic building. It exists so the consent check can
  stay meaningful: a public place has nobody whose consent could be recorded, so warning about it
  forever would only bury the hosted node that genuinely needs one
  ([ADR 0040](adr/0040-a-public-place-is-not-a-host.md)). If a person lives at the coordinate, it is
  `precise` with a `consent_ref`, never `public-place`.

Aim for overlapping coverage so one node dropping offline does not blind a block. The current demo
uses 150 synthetic nodes on a roughly 150 m grid; use the coverage principle, not that fixture's
node count, when choosing a scale for your network.

## Step 4 — Register your reference monitor(s)

List the station(s) you will calibrate against:

```yaml
reference_monitors:
- monitor_id: ref-aqs-0010
  label: Regulatory AQS station (your city)
  source: US EPA AQS site 06-067-0010
```

`source` is free text that records the provenance of the reference data so anyone auditing the
calibration knows what the nodes were corrected against.

## Step 5 — Record your co-location windows

A co-location window is a period when one of your nodes sat next to the reference monitor, so the
fit has paired readings to learn the correction from. Record one window per `(node, parameter)`:

```yaml
calibration_windows:
- node_id: node-01
  reference: ref-aqs-0010
  parameter: temp_c          # temp_c | pm25_ugm3 | pm10_ugm3 (one entry each)
  start: '2026-06-01T00:00:00Z'
  end: '2026-06-03T23:00:00Z'
```

Notes:

- Timestamps are ISO-8601 UTC (the trailing `Z` matters).
- Calibrate the parameters you care about. In the example, PM2.5 and PM10 get a humidity-aware
  correction and temperature gets an enclosure offset — three windows per co-located node.
- A node with **no** co-location window stays **raw** and is shown **provisional** on the dashboard.
  That is correct and honest, not a failure: a provisional location renders neutrally and never asserts
  an AQI category. You can ship a mostly-provisional network on day one and calibrate nodes as their
  windows complete.
- Re-co-locating a node later and re-fitting produces a new correction recorded with its window —
  an audit trail, not a problem. Log it (see `governance.md` §8).

## Step 6 — Run the pipeline

With your nodes, reference monitor, and windows in place, run the three commands that turn the file
into a live network. (`make demo` from the warm-up already exercised these against the demo store;
now point them at your own config and store.)

```console
# 1. Fit corrections from your co-location data and apply them to the store.
$ uv run swelter calibrate --store store --config my-network.yaml

# 2. (Optional but recommended) check node health before you publish.
$ uv run swelter qc --store store
#    Shows each node offline / degraded / ok with completeness, and lists gaps.
#    Add --json for a machine-readable report.

# 3. Serve the dashboard, the open API, and the exports.
$ uv run swelter serve --store store --config my-network.yaml
```

`swelter serve` brings up everything at <http://127.0.0.1:8000>:

- the dashboard (map, sortable table, plain list — three equal views of one surface, default List
  view), with the location-name search, the "use my location" nearest-location button, the °F/°C toggle,
  and the on-screen ± uncertainty;
- the surface API: `/api/surface.json?hours=N` and `/api/surface.geojson` (each cell carries
  `label`, `uncertainty`, `aqi`, `aqi_window`, and `provisional`);
- the read-only OGC SensorThings 1.1 subset (`/v1.1/...`, including `Datastreams` and `Locations`);
- the CSV/JSON exports, each value carrying its calibration state, QC verdict, uncertainty, and
  `trustworthy` flag.

To regenerate the offline `web/sample-surface.json` (so the dashboard renders even when opened as
static files), run `make demo` — but note that target uses the bundled demo data; for your own
network, serve from your own store as above.

That is the whole afternoon: copy the file, register your locations and reference monitor, record the
windows, calibrate, and serve.

## Location precision and governance — read this before you go live

The single most important policy in swelter is location precision, because a sensor sits on a real
person's home. The defaults protect hosts at no cost to the mission, and the guidance is in
[`governance.md`](governance.md). The short version:

- **Coarse is the floor and the default.** Every published coordinate is snapped to the
  `grid_resolution_m` cell. A reader of the map, table, CSV, or API sees the cell, never the porch.
- **Precise is a per-node, host opt-in that is never required.** Everything in swelter — ingest, QC,
  calibration, aggregation, dashboard, API, export — works fully on coarse locations. A host who
  never opts in loses nothing.
- **Disclosing a precise location is the host's decision, recorded.** Only that node's host may
  consent, the consent is written in the governance log, and the `network.yaml` change references
  it. Published coordinates can be copied beyond the collective's control—and an authorized CC0
  dedication cannot be recalled—so treat precise as permanent. When in doubt, stay coarse.
  (`governance.md` §3–§4.)
- **The collective owns the network.** Siting, grid resolution, and precision policy are the local
  collective's to decide; swelter is a tool the group runs, not a service that runs the group.
  Copy `governance.md` into your repo and adapt the roles, quorum, and cadence; keep the five hard
  rules. (`governance.md` §1, §6, §7, §9.)

## About this network (a note residents can read)

Copy the note below onto a flyer, a meeting handout, or your network's front page. Edit the bracketed
parts. It is written for neighbors, not engineers, and it states plainly what the map shows and what
coarse locations mean. (A standalone version lives in
[`ABOUT-THE-NETWORK.md`](ABOUT-THE-NETWORK.md).)

> **About [Eastside Cooperative heat & air network]**
>
> This is a neighborhood-run network of small sensors that measure heat and air quality across the
> neighborhood, so we can see which areas get hottest and where the air is worst. It is run by us — the
> people who live here and host the sensors — not by a company. The readings are open data anyone
> can download and check.
>
> **What the map shows.** Each marker is a *location*, named for a place you know. Tap one for its
> reading. Air quality leads with the AQI number and a plain category (for example "Moderate"), with
> a short "What is AQI?" note and health guidance from the US EPA. The AQI shown is an **hourly**
> reading — a recent snapshot, not the official 24-hour average — and the map says so.
>
> **What "coarse location" means.** We never publish where a sensor actually sits. Every location is
> rounded to roughly a [150-meter] grid cell so the map answers "is this area hot?" without showing
> "there's a sensor on this house." Hosts' homes stay private by default.
>
> **Provisional readings.** A location whose sensor is not yet calibrated is marked **provisional** and
> shown plainly as not-yet-confirmed — we never dress up an unverified reading as a fact. The combined
> heat-and-air exposure level stays provisional until both its heat and air readings are confirmed.
>
> **The data is portable.** Download the readings, check our work, or take a full copy and run the
> network elsewhere. Data produced by this collective is [CC0 / insert the terms the collective
> actually adopted]; readings fetched from another provider keep that provider's license and
> attribution. See the data notice shipped with each export.
>
> Questions, or want to host a sensor near you? [contact / meeting details].
