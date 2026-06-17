# swelter dashboard

A framework-free, dependency-free dashboard. No build step, no bundler, no npm: three static
files (`index.html`, `styles.css`, `app.js`) plus per-language string bundles. It is served by
`swelter serve` and is equally happy opened as static files behind any web server or GitHub
Pages.

## Why no framework

The people this tool is for open it on an old phone on a slow connection. A 2 MB JavaScript
bundle is a barrier, not a feature. Plain HTML/CSS/ES-modules keeps the page tiny, auditable,
and durable — there is no toolchain to rot. It installs as a PWA (`manifest.webmanifest` +
`sw.js`) so it opens offline at a tenant meeting or a council hearing with no signal.

## Three equal views, one dataset

The map is never the only way in. The **Map**, **Table**, and **List** tabs render the
identical aggregated surface:

- **Map** — a schematic plot of sensor cells (not map tiles; an honest positional layout).
  Each marker states its reading in text and carries an accessible name.
- **Table** — a real, sortable `<table>` with a row per cell. This is the canonical
  screen-reader path: the full dataset with no map required.
- **List** — a plain readings list, one sentence per cell.

Air-quality severity is conveyed by **text and pattern**, never color alone. Cells with only
uncalibrated readings are labelled **provisional**, never shown as fact. The time slider is
keyboard operable and announces its value through an `aria-live` output.

## Data it reads

| What | Endpoint (live) | Static fallback |
| --- | --- | --- |
| Time-sliced surface | `GET /api/surface.json?hours=72` | `sample-surface.json` |
| Map snapshot (GeoJSON, for GIS) | `GET /api/surface.geojson` | — |
| Full export | `GET /export.csv`, `GET /export.json` | — |
| SensorThings | `GET /v1.1/Things`, `/v1.1/Observations` | — |

If the live API is unreachable (for example, opened as static files), the page falls back to
the committed `sample-surface.json` so it still renders.

## Accessibility

This page targets WCAG 2.2 AA and is held to a structural floor on every PR by
`scripts/a11y_check.py` (`make a11y`), with an advisory axe/pa11y pass and manual
NVDA/VoiceOver review recorded in [`../docs/accessibility/ACR.md`](../docs/accessibility/ACR.md).
Regenerate the offline sample with `make demo` (it writes `sample-surface.json`).

## Run it

```console
$ make demo          # replay recorded data and serve at http://127.0.0.1:8000
# or
$ swelter serve --store store
```
