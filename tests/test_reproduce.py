"""Reproduce: re-deriving a frozen release's surface from its own frozen inputs.

The tests split in two. Most build a small synthetic release so every branch — a missing
correction registry, a manifest that records no version, a configuration that is not the one that
built the release — can be exercised exactly. One runs the real bundled demo end to end, because
a byte-identical claim over eight readings is not the claim the verb makes.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from swelter import aggregate as aggregate_module
from swelter import calibrate, reproduce, snapshot
from swelter.cli import main
from swelter.config import NetworkConfig, configuration_fingerprint, parse_config
from swelter.models import RAW, Observation
from swelter.store import open_store, store_paths

from .conftest import ROOT

FIXED_NOW = datetime(2026, 7, 3, 12, 0, 0, tzinfo=UTC)
REPO_CITATION = ROOT / "CITATION.cff"

NETWORK_DOC: dict[str, object] = {
    "name": "Reproduce Test Network",
    "grid_resolution_m": 500,
    "nodes": [
        {"node_id": "node-a", "label": "A", "lat": 33.87, "lon": -117.92},
        {"node_id": "node-b", "label": "B", "lat": 33.88, "lon": -117.93},
    ],
}


def _config() -> NetworkConfig:
    return parse_config(yaml.safe_load(yaml.safe_dump(NETWORK_DOC)))


def _observations() -> list[Observation]:
    out: list[Observation] = []
    for hour in range(6):
        stamp = f"2026-06-0{hour + 1}T0{hour}:00:00Z"
        for index, node in enumerate(("node-a", "node-b")):
            out.append(
                Observation(
                    node_id=node,
                    timestamp=stamp,
                    parameter="temp_c",
                    value=24.0 + hour + index,
                    unit="degC",
                )
            )
            out.append(
                Observation(
                    node_id=node,
                    timestamp=stamp,
                    parameter="humidity_pct",
                    value=40.0 + hour,
                    unit="percent",
                )
            )
    return out


def _registry() -> calibrate.CorrectionRegistry:
    registry = calibrate.CorrectionRegistry()
    registry.add(
        calibrate.Correction(
            version="temp_c.ols.node-a@testfit",
            node_id="node-a",
            parameter="temp_c",
            method="ols",
            predictors=("raw",),
            coefficients=(1.02,),
            intercept=-0.4,
            residual_std=0.31,
            r2=0.97,
            n=24,
            reference="ref-1",
            window_start="2026-05-01T00:00:00Z",
            window_end="2026-05-08T00:00:00Z",
        )
    )
    return registry


def _build_store(store_dir: Path, config: NetworkConfig) -> None:
    """A store shaped exactly like one the pipeline leaves behind: raw rows, calibrated rows,
    a committed correction registry, and the aggregated surface written the way `swelter
    aggregate` writes it."""
    registry = _registry()
    raw = _observations()
    paths = store_paths(store_dir)
    with open_store(store_dir) as store:
        store.write(raw)
        store.write([o for o in calibrate.apply(raw, registry) if o.calibration != RAW])
        surface = aggregate_module.aggregate(store.all(), config)
    registry.to_yaml(paths["registry"])
    paths["aggregate"].write_text(
        json.dumps(surface.snapshot_geojson(), indent=2), encoding="utf-8"
    )


@pytest.fixture
def release(tmp_path: Path) -> Iterator[Path]:
    """A built snapshot of the synthetic store, ready to be reproduced."""
    config = _config()
    store_dir = tmp_path / "store"
    _build_store(store_dir, config)
    out = tmp_path / "snap"
    snapshot.build_snapshot(
        store_dir, out, "1.0.0", None, citation_path=REPO_CITATION, now=FIXED_NOW, config=config
    )
    yield out


def _rewrite_manifest(release_dir: Path, mutate: object) -> None:
    path = release_dir / snapshot.MANIFEST_FILENAME
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert callable(mutate)
    mutate(doc)
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")


def _refresh_manifest_digests(release_dir: Path) -> None:
    """Keep the manifest honest after an edit, so ONLY the surface comparison can differ."""

    def mutate(doc: dict[str, object]) -> None:
        entries = doc["files"]
        assert isinstance(entries, list)
        for entry in entries:
            payload = (release_dir / entry["name"]).read_bytes()
            entry["sha256"] = hashlib.sha256(payload).hexdigest()
            entry["bytes"] = len(payload)

    _rewrite_manifest(release_dir, mutate)


# --------------------------------------------------------------------------------------------
# The snapshot side: what a release now records about how it was built.
# --------------------------------------------------------------------------------------------


def test_manifest_records_the_versions_and_configuration_a_rebuild_needs(release: Path) -> None:
    doc = json.loads((release / snapshot.MANIFEST_FILENAME).read_text(encoding="utf-8"))
    assert doc["data_schema_version"] == 2
    assert doc["config_fingerprint"] == configuration_fingerprint(_config())
    assert doc["swelter_version"]


def test_a_snapshot_built_without_a_configuration_says_so_rather_than_implying_one(
    tmp_path: Path,
) -> None:
    config = _config()
    store_dir = tmp_path / "store"
    _build_store(store_dir, config)
    out = tmp_path / "snap"
    manifest = snapshot.build_snapshot(
        store_dir, out, "1.0.0", None, citation_path=REPO_CITATION, now=FIXED_NOW
    )
    assert manifest.config_fingerprint is None
    assert any("cannot re-derive" in note for note in manifest.notes)


def test_the_fingerprint_is_a_digest_and_never_the_coordinates_themselves(release: Path) -> None:
    """Hard rule 2: `network.yaml` holds precise host coordinates, so no part of it may travel
    inside a published release. Only the digest does."""
    published = "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in sorted(release.iterdir())
        if path.is_file()
    )
    # Bounded so the grid-snapped cell centre the surface legitimately publishes
    # (-117.928057) does not satisfy the assertion as a prefix of the precise coordinate.
    assert not re.search(r"(?<![\d.])33\.87(?![\d])", published)
    assert not re.search(r"(?<![\d.])-117\.92(?![\d])", published)
    assert configuration_fingerprint(_config()) in published


# --------------------------------------------------------------------------------------------
# The happy path, and the two ways a release can fail to hold together.
# --------------------------------------------------------------------------------------------


def test_a_release_reproduces_byte_identically_and_every_required_check_ran(
    release: Path,
) -> None:
    receipt = reproduce.reproduce(release, _config())
    assert receipt.verdict == reproduce.VERDICT_REPRODUCED
    assert receipt.exit_code == reproduce.EXIT_REPRODUCED
    passed = {c.name for c in receipt.checks if c.status == reproduce.CHECK_OK}
    assert passed >= reproduce.REQUIRED_CHECKS
    assert receipt.surface["frozen_sha256"] == receipt.surface["rebuilt_sha256"]
    assert receipt.surface["first_difference"] is None


def test_one_edited_reading_yields_a_mismatch_naming_the_first_differing_feature(
    release: Path,
) -> None:
    path = release / snapshot.RAW_OBSERVATIONS_FILENAME
    doc = json.loads(path.read_text(encoding="utf-8"))
    latest = max(o["timestamp"] for o in doc["observations"])
    target = next(
        o for o in doc["observations"] if o["timestamp"] == latest and o["parameter"] == "temp_c"
    )
    target["value"] += 9.0
    path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    _refresh_manifest_digests(release)

    receipt = reproduce.reproduce(release, _config())
    assert receipt.verdict == reproduce.VERDICT_MISMATCH
    assert receipt.exit_code == reproduce.EXIT_NOT_REPRODUCED
    digests = receipt.check("frozen_digests")
    assert digests is not None and digests.status == reproduce.CHECK_OK
    difference = receipt.surface["first_difference"]
    assert isinstance(difference, str) and difference.startswith("$.features[")
    assert receipt.surface["frozen_sha256"] != receipt.surface["rebuilt_sha256"]


def test_an_edit_the_published_surface_cannot_see_is_still_caught_by_the_recorded_digests(
    release: Path,
) -> None:
    """The frozen surface publishes the latest cell-hour per cell, so an edit to an earlier hour
    changes no published feature. That is not a reproduction: the release no longer matches what
    it says about itself, and the verdict must say so rather than reporting a clean rebuild."""
    path = release / snapshot.RAW_OBSERVATIONS_FILENAME
    doc = json.loads(path.read_text(encoding="utf-8"))
    earliest = min(o["timestamp"] for o in doc["observations"])
    target = next(o for o in doc["observations"] if o["timestamp"] == earliest)
    target["value"] += 9.0
    path.write_text(json.dumps(doc, indent=2), encoding="utf-8")

    receipt = reproduce.reproduce(release, _config())
    surface_check = receipt.check("surface_identical")
    assert surface_check is not None and surface_check.status == reproduce.CHECK_OK
    digests = receipt.check("frozen_digests")
    assert digests is not None and digests.status == reproduce.CHECK_FAIL
    assert receipt.verdict == reproduce.VERDICT_MISMATCH
    assert receipt.exit_code == reproduce.EXIT_NOT_REPRODUCED


def test_a_manifest_that_lists_no_files_fails_the_digest_check_instead_of_passing_it(
    release: Path,
) -> None:
    """A digest check that covered nothing would report clean over a snapshot whose every file
    had been replaced."""

    def mutate(doc: dict[str, object]) -> None:
        doc["files"] = []

    _rewrite_manifest(release, mutate)
    receipt = reproduce.reproduce(release, _config())
    digests = receipt.check("frozen_digests")
    assert digests is not None and digests.status == reproduce.CHECK_FAIL
    assert receipt.verdict == reproduce.VERDICT_MISMATCH


# --------------------------------------------------------------------------------------------
# Absence: the states that are neither a pass nor a mismatch.
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("field", "reason"),
    [
        ("swelter_version", "version not recorded"),
        ("data_schema_version", "data-schema version not recorded"),
        ("config_fingerprint", "network configuration not recorded"),
    ],
)
def test_a_release_that_does_not_record_what_built_it_is_indeterminate_not_reproduced(
    release: Path, field: str, reason: str
) -> None:
    def mutate(doc: dict[str, object]) -> None:
        doc.pop(field)

    _rewrite_manifest(release, mutate)
    receipt = reproduce.reproduce(release, _config())
    assert receipt.verdict == reproduce.VERDICT_INDETERMINATE
    assert receipt.exit_code == reproduce.EXIT_INDETERMINATE
    assert receipt.exit_code != reproduce.EXIT_REPRODUCED
    assert any(reason in r for r in receipt.reasons)
    named = receipt.check(field)
    assert named is not None and named.status == reproduce.CHECK_FAIL


def test_a_different_swelter_version_is_reported_and_not_attempted(release: Path) -> None:
    receipt = reproduce.reproduce(release, _config(), running_version="99.0.0")
    assert receipt.verdict == reproduce.VERDICT_INDETERMINATE
    assert any("cross-version reproduction is reported" in r for r in receipt.reasons)
    assert receipt.surface["rebuilt_sha256"] is None


def test_a_configuration_that_did_not_build_the_release_is_refused_by_name(release: Path) -> None:
    other = dict(NETWORK_DOC)
    other["grid_resolution_m"] = 250
    receipt = reproduce.reproduce(release, parse_config(other))
    assert receipt.verdict == reproduce.VERDICT_REFUSED
    assert receipt.exit_code == reproduce.EXIT_NOT_REPRODUCED
    assert any("not the one this release was built with" in r for r in receipt.reasons)
    assert receipt.surface["rebuilt_sha256"] is None


def test_a_release_without_a_correction_registry_is_refused_with_a_named_error(
    release: Path,
) -> None:
    (release / snapshot.CORRECTIONS_FILENAME).unlink()
    receipt = reproduce.reproduce(release, _config())
    assert receipt.verdict == reproduce.VERDICT_REFUSED
    assert any(snapshot.CORRECTIONS_FILENAME in r for r in receipt.reasons)


def test_a_release_without_a_surface_is_refused_rather_than_reproduced(release: Path) -> None:
    (release / snapshot.AGGREGATE_FILENAME).unlink()
    receipt = reproduce.reproduce(release, _config())
    assert receipt.verdict == reproduce.VERDICT_REFUSED
    assert any(snapshot.AGGREGATE_FILENAME in r for r in receipt.reasons)


def test_a_release_freezing_no_observations_is_refused_rather_than_matching_an_empty_surface(
    release: Path,
) -> None:
    """Two absences must never agree: an empty rebuild equals an empty frozen surface, and
    reporting that as a reproduction is the defect this verb exists to avoid."""
    path = release / snapshot.RAW_OBSERVATIONS_FILENAME
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["observations"] = []
    path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    (release / snapshot.AGGREGATE_FILENAME).write_text(
        json.dumps({"type": "FeatureCollection", "features": []}, indent=2), encoding="utf-8"
    )
    _refresh_manifest_digests(release)

    receipt = reproduce.reproduce(release, _config())
    assert receipt.verdict == reproduce.VERDICT_REFUSED
    assert any("would prove nothing" in r for r in receipt.reasons)


def test_a_reading_with_no_value_is_refused_rather_than_averaged_around(release: Path) -> None:
    path = release / snapshot.RAW_OBSERVATIONS_FILENAME
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["observations"][0]["value"] = None
    path.write_text(json.dumps(doc, indent=2), encoding="utf-8")

    receipt = reproduce.reproduce(release, _config())
    assert receipt.verdict == reproduce.VERDICT_REFUSED
    assert any("cannot be reproduced" in r for r in receipt.reasons)


def test_a_directory_that_is_not_a_snapshot_raises_rather_than_returning_a_verdict(
    tmp_path: Path,
) -> None:
    with pytest.raises(reproduce.ReproduceError):
        reproduce.reproduce(tmp_path, _config())


# --------------------------------------------------------------------------------------------
# The receipt.
# --------------------------------------------------------------------------------------------


def test_the_receipt_is_byte_identical_across_two_runs(release: Path) -> None:
    first = reproduce.reproduce(release, _config()).to_json()
    second = reproduce.reproduce(release, _config()).to_json()
    assert first == second
    assert b"20" + datetime.now(UTC).strftime("%y-%m-%d").encode()[2:] not in first


def test_the_receipt_counts_the_three_outcomes_separately(release: Path) -> None:
    doc = json.loads(reproduce.reproduce(release, _config()).to_json())
    assert doc["counts"] == {"PASS": len(doc["checks"]), "FAIL": 0, "NOT_APPLICABLE": 0}
    assert doc["schema_version"] == reproduce.RECEIPT_SCHEMA_VERSION


def test_a_verdict_is_never_built_from_the_absence_of_a_failure() -> None:
    """The load-bearing rule, exercised directly: a required check that never ran must not read
    as a pass. Reached from here rather than only through `reproduce`, so the branch is a rule the
    suite enforces rather than an unreachable comment."""
    every = [
        reproduce.Check(name, reproduce.CHECK_OK, "") for name in sorted(reproduce.REQUIRED_CHECKS)
    ]
    assert reproduce.verdict_for(every)[0] == reproduce.VERDICT_REPRODUCED

    for omitted in sorted(reproduce.REQUIRED_CHECKS):
        short = [c for c in every if c.name != omitted]
        verdict, reasons = reproduce.verdict_for(short)
        assert verdict == reproduce.VERDICT_INDETERMINATE, omitted
        assert any(omitted in reason for reason in reasons)
        assert not [c for c in short if c.status == reproduce.CHECK_FAIL], (
            "nothing failed here — the point is that nothing ran either"
        )

    failed_one = [
        reproduce.Check(
            c.name, reproduce.CHECK_FAIL if c.name == "surface_identical" else c.status, ""
        )
        for c in every
    ]
    assert reproduce.verdict_for(failed_one)[0] == reproduce.VERDICT_MISMATCH


def test_a_not_applicable_check_is_never_counted_as_a_pass() -> None:
    """ "There were no corrections to compare" and "the corrections compared clean" are different
    sentences, and only one of them is evidence."""
    for absent in sorted(reproduce.REQUIRED_CHECKS):
        checks = [
            reproduce.Check(name, reproduce.CHECK_NA if name == absent else reproduce.CHECK_OK, "")
            for name in sorted(reproduce.REQUIRED_CHECKS)
        ]
        verdict, reasons = reproduce.verdict_for(checks)
        assert verdict == reproduce.VERDICT_INDETERMINATE, absent
        assert verdict != reproduce.VERDICT_REPRODUCED
        assert any(absent in reason for reason in reasons)


def test_first_difference_names_a_json_path_not_a_byte_offset() -> None:
    left = json.dumps({"features": [{"properties": {"temp_c": 20.0}}]}).encode()
    right = json.dumps({"features": [{"properties": {"temp_c": 21.0}}]}).encode()
    assert reproduce.first_difference(left, right) == "$.features[0].properties.temp_c"
    assert reproduce.first_difference(left, left) is None


def test_first_difference_reports_the_root_when_only_the_serialisation_moved() -> None:
    left = json.dumps({"a": 1, "b": 2}, indent=2).encode()
    right = json.dumps({"b": 2, "a": 1}, indent=4).encode()
    assert reproduce.first_difference(left, right) == "$"


def test_first_difference_names_an_element_that_is_present_on_only_one_side() -> None:
    left = json.dumps({"features": [1, 2, 3]}).encode()
    right = json.dumps({"features": [1, 2]}).encode()
    assert reproduce.first_difference(left, right) == "$.features[2]"


def test_a_manifest_that_is_not_readable_json_raises_rather_than_returning_a_verdict(
    release: Path,
) -> None:
    (release / snapshot.MANIFEST_FILENAME).write_text("{not json", encoding="utf-8")
    with pytest.raises(reproduce.ReproduceError):
        reproduce.reproduce(release, _config())


def test_a_manifest_that_is_not_a_json_object_raises(release: Path) -> None:
    (release / snapshot.MANIFEST_FILENAME).write_text("[]", encoding="utf-8")
    with pytest.raises(reproduce.ReproduceError):
        reproduce.reproduce(release, _config())


def test_a_frozen_surface_that_is_not_json_is_a_mismatch_at_the_root_not_a_crash(
    release: Path,
) -> None:
    (release / snapshot.AGGREGATE_FILENAME).write_text("not json at all", encoding="utf-8")
    _refresh_manifest_digests(release)
    receipt = reproduce.reproduce(release, _config())
    assert receipt.verdict == reproduce.VERDICT_MISMATCH
    assert receipt.surface["first_difference"] == "$"
    assert receipt.surface["frozen_features"] is None


def test_the_rendered_receipt_names_the_verdict_every_check_and_every_reason(
    release: Path,
) -> None:
    (release / snapshot.CORRECTIONS_FILENAME).unlink()
    receipt = reproduce.reproduce(release, _config())
    lines = reproduce.render(receipt)
    body = "\n".join(lines)
    assert "NOT reproduced" in body
    for check in receipt.checks:
        assert f"[{check.status}] {check.name}" in body
    for reason in receipt.reasons:
        assert reason in body
    assert "0 not applicable" in body


def test_an_unreadable_correction_registry_is_refused_by_name(release: Path) -> None:
    (release / snapshot.CORRECTIONS_FILENAME).write_text("::: not yaml :::", encoding="utf-8")
    receipt = reproduce.reproduce(release, _config())
    assert receipt.verdict == reproduce.VERDICT_REFUSED
    assert any("unusable" in r for r in receipt.reasons)


def test_a_raw_export_that_is_not_an_observations_document_is_refused(release: Path) -> None:
    (release / snapshot.RAW_OBSERVATIONS_FILENAME).write_text('{"license": "CC0-1.0"}', "utf-8")
    receipt = reproduce.reproduce(release, _config())
    assert receipt.verdict == reproduce.VERDICT_REFUSED
    assert any("observations" in r for r in receipt.reasons)


# --------------------------------------------------------------------------------------------
# The CLI.
# --------------------------------------------------------------------------------------------


def test_cli_exits_zero_and_can_write_the_receipt(
    release: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config_path = tmp_path / "network.yaml"
    config_path.write_text(yaml.safe_dump(NETWORK_DOC), encoding="utf-8")
    receipt_path = tmp_path / "out" / "REPRODUCTION.json"
    rc = main(
        [
            "reproduce",
            str(release),
            "--config",
            str(config_path),
            "--json",
            "--receipt",
            str(receipt_path),
        ]
    )
    assert rc == 0
    doc = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert doc["verdict"] == reproduce.VERDICT_REPRODUCED
    assert doc["running"]["config_path"] == str(config_path)
    assert json.loads(capsys.readouterr().out)["verdict"] == reproduce.VERDICT_REPRODUCED


def test_cli_uses_a_distinct_exit_status_for_indeterminate(release: Path, tmp_path: Path) -> None:
    """Exit 2, not 0: a caller gating on `$? -eq 0` must not be told that a release nobody could
    check is a release that checked out."""

    def mutate(doc: dict[str, object]) -> None:
        doc.pop("config_fingerprint")

    _rewrite_manifest(release, mutate)
    config_path = tmp_path / "network.yaml"
    config_path.write_text(yaml.safe_dump(NETWORK_DOC), encoding="utf-8")
    rc = main(["reproduce", str(release), "--config", str(config_path)])
    assert rc == reproduce.EXIT_INDETERMINATE
    assert rc != 0


def test_snapshot_records_no_fingerprint_when_there_is_no_configuration_file(
    tmp_path: Path,
) -> None:
    """`_load_config` substitutes an empty network for a missing file so the pipeline can keep
    running. An empty network has a perfectly good fingerprint, and writing *that* into a release
    manifest would publish "built with this configuration" over a file that was never read."""
    store_dir = tmp_path / "store"
    _build_store(store_dir, _config())
    out = tmp_path / "snap"
    rc = main(
        [
            "snapshot",
            "--store",
            str(store_dir),
            "--out",
            str(out),
            "--version",
            "1.0.0",
            "--config",
            str(tmp_path / "there-is-no-network-here.yaml"),
        ]
    )
    assert rc == 0
    doc = json.loads((out / snapshot.MANIFEST_FILENAME).read_text(encoding="utf-8"))
    assert doc["config_fingerprint"] is None
    assert doc["config_fingerprint"] != configuration_fingerprint(NetworkConfig())
    assert any("cannot re-derive" in note for note in doc["notes"])

    # And the release it produced reads as unknown, not as sound and not as rotten.
    config_path = tmp_path / "network.yaml"
    config_path.write_text(yaml.safe_dump(NETWORK_DOC), encoding="utf-8")
    assert main(["reproduce", str(out), "--config", str(config_path)]) == (
        reproduce.EXIT_INDETERMINATE
    )


def test_reproduce_refuses_a_missing_configuration_by_its_own_name(
    release: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Not "the configuration does not match" — there is no configuration. Reproducing against
    the empty substitute would rebuild an empty surface and blame the release for a bad path."""
    rc = main(["reproduce", str(release), "--config", str(tmp_path / "absent.yaml")])
    assert rc == reproduce.EXIT_NOT_REPRODUCED
    err = capsys.readouterr().err
    assert "no network configuration at" in err
    assert "is not the one this release was built with" not in err


