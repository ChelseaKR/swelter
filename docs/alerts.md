# Neighborhood heat/AQI alerts

swelter publishes a feed of areas where heat or air quality has crossed a public-health danger
threshold. There is no account, no subscriber list, and no PII: the alert is a **published artifact**,
and the "subscription" lives in your own tooling (an RSS/Atom reader, or an automation you run). This
is the static-Pages-friendly design recorded in
[ADR 0010](decisions/0010-neighborhood-alerts-feed.md).

Author: Chelsea Kelly-Reif. Year: 2026.

## What raises an alert

For the most recent hour, every published grid cell is checked against documented danger floors:

| Reading | Floor | Source |
| --- | --- | --- |
| PM2.5 AQI | ≥ 101 ("Unhealthy for Sensitive Groups") | US-EPA AQI 2024 breakpoints |
| Heat index | ≥ 39.4 °C / 103 °F ("Danger") | US-NWS heat-index bands |
| Heat + air exposure | ≥ level 3 ("High") | swelter compound surface ([ADR 0009](decisions/0009-compound-heat-air-exposure-surface.md)) |

A cell can raise more than one alert (hot **and** smoky). Provisional (uncalibrated) readings can
cross a floor; the alert is published but flagged `provisional`. Floors are overridable per network in
`network.yaml`:

```yaml
alert_thresholds:
  pm25_aqi: 101        # raise on USG and worse
  heat_index_c: 39.4   # NWS "Danger"
  exposure: 3          # combined level "High"
```

## The feed

| Path | Returns |
| --- | --- |
| `/api/alerts.json` | JSON: thresholds, a data-derived `generated` time, and the active alerts |
| `/api/alerts.xml` | Atom 1.0 feed (GeoRSS point per entry) — add this to any reader |
| `/api/alerts.json?area=<area_id>` | Narrowed to one published cell (live server only) |
| `/api/alerts.xml?area=<area_id>` | The same, as Atom |

`area_id` is the published grid-cell id (`lat,lon` of the cell centre), as it appears in the surface
and in each alert's `area_id`. On the static Pages site the baked `alerts.xml` is whole-network only;
per-area filtering needs a live `swelter serve`.

Build the feed yourself:

```console
$ swelter alerts --store store/demo --format atom        # Atom to stdout
$ swelter alerts --store store/demo --web web            # bake web/alerts.json + web/alerts.xml
```

`swelter demo` and `swelter fetch` bake the feed automatically. Timestamps come from the surface's
hour buckets, never the wall clock, so the baked feed is reproducible.

### Example

```console
$ curl -s http://localhost:8000/api/alerts.json
{
  "network": "swelter demo network (downtown)",
  "generated": "2026-06-08T00:00:00Z",
  "thresholds": {"pm25_aqi": 101.0, "heat_index_c": 39.4, "exposure": 3.0},
  "count": 1,
  "alerts": [
    {
      "id": "38.5681,-121.4945|pm25_ugm3",
      "area_id": "38.5681,-121.4945",
      "area": "Walnut & 3rd",
      "lat": 38.5681, "lon": -121.4945,
      "parameter": "pm25_ugm3",
      "bucket": "2026-06-08T00:00:00Z",
      "value": 41.2, "unit": "AQI", "aqi": 114,
      "severity": "Unhealthy for Sensitive Groups",
      "threshold": 101.0,
      "provisional": false,
      "headline": "Walnut & 3rd: air quality is Unhealthy for Sensitive Groups (AQI 114), as of 2026-06-08T00:00:00Z."
    }
  ]
}
```

## Subscribing

- **In a reader.** Add `https://<your-site>/api/alerts.xml` (or `…/alerts.xml` on Pages) to any
  RSS/Atom reader. The in-dashboard "Neighborhood alerts" panel has a *Copy this area's alert-feed
  link* button that hands you the right URL.
- **As a webhook (collective-run).** See the hardened recipe below for a push into a neighborhood
  Slack/Discord relay or an SMS/WhatsApp bridge.

### As a webhook (collective-run)

If a collective wants a push into a neighborhood Slack/Discord/SMS/WhatsApp relay, it runs the bridge
**in its own infrastructure**, in its own fork, on its own schedule. The hard invariant does not move:

> **swelter never sees a contact detail.** The alert feed carries a block label, a reading, and an
> `area_id` — never a phone number, a Slack member ID, or anything else that names a person or a
> device. The recipient list, the gateway credentials, and the act of delivery all live in the
> collective's fork and its repo secrets. If a resident's number ever needs to change or be removed,
> that happens entirely in the collective's own secret store; swelter has nothing to update and
> nothing to leak.

#### Generic webhook (Slack/Discord)

A minimal scheduled bridge that re-posts new, non-provisional alerts to a chat webhook URL held in a
repo secret:

