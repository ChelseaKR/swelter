"""`swelter diff` — what changed, attributed to exactly one kind, with absence kept as absence.

The property under test throughout is that this command cannot turn a missing reading into a
number. Every other assertion supports it: the attribution vocabulary is closed, a reading that
exists on one side only is reported as presence rather than as arithmetic, and an unrecorded
schema version is never reported as a matching one.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from swelter import diff as diff_module
from swelter.cli import main
from swelter.diff import (
    CHANGE_KINDS,
    DiffError,
    build_report,
    classify_field,
    load_side,
    render_markdown,
    render_text,
)

ROOT = Path(__file__).resolve().parents[1]
if ROOT.name == "mutants":  # pragma: no cover - mutation sandbox only
    ROOT = ROOT.parent
SAMPLE_SURFACE = ROOT / "web" / "sample-surface.json"


def _surface(
    tmp_path: Path, name: str, cells: list[dict[str, Any]], *, rights: dict[str, Any] | None = None
) -> Path:
    path = tmp_path / f"{name}.json"
    path.write_text(
        json.dumps(
            {
                "interval": "3600",
                "attribution": "fixture",
                "buckets": sorted({str(c["bucket"]) for c in cells}),
                "cells": cells,
                "rights": rights
                if rights is not None
                else {"schema_version": 1, "source": "fixture", "license": "CC0-1.0"},
            }
        ),
        encoding="utf-8",
    )
    return path


def _cell(**overrides: Any) -> dict[str, Any]:
    cell: dict[str, Any] = {
        "cell_id": "32.5839,-117.1131",
        "label": "Imperial Beach",
        "lat": 32.5839,
        "lon": -117.1131,
        "parameter": "temp_c",
        "bucket": "2026-06-08T00:00:00Z",
        "mean": 31.2,
        "n": 4,
        "provisional": False,
        "uncertainty": 0.4,
        "mean_member_sigma": 0.4,
        "aqi": None,
        "category": None,
    }
    cell.update(overrides)
    return cell


def _report(a: Path, b: Path, **kwargs: Any) -> dict[str, Any]:
    return build_report(load_side(a), load_side(b), **kwargs)


# ---- the four "done when" criteria ---------------------------------------------------------


def test_two_identical_surfaces_produce_an_empty_change_set_identically(tmp_path: Path) -> None:
    a = _surface(tmp_path, "a", [_cell()])
    b = _surface(tmp_path, "b", [_cell()])

    report = _report(a, b)

    assert report["changes"] == []
    assert set(report["summary"].values()) == {0}
    assert render_text(report) == render_text(_report(a, b))
    assert json.dumps(report) == json.dumps(_report(a, b))
    assert "generated_at" not in json.dumps(report), (
        "the report carries a clock, so two runs over identical inputs disagree"
    )


def test_a_calibration_version_moving_without_the_value_is_one_change_and_no_value_change(
    tmp_path: Path,
) -> None:
    """ADR 0038's question, asked directly: did the number move, or did the fit?"""
    a = _surface(tmp_path, "a", [_cell(method="epa-humidity@2026-05-01")])
    b = _surface(tmp_path, "b", [_cell(method="epa-humidity@2026-06-01")])

    report = _report(a, b)

    assert report["summary"]["calibration_version"] == 1
    assert report["summary"]["value_change"] == 0
    (change,) = report["changes"]
    assert change["field"] == "method"
    assert (change["from"], change["to"]) == ("epa-humidity@2026-05-01", "epa-humidity@2026-06-01")


def test_a_cell_absent_on_one_side_is_absence_and_never_a_numeric_delta(tmp_path: Path) -> None:
    """ADR 0037. The failure this guards against is a gap rendered as a fall to zero."""
    a = _surface(tmp_path, "a", [_cell(), _cell(parameter="pm25_ugm3", mean=13.4)])
    b = _surface(tmp_path, "b", [_cell()])

    report = _report(a, b)

    (change,) = report["changes"]
    assert change["kind"] == "present_to_absent"
    assert "to" not in change, "the absent side was given a value"
    assert change["from"]["mean"] == 13.4
    serialized = json.dumps(report)
    assert "delta" not in serialized
    assert "-13.4" not in serialized and "13.4," not in serialized.replace('"mean": 13.4,', "")
    assert "absent" in render_text(report)


def test_mismatched_recorded_schema_versions_are_refused_unless_skew_is_allowed(
    tmp_path: Path,
) -> None:
    a = _surface(tmp_path, "a", [_cell()], rights={"schema_version": 1, "source": "fixture"})
    b = _surface(tmp_path, "b", [_cell()], rights={"schema_version": 2, "source": "fixture"})

    with pytest.raises(DiffError, match="schema versions differ"):
        _report(a, b)

    report = _report(a, b, allow_schema_skew=True)
    kinds = [c["kind"] for c in report["changes"]]
    assert "schema_version_change" in kinds


