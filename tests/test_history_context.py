"""`history_context`: the per-cell historical percentile, and every way it refuses (#241).

The three acceptance clauses on the issue, each with a named test here:

* a cell with fewer than the minimum hours emits ``history_context: null`` **with a reason** —
  :func:`test_a_cell_below_the_minimum_emits_null_with_a_reason`;
* a synthetic store with a known distribution yields the expected percentile within rounding,
  identically across runs — :func:`test_a_known_distribution_yields_the_expected_percentile` and
  :func:`test_the_same_store_yields_byte_identical_context_across_runs`;
* raw-only history is labelled ``basis: raw`` and rendered as provisional wherever shown —
  :func:`test_raw_only_history_is_labelled_raw` and
  :func:`test_a_raw_basis_is_rendered_as_provisional_in_every_language`.

Everything here is offline and deterministic: no wall clock, no fetch, no climatology.
"""

from __future__ import annotations

from xml.sax.saxutils import escape

import pytest

from swelter import aggregate, alerts, exposure_brief, i18n_alerts
from swelter.aggregate import (
    HISTORY_ABSENT_ORDINAL,
    HISTORY_ABSENT_SINGLE_WINDOW,
    HISTORY_ABSENT_THIN,
    HISTORY_BASIS_CALIBRATED,
    HISTORY_BASIS_RAW,
)
from swelter.config import NetworkConfig, NodeConfig
from swelter.models import RAW, Observation

from .conftest import make_obs

_NODE = NodeConfig(
    node_id="node-01", label="Oak & 4th", lat=38.5816, lon=-121.4944, location="precise"
)
_CELL_ID = "38.581600,-121.494400"


def _config(*, min_hours: int = 5, window_days: int = 730) -> NetworkConfig:
    return NetworkConfig(
        grid_resolution_m=150.0,
        nodes=(_NODE,),
        history_min_hours=min_hours,
        history_window_days=window_days,
    )


def _hours(
    values: list[float],
    *,
    parameter: str = "temp_c",
    unit: str = "degC",
    calibrated: bool = True,
    start_day: str = "2026-06-01",
    start_hour: int = 0,
) -> list[Observation]:
    """One observation per consecutive hour, values in order, all in one calendar month."""
    out: list[Observation] = []
    for offset, value in enumerate(values):
        hour = start_hour + offset
        day = int(start_day[-2:]) + hour // 24
        out.append(
            make_obs(
                parameter=parameter,
                unit=unit,
                timestamp=f"{start_day[:-2]}{day:02d}T{hour % 24:02d}:00:00Z",
                value=value,
                calibration="v1" if calibrated else RAW,
            )
        )
    return out


def _readings(surface: aggregate.Surface, parameter: str = "temp_c") -> list[aggregate.CellReading]:
    return sorted((c for c in surface.cells if c.parameter == parameter), key=lambda c: c.bucket)


# -- clause 1: below the minimum, null AND a reason ------------------------------------------


def test_a_cell_below_the_minimum_emits_null_with_a_reason() -> None:
    """The issue's first clause, and the shape of the refusal: a bare `null` would be read as
    "nothing to report", which is exactly what a resident must not read here."""
    surface = aggregate.aggregate(_hours([20.0, 21.0, 22.0]), _config(min_hours=5))
    records = [r for r in surface.to_records() if r["parameter"] == "temp_c"]
    assert len(records) == 3
    for record in records:
        assert record["history_context"] is None
        reason = record["history_context_reason"]
        assert isinstance(reason, dict)
        assert reason["code"] == HISTORY_ABSENT_THIN
        assert "are required" in reason["note"]
    # The note counts what is actually there, so a reader can see how far off the minimum it is.
    assert "0 earlier recorded temp_c hour(s)" in records[0]["history_context_reason"]["note"]
    assert "2 earlier recorded temp_c hour(s)" in records[2]["history_context_reason"]["note"]


def test_the_issues_own_example_of_a_thin_record_gets_no_percentile() -> None:
    """ "A cell with 40 recorded hours gets no percentile" — the issue says so in terms, and the
    shipped default (72) has to be the reason, not a number a test chose to make this pass."""
    surface = aggregate.aggregate(
        _hours([20.0 + i * 0.1 for i in range(40)]),
        NetworkConfig(grid_resolution_m=150.0, nodes=(_NODE,)),
    )
    readings = _readings(surface)
    assert len(readings) == 40
    assert all(r.history_context is None for r in readings)
    assert {r.history_context_reason.code for r in readings if r.history_context_reason} == {
        HISTORY_ABSENT_THIN
    }


