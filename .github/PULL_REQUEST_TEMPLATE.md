<!--
Title must be a conventional commit, e.g. "feat: add no2 breakpoints" or
"fix(ingest): quarantine empty payloads". CI mirrors `make verify`; run it
locally before opening this PR.
-->

## What this changes

A short, concrete description of the change and why.

## How it was tested

Which `make` targets and which tests. Note any new tests added.

## Hard-rules gates

These are enforced project invariants. A PR that trips one is declined on
review, not merged with a follow-up. Confirm each:

- [ ] **No person-shaped data.** No new schema field could hold a person, and
      no per-device identifier was added.
- [ ] **No surveillance capability added.** No microphone, camera, Bluetooth,
      Wi-Fi client scanning, or equivalent sensing of people in firmware or
      software.
- [ ] **Calibrated vs raw stay distinguishable.** Calibrated values keep their
      version id and uncertainty; uncalibrated values stay shown provisional.
- [ ] **Accessibility gate passing.** `make a11y` (structural WCAG 2.2 AA
      subset) is green; the map is not the only way into the data.
- [ ] **Export path intact.** CSV/JSON export still works and data stays CC0.
- [ ] **`make verify` green.** fmt-check + lint + typecheck + a11y + test all
      pass locally.
- [ ] **Conventional-commit title.** The PR title follows Conventional Commits.

## Related issues / ADRs

Closes #... — and link any decision under `docs/decisions/` this touches.
