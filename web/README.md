# swelter dashboard

A framework-free, dependency-free exposure observatory. No build step, no bundler, no runtime npm:
four static shell files (`index.html`, `styles.css`, `observatory.css`, `app.js`) plus per-language
string bundles. It is served by `swelter serve` and is equally happy behind any static web server or
GitHub Pages.

## Why no framework

The people this tool is for open it on an old phone on a slow connection. A 2 MB JavaScript
bundle is a barrier, not a feature. Plain HTML/CSS/ES-modules keeps the page tiny, auditable,
and durable — there is no toolchain to rot. It installs as a PWA (`manifest.webmanifest` +
`sw.js`) so it opens offline at a tenant meeting or a council hearing with no signal.

## Resident-first Now, evidence-rich Explore

The first screen answers the resident's immediate question: what the network reports, where, how
fresh it is, whether it is provisional or confirmed/upstream-model data, and what sourced guidance
applies. Search and on-device geolocation select a place without creating an account or sending a
location to swelter.

Explore links four representations of the same published surface:

- **Exposure braid** — a keyboard- and pointer-operable SVG history. The line is observed data, the
  band is published uncertainty, provisional points are hatched, and missing buckets remain visible
  gaps rather than interpolated values. Two native range controls set the history window.
- **Network distribution** — a selectable ranking for the chosen hour. Selecting a bar updates the
  Now card, map/list/table selection, evidence inspector, and shareable URL.
- **Evidence inspector** — the selected place's trend, comparison, protective actions, watch,
  uncertainty, provenance, share card, and download.
- **Map, Table, and List** — three equal data representations. Larger screens open Map first; narrow
  screens open List first.

## Three equal data representations, one dataset

The map is never the only way in. The **Map**, **Table**, and **List** tabs render the
identical aggregated surface:

- **Map** — a schematic plot of sensor cells (not map tiles; an honest positional layout).
  Each marker states its reading in text and carries an accessible name.
- **Table** — a real, sortable `<table>` with a row per cell. This is the canonical
  screen-reader path: the full dataset with no map required.
- **List** — a plain readings list, one sentence per cell.

Air-quality severity is conveyed by **text and pattern**, never color alone. Cells with only
uncalibrated readings are labelled **provisional**, never shown as confirmed fact. The time slider,
history window, tabs, and exposure braid are keyboard operable; the selected time and linked-view
changes are exposed as text/status output.

## Data it reads

| What | Endpoint (live) | Static fallback |
| --- | --- | --- |
| Fast snapshot, then history | `GET /api/surface.json?hours=1`, then `?hours=168` | `sample-surface.json`, then lazy `surface-7d.json` |
| Map snapshot (GeoJSON, for GIS) | `GET /api/surface.geojson` | — |
| Full export | `GET /export.csv`, `GET /export.json` | — |
| SensorThings | `GET /v1.1/Things`, `/v1.1/Observations` | — |

The GitHub Pages build also writes `demo.json`, a source-of-truth contract generated from the
surface that actually won the OpenAQ → CAMS → synthetic fallback. It names that source and its
geography, calibration posture, reuse terms, and exact available measurements. Its `runtime:
"static"` flag lets the dashboard load the baked files directly instead of probing `/api/*` routes
that cannot exist on Pages. A normal `swelter serve` deployment has no contract and continues to
prefer the live API before falling back to `sample-surface.json`.

Static routes paint from the capped `sample-surface.json` first, then fetch `surface-7d.json` in the
background to enrich the linked history views. The service worker deliberately does not precache
that potentially multi-megabyte history file: the smaller sample remains the offline baseline, and
history is cached only after a browser actually requests it.

## Accessibility

This page targets WCAG 2.2 AA and is held to a structural floor on every PR by
`scripts/a11y_check.py` (`make a11y`), with a merge-blocking axe/pa11y pass and manual
NVDA/VoiceOver review recorded in [`../docs/accessibility/ACR.md`](../docs/accessibility/ACR.md).
Regenerate the offline sample with `make demo` (it writes `sample-surface.json`).

## Run it

```console
$ make demo          # replay recorded data and serve at http://127.0.0.1:8000
# or
$ swelter serve --store store
```

## GitHub Pages search metadata

The committed HTML stays portable for self-hosting. During the GitHub Pages build,
`scripts/pages_seo.py` consumes the built demo contract, then replaces the marked metadata block
with an absolute canonical URL for each known route, source-aware social metadata, and a Schema.org
graph for the software and the dataset that actually won the live-source fallback. A compatibility
path reads the baked attribution on pre-contract artifacts and fails if it cannot identify exactly
one source. The same build writes `/swelter/sitemap.xml`.

There is intentionally no `web/robots.txt`. This repository publishes a GitHub Pages **project**
site at `/swelter/`, while the robots exclusion protocol only recognizes `/robots.txt` at the
origin root. A `/swelter/robots.txt` file would look authoritative but control no crawler. Until the
origin root or a custom domain is controlled, the dashboard uses page-level `robots` metadata and
the sitemap can be submitted directly to search engines.
