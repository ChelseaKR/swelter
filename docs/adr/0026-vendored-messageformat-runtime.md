# ADR 0026: Compile and vendor MessageFormat without adopting a frontend framework

- Status: Accepted
- Date: 2026-07-16
- Deciders: Chelsea Kelly-Reif
- Supersedes: the no-build/no-runtime-dependency statements in ADR 0004

## Context

The bilingual observatory needs Unicode MessageFormat 2 semantics for plurals, selects, and stable
placeholder validation. A handwritten formatter would be a second localization language and would
weaken catalog conformance. ADR 0004's framework-free, equal-view, low-bandwidth design still holds,
but its statement that the dashboard has no build step or runtime dependency became inaccurate once
MessageFormat compilation was adopted.

## Decision

Keep the dashboard as plain HTML, CSS, and ES modules with no SPA framework or bundler. Pin
`messageformat@4.0.0-11` in the npm lock, run a deterministic install-time generator, and copy the
complete generated ESM runtime under `web/vendor/messageformat/`. Static Pages and signed-tag builds
generate that directory before packaging. Browsers load the vendored files from the same origin and
make no npm, CDN, font, analytics, or other package-network request at runtime.

## Consequences

A clean checkout now needs the locked Node build step before dashboard tests, Pages assembly, or a
signed frontend release. The generated vendor directory stays out of Git because the lockfile and
generator are its source of truth. Dependency license and complete-runtime hashes travel in the
frontend CycloneDX BOM. The accessible Map/List/Table decision and framework-free browser
architecture in ADR 0004 remain in force; only its no-build/no-dependency claims are superseded.
