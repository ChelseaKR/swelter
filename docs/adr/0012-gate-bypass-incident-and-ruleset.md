# ADR 0012: Incident note — the 2026-07-02 gate bypass and the ruleset that should prevent recurrence

- Status: Accepted
- Date: 2026-07-05
- Deciders: Chelsea Kelly-Reif

## Context

A merge gate that can be bypassed by the person it is supposed to hold accountable is not a gate,
it is a suggestion. The honest response to finding that out is to say so precisely (what, when,
why it was possible), fix what can be fixed without further live-infrastructure changes from an
audit/remediation pass, and leave an exact, actionable to-do for the one action that requires a
human with admin access to this GitHub repository — not to guess at repository settings or take
an irreversible action (like rewriting signed/unsigned history) on the maintainer's behalf.

## Decision

Record, plainly and without editing history, that three commits landed on `main` outside the
merge gate — and specify the branch-protection ruleset design that closes the gap, plus the
compensating controls put in place immediately (this ADR's own date) while that ruleset is
enacted.

### What happened

Commits `3042f35` ("FIX-01: authenticated node write path"), `2f66dc9` ("test(ingest-server):
drive the real listener, not just verify_request()"), and the merge commit `4cb7e11` (2026-07-02)
are the only commits in this repository's history that are (a) unsigned (`git log --format=%G?`
reports `N`, where every other recent commit reports `E`, signed with a key not available
locally) and (b) carry no PR reference, where every other recent commit does (`(#NN)`). They were
pushed directly to `main` and merged while `make verify` was red: 2 ruff `E501` violations, one
formatting drift, and 17 `mypy --strict` errors in `tests/test_ingest_server.py` and
`tests/test_firmware_signing.py` against the locked toolchain (ruff 0.15.17, mypy 2.1.0). The
2026-07-05 conformance audit (`STANDARDS/` v1.0.1) caught this; nothing else surfaced it.

This is direct, dated evidence that the "every commit lands through a green, reviewed PR" model
this project's own documentation (CLAUDE.md, the PR template) assumes was **not enforced** at the
platform level — a single maintainer with push access could (and did) bypass it, whether or not
that was the intent at the time.

### What this ADR does *not* do

It does not rewrite `main`'s history to remove or re-sign those three commits. Rewriting public
history to hide a mistake is worse than disclosing it; the README's Standards conformance table
now discloses it too. Commit signing is expected to resume for everything after this ADR.

### The fix, in two parts

**1. Immediate (done same-day, 2026-07-05, no GitHub admin action required):**

- The red gate itself is fixed — see the Standards conformance table in `README.md` and the
  Execution Log in `audit-2026-07-05/swelter-REMEDIATION.md`. `make verify` is green again.
- `.github/CODEOWNERS` is committed, naming the maintainer as owner of the whole tree and
  explicitly of `.github/workflows/`, `src/swelter/ingest_server.py` (the authenticated write
  path this incident touched), and `scripts/` (the gate scripts) — so a ruleset that requires
  code-owner review has something to enforce against.
- `release.yml` now re-runs `make verify` at the tag before signing/publishing anything, so a red
  `main` (as `main` was between 2026-07-02 and 2026-07-05) cannot ship a signed release even in
  the absence of branch protection.

**2. ⛔ Requires a manual, one-time action in GitHub's repo settings (cannot be done from a local
clone or by an agent without live write access to the repository's admin settings — see the
ground rules this remediation pass operated under):**

Create a ruleset on `main` (Settings → Rules → Rulesets → New branch ruleset, or
`gh api repos/ChelseaKR/swelter/rulesets` with a `POST`) with:

- Require a pull request before merging.
- Require ≥1 approving review. **Compensating control for the single-maintainer repo**: with one
  human maintainer, a second independent human reviewer is not available today. Until a co-
  maintainer or trusted external reviewer joins, the maintainer documents self-review explicitly
  in the PR description (what was checked, what could not be independently verified) rather than
  silently merging with no review record. This is a stated, temporary compensating control, not a
  substitute for the standard's ≥2-reviewer civic expectation — revisit when a second maintainer
  is onboarded.
- Required status checks: `checks`, `security`, `firmware` (from `ci.yml`); add `zizmor` and
  `codeql-actions` once P1-3 lands.
- Dismiss stale reviews on new pushes.
- Require signed commits.
- Require linear history.
- Block force pushes.
- **No bypass actors** — including repo admins. This is the control that would have stopped this
  incident; everything else is defense in depth around it.
- A companion tag ruleset for `v*`: block tag deletion and moves (REL-07's enforcement half).

After creating it, commit the exported artifact so the setting is verifiable from the clone
without a live API call:

```console
$ gh api /repos/ChelseaKR/swelter/rulesets/<id> > .github/rulesets/main.json
```

and verify enforcement empirically with a direct push attempt against `main`, which must be
rejected.

## Consequences

Until the ruleset above is actually created in GitHub's settings, **this incident could recur**:
nothing in this repository's committed files can force-enforce branch protection, because that
setting lives in GitHub's platform configuration, not in version-controlled files. The immediate
fixes (green gate, CODEOWNERS, release-time re-verification) reduce the blast radius of a repeat
but do not prevent one. The single-maintainer compensating control for required review is a real
gap against the standard's ≥2-reviewer expectation, not a full substitute; it should be revisited
the moment a second maintainer or trusted reviewer is available.

### Status update — 2026-07-10

A ruleset on `main` is now **active**, verified via
`gh api repos/ChelseaKR/swelter/rules/branches/main`. It enforces: branch deletion blocked,
non-fast-forward (force) pushes blocked, and six required status checks — `checks`, `security`,
`firmware`, `a11y-advisory`, `analyze (python)`, `analyze (actions)`. Differences from the design
above, stated plainly rather than glossed:

- **No require-pull-request rule yet**, so the ruleset requires green checks but not a PR or a
  review record; the self-review compensating control above therefore still carries weight.
- Signed commits and linear history are not asserted by the active rules.
- `.github/rulesets/main.json` (the committed export of the live setting) does not exist yet, so
  verifying the ruleset still requires a live API call.

The core exposure — a red-gate commit landing directly on `main` — is now blocked by the
required-status-check rules; the remaining deltas above stay open items.

Last verified: 2026-07-10. Recheck cadence: re-verify the ruleset is still active whenever
`.github/rulesets/main.json` would be expected to change, and at least once per release.
