# Map keyboard contract

Last reviewed: 2026-07-31

The map is a spatial enhancement over the same readings mounted in the List and Table tabs. ARIA APG
does not define an interactive-map pattern, so the map uses a named focusable group, native overview
cluster and reading buttons, native zoom buttons, and complete non-map alternatives. One fixed
projection aligns the California basemap and readings; interaction changes only the camera.

## Semantics and alternatives

- `#map` is a focusable `role="group"` with instructions in visible text.
- Each revealed reading marker is a native button whose accessible name states the place, reading,
  category, uncertainty or provisional state, and observation time.
- At the fitted statewide overview, nearby readings use a native cluster button. Its accessible name
  states the reading count and value range. `aria-expanded="false"` means its members are collapsed;
  the state changes to `true` when camera zoom reveals the member reading buttons.
- Zoom in, zoom out, and reset are separate native buttons with visible focus.
- List provides one sentence per reading. Table provides a caption, column and row headers, sortable
  columns, and the complete active dataset. Only the selected tab's equivalent view is mounted, so a
  dense network does not impose thousands of hidden accessibility-tree nodes.

## Keys and equivalent controls

| Input | Result |
| --- | --- |
| Tab / Shift+Tab | Move among the map group, zoom controls, and currently exposed cluster or reading buttons. |
| Arrow keys while the map group is focused | Pan in one axis. |
| Plus / Minus | Zoom in or out. |
| Reset button | Restore the fitted statewide view and collapsed cluster state without a gesture. |
| Enter / Space on an overview cluster | Fit the camera around that geographic group, reveal its reading buttons, update `aria-expanded`, and return focus to the named map group. |
| Enter / Space on a marker | Select that place across Current reading, distribution, evidence, List/Table, and the shareable URL. |

Drag, wheel, and pinch gestures are optional. Every outcome has a button or keyboard path, and no
task requires multipoint or path-based movement. Visible cluster and reading buttons meet the 24
CSS-pixel target floor; a separate geometry test measures every visible control.

## Deliberate deviations

- The map is not a `grid`, `tree`, or `application`; those roles would promise navigation semantics
  it does not implement.
- Arrow keys pan the viewport rather than moving an active-descendant cursor. Marker buttons remain
  ordinary Tab stops, while List and Table are the efficient paths for sequential data review.
- Clusters reduce overview density without changing data coordinates. Expanding a cluster changes
  the camera, not the shared projection; the state outline and readings stay geographically aligned.
- Geographic position is not the only relationship exposed. Place names, values, categories, and
  selection state remain explicit text.

Automated tests passed on 2026-07-31 across Chromium, Firefox, and WebKit, covering camera-only
cluster expansion, `aria-expanded`, keys, targets, focus, projection stability, and equivalent-view
switching. The expanded sequence still requires the manual screen-reader walkthrough recorded in the
accessibility statement.
