"""E6 — the interoperability round-trip proof.

A "standard SensorThings client" does not know anything about swelter internals: it walks the
JSON collections a SensorThings service publishes (``Things``, ``Datastreams``,
``ObservedProperties``, ``Observations``) using only the keys the OGC SensorThings 1.1 shape
defines. This test plays that client: it builds swelter ``Observation`` records, renders them
through :mod:`swelter.api` exactly as :mod:`swelter.server` would, walks the resulting JSON back
to (node, parameter, value, unit) using nothing but documented SensorThings fields, and then
shows every recovered parameter is translatable into OpenAQ/Sensor.Community vocabulary via
:mod:`swelter.crosswalk` — proving the loop closes: swelter model -> SensorThings JSON -> parsed
by a generic client -> commons vocabulary. No network, no external client library: the "standard
client" here is a plain dict walker, which is all a SensorThings JSON consumer needs to be.
"""

from __future__ import annotations

import json
from typing import Any

from swelter import api, crosswalk
from swelter.config import NetworkConfig, NodeConfig
from swelter.models import PARAMETERS, Observation

BASE_URL = "http://example.test"


def _network() -> NetworkConfig:
    return NetworkConfig(
        name="interop-test",
        nodes=(
            NodeConfig(node_id="node-a", label="Cedar & 4th", lat=38.58, lon=-121.49),
            NodeConfig(node_id="node-b", label="Oak & 4th", lat=38.60, lon=-121.50),
        ),
    )


def _observations() -> list[Observation]:
    """A small multi-node, multi-parameter set spanning raw and calibrated readings, covering
    every parameter swelter knows about (including one with no commons equivalent)."""
    obs = [
        Observation("node-a", "2026-06-01T00:00:00Z", "temp_c", 30.0, "degC"),
        Observation("node-a", "2026-06-01T00:00:00Z", "humidity_pct", 55.0, "%"),
        Observation(
            "node-a", "2026-06-01T00:00:00Z", "pm25_ugm3", 12.3, "ug/m3", calibration="raw"
        ),
        # A calibrated PM2.5 reading at the same (node, timestamp) — dedupe must prefer it.
        Observation(
            "node-a",
            "2026-06-01T00:00:00Z",
            "pm25_ugm3",
            11.8,
            "ug/m3",
            calibration="pm25_ugm3.ref-01.node-a",
            uncertainty=0.4,
        ),
        Observation("node-a", "2026-06-01T00:00:00Z", "heat_index_c", 34.2, "degC"),
        Observation("node-b", "2026-06-01T01:00:00Z", "pm10_ugm3", 20.5, "ug/m3"),
        Observation("node-b", "2026-06-01T01:00:00Z", "no2_ppb", 18.0, "ppb"),
    ]
    return obs


def test_sensorthings_export_conforms_to_the_documented_shape() -> None:
    """(a) The rendered payloads carry the SensorThings keys the spec/ADR 0007 promise."""
    config = _network()
    obs = _observations()

    things_doc: Any = json.loads(json.dumps(api.things(config, BASE_URL)))
    datastreams_doc: Any = json.loads(json.dumps(api.datastreams(config, BASE_URL)))
    op_doc: Any = json.loads(json.dumps(api.observed_properties(BASE_URL)))
    obs_doc: Any = json.loads(json.dumps(api.observations(obs, BASE_URL, top=100)))

    assert things_doc["@iot.count"] == len(config.nodes)
    for thing in things_doc["value"]:
        assert "@iot.id" in thing
        assert "name" in thing

    assert datastreams_doc["@iot.count"] == len(config.nodes) * len(PARAMETERS)
    for ds in datastreams_doc["value"]:
        assert "unitOfMeasurement" in ds
        assert "symbol" in ds["unitOfMeasurement"]

    assert op_doc["@iot.count"] == len(PARAMETERS)
    assert {row["@iot.id"] for row in op_doc["value"]} == set(PARAMETERS)

    # Dedupe (raw + calibrated pm25 at same node/timestamp/parameter) collapses to one row.
    assert obs_doc["@iot.count"] == 6
    for row in obs_doc["value"]:
        assert "result" in row
        assert "phenomenonTime" in row
        assert "parameter" in row["parameters"]
        assert "unit" in row["parameters"]


