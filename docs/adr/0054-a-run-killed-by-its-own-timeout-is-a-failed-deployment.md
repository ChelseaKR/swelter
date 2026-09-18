# ADR 0054: A run killed by its own timeout is a failed deployment, and a cancellation nobody classified is not a success

- Status: Accepted
- Date: 2026-09-13
- Deciders: swelter maintainers

## Context

`scripts/dora_evidence.py` scored a completed workflow run by selecting from its `conclusion`:

```python
FAILED_CONCLUSIONS = frozenset({"failure", "timed_out", "action_required", "startup_failure"})
failures = [record for record in completed if record["conclusion"] in FAILED_CONCLUSIONS]
attempts = [*successful, *failures]
```

**A job killed by its own `timeout-minutes` concludes `cancelled`, never `timed_out`.** Measured
directly on `gtfs-scorecard` run 34162993774: the job started 21:24:06Z and completed 22:09:20Z —
45 minutes to the second against `timeout-minutes: 45` — and both the job and the run concluded
`cancelled`. That workflow had been dying that way for eleven consecutive scheduled runs while
every sweep read the result as no signal.

Because a selection drops whatever it does not select, such a run left both the numerator *and*
the denominator of `change_fail_rate`, and never entered `failed_deployment_recovery_time`, which
iterates `failures` alone. The same was true of every other outcome outside the four: `skipped`,
`stale`, `neutral`, and any value GitHub adds later. `cancelled_runs` was reported beside the rate,
but it merged four different things and nothing read it.

The obvious repair — adding `cancelled` to `FAILED_CONCLUSIONS` — is worse than the blindness.
Every one of this repository's 38 cancelled `pages.yml` runs returns `total_count: 0` from the jobs
endpoint: each was evicted out of the pending queue before a runner existed. Counting them would
put a false 12.5% on a metric whose alert threshold is 15%.

The two cases are separable, and GitHub says which is which in exactly one place. The check-run
annotation on a capped job reads `The job has exceeded the maximum execution time of 45m0s`; a run
superseded while a job was already running reads `Canceling since a higher priority waiting request
for … exists` (measured on swelter `ci.yml` job 101911103002). Neither sentence is in the
`workflow_runs` payload the retained export was built from, so the old evidence could not have told
them apart from what it stored. This is therefore a change to what is retained, not only to how it
is scored.

## Decision

### 1. A cancelled run is retained with its cause, or it is not retained

Retention collects, for every cancelled run in the window, that run's jobs and each job's check-run
annotations, and stores a `cancellation` object on the record: the classified `cause` plus the
per-job step counts, start and completion times, and annotation text the cause was read from.
`retain` **refuses** a cancelled run whose evidence was not collected. A missing cause must not be
able to arrive downstream as "not a failure"; a failed fetch reddens the weekly run instead.

The schema version goes 1 → 2. A version 1 document genuinely cannot say why one of its runs was
cancelled, and a reader that read the absence as innocence would be making the mistake this change
exists to stop.

### 2. Four causes, three dispositions

`timeout_kill` is a **failed deployment attempt** — numerator and denominator, and it opens a
recovery event. `never_started` and `superseded` are **not deployment attempts** — neither total.
`unrecognised` **refuses**.

Classification runs toward the failure: a run with one superseded job and one capped job is a run
that hit its bound.

### 3. Every terminal outcome reaches a decision, including the ones nobody has met

`RUN_DISPOSITIONS` maps each `conclusion` GitHub documents for a completed run, and
`run_disposition` returns `REFUSED` for anything absent from it. An outcome nobody has classified
makes `change_fail_rate` and `failed_deployment_recovery_time` `unavailable`, naming the runs — it
does not make the denominator smaller. `deployment_frequency`, `change_lead_time` and
`deployment_rework_rate` read successful runs only and are unaffected, so one unclassifiable
cancellation does not blank the whole ledger.

This is ADR 0048 applied to a metric rather than to a gate: a run that could not be scored is not a
run that scored well.

### 4. The two numbers are an output, not a claim

`failure_mode_coverage()` reports how many of the eleven non-success terminal outcomes reach a
decision, and the `check` gate prints it on every run. Before this decision it was four of eleven.
It is now eleven of eleven — nine resolved to a side of the line, two refusing out loud.

## Consequences

`change_fail_rate` and `failed_deployment_recovery_time` become able to see the failure mode that
is most likely to go unnoticed, because a timeout kill is the one failure that already looks like
an absence of news. The retained evidence grows by one object per cancelled run, and the weekly
collection makes one extra API call per cancelled run plus one per job of those runs — bounded by
how rare cancellations are, and zero in a week with none.

Three costs, accepted deliberately.

A cancellation whose cause is neither of the two sentences above stops the two metrics until
someone adds the shape. That is a red weekly run for a case nobody has enumerated, which is the
signal wanted; `dora.yml` gates no merge, so the cost is a scheduled run and not a blocked branch.

The classification depends on GitHub's annotation wording. If that wording changes, a capped job
classifies as `unrecognised` and refuses — it does not silently become a success. That failure
direction is the reason the annotation is retained verbatim alongside the cause, so a reader can
see what the classifier was looking at.

And the bound itself is still not read from anywhere. `timeout-minutes` is not exposed by the jobs
API, so this decision takes GitHub's word for whether a bound was exceeded rather than recomputing
it from the declared bound and the observed duration. The duration and step count are retained so
that recomputation stays possible without another collection change.

**What this does not fix.** `dora.yml` still writes only to a 90-day build artifact, so the
committed `docs/audits/dora/*.json` stays `complete: false` and every metric still resolves to
`unavailable` in the committed snapshot. The improved scoring therefore reaches a reader only
through the artifact until publication is configured — the second half of #267, which
`publication_route` already holds the evidence's own sentence to, and which is not decided here.
A superseding ADR is needed when that publication route is chosen.