# ---- absence must not be laundered into agreement -------------------------------------------


def test_an_unrecorded_schema_version_is_not_reported_as_a_matching_one(tmp_path: Path) -> None:
    """The portfolio's dominant defect, in the field that would hide every other one.

    An artifact carrying no version has not told us it matches. Proceeding silently would put
    "these are comparable" behind a comparison that never happened.
    """
    a = _surface(tmp_path, "a", [_cell()], rights={"source": "fixture"})
    b = _surface(tmp_path, "b", [_cell()], rights={"schema_version": 2, "source": "fixture"})

    report = _report(a, b)

    block = report["schema_version_comparison"]
    assert block["comparable"] is False
    assert "NOT compared" in block["note"]
    assert "This is not a finding that they agree" in block["note"]
    assert [c["kind"] for c in report["changes"]] == []
    assert "NOTE:" in render_text(report)


def test_two_readings_with_the_same_identity_are_refused_rather_than_coalesced(
    tmp_path: Path,
) -> None:
    """Found while building this: the surface really does publish two records per key.

    `web/sample-surface.json` carries an `hourly-mean` PM2.5 record (with an error bar) and a
    `nowcast` one (explaining why it has none) for the same cell and bucket. Under a
    `(cell, parameter, bucket)` key those collapse — 1050 records become 900 — and half of every
    PM2.5 comparison is then made against whichever record happened to be last in the file.
    `aqi_window` is part of the identity, and a remaining collision is a refusal, not a guess.
    """
    duplicate = _cell(parameter="pm25_ugm3", aqi_window="nowcast")
    a = _surface(tmp_path, "a", [duplicate, dict(duplicate)])
    b = _surface(tmp_path, "b", [duplicate])

    with pytest.raises(DiffError, match="two readings with the same identity"):
        _report(a, b)


def test_the_committed_sample_surface_has_no_colliding_reading_identities() -> None:
    """The regression that motivated the key, asserted against the real published artifact."""
    report = build_report(load_side(SAMPLE_SURFACE), load_side(SAMPLE_SURFACE))
    assert report["changes"] == []


def test_a_recorded_null_is_not_the_same_as_an_absent_field(tmp_path: Path) -> None:
    """`uncertainty: null` means "no error bar, and here is why" (ADR 0035), not "not present"."""
    a = _surface(tmp_path, "a", [_cell(uncertainty=None)])
    b = _surface(tmp_path, "b", [_cell(uncertainty=0.4)])

    (change,) = _report(a, b)["changes"]

    assert change["kind"] == "value_change"
    assert change["from"] is None
    assert "from" in change, "a recorded null was dropped as though the field were absent"


# ---- the vocabulary ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("field", "expected"),
    [
        ("mean", "value_change"),
        ("n", "value_change"),
        ("aqi", "value_change"),
        ("method", "calibration_version"),
        ("reference", "calibration_version"),
        ("temp_c_method", "calibration_version"),
        ("version", "calibration_version"),
        ("provisional", "qc_state"),
        ("qc_flags", "qc_state"),
        ("pm25_ugm3_provisional", "qc_state"),
        ("rights.license", "source_or_rights_change"),
        ("data_attribution", "source_or_rights_change"),
        ("schema_version", "schema_version_change"),
        ("swelter_version", "schema_version_change"),
        ("something_nobody_has_added_yet", "value_change"),
    ],
)
def test_every_field_is_attributed_to_exactly_one_kind(field: str, expected: str) -> None:
    assert classify_field(field) == expected


def test_the_attribution_vocabulary_is_closed(tmp_path: Path) -> None:
    a = _surface(tmp_path, "a", [_cell(), _cell(parameter="pm25_ugm3")])
    b = _surface(
        tmp_path,
        "b",
        [_cell(mean=34.8, provisional=True, method="x")],
        rights={"schema_version": 1, "source": "changed", "license": "ODbL-1.0"},
    )

    report = _report(a, b)

    assert set(report["summary"]) == set(CHANGE_KINDS)
    assert {c["kind"] for c in report["changes"]} <= set(CHANGE_KINDS)
    assert report["summary"]["source_or_rights_change"] >= 2


# ---- alignment ------------------------------------------------------------------------------


