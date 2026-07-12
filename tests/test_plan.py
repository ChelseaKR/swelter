"""Siting what-if (EXP-08): pure-function coverage simulation, plus its CLI wrapper."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from swelter.cli import main
from swelter.config import NetworkConfig, NodeConfig, ReferenceMonitor
from swelter.plan import haversine_m, simulate_add_node

# A block apart in Davis, CA — inside network.yaml's grid_resolution_m (150 m) of each other.
NODE_LAT, NODE_LON = 38.575057, -121.509361
NEAR_LAT, NEAR_LON = 38.575120, -121.506400  # ~250m away: same neighbourhood, different cell
FAR_LAT, FAR_LON = 34.052235, -118.243683  # Los Angeles: far from anything above


def _config(**overrides: object) -> NetworkConfig:
    defaults: dict[str, object] = {
        "grid_resolution_m": 150.0,
        "nodes": (NodeConfig(node_id="node-01", label="Cedar & 4th", lat=NODE_LAT, lon=NODE_LON),),
    }
    defaults.update(overrides)
    return NetworkConfig(**defaults)  # type: ignore[arg-type]


def test_haversine_m_is_zero_for_the_same_point() -> None:
    assert haversine_m(38.5, -121.5, 38.5, -121.5) == 0.0


def test_haversine_m_matches_a_known_distance() -> None:
    # Davis <-> Sacramento, roughly 22 km as the crow flies.
    d = haversine_m(38.5449, -121.7405, 38.5816, -121.4944)
    assert 20_000 < d < 24_000


def test_redundant_cell_is_not_new_and_counts_the_existing_node() -> None:
    config = _config()
    result = simulate_add_node(config, NODE_LAT, NODE_LON, node_id="candidate-1")
    assert result["node_id"] == "candidate-1"
    assert result["new_cell"] is False
    assert result["redundancy"] == 1
    nearest = result["nearest_node"]
    assert nearest is not None
    assert nearest["node_id"] == "node-01"
    # nearest_node distance is to the *published* (coarse-snapped) location, not the raw
    # candidate-vs-raw-config distance, so it's within one grid cell, not necessarily ~0.
    assert 0 <= nearest["distance_m"] < 150.0
    candidate_cell_id = (
        f"{result['candidate_cell']['lat']:.6f},{result['candidate_cell']['lon']:.6f}"
    )
    assert candidate_cell_id in result["existing_cells"]


def test_new_cell_far_away_has_no_redundancy_and_reports_nearest_node() -> None:
    config = _config()
    result = simulate_add_node(config, FAR_LAT, FAR_LON)
    assert result["new_cell"] is True
    assert result["redundancy"] == 0
    nearest = result["nearest_node"]
    assert nearest is not None
    assert nearest["node_id"] == "node-01"
    assert nearest["distance_m"] > 400_000  # LA is genuinely far from Davis


def test_nearby_but_distinct_cell_is_new_coverage() -> None:
    config = _config()
    result = simulate_add_node(config, NEAR_LAT, NEAR_LON)
    # ~250m away is outside the 150m grid cell around node-01, so it is new coverage even though
    # a real node sits nearby — the coverage question and the distance question are independent.
    assert result["new_cell"] is True
    assert result["redundancy"] == 0
    nearest = result["nearest_node"]
    assert nearest is not None
    assert nearest["distance_m"] < 500


def test_empty_network_has_no_existing_cells_and_no_nearest_node() -> None:
    config = NetworkConfig()
    result = simulate_add_node(config, NODE_LAT, NODE_LON)
    assert result["existing_cells"] == []
    assert result["new_cell"] is True
    assert result["redundancy"] == 0
    assert result["nearest_node"] is None
    assert result["nearest_reference"] is None
    assert result["reference_note"] is None  # no monitors configured at all, not "uncomputable"


def test_reference_monitors_without_coordinates_note_why_distance_is_missing() -> None:
    config = _config(
        reference_monitors=(ReferenceMonitor(monitor_id="ref-01", label="Regulatory station"),)
    )
    result = simulate_add_node(config, NODE_LAT, NODE_LON)
    assert result["nearest_reference"] is None
    assert result["reference_note"] is not None
    assert "lat/lon" in result["reference_note"]


def test_nearest_reference_distance_when_a_monitor_has_coordinates() -> None:
    config = _config(
        reference_monitors=(
            ReferenceMonitor(monitor_id="ref-far", label="Far", lat=FAR_LAT, lon=FAR_LON),
            ReferenceMonitor(monitor_id="ref-near", label="Near", lat=NEAR_LAT, lon=NEAR_LON),
        )
    )
    result = simulate_add_node(config, NODE_LAT, NODE_LON)
    ref = result["nearest_reference"]
    assert ref is not None
    assert ref["monitor_id"] == "ref-near"  # the closer of the two, not the first in the list
    assert result["reference_note"] is None


def test_nearest_reference_second_monitor_not_closer_keeps_the_first() -> None:
    # Reversed order from the test above, so the loop's "not closer" branch runs too.
    config = _config(
        reference_monitors=(
            ReferenceMonitor(monitor_id="ref-near", label="Near", lat=NEAR_LAT, lon=NEAR_LON),
            ReferenceMonitor(monitor_id="ref-far", label="Far", lat=FAR_LAT, lon=FAR_LON),
        )
    )
    result = simulate_add_node(config, NODE_LAT, NODE_LON)
    ref = result["nearest_reference"]
    assert ref is not None
    assert ref["monitor_id"] == "ref-near"


def test_nearest_node_second_node_not_closer_keeps_the_first() -> None:
    config = _config(
        nodes=(
            NodeConfig(node_id="node-01", lat=NODE_LAT, lon=NODE_LON),
            NodeConfig(node_id="node-02", lat=FAR_LAT, lon=FAR_LON),
        )
    )
    result = simulate_add_node(config, NODE_LAT, NODE_LON)
    nearest = result["nearest_node"]
    assert nearest is not None
    assert nearest["node_id"] == "node-01"


def test_candidate_placement_is_coarse_like_a_real_coarse_node() -> None:
    # A precise lat/lon candidate still publishes to the grid cell, not the raw point — same
    # privacy boundary a real `location: coarse` node gets (hard rule 2).
    config = NetworkConfig()
    result = simulate_add_node(config, NODE_LAT, NODE_LON)
    cell = result["candidate_cell"]
    assert (cell["lat"], cell["lon"]) != (NODE_LAT, NODE_LON)


# -- CLI -----------------------------------------------------------------------------------------


def _write_network(path: Path) -> None:
    path.write_text(
        f"""\
