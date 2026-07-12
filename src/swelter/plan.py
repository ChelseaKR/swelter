"""Siting what-if: what a candidate node does to coverage, redundancy, and reference distance —
*before* hardware moves (EXP-08, ``docs/ideation/03-expansions.md``).

Co-location time is the scarce resource a collective governs (audit B5); this module is a pure,
reproducible instrument for that decision, not a recommender. ``simulate_add_node`` takes a
:class:`~swelter.config.NetworkConfig` and a candidate coordinate and reports descriptive signals
only — cells, counts, distances — never an "optimal placement" score (the same boundary
``qc.coverage_equity`` already draws). Everything here is a pure function over the config the
collective already reviewed; it collects no new data and calls no network.

The candidate site is always published coarse, snapped through :func:`swelter.config.snap_to_grid`
exactly as a real node's ``location: coarse`` would be — a hypothetical siting decision gets the
same privacy boundary as a real one (hard rule 2). Reference-monitor distance is only reported for
monitors that carry an optional ``lat``/``lon`` in ``network.yaml``; regulatory station coordinates
are already public record, so no grid-snap applies to them.
"""

from __future__ import annotations

import math
from typing import Any

from .config import NetworkConfig, snap_to_grid

#: Mean Earth radius (m), the standard haversine constant — plenty accurate at neighbourhood scale.
_EARTH_RADIUS_M = 6_371_000.0


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres between two lat/lon points (no external dependency)."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * _EARTH_RADIUS_M * math.asin(math.sqrt(a))


def _cell_id(cell: tuple[float, float]) -> str:
    return f"{cell[0]:.6f},{cell[1]:.6f}"


def simulate_add_node(
    config: NetworkConfig, lat: float, lon: float, node_id: str = "candidate"
) -> dict[str, Any]:
    """Descriptive what-if: what publishing a node at ``(lat, lon)`` would do to coverage.

    Returns a dict:

    * ``node_id`` — the candidate's label, for display only.
    * ``candidate_cell`` — the published cell (``{"lat", "lon"}``) the candidate would land in,
      via :func:`snap_to_grid` (coarse placement — the privacy boundary applies to a hypothetical
      node exactly as it would to a real one).
    * ``existing_cells`` — sorted list of every cell already published today, each placed node's
      coordinate run through :func:`snap_to_grid` so a precise-opt-in node and a coarse one land
      in the same grid space as the candidate (snapping an already-snapped, already-rounded
      coordinate a second time is not exactly idempotent at float precision, so this snaps once
      from each node's own configured coordinate rather than re-snapping ``public_location()``'s
      output).
    * ``new_cell`` — ``True`` when the candidate cell is not already in ``existing_cells`` (the
      coverage delta this siting choice would add).
    * ``redundancy`` — how many already-placed nodes fall in the *same* cell as the candidate
      (a co-location/overlap signal, not a verdict on whether that's good or bad).
    * ``nearest_node`` — ``{"node_id", "distance_m"}`` of the closest already-placed node, or
      ``None`` when the network has no placed nodes yet.
    * ``nearest_reference`` — ``{"monitor_id", "distance_m"}`` of the closest reference monitor
      that carries a coordinate, or ``None``.
    * ``reference_note`` — set when the network has reference monitors but none carry a
      coordinate, so a caller knows the ``None`` above means "not computable", not "none nearby".

    No score, no ranking, no "best of these three" — that judgment stays with the collective
    (EXP-08 risk note).
    """
    candidate_cell = snap_to_grid(lat, lon, config.grid_resolution_m)
    existing_locations = config.public_locations()  # node_id -> published (lat, lon)
    placed_cells = {
        node.node_id: snap_to_grid(node.lat, node.lon, config.grid_resolution_m)
        for node in config.nodes
        if node.lat is not None and node.lon is not None
    }
    existing_cells = set(placed_cells.values())
    redundancy = sum(1 for cell in placed_cells.values() if cell == candidate_cell)

    nearest_node: dict[str, Any] | None = None
    for other_id, loc in existing_locations.items():
        distance = haversine_m(lat, lon, loc[0], loc[1])
        if nearest_node is None or distance < nearest_node["distance_m"]:
            nearest_node = {"node_id": other_id, "distance_m": round(distance, 1)}

    located_refs = [m for m in config.reference_monitors if m.lat is not None and m.lon is not None]
    nearest_reference: dict[str, Any] | None = None
    for monitor in located_refs:
        m_lat, m_lon = monitor.lat, monitor.lon
        assert m_lat is not None and m_lon is not None  # noqa: S101 (located_refs filter)
        distance = haversine_m(lat, lon, m_lat, m_lon)
        if nearest_reference is None or distance < nearest_reference["distance_m"]:
            nearest_reference = {"monitor_id": monitor.monitor_id, "distance_m": round(distance, 1)}
    reference_note = (
        "reference monitors in this config carry no lat/lon; add optional lat/lon to "
        "reference_monitors entries in network.yaml to compute distance-to-reference"
        if config.reference_monitors and not located_refs
        else None
    )

    return {
        "node_id": node_id,
        "candidate_cell": {"lat": candidate_cell[0], "lon": candidate_cell[1]},
        "existing_cells": sorted(_cell_id(cell) for cell in existing_cells),
        "new_cell": candidate_cell not in existing_cells,
        "redundancy": redundancy,
        "nearest_node": nearest_node,
        "nearest_reference": nearest_reference,
        "reference_note": reference_note,
    }
