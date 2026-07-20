# Release publishing channel gap

Owner: Chelsea Kelly-Reif. Last reviewed: 2026-07-16. Recheck cadence: before enabling a new
package registry or changing release identity.

The GitHub Releases pipeline builds, checksums, signs, attests, stages, verifies, and publishes the
wheel and source distribution. That pipeline is ready, but it is not a complete standards-conforming
release channel for this repository on its own: the portfolio release standard explicitly classifies
`swelter` as a published Python package and makes PyPI Trusted Publishing mandatory.

PyPI publishing remains intentionally disabled. Trusted Publishing cannot succeed until two external
controls exist: a PyPI trusted-publisher record bound to this repository and workflow, and a dedicated
protected GitHub environment for PyPI. Adding a publishing job before those controls exist would
create a guaranteed-failing path. Treating the missing job as optional would overstate release
readiness. The machine-readable state therefore blocks a formal release until both controls exist.

The adjacent [`release-publishing-gap.json`](release-publishing-gap.json) is the machine-readable
state checked by `make release-readiness`. Once both controls exist, replace this gap with a
least-privilege, OIDC-only publish job, verify a clean consumer installation from PyPI, and update the
state in the same reviewed change.
