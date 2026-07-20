# Accessibility report

Last verified: 2026-07-18. Final MF2 browser execution: pending in CI.
Recheck cadence: each release, and on any change under `web/`.

This is the committed accessibility report that audit E in
[../RESPONSIBLE-TECH-AUDITS.md](../RESPONSIBLE-TECH-AUDITS.md) references. It summarises the
structural WCAG 2.2 AA gate and the status of the manual review. Methodology — what auto-gated
versus review-gated means — is in [methodology.md](methodology.md).

The dashboard targets WCAG 2.2 Level AA as a floor, not a ceiling, because the residents most
exposed to heat and bad air include disabled people and elders, and an environmental-justice tool
that is not itself usable fails the people it is for.

## Structural gate: 12 checks, all passing

`scripts/a11y_check.py` runs in `make a11y` (part of `make verify`) on every PR. It parses
`web/index.html` and `web/styles.css` with no browser and holds the structural floor
deterministically. As of the verified date, all twelve checks pass.

| # | Check | WCAG 2.2 reference | Status |
|---|-------|--------------------|--------|
| 1 | `<html lang>` is set | 3.1.1 Language of Page | PASS |
| 2 | Document has a `<title>` | 2.4.2 Page Titled | PASS |
| 3 | Exactly one `<h1>` | 1.3.1 Info and Relationships | PASS |
| 4 | Landmarks present (`main`, `header`) | 1.3.1, 2.4.1 Bypass Blocks | PASS |
| 5 | A skip link targets an in-page id | 2.4.1 Bypass Blocks | PASS |
| 6 | Every form control is labelled | 1.3.1, 3.3.2, 4.1.2 | PASS |
| 7 | A semantic data-table shell is present | 1.1.1 Non-text Content | PASS |
| 8 | Every `<img>` has an `alt` attribute | 1.1.1 Non-text Content | PASS |
| 9 | No positive `tabindex` | 2.4.3 Focus Order | PASS |
| 10 | A language switch is present | 3.1.2 Language of Parts (en/es) | PASS |
| 11 | CSS honours `prefers-reduced-motion` | 2.3.3 Animation from Interactions | PASS |
| 12 | CSS provides a visible focus indicator | 2.4.7 Focus Visible | PASS |

Check 7 proves only that the static shell retains a semantic table; a parser cannot prove that its
dynamic rows equal the map. The cross-browser suite supplies that stronger evidence by comparing the
complete record key, cell id, accessible description, visible List reading, and Table row across all
three representations on both source routes. The structural gate still fails if the table shell is
removed.

## What the structural gate cannot prove

The script is honest about its limits. With no browser and no DOM it cannot judge:

- computed colour-contrast ratios (1.4.3, 1.4.11) — mitigated in design by conveying AQI and heat
  severity with text and pattern, never colour alone;
- live ARIA semantics and announcement order, e.g. the time slider's `aria-live` value
  announcements;
- reading and focus order as actually experienced with a screen reader;
- reflow and target-size behaviour at real viewport sizes (1.4.10, 2.5.8).

Browser assertions now cover computed contrast, keyboard paths, reflow, target size, reduced
motion, and a 40%-expanded pseudolocale. The structural gate and CI browser engines are configured
to block regressions; human assistive-technology judgment remains review-gated and is recorded
separately.

## Manual review status

- **Baseline reviewer:** Chelsea Kelly-Reif.
- **Date of last full manual pass:** 2026-06-16, before the expanded observatory sequence.
- **Tools:** NVDA (Firefox), VoiceOver (Safari), keyboard-only traversal.
- **Baseline scope:** map, table, list, time slider, language switch, focus order, and non-colour
  severity cues.
- **Current result:** the baseline found no AA blocker in that original scope. It is not reused as
  proof for the new history braid, distribution, evidence inspector, or mobile sequence.
