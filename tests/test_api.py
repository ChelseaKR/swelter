"""The read-only API renders SensorThings and never exposes a precise location."""

from __future__ import annotations

import json
from typing import Any

from swelter import api, export
from swelter.config import NetworkConfig, NodeConfig
from swelter.models import SOURCE_OPENAQ, SOURCE_OPENMETEO

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


def test_observations_carry_exact_source_and_timestamp_specific_rights() -> None:
    observation = make_obs(node_id="oaq-1", source=SOURCE_OPENAQ)
    exact: dict[export.TermsKey, dict[str, str]] = {
        (observation.node_id, observation.timestamp): {
            "license": "Provider license A",
            "attribution": "Provider A",
        }
    }
    doc: Any = json.loads(
        json.dumps(
            api.observations(
                [observation],
                "http://x",
                data_license="Provider-specific (see ledger)",
                data_attribution="OpenAQ",
                data_license_url="https://openaq.org/about/initiatives/data-access/",
                terms_by_observation=exact,
            )
        )
    )
    parameters = doc["value"][0]["parameters"]
    assert parameters["source"] == SOURCE_OPENAQ
    assert parameters["data_license"] == "Provider license A"
    assert parameters["data_attribution"] == "Provider A"
    assert "data_license_url" not in parameters  # no blanket URL replaces exact provider terms


def test_observations_paginate_with_true_count_and_nextlink() -> None:
    obs = [make_obs(timestamp=f"2026-06-01T{i:02d}:00:00Z") for i in range(5)]
    doc: Any = json.loads(json.dumps(api.observations(obs, "http://x", top=2, skip=0)))
    assert doc["@iot.count"] == 5  # the true total, not the page size
    assert len(doc["value"]) == 2
    assert "@iot.nextLink" in doc


def test_observations_dedupe_prefers_calibrated() -> None:
    raw = make_obs(value=20.0)
    calibrated = raw.calibrated("temp_c.enclosure-offset.node-01", 19.0, 0.5)
    doc: Any = json.loads(json.dumps(api.observations([raw, calibrated], "http://x")))
    assert doc["@iot.count"] == 1
    assert doc["value"][0]["parameters"]["calibration"] != "raw"


def test_observations_keep_source_distinct_rows_and_ids() -> None:
    first = make_obs(source=SOURCE_OPENAQ)
    second = make_obs(source=SOURCE_OPENMETEO)

    doc: Any = json.loads(json.dumps(api.observations([first, second], "http://x")))

    assert doc["@iot.count"] == 2
    assert {row["parameters"]["source"] for row in doc["value"]} == {
        SOURCE_OPENAQ,
        SOURCE_OPENMETEO,
    }
    assert len({row["@iot.id"] for row in doc["value"]}) == 2


def test_observation_rights_can_be_keyed_by_source_aware_identity() -> None:
    first = make_obs(source=SOURCE_OPENAQ)
    second = make_obs(source=SOURCE_OPENMETEO)
    rights: dict[export.TermsKey, dict[str, str]] = {
        (first.node_id, first.timestamp, first.source): {"license": "OpenAQ provider terms"},
        (second.node_id, second.timestamp, second.source): {"license": "CAMS terms"},
    }

    doc: Any = json.loads(
        json.dumps(api.observations([first, second], "http://x", terms_by_observation=rights))
    )

    assert {row["parameters"]["data_license"] for row in doc["value"]} == {
        "OpenAQ provider terms",
        "CAMS terms",
    }


def test_datastreams_and_locations_collections() -> None:
    config = NetworkConfig(nodes=(NodeConfig(node_id="node-01", lat=38.58, lon=-121.49),))
    datastreams: Any = json.loads(json.dumps(api.datastreams(config, "http://x")))
    locations: Any = json.loads(json.dumps(api.locations(config, "http://x")))
    assert datastreams["@iot.count"] >= 1
    assert locations["@iot.count"] == 1


def test_observations_order_desc_returns_latest_first() -> None:
    obs = [make_obs(timestamp=f"2026-06-01T0{i}:00:00Z") for i in range(5)]
    doc: Any = json.loads(json.dumps(api.observations(obs, "http://x", top=2, order="desc")))
    assert doc["value"][0]["phenomenonTime"] == "2026-06-01T04:00:00Z"  # latest first
