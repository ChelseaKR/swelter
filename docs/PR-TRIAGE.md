# Pull-request triage

A read-only pass over the seven open pull requests as of 2026-08-28, against
`origin/main` at `b725a7e` (the merge of #204).

Nothing in this pass merged, closed, commented on, labelled, re-ran or otherwise
modified a pull request, an issue or a workflow run. Merge states were checked
against GitHub and independently re-derived with `git merge-tree`, because a
`MERGEABLE` verdict answers "do these lines conflict", which is a narrower
question than "should this land".

## Summary

| Group | Count | PRs |
| --- | --- | --- |
| Merge as-is | 2 | #205, #203 |
| Merge after rebase | 3 | #206, #202, #201 |
| Needs work | 1 | #207 |
| Close as superseded | 1 | #200 |

Every check on every open PR is currently passing. No PR in this queue is red.
The work here is ordering, duplication and one weak assertion, not breakage.

## Per-PR findings

| PR | Base | GitHub state | Re-derived state | CI | Recommendation |
| --- | --- | --- | --- | --- | --- |
| #207 test(calibrate): kill the mutants the core-safety gate could not see | `main` | DIRTY | conflicts on `CHANGELOG.md` only | all 6 checks pass | **needs work** |
| #206 fix(web): rebuild the offline fallback surface with #142's heat-index error bars | `main` | DIRTY | conflicts on `CHANGELOG.md` only | all 6 checks pass | **merge after rebase** |
| #205 fix(brief,chronicle): state what a Danger count rests on (#199) | `main` | CLEAN | clean | all 11 checks pass, run is current | **merge** |
| #203 build: bump aws-cdk-lib from 2.264.0 to 2.265.0 | `main` | CLEAN | clean | all 11 pass, run predates #204 | **merge** |
| #202 build: bump types-pyyaml to 6.0.12.20260815 | `main` | CLEAN | clean | all 11 pass, run predates #204 | **merge after rebase** |
| #201 build: bump mypy from 2.1.0 to 2.3.1 | `main` | CLEAN | clean | all 11 pass, run predates #204 | **merge after rebase** |
| #200 fix(mutation): copy scripts/ into the mutants/ sandbox | `main` | CLEAN | clean | all 11 pass | **close as superseded by #204** |

## The stack, and why GitHub does not show it

Three of the author's PRs are one change, then that change plus a second, then
both plus a third. GitHub shows all three as independent PRs based on `main`,
because that is what they are: no PR here is based on another PR's branch, so
merging any one of them auto-closes none of the others.

```
origin/main  b725a7e  (contains #204, and #200's entire diff)
  |
  +-- 841a5f0  #205  fix(brief,chronicle): Danger counts state what they rest on
                     rebased onto b725a7e, CLEAN

1f7bd62  (#142, an older main)
  |
  +-- 5310169  the SAME change as #205, pre-rebase, different commit id
        |
        +-- ecb965e  #206  rebuild web/sample-surface.json
              |
              +-- 115ee1d  #207  new tests/test_calibrate.py assertions
```

Read that as containment: **#207 contains #206 contains the content of #205.**
The consequence that matters for ordering is that `5310169` and `841a5f0` are
the same change under two commit ids. When #205 lands (squash merge, so a new
third id), a plain `git rebase origin/main` of #206 will try to replay a change
that is already present.

The remedy is to rebase across the duplicate rather than onto it:

```sh
git rebase --onto origin/main 5310169 ecb965e   # #206
git rebase --onto origin/main 5310169 115ee1d   # #207, if #206 lands first, use its new base
```

This is the same family as the "cumulative snapshot" trap, with one difference
worth stating plainly: here the later PRs are **not** empty. #206 adds 57 lines
of its own and #207 adds 165 of its own. Merging the tip alone would deliver all
three, but each of the three is a separate, reviewable claim, so they are worth
landing as three.

## #200 is superseded, and the evidence is byte-level

The claim checked was that #200's entire diff is already on `main` inside #204.
It holds, and not merely in spirit:

- #200 changes exactly one file, `pyproject.toml`, adding 8 lines
  (`also_copy = ["scripts/"]` and its comment).
- `origin/main:pyproject.toml` and `origin/fix/mutation-harness-scripts-import:pyproject.toml`
  are the **same blob**, `4343e387a1c0a4eafa971a9140ef0852cc939bc2`.
- `git log -S'also_copy' origin/main -- pyproject.toml` names `b725a7e`, the
  merge of #204, as the commit that introduced it.

GitHub still reports #200 MERGEABLE, and it is: merging a branch whose only
contribution is already present resolves cleanly and changes nothing. The green
checks are real and equally uninformative. `git cherry` marks the commit `+`
(not upstream) because #204 landed the lines under a different commit, which is
why the duplication is invisible to the usual staleness signals.

