# ADR 0033: Preserve statewide geography and cluster only the overview

- Status: Accepted
- Date: 2026-07-31
- Deciders: Chelsea Kelly-Reif
- Supersedes: the schematic-layout and collision-relaxation portions of ADR 0004

## Context

ADR 0004 established a framework-free dashboard and equal Map, Table, and List outcomes. Its
2026-07-18 amendment handled dense markers by moving overlapping controls away from their projected
positions. That solved target overlap, but it weakened the map's central claim: a reading could be
drawn somewhere other than its published coordinate. On the California route, a compact network
could appear to cover the whole state, and zooming into a dense group could produce a field of
markers with no stable relationship to the state outline.

The default static demonstration is statewide. It needs to communicate geographic coverage at a
glance, preserve each public coordinate through every interaction, keep nearby controls operable at
normal and enlarged text sizes, and retain the complete non-map alternatives required by ADR 0004.
Loading a tile service or mapping framework would add runtime requests and dependencies to a static,
offline-capable interface.

## Decision

When `basemap.geojson` is present, the browser derives one padded, equirectangular projection from
the California basemap bounds and uses it for both the state/county geometry and every reading. The
longitude axis is scaled by the cosine of the projection's midpoint latitude. A marker's position is
derived once from its published latitude/longitude; drag, pinch, wheel, keyboard, button zoom, reset,
and selection change only the camera. The SVG basemap view box and the fixed-size HTML targets are
both recalculated from that same camera, so they remain aligned at every scale. A deployment without
a basemap retains the existing data-fit fallback rather than pretending to have geographic context.

At the statewide overview, readings that would create overlapping targets are represented by
numbered groups. Dense surfaces use screen-pixel bins; smaller surfaces group only controls that
would overlap. Each group is anchored to the real member nearest the group's center, so a coastal
group cannot be placed offshore merely to make room. Activating a group by pointer or keyboard fits
the camera to its members without changing the projection or any member position. The group control
then yields to the underlying reading controls when the camera reaches their reveal scale. Reset
restores the complete statewide camera.

Clustering changes only the overview controls. Every reading remains a complete Map record in the
DOM, and the semantic List and sortable Table always expose the full filtered dataset. The three
representations retain the same record keys, labels, values, provisional state, selection, and
deep-link state. Map interaction is never required to reach an individual record.

The canonical 150-node synthetic fixture uses a separate, deterministic web-preview mapping to
validated public California place centroids. Its compact Sacramento coordinates remain unchanged in
the worked-example store, and the preview marker is accepted only for that exact generated fixture;
a custom community network is never silently spread across the state.

## Alternatives considered

- **Continue collision relaxation.** Rejected because accessible spacing is not permission to move a
  measurement away from its published geography.
- **Render every marker at the statewide overview.** Rejected because dense regions produce
  overlapping targets and unreadable visual weight, especially with enlarged text.
- **Use one statewide count.** Rejected because it erases the distribution of coverage and gives no
  meaningful place from which to inspect a local group.
- **Adopt a tile map or mapping framework.** Rejected for this reference deployment because the
  committed California geometry and small projection preserve offline/static operation without a
  runtime service or frontend framework.

## Consequences

The default view now communicates real statewide positioning, and a local inspection retains enough
state context to explain where it is. Accessible target spacing no longer changes the data's spatial
meaning. Overview groups are an intentional summary rather than 150 simultaneous reading controls;
the full Map DOM, List, and Table preserve outcome parity.

The browser owns more camera and clustering code, including a deep zoom range for tightly spaced
public coordinates. Changes to projection, basemap bounds, group thresholds, target size, or text
scaling require cross-browser regression evidence. The California basemap is decorative and is not
an administrative-boundary query service; public coordinates remain governed by ADR 0003.

Executable evidence:

- `web/tests/browser/conformance.spec.js::map keyboard pan, zoom, reset, selection, and equivalent views change real state`
- `web/tests/browser/conformance.spec.js::larger text preserves the map center and keeps a selected overview singleton clear`
- `web/tests/browser/conformance.spec.js::Map, List, and Table expose the same complete record set on both routes`
- `web/tests/app.unit.test.js::markerClusters anchors groups to real places and merges overlapping adjacent-bin controls`
- `web/tests/app.unit.test.js::fitMapBounds zooms the camera without changing projected marker positions`
- `web/tests/app.unit.test.js::the California overview keeps one projection while a cluster changes only the camera`
- `tests/test_web_preview.py::test_demo_web_preview_is_deterministic_statewide_and_geographically_mixed`

The acceptance contract is maintained under F-07, F-08, and F-16 in
[`../ACCEPTANCE-TEST-MAP.md`](../ACCEPTANCE-TEST-MAP.md).
