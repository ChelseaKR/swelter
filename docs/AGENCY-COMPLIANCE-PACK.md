# Agency compliance pack: accessibility + language access

A one-page brief for a public-entity partner (a city, county, special district, or their
procurement office) evaluating swelter: if your agency adopts, funds, or co-hosts a swelter
instance, here is your accessibility and language-access compliance posture and the evidence that
backs it. It assembles claims that are already made and sourced elsewhere in this repo — it adds
no new capability and reports no new conformance result. Where a gate is advisory rather than
proven, it says so.

This pack complements [`POSITIONING.md`](POSITIONING.md) (the strategy note) and
[`docs/accessibility/ACR.md`](accessibility/ACR.md) (the underlying conformance evidence); the
README is the source of truth and its hard rules bind everything here.

Author: Chelsea Kelly-Reif, 2026. swelter is an independent personal open-source project,
unaffiliated with any employer or client; see [`../NOTICE`](../NOTICE).

Last verified: 2026-07-03. Recheck cadence: on any WCAG 2.x revision, ADA Title II deadline
change, or a change to the dashboard's accessibility or i18n surface — and at minimum annually,
mirroring [`docs/standards/ACCESSIBILITY-STANDARD.md`](standards/ACCESSIBILITY-STANDARD.md).

---

## 1. What this is

Public entities that operate or fund web content — including a community dashboard they adopt,
co-brand, or link from official channels — are the content the 2024 ADA Title II rule covers.
swelter is built to clear that bar today, not to retrofit it later: WCAG 2.2 AA is a merge gate on
every change, and English/Spanish parity is mechanically enforced, not a translation pass bolted
on at the end. This pack packages that existing engineering discipline as something a
procurement office or ADA coordinator can cite directly.

## 2. The rule

The DOJ's 2024 ADA Title II final rule makes **WCAG 2.1 Level AA** load-bearing for state and
local government web content, with deadlines set from the rule's publication:

- **April 26, 2027** — public entities with a total population of **50,000 or more**.
- **April 26, 2028** — public entities with a population **under 50,000**, and special-district
  governments.

(Source: [`docs/standards/ACCESSIBILITY-STANDARD.md` §4](standards/ACCESSIBILITY-STANDARD.md),
"Legal context.") This is not a swelter-specific reading of the rule — it is the repo's standing
legal-context note, reused here rather than restated as a new claim.

## 3. How swelter clears it

- **Target exceeds the floor.** swelter is built and self-assessed to **WCAG 2.2 Level AA**. WCAG
  2.2 is backward-compatible with 2.1: meeting 2.2 AA meets the 2.1 AA criteria the Title II rule
  requires. Targeting the newer, stricter standard means a 2.1 AA deadline is met automatically,
  with headroom rather than a same-year scramble.
- **Auditable evidence, not a claim.** [`docs/accessibility/ACR.md`](accessibility/ACR.md) is the
  Accessibility Conformance Report, in the **VPAT 2.5 (Rev 508)** template — product information,
  evaluation methods, and the full WCAG 2.x Level A/AA success-criteria tables with per-criterion
  remarks. It is the artifact a procurement office actually asks for, and it is checked into the
  repo rather than issued once and left to go stale.
- **Three-layer verification**, cheapest to most thorough:
  1. **Structural gate — merge-blocking.** `scripts/a11y_check.py`, run by `make a11y` (and inside
     `make verify`). Twelve deterministic, browser-free checks hold the structural floor: page
     language, a non-empty title, exactly one `<h1>`, landmarks, a working skip link, labelled
     controls, a real data-table equivalent to the map, image text alternatives, no positive
     `tabindex`, a language switch, a `prefers-reduced-motion` rule, and a visible focus
     indicator. A regression on any of the twelve fails the build.
  2. **Automated audit — advisory.** `axe-core` and `pa11y` run against the served page and catch
     what the structural gate cannot, including computed color contrast. Advisory, not
     merge-blocking, because they neither prove nor disprove the criteria that require human
     judgement.
  3. **Manual screen-reader review.** NVDA (Firefox and Chrome on Windows) and VoiceOver (Safari
     on macOS), plus keyboard-only operation, 200% zoom and reflow, and the reduced-motion
     preference — run before each release and whenever the dashboard's markup or interaction
     model changes. Findings are folded back into the ACR.

## 4. Language justice

Title II accessibility and language access are related but separate civil-rights obligations, and
swelter treats both as mission-critical rather than as polish:

- **en + es parity for all resident-facing copy**, mechanically enforced: the EN/ES key-parity
  gate (`scripts/i18n_parity.py` + `tests/test_i18n.py`) fails the build if a key exists in one
  language bundle and not the other, or if an ES value is empty. See
  [`docs/I18N.md`](I18N.md) for the full catalog format and the live gate table.
  `docs/USER-RESEARCH.md`'s language-access notes frame the risk this closes: new resident-facing
  guidance or trust copy otherwise "risks landing English-first, duplicating a language gap" for
  Limited-English-Proficient residents, which is a civil-rights obligation, not a nice-to-have
  (`docs/USER-RESEARCH.md` ~line 588, footnote `[^lep]`; see also ~line 475, `[^ada]`).
- **Correctness, not just presence.** Both locales clear the same a11y screen-reader pass, and the
  `lang`/`xml:lang` attribute is verified correct per rendered locale (automated, via axe's
  `html-has-lang` and `valid-lang` checks).

## 5. What an agency partner receives / next steps

An agency adopting swelter gets, without further engineering work on this front:

- The **ACR** ([`docs/accessibility/ACR.md`](accessibility/ACR.md)) as the auditable VPAT to hand
  to an ADA coordinator or procurement reviewer.
- The **standard** ([`docs/standards/ACCESSIBILITY-STANDARD.md`](standards/ACCESSIBILITY-STANDARD.md))
  documenting why WCAG 2.2 AA was chosen over the legal floor, and the recheck cadence that keeps
  both current.
- A **bilingual dashboard by construction**, not by one-time translation, per
  [`docs/I18N.md`](I18N.md).

To use this pack in a real procurement conversation: a named public-entity partner should record
its applicable Title II deadline (2027 or 2028, per §2 above) in [`ROADMAP.md`](ROADMAP.md), the
same convention the accessibility standard already specifies for any repo with a named
public-entity client (`docs/standards/ACCESSIBILITY-STANDARD.md` line 232).

## Honest limits

- This pack packages existing, already-cited engineering discipline — it does not constitute
  legal advice, and it is not itself a Title II compliance certification. An agency's counsel
  makes that determination.
- The manual screen-reader review layer is point-in-time; its currency depends on the recheck
  cadence in [`docs/accessibility/README.md`](accessibility/README.md) being honored on future
  changes.
- The ES-language plain-language gate is human-reviewed, not automated (no reliable automated
  Spanish grade-level metric exists today) — see
  [`docs/standards/ACCESSIBILITY-STANDARD.md` §3](standards/ACCESSIBILITY-STANDARD.md).