Merging #200 would be harmless and would record a second, misleading authorship
of a fix that already shipped. Close it, and reference #204.

## #207: one assertion does not do what its comment says

#207 is good work, and most of it is exactly the kind of assertion the repository
asks for: exact values rather than tolerances, asymmetric comparisons against the
committed file rather than round-tripping both sides through the same serializer.
The header comment states the standard it holds itself to:

> Each is written against a value that is exact, not a tolerance, because a
> tolerance wide enough to be safe is usually wide enough to miss the mutant.

One test does not meet that standard.
`test_solve_refuses_a_singular_system_instead_of_fitting_noise` asserts:

```python
with pytest.raises(ValueError, match="singular system"):
    calibrate._solve([[1e-13, 0.0], [0.0, 1.0]], [1.0, 1.0])
# Just above the guard the same shape solves, so the threshold itself is pinned from both
# sides rather than only from the refusing one.
assert calibrate._solve([[1e-6, 0.0], [0.0, 1.0]], [1e-6, 1.0]) == [1.0, 1.0]
```

The guard in `calibrate._solve` is `if abs(a[pivot][col]) < 1e-12`. The first
assertion requires the threshold to be above `1e-13`; the second requires it to
be at or below `1e-6`. Together they pin the threshold to a **seven-decade
window**, not to `1e-12`. A guard silently widened to `1e-9`, `1e-8` or `1e-7`
passes both lines unchanged. The comment claiming the threshold is "pinned from
both sides" is the part that is wrong; the code under test is fine.

This is the "a bound asserted with data too far apart to exercise it" shape. Two
qualifications, so the finding is not overstated:

- mutmut's own number mutation adds 1 to the literal, turning `1e-12` into
  roughly `1.0`, which the second assertion does catch. This is not a surviving
  mutant today.
- The exposure is a hand edit or a future refactor moving the guard within that
  window, which nothing would notice.

Fix: straddle the guard tightly, for example `9e-13` for the refusing side and
`1.1e-12` with `rhs=[1.1e-12, 1.0]` for the solving side. That yields `[1.0, 1.0]`
exactly and leaves the threshold pinned to within ten percent.

### What was checked in #207 and found correct

- `test_residual_std_and_r2_are_the_documented_formulas` asserts
  `residual_std == 0.707107` with the comment "divided by n and not n - 1". This
  looked like a test pinning a defect as correct behaviour, since dividing by `n`
  rather than by `n - p` biases the 1-sigma downward, and understated error bars
  are precisely what #142 fixed elsewhere. It is not a defect.
  `docs/calibration.md` lines 250 to 257 publish the formula as
  `sqrt(sum(residual^2) / n)` and state that the divisor is `n` on purpose,
  because `residual_std` is the root-mean-square of the training residuals. The
  test pins published behaviour. The arithmetic also checks out: residuals
  `0.5, -1.0, 0.5` give `ss_res` 1.5, `sqrt(0.5) = 0.707107` at six decimal
  places, and `r2 = 1 - 1.5/6.0 = 0.75`.
- `test_round_collapses_negative_zero_so_a_refit_stays_byte_identical` and
  `test_round_holds_exactly_six_decimals` both genuinely fail if `_round` loses
  its `+ 0.0` or if `PRECISION` moves.
- `test_the_fitted_registry_matches_the_committed_file_key_for_key` is the
  asymmetric check its docstring claims: it compares against the parsed file
  rather than round-tripping both sides through `to_dict()`.

## #206: the fixture it fixes has no gate

#206 is correct and its reasoning is sound: `web/sample-surface.json` is the
artifact the dashboard falls back to offline, it is generated by replaying the
demo week through the real pipeline, and #142 changed how the derived heat index
propagates uncertainty without the fixture being rebuilt. The diff is confined to
`uncertainty` and `mean_member_sigma` on `heat_index_c` cells, every changed
value widens, and no mean, category, provisional flag or QC flag moves. That is
consistent with a slope floored at 1.0.

Two things follow that are not in the diff.

**A regeneration step, not a merge.** The fixture was regenerated at `1f7bd62`.
`main` has since moved to `b725a7e`, which changed `src/swelter/qc.py`. #204's
changelog states pairing behaviour is unchanged, and the change was a loop bound
rather than an arithmetic one, so the fixture is expected to be identical. That
expectation should be confirmed, not assumed. After rebasing #206, re-run
`swelter demo --web web` and confirm the tree is clean before merging.

**Nothing stops this recurring.** No test and no workflow step compares the
committed `web/sample-surface.json` against a fresh regeneration. Every reference
to it in `tests/` writes its own fixture into `tmp_path`; the only repository-copy
reader, `tests/test_demo_contract.py`, reads it for shape rather than currency.
The staleness #206 is fixing was undetectable for as long as it existed and will
be undetectable next time. A follow-up issue for a currency gate is worth
opening. It is a follow-up, not a blocker for #206.

