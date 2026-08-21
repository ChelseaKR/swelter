# ADR 0045: The published export is windowed; the accumulating store behind it is not

- Status: Accepted
- Date: 2026-08-21
- Deciders: Chelsea Kelly-Reif

## Context

ADR 0013/EXP-01 made `swelter fetch --accumulate` keep the store across runs instead of wiping it,
specifically so the dashboard's time slider has weeks of real history to slide over, not one day's
snapshot. That decision is unchanged and unchallenged here.

But `swelter publish` bakes the *entire* accumulated store into `export.csv` on every deploy, and the
store has no retention bound of its own — by design, per ADR 0013. Measured on the live artifact,
2026-08-19: `export.csv` was 314,470,584 bytes and growing roughly 15 MB/day (#181). Straight-lined,
the published site — which also carries `surface-7d.json`, `surface-24h.json`, and the smaller
artifacts — crosses the GitHub Pages 1 GB site limit in about a month, after which the whole map
stops deploying. Nothing in the site itself ever shows more than 7 days of history: the dashboard's
deepest view is `surface-7d.json`, a trailing window over the same store. A published `export.csv`
that outgrows every view the site offers is bytes served to no reader's benefit, purely because the
export path takes the whole store rather than what the site shows.

The alternative structural options (per-day shards, a columnar record shape, omitting null-valued
keys) each cut bytes-per-reading, but none of them bound the *count* of readings published, so the
same unbounded-growth problem returns on a longer timeline. They stay open as possible follow-ups
(filed with #181) and are not in conflict with this decision — they would compose with a window, not
replace one.

## Decision

**The store keeps accumulating without a bound (ADR 0013 stands). The published `export.csv` does
not.** `swelter publish` now windows `export.csv` to the same trailing span `surface-7d.json` already
uses — the most recent 24×7 distinct hourly timestamps present in the store, not a literal
now-minus-N-days cutoff, so a sparse or gappy feed still gets a full window's worth of readings
rather than an arbitrarily shorter one. This is the same windowing `_write_web_surface_slice` already
implements for the surface JSON, applied to the CSV export for the first time, using a single named
constant (`_EXPORT_WINDOW_HOURS`) so the two artifacts cannot drift out of sync with each other by
accident.

This draws the boundary the store/export layers were missing: **the accumulating store is
responsible for history; a static deploy is responsible for what it currently shows.** Anyone who
needs the complete, unbounded archive already has a citable path to it that this change does not
touch — `swelter snapshot` freezes the full store (raw observations, corrections, a MANIFEST.json
with per-file SHA-256, and a CITATION.cff/CITATION.txt pair) as a local, versioned release. The live,
dynamic `/export.csv` route (`swelter serve`, `swelter demo --serve`) is also untouched: it still
serves the complete store on demand, filterable by `since`/`until`/`node`/`parameter`, because that
route reads the store directly rather than baking a static file that has to sit on a size-limited
host indefinitely.

## Consequences

- `export.csv` in a static Pages deploy now has a ceiling determined by the network's cell/parameter
  count and 168 hourly buckets, not by how long the deploy has been running. Measured against the
  demo dataset (more than a week of hourly buckets), the windowed export is a strict, non-empty
  subset of the full store's export — the oldest reading in the store is provably absent from a
  fresh publish's `export.csv` (`test_publish_export_is_windowed_like_surface_7d`).
- `surface-7d.json` remains ~103 MB post-compaction (ADR "a dead probe reads zero, not dry" /
  #181's compact-JSON mitigation) and is still the single largest published artifact. This decision
  does not shrink it further; it stops the *other* large artifact from being strictly worse and
  growing without bound.
- A reader who downloaded `export.csv` from an old deploy and expects the same URL to always answer
  with the complete history will not find it there going forward. `docs/api.md` now says so
  explicitly, and points at `swelter snapshot` for the complete archive.
- If the site's own deepest view ever grows past 7 days (a decision this ADR does not make), the
  export window should grow with it via the shared `_EXPORT_WINDOW_HOURS` constant — the two are
  now deliberately coupled so a future change to one does not silently leave the other stale.
- Per-day shards, a columnar record shape, and omitting null-valued keys remain undecided follow-ups
  for shrinking bytes-per-reading; none of them is blocked or foreclosed by this decision.
