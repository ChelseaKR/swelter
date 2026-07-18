# ADR 0015: Validate `network.yaml` loudly, and add a `swelter doctor` gate

- Status: Accepted
- Date: 2026-07-03
- Deciders: Chelsea Kelly-Reif

## Context

The unknown-`alert_thresholds`-key case is a silent safety failure in the exact file a
first-time community editor is told to hand-edit: the danger floor a host believes they set is not
the one in effect, and there is no signal anywhere that it didn't take. Duplicate/empty node ids
are a silent data-integrity failure with the same shape — two sensors reporting as one. Both are
easy first-time mistakes (a missed `_c` suffix, a copy-pasted node block with the id left
unchanged) and both are cheap to catch mechanically before they reach a live network. A dedicated
`doctor` subcommand gives that check a stable, scriptable exit code instead of a message a host has
to notice among the demo's other stderr chatter.

The design deliberately keeps two speeds: warnings are folded into every load (so a running
`serve`/`demo` still surfaces a bad `network.yaml` without crashing) and only `doctor` is the hard
gate. This mirrors the existing `label_concerns` precedent (PII-shaped labels warn, they do not
block) and avoids turning `swelter demo`/`swelter serve` into commands that refuse to boot on a
network some other host already runs with a since-fixed-elsewhere quirk.

## Decision

`network.yaml` is the one file a new community edits by hand (`docs/ADD-YOUR-NEIGHBORHOOD.md`,
Phase 4), and until now a mistake in it failed silently:

- `alerts._resolve_thresholds` merged only the `alert_thresholds` keys it recognized and dropped
  the rest without a word. A host who wrote `heat_index: 37` (instead of `heat_index_c`) believed
  they had lowered the network's danger floor; the default floor stayed in effect and nothing said
  so.
- `config.parse_config` accepted a duplicate or empty `node_id` and built a `NetworkConfig` from
  it anyway, merging what should be two distinct sensors into one cell identity downstream.
- An unknown top-level key, an out-of-range `lat`/`lon`, a stray `location:` value, or a
  `calibration_windows` entry pointing at a node or reference monitor that does not exist all
  parsed without comment.

This ADR adds a validation pass and a CLI gate, without changing what the pipeline actually does
with a config once it is loaded:

- `config.config_concerns(config, doc) -> (errors, warnings)` (`src/swelter/config.py`) checks the
  parsed `NetworkConfig` against the *raw* parsed YAML mapping (`doc`) — the raw doc is needed
  because `parse_config` already drops anything it does not recognize before a check could see it.
  `config.load_config_doc(path)` returns both; `config.load_config(path)` (unchanged signature)
  is `load_config_doc(path)[0]` for every caller that only wants the typed config.
  - **Errors** (a mistake that would silently corrupt data or a safety knob): an unknown
    top-level key, a duplicate or empty `node_id`, an unknown `alert_thresholds` key (checked
    against `alerts.DEFAULT_THRESHOLDS`, with a "did you mean" hint — e.g. `heat_index` →
    `heat_index_c`), an out-of-range `lat`/`lon`.
  - **Warnings** (swelter already fails safe around these, but a host probably did not intend
    them): a `location:` value other than `coarse`/`precise` — this **keeps failing safe to
    `coarse`**, unchanged; a `calibration_windows` entry naming a `node_id` or `reference` that is
    not registered.
- `swelter doctor --config network.yaml` (`src/swelter/cli.py`) prints the full report (reusing
  `config_concerns` and the existing `label_concerns` PII heuristic) and **exits nonzero iff there
  is at least one error**. It is the thing to run before committing a `network.yaml` change, and
  the thing CI or a pre-merge hook can run on a PR.
- `serve`, `demo`, `fetch`, and every other subcommand that already loads a config print the same
  warnings and errors on load (via the shared `_load_config` helper) but **do not refuse to run**
  — a typo should not take down an already-deployed network the way a hard crash would. `doctor`
  is the strict gate; the running subcommands stay loud but lenient, the same posture
  `label_concerns` already had.
- `alerts._resolve_thresholds` is unchanged in behavior: it still merges only recognized keys and
  silently ignores the rest *at that layer*, because a pipeline run must never crash mid-build on
  a config typo. What changed is that the typo no longer goes unnoticed anywhere — `doctor` and
  `config_concerns` catch it at load time, before a build ever reaches `_resolve_thresholds`.

## Consequences

`alert_thresholds` validation is only as good as `alerts.DEFAULT_THRESHOLDS` staying the single
source of truth for recognized keys — a new threshold key must be added there for `doctor` to
recognize it, which is already true of `_resolve_thresholds` today so this adds no new coupling.
The out-of-range lat/lon check is a coarse sanity bound (`-90..90`/`-180..180`), not a check that
the point is actually inside the network's service area — a valid-but-wrong coordinate (e.g. a
digit transposed within range) still passes. The "did you mean" hint uses a simple string-distance
match (`difflib.get_close_matches`) and can occasionally suggest nothing or the wrong key; the
message still names the exact offending key and the full list of recognized ones, so a host is
never left guessing. `doctor` validates one file; it does not check that `network.yaml` and the
store/registry it is paired with agree (a separate, pre-existing rebuild/consistency concern this
ADR does not touch).

Last verified: 2026-07-03. Recheck cadence: revisit whenever `alert_thresholds` keys, the
top-level `network.yaml` schema, or the `coarse`/`precise` location vocabulary change.