## Non-diff hazards

**Changelog position.** Checked and clear. `CHANGELOG.md` on `main` has exactly
two section headings: `## [Unreleased]` at line 8 and `## [0.1.0] - 2026-07-16`
at line 512. #205 inserts at line 195, #206 and #207 at line 172. All three land
well inside `[Unreleased]`. No hunk is at risk of landing inside the released
`0.1.0` section.

**Two PRs appending to one file's end.** Checked and clear. The three author PRs
all add `docs/adr/0046-a-danger-count-states-what-it-rests-on.md` and all append
the same single line to `docs/adr/README.md`, but the content is identical in all
three, so an interleave is not possible. The `CHANGELOG.md` collisions are
mid-file insertions that git reports as real conflicts rather than resolving
silently, which is the safe failure. No PR appends to the end of a Python file.

**Lockfile collisions.** `git merge-tree` on all three pairs of #201, #202 and
#203 reports clean. `uv.lock` regions do not overlap.

**Stale green.** #201, #202 and #203 last ran CI on 2026-08-26. #204 landed on
2026-08-28 and added 609 lines to `tests/test_qc.py` and `tests/test_models.py`
plus a change to `src/swelter/qc.py`. All three PRs are CLEAN rather than BEHIND,
so branch protection will not force a re-run. A mypy major-version bump (#201
moves 2.1.0 to 2.3.1, with `ast-serialize` 0.5.0 to 0.8.0 and `librt` 0.11.0 to
0.15.0 alongside) that has never type-checked those 609 lines can land a red
`main` while every signal reads green. #202 is a stub bump with the same
mechanism and a smaller blast radius. #203 touches `aws-cdk-lib`, used only under
`infra/cdk/`, which #204 did not touch.

## Order of operations

1. **Close #200**, referencing #204. No merge, nothing to regenerate.
2. **Merge #205.** CLEAN, current CI against `b725a7e`, no regeneration step.
3. **Rebase #206** with `git rebase --onto origin/main 5310169 ecb965e`, not a
   plain rebase, so the duplicate copy of #205's commit is dropped rather than
   replayed. Resolve the `CHANGELOG.md` conflict by keeping both entries.
   **Then re-run `swelter demo --web web`** and confirm `web/sample-surface.json`
   is unchanged by the newer `main`. Merge once that is clean.
4. **Return #207 to its author** for the `_solve` threshold assertion. When it
   comes back, rebase it across both landed duplicates the same way, resolving
   the same `CHANGELOG.md` conflict.
5. **Rebase #201** onto the post-#205 `main` and let mypy 2.3.1 run against
   #204's new tests and the changed `qc.py` before merging.
6. **Rebase #202** and merge once #201 is green, for the same reason at lower
   risk.
7. **Merge #203** at any point. Its blast radius is `infra/cdk/`, which none of
   the above touches.

Steps 2 through 4 must stay in that order: each rebase depends on the previous
one having landed, because the branches share content rather than history.

## What was verified, and what was taken on trust

**Verified directly.**

- Every open PR's base branch, merge state and check conclusions, read from the
  GitHub API rather than assumed.
- #200's supersession, by blob hash equality on `pyproject.toml` and by
  `git log -S` naming `b725a7e` as the commit that introduced `also_copy`.
- The #205/#206/#207 containment, by `git merge-base --is-ancestor` and by
  `git range-diff` confirming `5310169` and `841a5f0` are the same change.
- The conflicting file set for #206 and #207, by `git merge-tree`, which reports
  `CHANGELOG.md` and nothing else.
- The `_solve` guard value `1e-12` and the test's `1e-13`/`1e-6` bracket, read
  from source, and the window they leave unpinned, derived from those values.
- That `residual_std`'s divisor of `n` is published in `docs/calibration.md`,
  so #207's assertion pins documented behaviour.
- The absence of any currency gate on `web/sample-surface.json`, by grepping
  `tests/`, `scripts/` and `.github/` for every reference to it.
- The `CHANGELOG.md` section boundaries and each PR's hunk line numbers.
- Pairwise `git merge-tree` cleanliness across #201, #202 and #203.
- The package set moved by #201's lockfile, read from the diff.

**Taken on trust.**

- That #204's changelog is right that `qc._pair_by_nearest_timestamp`'s pairing
  behaviour is unchanged. Step 3 above exists so this is confirmed rather than
  believed.
- #206's arithmetic that the 11 changed cells widen by 1.48x to 1.75x and that
  this is consistent with a slope floored at 1.0. The direction of every change
  was confirmed from the diff; the ratios were not recomputed.
- That the passing check runs on #201, #202 and #203 genuinely passed at the time
  they ran. The point made above is that they ran against an older `main`, not
  that their results were wrong.
- No test suite was executed as part of this pass. Correctness verdicts rest on
  reading the code and the published documents it cites.
