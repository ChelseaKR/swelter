"""Package: a snapshot rendered as a Frictionless Data Package plus a DCAT catalog record.

The tests are shaped around the four ways this could publish something untrue: a digest that was
recomputed instead of verified, an SPDX identifier a per-location source never granted, a Table
Schema that stops describing the file it names, and an empty cell read as an absence when it is a
measured empty set.
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

from swelter import aggregate as aggregate_module
from swelter import dictionary, package, snapshot
from swelter.config import NetworkConfig, parse_config
from swelter.export import _CSV_FIELDS
from swelter.models import Observation
from swelter.store import open_store, store_paths

from .conftest import ROOT

FIXED_NOW = datetime(2026, 7, 3, 12, 0, 0, tzinfo=UTC)
REPO_CITATION = ROOT / "CITATION.cff"

NETWORK_DOC: dict[str, object] = {
    "name": "Package Test Network",
    "grid_resolution_m": 500,
    "nodes": [
        {"node_id": "node-a", "label": "A", "lat": 33.87, "lon": -117.92},
        {"node_id": "node-b", "label": "B", "lat": 33.88, "lon": -117.93},
    ],
}


def _config() -> NetworkConfig:
    return parse_config(yaml.safe_load(yaml.safe_dump(NETWORK_DOC)))


def _observations() -> list[Observation]:
    """Enough rows, across enough cells and hours, that an ordering bug has room to show.

    One row is always in order and one cell never disagrees with itself; a fixture that small
    would make a determinism claim unfalsifiable rather than true.
    """
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
                    parameter="pm25_ugm3",
                    # One flagged reading, so `qc_flags` is non-empty somewhere and the
                    # empty-cell-is-a-value tests are not asserted over a column of blanks.
                    value=8.0 + hour * 3,
                    unit="ug/m3",
                    qc="spike" if (hour, index) == (3, 0) else "ok",
                )
            )
    return out


def _build_store(store_dir: Path, config: NetworkConfig) -> None:
    paths = store_paths(store_dir)
    with open_store(store_dir) as store:
        store.write(_observations())
        surface = aggregate_module.aggregate(store.all(), config)
    paths["aggregate"].write_text(
        json.dumps(surface.snapshot_geojson(), indent=2), encoding="utf-8"
    )


@pytest.fixture
def release(tmp_path: Path) -> Iterator[Path]:
    """A built snapshot of the synthetic store, ready to be packaged."""
    config = _config()
    store_dir = tmp_path / "store"
    _build_store(store_dir, config)
    out = tmp_path / "snap"
    snapshot.build_snapshot(
        store_dir, out, "1.0.0", None, citation_path=REPO_CITATION, now=FIXED_NOW, config=config
    )
    yield out


def _read_json(path: Path) -> dict[str, Any]:
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(doc, dict)
    return cast("dict[str, Any]", doc)


def _descriptor(out_dir: Path) -> dict[str, Any]:
    return _read_json(out_dir / package.DATAPACKAGE_FILENAME)


def _dcat(out_dir: Path) -> dict[str, Any]:
    return _read_json(out_dir / package.DCAT_FILENAME)


def _resources(out_dir: Path) -> list[dict[str, Any]]:
    resources = _descriptor(out_dir)["resources"]
    assert isinstance(resources, list)
    # A resource list that came back empty would make every per-resource assertion below vacuous.
    assert resources
    return cast("list[dict[str, Any]]", resources)


def _schema(out_dir: Path) -> dict[str, Any]:
    tabular = next(r for r in _resources(out_dir) if r["path"] == package.EXPORT_CSV_FILENAME)
    schema = tabular["schema"]
    assert isinstance(schema, dict)
    return cast("dict[str, Any]", schema)


def _fields(out_dir: Path) -> dict[str, dict[str, Any]]:
    return {field["name"]: field for field in _schema(out_dir)["fields"]}


def _distributions(out_dir: Path) -> list[dict[str, Any]]:
    distributions = _dcat(out_dir)["dcat:distribution"]
    assert isinstance(distributions, list)
    assert distributions
    return cast("list[dict[str, Any]]", distributions)


# --------------------------------------------------------------------------------------------
# What a package is, when the snapshot behind it is intact.
# --------------------------------------------------------------------------------------------


def test_the_package_is_self_contained_and_names_every_file_it_wrote(
    tmp_path: Path, release: Path
) -> None:
    out = tmp_path / "dp"
    result = package.build_package(release, out)

    for name in (
        package.DATAPACKAGE_FILENAME,
        package.DCAT_FILENAME,
        package.EXPORT_CSV_FILENAME,
        snapshot.RAW_OBSERVATIONS_FILENAME,
        snapshot.DATA_LICENSE_FILENAME,
        snapshot.AGGREGATE_FILENAME,
    ):
        assert (out / name).is_file(), name
    # Every declared resource path resolves inside the package: a Frictionless resource path may
    # not escape the package root, which is why the snapshot's files are copied rather than
    # referenced with `../`.
    for path in result.resources:
        assert ".." not in path
        assert (out / path).is_file()
    assert result.record_count == len(_observations())


def test_every_resource_digest_is_over_the_bytes_actually_written(
    tmp_path: Path, release: Path
) -> None:
    """A digest computed over something other than the delivered file is worse than none.

    A harvester republishes these as the dataset's own checksums, so they are checked here against
    the files on disk rather than against the values the writer intended to write.
    """
    out = tmp_path / "dp"
    package.build_package(release, out)
    for resource in _resources(out):
        payload = (out / resource["path"]).read_bytes()
        assert resource["hash"] == f"sha256:{package._sha256(payload)}", resource["path"]
        assert resource["bytes"] == len(payload), resource["path"]


def test_the_record_is_dated_from_the_snapshot_not_from_the_wall_clock(
    tmp_path: Path, release: Path
) -> None:
    out = tmp_path / "dp"
    package.build_package(release, out)
    assert _descriptor(out)["created"] == "2026-07-03T12:00:00Z"
    assert _dcat(out)["dct:issued"] == "2026-07-03T12:00:00Z"


def test_two_packagings_of_one_snapshot_are_byte_identical_across_processes(
    tmp_path: Path, release: Path
) -> None:
    """Determinism measured the only way it can be: separate interpreters, different hash seeds.

    Two renders inside one process share that process's string-hash seed, so a dropped `sorted`
    or a set iteration would be invisible to them. These run as two subprocesses under different
    ``PYTHONHASHSEED`` values.
    """
    outputs: list[bytes] = []
    for seed in ("0", "12345"):
        out = tmp_path / f"dp-{seed}"
        subprocess.run(  # noqa: S603 (#107)
            [
                sys.executable,
                "-c",
                "import sys;from pathlib import Path;from swelter import package;"
                "package.build_package(Path(sys.argv[1]), Path(sys.argv[2]))",
                str(release),
                str(out),
            ],
            check=True,
            env={"PATH": "/usr/bin:/bin", "PYTHONHASHSEED": seed},
            cwd=ROOT,
        )
        outputs.append(
            (out / package.DATAPACKAGE_FILENAME).read_bytes()
            + (out / package.DCAT_FILENAME).read_bytes()
        )
    assert outputs[0] == outputs[1]


# --------------------------------------------------------------------------------------------
# The refusals: what this must never publish a catalog record over.
# --------------------------------------------------------------------------------------------


def test_a_snapshot_whose_bytes_drifted_from_its_manifest_is_refused_by_name(
    tmp_path: Path, release: Path
) -> None:
    """The refusal this module exists for: re-hashing would have blessed the tampering."""
    target = release / snapshot.AGGREGATE_FILENAME
    original = target.read_bytes()
    target.write_bytes(original.replace(b'"provisional"', b'"provisionaL"', 1))
    assert target.read_bytes() != original, "the tamper must actually have changed the file"

    out = tmp_path / "dp"
    with pytest.raises(package.PackageError) as caught:
        package.build_package(release, out)
    assert snapshot.AGGREGATE_FILENAME in str(caught.value)
    assert not out.exists(), "nothing may be written from a snapshot that failed verification"


def test_a_manifest_that_lists_no_files_is_refused_rather_than_verifying_nothing(
    tmp_path: Path, release: Path
) -> None:
    path = release / snapshot.MANIFEST_FILENAME
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["files"] = []
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(package.PackageError, match="lists no files"):
        package.build_package(release, tmp_path / "dp")


def test_a_snapshot_without_recorded_terms_is_refused(tmp_path: Path, release: Path) -> None:
    (release / snapshot.DATA_LICENSE_FILENAME).unlink()
    with pytest.raises(package.PackageError, match="DATA-LICENSE"):
        package.build_package(release, tmp_path / "dp")


def test_a_directory_that_is_not_a_snapshot_is_refused(tmp_path: Path) -> None:
    with pytest.raises(package.PackageError, match="not a swelter snapshot"):
        package.build_package(tmp_path / "nowhere", tmp_path / "dp")


# --------------------------------------------------------------------------------------------
# The Table Schema: generated from the dictionary, and refusing to guess.
# --------------------------------------------------------------------------------------------


def test_table_schema_describes_every_csv_column_in_the_exported_order(
    tmp_path: Path, release: Path
) -> None:
    out = tmp_path / "dp"
    package.build_package(release, out)
    assert list(_fields(out)) == list(_CSV_FIELDS)

    header = (out / package.EXPORT_CSV_FILENAME).read_text(encoding="utf-8").splitlines()[0]
    assert header.split(",") == list(_CSV_FIELDS)


def test_a_csv_column_the_dictionary_does_not_describe_is_refused_not_emitted_blank(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A schema that quietly drops a column tells a portal the file is narrower than it is.

    Every row after the omitted column would then be misparsed, so the writer refuses instead.
    """

    real = dictionary.build_data_dictionary

    def with_an_undescribed_column(**_kwargs: str | None) -> dict[str, object]:
        doc = real()
        columns = doc["csv_columns"]
        assert isinstance(columns, list)
        doc["csv_columns"] = [*columns, "a_column_nobody_described"]
        return doc

    monkeypatch.setattr(dictionary, "build_data_dictionary", with_an_undescribed_column)
    with pytest.raises(package.PackageError, match="a_column_nobody_described"):
        package._table_schema()


