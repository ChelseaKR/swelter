# Accessibility report

Last verified: 2026-07-31. Automated MF2 and browser suites: passing in CI and locally.
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

- `scripts/a11y_check.py`: 12/12 structural checks passed on 2026-07-31.
- The equal 400-key English and Spanish MF2 catalogs passed extraction, parsing, placeholder, and
  unit contracts; the full JavaScript unit suite passed 117/117 checks.
- The Playwright source enumerates visible keyboard targets across Map, List, and Table and samples
  `elementsFromPoint` to reject full focus obscuration.
- The RTL assertion uses an actual Arabic fixture and checks direction, mirroring, overflow, and
  mixed-direction content rather than merely forcing `dir="rtl"` on English text.
- The target-size assertion enumerates native controls plus focusable/pointer composite surfaces in
  every Map/List/Table view at desktop and 320 CSS pixels, and allows only the WCAG 2.5.8 inline-text
  and 24 CSS-pixel-spacing exceptions.
- The browser suite passed 57/57 checks across Chromium, Firefox, and WebKit, including the Axe,
  keyboard, reflow, RTL, focus-obscuration, target-size, and equivalent-view assertions. Pa11y
  passed 2/2 route checks. Lighthouse passed both route budgets, including LCP at or below 2.5s.
  These automated results do not replace the pending manual assistive-technology and zoom review.

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
proven directly by the dedicated 2.5.8 test. With the statewide overview exposing non-overlapping
cluster controls and singleton markers, the allowlist is a defensive safety net rather than a mask
over crowding.

## Statewide geography and dense marker targets — resolved

The former collision-relaxation layout moved dense Sacramento readings away from their coordinates,
making a local network appear to cover unrelated parts of California. The current map uses one fixed
geographic projection for the California basemap and every reading. Pan, zoom, text scaling, and
cluster activation change only the camera; they do not rewrite projected positions.

At the fitted statewide view, nearby readings are represented by native overview cluster buttons
anchored to a real member position. Each button's accessible name states its reading count and value
range. It begins with `aria-expanded="false"`; Enter or Space activates the native button, fits the
camera around that geographic group, sets `aria-expanded="true"`, hides the overview control, and
reveals the member reading buttons at their original projected coordinates. Reset returns to the
statewide fit and restores the collapsed cluster state. List and Table always expose the complete
active dataset, including readings hidden behind an overview cluster.

- **Evidence.** The browser regression checks the statewide outline and reading span, rejects a
  single synthetic 150-reading cluster, activates a cluster with Enter, verifies its
  `aria-expanded` transition and focus return to the named map group, and proves every marker keeps
  the same projected fractions before and after the camera change. The Axe and dedicated WCAG 2.5.8
  gates pass for visible overview controls and revealed markers at desktop and 320 CSS pixels. The
  Map/List/Table equivalence test still matches every published record on both routes. The full
  browser suite passed across Chromium, Firefox, and WebKit on 2026-07-31.

## Render-shift and load — /sensors/ CLS resolved

