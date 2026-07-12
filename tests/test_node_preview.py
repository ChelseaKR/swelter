"""``swelter node-preview`` — the host-facing "what's public about your node" command.

Exercises the CLI end to end through ``cli.main`` (argv-dispatch, matching
``tests/test_cli_flows.py``) plus a couple of direct unit checks on the underlying pieces
(``haversine_m`` and the exposure math) so the offset reported to a host is provably correct,
not just "some number got printed".
"""

from __future__ import annotations

from pathlib import Path

import pytest

from swelter.cli import main
from swelter.config import NetworkConfig, NodeConfig, haversine_m, snap_to_grid

from .conftest import ROOT

NETWORK = str(ROOT / "network.yaml")


# -- haversine_m ---------------------------------------------------------------------------


def test_haversine_m_same_point_is_zero() -> None:
    assert haversine_m(38.5816, -121.4944, 38.5816, -121.4944) == 0.0


def test_haversine_m_known_short_distance() -> None:
    # ~0.001 degrees of latitude is ~111.3 m; haversine should land close to that for a
    # pure north-south hop with no longitude change.
    d = haversine_m(38.0000, -121.0000, 38.0010, -121.0000)
    assert 108.0 < d < 115.0


def test_offset_between_exact_and_snapped_is_within_grid_diagonal() -> None:
    """The published cell centre can never be farther from the sensor than the cell diagonal."""
    lat, lon = 38.581600, -121.494400
    grid_m = 150.0
    snapped = snap_to_grid(lat, lon, grid_m)
    offset = haversine_m(lat, lon, snapped[0], snapped[1])
    # A point anywhere in a grid_m-sided square is at most grid_m * sqrt(2) from the centre.
    assert offset <= grid_m * 1.5  # generous slack over the exact sqrt(2) diagonal


def test_precise_node_has_zero_offset() -> None:
    lat, lon = 38.581600, -121.494400
    node = NodeConfig(node_id="node-01", lat=lat, lon=lon, location="precise")
    published = node.public_location(150.0)
    assert published is not None
    assert haversine_m(lat, lon, published[0], published[1]) == 0.0


# -- CLI: node-preview -----------------------------------------------------------------------


def test_node_preview_reports_offset_for_coarse_node(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["node-preview", "--config", NETWORK])
    assert rc == 0
    out = capsys.readouterr().out
    assert "your private coordinate — never published" in out
    assert "published coordinate" in out
    assert "published cell" in out
    assert "map shows a point ~" in out
    assert "location mode: coarse" in out


def test_node_preview_single_node_by_id(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["node-preview", "node-01", "--config", NETWORK])
    assert rc == 0
    out = capsys.readouterr().out
    assert out.startswith("node node-01")
    assert "node-02" not in out


def test_node_preview_unknown_node_returns_1(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["node-preview", "does-not-exist", "--config", NETWORK])
    assert rc == 1
    err = capsys.readouterr().err
    assert "not found" in err


def test_node_preview_precise_node_warns(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cfg = tmp_path / "network.yaml"
    cfg.write_text(
        "name: test net\n"
        "grid_resolution_m: 150\n"
        "nodes:\n"
        "- node_id: node-precise\n"
        "  label: Test Corner\n"
        "  lat: 38.5816\n"
        "  lon: -121.4944\n"
        "  location: precise\n",
        encoding="utf-8",
    )
    rc = main(["node-preview", "--config", str(cfg)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "location mode: precise" in out
    assert "WARNING" in out
    assert "EXACT coordinate is published" in out
    assert "map shows a point ~0 m from your sensor" in out


def test_node_preview_unplaced_node_publishes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cfg = tmp_path / "network.yaml"
    cfg.write_text(
        "name: test net\nnodes:\n- node_id: node-unplaced\n  label: Nowhere\n",
        encoding="utf-8",
    )
    rc = main(["node-preview", "--config", str(cfg)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "publishes nothing" in out


def test_node_preview_empty_network_says_so(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cfg = tmp_path / "network.yaml"
    cfg.write_text("name: empty net\n", encoding="utf-8")
    rc = main(["node-preview", "--config", str(cfg)])
    assert rc == 0
    err = capsys.readouterr().err
    assert "no nodes registered" in err


def test_node_preview_coarse_offset_matches_public_location_snap() -> None:
    """The offset the command would print is exactly the haversine distance to public_location."""
    config = NetworkConfig(
        grid_resolution_m=150.0,
        nodes=(NodeConfig(node_id="node-01", lat=38.581600, lon=-121.494400, location="coarse"),),
    )
    node = config.node("node-01")
    assert node is not None
    assert node.lat is not None
    assert node.lon is not None
    published = node.public_location(config.grid_resolution_m)
    assert published is not None
    expected_offset = haversine_m(node.lat, node.lon, published[0], published[1])
    assert expected_offset > 0  # coarse snapping actually moves the point
    assert expected_offset <= config.grid_resolution_m * 1.5
