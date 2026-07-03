"""``swelter publish``: the pages.yml bash choreography promoted into a tested CLI command that
bakes a complete static site (sample surface, health, alerts, per-window surface slices, the CSV
export, license files, and an auditable manifest) from an existing store — no assumption about
which pipeline command (``fetch`` or ``demo``) populated it.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from swelter import aggregate, export
from swelter.cli import main
from swelter.config import load_config
from swelter.store import open_store

from .conftest import DEMO, ROOT

NETWORK = str(ROOT / "network.yaml")
COOLING = str(ROOT / "data" / "cooling_centers.geojson")


@pytest.fixture(scope="module")
def demo_store(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A populated store (raw + calibrated + registry), built once and shared read-only by the
    publish tests below — publish itself never mutates the store, only the web dir."""
    base = tmp_path_factory.mktemp("publish-demo")
    rc = main(
        [
            "demo",
            "--data",
            str(DEMO),
            "--store",
            str(base / "store"),
            "--config",
            NETWORK,
            "--web",
            str(base / "web"),
            "--cooling-centers",
            COOLING,
        ]
    )
    assert rc == 0
    return base / "store"


def _publish(store: Path, web: Path, **extra: str) -> int:
    args = [
        "publish",
        "--store",
        str(store),
        "--web",
        str(web),
        "--config",
        NETWORK,
        "--cooling-centers",
        COOLING,
    ]
    for key, value in extra.items():
        args += [f"--{key.replace('_', '-')}", value]
    return main(args)


EXPECTED_FILES = (
    "sample-surface.json",
    "sample-health.json",
    "alerts.json",
    "alerts.xml",
    "surface-24h.json",
    "surface-7d.json",
    "export.csv",
    "DATA-LICENSE",
    "publish-manifest.json",
)


def test_publish_writes_expected_files(demo_store: Path, tmp_path: Path) -> None:
    web = tmp_path / "web"
    rc = _publish(demo_store, web)
    assert rc == 0
    for name in EXPECTED_FILES:
        assert (web / name).is_file(), f"publish did not write {name}"


def test_publish_surface_slices_are_windowed_subsets(demo_store: Path, tmp_path: Path) -> None:
    web = tmp_path / "web"
    rc = _publish(demo_store, web)
    assert rc == 0

    store = open_store(demo_store)
    try:
        surface = aggregate.aggregate(store.all(), load_config(NETWORK))
    finally:
        store.close()
    all_buckets = sorted({c.bucket for c in surface.cells})
    assert len(all_buckets) > 7 * 24, "demo data should span more than a week of hourly buckets"

    slice_24h = json.loads((web / "surface-24h.json").read_text(encoding="utf-8"))
    slice_7d = json.loads((web / "surface-7d.json").read_text(encoding="utf-8"))

    # Window semantics match server.py's /api/surface.json?hours=N: the newest N hourly buckets.
    assert slice_24h["buckets"] == all_buckets[-24:]
    assert slice_7d["buckets"] == all_buckets[-(24 * 7) :]

    buckets_24h = set(slice_24h["buckets"])
    buckets_7d = set(slice_7d["buckets"])
    assert buckets_24h <= buckets_7d <= set(all_buckets)

    cells_24h = {(c["cell_id"], c["bucket"], c["parameter"]) for c in slice_24h["cells"]}
    cells_7d = {(c["cell_id"], c["bucket"], c["parameter"]) for c in slice_7d["cells"]}
    assert cells_24h <= cells_7d


def test_publish_export_matches_export_to_csv(demo_store: Path, tmp_path: Path) -> None:
    web = tmp_path / "web"
    rc = _publish(demo_store, web)
    assert rc == 0

    store = open_store(demo_store)
    try:
        all_obs = list(store.all())
    finally:
        store.close()

    # Read raw bytes, not read_text(): the CSV module's "\r\n" line terminator survives
    # byte-for-byte only if nothing does universal-newline translation on the way back in.
    baked = (web / "export.csv").read_bytes().decode("utf-8")
    assert baked == export.to_csv(all_obs)


def test_publish_manifest_enumerates_files_with_hashes(demo_store: Path, tmp_path: Path) -> None:
    web = tmp_path / "web"
    rc = _publish(demo_store, web)
    assert rc == 0

    manifest = json.loads((web / "publish-manifest.json").read_text(encoding="utf-8"))
    assert "interval_s" in manifest and "data_hour" in manifest
    assert manifest["data_hour"], "demo data should produce a non-empty latest bucket"

    listed = {entry["path"]: entry for entry in manifest["files"]}
    # publish-manifest.json never lists itself (no chicken-and-egg self-hash).
    assert "publish-manifest.json" not in listed
    for name in EXPECTED_FILES:
        if name == "publish-manifest.json":
            continue
        assert name in listed, f"manifest omits emitted file {name}"
        data = (web / name).read_bytes()
        assert listed[name]["bytes"] == len(data)
        assert listed[name]["sha256"] == hashlib.sha256(data).hexdigest()


def test_publish_manifest_is_deterministic(demo_store: Path, tmp_path: Path) -> None:
    """Re-running publish against an unchanged store reproduces the manifest byte for byte —
    the same determinism guarantee ``_write_web_alerts`` documents for alerts.json/alerts.xml."""
    web_a = tmp_path / "a"
    web_b = tmp_path / "b"
    assert _publish(demo_store, web_a) == 0
    assert _publish(demo_store, web_b) == 0

    manifest_a = (web_a / "publish-manifest.json").read_bytes()
    manifest_b = (web_b / "publish-manifest.json").read_bytes()
    assert manifest_a == manifest_b


def test_publish_skips_cooling_centers_when_dataset_absent(
    demo_store: Path, tmp_path: Path
) -> None:
    web = tmp_path / "web"
    rc = _publish(demo_store, web, cooling_centers=str(tmp_path / "no-such-file.geojson"))
    assert rc == 0
    assert not (web / "cooling-centers.geojson").exists()
    manifest = json.loads((web / "publish-manifest.json").read_text(encoding="utf-8"))
    listed = {entry["path"] for entry in manifest["files"]}
    assert "cooling-centers.geojson" not in listed


def test_publish_bakes_cooling_centers_when_dataset_present(
    demo_store: Path, tmp_path: Path
) -> None:
    web = tmp_path / "web"
    rc = _publish(demo_store, web)
    assert rc == 0
    assert (web / "cooling-centers.geojson").is_file()
    manifest = json.loads((web / "publish-manifest.json").read_text(encoding="utf-8"))
    listed = {entry["path"] for entry in manifest["files"]}
    assert "cooling-centers.geojson" in listed


def test_publish_creates_web_dir_if_missing(demo_store: Path, tmp_path: Path) -> None:
    web = tmp_path / "does" / "not" / "exist"
    assert not web.exists()
    rc = _publish(demo_store, web)
    assert rc == 0
    assert (web / "sample-surface.json").is_file()


def test_publish_data_license_content_matches_repo(demo_store: Path, tmp_path: Path) -> None:
    web = tmp_path / "web"
    rc = _publish(demo_store, web)
    assert rc == 0
    baked = (web / "DATA-LICENSE").read_bytes()
    source = (ROOT / "DATA-LICENSE").read_bytes()
    assert baked == source
