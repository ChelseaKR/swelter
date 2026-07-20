# ADR 0004: Ship a framework-free dashboard with three equal views, targeting WCAG 2.2 AA

- Status: Accepted
- Date: 2026-06-16
- Deciders: Chelsea Kelly-Reif
- **Amended:** 2026-07-16, 2026-07-18
- Build/runtime-dependency posture superseded by: ADR 0026

## Context

The people this tool is for open it on an old phone on a slow connection at a
tenant meeting or a council hearing, sometimes with no signal — a multi-megabyte
JavaScript bundle is a barrier, not a feature. Plain HTML/CSS/ES-modules keeps
the page tiny, auditable, and durable: there is no toolchain to rot and nothing
to rebuild years from now. Three equal views exist because the map cannot be the
only way in — a sortable table is the accessible, copyable, screen-reader-first
path to the same surface, and text-plus-pattern severity works for color-blind
and grayscale-print readers. WCAG 2.2 AA is the conformance target. Automated
structural and browser checks belong in the merge gate, while named manual
assistive-technology review remains separate release evidence; automation alone
cannot prove conformance. We rejected a SPA framework (a build step, a bundle, a dependency
tree to maintain, all of which we avoid elsewhere) and a map-only UI (excludes
non-visual users and assumes a fast connection).

## Decision

The dashboard under `web/` is plain HTML, CSS, and ES modules: no build step, no
bundler, no runtime npm. Four static shell files (`index.html`, `styles.css`,
`observatory.css`, `app.js`) plus
per-language string bundles, served by `swelter serve` or by any static host /
GitHub Pages. The Map, Table, and List tabs are three equal views of one
aggregated surface — the map is never the only way in, and the sortable `<table>`
is the canonical screen-reader path with the full dataset. Air-quality severity
is conveyed by text and pattern, never color alone; cells with only uncalibrated
readings are labelled provisional. The time slider is keyboard-operable and
announces its value through an `aria-live` output. The page ships en and es i18n
and installs as a PWA (`manifest.webmanifest` + `sw.js`). It reads
`GET /api/surface.json?hours=N` live and falls back to the committed
`web/sample-surface.json` when the API is unreachable. Accessibility is held to
automated structural and browser floors on every PR by the accessibility targets
inside `make verify`; the dated ACR records what those checks do and do not
establish.

The 2026-07-16 amendment adds a resident-first **Now** view and an analytical
**Explore** workspace without changing that architecture or data contract. Explore
adds a native-SVG history braid, a linked location distribution, and a persistent
evidence inspector around the existing Map/Table/List representations. The history
renderer draws only published buckets, leaves missing buckets as gaps, and shows
published uncertainty and provisional state directly. Desktop opens Map first;
narrow screens retain the lower-friction List default. The extra stylesheet is a
progressive visual layer; there are still no runtime dependencies or build output.

The 2026-07-18 amendment settles how the schematic map stays a valid WCAG 2.5.8
target surface when a dense network reprojects many readings into a tiny extent
(e.g. ~150 Sensor.Community locations inside a few hundred metres of Stuttgart),
stacking markers below the 24px target-size floor. Rather than thin the fixture
(fragile) or hide markers from the map (which would break the Map/List/Table
outcome-equivalence in invariant 5), `renderMap` declusters in place: a
deterministic collision relaxation separates overlapping markers on their axis of
least overlap until each 28px marker box is an unobscured ≥24px target, keeps each
marker near its true projected cell, and routes markers clear of the overlaid
zoom/reset controls. Every reading keeps its own marker, so the map still exposes
the complete record set and the equivalence-locked Table and List remain the exact
positional record. The map stays a schematic, framework-free, dependency-free
positional layout — the relaxation is a few lines of hand-written geometry, not a
mapping or force-layout library.

## Consequences

No framework means shared UI logic is hand-written in `app.js` and the linked
views must each be kept in sync with the surface shape by hand; there is no
component model to lean on as the UI grows. The structural `a11y_check.py` gate
catches a structural floor only — it is not a full audit. Browser automation and
manual NVDA/VoiceOver review are recorded separately in
`docs/accessibility/ACR.md`; the outstanding current manual signoff is tracked in
[issue #106](https://github.com/ChelseaKR/swelter/issues/106). The map is a schematic positional layout, not map
tiles, which keeps the page dependency-free and honest but means it is not a
geographic basemap. The committed `web/sample-surface.json` fallback can go stale;
`make demo` regenerates it.
