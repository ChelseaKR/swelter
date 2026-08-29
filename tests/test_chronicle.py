"""The event chronicle counts Danger/compound cell-hours and coverage confidence descriptively,
always renders a non-empty "what the network could not see" section, and never ranks or attributes.

Deterministic and offline: observations are built with the ``make_obs`` factory and written to the
throwaway ``store`` fixture, then read back through the ``Store`` seam exactly as the CLI does.
"""

from __future__ import annotations

from swelter import chronicle
from swelter.config import NetworkConfig, NodeConfig
from swelter.models import RAW
from swelter.store import SqliteStore

from .conftest import make_obs

_NODE = NodeConfig(
    node_id="node-01", label="Oak & 4th", lat=38.5816, lon=-121.4944, location="precise"
)
_CONFIG = NetworkConfig(name="Demo network", grid_resolution_m=150.0, nodes=(_NODE,))
_CELL_ID = "38.581600,-121.494400"
_START = "2026-06-01T00:00:00Z"
_END = "2026-06-01T23:00:00Z"


def _hour(hour: int) -> str:
    return f"2026-06-01T{hour:02d}:00:00Z"


def _chronicle(store: SqliteStore) -> chronicle.Chronicle:
    return chronicle.build_chronicle(store, _CONFIG, start=_START, end=_END)


# -- Danger-hour counting -----------------------------------------------------


def test_counts_hours_over_danger_tier(store: SqliteStore) -> None:
    store.write(
        [
            # 41 C -> NWS "Danger" (level 3); 52 C -> "Extreme Danger" (level 4); 30 C -> below.
            make_obs(parameter="heat_index_c", timestamp=_hour(13), value=41.0, calibration="v1"),
            make_obs(parameter="heat_index_c", timestamp=_hour(14), value=52.0, calibration="v1"),
            make_obs(parameter="heat_index_c", timestamp=_hour(15), value=30.0, calibration="v1"),
        ]
    )
    record = _chronicle(store)
    cell = record.cells[0]
    assert cell.cell_id == _CELL_ID
    assert cell.observed_hours == 3
    assert cell.danger_hours == 2  # both 41 C and 52 C reached at least Danger
    assert cell.extreme_danger_hours == 1  # only 52 C reached Extreme Danger
    assert record.danger_hours == 2
    assert record.extreme_danger_hours == 1
    # All three readings are calibrated, so coverage confidence is full and none are provisional.
    assert cell.calibrated_readings == 3
    assert cell.provisional_readings == 0
    assert cell.calibrated_share == 1.0


def test_raw_readings_count_as_provisional_coverage(store: SqliteStore) -> None:
    store.write(
        [
            make_obs(parameter="heat_index_c", timestamp=_hour(14), value=41.0, calibration="v1"),
            make_obs(parameter="heat_index_c", timestamp=_hour(15), value=42.0, calibration=RAW),
        ]
    )
    record = _chronicle(store)
    cell = record.cells[0]
    # A raw reading still counts its Danger hour, but lands on the provisional side of the share.
    assert cell.danger_hours == 2
    assert cell.calibrated_readings == 1
    assert cell.provisional_readings == 1
    assert cell.calibrated_share == 0.5
    assert "provisional" in record.to_markdown()


# -- Compound-exposure hours --------------------------------------------------


def test_compound_hours_counts_both_heat_and_air_elevated(store: SqliteStore) -> None:
    store.write(
        [
            # Hour 14: heat Danger (41 C) AND air elevated (40 ug/m3 -> "Unhealthy for Sensitive
            # Groups") -> compound. Hour 15: heat elevated but air clean (5 ug/m3) -> not compound.
            make_obs(parameter="heat_index_c", timestamp=_hour(14), value=41.0, calibration="v1"),
            make_obs(
                parameter="pm25_ugm3",
                unit="ug/m3",
                timestamp=_hour(14),
                value=40.0,
                calibration="v1",
            ),
            make_obs(parameter="heat_index_c", timestamp=_hour(15), value=41.0, calibration="v1"),
            make_obs(
                parameter="pm25_ugm3",
                unit="ug/m3",
                timestamp=_hour(15),
                value=5.0,
                calibration="v1",
            ),
        ]
    )
    record = _chronicle(store)
    cell = record.cells[0]
    assert cell.compound_hours == 1
    assert record.compound_hours == 1
    assert "both heat and air elevated" in record.to_markdown()


# -- "What the network could not see" -----------------------------------------


def test_could_not_see_section_is_present_with_zero_gaps(store: SqliteStore) -> None:
    # Two consecutive hourly raw readings: detect_gaps runs and finds nothing, so the section must
    # still render — "we saw nothing wrong" and "we could not see" are never collapsed by omission.
    store.write(
        [
            make_obs(parameter="heat_index_c", timestamp=_hour(14), value=41.0, calibration=RAW),
            make_obs(parameter="heat_index_c", timestamp=_hour(15), value=42.0, calibration=RAW),
        ]
    )
    record = _chronicle(store)
    assert record.gaps == ()
    markdown = record.to_markdown()
    assert "## What the network could not see" in markdown
    assert "Reporting gaps: none longer than the sampling interval were detected." in markdown
    # Provisional accounting is first-class, not a footnote.
    assert "Provisional coverage:" in markdown