def test_exactly_the_minimum_earlier_hours_is_enough() -> None:
    """The boundary is inclusive, and the hour being described is not one of the n_hours."""
    surface = aggregate.aggregate(_hours([20.0 + i for i in range(6)]), _config(min_hours=5))
    readings = _readings(surface)
    assert [r.history_context is None for r in readings] == [True] * 5 + [False]
    last = readings[-1].history_context
    assert last is not None
    assert last.n_hours == 5  # the five earlier hours, not the six recorded ones


# -- clause 2: a known distribution, the expected percentile, the same every run --------------


@pytest.mark.parametrize(
    ("current", "expected"),
    [
        (30.0, 100.0),  # above all ten earlier hours
        (25.5, 60.0),  # above 20.0 .. 24.0 and 25.0: six of ten
        (19.0, 0.0),  # below all ten
        (20.0, 0.0),  # equal to the lowest: ties are not "below" (the stated rule)
    ],
)
def test_a_known_distribution_yields_the_expected_percentile(
    current: float, expected: float
) -> None:
    """Ten earlier hours at 20.0..29.0, then one more. The arithmetic is `strictly below / n`."""
    surface = aggregate.aggregate(
        _hours([20.0 + i for i in range(10)] + [current]), _config(min_hours=10)
    )
    context = _readings(surface)[-1].history_context
    assert context is not None
    assert context.n_hours == 10
    assert context.percentile == pytest.approx(expected)
    assert context.window_start == "2026-06-01T00:00:00Z"


def test_a_value_equal_to_every_earlier_hour_reports_zero_not_fifty() -> None:
    """The tie rule, at its most load-bearing: a flat record is not "the median" of itself."""
    surface = aggregate.aggregate(_hours([22.0] * 11), _config(min_hours=10))
    context = _readings(surface)[-1].history_context
    assert context is not None
    assert context.percentile == 0.0


def test_the_same_store_yields_byte_identical_context_across_runs() -> None:
    """Deterministic and offline: nothing here reads a clock, a network, or a dict ordering."""
    observations = _hours([20.0 + (i % 7) for i in range(30)])
    first = aggregate.aggregate(observations, _config(min_hours=10)).to_records()
    second = aggregate.aggregate(list(reversed(observations)), _config(min_hours=10)).to_records()
    assert first == second


def test_only_earlier_hours_count_so_a_published_record_never_moves() -> None:
    """A record written today must read the same next year. Extending the store with later hours
    changes the new hours' context and none of the old ones'."""
    early = _hours([20.0 + i for i in range(12)])
    later = early + _hours([99.0, 98.0], start_hour=12)
    before = {r.bucket: r.history_context for r in _readings(aggregate.aggregate(early, _config()))}
    after = {r.bucket: r.history_context for r in _readings(aggregate.aggregate(later, _config()))}
    assert all(after[bucket] == context for bucket, context in before.items())
    assert len(after) == len(before) + 2


def test_a_different_calendar_month_is_a_different_distribution() -> None:
    """June is compared against June. Mixing months would answer a question nobody asked."""
    june = _hours([20.0 + i for i in range(8)], start_day="2026-06-01")
    july = _hours([40.0], start_day="2026-07-01")
    surface = aggregate.aggregate(june + july, _config(min_hours=5))
    july_reading = next(r for r in _readings(surface) if r.bucket.startswith("2026-07"))
    assert july_reading.history_context is None
    assert july_reading.history_context_reason is not None
    assert july_reading.history_context_reason.code == HISTORY_ABSENT_THIN


def test_an_hour_outside_the_window_is_not_in_the_distribution() -> None:
    """`history_window_days` bounds an archive that grows without limit."""
    old = _hours([50.0] * 6, start_day="2026-06-01")
    recent = _hours([20.0 + i for i in range(6)], start_day="2027-06-01")
    wide = aggregate.aggregate(old + recent, _config(min_hours=6, window_days=730))
    narrow = aggregate.aggregate(old + recent, _config(min_hours=6, window_days=30))
    newest_wide = _readings(wide)[-1].history_context
    newest_narrow = _readings(narrow)[-1].history_context
    assert newest_wide is not None and newest_wide.n_hours == 11
    assert newest_wide.window_start.startswith("2026-06")
    # Inside 30 days only the 2027 hours remain, and five earlier ones is under the minimum.
    assert newest_narrow is None


# -- clause 3: raw-only history is labelled, and shown as provisional -------------------------


def test_raw_only_history_is_labelled_raw() -> None:
    surface = aggregate.aggregate(
        _hours([20.0 + i for i in range(11)], calibrated=False), _config(min_hours=10)
    )
    context = _readings(surface)[-1].history_context
    assert context is not None
    assert context.basis == HISTORY_BASIS_RAW
    assert context.provisional is True


