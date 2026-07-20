# Map keyboard contract

Last reviewed: 2026-07-16

The map is a spatial enhancement over the same readings mounted in the List and Table tabs. ARIA APG
does not define an interactive-map pattern, so the map uses a named focusable group, native marker
buttons, native zoom buttons, and complete non-map alternatives.

## Semantics and alternatives

- `#map` is a focusable `role="group"` with instructions in visible text.
- Each visible reading marker is a native button whose accessible name states the place, reading,
  category, uncertainty or provisional state, and observation time.
- Zoom in, zoom out, and reset are separate native buttons with visible focus.
- List provides one sentence per reading. Table provides a caption, column and row headers, sortable
  columns, and the complete active dataset. Only the selected tab's equivalent view is mounted, so a
  dense network does not impose thousands of hidden accessibility-tree nodes.

## Keys and equivalent controls

| Input | Result |
| --- | --- |
| Tab / Shift+Tab | Move among the map group, zoom controls, and marker buttons. |
| Arrow keys while the map group is focused | Pan in one axis. |
| Plus / Minus | Zoom in or out. |
| Reset button | Restore the fitted view without a gesture. |
| Enter / Space on a marker | Select that place across Now, distribution, evidence, List/Table, and the shareable URL. |

Drag, wheel, and pinch gestures are optional. Every outcome has a button or keyboard path, and no
task requires multipoint or path-based movement. Markers meet the 24 CSS-pixel target floor; a
separate geometry test measures every visible control.

## Deliberate deviations

- The map is not a `grid`, `tree`, or `application`; those roles would promise navigation semantics
  it does not implement.
- Arrow keys pan the viewport rather than moving an active-descendant cursor. Marker buttons remain
  ordinary Tab stops, while List and Table are the efficient paths for sequential data review.
- Geographic position is not the only relationship exposed. Place names, values, categories, and
  selection state remain explicit text.

Automated tests cover keys, targets, focus, and equivalent-view switching. The expanded sequence
still requires the manual screen-reader walkthrough recorded in the accessibility statement.
