# DORA delivery-health ledger

This ledger uses the five-metric 2024 DORA model required by the pinned
[`QUALITY-AND-METRICS-STANDARD`](standards/QUALITY-AND-METRICS-STANDARD.md). It is
generated from retained GitHub Actions and incident-issue JSON, not from memory or
hand-maintained deployment counts.

Owner: maintainer. Evidence window: 2026-07-03T00:00:00Z through 2026-07-17T07:00:00Z.
Combined input SHA-256: `4e17fca41f85f06ec9540f73e363b7b9d74c245640f40cbfa8a0d5d1a2f17b4c`.

> **Evidence incomplete — no performance tier is claimed.** The previously reported aggregate counts had no retained row-level query output; they were retired rather than reverse-engineered. The scheduled run retains a complete window every week, but no step in .github/workflows/dora.yml writes it back into this repository, so that window reaches only a 90-day build artifact and this committed collection stays incomplete until publication is configured (#267).
> A maintainer must review a complete dated snapshot and commit it before this
> fail-closed baseline is replaced. The sentence above says where the scheduled
> run's own window can be read; it is checked against the workflow file.

| Metric | Portfolio target | Baseline | Result |
| --- | --- | --- | --- |
| Deployment frequency | At least weekly; alert after 14 days | Unavailable — retained inputs are incomplete | Unavailable |
| Change lead time | P90 under 1 day | Unavailable — retained inputs are incomplete | Unavailable |
| Change fail rate | Under 15% | Unavailable — retained inputs are incomplete | Unavailable |
| Failed-deployment recovery time | Under 1 day | Unavailable — retained inputs are incomplete | Unavailable |
| Deployment rework rate | Under 10% | Unavailable — retained inputs are incomplete | Unavailable |

## Reproduce and verify

The retained inputs include the API endpoint, parameters, window, pagination method,
collection completeness, and timestamp. The snapshot embeds each input digest plus a
digest. Any record or query-metadata edit therefore changes the snapshot.

```console
python scripts/dora_evidence.py check
```

Scheduled `.github/workflows/dora.yml` queries Pages runs and `incident` issues.
It normalizes the fields needed for the five metrics, generates and verifies the
snapshot, and retains all four evidence files as a CI artifact. A canceled run is
resolved from its own jobs and their check-run annotations: one killed by its
`timeout-minutes` bound is a failed deployment attempt, one whose jobs never started
or was superseded is no attempt at all, and one whose cause this reader cannot name
makes the change-failure metrics unavailable rather than smaller. Rework remains a
disclosed title proxy until human quarterly classification is retained alongside it.

Last verified: 2026-07-17. Recheck cadence: weekly in CI,
quarterly for the committed snapshot, and after an incident or event-model change.
