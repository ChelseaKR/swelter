# ADR 0044: An unattributable store is discarded, not refused forever

- Status: Accepted
- Date: 2026-08-19
- Deciders: Chelsea Kelly-Reif

## Context

`swelter fetch --accumulate` refuses to add to a store that cannot say where its readings came from:

```python
if existing_observations and not existing_metadata.is_file():
    raise ValueError("--accumulate requires source-metadata.json for an existing store")
```

The refusal is correct. Rule 6 says rights are source-specific and third-party terms are retained; a
store holding observations with no `source-metadata.json` cannot name their license or attribution,
so publishing from it would put readings on a public surface under terms nobody can state.

What was wrong is that the refusal had no exit.

The Pages workflow restores `/tmp/openaq`, `/tmp/cams` and `/tmp/sc` from an `actions/cache` entry
keyed by day, with `restore-keys: swelter-fetch-store-scope-v2-` as a most-recent fallback. The
cached `/tmp/sc` store predates the `source-metadata.json` requirement. So on every run:

1. `restore-keys` restores the same metadata-less `/tmp/sc` store — a cache **hit**, not a miss.
2. `swelter fetch --source sensor-community --accumulate` refuses.
3. The workflow's documented "a cache miss just degrades to a fresh fetch" never fires, because
   nothing missed.
4. `/sensors/` falls back to a copy of page 1, and the run reports success.

Observed on every `demo` run inspected from 2026-08-16 to 2026-08-19 (runs 31922835687,
31950970092, 32037396595, 32144077063, 32259812111):

```
swelter: source provenance is invalid (--accumulate requires source-metadata.json
for an existing store); refusing
```

The store that causes the refusal is written back into the cache and restored again next run. The
condition is self-sustaining: no rerun, no schedule, and no code change to the adapter can clear it.
`/sensors/` had been a byte-identical duplicate of page 1 for that whole window while CI stayed
green, because a source falling back is a supported outcome and the workflow cannot tell
"Sensor.Community declined" from "swelter refused to open its own cache".

Bumping the cache key fixes today's outage. It does not fix the shape of the bug, which is that a
*fail-closed check on restorable state* is a permanent outage unless the check has a recovery path.
The same trap is waiting for `/tmp/openaq` and `/tmp/cams` on the next requirement added to a store.

## Decision

**A store that cannot state its own terms is not a store to accumulate onto — so it is discarded and
the fetch starts fresh. Terms that *disagree* are still refused.**

`swelter fetch --accumulate` now distinguishes two cases that were one:

- **Absent provenance** — observations exist, `source-metadata.json` does not. The store is
  unattributable. It is discarded, `--accumulate` proceeds as a fresh fetch for that run, and the
  reason is printed to stderr so a workflow log shows what happened rather than a silent reset. The
  new run writes its own `source-metadata.json`, so the condition clears itself and cannot recur.
- **Disagreeing provenance** — `source-metadata.json` exists and names a different source, license,
  URL, or attribution than this fetch. That is still a hard refusal, unchanged. Mixing two sources'
  terms in one store, or rewriting recorded terms, is a rights error a fresh fetch would not fix; it
  needs an operator.

Discarding is not a weakening of the check. The alternative to discarding was never "publish the
unattributable readings" — it was "publish nothing from this source, forever". Discarding publishes
exactly the readings this run fetched under exactly the terms this run recorded, which is the
strictest of the three outcomes and identical to what a cache miss already produces.

Two details follow from it:

- An OpenAQ store's per-location license ledger is discarded with the observations it covers. Merging
  the old ledger forward would carry rights evidence for readings this run just dropped.
- The discard goes through the same rollback journal as every other fetch mutation, so a fetch that
  fails after the decision restores the prior bytes rather than leaving an emptied store.

The Pages cache key moves to `swelter-fetch-store-scope-v3-` in the same change, with its
`restore-keys` prefix. That clears the currently-stuck `/tmp/sc` store on the next run instead of
waiting for the first fetch to discard it, and it follows the in-file precedent set when `v2`
replaced `v1` for the California boundary change. The key bump is the remedy for today; the discard
is the remedy for the class.

## Consequences

`/sensors/` can publish Sensor.Community readings again. It will show them when the upstream feed
answers and page 1's artifact when it does not — which is the route's documented behaviour, and was
never reachable while the store refused to open.

Verified end to end on 2026-08-19 by reproducing the exact condition: a real `fetch --source
sensor-community --accumulate` was run into a fresh store, its `source-metadata.json` was deleted to
age it back past the requirement, and the same command was run again. Before this change that second
run refused. It now prints the discard reason, exits 0, reports `accumulated 1636 new of 1636 total`
— proving the old rows were dropped rather than added to — and writes a new `source-metadata.json`,
so the condition cannot recur on the following run.

Costs and accepted trade-offs:

- **Accumulated history in an unattributable store is lost, not recovered.** A store that predates a
  provenance requirement loses its readings the first time this path runs. That is the right
  direction to lose in: those readings could not have been published under nameable terms anyway,
  and ADR 0013's accumulation is an evictable Actions cache, explicitly not an archive. The citable
  archive is `swelter snapshot`, which carries its terms with it.
- **The network membership document is not discarded with the store.** `--accumulate` merges the
  previous `network.yaml`'s nodes into today's discovery before provenance is checked (EXP-01:
  "nodes that come and go"), so a node that was only in the discarded store keeps its config entry
  and is published as an explicit no-current-reading record rather than vanishing (ADR 0036). That
  document carries node ids, labels and public coordinates — no observations and no license — so it
  raises no rights question, and the published result is honest: the node exists and is not
  reporting.
- **A silent-looking reset is possible for an operator who does not read stderr.** Mitigated by
  making the message say the store was discarded and why. It is not raised as an error because it is
  not one: the fetch succeeded and published attributable data.
- **A green run can still hide a dark route.** This change removes one cause, not the general
  condition — the workflow treats "this source fell back" as success by design (ADR 0034 draws the
  line between a refused fetch and an empty area). Making a persistently-dark route visible without
  making a transient upstream outage fail the deploy is separate work, tracked in
  [issue #180](https://github.com/ChelseaKR/swelter/issues/180).
- **The `--accumulate` contract is now weaker in one direction and unchanged in the other.** A caller
  can no longer assume the command fails when the store has no metadata; it can still assume the
  command fails when the store's metadata contradicts the fetch.

Executable evidence:

- `tests/test_cli_flows.py::test_accumulate_discards_a_store_that_cannot_state_its_terms`
- `tests/test_cli_flows.py::test_a_discarded_openaq_store_does_not_carry_its_license_ledger_forward`
- `tests/test_cli_flows.py::test_fetch_accumulate_rejects_cross_source_without_mutation` (the
  disagreement half, unchanged by this ADR)

The acceptance contract is maintained under F-16 in
[`../ACCEPTANCE-TEST-MAP.md`](../ACCEPTANCE-TEST-MAP.md).
