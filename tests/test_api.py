"""The read-only API renders SensorThings and never exposes a precise location."""

from __future__ import annotations

import json
from typing import Any

from swelter import api
from swelter.config import NetworkConfig, NodeConfig

from .conftest import make_obs


def test_service_document_advertises_read_only() -> None:
    doc: Any = json.loads(json.dumps(api.service_document("http://x")))
    assert doc["serverSettings"]["readOnly"] is True
    names = {entry["name"] for entry in doc["value"]}
    assert {"Things", "Observations", "Datastreams"} <= names


def test_things_publishes_snapped_location_not_exact() -> None:
    config = NetworkConfig(
        nodes=(NodeConfig(node_id="node-01", lat=38.5816, lon=-121.4944, location="coarse"),)
    )
    doc: Any = json.loads(json.dumps(api.things(config, "http://x")))
    coords = doc["value"][0]["Locations"][0]["location"]["coordinates"]
    assert coords != [-121.4944, 38.5816]  # grid-snapped, not the porch


def test_observations_doc_carries_provenance() -> None:
    doc: Any = json.loads(json.dumps(api.observations([make_obs(calibration="v1")], "http://x")))
    assert doc["@iot.count"] == 1
    observation = doc["value"][0]
    assert "phenomenonTime" in observation
    assert observation["parameters"]["calibration"] == "v1"
