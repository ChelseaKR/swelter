# ADR 0020: Promote the Pages bash choreography into a tested `swelter publish` command

Date: 2026-07-03. Status: accepted.

## Decision

`swelter publish` is now a first-class CLI subcommand that bakes a complete, fully static site
from an existing store — the same artifact `.github/workflows/pages.yml` previously assembled with
~40 lines of untested bash (`cp`, `find … -exec cp`, `rm`, and stdout redirection into `export.csv`).

- `cli.cmd_publish` opens `--store`, loads `--config`, rebuilds the surface via `aggregate` (the
  same path `fetch`/`demo` use), and writes into `--web`:
  - the existing bakers — `sample-surface.json`, `sample-health.json`, `alerts.json`/`alerts.xml`,
    `cooling-centers.geojson` (only when a dataset is present, same as the live pipeline commands);
  - two new per-window slices, `surface-24h.json` and `surface-7d.json`, via a new
    `_write_web_surface_slice(web_dir, surface, hours, filename)` helper. The window is the newest
    *N* hourly buckets, matching `server.py`'s `/api/surface.json?hours=N` exactly (`sorted(...)
    [-hours:]`) — a static deploy's time-slider data has the same shape and windowing semantics as
    the live API, so the dashboard's client code does not need to special-case which one it's
    talking to;
  - `export.csv`, via `export.to_csv()` written directly to the artifact instead of a shell
    redirect;
  - `DATA-LICENSE` and `LICENSE`, copied from the repo root (resolved from `cli.py`'s own path, not
    the process cwd) when the command runs from a checkout — an installed package simply has
    nothing to copy and skips it, the same optional-source pattern `_write_web_cooling_centers`
    already uses for its dataset;
  - `publish-manifest.json`: every file `publish` wrote, with a `sha256` and byte size per file plus
    the store's `interval_s` and the latest `data_hour`, so a deploy can be checked against the
    manifest instead of trusted blind. The manifest never hashes itself (no chicken-and-egg).
- `pages.yml` now runs `swelter fetch … && swelter publish --store … --web …` for both the `/` and
  `/sensors/` artifacts. The bash choreography that remains is exactly what `publish` cannot do —
  copying the *static* site shell (`index.html`, `app.js`, `styles.css`, `i18n/`) into `web/sensors/`
  as scaffolding/fallback before the sensor-specific fetch — not data assembly, which is now a single
  tested call.
- Coverage: `tests/test_publish.py` drives `cmd_publish` through `cli.main` against a real demo
  store — asserts every expected file lands, that `surface-24h.json`'s buckets are a subset of
  `surface-7d.json`'s (and both subsets of the full surface), that the manifest enumerates exactly
  the files written (byte-identical hashes) and reproduces byte-for-byte on a second run against an
  unchanged store, and that `export.csv` matches `export.to_csv()` exactly (including the CSV
  module's `\r\n` line terminator, which round-trips only if nothing does universal-newline
  translation on the way back in).

## Why

The Pages workflow was the one place swelter's actual publish logic — which files a static deploy
needs, in what shape, sliced how — lived only in YAML: untested, unable to be driven by
`swelter demo`/`--help`, and copy-pasted between the `/` and `/sensors/` blocks (the license copy,
the CSV redirect, the `find … -exec cp` static-asset bootstrap). A community running its own
instance outside GitHub Actions had no equivalent one-liner to reproduce it — they either scripted
their own `cp`/`export` sequence or ran `swelter serve` and gave up the "just a folder on any static
host" story ADR 0005 and 0006 already promise. Promoting it into `cli.cmd_publish` makes "fully
static instance" a documented, `--help`-discoverable, unit-tested command, and deletes the one
place the static and live surfaces could silently drift out of schema sync (the 24h/7d slice window
is now asserted against `server.py`'s own filtering, not eyeballed).

It also opens the cheaper infrastructure path the item exists for: `infra/cdk`'s S3+CloudFront stack
today pairs the static bucket with a scale-to-zero Lambda (`handler.py`) wrapping `swelter.server`
purely to answer read-only GET routes. For an operator who does not need live ingestion between
`publish` runs — a daily or hourly cron is enough currency for a heat/AQI surface — `swelter publish
--web dist/ && aws s3 sync dist/ s3://bucket/` (or `rsync`, or a Pages-style Actions job) serves the
whole read path with **no server process at all**, retiring the Lambda/`handler.py` drift seam for
that deployment shape entirely. This ADR does not change `infra/cdk` — the Lambda API stays the
default for instances that want live queries between publishes — but the S3/CloudFront-only variant
is now a real, tested command away rather than a bespoke script a collective would have to write.

## Known weakness / Consequences

`publish` re-aggregates the whole store on every run (same cost `fetch`/`demo` already pay) — fine
for a network sized like the demo or the CA/Stuttuttgart fetches, but a very large or very
long-lived store would want an incremental path this ADR does not build (the demo and the CA/
Stuttgart fetches this repo ships are well within that cost). The 24h/7d windows count
*hourly buckets*, not wall-clock hours; a store with gaps (a node offline for a day) yields a
"24h" slice that spans more calendar time than 24 hours, exactly mirroring the live API's existing
behavior rather than fixing it — a real fix is a separate item, not smuggled into this promotion.
License bundling is best-effort: it silently omits `DATA-LICENSE`/`LICENSE` for an installed
(non-checkout) `swelter`, so an operator packaging swelter as a wheel and running `publish` from
outside a clone must supply those files another way — the command does not fail loudly on this, by
design (an absent optional file is not an error), but it is worth an operator's attention in
`docs/ADD-YOUR-NEIGHBORHOOD.md`. The S3/CloudFront serve-the-artifact variant described above is
documented, not built: `infra/cdk` still provisions the Lambda API by default, and a config flag to
omit it is future work.

Last verified: 2026-07-03. Recheck cadence: revisit if `server.py`'s `/api/surface.json?hours=N`
filtering semantics change (the static slice helper must keep matching it), or if `infra/cdk` grows
the static-only deployment mode described above.
