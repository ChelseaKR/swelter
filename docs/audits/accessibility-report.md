# Accessibility report

Last verified: 2026-06-16. Recheck cadence: each release, and on any change under `web/`.

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
| 7 | A data-table equivalent to the map exists | 1.1.1 Non-text Content | PASS |
| 8 | Every `<img>` has an `alt` attribute | 1.1.1 Non-text Content | PASS |
| 9 | No positive `tabindex` | 2.4.3 Focus Order | PASS |
| 10 | A language switch is present | 3.1.2 Language of Parts (en/es) | PASS |
| 11 | CSS honours `prefers-reduced-motion` | 2.3.3 Animation from Interactions | PASS |
| 12 | CSS provides a visible focus indicator | 2.4.7 Focus Visible | PASS |

Check 7 is the load-bearing one: it proves the map is never the only way in. The same aggregated
surface renders as a sortable table and a plain list, so a screen-reader user gets the full
dataset without the map. The gate fails the build if the table is removed.

## What the structural gate cannot prove

The script is honest about its limits. With no browser and no DOM it cannot judge:

- computed colour-contrast ratios (1.4.3, 1.4.11) — mitigated in design by conveying AQI and heat
  severity with text and pattern, never colour alone;
- live ARIA semantics and announcement order, e.g. the time slider's `aria-live` value
  announcements;
- reading and focus order as actually experienced with a screen reader;
- reflow and target-size behaviour at real viewport sizes (1.4.10, 2.5.8).

These are covered by the manual review below. The structural gate auto-blocks merge; the manual
review is review-gated and recorded here.

## Manual review status

- **Reviewer:** Chelsea Kelly-Reif.
- **Date of last manual pass:** 2026-06-16.
- **Tools:** NVDA (Firefox), VoiceOver (Safari), keyboard-only traversal.
- **Scope:** the three equal views (map, table, list); the time slider; the en/es language
  switch; focus order through the page; AQI severity legibility without colour.
- **Result:** no AA blocker found. The time slider is keyboard-operable and announces its value
  via `aria-live`; focus is not trapped; the table and list reproduce the map's data with the same
  filtering. AQI severity is readable by text and pattern with colour disabled.
- **Open items:** none blocking AA. A full Section 508 VPAT/ACR is tracked separately at
  `docs/accessibility/ACR.md` per the README; this report covers the WCAG 2.2 AA floor and the
  manual confirmation of it.

## Regenerating this report

Run `make a11y`, confirm 12/12, redo the keyboard and screen-reader pass for any changed view,
and update the two dates and the manual-review result above. A report whose date predates a change
under `web/` is itself a finding.

---
Reviewed by: Chelsea Kelly-Reif, 2026-06-16. swelter is an independent personal open-source
project; see NOTICE.
