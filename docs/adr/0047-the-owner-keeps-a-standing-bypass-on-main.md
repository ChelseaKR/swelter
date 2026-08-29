# ADR 0047: The owner keeps a standing bypass on `main`; the tag ruleset keeps none

- Status: Accepted
- Date: 2026-08-29
- Deciders: Chelsea Kelly-Reif

## Context

[ADR 0012](0012-gate-bypass-incident-and-ruleset.md) responded to the 2026-07-02 gate bypass by
specifying the `main` ruleset this repository should apply. That ruleset has still not been
created, so ADR 0012 is not a description of a live setting; it is an instruction waiting to be
carried out. One line of it is wrong, and carrying it out as written would cause the failure it
was trying to prevent:

> **No bypass actors** — including repo admins. This is the control that would have stopped this
> incident; everything else is defense in depth around it.

An empty `bypass_actors` list is not a stricter version of the same rules. It changes none of the
rules. What it removes is the maintainer's only route past a required check that cannot report a
result, and there is no second maintainer here to route around instead. GitHub answers `201` when
such a ruleset is applied, so nothing warns the person applying it, and the ruleset that now
blocks every merge is itself protected from deletion by the same rules.

This is not hypothetical. Automation applied exactly this configuration elsewhere in this
portfolio, locked the owner out of her own `main`, and restoring access took a sweep across
eighteen repositories. A bypass narrowed to `bypass_mode: pull_request` does not solve it either,
because the thing that is wedged is usually the pull request itself.

ADR 0012 was protecting something real: the 2026-07-02 incident happened because a merge gate
could be stepped around silently. But the property worth protecting is that a bypass is
*auditable*, not that it is unusable. Those are separable, and only the first one survives contact
with a single-maintainer repository.

## Decision

Supersede the bypass-actor line of ADR 0012. Every other bullet in that record still stands: the
pull-request requirement, the required status checks, stale-review dismissal, signed commits,
linear history, and the force-push block are unchanged.

When the `main` ruleset described in ADR 0012 is created, it carries exactly one bypass actor:

    { "actor_id": 5, "actor_type": "RepositoryRole", "bypass_mode": "always" }

That is the repository-admin role, held by the accountable maintainer, and nothing else: no team,
no app, no named user, no second role. `bypass_mode` is `always` rather than `pull_request`,
because a bypass that only functions inside a pull request is no use when the pull request is what
cannot merge.

The audit obligation moves onto the record instead of onto the actor list. A bypassed merge names
the blocked check and the explicit authorization in the pull request. A direct push to `main` is
the last resort, reserved for a branch so wedged that no pull request can merge at all, and it
carries the same record naming the pushed SHA. Force-push and branch deletion stay blocked in
every case, and the ruleset is never disabled or deleted to force a merge through.

The companion `v*` tag ruleset in ADR 0012 keeps `bypass_actors` empty, and that difference is
deliberate rather than an inconsistency to tidy up. A branch ruleset governs where all work lands,
so a wedged required check stops every merge and the maintainer must keep a way in. A tag ruleset
governs artifacts that have already shipped, where there is no equivalent emergency: a bad release
is corrected by cutting a new tag, never by moving an old one, and a bypass there would destroy
the immutability that makes a signed release worth anything. Do not harmonise the two lists in
either direction.

## Consequences

The maintainer can repair a wedged `main`, which is the point. The cost is that a repository-admin
bypass exists at all, and the mitigation is the record rather than the absence of the actor: a
bypass that is never explained in a pull request is the thing this repository still treats as an
incident, exactly as it did on 2026-07-02.

This posture is a deliberate divergence from the copy of `CI-CD-STANDARD.md` vendored in
`docs/standards/` at pin `v2.0.0`, whose CICD-15 row prescribes a PR-only bypass and whose §5.1
solo-maintainer profile asks for empty bypass actors. Upstream `portfolio-standards` corrected both
on 2026-08-29, but the correction is unreleased, so the vendored bytes still carry the old text and
`make standards-pin` correctly holds them to the pinned release. When a release containing the
correction is cut and vendored, this divergence closes on its own and this paragraph should be
removed rather than restated.

Two records still carry the superseded line as historical text: ADR 0012 itself, which is Accepted
and therefore append-only, and its legacy copy at
`docs/decisions/0012-gate-bypass-incident-and-ruleset.md`, which now carries a banner pointing
here. Neither was rewritten, because a decision log that edits its own past is not evidence of
anything.

A new superseding ADR is due if a second maintainer joins, which restores the option of an
independent human route past a wedged check and makes a standing admin bypass harder to justify.
