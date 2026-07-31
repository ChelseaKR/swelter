"""The built-in worked example and its statewide static presentation stay separate and honest."""

from __future__ import annotations

import json
import random
import runpy
from dataclasses import replace
from pathlib import Path

from swelter.config import (
    WEB_PREVIEW_STATEWIDE_CALIFORNIA,
    config_concerns,
    is_builtin_demo_web_preview,
    load_config,
    parse_config,
)
from swelter.sources._california_places import CALIFORNIA
from swelter.web_preview import (
    WEB_PREVIEW_NETWORK_NAME,
    WEB_PREVIEW_REFERENCE_LABEL,
    config_for_web,
    statewide_assignments,
)

from .conftest import ROOT


def test_demo_web_preview_is_deterministic_statewide_and_geographically_mixed() -> None:
    source = load_config(ROOT / "network.yaml")
    assert source.web_preview == WEB_PREVIEW_STATEWIDE_CALIFORNIA

    preview = config_for_web(source)
    assert preview == config_for_web(source)
    assert preview is not source
    assert source.name == "swelter demo network (downtown)"
    assert source.reference_monitors[0].label == "Regulatory AQS station (downtown)"
    assert preview.name == WEB_PREVIEW_NETWORK_NAME
    assert {monitor.label for monitor in preview.reference_monitors} == {
        WEB_PREVIEW_REFERENCE_LABEL
    }

    # The stored worked example remains its compact Sacramento calibration grid.
    source_lats = [node.lat for node in source.nodes if node.lat is not None]
    source_lons = [node.lon for node in source.nodes if node.lon is not None]
    assert max(source_lats) - min(source_lats) < 0.1
    assert max(source_lons) - min(source_lons) < 0.1

    validated = set(CALIFORNIA)
    published = {(node.label, node.lat, node.lon) for node in preview.nodes}
    assert len(published) == len(source.nodes) == 150
    assert published <= validated
    assert all(node.location == "precise" for node in preview.nodes)

    # Calibration belongs to node ids, not geography. Both confirmed and provisional groups must
    # span the state instead of becoming a synthetic north/south coverage divide.
    calibrated = {window.node_id for window in source.calibration_windows}
    assert all(node.lat is not None for node in preview.nodes)
    confirmed_lats = [
        node.lat for node in preview.nodes if node.node_id in calibrated and node.lat is not None
    ]
    provisional_lats = [
        node.lat
        for node in preview.nodes
        if node.node_id not in calibrated and node.lat is not None
    ]
    assert len(confirmed_lats) == 100
    assert len(provisional_lats) == 50
    assert max(confirmed_lats) - min(confirmed_lats) > 8
    assert max(provisional_lats) - min(provisional_lats) > 8
    assert min(confirmed_lats) < max(provisional_lats)
    assert min(provisional_lats) < max(confirmed_lats)


def test_statewide_assignment_does_not_depend_on_input_order() -> None:
    ids = ["node-02", "node-01", "node-03"]
    assert statewide_assignments(ids) == statewide_assignments(reversed(ids))


def test_committed_surface_and_health_use_the_configured_assignment() -> None:
    surface = json.loads((ROOT / "web" / "sample-surface.json").read_text(encoding="utf-8"))
    health = json.loads((ROOT / "web" / "sample-health.json").read_text(encoding="utf-8"))
    node_ids = {str(node) for cell in surface["cells"] for node in cell["nodes"]}
    assignments = statewide_assignments(node_ids)

    by_cell: dict[str, str] = {}
    for cell in surface["cells"]:
        assert len(cell["nodes"]) == 1
        name, lat, lon = assignments[str(cell["nodes"][0])]
        assert (cell["cell_id"], cell["label"], cell["lat"], cell["lon"]) == (
            f"{lat:.6f},{lon:.6f}",
            name,
            lat,
            lon,
        )
        by_cell[str(cell["cell_id"])] = str(cell["label"])

    coverage = health["coverage_equity"]["cells"]
    assert len(coverage) == len(by_cell) == 150
    assert all(by_cell.get(str(cell["cell_id"])) == cell["label"] for cell in coverage)
    references = {str(cell["reference"]) for cell in surface["cells"] if "reference" in cell}
    assert references == {WEB_PREVIEW_REFERENCE_LABEL}

    alerts = json.loads((ROOT / "web" / "alerts.json").read_text(encoding="utf-8"))
    assert alerts["network"] == WEB_PREVIEW_NETWORK_NAME
    for filename in (
        "sample-surface.json",
        "sample-health.json",
        "alerts.json",
        "alerts.xml",
        "alerts.es.xml",
    ):
        assert "downtown" not in (ROOT / "web" / filename).read_text(encoding="utf-8").casefold()


def test_unknown_web_preview_mode_fails_config_validation() -> None:
    doc = {"web_preview": "statewide-californa"}
    config = parse_config(doc)
    errors, _warnings = config_concerns(config, doc)
    assert any("web_preview: unknown mode" in error for error in errors)


def test_preview_marker_cannot_remap_a_community_network() -> None:
    source = load_config(ROOT / "network.yaml")
    original_lat = source.nodes[0].lat
    assert original_lat is not None
    changed_node = replace(source.nodes[0], lat=original_lat + 0.01)
    community = replace(source, nodes=(changed_node, *source.nodes[1:]))
    assert not is_builtin_demo_web_preview(community)
    assert config_for_web(community) is community

    doc = {"name": community.name, "web_preview": community.web_preview, "nodes": []}
    errors, _warnings = config_concerns(community, doc)
    assert any("does not match the exact generated synthetic fixture" in error for error in errors)


def test_custom_demo_size_does_not_claim_the_canonical_statewide_preview(tmp_path: Path) -> None:
    generator = runpy.run_path(str(ROOT / "scripts" / "gen_demo_data.py"))
    nodes = generator[
        "build_nodes"
    ](
        random.Random(generator["SEED"])  # noqa: S311 -- deterministic test data (#107)
    )[:3]
    generator["write_network_yaml"](nodes, root=tmp_path)

    custom = load_config(tmp_path / "network.yaml")
    assert custom.web_preview == ""
    assert len(custom.nodes) == 3
