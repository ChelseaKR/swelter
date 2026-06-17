# Governance and data stewardship

This document is how a swelter network is run and who decides what. It is written for a real
neighborhood group — a tenants' association, a block club, a community land trust, a mutual-aid
network — not for a company. swelter is a tool the collective runs, not a service that runs them.

If you are standing up a network, copy this file into your own repo and edit it. The roles, the
quorum, and the cadence below are a starting template; change the numbers to fit your group. What
should not change are the five hard rules from the README, because the code enforces them and a
network that breaks them is no longer swelter.

## 1. Who owns the network

The network is owned by the local hosting collective: the people who host the sensors, run the
ingest, and live in the neighborhood being measured. Ownership is not held by the original author,
by whoever set up the server, or by any vendor or platform. There is no account to lose, no contract
to renew, and no company that can switch the network off or change its terms.

Concretely, owning the network means the collective controls:

- where sensors go (siting),
- how precise published locations are (the location-precision policy),
- whether any precise location is ever disclosed, and how that is decided,
- where the data lives, who can copy it, and under what license, and
- the right to leave — to export everything and run the network elsewhere with no permission from
  anyone.

The codebase is Apache-2.0 and the observation data is CC0; neither license gives the author any
ongoing control over a network someone else runs. If the collective dissolves, the data is already
public-domain and already a copyable folder, so it outlives the group that made it.

## 2. Who decides sensor siting

A sensor sits on a real person's porch, fence, balcony, or roof. Siting is therefore two decisions
that must both be yes:

1. **The host consents.** Nobody hosts a sensor without agreeing to it. A host can ask for their
   node to be moved or removed at any time, for any reason, without having to justify it. Hosting is
   a favor to the neighborhood, not an obligation.
2. **The collective agrees the location is useful and safe.** The collective decides where coverage
   is needed — which blocks are hottest, which are unmeasured, where the grid has holes — using the
   `node_health` and gap views and the map's coverage. Siting aims for overlapping coverage so a
   single node dropping offline does not blind a block (see the demo network: 18 nodes on a ~150 m
   grid, with deliberate overlap).

Siting is recorded in `network.yaml`: each node's `node_id`, `label`, `lat`, `lon`, and `location`
precision. That file is the committed, versioned record of where the network has chosen to measure.
A siting change is a change to `network.yaml` with a commit message, so the history of the network's
footprint is auditable.

## 3. Location-precision policy

This is the most sensitive policy in the system, so it is the most explicit.

**Coarse grid by default.** Every published coordinate is snapped to a grid cell before it leaves
the system. The default cell is about 150 m (`grid_resolution_m: 150` in `network.yaml`).
`config.public_location()` returns the grid-cell centre, not the host's actual coordinates, by
calling `snap_to_grid(lat, lon, grid_m)`. A reader of the map, the table, the CSV, or the
SensorThings API sees the cell, not the porch. This is the setting for every node unless a host
chooses otherwise.

**Precise is an explicit, per-node, host opt-in.** A node publishes its real coordinates only when
its `NodeConfig.location` is set to `'precise'`. This is per node, not network-wide: one host opting
in does not opt anyone else in. The default value is `'coarse'`, so the safe choice is the one you
get by doing nothing.

**Precise is never required to use the system.** Every part of swelter works on coarse locations:
ingest, QC, calibration, aggregation, the dashboard, the API, and export. Calibration is per-node
and does not need the public coordinate at all. A host who never opts into precise loses no
functionality and is not nagged to change. There is no degraded tier for coarse hosts.

**Why coarse is the floor.** The point of the network is block-scale environmental exposure, and a
~150 m cell answers "is this block hotter than that one" without publishing "a sensor is on this
person's house." The two goals do not conflict, so the default protects the host at no cost to the
mission. This is hard rule 2.

## 4. Disclosing a precise location

Disclosing a precise location — flipping a node from `coarse` to `precise` — is a decision the
collective records, not a setting someone flips quietly.

**Who may decide.** Only the host of that specific node may consent to disclosing its precise
location. The collective cannot vote a host's node to `precise` over the host's objection; precision
is the host's to give. The collective's role is to make sure the host understands what `precise`
publishes (their actual coordinates, in the open CC0 data, downloadable by anyone, including for
commercial use) before agreeing.

**How it is recorded.** Three things happen together:

1. The host's consent is written down — a dated note in the governance log (Section 8) naming the
   node, the host (by host role, not by exposing more than the host wants), the reason, and that the
   host consented.
2. `NodeConfig.location` for that node is set to `'precise'` in `network.yaml`, in a commit that
   references the log entry.
3. The change is announced to the collective at or before the next meeting, so no node goes precise
   without the group knowing.

**Reversing it.** A host can withdraw consent at any time. Setting `location` back to `'coarse'`
re-snaps future published coordinates immediately. Note the limit honestly: data already exported
under CC0 cannot be recalled — that is what "open and portable" means — so the consent conversation
must make clear that precise disclosure is effectively permanent for any data already published.
When in doubt, stay coarse.

## 5. Data stewardship

**The license.** Observations are dedicated to the public domain under CC0 1.0 (see `DATA-LICENSE`).
The collective publishes open data by default. This is a deliberate trade: in exchange for giving up
control over who reuses the data, the collective makes the data impossible for any single party —
including a future bad actor, a hostile landlord, or the author — to fence off. Open data cannot be
taken away from the community that made it.

