# swelter serverless (CDK) — OPTIONAL

This stack is optional and is not required to run swelter. swelter runs on a single-board computer
with no cloud at all; see [`../README.md`](../README.md), Mode 1. This directory exists only for a
collective that wants a hosted, public copy of the dashboard behind a CDN, and it serves a
**read-only snapshot** of the store — never the data of record. Committing it commits a choice you
can make, not one you have made.

Last verified: 2026-07-16. Recheck cadence: every 6 months, or when `swelter_serverless_stack.py`
changes.

## What it provisions

- An **S3 bucket + CloudFront distribution** serving the static dashboard from `../../web/`.
- A **scale-to-zero Lambda** (function URL) with a read-only health/stub handler. It runs only while
  a request is in flight and costs nothing between visitors. It does **not** serve the full swelter
  API until the package and a snapshot are bundled (see [Packaging](#packaging-the-api) below).
- An **AWS Budgets monthly cost alarm** that emails a contact through SNS on overrun.

Everything is plain `aws-cdk-lib` L2 constructs — no custom resources, no third-party constructs,
nothing pinned to an exotic version.

## Prerequisites

```console
$ uv sync --locked --group infra         # exact aws-cdk-lib + constructs from the root lock
$ aws configure                          # credentials for the target account
$ npx --yes aws-cdk@2.1132.0 bootstrap   # exact CLI; one-time per account/region
```

## Deploy

Pass the funding contact and the dollar ceiling as context so nothing community-specific is baked
into the code:

```console
$ npx --yes aws-cdk@2.1132.0 synth  -c budget_email=alerts@example.org -c monthly_budget_usd=5
$ npx --yes aws-cdk@2.1132.0 deploy -c budget_email=alerts@example.org -c monthly_budget_usd=5
```

The deploy prints the dashboard URL, the API URL, and the budget contact as stack outputs. The SNS
email subscription must be confirmed once (AWS sends a confirmation link to the address).

To refresh the published snapshot after new readings: regenerate the dashboard sample locally
(`swelter demo`, which rewrites `web/sample-surface.json`) and run the pinned `npx ... deploy`
command again. The deploy re-uploads `web/` and invalidates the CDN cache.

## Destroy

```console
$ npx --yes aws-cdk@2.1132.0 destroy -c budget_email=alerts@example.org -c monthly_budget_usd=5
```

This removes everything cleanly. The S3 bucket holds only a re-uploadable snapshot of `web/`, never
the data of record, so it is set to empty and delete on destroy — you lose nothing irreplaceable.
The authoritative store stays on the host that runs swelter.

## Packaging the API

`lambda/handler.py` is a deliberate stub: it answers `/health` and refuses non-GET, so the stack is
deployable and smoke-testable as-is, but it does not yet serve real data. To wire it up, bundle the
`swelter` package and a **read-only snapshot of the store folder** into the function (as the
function asset or a layer) and dispatch the request path into swelter's API handling. Ingest,
calibration, and every write path stay on the host you control — the cloud only ever serves a
read-only snapshot. This keeps the function tiny and the trust in one place.

## Budget-alarm rationale

A community group funds this deployment, and the realistic bill for a static dashboard plus a
scale-to-zero API is single-digit dollars a month. The failure mode that actually hurts a funded
project is not downtime — the dashboard is static and the API scales to zero — it is a **surprise
bill** from a misconfiguration, a crawler, or a traffic spike. So the budget alarm is part of the
stack, not a thing someone has to remember to add in the console:

- It watches the **whole account's** monthly cost (AWS Budgets is account-scoped), which is what you
  want for a copy a group is paying for.
- It warns **early at 80% of forecast** so there is time to react before the ceiling, and again the
  moment **actual spend crosses 100%** of the limit.
- The ceiling defaults to a small dollar figure and is set per deployment with
  `-c monthly_budget_usd=...`, so the target is enforced, not hoped for.

If you do not want a cloud bill at all, you do not need this directory. Run swelter on a board.
