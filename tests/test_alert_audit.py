"""Alert hindcast audit: scoring a published claim against a reference monitor.

The tests are shaped around the one thing this module must never do — put a number on an
unmeasured claim. A precision of 0.0 over an empty denominator reads as "every alert was wrong",
a precision of 1.0 reads as "every alert was right", and the truth in both cases is that nothing
was checked.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from swelter import aggregate as aggregate_module
from swelter import alert_audit
from swelter.cli import main
from swelter.config import NetworkConfig, parse_config
from swelter.models import Observation
from swelter.sources.airnow import ReferenceReading
from swelter.store import open_store

# The reference monitor sits on top of the network, so distance never accidentally decides a
# test that is about something else. `far` is 1 degree of latitude away (~111 km), which no
# reasonable `max_distance_m` admits.
MONITOR_LAT = 33.87
MONITOR_LON = -117.92

NETWORK_DOC: dict[str, object] = {
    "name": "Audit Test Network",
    "grid_resolution_m": 500,
    "nodes": [
        {"node_id": "node-a", "label": "A", "lat": MONITOR_LAT, "lon": MONITOR_LON},
        {"node_id": "node-b", "label": "B", "lat": MONITOR_LAT + 0.002, "lon": MONITOR_LON},
    ],
    "reference_monitors": [
        {
            "monitor_id": "060670010",
            "label": "Del Paso Manor",
            "lat": MONITOR_LAT,
            "lon": MONITOR_LON,
        }
    ],
}


def _config(doc: dict[str, object] | None = None) -> NetworkConfig:
    return parse_config(yaml.safe_load(yaml.safe_dump(doc if doc is not None else NETWORK_DOC)))


def _hours(count: int) -> list[str]:
    return [f"2026-06-01T{hour:02d}:00:00Z" for hour in range(count)]


def _pm25_observations(
    values: dict[str, float], nodes: tuple[str, ...] = ("node-a",)
) -> list[Observation]:
    return [
        Observation(
            node_id=node,
            timestamp=stamp,
            parameter="pm25_ugm3",
            value=value,
            unit="ug/m3",
        )
        for stamp, value in values.items()
        for node in nodes
    ]


def _surface(
    observations: list[Observation], config: NetworkConfig, tmp_path: Path
) -> aggregate_module.Surface:
    store_dir = tmp_path / "store"
    with open_store(store_dir) as store:
        store.write(observations)
        return aggregate_module.aggregate(store.all(), config)


def _reference(values: dict[str, float], monitor_id: str = "060670010") -> list[ReferenceReading]:
    return [
        ReferenceReading(monitor_id=monitor_id, parameter="pm25_ugm3", timestamp=stamp, value=value)
        for stamp, value in values.items()
    ]


# A PM2.5 concentration well past the AQI 101 boundary, and one comfortably below it. Literals,
# not values derived from the pack's floor: a fixture computed from the constant it tests moves
# with the constant and can never catch a wrong one.
ALERTING_UGM3 = 90.0
CALM_UGM3 = 5.0


def test_the_alerting_and_calm_fixtures_really_sit_either_side_of_the_shipped_floor() -> None:
    """The two literals above are only useful if they straddle the floor the pack ships.

    Asserted here, once, rather than by deriving them from the floor in every fixture — which
    would make every test below a tautology that moves with whatever the floor becomes.
    """
    from swelter.hazard_packs import HEAT_PACK
    from swelter.models import pm25_aqi

    floor = HEAT_PACK.default_floors()["pm25_aqi"]
    assert pm25_aqi(ALERTING_UGM3)[0] >= floor
    assert pm25_aqi(CALM_UGM3)[0] < floor


# --------------------------------------------------------------------------------------------
# The three classifications.
# --------------------------------------------------------------------------------------------


def test_an_alert_a_reference_monitor_also_crossed_is_confirmed(tmp_path: Path) -> None:
    config = _config()
    hours = _hours(4)
    surface = _surface(_pm25_observations(dict.fromkeys(hours, ALERTING_UGM3)), config, tmp_path)
    audit = alert_audit.audit_alerts(
        surface, config, _reference(dict.fromkeys(hours, ALERTING_UGM3))
    )
    assert audit.alerts
    assert {a.classification for a in audit.alerts} == {alert_audit.CLASS_CONFIRMED}
    score = next(s for s in audit.scores if s.parameter == "pm25_ugm3")
    assert score.contradicted == 0
    assert score.precision == 1.0
    assert score.interval is not None
    low, high = score.interval
    assert 0.0 < low < 1.0, "a Wilson interval on a small sample is not a point"
    assert high == 1.0
    for alert in audit.alerts:
        assert alert.monitor_id == "060670010"
        assert alert.reference_crossed is True
        assert alert.reason is None


def test_an_alert_the_reference_monitor_did_not_cross_is_contradicted(tmp_path: Path) -> None:
    config = _config()
    hours = _hours(4)
    surface = _surface(_pm25_observations(dict.fromkeys(hours, ALERTING_UGM3)), config, tmp_path)
    audit = alert_audit.audit_alerts(surface, config, _reference(dict.fromkeys(hours, CALM_UGM3)))
    assert {a.classification for a in audit.alerts} == {alert_audit.CLASS_CONTRADICTED}
    score = next(s for s in audit.scores if s.parameter == "pm25_ugm3")
    assert score.precision == 0.0
    assert score.precision_note is None, "0.0 here is a measurement, not an absence"

    contradicted = audit.contradicted
    assert contradicted
    for alert in contradicted:
        assert alert.reference_value == CALM_UGM3
        assert alert.reference_timestamp == alert.bucket
        assert alert.monitor_label == "Del Paso Manor"
        assert alert.monitor_distance_m is not None


def test_an_alert_with_no_reference_in_range_is_unverifiable_and_scores_nothing(
    tmp_path: Path,
) -> None:
    """The refusal this module exists for: no precision at all, not 0% and not 100%."""
    config = _config()
    hours = _hours(4)
    surface = _surface(_pm25_observations(dict.fromkeys(hours, ALERTING_UGM3)), config, tmp_path)
    # Same readings, a monitor the config does not know about, so nothing pairs.
    audit = alert_audit.audit_alerts(
        surface, config, _reference(dict.fromkeys(hours, ALERTING_UGM3), monitor_id="999999999")
    )
    assert {a.classification for a in audit.alerts} == {alert_audit.CLASS_UNVERIFIABLE}
    score = next(s for s in audit.scores if s.parameter == "pm25_ugm3")
    assert score.scored == 0
    assert score.unverifiable == len(audit.alerts)
    assert score.precision is None
    assert score.interval is None
    assert score.precision_note is not None
    assert "no precision" in score.precision_note
    # ...and the reason names the *configuration* disagreement, not a coverage gap. Readings for
    # this parameter do exist in the run; none of them is from a monitor the network declares.
    for alert in audit.alerts:
        assert alert.reason is not None
        assert "none of them is from a monitor this network declares" in alert.reason
        assert "060670010" in alert.reason


def test_a_parameter_no_reference_reading_covers_is_a_different_sentence(tmp_path: Path) -> None:
    """ "Nothing measures this hazard" and "your ids disagree" must not share one message.

    The first is a coverage fact a steward can do nothing about; the second is a configuration
    error they can fix in a minute. Collapsing them hides the fixable one behind the other.
    """
    config = _config()
    hours = _hours(2)
    surface = _surface(
        [
            Observation(
                node_id="node-a",
                timestamp=stamp,
                parameter="heat_index_c",
                value=45.0,
                unit="degC",
            )
            for stamp in hours
        ],
        config,
        tmp_path,
    )
    audit = alert_audit.audit_alerts(
        surface, config, _reference(dict.fromkeys(hours, ALERTING_UGM3))
    )
    heat = [a for a in audit.alerts if a.parameter == "heat_index_c"]
    assert heat
    for alert in heat:
        assert alert.reason is not None
        assert "no reference reading in this run is for heat_index_c" in alert.reason
        assert "declares" not in alert.reason


# --------------------------------------------------------------------------------------------
# The four distinct reasons an alert cannot be checked.
# --------------------------------------------------------------------------------------------


def test_a_monitor_beyond_the_distance_bound_names_distance_as_the_reason(
    tmp_path: Path,
) -> None:
    doc = json.loads(json.dumps(NETWORK_DOC))
    doc["reference_monitors"][0]["lat"] = MONITOR_LAT + 1.0  # ~111 km north
    config = _config(doc)
    hours = _hours(2)
    surface = _surface(_pm25_observations(dict.fromkeys(hours, ALERTING_UGM3)), config, tmp_path)
    audit = alert_audit.audit_alerts(
        surface, config, _reference(dict.fromkeys(hours, ALERTING_UGM3))
    )
    assert audit.alerts
    for alert in audit.alerts:
        assert alert.classification == alert_audit.CLASS_UNVERIFIABLE
        assert alert.reason is not None
        assert "within" in alert.reason


def test_a_monitor_with_no_published_coordinate_is_unlocatable_not_at_zero_zero(
    tmp_path: Path,
) -> None:
    """`lat: null` must not be read as the equator.

    Defaulting a missing coordinate to 0,0 puts the monitor in the Gulf of Guinea and rules it
    out on distance, which publishes "checked, too far" over "we do not know where it is".
    """
    doc = json.loads(json.dumps(NETWORK_DOC))
    del doc["reference_monitors"][0]["lat"]
    del doc["reference_monitors"][0]["lon"]
    config = _config(doc)
    hours = _hours(2)
    surface = _surface(_pm25_observations(dict.fromkeys(hours, ALERTING_UGM3)), config, tmp_path)
    audit = alert_audit.audit_alerts(
        surface, config, _reference(dict.fromkeys(hours, ALERTING_UGM3))
    )
    assert audit.alerts
    for alert in audit.alerts:
        assert alert.classification == alert_audit.CLASS_UNVERIFIABLE
        assert alert.reason is not None
        assert "unknown rather than zero" in alert.reason
        assert alert.monitor_distance_m is None


def test_a_monitor_in_range_with_no_reading_that_hour_names_the_window_as_the_reason(
    tmp_path: Path,
) -> None:
    config = _config()
    surface = _surface(
        _pm25_observations(dict.fromkeys(_hours(6), ALERTING_UGM3)), config, tmp_path
    )
    # A reference series covering only the first hour: later alerts are outside the tolerance.
    audit = alert_audit.audit_alerts(
        surface,
        config,
        _reference({"2026-06-01T00:00:00Z": ALERTING_UGM3}),
        tolerance_s=1800.0,
    )
    reasons = {a.reason for a in audit.alerts if a.reason}
    assert any("published no" in reason for reason in reasons)
    assert any(a.classification == alert_audit.CLASS_CONFIRMED for a in audit.alerts)


def test_a_heat_alert_is_unverifiable_because_no_reference_publishes_a_heat_index(
    tmp_path: Path,
) -> None:
    """AirNow says nothing about a heat index, and a PM2.5 monitor must not be allowed to vouch.

    Without this the audit would either drop heat alerts from the report entirely — hiding the
    largest class of unchecked claim — or pair them against a concentration and score nonsense.
    """
    config = _config()
    hours = _hours(3)
    # A heat index past the NWS "Danger" floor the heat pack ships (39.4 degC). A literal, for
    # the same reason ALERTING_UGM3 is one.
    observations = [
        Observation(
            node_id="node-a", timestamp=stamp, parameter="heat_index_c", value=45.0, unit="degC"
        )
        for stamp in hours
    ]
    surface = _surface(observations, config, tmp_path)
    audit = alert_audit.audit_alerts(
        surface, config, _reference(dict.fromkeys(hours, ALERTING_UGM3))
    )
    heat = [a for a in audit.alerts if a.parameter == "heat_index_c"]
    assert heat, "the fixture must actually raise a heat alert for this test to mean anything"
    for alert in heat:
        assert alert.classification == alert_audit.CLASS_UNVERIFIABLE
        assert alert.reason is not None
        assert "no reference reading in this run is for heat_index_c" in alert.reason
    score = next(s for s in audit.scores if s.parameter == "heat_index_c")
    assert score.precision is None


# --------------------------------------------------------------------------------------------
# Arithmetic and shape.
# --------------------------------------------------------------------------------------------


def test_a_proportion_over_zero_trials_raises_rather_than_returning_a_number() -> None:
    with pytest.raises(ValueError, match="undefined"):
        alert_audit.wilson_interval(0, 0)


def test_the_wilson_interval_brackets_the_proportion_and_stays_inside_zero_and_one() -> None:
    for successes, trials in ((0, 1), (1, 1), (3, 4), (7, 10), (50, 100)):
        low, high = alert_audit.wilson_interval(successes, trials)
        assert 0.0 <= low <= successes / trials <= high <= 1.0
    # A small sample must not report a point estimate as if it were certain.
    low, high = alert_audit.wilson_interval(1, 1)
    assert low < 1.0


def test_an_empty_window_reports_no_alerts_and_says_that_is_not_a_perfect_score(
    tmp_path: Path,
) -> None:
    config = _config()
    surface = _surface(_pm25_observations(dict.fromkeys(_hours(4), CALM_UGM3)), config, tmp_path)
    audit = alert_audit.audit_alerts(
        surface, config, _reference(dict.fromkeys(_hours(4), CALM_UGM3))
    )
    assert audit.alerts == ()
    assert audit.scores == ()
    assert audit.window is None
    assert any("not a precision of 1.0" in note for note in audit.notes)
    assert "not measured" in alert_audit.render_markdown(audit)


def test_since_and_until_bound_the_window_that_is_audited(tmp_path: Path) -> None:
    config = _config()
    hours = _hours(8)
    surface = _surface(_pm25_observations(dict.fromkeys(hours, ALERTING_UGM3)), config, tmp_path)
    references = _reference(dict.fromkeys(hours, ALERTING_UGM3))
    everything = alert_audit.audit_alerts(surface, config, references)
    bounded = alert_audit.audit_alerts(surface, config, references, since=hours[2], until=hours[4])
    assert len(bounded.alerts) < len(everything.alerts)
    assert bounded.window == (hours[2], hours[4])
    assert all(hours[2] <= a.bucket <= hours[4] for a in bounded.alerts)


def test_the_audit_records_the_parameters_it_used_and_calls_them_swelters_own(
    tmp_path: Path,
) -> None:
    config = _config()
    surface = _surface(
        _pm25_observations(dict.fromkeys(_hours(2), ALERTING_UGM3)), config, tmp_path
    )
    audit = alert_audit.audit_alerts(
        surface, config, _reference(dict.fromkeys(_hours(2), ALERTING_UGM3)), max_distance_m=4321.0
    )
    record = audit.as_record()
    assert record["max_distance_m"] == 4321.0
    assert record["pack_id"] == "heat"
    assert any("not a published standard" in note for note in audit.notes)
    assert any("Recall is not measured" in note for note in audit.notes)


def test_the_rendered_report_states_that_recall_is_not_measured(tmp_path: Path) -> None:
    config = _config()
    surface = _surface(
        _pm25_observations(dict.fromkeys(_hours(3), ALERTING_UGM3)), config, tmp_path
    )
    audit = alert_audit.audit_alerts(
        surface, config, _reference(dict.fromkeys(_hours(3), CALM_UGM3))
    )
    document = alert_audit.render_markdown(audit)
    assert "Recall is not measured" in document
    assert "## Contradicted alerts" in document
    assert "Del Paso Manor" in document


def test_two_audits_of_one_store_are_byte_identical(tmp_path: Path) -> None:
    """No wall clock anywhere: the window comes from the data or from --since/--until."""
    config = _config()
    hours = _hours(5)
    surface = _surface(
        _pm25_observations(dict.fromkeys(hours, ALERTING_UGM3), nodes=("node-a", "node-b")),
        config,
        tmp_path,
    )
    references = _reference(dict.fromkeys(hours, CALM_UGM3))
    first = json.dumps(alert_audit.audit_alerts(surface, config, references).as_record(), indent=2)
    second = json.dumps(alert_audit.audit_alerts(surface, config, references).as_record(), indent=2)
    assert first == second


# --------------------------------------------------------------------------------------------
# The CLI.
# --------------------------------------------------------------------------------------------


def _write_fixture(path: Path, values: dict[str, float]) -> None:
    path.write_text(
        json.dumps(
            [
                {
                    "Latitude": MONITOR_LAT,
                    "Longitude": MONITOR_LON,
                    "UTC": stamp[:13],
                    "Parameter": "PM2.5",
                    "Unit": "UG/M3",
                    "Value": value,
                    "FullAQSCode": "060670010",
                }
                for stamp, value in values.items()
            ]
        ),
        encoding="utf-8",
    )


def test_the_cli_writes_json_and_markdown_and_exits_zero_on_a_contradiction(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A contradicted alert is a finding, not a tool failure — the exit status must not say so."""
    config_path = tmp_path / "network.yaml"
    config_path.write_text(yaml.safe_dump(NETWORK_DOC), encoding="utf-8")
    store_dir = tmp_path / "store"
    hours = _hours(3)
    with open_store(store_dir) as store:
        store.write(_pm25_observations(dict.fromkeys(hours, ALERTING_UGM3)))
    fixture = tmp_path / "reference.json"
    _write_fixture(fixture, dict.fromkeys(hours, CALM_UGM3))

    out, markdown = tmp_path / "audit.json", tmp_path / "audit.md"
    code = main(
        [
            "audit-alerts",
            "--store",
            str(store_dir),
            "--config",
            str(config_path),
            "--reference-fixture",
            str(fixture),
            "--out",
            str(out),
            "--markdown",
            str(markdown),
            "--json",
        ]
    )
    assert code == 0
    captured = capsys.readouterr()
    document = json.loads(out.read_text(encoding="utf-8"))
    assert document["schema_version"] == alert_audit.AUDIT_SCHEMA_VERSION
    assert any(
        alert["classification"] == alert_audit.CLASS_CONTRADICTED for alert in document["alerts"]
    )
    assert "Recall is not measured" in markdown.read_text(encoding="utf-8")
    assert "unverifiable" in captured.err
    assert json.loads(captured.out)["schema_version"] == alert_audit.AUDIT_SCHEMA_VERSION


def test_the_cli_refuses_to_run_without_a_reference_series(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """An audit with no references would call every alert unverifiable and look like it checked."""
    config_path = tmp_path / "network.yaml"
    config_path.write_text(yaml.safe_dump(NETWORK_DOC), encoding="utf-8")
    store_dir = tmp_path / "store"
    with open_store(store_dir) as store:
        store.write(_pm25_observations({"2026-06-01T00:00:00Z": ALERTING_UGM3}))
    assert main(["audit-alerts", "--store", str(store_dir), "--config", str(config_path)]) == 1
    assert "reference-fixture is required" in capsys.readouterr().err
