# Data protection impact assessment

Scope: community node placement and authenticated ingestion; live-provider Pages builds; browser
geolocation, preferences/watches, notifications, URL state, service-worker caching, and Google
Analytics 4 page counts on the reference site (section 7).

Status: implementation analysis current; named-human DPIA REVIEW-GATE signoff pending. Accountable
owner: Chelsea Kelly-Reif. Machine-assisted analysis: OpenAI Codex, 2026-07-16; this is not human
review. Recheck before release and any field/storage/provider/browser-permission change.

## 1. Processing and roles

The reference project publishes public environmental data without accounts. Since ADR 0055 its
reference site sends page counts to Google Analytics 4 (section 7). A local
hosting collective is controller/steward for its exact node configuration and first-party store.
External providers control their source systems. GitHub processes repository secrets, build/cache
data, artifacts, and access logs under its service terms. A visitor's browser/OS controls location
permission, local storage, notifications, and CacheStorage.

The authoritative item-by-item inventory, location, retention, access, and publication status is
[`data-flow.md`](data-flow.md). In summary:

- observation rows contain environmental values and a collective/public-source node id, but no
  person or coordinate;
- exact community-node coordinates and HMAC keys stay operator-local;
- an OpenAQ API key exists only as a build/runtime secret;
- browser geolocation is optional and used in memory to select a nearest public cell;
- `localStorage` retains UI preferences, public-cell selections/comparisons, and watch thresholds
  until the user clears settings/site data;
- a route-scoped service worker retains public same-origin shell/data responses for offline use;
  and
- URL fragments may expose a public cell/time/parameter/comparison to anyone the user shares with,
  but are not sent in HTTP requests, and are stripped from what Google Analytics receives; and
- on the reference host only, Google Analytics 4 receives page counts (section 7).

## 2. Purpose, necessity, and proportionality

Exact node placement is necessary to operate/calibrate a physical network but not necessary to
publish observations; coarse public cells therefore satisfy the public heat/air purpose with less
host risk. HMAC keys are necessary to resist fabricated writes and are separated from public config
and stores. Provider credentials are necessary only for OpenAQ access and are not reused for users.

Browser location is not required: search, ranking, list, table, and map selection provide complete
alternatives. When requested, only the nearest public cell is retained. Watches need a public cell,
parameter, and threshold, not a person, account, push token, or raw location. Offline caching is
useful at meetings with poor connectivity, but the cached data is already public and source terms
remain applicable.

No consent banner is used. There is no advertising or profile transfer: every advertising consent
signal is denied by default and never updated, and in the EEA, the UK and Switzerland analytics
storage is denied too, so GA4 sets no cookie there (section 7). Browser
permission is the consent step for raw geolocation/notifications; the app exposes its saved state and
an in-app clear action. A community host's explicit, recorded consent is separately required before
publishing an exact node coordinate.

## 3. Threats to people

| Threat | Person affected | Control | Residual |
| --- | --- | --- | --- |
| Exact or sparse-cell host re-identification | Sensor host/household | Coarse default, per-node consent, preview, coordinate outside observations | Sparse cells and old open copies remain inferential/irreversible |
| Forged environmental record | Residents relying on readings | Per-node HMAC, QC, provenance, raw/provisional labels | Stolen key or plausible forged values may evade QC |
| Browser geolocation disclosure | Visitor | Explicit permission; in-memory nearest-cell calculation; no app transmission/persistence | Browser/OS/extensions and shared devices are outside app control |
| Saved watch/selection disclosure | Visitor on shared device | Public-cell-only data, saved-state disclosure, clear-settings control | Another local device user may infer topics/areas of interest |
| Context-driven stigma | People associated with a neighborhood | No person fields/inference; historical/proxy labels; missing data omitted | Downstream users can still overgeneralize public context |
| Provider/license stripping | Source communities/providers | Source ledger/cards and artifact terms | Downstream copies can detach caveats/attribution |
| Cache staleness | Residents | Freshness/stale labels, release-scoped worker, manifest | Browser/Actions eviction and offline duration are not deterministic |