def test_cli_reports_a_snapshot_it_cannot_read_at_all(tmp_path: Path) -> None:
    rc = main(["reproduce", str(tmp_path), "--config", str(tmp_path / "absent.yaml")])
    assert rc == reproduce.EXIT_NOT_REPRODUCED


# --------------------------------------------------------------------------------------------
# The real thing.
# --------------------------------------------------------------------------------------------


def test_the_bundled_demo_release_reproduces_byte_identically(tmp_path: Path) -> None:
    """The claim `docs/citability.md` makes, against the real 150k-observation demo replay and
    the repository's own `network.yaml` — not a fixture built to reproduce."""
    store_dir = tmp_path / "store"
    assert (
        main(
            [
                "demo",
                "--data",
                str(ROOT / "data" / "demo"),
                "--store",
                str(store_dir),
                "--config",
                str(ROOT / "network.yaml"),
            ]
        )
        == 0
    )
    out = tmp_path / "snap"
    assert (
        main(
            [
                "snapshot",
                "--store",
                str(store_dir),
                "--out",
                str(out),
                "--version",
                "1.0.0",
                "--config",
                str(ROOT / "network.yaml"),
            ]
        )
        == 0
    )
    rc = main(["reproduce", str(out), "--config", str(ROOT / "network.yaml")])
    assert rc == reproduce.EXIT_REPRODUCED
