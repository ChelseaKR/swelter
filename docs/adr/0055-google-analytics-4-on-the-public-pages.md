# ADR 0055: Google Analytics 4 counts page views on the public pages, and never sees a place, search, or setting

- Status: Accepted
- Date: 2026-09-17
- Deciders: Chelsea Kelly-Reif

## Context

On 2026-09-17 the owner decided to run Google Analytics 4 on every public site in the portfolio,
and to update privacy pages and claims to match. Until then the swelter reference site promised the
opposite in several places. `SECURITY.md` said "There is no analytics", the ROADMAP listed client
analytics/RUM as a non-goal, the DPIA said no consent banner was needed "because the app has no
analytics", and the neighborhood-alerts intro told residents the data had "no tracking". The DPIA
also requires a new decision before analytics is merged. This record is that decision. It does not
rewrite the Accepted records that described the earlier posture (ADR 0010's "no tracking" framing
of the alert feed stays true of the feed itself: feeds are XML and are never tracked).

The invariant in `CLAUDE.md` that matters most here is "No surveillance": no people, accounts,
device scanning, or personal identifiers in the schema, firmware, browser, logs, or
infrastructure. GA4 is a third party that sets a pseudonymous browser cookie outside the EEA, the
UK, and Switzerland. The owner has accepted that cost for page-level counts. The design below keeps
GA away from everything the invariant protects: places, searches, watches, and settings.

## Decision

`web/analytics.js` is the only file that talks to Google. The dashboard (`/`), the `/sensors/`
route (a copy of the dashboard), and the planner (`/planner/`) load it with `defer`. On the
dashboard it comes after `app.js`, because deferred scripts run in document order and a loader
placed first measurably delayed the Lighthouse LCP; it announces itself with a
`swelter:analytics` event, which `app.js` waits for before wiring the opt-out control. It holds the measurement
ID, `G-CMSGSNGC9P` (GA4 property 554836705, 14-month retention, Google signals disabled on the
property). Setting it to `""` removes GA and the opt-out control entirely.

With an ID set, it loads `gtag.js` only when every one of these holds:

- the page is served over HTTPS from `chelseakr.github.io` under `/swelter/`, so `swelter serve`,
  a collective's own deployment, local previews, and the Playwright, pa11y, and Lighthouse servers
  on 127.0.0.1 never contact Google;
- `navigator.globalPrivacyControl` is not `true`, and Do Not Track (`navigator.doNotTrack`,
  `window.doNotTrack`, `navigator.msDoNotTrack`) is not `"1"` or `"yes"`; and
- the visitor has not opted out (localStorage `swelter.analytics-opt-out` is not `"1"`).

When it loads:

- **Consent Mode v2 defaults.** `ad_storage`, `ad_user_data`, and `ad_personalization` are denied
  everywhere. `analytics_storage` is denied through `region` for the EEA (EU-27 plus IS, LI, NO),
  GB, and CH, and granted elsewhere. There is no banner, so the defaults never change. In those
  regions GA sets no cookie and Google receives cookieless pings.
- **Config.** `allow_google_signals: false` and `allow_ad_personalization_signals: false`.
- **Place state is stripped.** `page_location` is origin plus path, so the `#p=…&t=…&l=…&c=…`
  fragment that names the selected cell, time, parameter, and comparison never reaches Google.
  `page_referrer` is the referring origin only. The file never reads `swelter.prefs`, the search
  box, geolocation, or watch thresholds, and sends no custom events.
- **The service worker stays out of it.** `web/sw.js` now returns early for every cross-origin
  request, so `gtag.js` and measurement pings are never cached or replayed from CacheStorage, and
  `analytics.js` joins the offline shell.

The opt-out is a footer button on the dashboard (localized through the MessageFormat catalogs) and
on the planner (English, like the rest of the planner). It stores `"1"` under
`swelter.analytics-opt-out`, sets Google's `window["ga-disable-G-CMSGSNGC9P"]`, and relabels to
"Opt back in". The key is deliberately outside `swelter.prefs`, so "Clear saved settings" never
silently opts a visitor back in. Under GPC/DNT, or with storage blocked, the button is hidden and
the status line says why. The dashboard footer gains a "Privacy and analytics" disclosure that
describes all of this in English and Spanish. The planner's "Nothing leaves this page" docket
becomes "Your answers stay on this page" and names GA.

The site sets no Content-Security-Policy (GitHub Pages sends none, and no page carries a CSP meta
tag), so no CSP changes. A future CSP must allow `script-src https://www.googletagmanager.com`,
`connect-src https://*.google-analytics.com https://*.analytics.google.com
https://www.googletagmanager.com`, and `img-src https://*.google-analytics.com
https://www.googletagmanager.com`.

## Consequences

- The "no analytics / no client telemetry / no tracking" claims in `SECURITY.md`, the README,
  `docs/ROADMAP.md`, `docs/ARCHITECTURE.md`, `docs/MULTIYEAR-PLAN.md`,
  `docs/RESPONSIBLE-TECH-AUDITS.md`, the DPIA, the data-flow inventory, the threat model, the
  residual-risk register, the ethics scan, and the dashboard and planner copy are corrected. The
  DPIA records this as a new decision with named-human signoff still pending.
- Field RUM stays N/A. GA4 page counts are not Core Web Vitals field data, and Lighthouse remains
  the lab regression gate; the lab runs never load GA.
- `web/tests/analytics.unit.test.js` runs the loader in Node for each guard and includes negative
  controls that remove a guard and assert the harness notices. `web/tests/app.unit.test.js` covers
  the dashboard control.
- Owner steps in the GA4 web stream: under Enhanced measurement, turn off "Page changes based on
  browser history events" (`updateHash()` calls `history.replaceState` on every selection, and GA
  could record each change as a page view that bypasses the stripped `page_location`), "Site
  search", and "Form interactions".
- A collective that deploys swelter elsewhere gets no GA: the loader is bound to this host and
  path. If that binding is ever widened, this ADR must be superseded first.
