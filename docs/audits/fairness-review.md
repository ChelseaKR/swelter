# Fairness and representational-harm review

Status: implementation analysis current for the exposure observatory; named-human REVIEW-GATE
signoff pending. Accountable owner: Chelsea Kelly-Reif. Machine-assisted analysis: OpenAI Codex,
2026-07-31; this is not human review. Independent Spanish-language and assistive-technology review
is also pending in [issue #106](https://github.com/ChelseaKR/swelter/issues/106).

## Segments that matter

- geography/source route: California physical sensors, California CAMS model points,
  Sensor.Community/Stuttgart, synthetic fallback;
- confidence: calibrated/confirmed, upstream model provenance, raw/provisional, missing/stale;
- coverage: measured vs unmeasured public cells and dense vs sparse provider areas;
- language: English vs Spanish capability and clarity;
- interaction: map, table, list, keyboard, screen reader, magnification/reflow, reduced motion;
- context availability: canopy, AC access, historical HOLC coverage, cooling-center data present vs
  absent.

No sensitive attribute is inferred. Context layers describe public cells and source limitations;
they do not classify people.

## Current evidence

The committed one-bucket synthetic surface has 150 public locations: 100 have at least one confirmed
record and 50 are entirely provisional. Its 1,050 rows include 600 confirmed and 450 provisional
records; all 150 estimated-WBGT rows are provisional. Those figures describe the deterministic test
fixture's initial snapshot, not production population coverage or equity.

The EN and ES catalogs have equal key sets (**400 each** at review time), and the MF2 extraction,
parsing, placeholder, and JavaScript unit checks pass locally and in CI. This mechanical parity proves
catalog completeness, not translation quality, cultural clarity, or equal task success. No
independent Spanish reviewer has signed the observatory copy. Likewise, the passing automated
keyboard, Arabic RTL, focus-obscuration, target-geometry, and cross-browser assertions do not
substitute for the open NVDA/VoiceOver/iOS/zoom/reflow release review.

## Findings and mitigations

| Risk | Finding | Mitigation / required evidence |
| --- | --- | --- |
| Confirmed-first ranking | Honest confidence ordering can systematically push under-calibrated neighborhoods down | Show provisional places rather than omit them; label the ordering; publish coverage gaps; steward plan prioritizes calibration/placement where confidence is weakest |
| Uneven provider coverage | OpenAQ/Sensor.Community caps and geography can make a route look representative when it is not | Source-specific cards, visible coverage/freshness, no statewide/block-complete claim, no cross-route comparison presented as like-for-like |
| Model vs sensor parity | CAMS offers broad California coverage but is coarser than physical sensors | Label model provenance in every view/export; do not call CAMS locations sensors or independent blocks |
| Context erasure/stigma | HOLC only covered some cities; AC/canopy datasets can be missing or proxy-limited | Omit missing context, never infer a grade, retain source/date/license, explain historical—not current—meaning |
| EN/ES capability | Equal keys can still hide mistranslation, reading-level, clipping, or interaction differences | Automated parity/reflow plus independent Spanish task review; issue #106 remains the release gate until performed |
| Disability access | Map-first analytical density can disadvantage nonvisual/cognitive users despite table/list parity | Equal table/list data, plain summary, text/pattern encoding, reduced motion; named screen-reader/reflow review in issue #106 |
| Geolocation affordance | “Near me” helps people with location permission/device support and may exclude others | Search/list/table remain complete alternatives; location use is optional and no raw coordinate is retained |

## Release decision

No evidence supports a claim that production coverage is demographically representative. A real
partner deployment must define jurisdiction-relevant coverage segments with the collective, report
calibrated/raw/missing counts per segment, and review allocation consequences before using rankings
for siting or resources. The observatory may ship as an evidence browser only with those limits
visible and issue #106 completed for formal accessibility/translation signoff.

Last verified: 2026-07-31. Recheck cadence: every release, source/coverage/ranking/context change,
and after real partner research.
