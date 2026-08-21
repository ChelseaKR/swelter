# swelter dashboard

A framework-free exposure observatory with a small, generated Unicode MessageFormat 2 runtime. It
uses no bundler and makes no runtime package or font request: the install step pins and vendors the
MF2 implementation beside the static shell and per-language string bundles. It is served by
`swelter serve` and is equally happy behind any static web server or GitHub Pages.

## Why no framework

The people this tool is for open it on an old phone on a slow connection. A 2 MB JavaScript
bundle is a barrier, not a feature. Plain HTML/CSS/ES modules plus one exact MF2 runtime keep the
page small and auditable. `npm ci` verifies the lock and generates `web/vendor/messageformat/`;
production never fetches that dependency from a third party. The page installs as a PWA
(`manifest.webmanifest` + `sw.js`) so it opens offline at a tenant meeting or a council hearing with
no signal.

## Current reading and Readings

The first screen answers the resident's immediate question: what the network reports, where, how
fresh it is, whether it is provisional or confirmed/upstream-model data, and what sourced guidance
applies. Search and on-device geolocation select a place without creating an account or sending a
location to swelter.

Readings links four representations of the same published surface:

- **Exposure braid** — a keyboard- and pointer-operable SVG history. The line is observed data, the
  band is published uncertainty, provisional points are hatched, and missing buckets remain visible
  gaps rather than interpolated values. Two native range controls set the history window.
- **Network distribution** — a selectable ranking for the chosen hour. Selecting a bar updates the
  Current reading card, map/list/table selection, evidence inspector, and shareable URL.
- **Evidence inspector** — the selected place's trend, comparison, protective actions, watch,
  uncertainty, provenance, share card, and download.
- **Map, Table, and List** — three equal data representations. Larger screens open Map first; narrow
  screens open List first.

## Three equal data representations, one dataset

The map is never the only way in. The **Map**, **Table**, and **List** tabs render the
identical aggregated surface:

- **Map** — a fixed geographic projection over the California basemap. Every marker remains on its
  published latitude/longitude. At the statewide overview, nearby markers are represented by a
  numbered group anchored to one of those real mapped places; activating it changes only the camera
  and reveals its members. Each reading remains in the Map DOM with text and an accessible name.
- **Table** — a real, sortable `<table>` with a row per cell. This is the canonical
  screen-reader path: the full dataset with no map required.
- **List** — a plain readings list, one sentence per cell.

Map zoom, pan, and group activation never recompute the projection or move a reading relative to the
state outline. Routes without `basemap.geojson` retain a data-fit positional fallback, but the
published California routes include the basemap. List and Table always expose every record even when
the overview represents nearby Map targets as one group.

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
surface that actually won the route's configured provider/fallback chain. It names that source and
its geography, calibration posture, reuse terms, and exact available measurements. Its `runtime:
"static"` flag lets the dashboard load the baked files directly instead of probing `/api/*` routes
that cannot exist on Pages. A normal `swelter serve` deployment has no contract and continues to
prefer the live API before falling back to `sample-surface.json`.

