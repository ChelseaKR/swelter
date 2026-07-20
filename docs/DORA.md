# DORA delivery-health ledger

This ledger uses the five-metric 2024 DORA model required by the pinned
[`QUALITY-AND-METRICS-STANDARD`](standards/QUALITY-AND-METRICS-STANDARD.md). It is
generated from retained GitHub Actions and incident-issue JSON, not from memory or
hand-maintained deployment counts.

Owner: maintainer. Evidence window: 2026-07-03T00:00:00Z through 2026-07-17T07:00:00Z.
Combined input SHA-256: `135ded7ddd14dfda63f977cd9f75bf9d43e8df97baf8bfdcac45c902b2e55a93`.

> **Evidence incomplete — no performance tier is claimed.** The previously reported aggregate counts had no retained row-level query output; they were retired rather than reverse-engineered. Scheduled CI will produce the first complete retained snapshot.
> Scheduled CI now collects complete row-level evidence; a maintainer must review
> commit a complete dated snapshot before replacing this fail-closed baseline.

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
snapshot, and retains all four evidence files as a CI artifact. Cancelled runs are
reported apart from completed deployment attempts. Rework remains a disclosed title
proxy until human quarterly classification is retained alongside it.

Last verified: 2026-07-17. Recheck cadence: weekly in CI,
quarterly for the committed snapshot, and after an incident or event-model change.
