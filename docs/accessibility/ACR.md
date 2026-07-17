# Accessibility Conformance Report — swelter dashboard

VPAT 2.5 (Rev 508) — Revised Section 508 Edition

Last full manual screen-reader verification: 2026-06-16. Observatory implementation regression
review: 2026-07-16 (structural gate, bilingual parity, automated browser interactions at desktop and
mobile widths, and CI axe/pa11y gate). The expanded linked visualizations retain text equivalents;
NVDA and VoiceOver should be re-run for the next formal conformance-signoff. Recheck cadence:
regenerated and re-committed each release, and at least every 6 months when no release ships.

> swelter is an independent, community-run heat and air-quality dashboard. It is **not federal
> ICT**, so the Revised Section 508 Standards (36 CFR Part 1194) do not apply to it as a matter
> of law. This report documents conformance with that standard anyway, because the people most
> exposed to heat and bad air include disabled residents and elders, and an environmental-justice
> tool that is not itself accessible fails the people it is for. The standard governments audit to
> is also the one that makes the data usable to the widest public.

## Product information

| | |
| --- | --- |
| Name of product | swelter dashboard (the `web/` single-page application) |
| Version | Tracks the repository release; this report covers the dashboard as committed on the date below |
| Report date | 2026-07-16 |
| Product description | A framework-free, dependency-free exposure observatory for neighborhood heat and air quality. A resident-first Now view leads into linked history, distribution, map, sortable table, plain list, and evidence-inspector views of one aggregated surface. Served by `swelter serve`; installable as a PWA; deployable to static hosting. |
| Contact information | Chelsea Kelly-Reif — github.com/ChelseaKR/swelter |
| Notes | The shell is four static files (`web/index.html`, `web/styles.css`, `web/observatory.css`, `web/app.js`) plus per-language string bundles (`web/i18n/en.json`, `web/i18n/es.json`). No build step, bundler, runtime framework, map tiles, or external font request. |
| Evaluation methods used | See below. |

### Evaluation methods used

- **Automated, advisory:** `axe-core` and `pa11y` run against the served page. Advisory because
  they cannot prove or disprove the criteria that require human judgement.
- **Automated, merge-blocking:** the structural WCAG 2.2 AA gate `scripts/a11y_check.py`
  (`make a11y`, part of `make verify`). Twelve deterministic, browser-free checks; the build
  fails if any regresses. It holds the structural floor — a language, a non-empty `<title>`, a
  single `<h1>`, landmarks, a working skip link, labelled controls, a real data-table equivalent
  to the map, image text alternatives, no positive `tabindex`, a language switch, a
  `prefers-reduced-motion` rule, and a visible focus indicator. As of this report all twelve pass.
- **Manual screen-reader review:** the 2026-06-16 baseline covered NVDA on Windows (Firefox and
  Chrome) and VoiceOver on macOS (Safari), exercising every original data representation and
  control. The 2026-07-16 observatory keeps those tested controls/IDs and adds text summaries for
  its decorative SVG, but its expanded linked-view sequence awaits the next full NVDA/VoiceOver
  signoff; this limitation is stated rather than silently rolling the old date forward.
- **Keyboard-only review:** full task completion using only Tab / Shift+Tab, Enter / Space, and
  arrow keys, confirming a visible focus indicator on every interactive element and no keyboard
  trap.
- **200% zoom and reflow:** browser zoom to 200% and a narrow viewport, confirming no loss of
  content or function and no horizontal scrolling of the page.
- **Reduced motion:** verified with the operating-system "reduce motion" preference set; the
  dashboard has no essential animation and honours `prefers-reduced-motion`.

### Applicable standards / guidelines

| Standard / guideline | Included in report |
| --- | --- |
| Web Content Accessibility Guidelines 2.x | Level A (Yes), Level AA (Yes), Level AAA (No) |
| Revised Section 508 Standards — 36 CFR Part 1194, Appendices A, B, and C | Yes |
| EN 301 549 | Not separately evaluated |

The dashboard is built and self-assessed to **WCAG 2.2 Level AA**. WCAG 2.2 is backward
compatible: meeting 2.2 A/AA meets the 2.0 A/AA criteria that the Revised 508 Standards
incorporate by reference. The success-criteria table below uses the WCAG numbering shared across
2.0/2.1/2.2.