**What is in the data, and what is not.** The observations are aggregate environmental measurements
only: temperature, humidity, particulate matter, NO2, and derived heat/air-quality indices. There is
no personal information, no device-as-tracker identifier, and no field that can hold a person. The
schema cannot carry one (hard rule 1), so opening the data does not open anyone's private life. The
only location information is the node's published coordinate, governed by Sections 3 and 4.

**Immutability and audit.** Raw observations are append-only and content-hashed; an edit is a new
record, never an overwrite. Calibrated and raw values are always distinguishable, and an
uncalibrated node is shown provisional (hard rule 3). The store is a copyable folder
(`observations.db`, `quarantine.jsonl`, `aggregate.geojson`, `corrections.yaml`), openable directly
in Datasette. Anyone can re-run `swelter calibrate` against the committed co-location data and
reproduce the published corrections, so the collective's stewardship is checkable, not asserted.

**The right to leave with the data.** Export is a first-class command, not an afterthought (hard
rule 4). Any member of the collective can run `swelter export` to take the full history as CC0 CSV
or JSON, and the whole store is a folder they can copy. Because the code is Apache-2.0 and the data
is CC0, the collective can fork the codebase, point a copy of `network.yaml` at their own nodes and
reference monitors, and stand the network up elsewhere — a different host, a different cloud, or a
single board computer with no cloud at all — without asking anyone. There is no lock-in to this
codebase, to any host, or to the original author. If the group splits, both halves can walk away
with a complete, working copy.

## 6. Roles

Keep this light. A small neighborhood group can fill all of these with a handful of people, and one
person can hold more than one role. The roles exist so that someone is responsible, not to build a
bureaucracy.

- **Hosts.** People whose property holds a node. They consent to siting, may request removal at any
  time, and are the only ones who can consent to their node going `precise`.
- **Stewards (data and operations).** One or two people who run ingest, watch `node_health`, keep
  `network.yaml` and the correction registry current, and run exports on request. Stewards execute
  the collective's decisions; they do not make policy alone.
- **Calibration lead.** Whoever organizes co-location windows against the reference monitor(s) and
  reviews when a node's residuals widen past bound and needs service. Can be a steward.
- **Accessibility and language keeper.** Someone responsible for the dashboard staying WCAG 2.2 AA
  (the `make a11y` gate) and for the non-English strings being real translations, not machine output
  — Spanish ships in v1 because of who the network serves.
- **The collective.** Everyone above plus interested neighbors. The collective is the owner and the
  final decision-maker. Membership is whoever shows up and hosts, helps, or lives in the measured
  area; there is no fee.

## 7. Decision process

Most decisions are not controversial and should not need a vote. Use the lightest process that fits:

- **Stewards decide and log routine operations.** Adding a node a host already consented to, running
  an export, scheduling a co-location window, replacing a dead sensor. The steward makes the call and
  notes it in the log. Anyone can ask for it to be revisited.
- **The collective decides policy and anything sensitive.** Changing `grid_resolution_m`, changing
  these rules, adopting a new parameter or calibration method, accepting money, or anything touching
  location precision at the network level. Decide at a meeting (in person or online). Aim for
  consensus; if you need a fallback, a simple majority of members present, with a quorum you set in
  advance (a sensible default is "at least half of active hosts plus one steward"). Record the
  decision and the rough split.
- **The host alone decides their own node.** Removal, and any move to `precise`. No vote can
  override a host on their own node.
- **Hard rules are not up for a vote.** The five rules below are enforced by the code and the review
  process. A change that would break one is not a governance decision the collective can make and
  still call the result swelter; a pull request that adds surveillance capability or a person-bearing
  field fails review regardless of who wants it.

Bigger structural choices — adopting these rules, picking the grid resolution, choosing a reference
monitor, changing the license posture — should also be written up as a short ADR in
`docs/decisions/` so the reasoning survives the meeting.

## 8. The governance log

Keep one plain, dated, append-only log — a Markdown file, a shared doc, or a notebook in a kitchen
drawer. Record:

- siting decisions and removals,
- every move to or from `precise`, with the host's consent noted,
- policy decisions and the rough vote,
- co-location windows run and recalibrations, and
- anyone joining or leaving a role.

The log is the human-readable companion to the git history of `network.yaml` and the correction
registry. Between them, the question "why is the network shaped the way it is" always has an answer.

## 9. How this maps to the five hard rules

The hard rules are in the README and are enforced by the code and the review process. Governance is
how the collective lives up to them.

1. **No surveillance, by construction.** Nothing in governance can add a microphone, a camera, or a
   person-bearing field, because the firmware and schema do not have them and a PR adding one fails
   review. Governance keeps siting focused on measuring the environment, never people.
2. **Exact node locations are the host's to disclose.** Sections 3 and 4. Coarse ~150 m grid by
   default; `precise` is a per-node host opt-in; precise is never required; disclosure needs the
   host's recorded consent.
3. **Calibrated and raw are always distinguishable.** The calibration lead and stewards keep the
   correction registry honest; uncalibrated nodes are shown provisional. Governance never pressures
   anyone to dress up a provisional reading as fact.
4. **The data is open and portable.** Section 5. CC0 data, Apache-2.0 code, first-class export, and
   the right to fork and leave with a complete copy. No lock-in.
5. **Owned by the people who host it.** Sections 1, 6, and 7. The local collective owns the network,
   decides siting and precision, and holds the final say. swelter is a tool they run, not a service
   that runs them.

---

Maintainer: Chelsea Kelly-Reif. Adapt freely for your own network; the hard rules are the part to
keep.