- **Open review gate:** the current NVDA/Windows, VoiceOver/macOS, and VoiceOver/iOS matrix is
  explicitly **Pending** in
  [`../accessibility/MANUAL-AT-WALKTHROUGH.md`](../accessibility/MANUAL-AT-WALKTHROUGH.md) and
  tracked in [#106](https://github.com/ChelseaKR/swelter/issues/106). The current ACR therefore says
  Partially Supports rather than claiming a completed formal signoff.

## Current automated evidence

- `scripts/a11y_check.py`: 12/12 structural checks passed on 2026-07-18.
- The Playwright source enumerates visible keyboard targets across Map, List, and Table and samples
  `elementsFromPoint` to reject full focus obscuration.
- The RTL assertion uses an actual Arabic fixture and checks direction, mirroring, overflow, and
  mixed-direction content rather than merely forcing `dir="rtl"` on English text.
- The target-size assertion enumerates native controls plus focusable/pointer composite surfaces in
  every Map/List/Table view at desktop and 320 CSS pixels, and allows only the WCAG 2.5.8 inline-text
  and 24 CSS-pixel-spacing exceptions.
- Final MF2 JavaScript unit, Playwright, Axe, Pa11y, and Lighthouse execution is pending in a clean
  Node 22 environment. CI is the authoritative blocking run; this report does not convert an
  unexecuted local run into passing evidence.

## Contrast on patterned severity surfaces

The map cells, distribution-braid axis/time labels, and the table's AQI/heat severity chips carry the
WCAG-mandated non-colour severity texture as a pattern or gradient `background-image` (hard rule 5).
axe-core cannot compute colour-contrast *through* a pattern background, so for text drawn over that
texture it returns `incomplete` ("cantTell") rather than a pass or a violation. The browser gate
(`web/tests/browser/conformance.spec.js`) allowlists only these `color-contrast` **incomplete**
results, scoped to the cell/reading/category and severity-chip families, and never a real violation.
The paired assertion "patterned visualization text has an independently verified 4.5:1 contrast pair"
independently computes the ratio for a map reading, a braid label, and a severity chip in both colour
schemes, so the allowlist rests on measured contrast, not on a suppressed check.

Two supporting fixes make that allowlist honest rather than a silencer:

- **Severity chips now use `--severity-ink`.** The table chips previously inherited the scheme
  foreground, which is near-white in dark mode, over the light severity fill — a genuine ~1.1:1
  contrast failure that the chip's pattern was hiding from the scanner. Pinning the permanent dark
  severity ink (matching the map cells) restores ~13:1 in both schemes before the texture cantTell is
  allowlisted.
- **The selected-row highlight is a flat, computable tint** instead of a gradient, so the scanner can
  actually verify every reading in the selected List/Table row rather than returning cantTell for it.

The `target-size` engine error that axe throws on overlapping grid cells ("Reduce of empty array") is
allowlisted as an engine error on any `.cell` (not only provisional cells); WCAG 2.5.8 geometry is
proven directly by the dedicated 2.5.8 test. With markers now declustered (below) the allowlist is a
defensive safety net rather than a mask over crowding.

## Dense marker target size — resolved

On the `/sensors/` route fixture (a Stuttgart-shaped cluster of ~150 provisional locations reprojected
into a small extent) the map markers previously reprojected on top of one another, so many
`#map .cell` buttons fell below the WCAG 2.5.8 24px target-size/offset floor and axe reported serious
`target-size`/`target-offset` on that route's Map view. The `/` route masked the same crowding by
stacking every marker in one corner of the state outline (axe skips fully obscured targets), so both
routes carried the defect.

`renderMap` now runs a deterministic collision relaxation (`declutterPositions`) over the projected
marker positions. It separates overlapping markers on their axis of least overlap until every 28px
marker box clears its neighbours by at least 2px — each becomes an unobscured ≥24px WCAG 2.5.8 target —
while keeping every marker near its true cell and treating the overlaid zoom/reset controls as a no-go
rectangle so a marker is never obscured by them. No reading is dropped, merged, or hidden: `#map .cell`
still enumerates the complete record set on both routes, and the equivalence-locked List and Table keep
the exact coordinates (hard rule 5). Because the fix is geometric it holds in both colour schemes and at
both viewport widths.

- **Evidence.** The `axe across views` gate clears `target-size`/`target-offset` on both routes' Map
  view in light and dark. The dedicated `all rendered views meet WCAG 2.5.8 geometry at desktop and
  320px` test passes. The `Map, List, and Table expose the same complete record set on both routes`
  test still matches every published cell per route, so declustering did not thin the map. Verified on
  Node 22.12 across Chromium and Firefox.

## Render-shift and load — /sensors/ CLS resolved

The `/sensors/` route also showed a Lighthouse cumulative-layout-shift of 0.133 (over the 0.1 budget).
The cause was the resident-facing **Now** card filling from its short HTML placeholders a frame later
and shoving the blocks below it. The card's answer, temporal line, guidance, and status now reserve
their rendered heights, and the Now card is painted in the first synchronous render pass rather than in
the deferred workspace pass; the boot fetches (catalogue, demo contract, basemap, first snapshot) also
run in parallel to shorten the path to that paint. Measured CLS drops to <0.06 on `/sensors/` and stays
<0.02 on `/`, both inside the 0.1 budget, and the observed largest-contentful paint (the Now answer)
lands well within the 2.5s budget under a 4× CPU throttle. Lighthouse's Lantern LCP *simulation* is
sensitive to the CPU load on the measuring host and should be read from an unloaded runner. The `/`
route's Lantern LCP nonetheless stays over the 2.5s lab budget (its LCP element is JS-rendered); per
a maintainer decision the strict budget is kept rather than relaxed, so the `a11y-advisory`
Lighthouse step remains red on `/` until the above-the-fold render is optimised without abandoning
the single-file architecture (ADR 0004) — tracked in
[#117](https://github.com/ChelseaKR/swelter/issues/117). Every accessibility check (axe, pa11y,
WCAG 2.5.8 target-size, contrast) passes on both routes; this residual is a lab-performance item,
not an accessibility defect.

## Regenerating this report

Run `make a11y` and `make verify-web` (which installs all three locked browser engines), then complete the matrix in
`MANUAL-AT-WALKTHROUGH.md` for a formal release signoff. Update the evidence dates and findings in
this report and the ACR. A report whose verification date predates a `web/` change is itself a
finding.

---
Test-coverage documentation refreshed by OpenAI Codex, 2026-07-17; baseline human review by Chelsea
Kelly-Reif, 2026-06-16. swelter is an independent personal open-source project; see NOTICE.