def _walk_client(obs_doc: dict[str, Any]) -> dict[tuple[str, str], tuple[float, str]]:
    """A "standard SensorThings client": walk Observations using only documented fields to
    recover (node, parameter) -> (value, unit). No knowledge of swelter internals."""
    recovered: dict[tuple[str, str], tuple[float, str]] = {}
    for row in obs_doc["value"]:
        node_id = row["parameters"]["node_id"]
        parameter = row["parameters"]["parameter"]
        unit = row["parameters"]["unit"]
        value = row["result"]
        recovered[(node_id, parameter)] = (value, unit)
    return recovered


def test_roundtrip_recovers_values_and_maps_to_commons_vocabulary() -> None:
    """(b) A generic client walking the JSON recovers the original values/units, and (c) every
    recovered parameter maps to the expected OpenAQ/Sensor.Community label via the crosswalk —
    the full round trip: swelter model -> SensorThings JSON -> parsed client -> commons terms."""
    config = _network()
    inputs = _observations()
    obs_doc: Any = json.loads(json.dumps(api.observations(inputs, BASE_URL, top=100)))

    recovered = _walk_client(obs_doc)

    # The calibrated pm25 value (11.8) wins over the raw one (12.3) for node-a — dedupe honored.
    expected: dict[tuple[str, str], tuple[float, str]] = {
        ("node-a", "temp_c"): (30.0, "degC"),
        ("node-a", "humidity_pct"): (55.0, "%"),
        ("node-a", "pm25_ugm3"): (11.8, "ug/m3"),
        ("node-a", "heat_index_c"): (34.2, "degC"),
        ("node-b", "pm10_ugm3"): (20.5, "ug/m3"),
        ("node-b", "no2_ppb"): (18.0, "ppb"),
    }
    assert recovered == expected

    expected_commons: dict[str, dict[str, tuple[str, str] | None]] = {
        "temp_c": {"openaq": ("temperature", "degC"), "sc": ("temperature", "degC")},
        "humidity_pct": {"openaq": ("relativehumidity", "%"), "sc": ("humidity", "%")},
        "pm25_ugm3": {"openaq": ("pm25", "ug/m3"), "sc": ("P2", "ug/m3")},
        "heat_index_c": {"openaq": None, "sc": None},
        "wbgt_c": {"openaq": None, "sc": None},
        "wind_chill_c": {"openaq": None, "sc": None},
        "pm10_ugm3": {"openaq": ("pm10", "ug/m3"), "sc": ("P1", "ug/m3")},
        "no2_ppb": {"openaq": ("no2", "ppb"), "sc": None},
    }

    for (_node_id, parameter), (_value, _unit) in recovered.items():
        commons = expected_commons[parameter]
        assert crosswalk.to_openaq(parameter) == commons["openaq"]
        assert crosswalk.to_sensor_community(parameter) == commons["sc"]

    # Every ObservedProperty a client discovers is itself resolvable in the crosswalk — a client
    # that only ever saw the ObservedProperties collection (never a raw Observation) can still
    # translate the whole vocabulary into commons terms.
    op_doc: Any = json.loads(json.dumps(api.observed_properties(BASE_URL)))
    for row in op_doc["value"]:
        name = row["@iot.id"]
        assert name in expected_commons  # crosswalk.to_openaq/to_sensor_community defined below
        # calling both must not raise, and must match the module-level table
        assert crosswalk.to_openaq(name) == expected_commons[name]["openaq"]
        assert crosswalk.to_sensor_community(name) == expected_commons[name]["sc"]

    # Sanity: the walked client's units match unitOfMeasurement.symbol on the matching Datastream.
    datastreams_doc: Any = json.loads(json.dumps(api.datastreams(config, BASE_URL)))
    unit_by_ds: dict[str, str] = {
        ds["@iot.id"]: ds["unitOfMeasurement"]["symbol"] for ds in datastreams_doc["value"]
    }
    for (node_id, parameter), (_value, unit) in recovered.items():
        assert unit_by_ds[f"{node_id}:{parameter}"] == unit
