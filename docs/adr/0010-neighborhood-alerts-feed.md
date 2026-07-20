# ADR 0010: Deliver neighborhood heat/AQI alerts as a generated public feed, not a subscriber list

- Status: Accepted
- Date: 2026-06-29
- Deciders: Chelsea Kelly-Reif

## Context

swelter deploys as a static site over a read-only, scale-to-zero server (ADR 0005). A push channel
that emailed or texted residents would need a backend that stores contact details and which areas
each person watches — exactly the person-shaped, surveillance-adjacent record the hard rules forbid,
and a hosted dependency that takes control away from the collective (hard rules 1 and 5). Inverting
it — publish the danger, let the subscription live in the resident's own tooling — delivers the same
"tell me when my block is dangerous" outcome with no account, no PII, and no tracking, and it works
unchanged on Pages. Atom is a 20-year-old open standard with universal reader support and trivial
webhook bridging, so the feature needs no new runtime dependency. Thresholds are public-health bands
with citable provenance, not swelter inventions, so an alert is defensible.

For collectives that do want a push (a neighborhood Slack/Discord/SMS/WhatsApp relay), the answer is a
**webhook bridge they run in their own infrastructure**: a scheduled job diffs the public feed and
POSTs new alerts to a URL they control, keeping any contact details on their side, never in swelter.
`docs/alerts.md` documents this pattern with SHA-pinned Action examples, including a hardened
SMS/WhatsApp delivery recipe with dedup state, an `area_id` allowlist, and a per-run send cap.

## Decision

Let a resident "subscribe to their neighborhood" for dangerous heat or air without swelter ever
holding who they are or where they live. The alert is a **published artifact**, not a message sent to
a person:

- `swelter.alerts.build_feed` scans the latest hour of the aggregated surface and raises one alert
  per published cell that crosses a documented danger floor — US-EPA AQI 101 ("Unhealthy for
  Sensitive Groups"), the US-NWS heat-index "Danger" tier (39.4 °C / 103 °F), or exposure level 3
  ("High", ADR 0009). Floors are overridable per network via `alert_thresholds` in `network.yaml`.
- The feed renders as `/api/alerts.json` and as a standards **Atom 1.0** feed at `/api/alerts.xml`
  (with a GeoRSS point per entry). A resident adds the feed — whole-network, or one area via
  `?area=<area_id>` on a live server — to any ordinary RSS/Atom reader, or points an automation at
  it. `swelter demo` / `swelter fetch` bake `web/alerts.json` + `web/alerts.xml` so the static Pages
  site carries them, and a new `swelter alerts` command writes them on demand.
- The dashboard adds a **Neighborhood alerts** panel: pick an area, see the active danger-level
  alerts in plain language (text-first, never color-only; provisional readings are flagged), and copy
  the area's feed link to subscribe in your own reader. This is separate from the existing on-device
  personal "watch", which stays a localStorage-only convenience with no network role.
- Every alert carries only public, aggregate fields (cell id, centroid, host area label, node ids,
  reading). Timestamps are the surface's hour buckets, never the wall clock, so the baked feed is
  reproducible byte-for-byte.

## Consequences

The feed is only as fresh as the last pipeline run — on Pages that is the daily rebuild, so it is a
"once a day, on a hot day" signal, not a real-time push; the docs say so plainly and a collective
that needs minute-level alerting runs a live `swelter serve` with its own bridge. A reader-based
subscription is more friction than a text message and assumes some tooling literacy; the in-page
panel softens this for the common case. Per-area filtering (`?area=`) needs a live server — the
static feed is whole-network only, and the dashboard says so. Provisional (uncalibrated) readings can
raise an alert; suppressing real danger because a sensor is not yet calibrated would be worse, so the
alert is published but labelled provisional, the same honesty the map keeps. Finally, danger floors
are a policy choice: the defaults are conservative public-health boundaries, but a network can lower
them, and a poorly chosen floor either cries wolf or stays silent — which is why the threshold lives
in the reviewable `network.yaml`, not buried in code.

Last verified: 2026-06-29. Recheck cadence: revisit whenever the EPA AQI breakpoints or the NWS
heat-index bands in `models.py` change, or if a real-time delivery requirement emerges.