def test_the_default_alignment_never_compares_two_different_instants(tmp_path: Path) -> None:
    a = _surface(tmp_path, "a", [_cell(bucket="2026-06-08T00:00:00Z", mean=31.2)])
    b = _surface(tmp_path, "b", [_cell(bucket="2026-06-15T00:00:00Z", mean=34.8)])

    kinds = [c["kind"] for c in _report(a, b)["changes"]]

    assert sorted(kinds) == ["absent_to_present", "present_to_absent"]


def test_latest_alignment_names_both_instants_on_every_record_it_produces(tmp_path: Path) -> None:
    """ "The block got worse this week" is a claim about two moments, and must say which two."""
    a = _surface(tmp_path, "a", [_cell(bucket="2026-06-08T00:00:00Z", mean=31.2)])
    b = _surface(tmp_path, "b", [_cell(bucket="2026-06-15T00:00:00Z", mean=34.8)])

    report = _report(a, b, align="latest")

    (change,) = report["changes"]
    assert change["kind"] == "value_change"
    assert change["context"] == {
        "from_bucket": "2026-06-08T00:00:00Z",
        "to_bucket": "2026-06-15T00:00:00Z",
    }
    assert "2026-06-15T00:00:00Z" in render_text(report)


def test_an_unknown_alignment_is_refused(tmp_path: Path) -> None:
    a = _surface(tmp_path, "a", [_cell()])
    with pytest.raises(DiffError, match="unknown alignment"):
        _report(a, a, align="whatever")


# ---- other input kinds -----------------------------------------------------------------------


def _health(tmp_path: Path, name: str, nodes: list[dict[str, Any]], **extra: Any) -> Path:
    path = tmp_path / f"{name}.json"
    path.write_text(json.dumps({"nodes": nodes, **extra}), encoding="utf-8")
    return path


def test_a_health_report_reports_node_and_correction_changes(tmp_path: Path) -> None:
    a = _health(
        tmp_path,
        "a",
        [{"node_id": "node-01", "status": "ok", "observations": 20, "online": True}],
        calibration={
            "corrections": [{"node_id": "node-01", "parameter": "temp_c", "version": "v1"}]
        },
    )
    b = _health(
        tmp_path,
        "b",
        [{"node_id": "node-01", "status": "degraded", "observations": 20, "online": True}],
        calibration={
            "corrections": [{"node_id": "node-01", "parameter": "temp_c", "version": "v2"}]
        },
    )

    report = _report(a, b)

    assert report["input_kind"] == "health"
    assert report["summary"]["qc_state"] == 1
    assert report["summary"]["calibration_version"] == 1
    assert report["summary"]["value_change"] == 0


def test_a_node_that_disappears_from_a_health_report_is_absence(tmp_path: Path) -> None:
    a = _health(tmp_path, "a", [{"node_id": "node-01"}, {"node_id": "node-02"}])
    b = _health(tmp_path, "b", [{"node_id": "node-01"}])

    (change,) = _report(a, b)["changes"]

    assert (change["kind"], change["subject_id"]) == ("present_to_absent", "node-02")
    assert "to" not in change


def _snapshot(tmp_path: Path, name: str, *, license_: str, sha: str, cell_mean: float) -> Path:
    directory = tmp_path / name
    directory.mkdir()
    (directory / "MANIFEST.json").write_text(
        json.dumps(
            {
                "release_version": "0.2.0",
                "created_at": "2026-06-08T00:00:00Z",
                "swelter_version": "0.2.0",
                "record_count": 12,
                "observation_window": {"start": "a", "end": "b"},
                "doi": None,
                "data_source": "fixture",
                "data_license": license_,
                "data_attribution": "fixture",
                "files": [
                    {
                        "name": "aggregate.geojson",
                        "description": "surface",
                        "sha256": sha,
                        "bytes": 10,
                    }
                ],
                "notes": [],
            }
        ),
        encoding="utf-8",
    )
    (directory / "aggregate.geojson").write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "geometry": {"type": "Point", "coordinates": [0, 0]},
                        "properties": {"cell_id": "c1", "label": "One", "temp_c": cell_mean},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return directory


def test_two_snapshots_compare_their_manifest_and_their_aggregate(tmp_path: Path) -> None:
    a = _snapshot(tmp_path, "a", license_="CC0-1.0", sha="aa", cell_mean=31.2)
    b = _snapshot(tmp_path, "b", license_="ODbL-1.0", sha="bb", cell_mean=34.8)

    report = _report(a, b)

    assert report["input_kind"] == "snapshot"
    by_kind = {c["kind"] for c in report["changes"]}
    assert "source_or_rights_change" in by_kind
    assert any(c["subject"] == "file" and c["field"] == "sha256" for c in report["changes"])
    assert any(c["subject"] == "cell" and c["field"] == "temp_c" for c in report["changes"])


