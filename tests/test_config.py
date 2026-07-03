"""Config loading and the privacy-preserving grid snap."""

from __future__ import annotations

from swelter.config import (
    NetworkConfig,
    NodeConfig,
    consent_concerns,
    label_concerns,
    load_config,
    parse_config,
    snap_to_grid,
)

from .conftest import ROOT


def test_label_concerns_flags_address_like_labels() -> None:
    config = NetworkConfig(
        nodes=(
            NodeConfig(node_id="node-01", label="Cedar & 4th"),  # place name — fine
            NodeConfig(node_id="node-02", label="Oak Park Commons"),  # fine
            NodeConfig(node_id="node-03", label="742 Evergreen Terrace"),  # street address
            NodeConfig(node_id="node-04", label="Rosa's place, Apt 3B"),  # unit
            NodeConfig(node_id="node-05", label="contact me@example.com"),  # email
        )
    )
    flagged = {c.split(":")[0] for c in label_concerns(config)}
    assert flagged == {"node-03", "node-04", "node-05"}  # the place names are not flagged


def test_demo_network_has_no_label_concerns() -> None:
    assert label_concerns(load_config(str(ROOT / "network.yaml"))) == []


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


def test_consent_concerns_flags_precise_node_without_consent_ref() -> None:
    config = NetworkConfig(
        nodes=(NodeConfig(node_id="node-07", lat=1.0, lon=2.0, location="precise"),)
    )
    flagged = {c.split(":")[0] for c in consent_concerns(config)}
    assert flagged == {"node-07"}


def test_consent_concerns_silent_when_consent_ref_recorded() -> None:
    config = NetworkConfig(
        nodes=(
            NodeConfig(
                node_id="node-07",
                lat=1.0,
                lon=2.0,
                location="precise",
                consent_ref="2026-05-01/node-07",
            ),
        )
    )
    assert consent_concerns(config) == []


def test_consent_concerns_ignores_coarse_nodes_regardless_of_consent_ref() -> None:
    config = NetworkConfig(
        nodes=(
            NodeConfig(node_id="node-01", lat=1.0, lon=2.0, location="coarse"),
            NodeConfig(
                node_id="node-02",
                lat=1.0,
                lon=2.0,
                location="coarse",
                consent_ref="2026-05-01/node-02",
            ),
        )
    )
    assert consent_concerns(config) == []


def test_parse_config_reads_nodes_and_languages() -> None:
    cfg = parse_config(
        {
            "name": "test net",
            "grid_resolution_m": 200,
            "languages": ["en", "es"],
            "nodes": [
                {
                    "node_id": "node-01",
                    "lat": 1.0,
                    "lon": 2.0,
                    "location": "precise",
                    "consent_ref": "2026-05-01/node-01",
                }
            ],
        }
    )
    assert cfg.grid_resolution_m == 200
    assert cfg.languages == ("en", "es")
    node = cfg.node("node-01")
    assert node is not None
    assert node.consent_ref == "2026-05-01/node-01"
    assert cfg.node("missing") is None


def test_parse_config_reads_alert_thresholds() -> None:
    cfg = parse_config({"alert_thresholds": {"pm25_aqi": 151, "heat_index_c": 41.0}})
    assert cfg.alert_thresholds == {"pm25_aqi": 151.0, "heat_index_c": 41.0}


def test_alert_thresholds_default_empty() -> None:
    assert parse_config({"name": "x"}).alert_thresholds == {}


def test_load_demo_network_yaml() -> None:
    cfg = load_config(ROOT / "network.yaml")
    assert len(cfg.nodes) >= 18  # a real demo network, count not hardcoded
    assert "es" in cfg.languages  # Spanish ships in v1 for the communities served
    assert len(cfg.public_locations()) == len(cfg.nodes)  # every node is placed
    # Some nodes calibrate and some don't; each calibrated node has a window registered.
    windowed = {w.node_id for w in cfg.calibration_windows}
    assert 0 < len(windowed) < len(cfg.nodes)