def test_calibrated_history_is_labelled_calibrated() -> None:
    surface = aggregate.aggregate(_hours([20.0 + i for i in range(11)]), _config(min_hours=10))
    context = _readings(surface)[-1].history_context
    assert context is not None
    assert context.basis == HISTORY_BASIS_CALIBRATED
    assert context.provisional is False


def test_a_provisional_reading_is_never_placed_in_a_calibrated_distribution() -> None:
    """The history is fully calibrated and the current hour is not. Comparing them under
    `basis: calibrated` would quote a raw value against a corrected record."""
    calibrated = _hours([20.0 + i for i in range(10)])
    raw_now = _hours([30.0], calibrated=False, start_hour=10)
    surface = aggregate.aggregate(calibrated + raw_now, _config(min_hours=10))
    newest = _readings(surface)[-1]
    assert newest.provisional is True
    assert newest.history_context is not None
    assert newest.history_context.basis == HISTORY_BASIS_RAW


@pytest.mark.parametrize("lang", ["en", "es"])
def test_a_raw_basis_is_rendered_as_provisional_in_every_language(lang: str) -> None:
    """ "Rendered as provisional wherever shown" — including the Spanish feed, which is where a
    clause that only exists in the English template would go missing unnoticed."""
    raw = aggregate.HistoryContext(
        percentile=92.3, n_hours=1340, window_start="2026-06-01T00:00:00Z", basis=HISTORY_BASIS_RAW
    )
    calibrated = aggregate.HistoryContext(
        percentile=92.3,
        n_hours=1340,
        window_start="2026-06-01T00:00:00Z",
        basis=HISTORY_BASIS_CALIBRATED,
    )
    raw_line = i18n_alerts.history_line("Oak & 4th", raw, None, lang)
    calibrated_line = i18n_alerts.history_line("Oak & 4th", calibrated, None, lang)
    assert "92.3%" in raw_line and "1340" in raw_line
    assert len(raw_line) > len(calibrated_line)
    assert raw_line.startswith(calibrated_line[:-1])  # the same sentence plus the caveat
    if lang == "es":
        assert "provisional" in raw_line
        assert raw_line != i18n_alerts.history_line("Oak & 4th", raw, None, "en")


# -- the two absences that waiting never resolves ---------------------------------------------


def test_the_derived_exposure_layer_never_gets_a_percentile() -> None:
    """An ordinal tier's share-of-hours-below describes how often the tier recurs, not how
    unusual this hour is. Same reason `exposure` publishes no `uncertainty`."""
    observations = _hours([41.0] * 11, parameter="heat_index_c") + _hours(
        [40.0] * 11, parameter="pm25_ugm3", unit="ug/m3"
    )
    surface = aggregate.aggregate(observations, _config(min_hours=5))
    exposure_cells = [c for c in surface.cells if c.parameter == aggregate.EXPOSURE]
    assert exposure_cells, "fixture must build the derived exposure layer"
    for cell in exposure_cells:
        assert cell.history_context is None
        assert cell.history_context_reason is not None
        assert cell.history_context_reason.code == HISTORY_ABSENT_ORDINAL


def test_the_nowcast_reading_says_no_nowcast_distribution_exists() -> None:
    """Exactly one NowCast reading is derived per cell, so "wait for more hours" — what the
    thin-history sentence would say — is the wrong advice, forever."""
    surface = aggregate.aggregate(
        _hours([8.0, 10.0, 12.0], parameter="pm25_ugm3", unit="ug/m3"), _config(min_hours=2)
    )
    nowcast = [c for c in surface.cells if c.aqi_window == aggregate.AQI_WINDOW_NOWCAST]
    assert nowcast, "fixture must build a NowCast reading"
    assert nowcast[0].history_context is None
    assert nowcast[0].history_context_reason is not None
    assert nowcast[0].history_context_reason.code == HISTORY_ABSENT_SINGLE_WINDOW
    # …and the hourly-mean reading for the same bucket is unaffected.
    hourly = [
        c
        for c in surface.cells
        if c.parameter == "pm25_ugm3"
        and c.aqi_window == aggregate.AQI_WINDOW
        and c.bucket == nowcast[0].bucket
    ]
    assert hourly and hourly[0].history_context is not None


def test_every_absence_code_has_its_own_sentence_and_an_unknown_one_raises() -> None:
    """A fourth cause published under the third one's sentence would read exactly like a match."""
    sentences = {
        code: i18n_alerts.history_line("Oak & 4th", None, code, "en")
        for code in aggregate.HISTORY_ABSENCE_CODES
    }
    assert len(set(sentences.values())) == len(aggregate.HISTORY_ABSENCE_CODES)
    with pytest.raises(ValueError, match="no history sentence is defined"):
        i18n_alerts.history_line("Oak & 4th", None, "a_code_nobody_defined", "en")


