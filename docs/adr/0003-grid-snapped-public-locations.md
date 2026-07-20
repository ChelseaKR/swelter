# ADR 0003: Publish grid-snapped locations by default; precise coordinates are opt-in

- Status: Accepted
- Date: 2026-06-16
- Deciders: Chelsea Kelly-Reif

## Context

This is privacy by construction, one of the project's hard rules: hosting a
sensor on your roof or balcony must not reveal where you live. Making the coarse
grid the default and the precise coordinate the explicit opt-in means the safe
behaviour is the one you get without thinking about it, and disclosing an exact
location is a deliberate, reviewable act by the host who owns that decision.
Routing every map, export, and API response through `public_location()` means
there is a single place to audit and no path that can leak a raw coordinate by
accident. ~150 m is coarse enough to obscure a specific dwelling while still
being useful for heat-island and AQI surfaces, which are neighbourhood-scale
phenomena, not doorstep-scale. We rejected publishing exact coordinates with an
opt-out (the unsafe default leaks until someone notices) and dropping coordinates
entirely (the surface needs position to be a surface).

## Decision

A node's published coordinate is snapped to the centre of a coarse grid cell
unless the host explicitly opts into a precise location. `config.snap_to_grid()`
maps a `(lat, lon)` to its `grid_resolution_m`-sided cell centre (default
~150 m; longitude cell width widens with latitude so cells stay roughly square),
and `NodeConfig.public_location()` is the *only* coordinate the rest of the
system is allowed to read: it returns `None` when the host has not placed the
node, the exact coordinate only when `location: precise`, and otherwise the
snapped cell centre. Every downstream consumer goes through this seam —
`NetworkConfig.public_locations()`, `aggregate` (which snaps to published grid
cells), the SensorThings `Things` response in `api.py` (which labels each block
"published cell" and reports `location_precision`), and the dashboard. Precision
is a per-node config field in `network.yaml`, reviewed in a diff.

## Consequences

Grid snapping reduces spatial resolution: two nearby nodes can land in the same
published cell, and the surface cannot resolve gradients finer than the grid.
Snapping is a deliberate, one-way loss of precision in what is published — the
exact coordinate still lives in `network.yaml`, so privacy depends on that file
not being public and on hosts who opt into `precise` understanding what they are
disclosing. A very coarse grid in a sparse network can leave a single node alone
in a cell, which narrows where it could be; this is mitigated by keeping the
default at neighbourhood scale, not by the snapping alone.
