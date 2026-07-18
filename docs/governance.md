# Governance and data stewardship

This is a template for a tenants' association, block club, community land trust, mutual-aid network,
or other local collective operating its own swelter instance. Copy it into the operator's private
governance repository and replace bracketed choices. swelter is a tool the collective runs, not a
service that governs the collective.

Template owner: Chelsea Kelly-Reif. Last verified: 2026-07-16. Recheck cadence: annually and whenever
roles, siting, precision, retention, sources, licensing, funding, or incident procedures change.

## 1. Ownership and scope

The local hosting collective owns its node hardware, operator credentials, exact siting record,
first-party observations, configuration, publication decision, and copies of the store. Apache-2.0
allows the collective to run/fork the software without the original maintainer's permission.

Ownership does not erase upstream rights. Data fetched from OpenAQ, CAMS/Open-Meteo,
Sensor.Community, or a civic/context provider remains subject to that source's terms and attribution.
The collective may dedicate its own observations to CC0 only when it has authority to do so; the
source boundary is documented in the root `DATA-LICENSE` and `docs/data-cards/`.

Adopt a written scope:

- purpose and intended users;
- geographic area and parameters;
- named operator/data steward and accessibility/language contact;
- public sources and refresh cadence;
- data-rights decision for first-party observations;
- explicit non-goals (no regulatory, medical, individualized safety, or surveillance use).

## 2. Siting and host consent

A sensor may sit on a porch, fence, balcony, roof, school, business, or public facility. Siting needs
both host consent and a collective decision that the placement is useful, representative, and safe.

The host may request removal, relocation, key rotation, or a change from precise to coarse publication
at any time. The collective cannot vote to disclose a host's precise location over that host's
objection. Hosting is voluntary and access to the public dashboard must not depend on hosting.

The operator keeps exact coordinates and node keys in private operator-controlled configuration.
Publishing a real deployment's exact `network.yaml`, key file, or siting register in a public source
repository is not required and can defeat the privacy design. Public examples use synthetic locations.

Siting review should record shade/airflow/inlet conditions, maintenance access, reference co-location
plan, coverage gaps, potential retaliation/landlord risk, and whether a coarse public cell remains too
revealing in that setting.

## 3. Location-precision policy

**Coarse is the default.** The public path uses `public_location()` and the configured grid resolution
before a location reaches aggregation, API, export, or UI. Precision is not needed for calibration or
normal use.

**Precise is a per-node host opt-in.** Before changing a node to `precise`, record:

1. the host's dated affirmative consent and how identity is protected in the governance record;
2. a plain explanation that exact coordinates can be copied, combined with other data, and may be
   impossible to recall after open publication;
3. the purpose, expected benefit, alternatives, and review/withdrawal route;
4. the collective's safety/privacy review and decision owner.

Withdrawing consent changes future publication to coarse and triggers a rebuild. It cannot recall
copies already downloaded. A suspected exact-location leak is an incident handled under
[`runbooks/operations.md`](runbooks/operations.md).

Browser geolocation is separate from node precision: a resident explicitly asks the browser to find a
nearby public cell; swelter uses the coordinate in memory and does not store the raw device location.

## 4. Data stewardship

### First-party observations

Decide whether the collective has authority and community consent to dedicate its measurements to
CC0-1.0. Record the decision and explain the consequence: CC0 copies cannot be recalled or limited to
non-commercial/beneficial use. If the collective chooses another lawful posture, configure exports and
publication to state it accurately.

The observation schema contains environmental measurement, time, collective-assigned node id,
published location, calibration/QC/uncertainty, and provenance—not people. Do not add names, addresses,
accounts, personal device identifiers, or resident behavior. A node id must not be reused as a host
identity.

### Third-party and contextual data

For every fetched or contextual source, assign a data steward to review the source card, permitted use,
required attribution, refresh, scope, quality, and redistribution conditions. OpenAQ publication
requires the generated per-location `source-license-ledger.json`; missing/incomplete evidence fails
closed. Do not relabel third-party data as CC0 to keep a site online.

