"""Export carries provenance and prints an honest summary."""

from __future__ import annotations

import csv
import json
from typing import Any

from swelter import export

from .conftest import make_obs


def test_to_csv_has_header_and_one_row_per_observation() -> None:
    text = export.to_csv([make_obs(), make_obs(parameter="humidity_pct", unit="%", value=50.0)])
    lines = text.strip().splitlines()
    assert lines[0].startswith("node_id,timestamp,parameter,value,unit,calibration,qc,uncertainty")
    assert lines[0].endswith("data_license,data_attribution")
    assert len(lines) == 3


def test_to_json_declares_the_data_license() -> None:
    doc: Any = json.loads(export.to_json([make_obs()]))
    assert doc["license"] == "CC0-1.0"
    assert len(doc["observations"]) == 1


def test_to_json_license_varies_by_source() -> None:
    """A fetched third-party source carries its own license, not the CC0 store default."""
    doc: Any = json.loads(
        export.to_json(
            [make_obs()],
            license="CC BY-SA 4.0",
            attribution="Readings from the Sensor.Community network, CC BY-SA 4.0.",
        )
    )
    assert doc["license"] == "CC BY-SA 4.0"
    assert doc["attribution"] == "Readings from the Sensor.Community network, CC BY-SA 4.0."


def test_to_csv_license_varies_by_source() -> None:
    text = export.to_csv(
        [make_obs()],
        license="CC BY-SA 4.0",
        attribution="Readings from the Sensor.Community network, CC BY-SA 4.0.",
    )
    rows = list(csv.DictReader(text.splitlines()))
    assert rows[0]["data_license"] == "CC BY-SA 4.0"
    assert (
        rows[0]["data_attribution"] == "Readings from the Sensor.Community network, CC BY-SA 4.0."
    )


def test_summary_reports_calibrated_vs_raw_and_license() -> None:
    text = export.summarize(
        [
            make_obs(),
            make_obs(
                node_id="node-02", parameter="pm25_ugm3", unit="ug/m3", value=10.0, calibration="v1"
            ),
        ]
    )
    assert "observations from 2 nodes" in text
    assert "1 calibrated, 1 raw-flagged" in text
    assert "CC0-1.0" in text


def test_summary_reports_a_non_default_license() -> None:
    text = export.summarize([make_obs()], license="CC BY-SA 4.0")
    assert "CC BY-SA 4.0" in text
    assert "CC0-1.0" not in text


def test_filter_observations() -> None:
    obs = [
        make_obs(timestamp="2026-06-01T00:00:00Z"),
        make_obs(node_id="node-02", timestamp="2026-06-02T00:00:00Z"),
    ]
    assert len(export.filter_observations(obs, node="node-02")) == 1
    assert len(export.filter_observations(obs, since="2026-06-01T12:00:00Z")) == 1