def test_a_directory_without_a_manifest_is_not_a_snapshot(tmp_path: Path) -> None:
    (tmp_path / "empty").mkdir()
    with pytest.raises(DiffError, match="not a swelter snapshot"):
        load_side(tmp_path / "empty")


def test_two_different_kinds_of_artifact_are_refused(tmp_path: Path) -> None:
    surface = _surface(tmp_path, "a", [_cell()])
    health = _health(tmp_path, "h", [{"node_id": "node-01"}])
    with pytest.raises(DiffError, match="different kinds of artifact"):
        _report(surface, health)


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ("not json at all", "not valid JSON"),
        ("[]", "not a JSON object"),
        ("{}", "neither a surface"),
    ],
)
def test_an_unusable_input_is_named_rather_than_guessed(
    tmp_path: Path, content: str, expected: str
) -> None:
    path = tmp_path / "x.json"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(DiffError, match=expected):
        load_side(path)


def test_a_missing_path_is_refused(tmp_path: Path) -> None:
    with pytest.raises(DiffError, match="does not exist"):
        load_side(tmp_path / "nope.json")


# ---- rendering and the CLI --------------------------------------------------------------------


def test_markdown_renders_every_change_and_stays_deterministic(tmp_path: Path) -> None:
    a = _surface(tmp_path, "a", [_cell(), _cell(parameter="pm25_ugm3", mean=13.4)])
    b = _surface(tmp_path, "b", [_cell(mean=34.8, provisional=True)])

    report = _report(a, b)
    rendered = render_markdown(report)

    assert rendered == render_markdown(_report(a, b))
    assert rendered.count("| `") >= len(report["changes"])
    assert "absent" in rendered


