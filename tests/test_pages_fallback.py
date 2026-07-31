"""Regression checks for the route-specific Pages fallback."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_sensor_community_fallback_restores_california_basemap_before_publish() -> None:
    workflow = (ROOT / ".github" / "workflows" / "pages.yml").read_text(encoding="utf-8")
    sensor_route = workflow.split('# Page 2 ("/sensors/"):', 1)[1]
    success, fallback = sensor_route.split("\n          else\n", 1)

    assert "rm -f web/sensors/basemap.geojson" in success
    assert "cp web/basemap.geojson web/sensors/basemap.geojson" not in success

    restore = fallback.index("cp web/basemap.geojson web/sensors/basemap.geojson")
    contract = fallback.index('build_demo_contract.py --source "$primary_source"')
    publish = fallback.index('swelter publish --store "$SOURCE1_STORE" --web web/sensors')
    assert restore < contract < publish
