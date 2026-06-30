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
- **As a webhook (collective-run).** If a collective wants a push into a neighborhood Slack/Discord/SMS
  relay, it runs the bridge **in its own infrastructure** so contact details never touch swelter. A
  minimal scheduled bridge that re-posts new alerts to a webhook URL held in a repo secret:

```yaml
# .github/workflows/alert-bridge.yml — runs in the COLLECTIVE's fork, not in swelter.
name: alert-bridge
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

Pin every Action by commit SHA with a `# vN` comment, as above — the swelter repo does the same.

## Privacy

An alert names a block and a reading, never a person or a device. The schema has no contact field; the
feed is public; subscribing requires no account. This is the same posture as the rest of swelter — see
the [hard rules](../README.md) and [ADR 0010](decisions/0010-neighborhood-alerts-feed.md).

Last verified: 2026-06-29. Recheck cadence: review when the EPA AQI breakpoints or NWS heat bands in
`models.py` change, or when the alert routes change.
