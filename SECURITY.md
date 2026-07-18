# Security policy

Last verified: 2026-07-16. Recheck cadence: each release and whenever ingest, source fetching,
publication, browser storage, service-worker caching, or release infrastructure changes.

## Supported versions

Swelter is pre-1.0. Security fixes are made on `main` and in the latest tagged release only. Before
the first public tag, `main` is the only supported line. A released version is immutable; fixes ship
forward in a new patch version.

| Version | Supported |
| --- | --- |
| Latest tagged 0.x release | Yes |
| Older tags | No |
| `main` before the first tag | Yes |

## Report a vulnerability

Use GitHub **Private Vulnerability Reporting** from the repository's Security tab. Do not include
exploit details, secrets, exact host locations, or affected node identifiers in a public issue. If
the private form is unavailable, open a minimal public issue asking the maintainer to establish a
private channel, with no sensitive details.

Include the affected version/commit, reproduction steps, expected impact, and whether a credential
or precise location may have been exposed. The maintainer will acknowledge receipt within **72
hours**, provide a triage status within **7 days**, and coordinate a fix/disclosure timeline based on
severity. This volunteer project offers no bounty; reporter credit is optional.

## Trust boundaries and sensitive assets

The detailed STRIDE analysis is in [`docs/audits/threat-model.md`](docs/audits/threat-model.md).
The primary boundaries are:

- **Node → operator ingest listener.** `swelter ingest-serve` is a separate, write-only process.
  It authenticates a fresh request with a per-node HMAC key before normal validation and ingest.
  Keys live in an operator-local mode-0600 file, outside `network.yaml`, the store, and public
  artifacts. Rotate a node by rerunning `swelter node-key NODE_ID` and reprovisioning that node.
- **Public read surface.** `swelter serve` and the static Pages artifact expose environmental data
  by GET. The stdlib server rejects mutation methods. It is intentionally small and should be
  placed behind an appropriate reverse proxy/CDN for hostile public traffic.
- **External source → GitHub Actions build.** OpenAQ uses an Actions secret; CAMS/Open-Meteo and
  Sensor.Community are keyless. Provider payloads are untrusted input. Source, geography,
  calibration/provisional state, license, and attribution must survive into the artifact.
- **Actions cache → build → Pages.** An accumulated environmental store can influence a later
  build. It is not a secret store or release trust root. The published manifest and source truth
  contract make the output inspectable; cache retention/approval controls remain operational risk.
- **Browser.** On explicit use, geolocation is processed in memory to choose the nearest public
  cell; raw coordinates are neither transmitted by app code nor persisted. `localStorage` holds
  display preferences, public cell selections/comparisons, and watch thresholds until the user
  clears them. A route-scoped service worker caches same-origin shell/data responses for offline
  use. There is no analytics, account, advertising SDK, or background push service.

Observation data is environmental, but exact host coordinates, OpenAQ API keys, node HMAC keys,
workflow identity, source-license integrity, calibration evidence, and the untampered raw archive
are security-relevant assets.

## Supply chain and releases

The locked Python runtime has one direct dependency (PyYAML); developer and browser-test tools have
their own locked sets. CI uses SHA-pinned Actions and blocking lint/type/test, SAST, dependency,
secret, and workflow checks. Release artifacts are built from a tagged commit in an isolated job
and are expected to ship checksums, a validated CycloneDX SBOM, keyless signatures, and provenance,
followed by consumer verification. The repository does **not** claim firmware OTA signing,
dual-slot installation, or rollback; [`firmware/README.md`](firmware/README.md) correctly records
those as unimplemented.

## Incident handling

Follow [`docs/runbooks/operations.md`](docs/runbooks/operations.md): preserve evidence, contain the
affected source/write path, rotate credentials, publish a known-good artifact, and record incident
start/recovery timestamps. Never rewrite raw history or relabel third-party data as CC0 to simplify
recovery.
