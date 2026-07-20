#!/usr/bin/env python3
"""Build a deterministic, version-stamped observatory release artifact and CycloneDX BOM."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import importlib
import io
import json
import shutil
import sys
import tarfile
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
if TYPE_CHECKING:
    from scripts import build_demo_contract, stamp_pages_version
else:
    sys.path.insert(0, str(ROOT))
    build_demo_contract = importlib.import_module("scripts.build_demo_contract")
    stamp_pages_version = importlib.import_module("scripts.stamp_pages_version")

CYCLONEDX_SCHEMA = "https://cyclonedx.org/schema/bom-1.7.schema.json"
EXCLUDED_PARTS = frozenset({"node_modules", "tests", "test-results", ".lighthouseci"})
EXCLUDED_NAMES = frozenset(
    {
        ".gitignore",
        ".nvmrc",
        ".pa11yci.cjs",
        "lighthouserc.cjs",
        "package-lock.json",
        "package.json",
        "playwright.config.cjs",
        "performance-baseline.json",
    }
)


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _runtime_files(web_dir: Path) -> list[Path]:
    files = []
    for path in web_dir.rglob("*"):
        relative = path.relative_to(web_dir)
        if not path.is_file() or any(part in EXCLUDED_PARTS for part in relative.parts):
            continue
        if path.name in EXCLUDED_NAMES:
            continue
        files.append(path)
    required = {
        "index.html",
        "app.js",
        "cooling-centers.geojson",
        "i18n-runtime.mjs",
        "sample-health.json",
        "sample-surface.json",
        "vendor/messageformat/index.js",
    }
    present = {path.relative_to(web_dir).as_posix() for path in files}
    missing = sorted(required - present)
    if missing:
        raise ValueError(f"frontend runtime is incomplete: {', '.join(missing)}")
    return sorted(files, key=lambda path: path.relative_to(web_dir).as_posix())


def _copy_runtime(web_dir: Path, stage: Path, project_root: Path) -> None:
    files = _runtime_files(web_dir)
    for source in files:
        relative = source.relative_to(web_dir)
        target = stage / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    for name in ("LICENSE", "NOTICE", "DATA-LICENSE"):
        source = project_root / name
        if not source.is_file():
            raise FileNotFoundError(source)
        shutil.copyfile(source, stage / name)

    sensors = stage / "sensors"
    for source in sorted(stage.rglob("*")):
        if not source.is_file() or sensors in source.parents:
            continue
        relative = source.relative_to(stage)
        target = sensors / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    for name in ("basemap.geojson", "cooling-centers.geojson"):
        (sensors / name).unlink(missing_ok=True)


def _prepare_static_route(route: Path, *, fallback_for: str | None = None) -> None:
    """Make a copied shell a complete, honest static reference route."""
    surface_path = route / "sample-surface.json"
    try:
        surface = json.loads(surface_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot build static route from {surface_path}: {exc}") from exc
    contract = build_demo_contract.build_contract("synthetic", surface, fallback_for=fallback_for)
    (route / "demo.json").write_text(
        json.dumps(contract, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    # The reference artifact has one committed week-sized surface. Publishing it under the full
    # history filename makes the static capability complete without inventing additional readings.
    shutil.copyfile(surface_path, route / "surface-7d.json")


def _artifact_manifest(stage: Path, *, version: str, commit: str) -> None:
    files = {
        path.relative_to(stage).as_posix(): sha256_path(path)
        for path in sorted(stage.rglob("*"))
        if path.is_file() and path.name != "artifact-manifest.json"
    }
    document = {
        "schema_version": 1,
        "name": "swelter-observatory",
        "version": version,
        "source_commit": commit,
        "files": files,
    }
    (stage / "artifact-manifest.json").write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _tar_info(name: str, *, epoch: int, directory: bool, size: int = 0) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name + ("/" if directory else ""))
    info.mtime = epoch
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    info.mode = 0o755 if directory else 0o644
    info.type = tarfile.DIRTYPE if directory else tarfile.REGTYPE
    info.size = size
    return info


def _write_archive(stage: Path, output: Path, *, prefix: str, epoch: int) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with (
        output.open("wb") as raw,
        gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=epoch) as compressed,
        tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as archive,
    ):
        archive.addfile(_tar_info(prefix, epoch=epoch, directory=True))
        for path in sorted(stage.rglob("*"), key=lambda item: item.relative_to(stage).as_posix()):
            relative = path.relative_to(stage).as_posix()
            name = f"{prefix}/{relative}"
            if path.is_dir():
                archive.addfile(_tar_info(name, epoch=epoch, directory=True))
            elif path.is_file():
                payload = path.read_bytes()
                archive.addfile(
                    _tar_info(name, epoch=epoch, directory=False, size=len(payload)),
                    io.BytesIO(payload),
                )


def _vendored_runtime_inventory(runtime_dir: Path) -> tuple[str, list[tuple[str, str]]]:
    """Return a deterministic tree digest and complete file inventory for a vendored runtime."""
    if not runtime_dir.is_dir():
        raise FileNotFoundError(runtime_dir)
    inventory = [
        (path.relative_to(runtime_dir).as_posix(), sha256_path(path))
        for path in sorted(runtime_dir.rglob("*"))
        if path.is_file()
    ]
    if not inventory:
        raise ValueError(f"vendored runtime has no files: {runtime_dir}")
    digest = hashlib.sha256()
    for relative, file_digest in inventory:
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_digest.encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest(), inventory


def _messageformat_component(web_dir: Path, runtime_dir: Path) -> dict[str, object]:
    lock = json.loads((web_dir / "package-lock.json").read_text(encoding="utf-8"))
    package = lock.get("packages", {}).get("node_modules/messageformat", {})
    version = package.get("version")
    if not isinstance(version, str) or not version:
        raise ValueError("package-lock has no messageformat version")
    license_id = package.get("license")
    if not isinstance(license_id, str) or not license_id:
        raise ValueError("package-lock has no messageformat license")
    tree_digest, inventory = _vendored_runtime_inventory(runtime_dir)
    purl = f"pkg:npm/messageformat@{quote(version, safe='.-_~')}"
    properties = [
        {
            "name": "swelter:vendored-runtime:tree-hash-format",
            "value": "sha256(sorted UTF-8 path + NUL + lowercase file SHA-256 + LF)",
        },
        {"name": "swelter:vendored-runtime:file-count", "value": str(len(inventory))},
        {
            "name": "swelter:vendored-runtime:archive-location",
            "value": "vendor/messageformat/",
        },
        {
            "name": "swelter:vendored-runtime:archive-location",
            "value": "sensors/vendor/messageformat/",
        },
    ]
    properties.extend(
        {
            "name": "swelter:vendored-runtime:file",
            "value": f"{file_digest}  {relative}",
        }
        for relative, file_digest in inventory
    )
    return {
        "type": "library",
        "bom-ref": purl,
        "name": "messageformat",
        "version": version,
        "purl": purl,
        "hashes": [{"alg": "SHA-256", "content": tree_digest}],
        "licenses": [{"license": {"id": license_id}}],
        "properties": properties,
    }


def frontend_sbom(
    artifact: Path,
    *,
    web_dir: Path,
    runtime_dir: Path,
    version: str,
    timestamp: str,
) -> dict[str, Any]:
    """Return a CycloneDX 1.7 BOM linked to the exact static artifact."""
    component = _messageformat_component(web_dir, runtime_dir)
    root_ref = f"pkg:generic/swelter-observatory@{quote(version, safe='.-_~')}"
    digest = sha256_path(artifact)
    serial = uuid.uuid5(uuid.NAMESPACE_URL, f"{root_ref}/{artifact.name}/{digest}")
    return {
        "$schema": CYCLONEDX_SCHEMA,
        "bomFormat": "CycloneDX",
        "specVersion": "1.7",
        "serialNumber": f"urn:uuid:{serial}",
        "version": 1,
        "metadata": {
            "timestamp": timestamp,
            "lifecycles": [{"phase": "post-build"}],
            "tools": {
                "components": [
                    {"type": "application", "name": "frontend-release", "version": "1.0.0"}
                ]
            },
            "authors": [{"name": "Chelsea Kelly-Reif"}],
            "component": {
                "type": "application",
                "bom-ref": root_ref,
                "name": "swelter-observatory",
                "version": version,
                "purl": root_ref,
                "hashes": [{"alg": "SHA-256", "content": digest}],
                "licenses": [{"license": {"id": "Apache-2.0"}}],
                "properties": [{"name": "swelter:release:artifact", "value": artifact.name}],
            },
        },
        "components": [component],
        "dependencies": [
            {"ref": root_ref, "dependsOn": [component["bom-ref"]]},
            {"ref": component["bom-ref"], "dependsOn": []},
        ],
    }


def build_frontend_release(
    *,
    web_dir: Path,
    output: Path,
    version: str,
    commit: str,
    repository: str,
    ref: str,
    source_epoch: int,
    project_root: Path = ROOT,
) -> Path:
    """Build and return the adjacent frontend BOM path."""
    timestamp = datetime.fromtimestamp(source_epoch, tz=UTC).isoformat(timespec="seconds")
    prefix = f"swelter-observatory-{version}"
    with tempfile.TemporaryDirectory(prefix="swelter-frontend-") as temporary:
        stage = Path(temporary) / prefix
        stage.mkdir()
        _copy_runtime(web_dir, stage, project_root)
        _prepare_static_route(stage)
        _prepare_static_route(stage / "sensors", fallback_for="sensor-community")
        expected_ref = f"refs/tags/v{version}"
        if ref != expected_ref:
            raise ValueError(f"release ref must be {expected_ref}, got {ref}")
        for route in (stage, stage / "sensors"):
            stamp_pages_version.stamp_route(
                route,
                commit=commit,
                ref=ref,
                repository=repository,
                # The Pages stamper also provides shared validation and HTML insertion. A tagged
                # artifact immediately replaces its deployment-run field with stable release
                # identity below, so no mutable workflow-run value enters the archive.
                run_id="1",
                source_timestamp=timestamp,
            )
            version_path = route / "version.json"
            document = json.loads(version_path.read_text(encoding="utf-8"))
            document.pop("workflow_run_id")
            document.update(
                {
                    "identity_kind": "signed-release",
                    "release_tag": ref.removeprefix("refs/tags/"),
                    "release_version": version,
                }
            )
            version_path.write_text(
                json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
        root_runtime = stage / "vendor" / "messageformat"
        sensor_runtime = stage / "sensors" / "vendor" / "messageformat"
        if _vendored_runtime_inventory(root_runtime) != _vendored_runtime_inventory(sensor_runtime):
            raise ValueError("root and sensors routes contain different MessageFormat runtimes")
        _artifact_manifest(stage, version=version, commit=commit)
        _write_archive(stage, output, prefix=prefix, epoch=source_epoch)
        bom = Path(f"{output}.cdx.json")
        bom.write_text(
            json.dumps(
                frontend_sbom(
                    output,
                    web_dir=web_dir,
                    runtime_dir=root_runtime,
                    version=version,
                    timestamp=timestamp,
                ),
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
    return bom


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--web-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--ref", required=True)
    parser.add_argument("--source-epoch", type=int, required=True)
    args = parser.parse_args()
    try:
        bom = build_frontend_release(
            web_dir=args.web_dir,
            output=args.output,
            version=args.version,
            commit=args.commit,
            repository=args.repository,
            ref=args.ref,
            source_epoch=args.source_epoch,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.exit(status=2, message=f"{parser.prog}: error: {exc}\n")
    print(f"frontend-release: wrote {args.output} and {bom}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