def test_an_empty_qc_flags_cell_is_the_empty_set_and_not_a_missing_value(
    tmp_path: Path, release: Path
) -> None:
    """The table-wide missing rule must not reach a column where blank is a measured result.

    Without the field-level override the reference validator reads every unflagged reading as a
    QC check nobody performed — a completed check published as an absence.
    """
    out = tmp_path / "dp"
    package.build_package(release, out)
    assert _schema(out)["missingValues"] == [""]
    fields = _fields(out)
    assert fields["qc_flags"]["missingValues"] == []
    assert fields["qc_flags"]["constraints"]["required"] is True
    # ... and the column it protects is genuinely blank most of the time, so the override is not
    # being asserted over a fixture in which it could never matter.
    rows = (out / package.EXPORT_CSV_FILENAME).read_text(encoding="utf-8").splitlines()[1:]
    flags = [row.split(",")[list(_CSV_FIELDS).index("qc_flags")] for row in rows]
    assert "" in flags and "spike" in flags


def test_an_unmeasured_uncertainty_stays_absent_rather_than_becoming_a_zero(
    tmp_path: Path, release: Path
) -> None:
    out = tmp_path / "dp"
    package.build_package(release, out)
    fields = _fields(out)
    assert "missingValues" not in fields["uncertainty"], (
        "uncertainty must inherit the table's missingValues, so a blank reads as absent"
    )
    assert fields["uncertainty"]["constraints"]["required"] is False


