"""The Pages artifact must describe the surface that actually won the source fallback."""

from __future__ import annotations

import json
import runpy
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import pytest

from .conftest import ROOT

SCRIPT = ROOT / "scripts" / "build_demo_contract.py"
NAMESPACE = runpy.run_path(str(SCRIPT))
build_contract = cast(Callable[..., dict[str, Any]], NAMESPACE["build_contract"])
main = cast(Callable[[], int], NAMESPACE["main"])


ATTRIBUTIONS = {
    "openaq": "Real readings accessed via OpenAQ; original providers vary.",
    "openmeteo": "Real hourly readings for California cities from the Copernicus Atmosphere model.",
    "sensor-community": "Real readings from the Sensor.Community network.",
    "synthetic": "Synthetic demonstration data — no real sensors.",
}


def _surface(
    states: list[bool],
    parameters: tuple[str, ...] = ("pm25_ugm3",),
    *,
    source: str = "openaq",
) -> dict[str, Any]:
    cells = []
    for i, provisional in enumerate(states):
        for parameter in parameters:
            cells.append(
                {
                    "cell_id": f"cell-{i}",
                    "bucket": "2026-07-09T12:00:00Z",
                    "parameter": parameter,
                    "provisional": provisional,
                }
            )
    return {
        "attribution": ATTRIBUTIONS[source],
        "buckets": ["2026-07-09T12:00:00Z"],
        "cells": cells,
    }


@pytest.mark.parametrize(
    ("source", "states", "mode"),
    [
        ("openaq", [True], "all_provisional"),
        ("sensor-community", [True], "all_provisional"),
        ("openmeteo", [False], "all_confirmed"),
        ("synthetic", [True, False], "mixed"),
    ],
)
def test_each_source_profile_agrees_with_its_surface(
    source: str, states: list[bool], mode: str
) -> None:
    contract = build_contract(
        source,
        _surface(states, ("pm10_ugm3", "pm25_ugm3"), source=source),
    )

    assert contract["runtime"] == "static"
    assert contract["source"]["id"] == source
    assert contract["surface"]["calibration_mode"] == mode
    assert contract["surface"]["parameters"] == ["pm25_ugm3", "pm10_ugm3"]
    assert contract["attribution"] == contract["source"]["attribution"]["en"]
    assert contract["build_input_attribution"] == ATTRIBUTIONS[source]
    assert contract["source"]["name"]["en"]
    assert contract["source"]["name"]["es"]
    assert contract["source"]["uncertainty"]["en"]
    assert contract["source"]["location"]["es"]
    assert contract["source"]["license"]["links"]


def test_cams_uses_model_terminology_instead_of_claiming_sensor_calibration() -> None:
    contract = build_contract("openmeteo", _surface([False], source="openmeteo"))
    terms = contract["source"]["terminology"]

    assert terms["non_provisional_label"] == {"en": "Upstream model", "es": "Modelo externo"}
    assert "not a Swelter sensor calibration" in terms["non_provisional_explanation"]["en"]


def test_source_terms_match_current_primary_policies() -> None:
    openaq = build_contract("openaq", _surface([True]))["source"]["license"]
    sensor_community = build_contract(
        "sensor-community", _surface([True], source="sensor-community")
    )["source"]["license"]
    openmeteo = build_contract("openmeteo", _surface([False], source="openmeteo"))["source"][
        "license"
    ]

    assert openaq["name"] == "Provider-specific OpenAQ terms"
    assert "every original data provider" in openaq["credit_text"]["en"]
    assert sensor_community["name"] == "Open Data Commons DbCL 1.0"
    assert sensor_community["url"].endswith("/licenses/dbcl/1-0/")
    assert openmeteo["name"] == "CC BY 4.0"
    assert openmeteo["url"] == "https://open-meteo.com/en/licence"


def test_contract_fails_closed_when_source_status_and_surface_disagree() -> None:
    with pytest.raises(ValueError, match="claims all_provisional.*all_confirmed"):
        build_contract("openaq", _surface([False]))


def test_contract_rejects_measurements_the_dashboard_cannot_name() -> None:
    with pytest.raises(ValueError, match="no label/control"):
        build_contract("openaq", _surface([True], ("ozone_ppb",)))


def test_contract_rejects_a_different_raw_sensor_source_with_the_same_status_mode() -> None:
    with pytest.raises(ValueError, match="does not match the baked surface attribution"):
        build_contract("openaq", _surface([True], source="sensor-community"))


def test_contract_accepts_estimated_wbgt_supported_by_the_current_dashboard() -> None:
    contract = build_contract("synthetic", _surface([True, False], ("wbgt_c",), source="synthetic"))

    assert contract["surface"]["parameters"] == ["wbgt_c"]


def test_fallback_route_names_the_source_it_is_actually_showing() -> None:
    contract = build_contract(
        "openmeteo",
        _surface([False], source="openmeteo"),
        fallback_for="sensor-community",
    )

    assert contract["source"]["id"] == "openmeteo"
    assert contract["fallback"]["requested_source"] == "sensor-community"
    assert contract["fallback"]["message"]["en"]
    assert contract["fallback"]["message"]["es"]


def test_cli_writes_deterministic_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    surface_path = tmp_path / "surface.json"
    output_path = tmp_path / "demo.json"
    surface_path.write_text(json.dumps(_surface([True])), encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(SCRIPT),
            "--source",
            "openaq",
            "--surface",
            str(surface_path),
            "--output",
            str(output_path),
        ],
    )

    assert main() == 0
    first = output_path.read_text(encoding="utf-8")
    assert main() == 0
    assert output_path.read_text(encoding="utf-8") == first
    assert json.loads(first)["source"]["id"] == "openaq"


def test_pages_build_records_each_fallback_winner() -> None:
    workflow = (ROOT / ".github" / "workflows" / "pages.yml").read_text(encoding="utf-8")

    assert "primary_source=synthetic" in workflow
    assert "primary_source=openaq" in workflow
    assert "primary_source=openmeteo" in workflow
    assert workflow.count('build_demo_contract.py --source "$primary_source"') == 2
    assert "build_demo_contract.py --source sensor-community" in workflow
    assert "--fallback-for sensor-community" in workflow


def test_static_runtime_uses_baked_files_without_api_probes() -> None:
    app = (ROOT / "web" / "app.js").read_text(encoding="utf-8")

    assert "state.demo = await loadDemoContract()" in app
    assert 'isStaticDeployment() ? null : await fetchJson("api/alerts.json")' in app
    assert 'isStaticDeployment() ? null : await fetchSurface("api/surface.json?hours=168")' in app
    assert '? await fetchSurface("sample-surface.json")' in app


def test_offline_shell_caches_the_contract_when_present_without_requiring_it() -> None:
    worker = (ROOT / "web" / "sw.js").read_text(encoding="utf-8")

    assert 'const OPTIONAL_SHELL = ["demo.json"]' in worker
    assert "Promise.allSettled" in worker


def test_static_shell_avoids_fixed_source_and_license_claims() -> None:
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")

    assert 'id="dataset-truth"' in html
    assert "California · CAMS model" not in html
    assert "Stuttgart · real sensors" not in html
    assert "All readings are public-domain (CC0)" not in html
