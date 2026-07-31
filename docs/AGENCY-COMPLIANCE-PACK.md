# Agency accessibility and language-access evidence pack

This brief helps a public-entity partner evaluate swelter's current engineering evidence. It is not
legal advice, a procurement approval, or a certification of an agency deployment. The adopting entity
remains responsible for its content, configuration, source data, applicable deadline, and conformance
decision.

Owner: Chelsea Kelly-Reif. Last verified: 2026-07-16. Recheck cadence: every release, every relevant
dashboard/language change, and any revision to the legal context in the vendored accessibility
standard.

## Posture

swelter targets WCAG 2.2 Level AA, which includes the WCAG 2.1 A/AA criteria referenced by the US DOJ
Title II web rule. The legal context and public-entity deadline categories are maintained in
[`standards/ACCESSIBILITY-STANDARD.md`](standards/ACCESSIBILITY-STANDARD.md); an agency should have
its ADA coordinator or counsel confirm which deadline and exceptions apply.

The dashboard is designed so the map is never the only route to an outcome. The same filtered surface
is available through semantic table and plain-list representations, and the Current reading/Readings
workspace retains keyboard operation, visible focus, reduced motion, text/pattern state, and data/text
equivalents for visualizations.

## Evidence layers

| Layer | Evidence | What it supports | What it does not prove |
|---|---|---|---|
| Structural automation | `make a11y` / `scripts/a11y_check.py` | Required landmarks, labels, table/list paths, language controls, focus and reduced-motion structure | Computed behavior, task success, comprehension, or assistive-technology usability |
| Browser automation | CI browser accessibility and interaction jobs | Runtime DOM, axe/pa11y rules, critical keyboard/state/schema behavior in supported browser automation | Every WCAG criterion or a human screen-reader experience |
| Language automation | UTF-8, BCP-47, EN/ES parity, CLDR pin | Catalog presence, encoding, tags, and locale-data discipline | Spanish accuracy, tone, health-context clarity, or cultural fit |
| Human review | Named keyboard, reflow/magnification, NVDA, VoiceOver, and independent Spanish review | The reviewed tasks, environments, findings, and date | Future regressions or environments outside the recorded scope |
| Conformance record | [`accessibility/ACR.md`](accessibility/ACR.md) | Criterion-by-criterion self-assessment and evaluation methods | Third-party certification or an agency-specific legal determination |

The current human review for the expanded observatory and independent Spanish signoff is open in
[#106](https://github.com/ChelseaKR/swelter/issues/106). The earlier baseline remains useful history,
but this pack does not relabel it as a current pass and does not infer human review from automation.

## Evidence an adopting agency receives

- the [Accessibility Conformance Report](accessibility/ACR.md), including evaluation scope and known
  limits;
- the [accessibility evidence index](accessibility/README.md) and automated gate sources;
- the [internationalization contract](I18N.md) and English/Spanish catalogs;
- the [acceptance-test map](ACCEPTANCE-TEST-MAP.md), including human-review criteria;
- the [responsible-technology audit](RESPONSIBLE-TECH-AUDITS.md), DPIA, fairness review, and residual-
  risk register;
- the [definition of done](../DEFINITION_OF_DONE.md) and PR/release attestations used to keep evidence
  current.

## Adoption checklist

Before public use, a named agency owner should:

1. identify the entity's applicable legal requirements and deadline with qualified counsel;
2. replace/verify jurisdiction-specific source, cooling-center, guidance, and translation content;
3. run the complete automated gate on the exact deployment candidate;
4. complete dated keyboard, reflow/magnification, NVDA, VoiceOver, and independent Spanish review on
   the configured deployment's critical tasks;
5. update the ACR remarks to match the deployed version and document exceptions/remediation owners;
6. provide an accessible feedback/support route and monitor reported barriers;
7. repeat the review after material interaction/content changes and at each release.

## Honest limits

- swelter is a self-assessed open-source reference implementation; no independent certification is
  claimed.
- Machine parity does not establish language justice or equal comprehension. A partner should involve
  affected Spanish-speaking residents, not only a professional copy review.
- The visualization/data alternatives reduce map dependence but do not guarantee that every resident
  can interpret air/heat uncertainty or act on it; real partner usability research remains open.
- Data-source correctness, freshness, licensing, and local public-health copy are separate from web
  accessibility and require their own review.
- An agency that changes branding, content, hosting, source data, CSS, or interaction behavior must
  reassess the resulting product rather than inheriting this repository's evidence unchanged.
