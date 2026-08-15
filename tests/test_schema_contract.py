"""The Python/JS surface contract (FIX-07): emitter output validated against `schemas/*.json`.

These schemas are the shared, versioned contract between the Python emitters
(`aggregate.CellReading.as_record`, `qc.health_report`, `alerts.AlertFeed.to_json`) and the
JavaScript dashboard consumer (`web/app.js`). `web/tests/schema-contract.test.js` validates the
same fixture files against the same schemas from the JS side. A deliberate field change on either
side must edit the schema and both tests in the same PR — that is the point of a contract: it
fails loud, not quiet.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema
import pytest

from swelter import aggregate, alerts, qc
from swelter.config import NetworkConfig, NodeConfig

from .conftest import make_obs

ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "schemas"
WEB = ROOT / "web"

_NODE = NodeConfig(
    node_id="node-01", label="Oak & 4th", lat=38.5816, lon=-121.4944, location="precise"
)
_CONFIG = NetworkConfig(grid_resolution_m=150.0, nodes=(_NODE,))


def _schema(name: str) -> dict[str, Any]:
    payload: dict[str, Any] = json.loads((SCHEMAS / name).read_text(encoding="utf-8"))
    return payload


def _validate(payload: object, schema_name: str) -> None:
    jsonschema.validate(payload, _schema(schema_name))


# -- the committed dashboard fixtures, exactly as `web/app.js` fetches them -------------------


def test_committed_sample_surface_matches_schema() -> None:
    payload = json.loads((WEB / "sample-surface.json").read_text(encoding="utf-8"))
    _validate(payload, "sample-surface.schema.json")


def test_committed_sample_health_matches_schema() -> None:
    payload = json.loads((WEB / "sample-health.json").read_text(encoding="utf-8"))
    _validate(payload, "sample-health.schema.json")


def test_committed_alerts_matches_schema() -> None:
    payload = json.loads((WEB / "alerts.json").read_text(encoding="utf-8"))
    _validate(payload, "alerts.schema.json")


# -- freshly built emitter output, so a future field change is caught even before the fixtures --
# -- are regenerated ------------------------------------------------------------------------------


def test_freshly_aggregated_surface_matches_schema() -> None:
    surface = aggregate.aggregate(
        [
            make_obs(parameter="pm25_ugm3", unit="ug/m3", value=12.0, calibration="v1"),
            make_obs(parameter="heat_index_c", unit="degC", value=30.0, calibration="v1"),
        ],
        _CONFIG,
    )
    payload = {
        "interval": surface.interval,
        "attribution": "swelter demo network",
        "buckets": sorted({c.bucket for c in surface.cells}),
        "cells": surface.to_records(),
    }
    assert payload["cells"], "the fixture must exercise at least one cell record"
    _validate(payload, "sample-surface.schema.json")


def test_surface_with_an_uncertainty_note_matches_schema() -> None:
    """A cell that publishes no numeric uncertainty carries `uncertainty_note` saying why — on any
    parameter, not just `exposure` (ADR 0037). The fresh emitter output must still validate, so the
    field stays inside the shared Python↔JS contract (FIX-07). The JS side of this same assertion
    is `web/tests/schema-contract.test.js`."""
    surface = aggregate.aggregate(
        [
            make_obs(
                parameter="pm25_ugm3",
                unit="ug/m3",
                timestamp=f"2026-06-01T0{hour}:00:00Z",
                value=value,
                calibration="v1",
                uncertainty=0.8,
            )
            for hour, value in enumerate([8.0, 10.0, 12.0])
        ],
        _CONFIG,
    )
    records = surface.to_records()
    nowcast = [r for r in records if r.get("aqi_window") == "nowcast"]
    assert nowcast, "fixture must exercise a NowCast record"
    assert nowcast[0]["uncertainty"] is None
    assert nowcast[0]["uncertainty_note"], "a null uncertainty must say why"
    payload = {
        "interval": surface.interval,
        "attribution": "swelter demo network",
        "buckets": sorted({c.bucket for c in surface.cells}),
        "cells": records,
    }
    _validate(payload, "sample-surface.schema.json")


def test_surface_with_qc_flags_matches_schema() -> None:
    """A suspicious-only cell emits `qc_flags` (ADR 0029); the fresh emitter output must still
    validate, so the new field stays inside the shared Python↔JS contract (FIX-07). The JS side of
    this same assertion is `web/tests/schema-contract.test.js`."""
    surface = aggregate.aggregate(
        [make_obs(parameter="pm25_ugm3", unit="ug/m3", value=420.0, qc="spike")],
        _CONFIG,
    )
    records = surface.to_records()
    assert any(record.get("qc_flags") for record in records), "fixture must exercise a flagged cell"
    payload = {
        "interval": surface.interval,
        "attribution": "swelter demo network",
        "buckets": sorted({c.bucket for c in surface.cells}),
        "cells": records,
    }
    _validate(payload, "sample-surface.schema.json")


def test_freshly_built_health_report_matches_schema() -> None:
    report = qc.health_report(
        [make_obs(parameter="pm25_ugm3", unit="ug/m3", value=12.0, calibration="v1")]
    )
    _validate(report, "sample-health.schema.json")


def test_empty_health_report_matches_schema() -> None:
    """The zero-observations branch (`qc.health_report([])`) is a distinct code path — cover it."""
    _validate(qc.health_report([]), "sample-health.schema.json")


def test_freshly_built_alert_feed_matches_schema() -> None:
    surface = aggregate.aggregate(
        [make_obs(parameter="heat_index_c", unit="degC", value=41.0, calibration="v1")],
        _CONFIG,
    )
    feed = alerts.build_feed(surface, network="demo", base_url="https://example.org")
    assert feed.alerts, "the fixture must exercise at least one raised alert"
    _validate(feed.to_json(), "alerts.schema.json")


def test_quiet_alert_feed_matches_schema() -> None:
    """The zero-alerts branch is a distinct shape (empty `alerts` array) — cover it too."""
    surface = aggregate.aggregate(
        [make_obs(parameter="temp_c", unit="degC", value=20.0, calibration="v1")], _CONFIG
    )
    feed = alerts.build_feed(surface, network="demo", base_url="https://example.org")
    assert feed.alerts == ()
    _validate(feed.to_json(), "alerts.schema.json")


def test_cold_pack_alert_feed_matches_schema() -> None:
    """A non-heat pack's feed carries pack-specific threshold keys (`wind_chill_c`) and parameter
    values, so the contract must accept them — the schema was widened for it, not silently."""
    from swelter import hazard_packs

    cold_config = NetworkConfig(grid_resolution_m=150.0, nodes=(_NODE,), hazard_pack="cold")
    surface = aggregate.aggregate(
        [make_obs(parameter="wind_chill_c", unit="degC", value=-30.0, calibration="v1")],
        cold_config,
    )
    feed = alerts.build_feed(
        surface,
        network="demo",
        base_url="https://example.org",
        pack=hazard_packs.resolve_pack(cold_config.hazard_pack),
    )
    assert feed.alerts and feed.alerts[0].parameter == "wind_chill_c"
    _validate(feed.to_json(), "alerts.schema.json")


# -- the schemas themselves are well-formed JSON Schema (draft 2020-12) -------------------------


@pytest.mark.parametrize(
    "name",
    ["sample-surface.schema.json", "sample-health.schema.json", "alerts.schema.json"],
)
def test_schema_is_valid_json_schema(name: str) -> None:
    jsonschema.Draft202012Validator.check_schema(_schema(name))