# -- the surfaces it has to reach --------------------------------------------------------------


def test_every_surface_record_carries_both_keys_whatever_the_answer() -> None:
    """One stable shape: a consumer never has to tell "no baseline" from "old build"."""
    observations = _hours([20.0 + i for i in range(11)], parameter="heat_index_c") + _hours(
        [40.0] * 11, parameter="pm25_ugm3", unit="ug/m3"
    )
    records = aggregate.aggregate(observations, _config(min_hours=5)).to_records()
    assert records
    for record in records:
        assert "history_context" in record
        assert "history_context_reason" in record
        assert (record["history_context"] is None) != (record["history_context_reason"] is None)


def test_an_alert_carries_the_context_of_the_cell_it_was_raised_on() -> None:
    surface = aggregate.aggregate(
        _hours([41.0 + i * 0.01 for i in range(11)], parameter="heat_index_c"),
        _config(min_hours=5),
    )
    feed = alerts.build_feed(surface)
    assert feed.alerts, "fixture must raise an alert"
    alert = feed.alerts[0]
    newest = _readings(surface, "heat_index_c")[-1]
    assert alert.history_context == newest.history_context
    record = alert.as_record()
    assert record["history_context"] == newest.history_context.as_record()
    assert record["history_line"] == alert.history_line
    assert record["history_line_es"] != record["history_line"]
    # The Atom summary carries the sentence; the title is unchanged.
    atom = feed.to_atom()
    assert escape(alert.history_line) in atom
    assert f"<title>{escape(alert.headline())}</title>" in atom


def test_the_brief_always_states_the_local_baseline_or_its_absence() -> None:
    """A resident asking "is this normal?" gets an answer or an explicit "we cannot say" — never
    silence, which reads as "it is"."""
    thin = aggregate.aggregate(_hours([41.0, 41.5], parameter="heat_index_c"), _config(min_hours=5))
    rich = aggregate.aggregate(
        _hours([41.0 + i * 0.01 for i in range(11)], parameter="heat_index_c"),
        _config(min_hours=5),
    )
    thin_brief = exposure_brief.build_brief(_CELL_ID, thin)
    rich_brief = exposure_brief.build_brief(_CELL_ID, rich)
    assert thin_brief is not None and rich_brief is not None
    assert any("no local baseline" in line for line in thin_brief.lines())
    assert any("this hour is above" in line for line in rich_brief.lines())
    record = rich_brief.as_record()
    assert record["history_context"] == rich_brief.history.as_record()
    assert record["history_context_reason"] is None
    assert record["history_bucket"] == rich_brief.history_bucket


def test_the_data_dictionary_publishes_the_rules_from_the_running_constants() -> None:
    """Generated, never restated: a reader of `/api/schema.json` gets the same tie rule, window
    rule, basis vocabulary and absence codes the rollup runs on."""
    from swelter.config import DEFAULT_HISTORY_MIN_HOURS, DEFAULT_HISTORY_WINDOW_DAYS
    from swelter.dictionary import build_data_dictionary

    block = build_data_dictionary()["history_context"]
    assert isinstance(block, dict)
    assert block["tie_rule"] == aggregate.HISTORY_TIE_RULE
    assert block["window_rule"] == aggregate.HISTORY_WINDOW_RULE
    assert block["absence"]["codes"] == list(aggregate.HISTORY_ABSENCE_CODES)
    assert [f["name"] for f in block["fields"]] == [
        "percentile",
        "n_hours",
        "window_start",
        "basis",
    ]
    assert block["defaults"]["history_min_hours"] == DEFAULT_HISTORY_MIN_HOURS
    assert block["defaults"]["history_window_days"] == DEFAULT_HISTORY_WINDOW_DAYS


def test_the_committed_demo_surface_exercises_every_state() -> None:
    """The published artifact, not a fixture. A field whose absence branch never ships is a
    branch nobody has read: the committed demo has to show all four outcomes."""
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    if root.name == "mutants":
        root = root.parent
    cells = json.loads((root / "web" / "sample-surface.json").read_text(encoding="utf-8"))["cells"]
    seen: set[str] = set()
    for cell in cells:
        context = cell["history_context"]
        reason = cell["history_context_reason"]
        seen.add(context["basis"] if context else reason["code"])
    assert {HISTORY_BASIS_CALIBRATED, HISTORY_BASIS_RAW} <= seen
    assert {HISTORY_ABSENT_ORDINAL, HISTORY_ABSENT_SINGLE_WINDOW} <= seen
