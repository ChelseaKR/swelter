"""Coordinate presentation for baked demonstration artifacts.

The recorded worked example remains a dense Sacramento calibration fixture. Its static root
preview uses public California place centroids so the statewide basemap is useful without claiming
that the synthetic readings describe those places. This module changes only an in-memory copy of
the network configuration used to bake web artifacts; it never rewrites the store or network.yaml.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from dataclasses import replace

from .config import LOCATION_PUBLIC_PLACE, NetworkConfig, is_builtin_demo_web_preview
from .sources._california_places import CALIFORNIA

Place = tuple[str, float, float]
_ASSIGNMENT_SALT = "swelter-statewide-preview-v1"
WEB_PREVIEW_NETWORK_NAME = "Swelter statewide synthetic preview"
WEB_PREVIEW_REFERENCE_LABEL = "Synthetic calibration reference"
_WEB_PREVIEW_REFERENCE_SOURCE = "Synthetic worked-example reference series"


def node_key(node_id: str) -> tuple[int, str]:
    """Sort generated node ids numerically while remaining deterministic for arbitrary ids."""
    match = re.search(r"(\d+)$", node_id)
    return (int(match.group(1)) if match else 10**9, node_id)


def _sampled_places(count: int) -> list[Place]:
    if count < 1 or count > len(CALIFORNIA):
        raise ValueError(f"statewide preview needs 1..{len(CALIFORNIA)} unique locations")
    if count == 1:
        return [CALIFORNIA[len(CALIFORNIA) // 2]]
    indices = [round(i * (len(CALIFORNIA) - 1) / (count - 1)) for i in range(count)]
    if len(set(indices)) != count:
        raise ValueError("place sampling produced duplicate California centroids")
    return [CALIFORNIA[index] for index in indices]


def _permutation_key(place: Place) -> bytes:
    name, lat, lon = place
    value = f"{_ASSIGNMENT_SALT}\0{name}\0{lat:.6f}\0{lon:.6f}".encode()
    return hashlib.sha256(value).digest()


def statewide_assignments(node_ids: Iterable[str]) -> dict[str, Place]:
    """Return a stable, geographically mixed node-to-place assignment.

    ``CALIFORNIA`` is ordered north-to-south. Hash-ordering the sampled centroids before pairing
    them with numeric node ids prevents generated traits such as calibration status from becoming
    a false north/south pattern while remaining byte-stable across runs and Python versions.
    """
    ids = [str(node_id) for node_id in node_ids]
    if len(set(ids)) != len(ids):
        raise ValueError("statewide preview requires unique node ids")
    ids.sort(key=node_key)
    places = sorted(_sampled_places(len(ids)), key=_permutation_key)
    if len({(lat, lon) for _, lat, lon in places}) != len(places):
        raise ValueError("statewide preview place coordinates must be unique")
    return dict(zip(ids, places, strict=True))


def config_for_web(config: NetworkConfig) -> NetworkConfig:
    """Return the coordinate presentation used to bake static web artifacts."""
    if not is_builtin_demo_web_preview(config):
        return config
    assignments = statewide_assignments(node.node_id for node in config.nodes)
    nodes = tuple(
        replace(
            node,
            label=assignments[node.node_id][0],
            lat=assignments[node.node_id][1],
            lon=assignments[node.node_id][2],
            # These are public place centroids, not host locations: exact, and hostless, so
            # they publish without grid drift and without a consent question (ADR 0040).
            location=LOCATION_PUBLIC_PLACE,
        )
        for node in config.nodes
    )
    monitors = tuple(
        replace(
            monitor,
            label=WEB_PREVIEW_REFERENCE_LABEL,
            source=_WEB_PREVIEW_REFERENCE_SOURCE,
            lat=None,
            lon=None,
        )
        for monitor in config.reference_monitors
    )
    return replace(
        config,
        name=WEB_PREVIEW_NETWORK_NAME,
        nodes=nodes,
        reference_monitors=monitors,
    )
