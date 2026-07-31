# Accessibility

Implementation/test-coverage review: 2026-07-31. Automated MF2 and browser suites: passing in CI and
locally. Last full manual screen-reader baseline: 2026-06-16. Recheck cadence: each release, and at
least every 6 months otherwise.

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
- **[`STATEMENT.md`](STATEMENT.md)** — the short public accessibility statement, current limitation,
  alternatives, and contact path.
- **[`APG-BRAID.md`](APG-BRAID.md)** and **[`APG-MAP.md`](APG-MAP.md)** — keyboard contracts and
  documented deviations for the two custom visualizations, for which APG defines no chart/map role.
- **[`MANUAL-AT-WALKTHROUGH.md`](MANUAL-AT-WALKTHROUGH.md)** — the required NVDA/VoiceOver/iOS task
  matrix and evidence fields. Its current Pending status is deliberate and must not be read as a pass.
- **[`../AGENCY-COMPLIANCE-PACK.md`](../AGENCY-COMPLIANCE-PACK.md)** — the agency-partner
  packaging of this ACR: a one-page brief framing WCAG 2.2 AA + en/es parity as a DOJ ADA Title II
  compliance asset for a public-entity partner's procurement or ADA-coordinator review.

## How conformance is checked

Three layers, from cheapest to most thorough:

1. **Structural gate — merge-blocking.** `scripts/a11y_check.py`, run by `make a11y` (and inside
   `make verify`). It is pure Python, needs no browser, and is deterministic. Twelve checks hold
   the structural floor the dashboard promises: `<html lang>`, a non-empty `<title>`, exactly one
   `<h1>`, the `main`/`header` landmarks, a skip link that targets a real in-page id, every form
   control labelled, a semantic data-table shell, every `<img>` carrying `alt`, no
   positive `tabindex`, a language switch, a `prefers-reduced-motion` CSS rule, and a visible
   focus indicator. A regression on any of the twelve fails the build. They all currently pass.
   The gate cannot judge computed color contrast or live ARIA semantics — that is what the next
   two layers are for.
2. **Browser and localization gates — merge-blocking in CI.** `npm --prefix web run verify` runs
   the MF2/unit contract, Playwright plus Axe, Pa11y, and Lighthouse. Assertions
   cover both published routes with distinct source/data fixtures; Chromium, Firefox, and WebKit;
   light and dark schemes; Axe scans of every Map/List/Table view in English and Spanish; primary
   keyboard tasks; `elementsFromPoint` focus non-obscuration; all-view 320 CSS-pixel reflow; reduced
   motion; pseudolocale expansion; an actual Arabic RTL fixture; and performance/DOM/asset budgets.
   Target geometry includes native controls and focusable/pointer composite surfaces in every view at
   desktop and 320 CSS pixels, with only the WCAG 2.5.8 inline-text and 24px-spacing exceptions. The
   unit contract blocks EN/ES key or placeholder drift,
   invalid MF2/count selection, unmarked public HTML copy, natural-language JavaScript UI sinks,
   physical CSS direction, duplicate semantic tokens, and static-asset budget regressions. On
   2026-07-31, the equal 400-key EN/ES catalogs and JavaScript unit suite passed 117/117 checks;
   Playwright passed 57/57 checks across Chromium, Firefox, and WebKit; Pa11y passed both routes;
   and Lighthouse passed both route budgets with LCP at or below 2.5s.
3. **Manual assistive-technology, zoom, and reflow review.** Automation does not prove usability.
   The 2026-06-16 NVDA/VoiceOver and 200% zoom baseline predates the expanded linked visualization
   and statewide cluster sequence. A new dated walkthrough on NVDA/Windows, VoiceOver/macOS,
   VoiceOver/iOS, 200% zoom, and reflow remains required before formal signoff; this is stated in the
   ACR and public statement rather than inferred from automation.

## Maintenance

The ACR is **regenerated and re-committed on each release**, the same audit-as-artifact discipline
as the calibration record: the report is a checked-in file that travels with the code it
describes, not a claim made once and left to rot. When a release changes the dashboard's
accessibility surface, update the ACR remarks and its evidence dates in the same change.
