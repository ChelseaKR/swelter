"""``swelter publish``: the pages.yml bash choreography promoted into a tested CLI command that
bakes a complete static site (sample surface, health, alerts, per-window surface slices, the CSV
export, license files, and an auditable manifest) from an existing store — no assumption about
which pipeline command (``fetch`` or ``demo``) populated it.
"""

from __future__ import annotations

import csv
import hashlib
import json
import shutil
from collections.abc import Iterable
from pathlib import Path

import pytest

from swelter import aggregate, export, snapshot
from swelter.cli import main
from swelter.config import load_config
from swelter.models import Observation
from swelter.sources import openaq, sensor_community
from swelter.sources._california_places import CALIFORNIA
from swelter.store import SqliteStore, open_store
from swelter.web_preview import WEB_PREVIEW_NETWORK_NAME, WEB_PREVIEW_REFERENCE_LABEL

from .conftest import DEMO, ROOT, make_obs

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
    "alerts.es.xml",
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


def test_publish_uses_one_statewide_mapping_across_location_artifacts_and_manifest(
    demo_store: Path, tmp_path: Path
) -> None:
    web = tmp_path / "web"
    assert _publish(demo_store, web) == 0

    def locations(filename: str) -> dict[str, tuple[str, str, float, float]]:
        payload = json.loads((web / filename).read_text(encoding="utf-8"))
        by_node: dict[str, tuple[str, str, float, float]] = {}
        for cell in payload["cells"]:
            assert len(cell["nodes"]) == 1
            node_id = str(cell["nodes"][0])
            location = (
                str(cell["cell_id"]),
                str(cell["label"]),
                float(cell["lat"]),
                float(cell["lon"]),
            )
            assert by_node.setdefault(node_id, location) == location
        return by_node

    sample = locations("sample-surface.json")
    assert sample == locations("surface-24h.json") == locations("surface-7d.json")
    assert len(sample) == 150
    validated = set(CALIFORNIA)
    assert {(label, lat, lon) for _cell_id, label, lat, lon in sample.values()} <= validated
    sample_payload = json.loads((web / "sample-surface.json").read_text(encoding="utf-8"))
    references = {str(cell["reference"]) for cell in sample_payload["cells"] if "reference" in cell}
    assert references == {WEB_PREVIEW_REFERENCE_LABEL}

    health = json.loads((web / "sample-health.json").read_text(encoding="utf-8"))
    expected_coverage = {(cell_id, label) for cell_id, label, _lat, _lon in sample.values()}
    actual_coverage = {
        (str(cell["cell_id"]), str(cell["label"])) for cell in health["coverage_equity"]["cells"]
    }
    assert actual_coverage == expected_coverage

    alerts = json.loads((web / "alerts.json").read_text(encoding="utf-8"))
    assert alerts["network"] == WEB_PREVIEW_NETWORK_NAME
    for name in (
        "sample-surface.json",
        "sample-health.json",
        "alerts.json",
        "alerts.xml",
        "alerts.es.xml",
    ):
        assert "downtown" not in (web / name).read_text(encoding="utf-8").casefold()

    manifest = json.loads((web / "publish-manifest.json").read_text(encoding="utf-8"))
    listed = {entry["path"]: entry for entry in manifest["files"]}
    for name in (
        "sample-surface.json",
        "surface-24h.json",
        "surface-7d.json",
        "sample-health.json",
        "alerts.json",
        "alerts.xml",
        "alerts.es.xml",
    ):
        data = (web / name).read_bytes()
        assert listed[name]["bytes"] == len(data)
        assert listed[name]["sha256"] == hashlib.sha256(data).hexdigest()


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
    assert baked == export.to_csv(all_obs, license=export.DEFAULT_LICENSE)


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


def test_publish_manifest_includes_a_prebuilt_demo_contract(
    demo_store: Path, tmp_path: Path
) -> None:
    web = tmp_path / "web"
    web.mkdir()
    contract = b'{"schema_version": 1}\n'
    (web / "demo.json").write_bytes(contract)

    assert _publish(demo_store, web) == 0

    manifest = json.loads((web / "publish-manifest.json").read_text(encoding="utf-8"))
    listed = {entry["path"]: entry for entry in manifest["files"]}
    assert listed["demo.json"] == {
        "path": "demo.json",
        "bytes": len(contract),
        "sha256": hashlib.sha256(contract).hexdigest(),
    }


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


def test_pages_omits_illustrative_centers_before_writing_the_manifest() -> None:
    workflow = (ROOT / ".github" / "workflows" / "pages.yml").read_text(encoding="utf-8")
    primary_publish = (
        'uv run swelter publish --store "$SOURCE1_STORE" --web web --config "$SOURCE1_CONFIG" '
        "\\\n            --cooling-centers /dev/null/none"
    )
    assert primary_publish in workflow
    assert "Illustrative cooling-center data must not be published" in workflow


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


def test_publish_license_overrides_travel_into_the_artifact(
    demo_store: Path, tmp_path: Path
) -> None:
    """--license/--attribution replace the CC0 default everywhere provenance shows: the baked
    DATA-LICENSE names the real terms (never the repo's CC0 file) and export.csv carries the same
    license/attribution columns — a fetched third-party store must not publish as CC0 (FIX-05)."""
    web = tmp_path / "web"
    rc = _publish(
        demo_store,
        web,
        license="ODC-DbCL-1.0",
        attribution="Real readings from a third-party network — uncalibrated.",
    )
    assert rc == 0
    baked = (web / "DATA-LICENSE").read_text(encoding="utf-8")
    assert "ODC-DbCL-1.0" in baked
    assert "Real readings from a third-party network" in baked
    assert baked != (ROOT / "DATA-LICENSE").read_text(encoding="utf-8")
    csv_text = (web / "export.csv").read_text(encoding="utf-8")
    assert "ODC-DbCL-1.0" in csv_text
    # the sample surface carries the attribution the dashboard shows
    sample = json.loads((web / "sample-surface.json").read_text(encoding="utf-8"))
    assert sample["attribution"].startswith("Real readings from a third-party network")


