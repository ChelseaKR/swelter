# ADR 0031: Generalize the alert layer into versioned hazard packs, and ship a cold pack

- Status: Accepted
- Date: 2026-07-18
- Deciders: Chelsea Kelly-Reif

## Context

swelter's alert layer was heat-shaped in code, not just in intent. `alerts.DEFAULT_THRESHOLDS`
hard-coded three floors (PM2.5 AQI, heat index, exposure), and `alerts.build_feed` iterated a
hard-coded `_ALERTING_PARAMETERS` tuple. That is fine for July. But the same frontline block that
overheats in summer freezes in January and chokes in fire season, and a network that can only speak
"heat" goes silent for half the year — which, per `docs/POSITIONING.md`, is exactly the window in
which a volunteer-run network dies. The pipeline is already parameter-generic (QC, aggregation,
export, and interop all key off `models.PARAMETERS`), so the missing piece was never the plumbing;
it was that "what counts as danger" lived in code instead of in reviewable, cited data.

EXP-13 (`docs/ideation/03-expansions.md`) proposed a "hazard pack" abstraction to fix that. This ADR
lands the abstraction plus the first new pack (cold). Smoke-event mode, the other pack EXP-13
sketches, is deferred; it depends on corroboration/NowCast work and is out of scope here.

## Decision

Introduce a **hazard pack**: versioned data — like a calibration correction (ADR 0002) — that names
the parameters a network alerts on, the floor a reading crosses on each, and a public-source
citation for every floor. Packs live in `src/swelter/hazard_packs.py` as frozen dataclasses
(`Citation`, `HazardThreshold`, `HazardPack`); `HAZARD_PACK` selection is a `network.yaml` field,
never a fork.

1. **Heat is the default, and unchanged.** `HEAT_PACK` reproduces the original three floors exactly.
   `alerts.DEFAULT_THRESHOLDS` is now `HEAT_PACK.default_floors()`, `resolve_thresholds`/`build_feed`
   take an optional `pack` that defaults to heat, and `aggregate` unions in a pack's surface
   parameters (heat adds none already on the map). A config that names no `hazard_pack` therefore
   produces byte-for-byte identical output — the demo, its committed fixtures, and every existing
   test are untouched.

2. **A collective enables a pack by config alone.** `hazard_pack: cold` in `network.yaml` is the
   only change needed: `aggregate` reads it to roll up the pack's parameters, and the CLI/server
   pass `hazard_packs.resolve_pack(config.hazard_pack)` to `build_feed`. `swelter doctor` rejects an
   unknown pack id and validates `alert_thresholds` override keys against the *active* pack's floors
   (so a cold network is told `heat_index_c` is not one of its keys, and vice versa).

3. **The cold pack.** A new `wind_chill_c` parameter joins `models.PARAMETERS` (QC bounds −100..60
   °C, spike threshold 12 °C, crosswalk entry, SensorThings/export coverage). `models.wind_chill_c`
   is the documented NWS/Environment-Canada metric wind-chill index (2001 revision, `WCT = 13.12 +
   0.6215*T − 11.37*V^0.16 + 0.3965*T*V^0.16`, T in °C and V in km/h), honestly labelled: it is an
   **approximation of how cold exposed skin feels**, not a measured quantity, defined only for T ≤
   10 °C and wind > 4.8 km/h (it passes air temperature through outside that domain, the same
   convention `heat_index_c` uses). The cold pack alerts when a cell's wind chill falls **at or
   below −28.3 °C (−19 °F)** — the one frostbite-time boundary the NWS Wind Chill Chart states
   numerically ("exposed skin can freeze in 30 minutes"). Air quality is not seasonal, so the cold
   pack keeps the same EPA PM2.5 floor the heat pack uses.

4. **Danger has a direction.** Heat, air, and exposure cross *upward* (hotter/dirtier is worse);
   wind chill crosses *downward* (colder is worse). `alerts.crossing` encodes this per parameter, so
   the live feed and the historical `exposure_brief` count share one definition of a crossing and
   can never drift apart.

## Consequences

**Wind speed is not a swelter source parameter.** Unlike `heat_index_c` — which the fetch adapters
derive from `temp_c` + `humidity_pct` — nothing in the current source set supplies wind, so
`wind_chill_c` is *not* auto-derived in the fetch path. It enters as a value a node (or an operator
with a wind feed) reports directly; `models.wind_chill_c` is the reference implementation for that
producer. A wind-speed parameter and an adapter that derives wind chill are a clean follow-up.

**`wind_chill_c` is in `PARAMETERS` but not on the default map.** It is a first-class parameter
(QC, export, `ObservedProperties`, data dictionary — the demo's stream and property counts rise
accordingly, and `docs/api.md` is updated), but it is deliberately absent from
`aggregate.SURFACE_PARAMETERS`, so a heat network's map, table, list, and `sample-surface` contract
are unchanged. A cold network *does* aggregate a `wind_chill_c` cell; wiring the dashboard to label
and render it (with EN/ES + Grade-8 copy) is a follow-up, gated the same way any resident-facing
surface is. Because that dashboard copy is not shipped here, no `web/i18n` catalog or `web/app.js`
change is made in this ADR.

**Only one cold band is asserted, on purpose.** The NWS Wind Chill Chart's colder 10- and 5-minute
frostbite zones are not published as numeric wind-chill cutoffs, so `_WIND_CHILL_BANDS` asserts only
the one boundary the chart states in numbers. A graduated cold scale would need those values sourced
first — the same discipline ADR 0019 used to ship estimated WBGT without guidance bands.

**Sourced provenance, not personal safety advice.** Every floor and every pack's `guidance` entries
carry a source, detail, URL, and `last_verified` date, so the "why this number" travels with the
number (invariant 4). A severity name (`"Danger"`, `"Frostbite in 30 min"`) is the source's own
label for a documented band — never a swelter instruction to a resident. The alert feed's Spanish
wind-chill headline is machine-drafted and labelled as such, exactly like the existing surfaces
(`i18n_alerts`, issue #106).

No invariant is weakened: no person-shaped field is added; raw and calibrated stay distinct (a
`wind_chill_c` reading is raw/provisional unless calibrated, like any other parameter); and the
alert feed remains a published artifact with no subscriber list (ADR 0010).

Last verified: 2026-07-18. Recheck cadence: revisit when a new pack is added, when the NWS wind-chill
formula or its cited frostbite boundary changes, or before any work adds a wind-speed source
adapter, a graduated cold band scale, or resident-facing pack guidance copy — each of which should
land as its own ADR per the deferrals above.
