# ADR 0011: Add a curated, provenance-bearing cooling-center overlay with accessible list parity

Date: 2026-06-29. Status: accepted.

## Decision

Pair the heat/AQI surface with a toggleable map overlay of **cooling centers** — public places to
cool down (libraries, community and senior centers, cooled public buildings, shaded public space) —
so the map answers "where do I go", not only "how bad is it".

- The dataset is a curated GeoJSON FeatureCollection (`data/cooling_centers.geojson`) with explicit
  provenance: a set-level `license`, `attribution`, `source`, and `last_verified`, plus a `source`
  and `last_verified` on every feature. `swelter.cooling_centers` loads and **validates** it: every
  feature needs a name and an in-range Point coordinate, and properties are held to a documented
  public-field allowlist, so a future edit cannot smuggle a private phone, a contact name, or a
  personal note onto the map.
- It is served at `/api/cooling-centers.geojson` and baked beside the dashboard by `swelter demo` /
  `swelter fetch`. The dataset is **not** part of the CC0 observation stream — it is separately
  licensed civic data with its own metadata.
- The dashboard renders a **Cooling centers** section whose list is the accessible equivalent (name,
  type, hours, wheelchair access, air-conditioning, distance to the selected location, and the source
  line) — always present when the section is shown. A toggle button layers a distinct snowflake glyph
  per center over the map; the glyph is a shape, not a color, and is `aria-hidden` because the list,
  not the marker, is the canonical text. This keeps the README's "the map is never the only way in"
  and "status is never color-only" promises intact.

## Why

On a dangerous-heat day the highest-value next click after "it is dangerous here" is "the nearest
cool place I can get to". Cooling-center lists are exactly the kind of public civic data that belongs
beside the readings, and overlaying them turns a diagnostic into an action — serving residents
directly and giving health departments and mutual-aid groups a shared map. The data is public-facility
information (the addresses are public buildings, not residences), so it sits cleanly inside the
privacy posture as long as the schema is held to an allowlist, which the loader enforces.

The committed dataset is an **illustrative sample** placed within the synthetic demo network's
footprint — it is labelled as such in its metadata and is explicitly not a real facility list. A real
deployment replaces it with the jurisdiction's published cooling-center data (a county OES / 211 list
or a city open-data portal) under that source's license, keeping the `last_verified` discipline the
repo applies to every external-fact artifact.

## Known weakness / Consequences

Cooling-center data goes stale fast: hours change, sites open only during declared heat emergencies,
and a wrong "open" is worse than no entry. The dataset carries `last_verified` per feature and a
documented refresh path, but swelter cannot keep a third party's list current — that is the hosting
collective's ongoing job, and the demo dataset must never be mistaken for live truth (its metadata
says so). The overlay adds surface area to keep green (a loader, a validator, an API route, the map
layer, and the parity list) and a second non-CC0 data license to track. The map glyph can crowd a
dense network; it is drawn only when toggled on, and the list remains the source of record. Distances
are straight-line (haversine), not walking or transit time, so "nearest" is approximate.

Last verified: 2026-06-29. Recheck cadence: review the committed sample and the field allowlist
whenever the dashboard's privacy posture or the cooling-center schema changes; a real deployment
rechecks its own dataset on its own cadence.