```yaml
# .github/workflows/alert-bridge-webhook.yml — runs in the COLLECTIVE's fork, not in swelter.
name: alert-bridge-webhook
on:
  schedule:
    - cron: "0 * * * *"   # hourly; swelter's own Pages build is daily
  workflow_dispatch:
permissions:
  contents: read
jobs:
  notify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5 # v4
      - name: Post new danger alerts to the collective's webhook
        env:
          FEED_URL: https://your-swelter-site.example/api/alerts.json
          WEBHOOK_URL: ${{ secrets.ALERT_WEBHOOK_URL }}
        run: |
          curl -fsSL "$FEED_URL" \
            | jq -r '.alerts[] | select(.provisional == false) | .headline' \
            | while IFS= read -r line; do
                curl -fsSL -X POST -H 'Content-Type: application/json' \
                  --data "$(jq -n --arg t "$line" '{text:$t}')" "$WEBHOOK_URL"
              done
```

This minimal form is fine for a low-traffic team chat, but it reposts **every** non-provisional alert
on **every** run — an alert that is still active an hour later gets re-sent hourly. That is noisy but
harmless in a chat channel. It is not acceptable for SMS/WhatsApp, where every re-send is a metered
message to a resident's phone. The recipe below fixes that for the channels where it matters.

#### SMS/WhatsApp gateway, with dedup and guardrails

This is a separate job from the chat webhook above, decoupled because SMS/WhatsApp needs three things
the generic webhook does not: a **provider-agnostic gateway call** (not a chat webhook shape), **dedup
state** so a resident is texted once per new alert instead of once per hour, and **cost/scope
guardrails** because a text costs money and a phone is more intimate than a chat channel.

```yaml
# .github/workflows/alert-bridge-sms.yml — runs in the COLLECTIVE's fork, not in swelter.
name: alert-bridge-sms
on:
  schedule:
    - cron: "0 * * * *"   # hourly; swelter's own Pages build is daily
  workflow_dispatch:
permissions:
  contents: write   # only to commit the seen-alert-ids state file below; nothing else
jobs:
  notify:
    runs-on: ubuntu-latest
    env:
      FEED_URL: https://your-swelter-site.example/api/alerts.json
      # Allowlist of area_ids this run may text — residents only get their own
      # block, never the whole network. area_id is the public grid-cell id from
      # the feed (see "The feed" above), never a street address.
      ALLOWED_AREAS: ${{ secrets.ALERT_AREA_IDS }}          # comma-separated area_ids
      # Hard cap on messages sent in one run, independent of how many alerts
      # fire, so a bad hour (or a bad threshold) can't run up an SMS bill.
      # This counts actual sends (alert x recipient), not distinct alerts —
      # one alert fanned out to 30 recipients spends 30 against this cap.
      MAX_PER_RUN: 20
      # Provider-agnostic SMS/WhatsApp gateway: point this at whatever gateway
      # the collective already has an account with (a Twilio-style REST API, a
      # WhatsApp Business API provider, a local telco reseller, ...). swelter
      # names no vendor here and bakes in no key — GATEWAY_URL and GATEWAY_AUTH
      # are opaque secrets the collective owns and rotates on its own.
      GATEWAY_URL: ${{ secrets.SMS_GATEWAY_URL }}           # e.g. a Messages endpoint
      GATEWAY_AUTH: ${{ secrets.SMS_GATEWAY_AUTH }}         # e.g. "Basic <base64 sid:token>"
      # area_id -> recipient list (phone numbers or WhatsApp IDs). This JSON
      # lives ONLY as an encrypted Actions secret, never as a file in the fork,
      # so a commit, a PR diff, or a public fork can never leak a number.
      RECIPIENTS_JSON: ${{ secrets.ALERT_RECIPIENTS_BY_AREA }}
    steps:
      - uses: actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5 # v4

      - name: Diff the feed against alerts already delivered
        run: |
          mkdir -p .alert-bridge
          [ -f .alert-bridge/seen-ids.json ] || echo '[]' > .alert-bridge/seen-ids.json
          curl -fsSL "$FEED_URL" > feed.json
          python3 - <<'PY'
          import json, os

          seen = set(json.load(open(".alert-bridge/seen-ids.json")))
          feed = json.load(open("feed.json"))
          allowed = {a.strip() for a in os.environ["ALLOWED_AREAS"].split(",") if a.strip()}
          cap = int(os.environ["MAX_PER_RUN"])
          recipients = json.loads(os.environ.get("RECIPIENTS_JSON") or "{}")

          # Only alerts that are: confirmed (not provisional), for an allowed
          # area, and not already delivered in a prior run.
          candidates = [
              a for a in feed["alerts"]
              if not a["provisional"]
              and a["area_id"] in allowed
              and a["id"] not in seen
          ]

          # MAX_PER_RUN bounds actual messages sent, not distinct alerts: one
          # alert fans out to every recipient in its area, so take alerts
          # greedily until the next one would push the run's total send count
          # over the cap. Skipped alerts are left off `seen` so they're
          # retried (and re-counted against the cap) next run.
          new = []
          send_count = 0
          for a in candidates:
              would_send = len(recipients.get(a["area_id"], []))
              if send_count + would_send > cap:
                  continue
              new.append(a)
              send_count += would_send

          json.dump(new, open("new_alerts.json", "w"))
          json.dump(sorted(seen | {a["id"] for a in new}), open(".alert-bridge/seen-ids.json", "w"))
          print(f"{len(new)} new alert(s) / {send_count} message(s) to deliver (cap {cap}), {len(feed['alerts'])} in feed")
          PY

      - name: Send each new alert to the SMS/WhatsApp gateway
        run: |
          python3 - <<'PY'
          import json, os, subprocess

          alerts = json.load(open("new_alerts.json"))
          recipients = json.loads(os.environ.get("RECIPIENTS_JSON") or "{}")

          for alert in alerts:
              for to in recipients.get(alert["area_id"], []):
                  # Provider-neutral request shape — swap the JSON body for your
                  # gateway's schema (most SMS/WhatsApp REST APIs take a variant
                  # of To/Body over HTTPS with bearer or basic auth). `to` comes
                  # from a secret and is never echoed, logged, or written to a
                  # file other than this in-memory request.
                  subprocess.run(
                      [
                          "curl", "-fsSL", "-X", "POST",
                          "-H", f"Authorization: {os.environ['GATEWAY_AUTH']}",
                          "-H", "Content-Type: application/json",
                          "--data", json.dumps({"to": to, "body": alert["headline"]}),
                          os.environ["GATEWAY_URL"],
                      ],
                      check=True,
                  )
          PY

      - name: Commit the updated seen-alerts state
        run: |
          git config user.name "alert-bridge"
          git config user.email "alert-bridge@users.noreply.github.com"
          git add .alert-bridge/seen-ids.json
          git diff --cached --quiet || git commit -m "alert-bridge: record delivered alert ids"
          git push
```

