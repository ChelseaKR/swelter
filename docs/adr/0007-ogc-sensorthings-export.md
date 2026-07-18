# ADR 0007: Expose a read-only OGC SensorThings 1.1 subset for interoperability

- Status: Accepted
- Date: 2026-06-16
- Deciders: Chelsea Kelly-Reif

## Context

Standards-based interoperability means a community's data is useful in the tools
people already have — QGIS, SensorThings clients, sensor-network aggregators —
without anyone writing a swelter-specific connector, which matches the project's
portability goal and the open-data license (ADR 0006). Implementing a subset
rather than the full specification keeps the surface small and honest: we expose
exactly the read paths a public dashboard and a data reuser need, and nothing
that would imply write or transaction support the project deliberately does not
offer (ADR 0005). Advertising `readOnly: true` in the service document tells
clients the truth up front. Shipping flat CSV/JSON beside SensorThings covers
everyone who does not run GIS software, so the standard is an on-ramp, not a gate.
We rejected a bespoke JSON API as the only interface (it would force every
consumer to learn our shape) and implementing the full SensorThings spec
including its write/`Tasking` paths (scope and a write surface we will not build).

## Decision

The API renders observations into the OGC SensorThings 1.1 shape so standard GIS
and analysis tools consume swelter unchanged. `swelter.api` implements a read-only
subset: `service_document()` is the `/v1.1` entry point and advertises
`"readOnly": true` in its `serverSettings`; `things()` maps nodes to `Things`
carrying only their published, grid-snapped locations (ADR 0003) with a
`location_precision` property; `observed_properties()` maps the parameter set to
`ObservedProperties` with units; and `observations()` maps readings to
`Observations`, keeping provenance (`qc`, `uncertainty`, `calibration`) in
`resultQuality` and `parameters`. Alongside it, the same data is emitted as flat
CSV and JSON (`export.to_csv`/`to_json`, re-exported from `api`). The functions
return plain dicts and strings; `swelter.server` is the thin HTTP layer over
them, so the whole API is testable without a socket.

## Consequences

A subset is not the whole specification: clients that expect full SensorThings
query options (`$expand`, `$filter`, deep navigation), `Datastreams`/`Sensors`
entities, or the create/update/delete paths will find them absent — the
`Things`/`ObservedProperties`/`Observations` collections and basic query
parameters are what is implemented. Conformance is therefore partial and is
declared as such in the service document rather than claimed wholesale. The
SensorThings vocabulary maps imperfectly onto swelter's model (parameters stand
in for `Datastreams`, and calibration/QC provenance rides in `parameters` and
`resultQuality` rather than first-class fields), so a strict client may need to
read those properties to recover full provenance. This is an external interface,
so its expected shape should be rechecked against the OGC SensorThings 1.1 spec
periodically.

Last verified: 2026-06-16. Recheck cadence: every 12 months or on a SensorThings
spec revision.

### Addendum (2026-07): outbound crosswalk + round-trip proof

`swelter.crosswalk` closes the loop this ADR opened: it maps swelter's parameter vocabulary
outbound to OpenAQ and Sensor.Community's own parameter names/units (the inverse of the inbound
maps in `sources/openaq.py`/`sources/sensor_community.py`), so data leaving over this
SensorThings export is translatable back into the commons vocabulary swelter draws from — a
label/vocabulary mapping only, with no unit conversion and an honest `None` where a parameter
(`heat_index_c`; NO2 against Sensor.Community) has no equivalent. `tests/test_roundtrip_interop.py`
proves the full round trip — swelter model → SensorThings JSON → a generic dict-walking client →
commons vocabulary — end to end. See [`docs/interop-crosswalk.md`](../interop-crosswalk.md) and
`swelter crosswalk` (read-only CLI, static table, no network).