The `/sensors/` route also showed a Lighthouse cumulative-layout-shift of 0.133 (over the 0.1 budget).
The cause was the resident-facing **Now** card filling from its short HTML placeholders a frame later
and shoving the blocks below it. The card's answer, temporal line, guidance, and status now reserve
their rendered heights, and the Now card is painted in the first synchronous render pass rather than in
the deferred workspace pass; the boot fetches (catalogue, demo contract, basemap, first snapshot) also
run in parallel to shorten the path to that paint. Measured CLS drops to <0.06 on `/sensors/` and
stays <0.02 on `/`, both inside the 0.1 budget. The 2026-07-31 local and CI Lighthouse runs passed
both route budgets, with largest-contentful paint at or below 2.5s under the configured throttle. PR
[#130](https://github.com/ChelseaKR/swelter/pull/130) resolved the above-the-fold work tracked in
[#117](https://github.com/ChelseaKR/swelter/issues/117); the advisory is no longer red. Axe, Pa11y,
WCAG 2.5.8 target-size, and contrast checks also pass on both routes.

## WebKit text-scale map-centering flake — resolved

The browser gate's "larger text preserves the map center" check (a WCAG 1.4.4 assertion that the
in-page text-size control never displaces the geographic point a reader had centered) failed
reproducibly on WebKit in CI, with the map's vertical center reading 4.6% off the expected fraction
([#169](https://github.com/ChelseaKR/swelter/issues/169)). It never reproduced locally, including 8
repeated runs against real WebKit at 5-way parallelism.

The cause is a harness race, not a layout defect, and the dashboard's text-scale re-centering is
correct: there is no WebKit text-scale defect. The mechanism, however, was misidentified twice
before it was pinned down. Both earlier readings are kept below, marked as superseded, so the record
shows what was believed and when.

**Corrected diagnosis (2026-08-29).** The check failed again on WebKit, with the identical
signature, on two unrelated pull requests ([#211](https://github.com/ChelseaKR/swelter/pull/211) and
[#212](https://github.com/ChelseaKR/swelter/pull/212), runs 33266336949 and 33266337675), one of
which changes no `web/` file at all.

The failure is a stale baseline, not a late correction. The test zooms with `+`, pans with
`ArrowRight` then `ArrowDown`, and captures the pre-reflow camera as its reference. A pan key
mutates `state.mapView` and defers the DOM write to the next animation frame (`scheduleTransform`),
so when a frame boundary falls between the two presses the camera briefly shows `ArrowRight` only.
The wait before the capture was "the camera is no longer the post-zoom value", which `ArrowRight`
satisfies by itself, so the reference was recorded with `ArrowDown` still pending. Everything after
that compared a correct measurement against a wrong reference.

The trace attached to run 33266336949 settles it arithmetically. The map box went from 540x626 to
585x678 CSS pixels, and the camera from `translate(-148px, -165.2px) scale(1.4)` to
`translate(-160.33333333333331px, -178.9226837060703px) scale(1.4)`. Those are exactly
`-148 * 585/540` and `-165.2 * 678/626`: the geographic center was preserved to sixteen digits, in
both axes. The horizontal assertion passed for the same reason it always did, because `ArrowRight`
was in the reference; the vertical one failed because `ArrowDown` was not. The reported drift of
0.0456412596987678 is `40 / (626 * 1.4)`, the single deferred 40-pixel pan step.

Reproduced deterministically on local WebKit by holding the `ArrowDown` keydown until after the
baseline read, which yields the CI failure to every digit (`Expected: 0.5`, `Received:
0.5456412596987678`); the same injection passes once each pan is settled in turn. The fix waits on
each pan against the camera observed immediately before it, which is stricter than the wait it
replaces: it requires both pans to have landed where the old one required only the first. The
`toBeCloseTo(..., 7)` tolerance, the polls, and the `test.slow()` and 20s ceilings added in August
are all unchanged, so a genuine non-convergence still fails.

This also explains why it never reproduced locally on an idle machine and why it survived retries.
Both key presses land inside one animation frame when the runner is not contended and in separate
frames when it is, which holds for a whole run rather than varying per attempt. It is
load-correlated, not a per-attempt flake, and it was never evidence about the pull request it
blocked.

### Superseded readings

**Superseded (original).** The map's own resize handling
(`ResizeObserver` → one `requestAnimationFrame` → `restoreMapCameraCenter` in `web/app.js`) already
recenters the camera correctly after a text-scale reflow changes the map's rem-driven pixel box; the
test set the `--text-scale` CSS variable and immediately read the camera on the same tick, before
that asynchronous correction had necessarily run. Confirmed by reproducing the same failure signature
on Chromium with `requestAnimationFrame` artificially delayed, then confirming a poll-based read
survives the same delay. The fix polls for the corrected camera state instead of reading once; a
genuine future regression (the correction never landing) still fails the check, just after the poll
timeout rather than immediately. No `web/app.js` change was needed.

**Superseded (follow-up, 2026-08-21).** The initial poll used the suite's 10s default `expect` timeout, which
was observed to time out under heavy same-day CI concurrency (many parallel workflow runs sharing
runner capacity) — not because the correction was slow in absolute terms, but because the runner's
event loop was contended. `test.slow()` (triples the test's own timeout) plus an explicit 20s ceiling
on each poll give real headroom; a genuine non-convergence still fails the check, just after a
longer wait.

## Regenerating this report

Run `make a11y` and `make verify-web` (which installs all three locked browser engines), then
complete the matrix in `MANUAL-AT-WALKTHROUGH.md` for a formal release signoff. Update the evidence
dates and findings in this report and the ACR. A report whose verification date predates a `web/`
change is itself a finding.

---
Test-coverage documentation refreshed by OpenAI Codex, 2026-07-31; baseline human review by Chelsea
Kelly-Reif, 2026-06-16. swelter is an independent personal open-source project; see NOTICE.
