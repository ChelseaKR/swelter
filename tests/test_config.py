"""Config loading and the privacy-preserving grid snap."""

from __future__ import annotations

from pathlib import Path

import pytest

from swelter.config import (
    NetworkConfig,
    NodeConfig,
    config_concerns,
    consent_concerns,
    label_concerns,
    load_config,
    load_config_doc,
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
    # The demo network's twin_windows example is committed commented-out (docs, not live config).
    assert cfg.twin_windows == ()
    # None of the demo nodes carry a sensor_model — this is what keeps the committed corrections
    # registry byte-for-byte reproducible (fit() falls back to the per-parameter default).
    assert all(n.sensor_model == "" for n in cfg.nodes)


def test_parse_config_reads_twin_windows() -> None:
    cfg = parse_config(
        {
            "twin_windows": [
                {
                    "node_a": "node-01",
                    "node_b": "node-02",
                    "parameter": "pm25_ugm3",
                    "start": "2026-06-01T00:00:00Z",
                    "end": "2026-06-03T23:00:00Z",
                }
            ]
        }
    )
    assert len(cfg.twin_windows) == 1
    window = cfg.twin_windows[0]
    assert window.node_a == "node-01"
    assert window.node_b == "node-02"
    assert window.parameter == "pm25_ugm3"
    assert window.start == "2026-06-01T00:00:00Z"
    assert window.end == "2026-06-03T23:00:00Z"


def test_twin_windows_default_empty() -> None:
    assert parse_config({"name": "x"}).twin_windows == ()


# -- sensor_model (EXP-03) ----------------------------------------------------------------------


def test_node_config_sensor_model_defaults_empty() -> None:
    assert NodeConfig(node_id="node-01").sensor_model == ""


def test_sensor_model_roundtrips_through_load_config(tmp_path: Path) -> None:
    doc = tmp_path / "network.yaml"
    doc.write_text(
        "nodes:\n"
        "- node_id: node-01\n"
        "  lat: 1.0\n"
        "  lon: 2.0\n"
        "  sensor_model: PMS5003\n"
        "- node_id: node-02\n"
        "  lat: 1.0\n"
        "  lon: 2.0\n",
        encoding="utf-8",
    )
    cfg = load_config(doc)
    node_1 = cfg.node("node-01")
    node_2 = cfg.node("node-02")
    assert node_1 is not None and node_1.sensor_model == "PMS5003"
    assert node_2 is not None and node_2.sensor_model == ""  # unspecified


def test_parse_config_reads_sensor_model() -> None:
    cfg = parse_config(
        {"nodes": [{"node_id": "node-01", "sensor_model": "SDS011"}]},
    )
    node = cfg.node("node-01")
    assert node is not None
    assert node.sensor_model == "SDS011"


@pytest.mark.parametrize(
    "value",
    [
        "SN123456",  # explicit serial-number marker
        "S/N: 4471829",
        "PMS5003-000123456",  # a long digit run — a device instance, not a family
        "serial 88213",
        "AA:BB:CC:DD:EE:FF",  # MAC-address-shaped
        "550e8400-e29b-41d4-a716-446655440000",  # UUID-shaped
    ],
)
def test_sensor_model_rejects_serial_number_like_values(value: str) -> None:
    with pytest.raises(ValueError, match="sensor_model"):
        NodeConfig(node_id="node-01", sensor_model=value)


@pytest.mark.parametrize("value", ["PMS5003", "SDS011", "SPS30", "BME280", ""])
def test_sensor_model_accepts_public_family_strings(value: str) -> None:
    node = NodeConfig(node_id="node-01", sensor_model=value)
    assert node.sensor_model == value


def test_parse_config_rejects_serial_like_sensor_model() -> None:
    with pytest.raises(ValueError, match="sensor_model"):
        parse_config({"nodes": [{"node_id": "node-01", "sensor_model": "SN000123456"}]})

# -- config_concerns (strict validation / `swelter doctor`) ------------------


def test_demo_network_has_no_config_concerns() -> None:
    config, doc = load_config_doc(str(ROOT / "network.yaml"))
    errors, warnings = config_concerns(config, doc)
    assert errors == []
    assert warnings == []


def test_config_concerns_flags_duplicate_node_id() -> None:
    config = parse_config(
        {
            "nodes": [
                {"node_id": "node-01", "lat": 1.0, "lon": 1.0},
                {"node_id": "node-01", "lat": 2.0, "lon": 2.0},
            ]
        }
    )
    errors, warnings = config_concerns(config, {})
    assert any("node-01" in e and "reused" in e for e in errors)
    assert warnings == []


def test_config_concerns_flags_empty_node_id() -> None:
    config = parse_config({"nodes": [{"lat": 1.0, "lon": 1.0}]})
    errors, _warnings = config_concerns(config, {})
    assert any("empty or missing node_id" in e for e in errors)


def test_config_concerns_flags_unknown_top_level_key() -> None:
    doc = {"name": "x", "unexpected_key": True}
    config = parse_config(doc)
    errors, _warnings = config_concerns(config, doc)
    assert any("unknown top-level key 'unexpected_key'" in e for e in errors)


def test_config_concerns_flags_typo_alert_threshold_key() -> None:
    # heat_index (missing the _c suffix) silently fails to override the default at runtime —
    # this must be a loud error, not a silent drop.
    config = parse_config({"alert_thresholds": {"heat_index": 37.0}})
    errors, _warnings = config_concerns(config, {})
    assert any("unknown key 'heat_index'" in e and "heat_index_c" in e for e in errors)


def test_config_concerns_accepts_known_alert_threshold_keys() -> None:
    config = parse_config({"alert_thresholds": {"pm25_aqi": 120.0, "heat_index_c": 40.0}})
    errors, _warnings = config_concerns(config, {})
    assert errors == []


def test_config_concerns_flags_out_of_range_lat_lon() -> None:
    config = parse_config({"nodes": [{"node_id": "node-01", "lat": 200.0, "lon": -400.0}]})
    errors, _warnings = config_concerns(config, {})
    assert any("lat 200.0 is out of range" in e for e in errors)
    assert any("lon -400.0 is out of range" in e for e in errors)


def test_config_concerns_warns_not_errors_on_bad_location() -> None:
    node = NodeConfig(node_id="node-01", lat=1.0, lon=1.0, location="exact")
    config = NetworkConfig(nodes=(node,))
    errors, warnings = config_concerns(config, {})
    assert errors == []
    assert any("location 'exact'" in w and "coarse" in w for w in warnings)
    # Fail-safe behaviour is unchanged: an unrecognized location still snaps to the grid.
    assert node.public_location(150.0) != (1.0, 1.0)


def test_config_concerns_warns_on_unresolved_calibration_window_references() -> None:
    config = parse_config(
        {
            "nodes": [{"node_id": "node-01", "lat": 1.0, "lon": 1.0}],
            "calibration_windows": [
                {
                    "node_id": "node-99",
                    "reference": "ref-99",
                    "parameter": "pm25_ugm3",
                    "start": "2026-01-01T00:00:00Z",
                    "end": "2026-01-02T00:00:00Z",
                }
            ],
        }
    )
    errors, warnings = config_concerns(config, {})
    assert errors == []
    assert any("node_id 'node-99'" in w for w in warnings)
    assert any("reference 'ref-99'" in w for w in warnings)
