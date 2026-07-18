# Threat model

Method: STRIDE over the current data flow. Target posture: OWASP ASVS 5.0 Level 1 for the public
read-only reference surface; Level 2 controls are applied to credential-bearing operator ingest and
release paths. Swelter holds no account/health/payment data, but exact host locations, node/API
credentials, source-license integrity, and environmental record integrity are sensitive.

Accountable owner: Chelsea Kelly-Reif. Machine-assisted analysis: OpenAI Codex on 2026-07-16;
named-human security REVIEW-GATE signoff remains pending.

## Assets and trust boundaries

1. Sensor/firmware → separate operator `ingest-serve` listener.
2. Operator HMAC key file and exact-coordinate config → local store/pipeline.
3. OpenAQ/CAMS/Sensor.Community → GitHub Actions build.
4. Actions secret/cache/workflow identity → generated artifact.
5. Generated artifact → Pages CDN → browser/service worker/local storage.
6. Tagged source → isolated release build → public artifacts/signatures/provenance.

## Threats and controls

| ID / STRIDE | Scenario | Existing control | Residual / action |
| --- | --- | --- | --- |
| T1 Spoofing | Attacker submits fabricated node readings | Per-node HMAC over node id, timestamp, and body; known-node lookup; constant-time compare; freshness window; write listener separate from public server | A stolen node key can forge that node until rotation; operational detection and key custody remain steward duties |
| T2 Tampering | Raw rows, calibration registry, source ledger, or generated surface is changed | Frozen observation model, idempotent insert, stored content hashes, archive verification/digest chain, deterministic manifest, CI tests | Digest chain is not externally anchored; a privileged operator could rewrite data and evidence together |
| T3 Repudiation | Provider/operator disputes which source/version produced a claim | Per-record provenance, run/publish manifests, source truth contract, OpenAQ per-location license ledger, commit/deploy SHA | Public Pages does not provide a non-repudiation guarantee for every upstream response |
| T4 Information disclosure | Exact host coordinate or HMAC/OpenAQ key enters logs/artifact | Coordinates/keys separated from observation; coarse default; key file mode 0600; no app analytics; secret/SAST scans | `network.yaml` may itself be committed by an operator; precise opt-in/open copies are irreversible |
| T5 Denial of service | Slow client blocks stdlib server, source API stalls, or provider fails | Socket timeout, response cache/ETag/gzip, bounded source timeout/retry, static fallback, chunk-level skip | Direct hostile traffic still requires reverse proxy/CDN; fallback can be stale and must be labelled |
| T6 Elevation | Public read access reaches write path or workflow gains excess authority | Separate processes/routes, mutation verbs rejected, least-privilege workflow permissions, pinned Actions, workflow SAST | Live branch/environment governance exception is tracked in issue #105 and intentionally not remediated here |
| T7 Supply chain | Dependency/Action/workflow compromise alters a signed/public artifact | Locked install, SHA-pinned Actions, SAST/SCA/secret/workflow scanning, uncredentialed build isolated from no-checkout OIDC signer, clean draft publisher, full-asset digest binding, read-only consumer verification, and clean digest-matching promotion | GitHub-hosted runner, Actions artifact service, and signing/attestation services remain trusted; Pages cache governance exception remains |
| T8 Cache poisoning/staleness | Accumulated Actions or browser cache republishes old/wrong-source data | Scope/versioned cache keys, source contract, source-specific paths, artifact manifest, route-owned service-worker prefixes and release cleanup | Pages build uses Actions cache in an OIDC job by explicit user-excluded governance decision; cache retention/lineage requires monitoring |
| T9 License stripping | Mixed OpenAQ or other provider data is emitted as CC0 | Source-specific license parameters, generated `DATA-LICENSE`, source cards, fail-closed OpenAQ ledger | Upstream metadata may omit fields; artifact must disclose unavailability and cannot claim unrestricted reuse |
| T10 Browser privacy | Raw geolocation or watch behavior is transmitted/persisted unexpectedly | Explicit user action; nearest-cell calculation in memory; local-only preferences/watches; fragments not sent in HTTP; no analytics/push service; clear-settings control | Browser extensions, OS, CDN access logs, or shared-device users are outside app control; public cell/watch state may be visible locally |
| T11 XSS/content injection | Provider labels/attribution or URL state becomes executable markup | Text-node/textContent rendering, validated URL/state parsing, bounded static paths, schema checks | New render paths must preserve text-safe construction; Content Security Policy is deployment-specific |
| T12 Misleading safety | Stale/provisional/model/estimated value loses its caveat | State/provenance in schema and UI, source truth contract, stale label, caveat-baked share card, no “safe” claim | Screenshots/manual transcription can still remove context; downstream misuse cannot be prevented by license alone |

## Security review triggers

Update this model before merging any new credential, network listener, provider, external script,
browser permission/storage mechanism, user-generated content, publication cache, release identity,
or field capable of narrowing a person/location. Close or consciously carry every matching item in
[`residual-risk-register.md`](residual-risk-register.md).

Last verified: 2026-07-17. Recheck cadence: every release and every trust-boundary change.
