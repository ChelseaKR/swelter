# Residual-risk register

Scale: likelihood and impact are Low / Medium / High for the reference implementation. “Monitored”
means the risk is not eliminated; it has a named owner, control, and recheck trigger.

| ID | Residual risk | Likelihood | Impact | Current control | Owner | Status / next review |
| --- | --- | --- | --- | --- | --- | --- |
| R-01 | Sparse/coarse cells can still narrow a sensor host, and precise opt-in copies cannot be recalled | Medium | High | Coarse default, host consent, node preview, no coordinate in observation | Hosting collective / host | Monitored; review every siting/precision change |
| R-02 | Stolen per-node HMAC key permits forged readings for that node until rotation | Low | High | Separate mode-0600 key file, freshness window, quarantine, per-node rotation | Local steward | Monitored; rotate on suspicion and each steward handoff |
| R-03 | A privileged operator can rewrite rows and regenerate an internally consistent digest chain | Low | High | Row hash check, chained daily digest, snapshots/manifests, published copies | Data steward | Accepted only for non-regulatory use; evaluate external anchoring before consequential deployment |
| R-04 | Low-cost/provisional/model-derived data is mistaken for a safety or regulatory determination | Medium | High | Visible source/state/staleness/uncertainty, no safe claim, source cards, share-card caveats | Product/data steward | Monitored every copy/method change |
| R-05 | Confirmed-first rankings amplify calibration/coverage inequity | Medium | Medium | Provisional locations retained, coverage gaps visible, fairness review, steward planning | Hosting collective | Monitored; real deployment must disaggregate coverage before allocation use |
| R-06 | Context proxies stigmatize a neighborhood or are treated as causal/current | Medium | High | Historical/illustrative labels, omit missing data, per-layer provenance/license, no sensitive-attribute inference | Data steward | Monitored every context-source change |
| R-07 | OpenAQ provider metadata is incomplete or stripped downstream | Medium | High | Fail-closed `source-license-ledger.json`, explicit unavailable fields, no blanket CC0 | Data steward | Review every OpenAQ run/terms change |
| R-08 | Actions accumulation cache is stale, poisoned, or unavailable | Low | High | Source/scope keys, manifest/truth contract, clean fallback | Maintainer | Explicit governance exception in issue #105; review after every cache/workflow incident |
| R-09 | Service-worker cache retains stale or third-party-licensed data on a user's device | Medium | Medium | Route/release ownership, stale-while-revalidate, old-release deletion, browser clear-site controls | Maintainer / browser user | Monitored every worker/cache change |
| R-10 | Browser permission/extension/shared-device behavior exposes geolocation or saved public-cell watches outside app control | Low | Medium | Explicit location action, in-memory raw coordinate, no app telemetry, local clear-settings | Browser user | Disclosed in DPIA; review every browser-storage/permission change |
| R-11 | Automated a11y/catalog parity is mistaken for current screen-reader or Spanish-language usability | Medium | High | Honest evidence labels and release checklist | Accessibility/language reviewer | Open: [issue #106](https://github.com/ChelseaKR/swelter/issues/106) blocks formal release signoff |
| R-12 | Single-maintainer review and non-strict repository/environment governance allow an unsafe change/deploy | Medium | High | Current ruleset/status checks and disclosed incident | Maintainer | Explicitly excluded from this remediation; [issue #105](https://github.com/ChelseaKR/swelter/issues/105) |
| R-13 | Direct public exposure of the stdlib server is overwhelmed or misconfigured | Medium | Medium | Read-only methods, socket timeout/cache, reverse-proxy/CDN guidance | Deployment steward | Monitored; load/security review before hostile public exposure |
| R-14 | GitHub/Action/release identity compromise affects public artifacts | Low | High | Pinned Actions, least privilege, scanning, SBOM/signature/provenance and consumer verification | Maintainer | Monitored each release/platform advisory |
| R-15 | No real partner/user research means priorities and comprehension may not fit affected communities | High | Medium | Synthetic research is labelled; roadmap calls for partner research | Product owner / future partner | Open research risk; do not claim validated demand/usability |

No row is a claim of zero risk or external certification. Any High-impact row without a working
control blocks a consequential/public-partner release until the owner records a decision.

Last verified: 2026-07-16. Recheck cadence: each release, quarterly, after incidents, and whenever a
listed control or owner changes.
