# Accessibility

Last verified: 2026-06-16. Recheck cadence: each release, and at least every 6 months otherwise.

swelter targets **WCAG 2.2 Level AA** for the `web/` dashboard and documents conformance with the
**Revised Section 508 Standards** (36 CFR Part 1194). A community-run dashboard is not federal
ICT, so 508 is not legally required here; building to it is deliberate, because the residents most
exposed to heat and bad air include disabled and elderly people, and an environmental-justice tool
that is not itself accessible fails the people it is for.

## What is in this folder

- **[`ACR.md`](ACR.md)** — the Accessibility Conformance Report, in the **VPAT 2.5 (Rev 508)**
  template. It carries product information, the evaluation methods, the WCAG 2.x Level A and AA
  success-criteria tables, the Revised 508 Chapter 5 (Software) and Chapter 6 (Support
  Documentation) tables, and the Chapter 3 Functional Performance Criteria. Conformance terms are
  Supports / Partially Supports / Does Not Support / Not Applicable, with specific remarks.

## How conformance is checked

Three layers, from cheapest to most thorough:

1. **Structural gate — merge-blocking.** `scripts/a11y_check.py`, run by `make a11y` (and inside
   `make verify`). It is pure Python, needs no browser, and is deterministic. Twelve checks hold
   the structural floor the dashboard promises: `<html lang>`, a non-empty `<title>`, exactly one
   `<h1>`, the `main`/`header` landmarks, a skip link that targets a real in-page id, every form
   control labelled, a real data-table equivalent to the map, every `<img>` carrying `alt`, no
   positive `tabindex`, a language switch, a `prefers-reduced-motion` CSS rule, and a visible
   focus indicator. A regression on any of the twelve fails the build. They all currently pass.
   The gate cannot judge computed color contrast or live ARIA semantics — that is what the next
   two layers are for.
2. **Automated audit — advisory.** `axe-core` and `pa11y` run against the served page and catch
   what the structural gate cannot, including contrast. Advisory, not merge-blocking, because they
   neither prove nor disprove the criteria that require human judgement.
3. **Manual screen-reader review.** NVDA (Firefox and Chrome on Windows) and VoiceOver (Safari on
   macOS), plus keyboard-only operation, 200% zoom and reflow, and the reduced-motion preference.
   Run before each release and whenever the dashboard's markup or interaction model changes
   (a new view, a new control, a change to the table, tablist, or slider). Findings are folded
   back into the ACR.

## Maintenance

The ACR is **regenerated and re-committed on each release**, the same audit-as-artifact discipline
as the calibration record: the report is a checked-in file that travels with the code it
describes, not a claim made once and left to rot. When a release changes the dashboard's
accessibility surface, update the ACR remarks and the "Last verified" date in the same change.