### Terms

- **Supports:** the functionality meets the criterion without known defects.
- **Partially Supports:** some functionality meets the criterion.
- **Does Not Support:** the majority of the functionality does not meet the criterion.
- **Not Applicable:** the criterion is not relevant to the product.

---

## WCAG 2.x Report — Level A and Level AA

### Table 1: Success Criteria, Level A

| Criterion | Conformance level | Remarks and explanations |
| --- | --- | --- |
| 1.1.1 Non-text Content | Supports | No content `<img>` elements ship; the map uses text-labelled buttons. The exposure-braid SVG is `aria-hidden` and described by keyboard instructions, a plain-text statistical summary, and a method/uncertainty note; the same readings remain in List and Table. Legend swatches are decorative with adjacent category text. The gate asserts every `<img>` has `alt`. |
| 1.2.1 Audio-only and Video-only (Prerecorded) | Not Applicable | No audio or video content. |
| 1.2.2 Captions (Prerecorded) | Not Applicable | No multimedia. |
| 1.2.3 Audio Description or Media Alternative (Prerecorded) | Not Applicable | No multimedia. |
| 1.3.1 Info and Relationships | Supports | Semantic HTML throughout: `<header>`/`<main>`/`<footer>` landmarks, one `<h1>` and section `<h2>`s, a real `<table>` with `<caption>`, `<th scope="col">` and per-row `<th scope="row">`, `<label for>` on every control, and `aria-sort` on sortable columns. The tablist uses `role="tablist"`/`tab`/`tabpanel` with `aria-controls`/`aria-labelledby`. |
| 1.3.2 Meaningful Sequence | Supports | DOM order matches reading order: Now, Explore heading and controls, linked visual summaries, representation tabs and panels, inspector, Network, then Data & Method. Responsive CSS changes columns, not semantic order. |
| 1.3.3 Sensory Characteristics | Supports | Instructions never rely on shape, size, or position alone; views are named "Map", "Table", "List" and severity is named in text. |
| 1.4.1 Use of Color | Supports | Air-quality category is conveyed by **text and a distinct background pattern**, not color alone (see `.aqi-*` rules in `styles.css`, which pair each color with a unique hatch/dot pattern and an always-present text label). Provisional cells use a dashed border plus the word "provisional". |
| 1.4.2 Audio Control | Not Applicable | No auto-playing audio. |
| 2.1.1 Keyboard | Supports | Controls are native `<select>`, `<input type="range">`, links, and buttons. The exposure braid itself accepts Left/Right/Home/End, its range has two labelled native sliders, tabs use roving focus, map pan/zoom has button and arrow-key alternatives, and sort is a button in the table header. |
| 2.1.2 No Keyboard Trap | Supports | Focus moves into and out of every component with Tab/Shift+Tab. No modal or custom focus capture exists. |
| 2.1.4 Character Key Shortcuts | Supports | Optional `l`, `t`, `m`, and `/` shortcuts never fire while typing or with a modifier, and can be disabled through the persistent “Enable keyboard shortcuts” checkbox. |
| 2.2.1 Timing Adjustable | Not Applicable | No task or content has a time limit. |
| 2.2.2 Pause, Stop, Hide | Supports | The hourly playback never starts automatically. Its initiating button becomes Pause; manual time/range input stops it, and reduced-motion preferences remove transitional motion. |
| 2.3.1 Three Flashes or Below Threshold | Supports | Nothing flashes. |
| 2.4.1 Bypass Blocks | Supports | A "Skip to the data" link targets `#main`; the a11y gate asserts the skip link points at a real in-page id. |
| 2.4.2 Page Titled | Supports | `<title>` identifies the neighborhood heat-and-air evidence observatory and is localized with the page; the gate asserts a non-empty title. |
| 2.4.3 Focus Order | Supports | Focus order follows the visual and DOM order; the active tab is the single tab stop (roving `tabindex`), panel content follows it, and rerendered map/list/table, ranking, overview, and alert controls restore focus to the equivalent control or the selected List row. |
| 2.4.4 Link Purpose (In Context) | Supports | Skip, section navigation, source switching, “Open the evidence,” license, feed, and download links state their purpose in text and context. |
| 2.5.1 Pointer Gestures | Supports | The map accepts pan/pinch, but none is required: zoom/reset buttons, arrow keys, selectable markers, List, and Table expose the same outcomes without a path-based or multipoint gesture. |
| 2.5.2 Pointer Cancellation | Supports | Actions fire on `click`/`change`/`input` (up event), not `mousedown`; a pointer can be moved off before release. |
| 2.5.3 Label in Name | Supports | Visible labels match accessible names; tab buttons' visible text is their name, controls are tied to visible `<label>`s. |
| 2.5.4 Motion Actuation | Not Applicable | No device-motion or user-motion actuation. |
| 3.1.1 Language of Page | Supports | `<html lang>` is set and updated when the language switch changes (en/es); the gate asserts `lang` is present. |
| 3.2.1 On Focus | Supports | Focusing a control causes no change of context. |
| 3.2.2 On Input | Supports | Changing the parameter, slider, or language re-renders the same views in place; no new window, no focus jump, no navigation. |
| 3.3.1 Error Identification | Not Applicable | No data-entry forms; the only inputs are a select and a slider with constrained values. The "no data" state is announced as text in the status region. |
| 3.3.2 Labels or Instructions | Supports | Every control has a persistent visible `<label>`; the slider has a hint via `aria-describedby` and the map panel carries a text hint pointing to the Table and List. |
| 4.1.1 Parsing | Supports | Valid HTML5; the gate parses the page with the standard-library HTML parser without structural error. (Obsolete in WCAG 2.2; reported as a courtesy.) |
| 4.1.2 Name, Role, Value | Supports | Native controls expose name/role/value to the platform; the tablist exposes `aria-selected`, selectable Map/List/Table and distribution buttons expose the linked location with `aria-pressed`, sortable headers expose `aria-sort` updated on sort, and the time readout uses `<output for>` with `aria-live="polite"`. |