# --------------------------------------------------------------------------------------------
# Rights: an SPDX identifier is a claim, and a per-location source has not made it.
# --------------------------------------------------------------------------------------------


def test_a_cc0_native_release_gets_its_spdx_identifier(tmp_path: Path, release: Path) -> None:
    out = tmp_path / "dp"
    package.build_package(release, out)
    licenses = _descriptor(out)["licenses"]
    assert isinstance(licenses, list) and licenses
    assert licenses[0]["name"] == "CC0-1.0"
    assert "path" not in licenses[0]


def test_a_per_location_source_gets_a_statement_and_the_ledger_not_an_spdx_id(
    tmp_path: Path, release: Path
) -> None:
    """OpenAQ's terms differ location by location; flattening them to one id would assert a grant.

    The package points at the retained per-location evidence instead.
    """
    ledger = release / snapshot.SOURCE_LICENSE_LEDGER_FILENAME
    ledger.write_text(json.dumps({"schema_version": 1, "entries": []}) + "\n", encoding="utf-8")
    manifest_path = release / snapshot.MANIFEST_FILENAME
    doc = json.loads(manifest_path.read_text(encoding="utf-8"))
    doc["data_license"] = "Per-location; see source-license-ledger.json"
    entries = doc["files"]
    entries.append(
        {
            "name": snapshot.SOURCE_LICENSE_LEDGER_FILENAME,
            "description": "per-location evidence",
            "sha256": package._sha256(ledger.read_bytes()),
            "bytes": ledger.stat().st_size,
        }
    )
    manifest_path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")

    out = tmp_path / "dp"
    package.build_package(release, out)
    licenses = _descriptor(out)["licenses"]
    assert isinstance(licenses, list) and licenses
    assert "name" not in licenses[0], "no SPDX identifier may be invented for mixed terms"
    assert licenses[0]["title"] == "Per-location; see source-license-ledger.json"
    assert licenses[0]["path"] == snapshot.SOURCE_LICENSE_LEDGER_FILENAME
    assert (out / snapshot.SOURCE_LICENSE_LEDGER_FILENAME).is_file()


