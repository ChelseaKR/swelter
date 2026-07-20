# Exposure braid keyboard contract

Last reviewed: 2026-07-16

The exposure braid is a custom time-series visualization. ARIA APG does not define a chart pattern,
so swelter uses a named focusable group plus native controls and text equivalents instead of
inventing chart roles or presenting the plot as a slider.

## Semantics and alternatives

- `#exposure-braid` is one focus stop with `role="group"`, an accessible heading, instructions, the
  range summary, the method note, and the selection status referenced through ARIA.
- Its generated SVG is decorative (`aria-hidden="true"`, `focusable="false"`). Individual points do
  not create dozens of competing focus stops.
- `#braid-summary` states the location, range, minimum, median, maximum, provisional count, and gap
  count. The List and Table retain the underlying readings.
- `#range-start`, `#range-end`, and the main time input are native range controls. They remain the
  robust alternative for assistive technology that does not benefit from plot navigation.

## Keys

| Key | Result |
| --- | --- |
| Tab / Shift+Tab | Enter or leave the visualization as one focus stop. |
| Left Arrow / Right Arrow | Select the previous or next published observation inside the chosen evidence window. |
| Home / End | Select the first or last observation in that window. |

Pointer selection snaps to the nearest published observation by elapsed time. Every successful
keyboard or pointer change updates the native time input, linked views, URL state, and the polite
selection status. Missing buckets remain gaps and are not synthesized into focus targets.

## Deliberate deviations

- This is not an APG slider: it does not expose `role="slider"`, `aria-valuemin`, or
  `aria-valuemax`. Those semantics belong to the adjacent native range inputs.
- Points are not tab stops. A single group avoids an unbounded focus sequence while the status and
  text summary expose the same result.
- Selection uses physical Left/Right Arrow because the x-axis is chronological in both LTR and RTL
  documents; time does not reverse when interface direction changes.

Automated tests exercise the key sequence and linked state. The expanded component still requires
the manual NVDA and VoiceOver walkthrough recorded as pending in the accessibility statement.
