"""The exposure brief counts Danger days using alerts.py's own threshold logic, joins optional
sourced context by cell, and never fabricates a line for context it doesn't have."""

from __future__ import annotations

from swelter import aggregate, exposure_brief
from swelter.ac_access_layer import ACAccessCell
from swelter.ac_access_layer import from_cells as ac_from_cells
from swelter.config import NetworkConfig, NodeConfig
from swelter.context_layers import ContextCell
from swelter.context_layers import from_cells as canopy_from_cells
from swelter.models import Observation
from swelter.redlining_layer import RedliningCell
from swelter.redlining_layer import from_cells as redlining_from_cells

from .conftest import make_obs

_NODE = NodeConfig(
    node_id="node-01", label="Oak & 4th", lat=38.5816, lon=-121.4944, location="precise"
)
_CONFIG = NetworkConfig(grid_resolution_m=150.0, nodes=(_NODE,))
_CELL_ID = "38.581600,-121.494400"


def _surface(*obs: Observation) -> aggregate.Surface:
    return aggregate.aggregate(obs, _CONFIG)


# -- count_danger_days --------------------------------------------------------


def test_no_data_means_the_cell_is_absent_not_zero() -> None:
    surface = _surface(make_obs(parameter="pm25_ugm3", unit="ug/m3", value=5.0, calibration="v1"))
    counts = exposure_brief.count_danger_days(surface)  # default parameter: heat_index_c
    assert counts == {}


def test_counts_only_days_that_actually_crossed_the_floor() -> None:
    surface = _surface(
        # Day 1: one hour crosses Danger (41 C), one does not.
        make_obs(
            parameter="heat_index_c", timestamp="2026-06-01T14:00:00Z", value=41.0, calibration="v1"
        ),
        make_obs(
            parameter="heat_index_c", timestamp="2026-06-01T02:00:00Z", value=22.0, calibration="v1"
        ),
        # Day 2: stays below Danger all day.
        make_obs(
            parameter="heat_index_c", timestamp="2026-06-02T14:00:00Z", value=30.0, calibration="v1"
        ),
        # Day 3: crosses again.
        make_obs(
            parameter="heat_index_c", timestamp="2026-06-03T15:00:00Z", value=42.5, calibration="v1"
        ),
    )
    counts = exposure_brief.count_danger_days(surface)
    count = counts[_CELL_ID]
    assert count.days_observed == 3
    assert count.danger_days == 2
    assert count.severity == "Danger"
    assert count.floor == 39.4
    assert count.period_start == "2026-06-01"
    assert count.period_end == "2026-06-03"


def test_custom_threshold_changes_the_count() -> None:
    surface = _surface(
        make_obs(
            parameter="heat_index_c", timestamp="2026-06-01T14:00:00Z", value=33.0, calibration="v1"
        )
    )
    default_counts = exposure_brief.count_danger_days(surface)
    assert default_counts[_CELL_ID].danger_days == 0  # below the default 39.4 floor

    lowered = exposure_brief.count_danger_days(surface, thresholds={"heat_index_c": 32.0})
    assert lowered[_CELL_ID].danger_days == 1


def test_pm25_parameter_uses_the_aqi_floor_and_category_name() -> None:
    surface = _surface(
        # 40 ug/m3 -> AQI ~112, "Unhealthy for Sensitive Groups", past the 101 floor.
        make_obs(
            parameter="pm25_ugm3",
            unit="ug/m3",
            timestamp="2026-06-01T14:00:00Z",
            value=40.0,
            calibration="v1",
        )
    )
    counts = exposure_brief.count_danger_days(surface, parameter="pm25_ugm3")
    count = counts[_CELL_ID]
    assert count.danger_days == 1
    assert count.severity == "Unhealthy for Sensitive Groups"
    assert count.floor == 101.0


# -- ExposureBrief / build_briefs ---------------------------------------------


def _danger_only_surface() -> aggregate.Surface:
    return _surface(
        make_obs(
            parameter="heat_index_c", timestamp="2026-06-01T14:00:00Z", value=41.0, calibration="v1"
        )
    )


def test_brief_with_no_context_has_only_the_danger_line() -> None:
    briefs = exposure_brief.build_briefs(_danger_only_surface())
    brief = briefs[_CELL_ID]
    lines = brief.lines()
    assert len(lines) == 1
    assert "Danger" in lines[0]
    assert "1 of 1 day(s)" in lines[0]
    assert brief.canopy is None
    assert brief.ac_access is None
    assert brief.redlining is None


def test_brief_joins_all_three_context_layers_by_cell_id() -> None:
    canopy = canopy_from_cells(
        [
            ContextCell(
                lat=38.5816,
                lon=-121.4944,
                canopy_pct=27.5,
                cell_id=_CELL_ID,
                source="USDA Forest Service",
                source_url="https://www.fs.usda.gov/r05/state-private-tribal/california-urban-canopy-data",
                last_verified="2026-07-09",
            )
        ]
    )
    ac_access = ac_from_cells(
        [
            ACAccessCell(
                lat=38.5816,
                lon=-121.4944,
                no_ac_pct=22.0,
                cell_id=_CELL_ID,
                source="U.S. Census Bureau (LACE)",
                source_url="https://www.census.gov/data/experimental-data-products/lace.html",
                last_verified="2026-07-09",
            )
        ]
    )
    redlining = redlining_from_cells(
        [
            RedliningCell(
                lat=38.5816,
                lon=-121.4944,
                holc_grade="D",
                cell_id=_CELL_ID,
                source="Mapping Inequality",
                source_url="https://dsl.richmond.edu/panorama/redlining/",
                last_verified="2026-07-09",
            )
        ]
    )
    briefs = exposure_brief.build_briefs(
        _danger_only_surface(), canopy=canopy, ac_access=ac_access, redlining=redlining
    )
    brief = briefs[_CELL_ID]
    lines = brief.lines()
    assert len(lines) == 4
    assert "27.5%" in lines[1] and "USDA Forest Service" in lines[1]
    assert "22%" in lines[2] and "may lack air" in lines[2] and "LACE" in lines[2]
    assert 'grade D ("Hazardous")' in lines[3] and "Mapping Inequality" in lines[3]
    assert "https://dsl.richmond.edu/panorama/redlining/" in lines[3]

    record = brief.as_record()
    canopy_record = record["canopy"]
    ac_record = record["ac_access"]
    redlining_record = record["redlining"]
    assert isinstance(canopy_record, dict) and canopy_record["canopy_pct"] == 27.5
    assert isinstance(ac_record, dict) and ac_record["no_ac_pct"] == 22.0
    assert isinstance(redlining_record, dict) and redlining_record["holc_grade"] == "D"
    assert brief.to_text() == "\n".join(lines)


def test_context_layer_with_no_coverage_for_this_cell_is_omitted() -> None:
    canopy = canopy_from_cells(
        [ContextCell(lat=10.0, lon=10.0, canopy_pct=50.0, cell_id="10.000000,10.000000")]
    )
    briefs = exposure_brief.build_briefs(_danger_only_surface(), canopy=canopy)
    assert briefs[_CELL_ID].canopy is None
    assert len(briefs[_CELL_ID].lines()) == 1


def test_build_brief_returns_none_for_unreported_area() -> None:
    result = exposure_brief.build_brief("not,acell", _danger_only_surface())
    assert result is None


def test_build_brief_returns_the_area_when_present() -> None:
    result = exposure_brief.build_brief(_CELL_ID, _danger_only_surface())
    assert result is not None
    assert result.area_id == _CELL_ID