### Table 2: Success Criteria, Level AA

| Criterion | Conformance level | Remarks and explanations |
| --- | --- | --- |
| 1.2.4 Captions (Live) | Not Applicable | No live multimedia. |
| 1.2.5 Audio Description (Prerecorded) | Not Applicable | No multimedia. |
| 1.3.4 Orientation | Supports | Layout is responsive and works in portrait and landscape; orientation is not locked. |
| 1.3.5 Identify Input Purpose | Not Applicable | No fields collect information about the user; the inputs select a measurement and an hour, which are not autocomplete-eligible purposes. |
| 1.4.3 Contrast (Minimum) | Supports | Body text, labels, and control text meet at least 4.5:1, and large text and UI borders meet 3:1, in both the light and dark `prefers-color-scheme` palettes defined in `:root`. Category swatch colors are paired with patterns and never carry meaning by contrast alone. Verified with the axe/pa11y contrast checks; spot-checked manually. |
| 1.4.4 Resize Text | Supports | All sizing uses `rem`/relative units; text scales to 200% with no clipping. |
| 1.4.5 Images of Text | Supports | No images of text; all text is real text. The PWA icon is the only image asset and is non-text branding. |
| 1.4.10 Reflow | Supports | The single-column responsive layout reflows to a 320 CSS-pixel width with no two-dimensional scrolling (`@media (max-width: 40rem)` and flex wrapping). |
| 1.4.11 Non-text Contrast | Supports | Control borders, the focus outline (`--focus`), the cell borders, and tab boundaries meet 3:1 against their adjacent surfaces in both palettes. |
| 1.4.12 Text Spacing | Supports | No fixed line-height or letter-spacing that would clip when users override text spacing; content uses normal flow with `line-height: 1.5`. |
| 1.4.13 Content on Hover or Focus | Not Applicable | No hover/focus-triggered tooltips or popovers; readings are stated inline, not on hover. |
| 2.4.5 Multiple Ways | Supports | The same aggregated surface is reachable three ways within the page — Map, Table, and List tabs — and the page is a single view; export endpoints (`/export.csv`, `/export.json`) offer an additional path to the data. |
| 2.4.6 Headings and Labels | Supports | Headings ("swelter", "Air-quality categories (PM2.5)") and control labels are descriptive; the visually-hidden "Controls" heading names the control group. |
| 2.4.7 Focus Visible | Supports | A 3px `:focus-visible` outline with offset is applied to every interactive element, including map cells and tabs; the gate asserts a visible focus indicator exists in CSS. |
| 2.4.11 Focus Not Obscured (Minimum) | Supports | Sticky command-bar and desktop-inspector layouts reserve scroll padding/margins; the inspector stops being sticky in the stacked layout. Automated keyboard review found no focused control fully obscured. (WCAG 2.2.) |
| 2.5.7 Dragging Movements | Supports | The time slider is fully operable with arrow keys; no action requires a dragging movement. (WCAG 2.2.) |
| 2.5.8 Target Size (Minimum) | Supports | Interactive targets — tabs, selects, slider thumbs, sort buttons, map cells, and distribution rows — meet the 24×24 CSS-pixel minimum or its spacing exception. The braid's full plot surface is one large pointer target that selects the nearest observation; compact dots also have expanded hit areas, and the time slider is an equivalent control. (WCAG 2.2.) |
| 3.1.2 Language of Parts | Supports | UI strings follow the selected document language (`en`/`es`). Source-authored English exposure-method notes can appear inside the Spanish interface; those raw notes are explicitly marked `lang="en"` in the braid and provenance views so assistive technology switches pronunciation correctly. |
| 3.2.3 Consistent Navigation | Supports | The single-page dashboard presents the same controls and tab order on every render. |
| 3.2.4 Consistent Identification | Supports | The same components ("provisional" tag, AQI tag, view tabs) are labelled identically wherever they appear. |
| 3.2.6 Consistent Help | Not Applicable | No help mechanism is provided across multiple pages; the dashboard is a single page. (WCAG 2.2.) |
| 3.3.3 Error Suggestion | Not Applicable | No data-entry forms produce errors. |
| 3.3.4 Error Prevention (Legal, Financial, Data) | Not Applicable | No legal, financial, or data-modifying transactions; the dashboard is read-only. |
| 3.3.7 Redundant Entry | Not Applicable | No multi-step process re-asks for information. (WCAG 2.2.) |
| 3.3.8 Accessible Authentication (Minimum) | Not Applicable | No authentication; the data is open and requires no account. (WCAG 2.2.) |
| 4.1.3 Status Messages | Supports | Cell count, source headline, alert/copy/watch feedback, and no-data/offline states use status/live text without moving focus. Range values and braid summaries are persistent control descriptions rather than live regions, preventing announcement storms during slider input. |

