"""Snapshot: a frozen, citable data release built from an existing store (E3)."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from swelter import snapshot
from swelter.cli import main
from swelter.store import SqliteStore

from .conftest import ROOT, make_obs

FIXED_NOW = datetime(2026, 7, 3, 12, 0, 0, tzinfo=UTC)
REPO_CITATION = ROOT / "CITATION.cff"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def demo_store(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The bundled demo replayed through the whole pipeline — real raw observations, a fitted
    correction registry, and an aggregated surface, exactly what a snapshot freezes."""
    store_dir = tmp_path_factory.mktemp("snapshot-store") / "store"
    rc = main(
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
    assert rc == 0
    return store_dir


def test_build_snapshot_writes_all_expected_files(tmp_path: Path, demo_store: Path) -> None:
    out = tmp_path / "snap"
    manifest = snapshot.build_snapshot(
        demo_store, out, "1.0.0", None, citation_path=REPO_CITATION, now=FIXED_NOW
    )
    assert (out / snapshot.MANIFEST_FILENAME).is_file()
    assert (out / snapshot.DATA_CITATION_FILENAME).is_file()
    assert (out / snapshot.CITATION_TXT_FILENAME).is_file()
    assert (out / snapshot.RAW_OBSERVATIONS_FILENAME).is_file()
    assert (out / snapshot.CORRECTIONS_FILENAME).is_file()
    assert (out / snapshot.AGGREGATE_FILENAME).is_file()
    assert manifest.record_count > 0
    assert manifest.observation_window is not None
    assert manifest.observation_window[0] <= manifest.observation_window[1]


def test_manifest_has_stable_keys_and_hashes_match_recomputation(
    tmp_path: Path, demo_store: Path
) -> None:
    out = tmp_path / "snap"
    snapshot.build_snapshot(
        demo_store, out, "1.0.0", None, citation_path=REPO_CITATION, now=FIXED_NOW
    )
    doc = json.loads((out / snapshot.MANIFEST_FILENAME).read_text(encoding="utf-8"))

    assert set(doc) == {
        "release_version",
        "created_at",
        "swelter_version",
        "record_count",
        "observation_window",
        "doi",
        "files",
        "notes",
    }
    assert doc["release_version"] == "1.0.0"
    assert doc["created_at"] == "2026-07-03T12:00:00Z"
    assert doc["swelter_version"]
    assert doc["record_count"] > 0
    assert doc["observation_window"]["start"] <= doc["observation_window"]["end"]
    assert doc["files"], "expected at least the raw-observations file to be manifested"

    for entry in doc["files"]:
        assert set(entry) == {"name", "description", "sha256", "bytes"}
        path = out / entry["name"]
        assert _sha256(path) == entry["sha256"]
        assert entry["bytes"] == path.stat().st_size


def test_data_citation_cff_is_a_dataset_under_cc0_with_the_given_doi(
    tmp_path: Path, demo_store: Path
) -> None:
    out = tmp_path / "snap"
    snapshot.build_snapshot(
        demo_store,
        out,
        "2.3.4",
        "10.5281/zenodo.1234567",
        citation_path=REPO_CITATION,
        now=FIXED_NOW,
    )
    doc = yaml.safe_load((out / snapshot.DATA_CITATION_FILENAME).read_text(encoding="utf-8"))
    assert doc["cff-version"] == "1.2.0"
    assert doc["type"] == "dataset"
    assert doc["license"] == "CC0-1.0"
    assert doc["version"] == "2.3.4"
    assert doc["date-released"] == "2026-07-03"
    assert doc["title"] == "swelter observation snapshot 2.3.4"
    assert doc["authors"], "authors should be mirrored from the repo CITATION.cff"
    assert doc["identifiers"][0]["type"] == "doi"
    assert doc["identifiers"][0]["value"] == "10.5281/zenodo.1234567"

    software_cff = yaml.safe_load(REPO_CITATION.read_text(encoding="utf-8"))
    assert software_cff["type"] == "software"  # the two CFFs stay distinct
    assert doc["authors"] == software_cff["authors"]


def test_data_citation_cff_placeholder_doi_when_none_given(
    tmp_path: Path, demo_store: Path
) -> None:
    out = tmp_path / "snap"
    snapshot.build_snapshot(
        demo_store, out, "1.0.0", None, citation_path=REPO_CITATION, now=FIXED_NOW
    )
    doc = yaml.safe_load((out / snapshot.DATA_CITATION_FILENAME).read_text(encoding="utf-8"))
    identifier = doc["identifiers"][0]
    assert identifier["value"] == snapshot.DOI_PLACEHOLDER
    assert "placeholder" in identifier["description"].lower()


def test_citation_txt_is_a_nonempty_pasteable_string(tmp_path: Path, demo_store: Path) -> None:
    out = tmp_path / "snap"
    snapshot.build_snapshot(
        demo_store,
        out,
        "1.0.0",
        "10.5281/zenodo.99",
        citation_path=REPO_CITATION,
        now=FIXED_NOW,
    )
    text = (out / snapshot.CITATION_TXT_FILENAME).read_text(encoding="utf-8").strip()
    assert text
    assert "swelter observation snapshot 1.0.0" in text
    assert "10.5281/zenodo.99" in text
    assert "2026" in text


def test_rerun_with_fixed_timestamp_is_byte_identical(tmp_path: Path, demo_store: Path) -> None:
    out1 = tmp_path / "run1"
    out2 = tmp_path / "run2"
    snapshot.build_snapshot(
        demo_store,
        out1,
        "1.0.0",
        "10.5281/zenodo.42",
        citation_path=REPO_CITATION,
        now=FIXED_NOW,
    )
    snapshot.build_snapshot(
        demo_store,
        out2,
        "1.0.0",
        "10.5281/zenodo.42",
        citation_path=REPO_CITATION,
        now=FIXED_NOW,
    )
    for name in (
        snapshot.MANIFEST_FILENAME,
        snapshot.DATA_CITATION_FILENAME,
        snapshot.CITATION_TXT_FILENAME,
        snapshot.RAW_OBSERVATIONS_FILENAME,
        snapshot.CORRECTIONS_FILENAME,
        snapshot.AGGREGATE_FILENAME,
    ):
        assert (out1 / name).read_bytes() == (out2 / name).read_bytes(), name


def test_raw_only_store_snapshots_honestly_without_mixing_in_absent_data(tmp_path: Path) -> None:
    """No calibration has run yet, so there is no corrections.yaml/aggregate.geojson to freeze —
    the snapshot must say so rather than silently omitting or fabricating either file."""
    store_dir = tmp_path / "raw-only-store"
    db = SqliteStore(store_dir / "observations.db")
    db.write([make_obs()])
    db.close()

    out = tmp_path / "snap"
    manifest = snapshot.build_snapshot(
        store_dir, out, "0.0.1", None, citation_path=REPO_CITATION, now=FIXED_NOW
    )
    assert manifest.record_count == 1
    assert any("corrections.yaml" in note for note in manifest.notes)
    assert any("aggregate.geojson" in note for note in manifest.notes)
    assert not (out / snapshot.CORRECTIONS_FILENAME).exists()
    assert not (out / snapshot.AGGREGATE_FILENAME).exists()
    assert (out / snapshot.RAW_OBSERVATIONS_FILENAME).is_file()


def test_missing_repo_citation_falls_back_instead_of_failing(tmp_path: Path) -> None:
    store_dir = tmp_path / "raw-only-store"
    db = SqliteStore(store_dir / "observations.db")
    db.write([make_obs()])
    db.close()

    out = tmp_path / "snap"
    manifest = snapshot.build_snapshot(
        store_dir,
        out,
        "0.0.1",
        None,
        citation_path=tmp_path / "no-such-CITATION.cff",
        now=FIXED_NOW,
    )
    assert manifest.record_count == 1
    doc = yaml.safe_load((out / snapshot.DATA_CITATION_FILENAME).read_text(encoding="utf-8"))
    assert doc["authors"]  # the fallback author, not an empty/broken list


def test_cli_snapshot_prints_citation_and_returns_zero(
    tmp_path: Path, demo_store: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "cli-snap"
    rc = main(["snapshot", "--store", str(demo_store), "--out", str(out), "--version", "9.9.9"])
    assert rc == 0
    printed = capsys.readouterr().out.strip()
    assert "swelter observation snapshot 9.9.9" in printed
    assert (out / snapshot.MANIFEST_FILENAME).is_file()


def test_cli_snapshot_defaults_version_to_the_package_version(
    tmp_path: Path, demo_store: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from swelter import __version__

    out = tmp_path / "cli-snap-default"
    rc = main(["snapshot", "--store", str(demo_store), "--out", str(out)])
    assert rc == 0
    capsys.readouterr()
    manifest = json.loads((out / snapshot.MANIFEST_FILENAME).read_text(encoding="utf-8"))
    assert manifest["release_version"] == __version__
