# ADR 0016: Bake the provisional label and hourly-window caveat into share-card pixels, not overlaid HTML

- Status: Accepted
- Date: 2026-07-02
- Deciders: Chelsea Kelly-Reif

## Context

The dashboard already puts real effort into never letting a number travel without its caveats on
screen (R5/R9, ADR 0008's claim discipline) — provisional cells are marked with `~` and a text
label, and the AQI legend states the hourly-vs-24-hour window. A screenshot defeats all of that:
crop out the caption or the legend below the fold and a `~112 AQI` becomes an unqualified `112`
that a resident, reporter, or advocate then shares as if it were a confirmed daily figure. E2's
"show your work" trust view and E1's advocacy brief both assume the *text* travels with the
number; a share card is the same guarantee for the *image* — the format people actually screenshot
and forward. Rendering the caveats as canvas pixels rather than an HTML overlay means there is no
DOM to crop around: whatever the PNG contains is the whole message, byte for byte, once saved.

## Decision

Give the detail panel a **"Save share card"** button (`web/index.html`, `#share-card`) that renders
the currently selected location to an offscreen `<canvas>` and downloads it as a PNG
(`buildShareCanvas` / `saveShareCard` in `web/app.js`). The card always draws, as canvas pixels:

- the place name and the measurement + selected hour (`fmtBucket(currentBucket())`), so the image
  states *what* was measured and *when*, not just a bare number;
- the same reading text the list/detail view already shows (`describe(row)`), so the exported
  number can never drift from what the page displayed;
- the "hourly mean, not a 24-hour average" window caveat (`share-card-window`), the same fact the
  legend states at `web/index.html` for the AQI window, generalized to every measurement so the
  card is honest about the reading's time base regardless of parameter;
- a visible amber **provisional band** (`share-card-provisional`), reusing the existing `~`
  convention (`exposureReading`, `describe`), whenever `row.provisional` is true.

No library is used — canvas 2D `fillText`/`fillRect`/`strokeRect` only, CSP-safe and consistent
with the dashboard's zero-dependency posture (ADR 0004). The download reuses the existing
object-URL + temporary `<a download>` pattern already used elsewhere in the file. The card renders
in the page's current locale via the existing `t()` catalog, so an `es` export carries Spanish
labels, and the button's own accessible name comes from visible i18n text, the same pattern as
every other detail-panel control.

## Consequences

The card is a fixed-size (1000×620) layout with a simple greedy word-wrap; an unusually long place
name or reading string could in principle push the provisional band or footer close to the card's
bottom edge. Existing place labels and reading strings are short enough in practice that this has
not been observed, but a future very long label is a rendering risk worth watching, not a crash
risk (canvas silently draws past its own edge). The card is a point-in-time export of what is on
screen when clicked — it does not itself watermark or timestamp against tampering, so a bad-faith
actor could still edit the PNG in an image editor; the goal is to raise the bar for the common case
(an honest crop) that is very common, not to defeat deliberate forgery. The card always renders
light-on-white regardless of the page's high-contrast setting, a deliberate choice so the exported
image is legible standalone once shared outside the app's own theme context.

Last verified: 2026-07-02. Recheck cadence: revisit if the detail panel gains new caveats (e.g. a
future data-quality flag) that a share card claiming to speak for "the reading" should also carry.