---

## Revised Section 508 Report

### Chapter 3: Functional Performance Criteria (FPC)

Applied where the WCAG criteria above do not fully address the user need.

| Criterion | Conformance level | Remarks and explanations |
| --- | --- | --- |
| 302.1 Without Vision | Supports | The map is never the only way in. The identical dataset renders as a semantic `<table>` (the canonical screen-reader path: caption, column and row headers, sortable columns with `aria-sort`) and as a plain readings list with one sentence per cell. Each map cell also carries a text `aria-label`. Slider value and cell counts are announced via `aria-live`. Verified with NVDA and VoiceOver. |
| 302.2 With Limited Vision | Supports | Text scales to 200% and the layout reflows to ~320 px with no loss of content; contrast meets AA in light and dark palettes; a 3px visible focus outline tracks the keyboard; severity is text-and-pattern, not fine color discrimination. |
| 302.3 Without Perception of Color | Supports | Air-quality category is conveyed by text and a distinct background pattern per category, and provisional state by a dashed border plus the word "provisional"; color is never the only signal (WCAG 1.4.1). |
| 302.4 Without Hearing | Supports | The dashboard conveys no information through sound; nothing depends on hearing. |
| 302.5 With Limited Hearing | Supports | No audio output. |
| 302.6 Without Speech | Supports | No operation requires speech input. |
| 302.7 With Limited Manipulation | Supports | Every task is completable by keyboard alone with no dragging, no multipoint gesture, and no timed action; targets meet the 24×24 px minimum with spacing (WCAG 2.5.7, 2.5.8, 2.1.1). |
| 302.8 With Limited Reach and Strength | Supports | All controls are reachable in a single tab order from a keyboard or switch; no action requires simultaneous keys, sustained pressure, or precise pointer travel. |
| 302.9 With Limited Language, Cognitive, and Learning Abilities | Partially Supports | Plain, concrete labels; one screen with a consistent layout; severity named in words; an explicit note that the page reports what the readings are and "does not tell anyone they are safe"; English and Spanish parity. The underlying subject (AQI categories, calibrated-vs-provisional, µg/m³ units) is inherently technical, and while it is explained in text it still asks more of the reader than a single number would. |