Illustrative context/cooling-center fixtures are for the synthetic demo only. A public deployment must
provide jurisdiction-verified replacements or omit the layer.

### Integrity, correction, and retention

- Raw observations are append-only. Corrections create versioned derived records; they do not rewrite
  history.
- QC labels, provisional state, uncertainty, source, freshness, and rights travel with published
  values.
- A correction to metadata, source attribution, or a bad reading is logged with reason and impact.
- Keep keys, exact siting, and private incident records outside public exports; set local retention and
  backup schedules explicitly.
- Periodically run archive verification and test restore/hand-off from a copy.

## 5. Roles and separation of responsibility

A small group may combine roles, but every responsibility needs a named person and backup:

- **Hosts:** consent to siting and decide their node's precision.
- **Data/operations steward:** operates ingest/publication, source/rights review, backups, integrity,
  freshness, keys, and incidents.
- **Calibration lead:** plans co-location, reviews evidence/residuals/drift, and approves correction
  promotion/retirement.
- **Accessibility and language reviewer:** coordinates current keyboard/reflow/assistive-technology and
  independent Spanish review; automation does not self-attest.
- **Community liaison:** explains provisional/model/estimated data, gathers feedback, and brings
  affected residents into source/siting/action decisions.
- **Collective:** owns policy, funding, scope, public publication, and material risk acceptance.

Avoid one person silently approving their own sensitive location, source-rights, calibration, and
release decision. Where independent review is unavailable, record that constraint and the compensating
control instead of claiming independence.

## 6. Decision process

Routine reversible operations may be logged by the steward. The collective reviews material choices:

- purpose/scope, new source/parameter/context/ranking/guidance;
- grid resolution or any precision-policy change;
- first-party license/retention/publication posture;
- new funding/vendor/hosting dependency;
- a calibration method or evidence threshold;
- public incident disclosure and material residual-risk acceptance.

Use consensus where practical and write down the fallback vote/quorum used by the group. A host alone
controls their node's removal and precise-location consent. The repository's core no-surveillance,
honest-calibration, caveat-preservation, source-rights, portability, and accessible-alternative rules
are conditions of calling the deployment swelter, not defaults to waive quietly.

Load-bearing technical decisions use the MADR-compatible format in [`adr/`](adr/README.md). The local
collective should keep an append-only governance log with date, participants/roles, decision,
rationale, dissent/uncertainty, owner, review date, and linked technical/config change.

## 7. Incident, appeal, and exit

Publish a resident-accessible route for corrections, accessibility barriers, source/translation
errors, and privacy concerns. Sensitive reports use a private channel. Affected hosts/residents can ask
for a decision to be reviewed without needing to understand GitHub.

Treat forged ingestion, precise-location exposure, misleading stale/provisional data, missing source
terms, illustrative production data, inaccessible critical paths, or materially wrong bilingual
guidance as incidents. Contain unsafe publication first; preserve evidence; notify affected people;
recover/rollback; record cause, duration, impact, and follow-up.

The right to leave is operational, not rhetorical: at least two stewards know how to copy and restore
the store, correction/config evidence, source/license artifacts, keys, docs, and static site to a new
host. Exports retain actual source terms. The collective can fork the Apache-2.0 code, but it cannot
strip third-party obligations from the data it takes.

## 8. Minimum review cadence

| Item | Owner | Cadence/trigger |
|---|---|---|
| Host consent and precision | Operations steward + host | Before siting/change; annual reconfirmation |
| Node health/calibration gaps | Calibration lead | At least monthly and after sensor/QC alerts |
| Source terms, attribution, scope, freshness | Data steward | Every provider change and release |
| Keys, backup, restore, incident contacts | Operations steward | Quarterly and after personnel change |
| ACR, assistive technology, Spanish clarity | Accessibility/language reviewers | Every release/material UI-copy change |
| DPIA, threat/fairness/ethics review | Collective + named reviewers | Every release/material boundary change |
| Purpose, partners, funding, community outcomes | Collective | At least annually with affected residents |
