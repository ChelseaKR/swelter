"""Read-only API surface: an OGC SensorThings 1.1 subset plus CSV/JSON export.

The API is read-only by construction — there is no write path here, so the public surface
cannot be used to alter the record. It renders observations into the OGC SensorThings shape
(``Things`` are nodes, ``Datastreams`` are parameters, ``Observations`` are readings) so
standard GIS and analysis tools consume swelter unchanged, and emits the same data as flat CSV
and JSON for everyone else.

These functions return plain dicts and strings; :mod:`swelter.server` is the thin HTTP layer
over them. Keeping the rendering pure makes the whole API testable without a socket.
"""

from __future__ import annotations

from collections.abc import Sequence

from . import export
from .config import NetworkConfig
from .models import PARAMETERS, Observation

SENSORTHINGS_VERSION = "1.1"


def service_document(base_url: str) -> dict[str, object]:
    """The SensorThings entry point: the collections a client can follow."""
    base = base_url.rstrip("/")
    names = ("Things", "Locations", "Datastreams", "Observations", "ObservedProperties")
    return {
        "serverSettings": {
            "conformance": [
                "http://www.opengis.net/spec/iot_sensing/1.1/req/datamodel",
                "http://www.opengis.net/spec/iot_sensing/1.1/req/request-data",
            ],
            "readOnly": True,
        },
        "value": [
            {"name": name, "url": f"{base}/v{SENSORTHINGS_VERSION}/{name}"} for name in names
        ],
    }


def things(config: NetworkConfig, base_url: str) -> dict[str, object]:
    """Nodes as SensorThings ``Things`` with their *published* (grid-snapped) locations."""
    base = base_url.rstrip("/")
    locations = config.public_locations()
    value: list[dict[str, object]] = []
    for node in config.nodes:
        loc = locations.get(node.node_id)
        location_block: list[dict[str, object]] = []
        if loc is not None:
            lat, lon = loc
            location_block = [
                {
                    "name": f"{node.node_id} (published cell)",
                    "encodingType": "application/geo+json",
                    "location": {"type": "Point", "coordinates": [lon, lat]},
                }
            ]
        nav = f"{base}/v{SENSORTHINGS_VERSION}/Things({node.node_id})/Locations"
        value.append(
            {
                "@iot.id": node.node_id,
                "name": node.label or node.node_id,
                "description": "Community heat/air-quality sensor node",
                "properties": {"location_precision": node.location},
                "Locations": location_block,
                "Locations@iot.navigationLink": nav,
            }
        )
    return {"@iot.count": len(value), "value": value}


def observed_properties(base_url: str) -> dict[str, object]:
    value = [
        {
            "@iot.id": name,
            "name": name,
            "definition": f"https://github.com/ChelseaKR/swelter/blob/main/docs/api.md#{name}",
            "properties": {"unit": param.unit},
        }
        for name, param in PARAMETERS.items()
    ]
    return {"@iot.count": len(value), "value": value}


def observations(
    obs: Sequence[Observation], base_url: str, *, top: int = 1000
) -> dict[str, object]:
    """Readings as SensorThings ``Observations``; provenance kept in ``parameters``."""
    sliced = list(obs)[:top]
    value = [
        {
            "@iot.id": f"{o.node_id}|{o.timestamp}|{o.parameter}|{o.calibration}",
            "phenomenonTime": o.timestamp,
            "result": o.value,
            "resultQuality": {"qc": o.qc, "uncertainty": o.uncertainty},
            "parameters": {
                "node_id": o.node_id,
                "parameter": o.parameter,
                "unit": o.unit,
                "calibration": o.calibration,
            },
        }
        for o in sliced
    ]
    return {"@iot.count": len(value), "value": value}


# Re-export the flat formats so callers have one import for "the API and its dumps".
to_csv = export.to_csv
to_json = export.to_json