### Chapter 4: Hardware

Not applicable. The dashboard is web content with no hardware component. (The sensor nodes are
documented separately and are out of scope for this software ACR.)

### Chapter 5: Software

The dashboard is web content; the applicable software provisions are those that govern web-based
software. Where a provision targets platform/native software it is marked Not Applicable with a
reason.

| Criterion | Conformance level | Remarks and explanations |
| --- | --- | --- |
| 502 Interoperability with Assistive Technology | Supports | The dashboard uses native HTML controls and standard ARIA, exposing name, role, state, and value through the browser's accessibility tree to NVDA and VoiceOver. No custom accessibility API bridge is used or needed. |
| 502.2.1 User Control of Accessibility Features | Not Applicable | The dashboard is not platform software and does not disrupt platform accessibility features. |
| 502.2.2 No Disruption of Accessibility Features | Supports | The page does not override or disable platform or browser accessibility features (zoom, contrast, reduced motion, screen-reader). It honours `prefers-color-scheme` and `prefers-reduced-motion`. |
| 502.3 Accessibility Services | Not Applicable | Web content; it relies on the browser's accessibility services rather than implementing a platform accessibility API. |
| 502.4 Platform Accessibility Features | Not Applicable | Not a platform; no platform features are claimed or implemented. |
| 503 Applications | Supports | See sub-criteria. |
| 503.2 User Preferences | Supports | The page inherits the platform/browser settings for color, contrast, font size, and motion; it does not impose its own font or color that overrides user settings, and it offers a language preference. |
| 503.3 Alternative User Interfaces | Not Applicable | No alternative UI replaces platform accessibility features. |
| 503.4 User Controls for Captions and Audio Description | Not Applicable | No multimedia player. |
| 504 Authoring Tools | Not Applicable | The dashboard is not an authoring tool; it presents read-only data and produces no user-authored content. |
| 602.3 / WCAG conformance of web content | Supports | As detailed in the WCAG 2.x tables above, the web content conforms to WCAG 2.2 Level AA (and thereby the WCAG 2.0 A/AA incorporated by 508). |

### Chapter 6: Support Documentation and Services

| Criterion | Conformance level | Remarks and explanations |
| --- | --- | --- |
| 602.2 Accessibility and Compatibility Features | Supports | The documentation (the repository README's "Accessibility and Section 508 conformance" section, `web/README.md`, and this ACR) describes the dashboard's accessibility and compatibility features: the three equal views, the non-visual table/list equivalent to the map, text-and-pattern severity, the keyboard-operable announced slider, and PWA/offline use. |
| 602.3 Electronic Support Documentation | Supports | All support documentation is electronic Markdown that itself conforms to WCAG 2.2 Level A and AA (headings, tables with header rows, real text, link purpose in context) and is readable by assistive technology. |
| 602.4 Alternate Formats for Non-Electronic Support Documentation | Not Applicable | There is no non-electronic (printed) support documentation. |
| 603.2 Information on Accessibility and Compatibility Features | Supports | Support is provided through the public repository: issues at github.com/ChelseaKR/swelter and the maintainer contact above. The accessibility features are documented in this ACR and the READMEs. |
| 603.3 Accommodation of Communication Needs | Partially Supports | As a single-maintainer volunteer project, support is asynchronous via the public issue tracker and email; there is no telephone or real-time support channel, but written requests are accepted and English/Spanish documentation is provided. |

---

## Legal disclaimer

This report is a good-faith self-assessment by the project maintainer, not a third-party audit or
a legal certification. swelter is a volunteer, open-source community tool and is not federal ICT;
Section 508 does not legally apply to it. The report reflects the dashboard as committed on the
date above and is regenerated and re-committed each release. Remarks are written to be specific
and honest, including where conformance is partial.
