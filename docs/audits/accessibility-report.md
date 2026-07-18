# Accessibility report

Last verified: 2026-07-17. Final MF2 browser execution: pending in CI.
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

- `scripts/a11y_check.py`: 12/12 structural checks passed on 2026-07-17.
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

## Regenerating this report

Run `make a11y` and `make verify-web` (which installs all three locked browser engines), then complete the matrix in
`MANUAL-AT-WALKTHROUGH.md` for a formal release signoff. Update the evidence dates and findings in
this report and the ACR. A report whose verification date predates a `web/` change is itself a
finding.

---
Test-coverage documentation refreshed by OpenAI Codex, 2026-07-17; baseline human review by Chelsea
Kelly-Reif, 2026-06-16. swelter is an independent personal open-source project; see NOTICE.
