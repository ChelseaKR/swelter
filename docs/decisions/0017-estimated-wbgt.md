# ADR 0017: Ship an estimated WBGT parameter, without guidance bands

Date: 2026-07-02. Status: accepted.

## Decision

Add `wbgt_c` to the `PARAMETERS` registry as a first-class, estimated wet-bulb globe temperature —
the metric occupational-heat guidance (OSHA/NIOSH-style outdoor-work standards) actually uses,
distinct from the resident-facing NWS heat index already in `heat_index_c`. The estimate is a
documented, citable **shade approximation from air temperature and relative humidity only**:

1. Natural wet-bulb temperature via Stull, R. (2011), "Wet-Bulb Temperature from Relative Humidity
   and Air Temperature," *Journal of Applied Meteorology and Climatology* 50(11): 2267-2269 — a
   closed-form regression, no iterative psychrometric solve required.
2. Combined into the two-term **shade** WBGT form from ISO 7243 (`WBGT = 0.7*Tw + 0.3*Td`), which
   omits the black-globe (solar-radiation) term entirely rather than approximating it.

This ships end to end: `models.wbgt_c()` (mirrored in `scripts/gen_demo_data.py` for the synthetic
demo field, and derived alongside `heat_index_c` in every source adapter that computes a heat index
from `temp_c` + `humidity_pct`: `sources/openaq.py`, `sources/sensor_community.py`,
`sources/openmeteo.py`), `qc._SPIKE_THRESHOLD`, `aggregate.SURFACE_PARAMETERS`, the SensorThings
`ObservedProperties`/`Datastreams` (parameter-generic, no code change needed), CSV/JSON export
(parameter-generic), and the dashboard's map/table/list/legend, in English and Spanish, with the
word "estimated" **inseparable from the value** everywhere it is displayed (R5 — caveats travel
with the value, not just in a tooltip or a docs page).

**Explicitly deferred, by design, out of this change:** any heat-risk guidance band, threshold, or
occupational action-level scale for WBGT (analogous to the NWS `_HEAT_BANDS` on `heat_index_c`).
Publishing thresholds against a value with the documented error this estimate carries is a call
that needs an occupational-health/SME sign-off, not an engineering default — the same discipline
`docs/RESEARCH-ROADMAP.md`'s R1 pattern and audit A6 already hold heat-guidance copy to. Firmware
black-globe sensor support is a separate hardware decision (`docs/HARDWARE.md`), not part of this
software-estimation change.

## Why

The README's own hardware framing already promises "a wet-bulb-globe-style heat index," but before
this change only `heat_index_c` (NWS "feels-like") existed in `models.py` — there was no metric
speaking the language outdoor-work heat standards use. WBGT is the standard input to occupational
heat-stress guidance worldwide (ISO 7243, US OSHA/NIOSH), so adding it, honestly labeled, opens a
concrete new audience (outdoor-work crews and the organizations that watch out for them) that the
existing resident-facing heat index does not serve — adjacent to, not duplicating, the
CDC-HeatRisk-style resident guidance layer proposed separately (RESEARCH-ROADMAP E7). The
surface/table/list/API/export plumbing was already parameter-generic (one entry in
`aggregate.SURFACE_PARAMETERS`, one dashboard label set), so the estimation itself — with its
caveats — was the one piece of real, citable work needed to make the metric trustworthy rather than
decorative.

## Known weakness

An estimated WBGT computed from air temperature and humidity alone, with no black-globe radiometer
and no solar-radiation term, **reads cooler than the true outdoor WBGT in direct sun** — the whole
point of the black-globe term is to capture radiant heat load, and this estimate cannot. The Stull
(2011) wet-bulb regression itself is validated against psychrometric tables to within about ±1°C
over typical outdoor temperature/humidity ranges (per Stull's own reported RMSE), but that bound
covers only the wet-bulb term — it says nothing about the shade-vs-sun gap, which is the estimate's
larger and more consequential source of error and is undocumented in absolute terms here because it
is site-, sky-, and surface-dependent (a nearby paved lot in direct noon sun and a shaded canopy at
the same air temperature and humidity have materially different true WBGT, and this estimate cannot
tell them apart). This is precisely why no guidance band ships with this change: publishing an
action-level threshold against a value that can meaningfully understate heat stress in direct sun
would be worse than publishing no threshold at all, and deciding how (or whether) to communicate
that gap to an outdoor-work audience is exactly the SME call this ADR defers. Every caller-facing
label says "estimated WBGT," never bare "WBGT," so the gap travels with the number; the codebase
following this ADR must not silently drop that word.

`heat_index_c`'s established pattern — published raw/provisional, never fit against a co-location
reference — is followed here too: `wbgt_c` is a *derived* reading (it inherits its `temp_c`/
`humidity_pct` inputs' calibration state, or lack of one) not a directly-sensed quantity, so it is
not a candidate for the `calibrate.py` co-location fit and none is added.

Last verified: 2026-07-02. Recheck cadence: revisit if the Stull (2011) regression, the ISO 7243
shade-WBGT combination, or the decision to withhold guidance bands changes — and before any future
work adds black-globe firmware support, guidance-band copy, or a `wbgt_c` calibration path, all of
which should land as their own ADRs per the deferrals above.