The technical STRIDE view is in [`threat-model.md`](threat-model.md); accepted/monitored limits are
in [`residual-risk-register.md`](residual-risk-register.md).

## 4. Retention, access, deletion, and security

- **Operator data:** the hosting collective sets raw-store/quarantine/config retention and access.
  HMAC keys are mode 0600 and rotated per node. Removing a node stops future collection; exact data
  already published under open terms cannot reliably be recalled.
- **GitHub build data:** source-specific stores may live in an evictable Actions cache; the workflow
  has no application-level promise of a fixed deletion date. The public artifact remains until
  replaced and can be downloaded/copied. The excluded cache/environment governance risk is issue
  [#105](https://github.com/ChelseaKR/swelter/issues/105).
- **Browser data:** “Clear saved settings” removes `swelter.prefs`; browser clear-site-data removes
  local and service-worker storage/permission according to browser controls. Raw location and
  notification-crossing state are not stored by application code.
- **Transfer/security:** app traffic uses the deployment's HTTPS; local operators are responsible
  for transport security when exposing ingest. No secrets/person data belong in logs. Locked/pinned
  build inputs, secret/SAST scans, artifact hashes, signing/provenance, and fail-closed source
  licensing protect integrity.

## 5. Rights and notices

The reference site has no account dossier to export or correct. Users can inspect and delete the
browser state through the UI/browser. A sensor host works through the collective to inspect or remove
their private node config and withdraw precision consent for future publication. The host must be
told that prior open exports/caches may be irreversible. Provider correction/licensing requests are
routed to the original provider and reflected in the next artifact.

## 6. Decision (2026-07-16)

Processing is proportionate for a public environmental evidence tool only while minimization
controls stay intact: no person-shaped observation field, coarse host location by default, separate
credentials, optional/in-memory browser location, local-only preferences, visible source/state/
freshness, and source-specific licensing. A change that introduces accounts, background push,
analytics, exact-location persistence, person data, or a new third-party transfer requires a new
DPIA decision before merge.

## 7. Decision (2026-09-17): Google Analytics 4 page counts, ADR 0055

Section 6 requires a new decision before analytics is merged. This is that decision. The owner
directed GA4 on every public portfolio site on 2026-09-17.

- **What and why.** Page counts for the dashboard, `/sensors/`, and the planner on
  `chelseakr.github.io/swelter/`, to see which pages are used. Google receives the page address
  as origin plus path (never the `#…` place/time state or a query string), the title, the
  referring origin, browser/device/screen/language, and an approximate location it derives from
  the IP address (GA4 does not store IP addresses), plus enhanced-measurement events (scrolls,
  outbound clicks, file downloads). It never receives a search, location, watch, threshold, or
  setting.
- **Who.** Google LLC (US) processes the data under its terms. The owner's GA4 property keeps event
  data for 14 months, with Google signals disabled.
- **Controls.** No load under Global Privacy Control or Do Not Track, or after the footer opt-out
  (`swelter.analytics-opt-out`, kept outside `swelter.prefs` so "Clear saved settings" cannot undo
  it). Consent Mode v2: advertising signals denied everywhere; analytics storage denied in the EEA,
  UK and CH (cookieless pings), granted elsewhere (`_ga`, `_ga_CMSGSNGC9P` cookies, up to two
  years). The loader is bound to the reference host, so collectives' own deployments, `swelter
  serve`, and CI never load it. The service worker ignores cross-origin requests.
- **Residual risk.** Registered as R-16. Visitors outside the EEA/UK/CH carry a pseudonymous Google
  cookie, and page visits leave the site. Disclosed in the dashboard footer ("Privacy and
  analytics", English and Spanish) and on the planner.
- **Status.** Owner-directed and implemented. Named-human DPIA REVIEW-GATE signoff for this section
  is pending, like the rest of this document.

Last verified: 2026-09-17. Recheck cadence: every release and any change to schema, config,
ingestion, provider, Actions cache, browser permission/storage, service worker, analytics
configuration, or public source.