def test_reporting_gaps_are_reported_when_present(store: SqliteStore) -> None:
    # Two raw readings six hours apart at an hourly interval -> one detected gap.
    store.write(
        [
            make_obs(parameter="heat_index_c", timestamp=_hour(0), value=41.0, calibration=RAW),
            make_obs(parameter="heat_index_c", timestamp=_hour(6), value=41.0, calibration=RAW),
        ]
    )
    record = _chronicle(store)
    assert len(record.gaps) == 1
    markdown = record.to_markdown()
    assert "Reporting gaps (1):" in markdown
    assert "node-01/heat_index_c" in markdown


# -- Descriptive-only discipline and citability -------------------------------


def test_markdown_refuses_attribution_and_ranking(store: SqliteStore) -> None:
    store.write(
        [make_obs(parameter="heat_index_c", timestamp=_hour(14), value=41.0, calibration="v1")]
    )
    markdown = _chronicle(store).to_markdown()
    assert "does not attribute health outcomes" in markdown
    assert "does not rank, score, or compare" in markdown
    # The coverage-equity refusal note travels verbatim into the chronicle.
    assert "not a ranking of neighborhoods" in markdown


def test_source_digest_is_deterministic_and_data_sensitive(store: SqliteStore) -> None:
    store.write(
        [make_obs(parameter="heat_index_c", timestamp=_hour(14), value=41.0, calibration="v1")]
    )
    first = _chronicle(store).source_digest
    second = _chronicle(store).source_digest
    assert first == second  # same window, same store -> same digest
    store.write(
        [make_obs(parameter="heat_index_c", timestamp=_hour(15), value=42.0, calibration="v1")]
    )
    assert _chronicle(store).source_digest != first  # a new reading changes the digest


def test_empty_window_still_renders_a_chronicle(store: SqliteStore) -> None:
    record = _chronicle(store)  # nothing written
    assert record.cells == ()
    assert record.calibrated_share is None
    markdown = record.to_markdown()
    assert "no published cells reported in this window" in markdown
    assert "## What the network could not see" in markdown


# -- how much of the Danger count swelter vouches for (issue #199, ADR 0046) --


def test_danger_hours_from_a_qc_flagged_spike_are_counted_and_named(store: SqliteStore) -> None:
    store.write(
        [
            make_obs(parameter="heat_index_c", timestamp=_hour(13), value=41.0, calibration="v1"),
            # QC already called this one an implausible spike; it is still an hour a reader must
            # be able to see (ADR 0029), so it is counted and then qualified, never dropped.
            make_obs(parameter="heat_index_c", timestamp=_hour(14), value=95.0, qc="spike"),
        ]
    )
    record = _chronicle(store)
    cell = record.cells[0]
    assert cell.danger_hours == 2
    assert cell.danger_hours_provisional == 1
    assert cell.danger_hours_qc_flagged == 1
    assert record.danger_hours_provisional == 1
    assert record.danger_hours_qc_flagged == 1


def test_an_uncalibrated_danger_hour_is_provisional_but_not_flagged(store: SqliteStore) -> None:
    store.write(
        [make_obs(parameter="heat_index_c", timestamp=_hour(14), value=41.0, calibration=RAW)]
    )
    cell = _chronicle(store).cells[0]
    assert cell.danger_hours == 1
    assert cell.danger_hours_provisional == 1
    assert cell.danger_hours_qc_flagged == 0


def test_a_calibrated_danger_hour_is_on_neither_untrusted_count(store: SqliteStore) -> None:
    store.write(
        [make_obs(parameter="heat_index_c", timestamp=_hour(14), value=41.0, calibration="v1")]
    )
    cell = _chronicle(store).cells[0]
    assert cell.danger_hours == 1
    assert cell.danger_hours_provisional == 0
    assert cell.danger_hours_qc_flagged == 0


def test_the_document_states_the_untrusted_danger_hours(store: SqliteStore) -> None:
    store.write(
        [
            make_obs(parameter="heat_index_c", timestamp=_hour(13), value=41.0, calibration="v1"),
            make_obs(parameter="heat_index_c", timestamp=_hour(14), value=95.0, qc="spike"),
        ]
    )
    markdown = _chronicle(store).to_markdown()
    # Headline, always-rendered caveat section, and the per-cell table all carry the split, so a
    # figure cannot be quoted out of the document without the caveat that bounds it.
    assert "1 of the Danger cell-hour(s) came from a provisional reading" in markdown
    assert "1 of those from a reading QC flagged as suspicious" in markdown
    assert "Danger hours resting on untrusted readings: 1 of 2 Danger cell-hour(s)" in markdown
    assert "| Danger hours provisional | Danger hours QC-flagged |" in markdown


def test_the_untrusted_danger_hour_line_is_rendered_even_at_zero(store: SqliteStore) -> None:
    """Never collapsed by omission: "nothing in doubt" is a claim, and it gets stated."""
    store.write(
        [make_obs(parameter="heat_index_c", timestamp=_hour(14), value=41.0, calibration="v1")]
    )
    markdown = _chronicle(store).to_markdown()
    assert "Danger hours resting on untrusted readings: 0 of 1 Danger cell-hour(s)" in markdown
    assert "0 of the Danger cell-hour(s) came from a provisional reading" in markdown
