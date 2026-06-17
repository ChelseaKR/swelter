"""Config loading and the privacy-preserving grid snap."""

from __future__ import annotations

from swelter.config import NodeConfig, load_config, parse_config, snap_to_grid

from .conftest import ROOT


def test_snap_to_grid_coarsens_within_one_cell() -> None:
    lat, lon = 38.581600, -121.494400
    cell = snap_to_grid(lat, lon, 150.0)
    assert cell != (lat, lon)  # the published coordinate is coarsened, not exact
    assert snap_to_grid(lat, lon, 150.0) == cell  # deterministic
    # The cell centre is within one grid cell of the true point.
    assert abs(cell[0] - lat) * 111_320 < 150
    assert abs(cell[1] - lon) * 111_320 < 150


def test_coarse_node_publishes_snapped_location() -> None:
    node = NodeConfig(node_id="node-01", lat=38.5816, lon=-121.4944, location="coarse")
    published = node.public_location(150.0)
    assert published is not None
    assert published != (38.5816, -121.4944)


def test_precise_node_publishes_exact_location() -> None:
    node = NodeConfig(node_id="node-01", lat=38.5816, lon=-121.4944, location="precise")
    assert node.public_location(150.0) == (38.5816, -121.4944)


def test_unplaced_node_has_no_public_location() -> None:
    node = NodeConfig(node_id="node-99")
    assert node.public_location(150.0) is None


def test_parse_config_reads_nodes_and_languages() -> None:
    cfg = parse_config(
        {
            "name": "test net",
            "grid_resolution_m": 200,
            "languages": ["en", "es"],
            "nodes": [{"node_id": "node-01", "lat": 1.0, "lon": 2.0}],
        }
    )
    assert cfg.grid_resolution_m == 200
    assert cfg.languages == ("en", "es")
    assert cfg.node("node-01") is not None
    assert cfg.node("missing") is None


def test_load_demo_network_yaml() -> None:
    cfg = load_config(ROOT / "network.yaml")
    assert len(cfg.nodes) == 18
    assert "es" in cfg.languages  # Spanish ships in v1 for the communities served
    assert len(cfg.public_locations()) == 18
    # Every calibrated node has a calibration window registered.
    windowed = {w.node_id for w in cfg.calibration_windows}
    assert len(windowed) == 12