def test_the_command_exits_zero_on_a_clean_comparison(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    a = _surface(tmp_path, "a", [_cell()])
    b = _surface(tmp_path, "b", [_cell()])
    assert main(["diff", str(a), str(b)]) == 0
    assert "no changes" in capsys.readouterr().out


def test_the_command_exits_zero_when_there_are_changes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A diff is a report, not a gate; a change is not an error."""
    a = _surface(tmp_path, "a", [_cell()])
    b = _surface(tmp_path, "b", [_cell(mean=34.8)])
    assert main(["diff", str(a), str(b), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"]["value_change"] == 1


def test_the_command_exits_two_on_a_refusal(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    a = _surface(tmp_path, "a", [_cell()], rights={"schema_version": 1})
    b = _surface(tmp_path, "b", [_cell()], rights={"schema_version": 2})
    assert main(["diff", str(a), str(b)]) == 2
    assert "schema versions differ" in capsys.readouterr().err


def test_the_command_can_render_markdown(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    a = _surface(tmp_path, "a", [_cell()])
    b = _surface(tmp_path, "b", [_cell(mean=34.8)])
    assert main(["diff", str(a), str(b), "--format", "md"]) == 0
    assert capsys.readouterr().out.startswith("# swelter diff")


def test_the_module_exports_what_the_cli_uses() -> None:
    for name in diff_module.__all__:
        assert hasattr(diff_module, name)


# ---- the paths a real operator hits, and the refusals ------------------------------------------


def test_a_correction_that_appears_or_disappears_is_absence_not_a_calibration_change(
    tmp_path: Path,
) -> None:
    """A node gaining its first correction is not the same claim as its fit having moved."""
    a = _health(tmp_path, "a", [{"node_id": "node-01"}], calibration={"corrections": []})
    b = _health(
        tmp_path,
        "b",
        [{"node_id": "node-01"}],
        calibration={
            "corrections": [{"node_id": "node-01", "parameter": "temp_c", "version": "v1"}]
        },
    )

    (change,) = _report(a, b)["changes"]

    assert change["kind"] == "absent_to_present"
    assert change["subject"] == "correction"
    assert "from" not in change

    (reverse,) = _report(b, a)["changes"]
    assert reverse["kind"] == "present_to_absent"
    assert "to" not in reverse


def test_a_health_report_without_a_calibration_block_reports_no_corrections(
    tmp_path: Path,
) -> None:
    """Absence of the block is absence of information, not an empty set of corrections."""
    a = _health(tmp_path, "a", [{"node_id": "node-01"}])
    b = _health(tmp_path, "b", [{"node_id": "node-01"}], calibration="not a block")
    assert _report(a, b)["changes"] == []


def test_a_node_appearing_in_a_health_report_is_absence_to_presence(tmp_path: Path) -> None:
    a = _health(tmp_path, "a", [{"node_id": "node-01"}])
    b = _health(tmp_path, "b", [{"node_id": "node-01"}, {"node_id": "node-02"}])

    (change,) = _report(a, b)["changes"]

    assert (change["kind"], change["subject_id"]) == ("absent_to_present", "node-02")
    assert "from" not in change


def test_a_health_report_whose_nodes_are_not_a_list_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"nodes": {"node-01": {}}}), encoding="utf-8")
    with pytest.raises(DiffError, match="must be a list"):
        _report(path, path)


def test_a_file_that_appears_in_a_snapshot_manifest_is_absence_to_presence(
    tmp_path: Path,
) -> None:
    a = _snapshot(tmp_path, "a", license_="CC0-1.0", sha="aa", cell_mean=31.2)
    b = _snapshot(tmp_path, "b", license_="CC0-1.0", sha="aa", cell_mean=31.2)
    manifest = json.loads((b / "MANIFEST.json").read_text(encoding="utf-8"))
    manifest["files"].append(
        {"name": "export.csv", "description": "rows", "sha256": "cc", "bytes": 4}
    )
    (b / "MANIFEST.json").write_text(json.dumps(manifest), encoding="utf-8")

    changes = _report(a, b)["changes"]

    appeared = [c for c in changes if c["kind"] == "absent_to_present"]
    assert [c["subject_id"] for c in appeared] == ["export.csv"]
    assert "from" not in appeared[0]


def test_a_snapshot_missing_its_aggregate_reports_the_manifest_and_invents_no_cells(
    tmp_path: Path,
) -> None:
    """Nothing is fabricated for a file that is not on both sides."""
    a = _snapshot(tmp_path, "a", license_="CC0-1.0", sha="aa", cell_mean=31.2)
    b = _snapshot(tmp_path, "b", license_="CC0-1.0", sha="bb", cell_mean=34.8)
    (b / "aggregate.geojson").unlink()

    changes = _report(a, b)["changes"]

    assert not any(c["subject"] == "cell" for c in changes)
    assert any(c["subject"] == "file" and c["field"] == "sha256" for c in changes)


def test_a_snapshot_manifest_scalar_change_is_reported(tmp_path: Path) -> None:
    a = _snapshot(tmp_path, "a", license_="CC0-1.0", sha="aa", cell_mean=31.2)
    b = _snapshot(tmp_path, "b", license_="CC0-1.0", sha="aa", cell_mean=31.2)
    manifest = json.loads((b / "MANIFEST.json").read_text(encoding="utf-8"))
    manifest["record_count"] = 13
    (b / "MANIFEST.json").write_text(json.dumps(manifest), encoding="utf-8")

    (change,) = _report(a, b)["changes"]

    assert (change["kind"], change["field"]) == ("value_change", "record_count")


def test_an_aggregate_without_features_is_refused(tmp_path: Path) -> None:
    a = _snapshot(tmp_path, "a", license_="CC0-1.0", sha="aa", cell_mean=31.2)
    b = _snapshot(tmp_path, "b", license_="CC0-1.0", sha="aa", cell_mean=31.2)
    (b / "aggregate.geojson").write_text(json.dumps({"type": "FeatureCollection"}), "utf-8")
    with pytest.raises(DiffError, match="no `features` array"):
        _report(a, b)


def test_a_surface_whose_cells_are_not_objects_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"cells": ["nope"]}), encoding="utf-8")
    with pytest.raises(DiffError, match="non-object entry"):
        _report(path, path)


def test_markdown_and_text_render_an_empty_change_set_without_a_table_of_nothing(
    tmp_path: Path,
) -> None:
    a = _surface(tmp_path, "a", [_cell()])
    report = _report(a, a)
    assert "No changes." in render_markdown(report)
    assert "no changes" in render_text(report)


def test_a_cell_that_appears_in_a_snapshot_aggregate_is_absence_to_presence(
    tmp_path: Path,
) -> None:
    a = _snapshot(tmp_path, "a", license_="CC0-1.0", sha="aa", cell_mean=31.2)
    b = _snapshot(tmp_path, "b", license_="CC0-1.0", sha="aa", cell_mean=31.2)
    aggregate = json.loads((b / "aggregate.geojson").read_text(encoding="utf-8"))
    aggregate["features"].append(
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [1, 1]},
            "properties": {"cell_id": "c2", "label": "Two", "temp_c": 29.0},
        }
    )
    (b / "aggregate.geojson").write_text(json.dumps(aggregate), encoding="utf-8")

    changes = [c for c in _report(a, b)["changes"] if c["subject"] == "cell"]

    assert [(c["kind"], c["subject_id"]) for c in changes] == [("absent_to_present", "c2")]
