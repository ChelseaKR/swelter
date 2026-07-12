# ADR 0013: `swelter fetch --accumulate` persists the demo store via a GitHub Actions cache

Date: 2026-07-08. Status: accepted.

## Decision

`swelter fetch` wiped its store (`observations.db`) at the start of every run — "a fresh snapshot
each fetch" — so the live Pages demo (`.github/workflows/pages.yml`) never held more than one
day's readings and the dashboard's time slider had nothing to slide over. `fetch` gains an
`--accumulate` flag that keeps the existing store instead of unlinking it:

- With `--accumulate`, `cmd_fetch` skips the unlink and opens the store as-is; `SqliteStore.write()`
  is already `INSERT OR IGNORE` on the `(node_id, timestamp, parameter, calibration)` key (ADR
  0001), so re-fetching an overlapping window is idempotent, not duplicated — the store key was
  built for exactly this and was previously unused for it.
- The written `network.yaml` is **merged**, not replaced: node entries seen in today's fetch
  overwrite the prior entry (refreshed label/location), and a node that dropped out of today's
  discovery (OpenAQ's live site list changes day to day) keeps its prior entry, because `aggregate`
  resolves a stored observation's node through the config — drop the node from the config and its
  history silently stops resolving to a map cell even though the raw rows are still in the store.
  `_merge_network_doc()` does this union.
- CI persistence uses `actions/cache`, keyed on the calendar day, with `restore-keys` falling back
  to the most recent cache so a cold cache (first run, or one that expired from seven days of
  inactivity) degrades to today's fetch rather than failing. This was chosen over a dedicated data
  branch: a data branch keeps history forever in git (real repo-size growth with every daily commit,
  and the exact growth problem FIX-09 is scoped to solve) where a cache entry is disposable
  infrastructure with a size cap GitHub already enforces, and it needs no extra push permission on
  the Pages workflow (`contents: read` stays sufficient for the fetch step).

## Why

The demo's whole point is showing the compound-exposure surface (ADR 0009) *over time* — a heat
island is a multi-day pattern, and a time slider with one populated hour proves nothing. The
`(node_id, timestamp, parameter, calibration)` store key and `INSERT OR IGNORE` write path already
supported an accumulating archive; only the CLI was throwing the accumulated value away every run.
Flag-gating it (default stays "wipe") keeps every existing local/CI invocation and test byte-for-byte
unchanged, and keeps a one-off `swelter fetch` (a contributor trying the CLI once) behaving the way
its docstring always promised: a fresh snapshot.

## Known weakness / Consequences

This is the flag plus its CI wiring — it is not FIX-09 (store growth: rollups, retention, monthly
archive files), which EXP-01's own ideation entry names as the real growth answer. A daily cache
that accumulates unboundedly will eventually hit the cache's size limit; until FIX-09 lands, the
practical ceiling is "however many weeks fit before GitHub evicts the cache," which is adequate for
proving the longitudinal story but is not a retention policy. `actions/cache` is also
best-effort — GitHub can evict any entry under storage pressure regardless of the `restore-keys`
fallback — so the Pages workflow must keep working (falling back to a fresh fetch) on a cache miss,
which the layered `openaq → openmeteo → committed demo` fallback already guarantees independent of
this change. Source terms-of-use for retaining and republishing third-party readings over weeks
(rather than a same-day snapshot) is a real-data gate this ADR does not itself clear — see FIX-05
for the honest-licensing work that governs what the accumulated export may say.

Last verified: 2026-07-08. Recheck cadence: when FIX-09 lands (retention policy supersedes "cache
until it's evicted"), or if the Pages workflow's cache hit rate/size becomes a problem in practice.
