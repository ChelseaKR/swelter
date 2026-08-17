# ADR 0040: A public place is not a host, and the consent check should not pretend otherwise

- Status: Accepted
- Date: 2026-08-16
- Deciders: Chelsea Kelly-Reif

## Context

`config.consent_concerns` warns for any node with `location: "precise"` and no `consent_ref`. Its
reason is invariant 2 and governance §4: disclosing a precise location is a decision only the host
of that node may make, and it has to be written down as a dated governance-log entry.

`openmeteo.network_doc` wrote `"location": "precise"` for every place it fetched, with a comment on
the same line saying what those places actually are: `# public city/place centroids, not private
homes`. `web_preview.config_for_web` did the same, with the same comment. The schema had one
spelling for "publish this coordinate exactly" and no way to say whether anyone lives there.

The measured cost (issue #166): the live deploy log for run 31888244080 carried hundreds of
consecutive lines of

```
swelter: ⚠ san-diego: location is 'precise' but no consent_ref recorded — a precise location
requires a dated governance-log consent entry (governance.md §4)
```

for `redding`, `crescent-city`, `yreka`, `alturas`, `weed`, `mount-shasta`, `calexico`,
`chula-vista`, `el-centro` and on through the statewide place list — once per place, twice per
deploy, every day. None of them is actionable. A CAMS model grid cell identified by a city centroid
has no host, so no consent entry can ever exist for it and the warning can never go away.

That is worse than noise. The consent warning is the mechanism that would tell a steward a real
household node has started publishing an exact coordinate without a governance-log entry, and it was
buried several hundred lines deep in a log nobody reads to the end. Nobody could diff two runs and
see that a *new* precise node had appeared. A privacy guardrail that only ever cries wolf is a
privacy guardrail that has been switched off by attrition.

## Decision

**Add a third location kind, `public-place`: an exact coordinate with no host.**

- `NodeConfig.public_location` returns the exact coordinate for `precise` *and* `public-place`.
  Every other value, including a misspelling, still snaps to the grid — only these two exact
  spellings turn coarse-by-default off.
- `consent_concerns` warns for `precise` only. A `public-place` node has nobody to ask.
- A `public-place` node carrying a `consent_ref` is a **configuration error**, not a warning. A
  consent reference means somebody believed there was a host: either a hosted node has been
  mislabelled as a public place — which would silently exempt a real home from the consent check —
  or the reference is stale. Both need a human.
- `swelter node-preview` still says the exact coordinate is published, in as many words, and adds
  that the node is declared to have no host. The exemption is from the consent *question*, never
  from the disclosure.
- `openmeteo.network_doc` and `web_preview.config_for_web` — the two places whose code comments
  already said "public place centroids, not host locations" — emit the new kind.

Two smaller alternatives from the issue were rejected. A source-level "this network is hostless"
declaration keeps the schema's conflation of "coordinate is exact" with "somebody's home is here"
and just routes around it. Aggregating the warnings into one line naming a count would shrink the
noise without making any of it actionable, and the whole California place list would still be
reported as a standing consent gap forever.

Sensor.Community nodes deliberately stay `precise`. Those are real sensors at coordinates published
by the upstream network, some of them almost certainly homes, and swelter holds no consent record
for any of them. Reclassifying them would suppress a warning that is arguably true; whether that
network's own publication satisfies governance §4 is a steward's judgement, not a schema change.

## Consequences

A deploy log contains no consent warnings for the Open-Meteo place list, and one for a
`network.yaml` node that really is a precise host location with no `consent_ref`. That one line is
legible again, and two runs can be diffed to see a new precise node appear.

Costs and accepted trade-offs:

- **`public-place` is an exemption, and exemptions can be misused.** Marking a hosted node
  `public-place` publishes its exact coordinate with no consent warning. That is why the
  `consent_ref` contradiction is a hard error, why `node-preview` states the disclosure plainly,
  and why the field documentation says outright that a coordinate where a person lives is `precise`
  with a `consent_ref`, never `public-place`. It cannot be enforced further from inside a config
  file: only a person knows whether a home is there.
- **A published node record now has a third possible `location` value.** It is additive — existing
  configs are untouched and `coarse` remains the default — and an unrecognised value still snaps, so
  an older reader that does not know the kind fails safe rather than open.
- **The web preview's 150 demo nodes change location kind**, from a `precise` that was never true
  to the `public-place` their own code comment described. Their published coordinates do not move.

Executable evidence:

- `tests/test_config.py::test_public_place_node_publishes_its_exact_coordinate`
- `tests/test_config.py::test_an_unrecognised_location_kind_still_snaps`
- `tests/test_config.py::test_consent_concerns_is_silent_for_a_hostless_public_place`
- `tests/test_config.py::test_a_public_place_that_records_host_consent_is_a_configuration_error`
- `tests/test_openmeteo.py::test_the_open_meteo_place_list_raises_no_host_consent_warnings`
- `tests/test_openmeteo.py::test_a_hosted_node_with_no_consent_ref_is_still_flagged_beside_them`

The acceptance contract is maintained under F-10 in
[`../ACCEPTANCE-TEST-MAP.md`](../ACCEPTANCE-TEST-MAP.md).
