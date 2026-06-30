# ADR 0009: Add a compound heat-and-air exposure surface as the flagship differentiating feature

Date: 2026-06-18. Status: accepted.

## Decision

Build a single neighborhood **exposure surface** that combines the calibrated heat index and the
PM2.5 AQI into one published layer, rather than leaving heat and air as two surfaces a reader must
cross-reference. The exposure layer keeps every existing discipline intact: it is computed per
published grid cell from calibrated, QC-clean values where they exist; it inherits the cell's
`provisional` flag and carries forward the component uncertainties; it never blends a calibrated and
a raw value as if they were the same kind of number; and it is exposed through the same routes as the
current surface (`/api/surface.json`, the SensorThings subset, CSV/JSON export) and rendered as a
fourth measurement option across the map, table, and list — three equal views, no color-alone
severity. The exact combination function (a documented index versus a two-axis "hot AND smoky" flag)
is left to the implementing PR, which must publish the method and its limits the way calibration
already does.

As built, the layer is a two-axis flag rather than a blended number: the level is the higher of the
heat tier (NWS heat-index categories) and the air tier (PM2.5 AQI category) on a shared 0–4 ordinal,
with a separate `compound` flag when both are at least mid-tier. The combination lives in
`models.exposure_level` / `models.heat_index_category` (unit-tested); `aggregate` derives an
`exposure` cell per cell/hour only where both halves exist and marks it provisional if either is;
`api.md` documents the surface fields; and the dashboard adds it as a measurement option across the
map, table, and list, with severity carried in the level name, never color alone.

## Why

Heat and air quality are read together in practice — CDC pairs HeatRisk with the AQI for clinicians —
and the joint exposure is where the harm concentrates: compound extreme-heat-and-PM2.5 events carry
materially higher mortality than either hazard alone. The scan found no incumbent that publishes a
combined neighborhood surface: PurpleAir and OpenAQ carry temperature but not a calibrated heat
surface, the AirNow Fire and Smoke Map is PM/smoke only, and CAPA Heat Watch is heat only. swelter
already measures, calibrates, and aggregates both halves, so the compound surface is the highest-
leverage thing it can build with what it has — it converts "we happen to carry both parameters,"
which is not unique, into "we publish the combined exposure that matters," which was not found
elsewhere (ADR 0008). It serves three of the four target audiences at once: residents deciding
whether to be outside, health departments targeting interventions, and journalists telling the
inequity story.

## Known weakness / Consequences

This is the project's least-proven bet. The market for a combined index is an assumption, not an
observation, and a bespoke index risks implying a precision the inputs do not support — the same trap
the calibration work avoids by publishing uncertainty, which is why the combined surface must do the
same and may be safer as a two-axis flag than a single blended number. Combining a heat index (NWS
Rothfusz) and an EPA AQI mixes two unlike scales with different health bases, so the method writeup
has to be explicit that the layer is decision-support, not a validated health index, and never
regulatory-grade. It adds a measurement option, surface records, and tests across `aggregate`, `api`,
the dashboard, and the a11y gate; that is real surface area to keep green. And it must not become a
back door around the hard rules: no new coordinate path that skips `public_location()`, and the
combined cell stays provisional whenever either component is.

Last verified: 2026-06-18. Recheck cadence: revisit whenever the EPA AQI breakpoints, the NWS
heat-index bands, or the heat-index formula in `models.py` change.