**Why a committed state file, not just a longer cron.** GitHub Actions cache entries are
content-addressed and immutable — you cannot overwrite `.alert-bridge/seen-ids.json` under the same
`actions/cache` key run after run, only save it once. A collective that would rather not have a bot
commit to its fork can use `actions/cache` instead, at the cost of a little more bookkeeping: give the
cache key a run-varying suffix (e.g. the ISO week) with `restore-keys` pointing at the previous
suffix, so each run restores the most recent state and saves a fresh entry, and prune stale entries
periodically. `actions/cache@0400d5f644dc74513175e3cd8d07132dd4860809 # v4` is the SHA to pin if you
go that route. Either way, the state file holds only opaque alert `id` strings (e.g.
`"38.5681,-121.4945|pm25_ugm3"`) — the same public, aggregate id already in the feed — never a
recipient, so it carries no privacy weight of its own.

**Guardrails, restated:**

- **Area allowlist.** `ALLOWED_AREAS` plus the per-area `RECIPIENTS_JSON` mapping mean a resident is
  only ever texted about their own block's `area_id`, never the whole network's alert volume.
- **Per-run cap.** `MAX_PER_RUN` bounds how many messages (SMS/WhatsApp sends) one run can push out,
  independent of how many cells cross a danger floor in a bad hour. It counts actual sends, not
  distinct alerts — an alert fanned out to many recipients in `RECIPIENTS_JSON` spends one unit of
  the cap per recipient, not one unit total. Alerts skipped because the cap is exhausted stay off the
  seen-ids list and are retried (and re-counted) next run.
- **Dedup.** The seen-ids diff means each alert is delivered once, not re-sent every hour it stays
  active — the generic webhook above does not have this property and should not be pointed at a
  per-message-billed channel.
- **Templating, opt-in, and carrier compliance are the collective's responsibility, not swelter's.**
  swelter hands you a plain-language `headline` string and nothing else. Consent capture, message
  templates and character limits, STOP/opt-out handling, WhatsApp Business template approval, and any
  telecom regulatory compliance (e.g. TCPA in the US) belong entirely to the collective operating the
  gateway — swelter has no subscriber list to consult and no standing to collect that consent on
  anyone's behalf.

Pin every Action by commit SHA with a `# vN` comment, as above — the swelter repo does the same.

## Privacy

An alert names a block and a reading, never a person or a device. The schema has no contact field; the
feed is public; subscribing requires no account. This is the same posture as the rest of swelter — see
the [hard rules](../README.md) and [ADR 0010](decisions/0010-neighborhood-alerts-feed.md).

Last verified: 2026-07-02. Recheck cadence: review when the EPA AQI breakpoints or NWS heat bands in
`models.py` change, when the alert routes change, or when the collective webhook/SMS recipe's pinned
Action SHAs go stale.
