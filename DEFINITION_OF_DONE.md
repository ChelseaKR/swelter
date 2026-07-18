# Definition of Done

This is the release contract for swelter. A change is done only when every applicable gate below
passes at the same commit. The numeric and procedural floors come from the pinned portfolio
standards in [`docs/standards/`](docs/standards/); this file records the swelter-specific evidence.

Owner: Chelsea Kelly-Reif. Review cadence: quarterly and before every release.

## AUTO-GATE

- [ ] `make verify` passes from a locked install and runs the complete local merge gate documented
  by `make help`. CI invokes that same target rather than maintaining a second command list.
- [ ] Python formatting, lint (including complexity and security rules), strict typing, tests, and
  the branch-coverage floor pass.
- [ ] Dashboard unit/schema tests, firmware checks, structural and browser accessibility checks,
  internationalization checks, documentation checks, and declared performance budgets pass.
- [ ] Playwright passes in the locked Chromium, Firefox, and WebKit engines; no engine is silently
  skipped in CI or the signed-tag verification job.
- [ ] Dependency, secret, source, and workflow scans pass with no error-suppressing fallback.
- [ ] The built wheel and source distribution pass the package/version consistency checks.
- [ ] Every changed feature has a measurable acceptance criterion and test reference in
  [`docs/ACCEPTANCE-TEST-MAP.md`](docs/ACCEPTANCE-TEST-MAP.md).
- [ ] Every external dataset used or published has a current source card, provenance, method,
  license, and retention statement under [`docs/data-cards/`](docs/data-cards/README.md).
- [ ] No hard rule regresses: person-shaped data and surveillance remain absent; public host
  locations remain coarse by default; raw/provisional and calibrated values remain distinct;
  source license terms travel with generated artifacts; export remains available.

## REVIEW-GATE

- [ ] The PR links its acceptance criteria and names the affected ISO/IEC 25010:2023 quality
  characteristic(s).
- [ ] Documentation, user-facing claims, data cards, and the changelog change in the same PR as
  the behavior they describe.
- [ ] A new or changed trust boundary updates the threat model, DPIA, data-flow inventory, and
  residual-risk register. A new external source also receives a source/license review.
- [ ] A hard guardrail, permission boundary, dependency/license posture, or architectural decision
  has a proposed MADR record under [`docs/adr/`](docs/adr/README.md).
- [ ] A custom interactive component updates the accessibility evidence. Screen-reader and
  translation review are recorded only when a named reviewer actually performed them; an
  unperformed manual review stays explicitly open.
- [ ] Operational impact, rollback, and observability are addressed. “Not applicable” includes a
  reason in the PR, not a blank checkbox.
- [ ] The responsible-tech A–F artifacts are current for the changed surface and identify an owner,
  review trigger, and residual risk.
- [ ] Commits include a Developer Certificate of Origin sign-off (`Signed-off-by:`).

## RELEASE-GATE

- [ ] The tag, package metadata, changelog section, citation metadata, and deployed version agree.
- [ ] The full verification target is rerun at the tagged commit in an isolated release job.
- [ ] The release attaches the wheel/sdist, checksums, validated CycloneDX SBOM, signatures,
  provenance, and the human-readable changelog section.
- [ ] A clean consumer environment verifies the downloaded artifact, signature, provenance,
  metadata version, and basic CLI behavior.
- [ ] The ACR and manual assistive-technology record are current, or the release is explicitly
  blocked; the same rule applies to required human translation review.
- [ ] Current and prior stable branded Edge pass the compatibility smoke defined in
  [`web/README.md`](web/README.md#browser-support-policy), or the release is explicitly blocked; the
  Chromium engine run is supporting evidence, not a relabelled branded-Edge pass.
- [ ] The source cards, DPIA, threat model, fairness review, ethics scan, and residual-risk register
  have been rechecked against the exact release candidate.
- [ ] The operations runbook and rollback procedure are current.
- [ ] There are no open P0/P1 defects for the release. Any accepted lower-severity residual risk is
  recorded with an owner and next review date.

Last verified: 2026-07-16. Recheck cadence: quarterly, before every release, and whenever the
pinned portfolio standards change.