Static routes paint from `sample-surface.json`, which contains only the newest published bucket,
then fetch `surface-7d.json` in the background to enrich the linked history views. Publication also
retains the newest 24 hours in `surface-24h.json`; neither history artifact is truncated to the
initial snapshot. Both are written as compact JSON, because they are parsed rather than read: they
carry one record per (place, hour, parameter), so the 7-day file published on 2026-08-19 held
340,033 records and 152,665,280 bytes before compaction and 103,463,029 after. The service worker
deliberately does not precache it — the one-bucket sample remains the offline baseline, and history
is cached only after a browser actually requests it. A file that large is still more than a phone
should have to parse; shrinking it structurally is
[issue #181](https://github.com/ChelseaKR/swelter/issues/181).

The committed 150-node synthetic worked example remains a compact Sacramento calibration fixture in
the store. Its static web presentation is deterministically assigned to validated public California
place centroids so the default map demonstrates the statewide view without implying real statewide
sensor coverage. That preview mode is fail-closed to the exact generated fixture; custom networks
retain their configured geography.

## Accessibility

This page targets WCAG 2.2 AA. `scripts/a11y_check.py` holds the structural floor, while
`npm --prefix web run verify` is configured to run MF2 catalog/copy/design-token contracts,
Playwright plus Axe, Pa11y, and Lighthouse budgets. The browser assertions cover distinct root and
Sensor.Community route fixtures; Chromium, Firefox, and WebKit; light/dark schemes; English/Spanish
Axe scans of every view; primary keyboard tasks; `elementsFromPoint` focus non-obscuration;
Map/List/Table record equivalence; all-view 320px reflow; reduced motion; pseudolocale expansion; and
an actual Arabic RTL fixture. Target geometry includes native controls and focusable/pointer
composites in every view at desktop and 320px, with only the WCAG 2.5.8 inline-text and 24px-spacing
exceptions.

CI is the authoritative clean Node 22 run. Its current browser gate passes the MF2 unit suite,
Chromium/Firefox/WebKit conformance, Axe, Pa11y, and both-route Lighthouse budgets. That automation
does not replace the open current NVDA/VoiceOver review.

The [public accessibility statement](../docs/accessibility/STATEMENT.md),
[criterion-level ACR](../docs/accessibility/ACR.md), and custom
[braid](../docs/accessibility/APG-BRAID.md) / [map](../docs/accessibility/APG-MAP.md) keyboard
contracts record the evidence and its limits. The last full NVDA/VoiceOver baseline predates the
expanded linked views, so the statement keeps that rerun explicitly open rather than treating
automation as manual signoff.

```console
$ make verify-web  # locked install + Chromium/Firefox/WebKit + unit/Axe/Pa11y/Lighthouse
```

### Browser support policy

The automated compatibility floor runs the Playwright versions locked by `web/package-lock.json`
against Chromium, Firefox, and WebKit on every browser job and again from the signed release tag.
Weekly npm update PRs keep those engine builds current. The product target is the current and prior
stable releases of Chrome, Firefox, Safari, and Edge. Chromium is the fail-closed engine proxy for
both Chrome and Edge; before a formal release, the current and prior branded Edge builds receive a
short manual smoke of source switching, Map/List/Table navigation, language switching, and export.
Any branded-Edge-only defect blocks the release and becomes a reproducible Playwright regression when
the runner can install that channel. This policy does not describe Chromium alone as proof that a
specific branded Edge release passed.

Regenerate the offline sample with `make demo` (it writes `sample-surface.json`).

## Run it

```console
$ npm --prefix web ci  # verifies the lock and generates the local MF2 runtime
$ make demo            # replay recorded data and serve at http://127.0.0.1:8000
# or
$ uv run swelter serve --store store
```

## GitHub Pages search metadata

The committed HTML stays portable for self-hosting. During the GitHub Pages build,
`scripts/pages_seo.py` consumes the built demo contract, then replaces the marked metadata block
with an absolute canonical URL for each known route, source-aware social metadata, and a Schema.org
graph for the software and the dataset that actually won the live-source fallback. A compatibility
path reads the baked attribution on pre-contract artifacts and fails if it cannot identify exactly
one source. The same build writes `/swelter/sitemap.xml`. `node scripts/render_social_card.mjs`
regenerates the deterministic SVG social-card source from the committed California basemap; keep its
1280×640 PNG raster in sync when the card changes.

## Deployment and release identity

Every Pages build writes `version.json` and a `swelter-build-commit` meta tag on both `/` and
`/sensors/`. The document records the full repository/ref/commit, workflow run, and source-commit
timestamp, so a running static route can be traced to its exact build without relying on mutable UI
copy. The source-aware dataset timestamps and rights manifests remain separate: code identity never
stands in for data freshness or provider terms.

Each signed version tag also builds `swelter-observatory-VERSION.tgz`. It contains the two stamped
routes, an exact per-file hash manifest, code/data notices, and the vendored MessageFormat runtime.
Both routes are complete static builds with a source contract and local history surface. Because a
signed tag does not fetch mutable upstream readings, the root is the reproducible synthetic worked
example and `/sensors/` honestly carries the same data as a Sensor.Community fallback—not a claim of
live sensor data. The Pages workflow remains the source-aware path for current public readings;
the tagged artifact instead stamps stable repository, tag, commit, and commit-timestamp identity and
never embeds a mutable workflow run ID. Its adjacent CycloneDX 1.7 BOM links the archive and binds
the complete generated MessageFormat runtime with a sorted tree digest, every vendored file hash,
and the Apache-2.0 license recorded by the exact package lock. The release workflow attests, signs,
checksums, stages, downloads, and independently verifies that frontend artifact with the Python
distributions. Source maps are N/A: the shipped JavaScript is already the unminified, open-source
ES-module source, and there is no transformed bundle whose mapping could be generated or
access-controlled.

There is intentionally no `web/robots.txt`. This repository publishes a GitHub Pages **project**
site at `/swelter/`, while the robots exclusion protocol only recognizes `/robots.txt` at the
origin root. A `/swelter/robots.txt` file would look authoritative but control no crawler. Until the
origin root or a custom domain is controlled, the dashboard uses page-level `robots` metadata and
the sitemap can be submitted directly to search engines.
