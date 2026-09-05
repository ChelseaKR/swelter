# The committed branch ruleset

`main.json` is a copy of the ruleset live on `main`, captured from
`GET /repos/ChelseaKR/swelter/rulesets/18752856` on 2026-09-05.

It exists because branch protection is otherwise a setting with no evidence: it
lives in repository settings, it can be widened, narrowed, or deleted without a
commit, and nothing in the history would show it. This repository already relied
on that setting in code without stating it — `.github/workflows/ci.yml` carries a
comment on the `a11y` job that "this published name is required by the existing
repository ruleset; changing it would wedge pull requests" — so the constraint was
load-bearing while being unwritten. This file writes it down.

This closes a named, dated open item.
[ADR 0012](../../docs/adr/0012-gate-bypass-incident-and-ruleset.md) asked for exactly
this file — "commit the exported artifact so the setting is verifiable from the
clone without a live API call" — and its own 2026-07-10 status update records
that `.github/rulesets/main.json` "does not exist yet, so verifying the ruleset
still requires a live API call." It does now.

## What it does not claim

**The repository-admin role can bypass every rule, always**, and the maintainer's
own account can additionally bypass through a pull request. Both are in the file
as `bypass_actors`, faithfully, rather than omitted to make the posture read
better. A solo maintainer who cannot push to their own default branch has locked
themselves out rather than hardened anything, so this file is evidence of intent
rather than proof of enforcement against the owner.

Writing them down puts two of them in view at once, which is the point:

- ADR 0012's design said **"No bypass actors — including repo admins. This is the
  control that would have stopped this incident."** The live ruleset carries two.
  ADR 0012's 2026-07-10 status update lists the deltas from its design "plainly
  rather than glossed" — the missing pull-request requirement, signed commits,
  linear history, the missing committed export — but does not mention the bypass
  actors, so that delta was the one the record did not carry.
- The unmerged `fix/cicd15-no-bypass-actors-instruction` branch supersedes that
  line with ADR 0047, and argues the admin-role bypass is deliberate and should
  stay. It also says the ruleset should carry that role **"and nothing else: no
  team, no app, no named user, no second role"** — and that a
  `bypass_mode: pull_request` bypass is no use anyway, "because the thing that is
  wedged is usually the pull request itself." The live ruleset's second actor,
  `actor_id: 3114598` (the maintainer, as a named `User`, at
  `bypass_mode: pull_request`), is precisely the entry that decision excludes.

Nothing here changes either. That is the maintainer's call in repository settings,
and this file's job is to make it a visible one.

It is also not a live-settings check. The test below deliberately does **not**
compare this file against the API: a public-scope token cannot read
`bypass_actors`, and a check that silently drops a field it could not read passes
for the wrong reason — the same "absence rendered as a value" failure this
repository guards against elsewhere. Re-capture instead:

```sh
gh api repos/ChelseaKR/swelter/rulesets/18752856 \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); print(json.dumps({k: d[k] for k in ("name","target","enforcement","conditions","bypass_actors","rules")}, indent=2))' \
  > .github/rulesets/main.json
```

## Two jobs run on a pull request and cannot block it

Capturing the live ruleset made this visible, and it is the reason the file is
worth committing. Six checks are required — `checks`, `security`, `firmware`,
`a11y-advisory`, `analyze (python)`, `analyze (actions)`. Two more run on every
pull request and are required by nothing:

| Job | Required? | Why it matters |
|---|---|---|
| `web-tests` | **no** | Runs `make web-unit`: the dashboard unit, schema, i18n, and conformance tests. The `docs/ROADMAP.md` metrics ledger names `make web-test` as the **AUTO** gate for the web interaction contract, and `make web-test` is an alias for that same target. |
| `scorecard` | no | OpenSSF Scorecard grades the repository, not the diff, and skips fork pull requests by its own `if:`. |

`web-tests` is the one that matters. An AUTO gate that cannot block a merge is a
gate in name only, and this is not a new discovery: issue
[#105](https://github.com/ChelseaKR/swelter/issues/105) already lists "strict
required checks including web-tests" among the governance controls deliberately
deferred from the July 2026 remediation. Nothing here changes the live ruleset —
making a check required is a repository-settings change, which #105 says is the
maintainer's deliberate act, not a side effect of a pull request.

Both are enumerated in `tests/test_ruleset.py`'s `NOT_REQUIRED` with a written
reason, so the list is reviewable rather than invisible, and a **third** one
cannot appear without the suite failing.

## What holds the file to the code

`tests/test_ruleset.py`, which reads the workflows rather than a hand-written
list:

- every job that runs on a pull request is a required status check, or is
  declared in `NOT_REQUIRED` with a written reason;
- no required check names a job that cannot report, which would block every merge
  — exactly the wedge the `ci.yml` comment warns about;
- no exemption outlives the job it excuses, and nothing is both required and
  excused;
- the ruleset is still `active` on `refs/heads/main` and still refuses deletion
  and force-pushes.

Matrix legs are expanded the way GitHub names them. CodeQL's job is named
`analyze (${{ matrix.language }})`, which GitHub renders by **substitution** into
`analyze (python)` and `analyze (actions)` — not by appending a leg suffix — so
the test substitutes when the name references the matrix and appends otherwise. A
checker that only appended would read both required CodeQL contexts as missing.

The `scorecard` guard is read the same way GitHub evaluates it. Its `if:` is
`github.event_name != 'pull_request' || <head repo is this repo>`, which is a fork
guard, not a pull-request exclusion; a checker that matched `!= 'pull_request'`
anywhere in the string would drop the job silently, and dropping it is exactly how
an unrequired pull-request job stays invisible.

Both workflow suffixes are scanned, reusing
`scripts/workflow_policy_check.WORKFLOW_SUFFIXES` rather than restating it, so the
two gates cannot come to disagree about what a workflow is. That constant exists
because this repository already made the other mistake: that gate globbed `*.yml`
alone, so a workflow committed as `.yaml` was invisible to it while it still
claimed to have checked every one. Here, an unseen workflow would be an unseen
unrequired job.
