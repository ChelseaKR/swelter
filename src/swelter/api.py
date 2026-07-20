"""Read-only API surface: an OGC SensorThings 1.1 subset plus CSV/JSON export.

The API is read-only by construction — there is no write path here, so the public surface cannot
be used to alter the record. It renders observations into the OGC SensorThings shape (``Things``
are nodes, ``Datastreams`` are node/parameter streams, ``Observations`` are readings) so standard
GIS and analysis tools consume swelter unchanged, and emits the same data as flat CSV and JSON for
everyone else.

The subset is honest about its limits: ``Observations`` paginate with ``$top``/``$skip``, report a
true total ``@iot.count``, and emit an ``@iot.nextLink``; by default they are deduped to one row per
(node, timestamp, parameter, source) preferring the calibrated value (pass ``dedupe=False`` for the
raw *and* calibrated rows). These functions return plain dicts; :mod:`swelter.server` is the thin
HTTP layer over them, which keeps the whole API testable without a socket.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from . import export
from .config import NetworkConfig
from .dictionary import DATA_SCHEMA_VERSION, build_data_dictionary
from .models import PARAMETERS, RAW, Observation

SENSORTHINGS_VERSION = "1.1"
_DEF = "https://github.com/ChelseaKR/swelter/blob/main/docs/api.md"


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
            # The data-schema version an integrator pins against — see /api/schema.json and
            # docs/VERSIONING.md ("Data schema — what counts as breaking"). Advertised here too so
            # a SensorThings client sees it at the entry point, not just the dictionary endpoint.
            "dataSchemaVersion": DATA_SCHEMA_VERSION,
        },
        "value": [
            {"name": name, "url": f"{base}/v{SENSORTHINGS_VERSION}/{name}"} for name in names
        ],
    }


def schema_document(
    *,
    data_source: str | None = None,
    data_license: str | None = None,
    data_attribution: str | None = None,
    data_license_url: str | None = None,
) -> dict[str, object]:
    """The machine-readable data dictionary served at ``/api/schema.json``."""
    return build_data_dictionary(
        data_source=data_source,
        data_license=data_license,
        data_attribution=data_attribution,
        data_license_url=data_license_url,
    )


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
                    "name": f"{node.label or node.node_id} (published cell)",
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
                "properties": {"location_precision": node.location, "label": node.label},
                "Locations": location_block,
                "Locations@iot.navigationLink": nav,
            }
        )
    return {"@iot.count": len(value), "value": value}


def locations(config: NetworkConfig, base_url: str) -> dict[str, object]:
    """The published (grid-snapped) cell centres as SensorThings ``Locations``."""
    value: list[dict[str, object]] = []
    for node in config.nodes:
        loc = config.public_locations().get(node.node_id)
        if loc is None:
            continue
        lat, lon = loc
        value.append(
            {
                "@iot.id": f"{node.node_id}-loc",
                "name": f"{node.label or node.node_id} (published cell)",
                "encodingType": "application/geo+json",
                "location": {"type": "Point", "coordinates": [lon, lat]},
            }
        )
    return {"@iot.count": len(value), "value": value}


def datastreams(config: NetworkConfig, base_url: str) -> dict[str, object]:
    """One ``Datastream`` per (node, parameter), linking a Thing to an ObservedProperty."""
    vbase = f"{base_url.rstrip('/')}/v{SENSORTHINGS_VERSION}"
    value: list[dict[str, object]] = []
    for node in config.nodes:
        for name, param in PARAMETERS.items():
            value.append(
                {
                    "@iot.id": f"{node.node_id}:{name}",
                    "name": f"{node.label or node.node_id} — {name}",
                    "unitOfMeasurement": {
                        "name": name,
                        "symbol": param.unit,
                        "definition": f"{_DEF}#{name}",
                    },
                    "observationType": (
                        "http://www.opengis.net/def/observationType/OGC-OM/2.0/OM_Measurement"
                    ),
                    "Thing@iot.navigationLink": f"{vbase}/Things({node.node_id})",
                    "ObservedProperty@iot.navigationLink": f"{vbase}/ObservedProperties({name})",
                }
            )
    return {"@iot.count": len(value), "value": value}


def observed_properties(base_url: str) -> dict[str, object]:
    value = [
        {
            "@iot.id": name,
            "name": name,
            "definition": f"{_DEF}#{name}",
            "properties": {"unit": param.unit},
        }
        for name, param in PARAMETERS.items()
    ]
    return {"@iot.count": len(value), "value": value}


def _dedupe_prefer_calibrated(obs: Sequence[Observation]) -> list[Observation]:
    """One observation per source-aware identity, preferring its calibrated value."""
    chosen: dict[tuple[str, str, str, str], Observation] = {}
    for o in obs:
        key = (o.node_id, o.timestamp, o.parameter, o.source)
        existing = chosen.get(key)
        if existing is None or (existing.calibration == RAW and o.calibration != RAW):
            chosen[key] = o
    return list(chosen.values())


def observations(
    obs: Sequence[Observation],
    base_url: str,
    *,
    top: int = 1000,
    skip: int = 0,
    dedupe: bool = True,
    order: str = "asc",
    data_license: str | None = None,
    data_attribution: str | None = None,
    data_license_url: str | None = None,
    terms_by_observation: Mapping[export.TermsKey, Mapping[str, str]] | None = None,
) -> dict[str, object]:
    """Readings as SensorThings ``Observations``, paginated with a true total and a nextLink.

    ``order="desc"`` returns latest-first (newest ``phenomenonTime``) so a client can fetch the
    most recent N; the default ``asc`` preserves the stored order.
    """
    items = _dedupe_prefer_calibrated(obs) if dedupe else list(obs)
    if order == "desc":
        items = sorted(items, key=lambda o: o.timestamp, reverse=True)
    total = len(items)
    top = max(0, top)
    skip = max(0, skip)
    page = items[skip : skip + top] if top else []
    value: list[dict[str, object]] = []
    for o in page:
        exact_terms: Mapping[str, str] | None = None
        if terms_by_observation is not None:
            exact_terms = terms_by_observation.get((o.node_id, o.timestamp, o.source))
            if exact_terms is None:
                exact_terms = terms_by_observation.get((o.node_id, o.timestamp))
            if exact_terms is None:
                exact_terms = terms_by_observation.get(o.node_id)
        row_license = exact_terms.get("license") if exact_terms is not None else data_license
        row_attribution = (
            exact_terms.get("attribution") if exact_terms is not None else data_attribution
        )
        row_license_url = (
            exact_terms.get("license_url") if exact_terms is not None else data_license_url
        )
        parameters: dict[str, object] = {
            "node_id": o.node_id,
            "parameter": o.parameter,
            "unit": o.unit,
            "source": o.source,
            "calibration": o.calibration,
        }
        if row_license:
            parameters["data_license"] = row_license
        if row_attribution:
            parameters["data_attribution"] = row_attribution
        if row_license_url:
            parameters["data_license_url"] = row_license_url
        value.append(
            {
                "@iot.id": (f"{o.node_id}|{o.timestamp}|{o.parameter}|{o.source}|{o.calibration}"),
                "phenomenonTime": o.timestamp,
                "result": o.value,
                "resultQuality": {
                    "qc": o.qc,
                    "uncertainty": o.uncertainty,
                    "trustworthy": o.is_trustworthy,
                },
                "parameters": parameters,
            }
        )
    result: dict[str, object] = {"@iot.count": total, "value": value}
    if top and skip + top < total:
        base = base_url.rstrip("/")
        order_q = "&order=desc" if order == "desc" else ""
        result["@iot.nextLink"] = (
            f"{base}/v{SENSORTHINGS_VERSION}/Observations?$skip={skip + top}&$top={top}{order_q}"
        )
    return result


# Re-export the flat formats so callers have one import for "the API and its dumps".
to_csv = export.to_csv
to_json = export.to_json
