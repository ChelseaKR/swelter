<!--
Title must be a conventional commit, e.g. "feat: add no2 breakpoints" or
"fix(ingest): quarantine empty payloads". Run `make verify` locally before
opening this PR. Complete every applicable attestation; use "N/A — reason"
instead of silently skipping one.
-->

## What this changes

A short, concrete description of the change and why.

## How it was tested

Which `make` targets and which tests. Note any new tests added.

## Acceptance and quality

- Linked issue / acceptance criteria:
- ISO/IEC 25010:2023 characteristic(s):
- Acceptance-test map row(s):
- User-visible or data-contract impact:

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
- [ ] **Export path intact.** CSV/JSON export still works and preserves the selected source's
      actual license/provenance (first-party CC0 or the applicable third-party terms).
- [ ] **Source terms intact.** First-party CC0 data and third-party provider
      terms remain distinguishable; any new/changed source card is in the diff.
- [ ] **`make verify` green.** The complete local merge gate passes at this commit.
- [ ] **Conventional-commit title.** The PR title follows Conventional Commits.

## Review-gate attestations

- [ ] **Docs and changelog.** Behavior, claims, API/data docs, source cards,
      acceptance mapping, and `CHANGELOG.md` are updated together (or N/A — reason).
- [ ] **Observability.** New paths have an observable failure signal and do not
      log secrets, exact host coordinates, or browser data (or N/A — reason).
- [ ] **Rollback.** Schema, data, infrastructure, cache, and deploy changes name
      a safe rollback or forward-fix procedure (or N/A — reason).
- [ ] **Responsible tech.** A new trust boundary, external source, sensitive
      field, ranking, or public claim updates the applicable A–F artifacts.
- [ ] **Accessibility.** A new/changed custom interaction has APG, keyboard,
      reflow, motion, and assistive-technology evidence; no unperformed manual
      review is represented as complete (or N/A — reason).
- [ ] **Internationalization.** Resident-facing copy is catalogued with EN/ES
      parity and placeholder/plural handling; human translation review is named
      only when it happened (or N/A — reason).
- [ ] **Architecture.** A guardrail, workflow permission, quality threshold,
      dependency/license posture, or durable architecture change links a MADR
      under `docs/adr/` (or N/A — reason).
- [ ] **DCO.** Every commit carries `Signed-off-by:` for the contributor.

## Related issues / ADRs

Closes #... — and link any decision under `docs/adr/` this touches.