name: test network
grid_resolution_m: 150
nodes:
- node_id: node-01
  label: Cedar & 4th
  lat: {NODE_LAT}
  lon: {NODE_LON}
  location: coarse
reference_monitors:
- monitor_id: ref-01
  label: Regulatory station
  lat: {NEAR_LAT}
  lon: {NEAR_LON}
""",
        encoding="utf-8",
    )


def test_cli_plan_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config_path = tmp_path / "network.yaml"
    _write_network(config_path)
    rc = main(["plan", "--add-node", "33.87,-117.92", "--json", "--config", str(config_path)])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["node_id"] == "candidate"
    assert payload["new_cell"] is True
    assert payload["nearest_node"]["node_id"] == "node-01"
    assert payload["nearest_reference"]["monitor_id"] == "ref-01"


def test_cli_plan_text_summary(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config_path = tmp_path / "network.yaml"
    _write_network(config_path)
    rc = main(["plan", "--add-node", f"{NODE_LAT},{NODE_LON}", "--config", str(config_path)])
    assert rc == 0
    err = capsys.readouterr().err
    assert "candidate cell" in err
    assert "already covered" in err
    assert "redundancy: 1" in err
    assert "nearest reference monitor: ref-01" in err


def test_cli_plan_rejects_malformed_add_node(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config_path = tmp_path / "network.yaml"
    _write_network(config_path)
    rc = main(["plan", "--add-node", "not-a-coordinate", "--config", str(config_path)])
    assert rc == 1
    assert "lat,lon" in capsys.readouterr().err

    rc_single = main(["plan", "--add-node", "38.5", "--config", str(config_path)])
    assert rc_single == 1


def test_cli_plan_with_no_reference_monitor_coordinates(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config_path = tmp_path / "network.yaml"
    config_path.write_text(
        f"""\
name: test network
grid_resolution_m: 150
nodes:
- node_id: node-01
  lat: {NODE_LAT}
  lon: {NODE_LON}
reference_monitors:
- monitor_id: ref-01
  label: Regulatory station
""",
        encoding="utf-8",
    )
    rc = main(["plan", "--add-node", "33.87,-117.92", "--config", str(config_path)])
    assert rc == 0
    err = capsys.readouterr().err
    assert "lat/lon" in err


def test_cli_plan_with_no_config_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    missing = tmp_path / "does-not-exist.yaml"
    rc = main(["plan", "--add-node", "33.87,-117.92", "--config", str(missing)])
    assert rc == 0
    err = capsys.readouterr().err
    assert "no reference monitors configured" in err
    assert "nearest node: none placed yet" in err
