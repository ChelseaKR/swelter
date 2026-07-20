# Accessibility statement

Last reviewed: 2026-07-17

swelter aims to meet WCAG 2.2 Level AA on the dashboard's primary and community-sensor routes.
This is a good-faith self-assessment, not a certification or a third-party audit.

## What the dashboard provides

- Native controls, visible keyboard focus, a skip link, landmarks, and status announcements.
- Map, List, and sortable Table routes through the same readings. The map is never the only way to
  reach the data.
- A keyboard-operable exposure history, two native range inputs, and a text summary of the plotted
  range, uncertainty, gaps, and provisional evidence.
- Severity stated in words and reinforced with patterns, not color alone.
- Light, dark, high-contrast, reduced-motion, narrow-screen, text-expansion, and English/Spanish
  support.
- Locale-aware numbers, dates, and plurals, with document language and direction updated together.

## How it is checked

The repository is configured to block structural, catalog, and browser-detectable regressions through
unit checks, Playwright plus Axe, Pa11y, and Lighthouse budgets. Browser assertions cover both
published routes with distinct source/data fixtures; Chromium, Firefox, and WebKit; light and dark
themes; Axe scans across every view in English and Spanish; keyboard task completion;
`elementsFromPoint` focus non-obscuration across Map, List, and Table; all-view 320 CSS-pixel reflow;
reduced motion; pseudolocale expansion; and an actual Arabic RTL fixture. Target geometry includes
native controls and focusable/pointer composite surfaces in every view at desktop and 320 CSS pixels,
with only the WCAG 2.5.8 inline-text and 24 CSS-pixel-spacing exceptions. See
the [Accessibility Conformance Report](ACR.md) for criterion-level evidence.

The final MF2 unit and browser suites remain pending in a clean Node 22 environment. CI is the
authoritative execution environment; configured assertions are not presented here as a local pass.

## Current limitation

The last recorded manual screen-reader baseline was completed on 2026-06-16, before the expanded
exposure braid, linked distribution, and evidence-inspector sequence. The 2026-07-16 overhaul adds
automated accessibility and keyboard assertions, but its complete tasks have **not yet been re-run**
with NVDA on Windows, VoiceOver on macOS, or VoiceOver on iOS. The expanded interface also needs a
fresh manual 200% zoom and reflow walkthrough. Full conformance for that sequence is therefore not
claimed until the dated walkthrough is completed and the authoritative browser gates pass.

In the meantime, every plotted reading remains available through the plain List and semantic Table,
and every chart has a text summary. The component-specific keyboard contracts and deviations are in
[Exposure braid keyboard contract](APG-BRAID.md) and [Map keyboard contract](APG-MAP.md).

## Report a problem

Open an [accessibility issue](https://github.com/ChelseaKR/swelter/issues/new) with the page or route,
browser, assistive technology, and the task that was blocked. Please do not include private health or
location information. Written reports are the supported contact path; response is asynchronous.
