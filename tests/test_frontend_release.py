"""The frontend release is deterministic, versioned, and artifact-bound."""

from __future__ import annotations

import importlib
import json
import sys
import tarfile
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest

ROOT = Path(__file__).resolve().parent.parent
if TYPE_CHECKING:
    from scripts import frontend_release, release_artifacts
else:
    sys.path.insert(0, str(ROOT))
    frontend_release = importlib.import_module("scripts.frontend_release")
    release_artifacts = importlib.import_module("scripts.release_artifacts")


def _fixture(root: Path) -> Path:
    web = root / "web"
    (web / "vendor/messageformat").mkdir(parents=True)
    (web / "i18n").mkdir()
    (web / "index.html").write_text("<html><head></head><body></body></html>\n", encoding="utf-8")
    (web / "app.js").write_text("export {};\n", encoding="utf-8")
    (web / "i18n-runtime.mjs").write_text("export {};\n", encoding="utf-8")
    (web / "vendor/messageformat/index.js").write_text("export {};\n", encoding="utf-8")
    (web / "vendor/messageformat/formatters").mkdir()
    (web / "vendor/messageformat/formatters/date.js").write_text(
        "export const date = {};\n", encoding="utf-8"
    )
    (web / "vendor/messageformat/asset-manifest.json").write_text(
        json.dumps(
            [
                "vendor/messageformat/formatters/date.js",
                "vendor/messageformat/index.js",
            ],
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (web / "i18n/en.json").write_text("{}\n", encoding="utf-8")
    (web / "cooling-centers.geojson").write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "metadata": {"source": "Illustrative synthetic demo fixture"},
                "features": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (web / "sample-health.json").write_text(
        json.dumps({"summary": {"total": 1, "ok": 1}}) + "\n", encoding="utf-8"
    )
    (web / "sample-surface.json").write_text(
        json.dumps(
            {
                "attribution": "Synthetic demonstration data — no real sensors",
                "buckets": ["2026-01-15T00:00:00Z"],
                "cells": [
                    {
                        "bucket": "2026-01-15T00:00:00Z",
                        "parameter": "pm25_ugm3",
                        "provisional": True,
                    },
                    {
                        "bucket": "2026-01-15T00:00:00Z",
                        "parameter": "temp_c",
                        "provisional": False,
                    },
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (web / "package-lock.json").write_text(
        json.dumps(
            {
                "packages": {
                    "node_modules/messageformat": {
                        "version": "4.0.0-11",
                        "license": "Apache-2.0",
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    for name in ("LICENSE", "NOTICE", "DATA-LICENSE"):
        (root / name).write_text(f"{name}\n", encoding="utf-8")
    return web


def _build(web: Path, output: Path, root: Path) -> dict[str, object]:
    bom = frontend_release.build_frontend_release(
        web_dir=web,
        output=output,
        version="0.1.0",
        commit="a" * 40,
        repository="ChelseaKR/swelter",
        ref="refs/tags/v0.1.0",
        source_epoch=1_768_521_600,
        project_root=root,
    )
    return cast(dict[str, object], json.loads(bom.read_text(encoding="utf-8")))


def _messageformat(document: dict[str, object]) -> dict[str, object]:
    components = document["components"]
    assert isinstance(components, list)
    component = next(
        candidate
        for candidate in components
        if isinstance(candidate, dict) and candidate.get("name") == "messageformat"
    )
    return cast(dict[str, object], component)


def _component_digest(component: dict[str, object]) -> str:
    hashes = component["hashes"]
    assert isinstance(hashes, list) and len(hashes) == 1
    entry = hashes[0]
    assert isinstance(entry, dict)
    content = entry.get("content")
    assert isinstance(content, str)
    return content


def test_frontend_release_is_reproducible_across_workflow_runs_and_has_two_stamped_routes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    web = _fixture(tmp_path)
    artifact_name = "swelter-observatory-0.1.0.tgz"
    outputs = [tmp_path / "run-42" / artifact_name, tmp_path / "run-9001" / artifact_name]
    for output, run_id in zip(outputs, ("42", "9001"), strict=True):
        monkeypatch.setenv("GITHUB_RUN_ID", run_id)
        _build(web, output, tmp_path)
    assert outputs[0].read_bytes() == outputs[1].read_bytes()
    assert (
        Path(f"{outputs[0]}.cdx.json").read_bytes() == Path(f"{outputs[1]}.cdx.json").read_bytes()
    )

    with tarfile.open(outputs[0], "r:gz") as archive:
        names = set(archive.getnames())
        prefix = "swelter-observatory-0.1.0"
        assert f"{prefix}/version.json" in names
        assert f"{prefix}/sensors/version.json" in names
        assert f"{prefix}/demo.json" in names
        assert f"{prefix}/sensors/demo.json" in names
        assert f"{prefix}/surface-7d.json" in names
        assert f"{prefix}/sensors/surface-7d.json" in names
        assert f"{prefix}/cooling-centers.geojson" in names
        assert f"{prefix}/sensors/cooling-centers.geojson" not in names
        assert f"{prefix}/artifact-manifest.json" in names
        assert not any("node_modules" in name or "/tests/" in name for name in names)
        root_demo_member = archive.extractfile(f"{prefix}/demo.json")
        sensor_demo_member = archive.extractfile(f"{prefix}/sensors/demo.json")
        history_member = archive.extractfile(f"{prefix}/surface-7d.json")
        sample_member = archive.extractfile(f"{prefix}/sample-surface.json")
        root_version_member = archive.extractfile(f"{prefix}/version.json")
        sensor_version_member = archive.extractfile(f"{prefix}/sensors/version.json")
        assert root_demo_member is not None
        assert sensor_demo_member is not None
        assert history_member is not None
        assert sample_member is not None
        assert root_version_member is not None
        assert sensor_version_member is not None
        root_demo = json.load(root_demo_member)
        sensor_demo = json.load(sensor_demo_member)
        root_version = json.load(root_version_member)
        sensor_version = json.load(sensor_version_member)
        assert root_demo["runtime"] == sensor_demo["runtime"] == "static"
        assert root_demo["source"]["id"] == sensor_demo["source"]["id"] == "synthetic"
        assert "fallback" not in root_demo
        assert sensor_demo["fallback"]["requested_source"] == "sensor-community"
        assert history_member.read() == sample_member.read()
        assert root_version == sensor_version
        assert root_version["identity_kind"] == "signed-release"
        assert root_version["release_tag"] == "v0.1.0"
        assert root_version["commit"] == "a" * 40
        assert "workflow_run_id" not in root_version

    bom = Path(f"{outputs[0]}.cdx.json")
    assert release_artifacts.validate_sbom(bom) == []
    document = json.loads(bom.read_text(encoding="utf-8"))
    assert document["metadata"]["component"]["hashes"][0][
        "content"
    ] == release_artifacts.sha256_path(outputs[0])
    messageformat = _messageformat(document)
    assert messageformat["licenses"] == [{"license": {"id": "Apache-2.0"}}]
    properties = messageformat["properties"]
    assert isinstance(properties, list)
    bound_files = {
        item["value"].split("  ", 1)[1]
        for item in properties
        if isinstance(item, dict) and item.get("name") == "swelter:vendored-runtime:file"
    }
    assert bound_files == {
        "asset-manifest.json",
        "formatters/date.js",
        "index.js",
    }


def test_frontend_sbom_tree_hash_detects_tampered_and_added_vendored_files(
    tmp_path: Path,
) -> None:
    web = _fixture(tmp_path)
    baseline = _messageformat(_build(web, tmp_path / "baseline.tgz", tmp_path))

    (web / "vendor/messageformat/index.js").write_text(
        "export const changed = true;\n", encoding="utf-8"
    )
    tampered = _messageformat(_build(web, tmp_path / "tampered.tgz", tmp_path))

    (web / "vendor/messageformat/extra.js").write_text("export {};\n", encoding="utf-8")
    added = _messageformat(_build(web, tmp_path / "added.tgz", tmp_path))

    digests = {_component_digest(component) for component in (baseline, tampered, added)}
    assert len(digests) == 3
    added_properties = added["properties"]
    assert isinstance(added_properties, list)
    bound_files = {
        item["value"].split("  ", 1)[1]
        for item in added_properties
        if isinstance(item, dict) and item.get("name") == "swelter:vendored-runtime:file"
    }
    assert "extra.js" in bound_files