# --------------------------------------------------------------------------------------------
# The DCAT record: what a portal harvests, and what it must not be told.
# --------------------------------------------------------------------------------------------


def test_the_dcat_record_is_a_dataset_with_one_checksummed_distribution_per_resource(
    tmp_path: Path, release: Path
) -> None:
    out = tmp_path / "dp"
    package.build_package(release, out)
    record = _dcat(out)
    assert record["@type"] == "dcat:Dataset"
    assert "dcat" in record["@context"]
    resources = _resources(out)
    distributions = _distributions(out)
    assert len(distributions) == len(resources)
    by_hash = {str(r["hash"]).removeprefix("sha256:") for r in resources}
    assert {d["spdx:checksum"]["spdx:checksumValue"] for d in distributions} == by_hash


def test_the_title_and_description_are_language_tagged_english_not_untagged_prose(
    tmp_path: Path, release: Path
) -> None:
    """An untagged string lets a Spanish-language portal present English as its translation.

    swelter has no independently reviewed Spanish catalog text (#106), so the record says `en`.
    """
    out = tmp_path / "dp"
    package.build_package(release, out)
    record = _dcat(out)
    assert record["dct:title"]["@language"] == "en"
    assert record["dct:description"]["@language"] == "en"


def test_without_a_base_url_no_distribution_carries_an_access_url_and_it_says_so(
    tmp_path: Path, release: Path
) -> None:
    out = tmp_path / "dp"
    result = package.build_package(release, out)
    notes = _dcat(out)["swelter:note"]
    assert isinstance(notes, list)
    assert all("dcat:accessURL" not in d for d in _distributions(out))
    assert any("access URL" in note for note in result.notes)
    assert any("access URL" in str(note) for note in notes)


def test_a_base_url_produces_access_and_download_urls_for_every_distribution(
    tmp_path: Path, release: Path
) -> None:
    out = tmp_path / "dp"
    package.build_package(release, out, base_url="https://example.org/data/")
    for distribution in _distributions(out):
        assert str(distribution["dcat:accessURL"]).startswith("https://example.org/data/")
        assert distribution["dcat:accessURL"] == distribution["dcat:downloadURL"]


def test_a_release_with_no_observation_window_publishes_no_temporal_extent(
    tmp_path: Path, release: Path
) -> None:
    """An interval with null endpoints is worse than no interval: a portal renders it as a range."""
    path = release / snapshot.MANIFEST_FILENAME
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["observation_window"] = None
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")

    out = tmp_path / "dp"
    package.build_package(release, out)
    assert "temporal" not in _descriptor(out)
    assert "dct:temporal" not in _dcat(out)


def test_a_snapshot_without_a_surface_still_packages_and_says_what_is_missing(
    tmp_path: Path, release: Path
) -> None:
    path = release / snapshot.MANIFEST_FILENAME
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["files"] = [f for f in doc["files"] if f["name"] != snapshot.AGGREGATE_FILENAME]
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")

    out = tmp_path / "dp"
    result = package.build_package(release, out)
    assert not (out / snapshot.AGGREGATE_FILENAME).exists()
    assert any(snapshot.AGGREGATE_FILENAME in note for note in result.notes)


def test_the_cli_verb_refuses_with_a_nonzero_status_and_writes_nothing(
    tmp_path: Path, release: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from swelter.cli import main

    (release / snapshot.DATA_LICENSE_FILENAME).unlink()
    out = tmp_path / "dp"
    assert main(["package", str(release), "--out", str(out)]) == 1
    assert "refusing" in capsys.readouterr().err
    assert not out.exists()