def test_publish_automatically_uses_fetched_store_terms(demo_store: Path, tmp_path: Path) -> None:
    store = tmp_path / "store"
    shutil.copytree(demo_store, store)
    snapshot.write_source_metadata(
        store,
        source="Sensor.Community",
        license=sensor_community.LICENSE,
        attribution=sensor_community.ATTRIBUTION,
        license_url=sensor_community.LICENSE_URL,
        recorded_at="2026-07-16T12:00:00Z",
    )

    web = tmp_path / "web"
    assert _publish(store, web) == 0
    assert "ODC-DbCL-1.0" in (web / "DATA-LICENSE").read_text(encoding="utf-8")
    assert (web / snapshot.SOURCE_METADATA_FILENAME).is_file()
    manifest = json.loads((web / "publish-manifest.json").read_text(encoding="utf-8"))
    assert snapshot.SOURCE_METADATA_FILENAME in {entry["path"] for entry in manifest["files"]}


def test_publish_copies_the_exact_source_metadata_bytes_it_validated(
    demo_store: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = tmp_path / "store"
    shutil.copytree(demo_store, store)
    metadata_path = snapshot.write_source_metadata(
        store,
        source="Sensor.Community",
        license=sensor_community.LICENSE,
        attribution=sensor_community.ATTRIBUTION,
        license_url=sensor_community.LICENSE_URL,
        recorded_at="2026-07-16T12:00:00Z",
    )
    validated_bytes = metadata_path.read_bytes()
    original_loader = snapshot.load_data_terms

    def load_then_replace_source(
        store_path: Path,
        *,
        license_override: str | None = None,
        attribution_override: str | None = None,
        observations: Iterable[Observation] = (),
    ) -> snapshot.DataTerms:
        terms = original_loader(
            store_path,
            license_override=license_override,
            attribution_override=attribution_override,
            observations=observations,
        )
        metadata_path.write_bytes(b'{"tampered":true}\n')
        return terms

    monkeypatch.setattr(snapshot, "load_data_terms", load_then_replace_source)
    web = tmp_path / "web"

    assert _publish(store, web) == 0
    assert (web / snapshot.SOURCE_METADATA_FILENAME).read_bytes() == validated_bytes


def test_publish_refuses_openaq_without_per_location_license_ledger(
    demo_store: Path, tmp_path: Path
) -> None:
    store = tmp_path / "store"
    shutil.copytree(demo_store, store)
    web = tmp_path / "web"
    assert (
        _publish(
            store,
            web,
            license=openaq.LICENSE,
            attribution=openaq.ATTRIBUTION,
        )
        == 1
    )
    assert not (web / "publish-manifest.json").exists()


def test_publish_copies_and_hashes_openaq_license_ledger(tmp_path: Path) -> None:
    store = tmp_path / "store"
    with SqliteStore(store / "observations.db") as db:
        db.write([make_obs(node_id="oaq-1")])
    snapshot.write_source_metadata(
        store,
        source="OpenAQ",
        license=openaq.LICENSE,
        attribution=openaq.ATTRIBUTION,
        license_url=openaq.LICENSE_URL,
        recorded_at="2026-07-16T00:00:00Z",
    )
    ledger = {
        "schema_version": 1,
        "source": "OpenAQ v3",
        "generated_at": "2026-07-16T00:00:00Z",
        "entries": [
            {
                "location_id": 1,
                "license_id": 1,
                "location_name": "Site 1",
                "provider": "Provider",
                "license_name": "CC BY 4.0",
                "license_url": "https://creativecommons.org/licenses/by/4.0/",
                "attribution": "Provider",
                "attribution_url": "",
                "valid_from": None,
                "valid_to": None,
                "upstream_url": f"{openaq.API}/locations/1",
                "fetched_at": "2026-07-16T00:00:00Z",
                "unavailable_fields": [],
            }
        ],
        "excluded_locations": [],
    }
    source = store / openaq.LICENSE_LEDGER_FILENAME
    source.write_text(json.dumps(ledger, indent=2), encoding="utf-8")
    web = tmp_path / "web"
    assert _publish(store, web) == 0
    target = web / openaq.LICENSE_LEDGER_FILENAME
    assert json.loads(target.read_text(encoding="utf-8")) == ledger
    manifest = json.loads((web / "publish-manifest.json").read_text(encoding="utf-8"))
    listed = {entry["path"]: entry for entry in manifest["files"]}
    assert (
        listed[openaq.LICENSE_LEDGER_FILENAME]["sha256"]
        == hashlib.sha256(target.read_bytes()).hexdigest()
    )
    assert "source-license-ledger.json" in (web / "DATA-LICENSE").read_text(encoding="utf-8")
    sample = json.loads((web / "sample-surface.json").read_text(encoding="utf-8"))
    assert {link["rel"] for link in sample["rights"]["links"]} == {
        "license",
        "describedby",
    }
    atom = (web / "alerts.xml").read_text(encoding="utf-8")
    assert '<link rel="license" href="DATA-LICENSE"/>' in atom
    assert '<link rel="describedby" href="source-license-ledger.json"/>' in atom
    rows = list(csv.DictReader((web / "export.csv").read_text(encoding="utf-8").splitlines()))
    assert rows[0]["data_license"].startswith("CC BY 4.0")
    assert rows[0]["data_attribution"] == "Provider"
