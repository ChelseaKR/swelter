# Deploying swelter

swelter needs no cloud. A whole network — ingest, calibration, the read-only API, and the
dashboard — runs on a single-board computer you can hold in one hand. The serverless copy in this
folder is **optional**: a way to put the public dashboard behind a CDN when a community group wants
that, not a requirement to use swelter. Committing this infrastructure-as-code does not oblige
anyone to deploy it; you can read it, ignore it, or delete the folder and lose nothing.

There are two supported deployment modes. Pick one. Most networks should pick the first.

Last verified: 2026-07-16. Recheck cadence: every 6 months, or when the cloud stack in
[`cdk/`](cdk/) changes.

---

## Mode 1 — single-board computer / self-host (recommended default)

Run swelter on hardware you own. A Raspberry-Pi-class board is enough: the services are pure
Python (the only direct runtime dependencies are PyYAML and structlog), the store is SQLite plus a
few plain files, and the
server is single-threaded and read-only.

```console
$ swelter serve --store store
swelter: serving dashboard + API at http://127.0.0.1:8000  (Ctrl-C to stop)
  dashboard http://127.0.0.1:8000/   ·   SensorThings http://127.0.0.1:8000/v1.1   ·   export http://127.0.0.1:8000/export.csv
```

Put a reverse proxy or a CDN in front for TLS and caching — the stdlib `http.server` is not
hardened for hostile direct exposure (see ADR 0005) — and you are done. Any of nginx, Caddy, or a
tunnel works; swelter does not care which.

**The store is a copyable folder.** Everything swelter publishes lives under one directory:

```
store/
├── observations.db      # SQLite; open it directly with Datasette
├── quarantine.jsonl     # malformed payloads, set aside rather than ingested
├── aggregate.geojson    # the gridded heat / AQI surface the dashboard reads
└── corrections.yaml     # the published, reproducible calibration registry
```

To back up, you copy the folder. To move to a different host, you copy the folder. To hand the
whole archive to a researcher, you copy the folder. There is no database server to administer and
nothing proprietary to export out of. The derived surfaces rebuild from the immutable raw
observations with `swelter rebuild` (or `make rebuild`), so the only thing you must not lose is the
raw table — and that is append-only.

**Cost.** One board, the electricity to run it, and a domain name if you want one. No metered cloud
bill, no account that can be suspended, no vendor between the community and its own data.

**What can fail, and what happens.** The board is the only moving part. If it loses power, the
dashboard goes dark until it comes back — but the nodes buffer and forward (store-and-forward
firmware), so readings taken during the outage backfill when the board returns rather than being
lost. If the board dies for good, you restore the copied store onto another board and keep going.
Nothing about the data depends on a cloud provider staying up.

---

## Mode 2 — optional serverless (only if a community group wants a hosted copy)

Some collectives would rather not babysit a board on someone's shelf, and want the public dashboard
on a URL that survives a power cut at the host's house. For them, [`cdk/`](cdk/) provisions a
scale-to-zero cloud copy on AWS:

- **A static dashboard on object storage behind a CDN.** The `web/` files (`index.html`,
  `styles.css`, `app.js`, the language bundles) are uploaded to S3 and served through CloudFront.
  Static files served from a CDN have no server to crash; this is the part people actually look at,
  and it stays up on its own.
- **A read-only scale-to-zero function scaffold.** The committed Lambda answers health checks and
  rejects writes. It does not expose `swelter.server`'s data routes until an operator explicitly
  bundles the package and a read-only snapshot, as documented in `cdk/README.md`.
- **A hard monthly budget alarm.** AWS Budgets watches the account spend and emails a contact when
  it crosses a single-digit-dollar threshold, because a community group funds this and a surprise
  bill is the failure mode that actually hurts.

### Scale-to-zero and cost

The point of this mode is that **nothing is always on**. The dashboard is static files. The API
function costs nothing while no one is asking it anything; between visitors it scales to zero and
the meter stops. Object storage and CDN charges are by-the-request and by-the-byte, and a
neighborhood dashboard's traffic is small, so the realistic bill is **single-digit dollars a
month** — the target this project is built to, stated in the root README. The budget alarm exists
so that target is enforced, not hoped for: if a misconfiguration, a crawler, or a sudden spike
pushes spend past the line, a human hears about it the same day.

### No always-on component whose failure takes the data down

This is the design goal of the serverless mode, and it mirrors the self-host mode:

- The dashboard is static, so there is no app server to fall over.
- The API scales to zero, so there is no long-running process to crash, leak, or need patching at
  2 a.m.; a cold start is slower, never an outage.
- The data of record is not in the cloud at all. The authoritative store is the copyable folder
  from Mode 1. The cloud copy is a published *snapshot* of it — you regenerate `aggregate.geojson`
  and the export artifacts locally and re-upload. If the entire AWS account vanished tomorrow, the
  observations would still exist in the store folder, and you would stand the dashboard back up
  somewhere else from the same files.

In other words: there is no single box, function, or vendor whose failure loses the readings. The
worst a cloud outage can do is take the *convenience copy* of the dashboard offline for a while.

### What this mode deliberately does not do

It does not run ingest, calibration, or any write path in the cloud. Those stay where the data and
the trust live: on hardware the collective controls. The cloud is only ever serving a read-only
snapshot. That keeps the attack surface tiny and the bill small, and it keeps the hard rules — no
surveillance, calibrated-vs-raw always distinguishable, the data open and portable — enforced in
one place rather than scattered across a provider's services.

See [`cdk/README.md`](cdk/README.md) for the deploy and destroy commands and the budget-alarm
rationale.

---

## Choosing

| | Mode 1: single-board / self-host | Mode 2: optional serverless |
| --- | --- | --- |
| Where the data of record lives | the copyable store folder | the copyable store folder (cloud holds a snapshot) |
| Always-on component | the board (one moving part) | none |
| Monthly cost | a board + power | single-digit dollars, with a budget alarm |
| Who you depend on | yourself | yourself + a cloud provider for the convenience copy |
| When to pick it | almost always | a group wants a hosted URL and accepts a small metered bill |

If you are not sure, pick Mode 1. You can add Mode 2 later without changing anything about how
swelter stores or publishes data, and you can remove it just as cleanly.
