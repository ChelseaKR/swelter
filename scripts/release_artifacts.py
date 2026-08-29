#!/usr/bin/env python3
"""Build and verify the cryptographic release evidence consumed by downstream users."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
import re
import tarfile
import tomllib
import uuid
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
PROJECT_FILE = ROOT / "pyproject.toml"
LOCK_FILE = ROOT / "uv.lock"
CHANGELOG = ROOT / "CHANGELOG.md"
CYCLONEDX_SCHEMA = "https://cyclonedx.org/schema/bom-1.7.schema.json"
GENERATOR_VERSION = "1.0.0"
PROVENANCE_BUNDLE = "SUPPLY_CHAIN_PROVENANCE.tgz"
PROVENANCE_MANIFEST = "MANIFEST.json"
SIGSTORE_BUNDLE_MEDIA_TYPE = "application/vnd.dev.sigstore.bundle.v0.3+json"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_CHECKSUM_LINE = re.compile(r"^([0-9a-f]{64}) [ *](\S+)$")


def sha256_path(path: Path) -> str:
    """Return a streaming SHA-256 digest for *path*."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_toml(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def _pypi_purl(name: str, version: str) -> str:
    normalized = name.lower().replace("_", "-")
    return f"pkg:pypi/{quote(normalized, safe='.-_~')}@{quote(version, safe='.-_~')}"


def _locked_packages() -> dict[str, dict[str, Any]]:
    packages = _load_toml(LOCK_FILE).get("package", [])
    if not isinstance(packages, list):
        raise ValueError("uv.lock has no package array")
    result: dict[str, dict[str, Any]] = {}
    for package in packages:
        if isinstance(package, dict) and isinstance(package.get("name"), str):
            result[package["name"]] = package
    return result


def _locked_sha256(package: dict[str, Any]) -> str:
    candidates = [package.get("sdist")]
    wheels = package.get("wheels", [])
    if isinstance(wheels, list):
        candidates.extend(wheels)
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        value = candidate.get("hash")
        if isinstance(value, str) and value.startswith("sha256:"):
            digest = value.removeprefix("sha256:")
            if _SHA256.fullmatch(digest):
                return digest
    raise ValueError(f"locked package {package.get('name')!r} has no SHA-256 artifact hash")


def _runtime_components() -> tuple[list[dict[str, Any]], list[str]]:
    packages = _locked_packages()
    project = packages.get("swelter")
    if project is None:
        raise ValueError("uv.lock has no swelter project package")
    queue = [
        dependency["name"]
        for dependency in project.get("dependencies", [])
        if isinstance(dependency, dict) and isinstance(dependency.get("name"), str)
    ]
    seen: set[str] = set()
    components: list[dict[str, Any]] = []
    while queue:
        name = queue.pop(0)
        if name in seen:
            continue
        seen.add(name)
        package = packages.get(name)
        if package is None:
            raise ValueError(f"runtime dependency {name!r} is absent from uv.lock")
        version = package.get("version")
        if not isinstance(version, str) or not version:
            raise ValueError(f"runtime dependency {name!r} has no locked version")
        purl = _pypi_purl(name, version)
        components.append(
            {
                "type": "library",
                "bom-ref": purl,
                "name": name,
                "version": version,
                "purl": purl,
                "hashes": [{"alg": "SHA-256", "content": _locked_sha256(package)}],
            }
        )
        queue.extend(
            dependency["name"]
            for dependency in package.get("dependencies", [])
            if isinstance(dependency, dict)
            and isinstance(dependency.get("name"), str)
            and dependency["name"] not in seen
        )
    components.sort(key=lambda component: (component["name"], component["version"]))
    return components, [component["bom-ref"] for component in components]


def _timestamp() -> str:
    epoch = os.environ.get("SOURCE_DATE_EPOCH")
    instant = datetime.fromtimestamp(int(epoch), tz=UTC) if epoch else datetime.now(tz=UTC)
    return instant.isoformat(timespec="seconds").replace("+00:00", "Z")


def _source_epoch() -> int:
    value = os.environ.get("SOURCE_DATE_EPOCH", "0")
    try:
        epoch = int(value)
    except ValueError as exc:
        raise ValueError("SOURCE_DATE_EPOCH must be an integer") from exc
    if epoch < 0:
        raise ValueError("SOURCE_DATE_EPOCH cannot be negative")
    return epoch


def build_sbom(artifact: Path) -> dict[str, Any]:
    """Return a CycloneDX 1.7 release BOM bound to one built artifact."""
    if not artifact.is_file():
        raise FileNotFoundError(artifact)
    project = _load_toml(PROJECT_FILE).get("project", {})
    version = project.get("version") if isinstance(project, dict) else None
    if not isinstance(version, str) or not version:
        raise ValueError("pyproject.toml has no project.version")
    artifact_digest = sha256_path(artifact)
    root_ref = _pypi_purl("swelter", version)
    components, runtime_refs = _runtime_components()
    serial = uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"https://github.com/ChelseaKR/swelter/releases/{version}/{artifact.name}/{artifact_digest}",
    )
    dependencies = [{"ref": root_ref, "dependsOn": runtime_refs}]
    dependencies.extend({"ref": component["bom-ref"], "dependsOn": []} for component in components)
    return {
        "$schema": CYCLONEDX_SCHEMA,
        "bomFormat": "CycloneDX",
        "specVersion": "1.7",
        "serialNumber": f"urn:uuid:{serial}",
        "version": 1,
        "metadata": {
            "timestamp": _timestamp(),
            "lifecycles": [{"phase": "post-build"}],
            "tools": {
                "components": [
                    {
                        "type": "application",
                        "name": "swelter-release-artifacts",
                        "version": GENERATOR_VERSION,
                    }
                ]
            },
            "authors": [{"name": "Chelsea Kelly-Reif"}],
            "component": {
                "type": "application",
                "bom-ref": root_ref,
                "name": "swelter",
                "version": version,
                "purl": root_ref,
                "hashes": [{"alg": "SHA-256", "content": artifact_digest}],
                "licenses": [{"license": {"id": "Apache-2.0"}}],
                "properties": [
                    {"name": "swelter:release:artifact", "value": artifact.name},
                ],
            },
        },
        "components": components,
        "dependencies": dependencies,
    }


def _component_problems(component: object, label: str) -> list[str]:
    if not isinstance(component, dict):
        return [f"{label} is not an object"]
    problems: list[str] = []
    for field in ("type", "name", "version", "purl", "bom-ref"):
        if not isinstance(component.get(field), str) or not component[field]:
            problems.append(f"{label} has no {field}")
    hashes = component.get("hashes")
    if not isinstance(hashes, list) or not any(
        isinstance(item, dict)
        and item.get("alg") == "SHA-256"
        and isinstance(item.get("content"), str)
        and bool(_SHA256.fullmatch(item["content"]))
        for item in hashes
    ):
        problems.append(f"{label} has no valid SHA-256 hash")
    return problems


def _dependency_problems(dependencies: object, valid_references: set[str]) -> list[str]:
    if not isinstance(dependencies, list):
        return ["dependencies is not an array"]
    problems: list[str] = []
    dependency_refs: set[str] = set()
    for index, dependency in enumerate(dependencies):
        if not isinstance(dependency, dict) or not isinstance(dependency.get("ref"), str):
            problems.append(f"dependencies[{index}] has no ref")
            continue
        dependency_refs.add(dependency["ref"])
        targets = dependency.get("dependsOn", [])
        if not isinstance(targets, list) or any(
            target not in valid_references for target in targets
        ):
            problems.append(f"dependencies[{index}] references an unknown component")
    if dependency_refs != valid_references:
        problems.append("dependency graph does not enumerate every component")
    return problems


def validate_sbom_document(document: object) -> list[str]:
    """Return strict portfolio-policy findings for a CycloneDX document."""
    if not isinstance(document, dict):
        return ["BOM root is not an object"]
    problems: list[str] = []
    if document.get("$schema") != CYCLONEDX_SCHEMA:
        problems.append("$schema is not the CycloneDX 1.7 schema")
    if document.get("bomFormat") != "CycloneDX" or document.get("specVersion") != "1.7":
        problems.append("BOM must declare CycloneDX specVersion 1.7")
    try:
        serial = document.get("serialNumber", "").removeprefix("urn:uuid:")
        uuid.UUID(serial)
    except (AttributeError, ValueError):
        problems.append("serialNumber is not an RFC 4122 urn:uuid")
    metadata = document.get("metadata")
    root_component = metadata.get("component") if isinstance(metadata, dict) else None
    problems.extend(_component_problems(root_component, "metadata.component"))
    components = document.get("components")
    if not isinstance(components, list):
        problems.append("components is not an array")
        components = []
    for index, component in enumerate(components):
        problems.extend(_component_problems(component, f"components[{index}]"))
    all_components = [root_component, *components]
    references = [
        component.get("bom-ref") for component in all_components if isinstance(component, dict)
    ]
    valid_references = {reference for reference in references if isinstance(reference, str)}
    if len(valid_references) != len(references):
        problems.append("component bom-ref values are absent or duplicated")
    problems.extend(_dependency_problems(document.get("dependencies"), valid_references))
    return problems


def validate_sbom(path: Path) -> list[str]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"cannot read JSON: {exc}"]
    return validate_sbom_document(document)


def write_sbom(artifact: Path, output: Path) -> None:
    document = build_sbom(artifact)
    problems = validate_sbom_document(document)
    if problems:
        raise ValueError("generated invalid BOM: " + "; ".join(problems))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def changelog_section(version: str) -> str:
    """Extract one dated version section as human-readable release notes."""
    lines = CHANGELOG.read_text(encoding="utf-8").splitlines()
    heading = re.compile(rf"^## \[{re.escape(version)}\] - \d{{4}}-\d{{2}}-\d{{2}}$")
    start = next((index for index, line in enumerate(lines) if heading.fullmatch(line)), None)
    if start is None:
        raise ValueError(f"CHANGELOG.md has no dated section for {version}")
    end = next(
        (index for index in range(start + 1, len(lines)) if lines[index].startswith("## [")),
        len(lines),
    )
    section = "\n".join(lines[start:end]).strip()
    return f"# swelter {version}\n\n{section}\n"


def _json_lines_problems(path: Path) -> list[str]:
    problems: list[str] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        return [f"cannot read {path.name}: {exc}"]
    if not lines:
        return [f"{path.name} is empty"]
    for line_number, line in enumerate(lines, start=1):
        try:
            document = json.loads(line)
        except json.JSONDecodeError as exc:
            problems.append(f"{path.name}:{line_number} is not JSON: {exc.msg}")
            continue
        if not isinstance(document, dict):
            problems.append(f"{path.name}:{line_number} is not a JSON object")
    return problems


def _tar_info(name: str, size: int, epoch: int) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name=name)
    info.size = size
    info.mode = 0o644
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    info.mtime = epoch
    return info


def build_provenance_bundle(
    *,
    assets: list[Path],
    attestations_directory: Path,
    output: Path,
    version: str,
    commit: str,
    repository: str,
) -> None:
    """Create a deterministic, downloadable bundle of GitHub provenance attestations."""
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("release commit must be a full lowercase Git SHA")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("repository must use owner/name form")
    if not assets or len({asset.name for asset in assets}) != len(assets):
        raise ValueError("provenance subjects must be non-empty with unique filenames")
    trusted_root = attestations_directory / "trusted_root.jsonl"
    inputs: dict[str, Path] = {"trusted_root.jsonl": trusted_root}
    subjects: list[dict[str, str]] = []
    for asset in sorted(assets, key=lambda item: item.name):
        if not asset.is_file():
            raise FileNotFoundError(asset)
        bundle = attestations_directory / f"{asset.name}.intoto.jsonl"
        inputs[f"attestations/{bundle.name}"] = bundle
        subjects.append(
            {
                "name": asset.name,
                "sha256": sha256_path(asset),
                "attestation": f"attestations/{bundle.name}",
            }
        )
    for path in inputs.values():
        problems = _json_lines_problems(path)
        if problems:
            raise ValueError("; ".join(problems))
    payloads = {name: path.read_bytes() for name, path in inputs.items()}
    manifest = {
        "schema_version": 1,
        "release": {
            "version": version,
            "tag": f"v{version}",
            "commit": commit,
            "repository": repository,
        },
        "subjects": subjects,
        "files_sha256": {
            name: hashlib.sha256(payload).hexdigest() for name, payload in sorted(payloads.items())
        },
    }
    payloads[PROVENANCE_MANIFEST] = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    epoch = _source_epoch()
    output.parent.mkdir(parents=True, exist_ok=True)
    with (
        output.open("wb") as raw,
        gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=epoch) as compressed,
        tarfile.open(fileobj=compressed, mode="w") as archive,
    ):
        for name, payload in sorted(payloads.items()):
            archive.addfile(_tar_info(name, len(payload), epoch), io.BytesIO(payload))


def _read_provenance_bundle(path: Path) -> tuple[dict[str, bytes], list[str]]:
    members: dict[str, bytes] = {}
    problems: list[str] = []
    try:
        with tarfile.open(path, mode="r:gz") as archive:
            for member in archive.getmembers():
                candidate = Path(member.name)
                if (
                    not member.isfile()
                    or candidate.is_absolute()
                    or ".." in candidate.parts
                    or candidate.as_posix() != member.name
                    or member.name in members
                ):
                    problems.append(f"unsafe or duplicate provenance member: {member.name!r}")
                    continue
                handle = archive.extractfile(member)
                if handle is None:
                    problems.append(f"cannot read provenance member: {member.name}")
                    continue
                members[member.name] = handle.read()
    except (OSError, tarfile.TarError) as exc:
        return {}, [f"cannot read provenance bundle: {exc}"]
    return members, problems


def _provenance_release_findings(manifest: dict[str, Any], version: str) -> list[str]:
    findings: list[str] = []
    release = manifest.get("release")
    if not isinstance(release, dict) or release.get("version") != version:
        findings.append("provenance manifest release version does not match")
    elif release.get("tag") != f"v{version}":
        findings.append("provenance manifest tag does not match")
    elif not re.fullmatch(r"[0-9a-f]{40}", str(release.get("commit", ""))):
        findings.append("provenance manifest has no full release commit")
    return findings


def _provenance_subjects(
    manifest: dict[str, Any], members: dict[str, bytes]
) -> tuple[dict[str, str], set[str], list[str]]:
    problems: list[str] = []
    subjects = manifest.get("subjects")
    actual_subjects: dict[str, str] = {}
    attestation_names: set[str] = set()
    if not isinstance(subjects, list):
        return {}, set(), ["provenance subjects is not an array"]
    for subject in subjects:
        if not isinstance(subject, dict):
            problems.append("provenance subject is not an object")
            continue
        name = subject.get("name")
        digest = subject.get("sha256")
        attestation = subject.get("attestation")
        if not isinstance(name, str) or not isinstance(digest, str):
            problems.append("provenance subject has no name or SHA-256")
            continue
        if not isinstance(attestation, str) or attestation not in members:
            problems.append(f"provenance attestation is missing for {name}")
            continue
        actual_subjects[name] = digest
        attestation_names.add(attestation)
        try:
            text = members[attestation].decode()
            if not text.splitlines() or any(
                not isinstance(json.loads(line), dict) for line in text.splitlines()
            ):
                problems.append(f"provenance attestation is invalid for {name}")
        except (UnicodeError, json.JSONDecodeError):
            problems.append(f"provenance attestation is invalid for {name}")
    return actual_subjects, attestation_names, problems


def _provenance_file_findings(
    manifest: dict[str, Any], members: dict[str, bytes], attestation_names: set[str]
) -> list[str]:
    problems: list[str] = []
    hashes = manifest.get("files_sha256")
    expected_members = {PROVENANCE_MANIFEST, "trusted_root.jsonl", *attestation_names}
    if set(members) != expected_members:
        problems.append("provenance archive contains missing or unexpected members")
    if not isinstance(hashes, dict) or set(hashes) != expected_members - {PROVENANCE_MANIFEST}:
        problems.append("provenance file hash inventory is incomplete")
    else:
        for name, expected in hashes.items():
            if (
                not isinstance(expected, str)
                or hashlib.sha256(members[name]).hexdigest() != expected
            ):
                problems.append(f"provenance member hash mismatch: {name}")
    return problems


def verify_provenance_bundle(
    path: Path, *, version: str, expected_artifacts: dict[str, str]
) -> list[str]:
    """Validate provenance inventory and subject linkage without trusting archive paths."""
    members, problems = _read_provenance_bundle(path)
    manifest_bytes = members.get(PROVENANCE_MANIFEST)
    if manifest_bytes is None:
        return [*problems, f"{PROVENANCE_MANIFEST} is missing from provenance bundle"]
    try:
        manifest = json.loads(manifest_bytes)
    except (UnicodeError, json.JSONDecodeError) as exc:
        return [*problems, f"provenance manifest is invalid JSON: {exc}"]
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        return [*problems, "provenance manifest schema_version must be 1"]
    actual_subjects, attestation_names, subject_problems = _provenance_subjects(manifest, members)
    if actual_subjects != expected_artifacts:
        subject_problems.append("provenance subjects do not exactly match release payloads")
    return [
        *problems,
        *_provenance_release_findings(manifest, version),
        *subject_problems,
        *_provenance_file_findings(manifest, members, attestation_names),
    ]


def extract_provenance_bundle(path: Path, destination: Path) -> None:
    """Safely materialize already-named regular files from a provenance bundle."""
    members, problems = _read_provenance_bundle(path)
    if problems:
        raise ValueError("; ".join(problems))
    for name, payload in members.items():
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)


def _checksums(path: Path) -> dict[str, str]:
    checksums: dict[str, str] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        match = _CHECKSUM_LINE.fullmatch(line)
        if match is None:
            raise ValueError(f"invalid checksum line {line_number}: {line!r}")
        digest, filename = match.groups()
        candidate = Path(filename)
        if candidate.name != filename or filename in checksums:
            raise ValueError(f"unsafe or duplicate checksum filename: {filename!r}")
        checksums[filename] = digest
    if not checksums:
        raise ValueError("SHA256SUMS is empty")
    return checksums


def _checksum_problems(directory: Path, checksums: dict[str, str]) -> list[str]:
    problems: list[str] = []
    for filename, expected in checksums.items():
        path = directory / filename
        if not path.is_file():
            problems.append(f"checksummed asset is missing: {filename}")
        elif sha256_path(path) != expected:
            problems.append(f"checksum mismatch: {filename}")
    return problems


def _release_inventory(
    directory: Path,
) -> tuple[list[Path], list[Path], list[Path], list[Path], Path, list[str]]:
    wheels = sorted(directory.glob("*.whl"))
    sdists = sorted(directory.glob("swelter-*.tar.gz"))
    frontends = sorted(directory.glob("swelter-observatory-*.tgz"))
    sboms = sorted(directory.glob("*.cdx.json"))
    provenance = directory / PROVENANCE_BUNDLE
    problems: list[str] = []
    if len(wheels) != 1 or len(sdists) != 1:
        problems.append("release must contain exactly one wheel and one source distribution")
    if len(frontends) != 1:
        problems.append("release must contain exactly one versioned observatory artifact")
    if len(sboms) != len(wheels) + len(sdists) + len(frontends):
        problems.append("release must contain one CycloneDX BOM per released artifact")
    if not (directory / "RELEASE_NOTES.md").is_file():
        problems.append("RELEASE_NOTES.md is missing")
    if not provenance.is_file():
        problems.append(f"{PROVENANCE_BUNDLE} is missing")
    return wheels, sdists, frontends, sboms, provenance, problems


def _sbom_linkage_problems(
    sbom: Path, version: str, expected_artifacts: dict[str, str]
) -> tuple[list[str], str | None]:
    problems = [f"{sbom.name}: {problem}" for problem in validate_sbom(sbom)]
    described: str | None = None
    try:
        document = json.loads(sbom.read_text(encoding="utf-8"))
        component = document["metadata"]["component"]
        if component.get("version") != version:
            problems.append(f"{sbom.name}: package version does not equal {version}")
        properties = component.get("properties", [])
        filename = next(
            item.get("value")
            for item in properties
            if isinstance(item, dict) and item.get("name") == "swelter:release:artifact"
        )
        if not isinstance(filename, str) or filename not in expected_artifacts:
            problems.append(f"{sbom.name}: describes unknown artifact {filename!r}")
            return problems, None
        described = filename
        hashes = component.get("hashes", [])
        actual = next(
            item.get("content")
            for item in hashes
            if isinstance(item, dict) and item.get("alg") == "SHA-256"
        )
        if actual != expected_artifacts[filename]:
            problems.append(f"{sbom.name}: artifact hash linkage is invalid")
    except (
        AttributeError,
        KeyError,
        OSError,
        StopIteration,
        TypeError,
        json.JSONDecodeError,
    ) as exc:
        problems.append(f"{sbom.name}: cannot inspect release linkage: {exc}")
    return problems, described


def _release_sbom_problems(
    sboms: list[Path], version: str, expected_artifacts: dict[str, str]
) -> list[str]:
    problems: list[str] = []
    described_artifacts: set[str] = set()
    for sbom in sboms:
        findings, described = _sbom_linkage_problems(sbom, version, expected_artifacts)
        problems.extend(findings)
        if described is not None:
            described_artifacts.add(described)
    if described_artifacts != set(expected_artifacts):
        problems.append("SBOM set does not describe every package artifact")
    return problems


def validate_sigstore_bundle(path: Path) -> list[str]:
    """Validate the consumer-visible structure emitted by the pinned Cosign v3 signer."""
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return [f"cannot read Sigstore bundle: {exc}"]
    if not isinstance(document, dict):
        return ["Sigstore bundle root is not an object"]
    problems: list[str] = []
    if document.get("mediaType") != SIGSTORE_BUNDLE_MEDIA_TYPE:
        problems.append("Sigstore bundle is not the v0.3 format emitted by Cosign v3")
    if not isinstance(document.get("verificationMaterial"), dict):
        problems.append("Sigstore bundle has no verificationMaterial object")
    if not isinstance(document.get("messageSignature"), dict):
        problems.append("Sigstore bundle has no messageSignature object")
    return problems


def _evidence_problems(assets: list[Path], manifest: Path, checksums: dict[str, str]) -> list[str]:
    problems: list[str] = []
    for asset in assets:
        if asset.name not in checksums and asset != manifest:
            problems.append(f"asset is absent from SHA256SUMS: {asset.name}")
        bundle = Path(f"{asset}.sigstore.json")
        if not bundle.is_file():
            problems.append(f"Sigstore bundle is missing: {asset.name}")
            continue
        problems.extend(f"{bundle.name}: {problem}" for problem in validate_sigstore_bundle(bundle))
    return problems


def verify_download(directory: Path, version: str) -> list[str]:
    """Verify release payload linkage before external signature/provenance checks."""
    problems: list[str] = []
    manifest = directory / "SHA256SUMS"
    if not manifest.is_file():
        return ["SHA256SUMS is missing"]
    try:
        checksums = _checksums(manifest)
    except (OSError, ValueError) as exc:
        return [str(exc)]
    problems.extend(_checksum_problems(directory, checksums))
    wheels, sdists, frontends, sboms, provenance, inventory_problems = _release_inventory(directory)
    problems.extend(inventory_problems)
    expected_artifacts = {path.name: sha256_path(path) for path in [*wheels, *sdists, *frontends]}
    problems.extend(_release_sbom_problems(sboms, version, expected_artifacts))
    provenance_subjects = {
        path.name: sha256_path(path)
        for path in [*wheels, *sdists, *frontends, *sboms, directory / "RELEASE_NOTES.md"]
        if path.is_file()
    }
    if provenance.is_file():
        problems.extend(
            verify_provenance_bundle(
                provenance, version=version, expected_artifacts=provenance_subjects
            )
        )
    checksummed_assets = [
        *wheels,
        *sdists,
        *frontends,
        *sboms,
        directory / "RELEASE_NOTES.md",
        provenance,
    ]
    expected_checksums = {path.name for path in checksummed_assets if path.is_file()}
    if set(checksums) != expected_checksums:
        problems.append("SHA256SUMS does not exactly enumerate the release payloads")
    signed_assets = [*checksummed_assets, manifest]
    problems.extend(_evidence_problems(signed_assets, manifest, checksums))
    expected_files = {path.name for path in signed_assets if path.is_file()}
    signed_names = set(expected_files)
    expected_files.update(f"{name}.sigstore.json" for name in signed_names)
    actual_files = {path.name for path in directory.iterdir() if path.is_file()}
    if actual_files != expected_files:
        problems.append("release contains missing or unexpected downloadable assets")
    return problems


#: Issue #105 is the merge/Pages governance gap. It is a separate, separately tracked deferral,
#: and the PyPI evidence file must not fold itself into it. Matched as a reference, not as three
#: digits appearing anywhere in the file.
_GOVERNANCE_ISSUE_REFERENCE = re.compile(
    r"(?:#105\b|\bissues?/105\b|\"tracking_issue\"\s*:\s*105\b)"
)


def validate_publishing_gap(path: Path) -> list[str]:
    """Validate the explicit machine-readable state of the required PyPI channel."""
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"cannot read publishing gap: {exc}"]
    if not isinstance(document, dict):
        return ["publishing gap root is not an object"]
    problems: list[str] = []
    expected = {
        "schema_version": 1,
        "channel": "PyPI",
        "state": "pending_external_configuration",
        "release_blocking": True,
        "canonical_distribution": "GitHub Releases",
    }
    for field, value in expected.items():
        if document.get(field) != value:
            problems.append(f"publishing gap {field} must be {value!r}")
    prerequisites = document.get("required_external_configuration")
    if (
        not isinstance(prerequisites, list)
        or len(prerequisites) < 2
        or any(not isinstance(item, str) or not item.strip() for item in prerequisites)
    ):
        problems.append("publishing gap must name each external prerequisite")
    for field in ("owner", "reviewed"):
        if not isinstance(document.get(field), str) or not document[field].strip():
            problems.append(f"publishing gap {field} is missing")
    try:
        date.fromisoformat(str(document.get("reviewed")))
    except ValueError:
        problems.append("publishing gap reviewed must be an ISO calendar date")
    # A bare ``"105" in text`` substring test could not tell an issue reference from any other
    # occurrence of those three digits -- a byte count, a run id, part of a longer number. It
    # would have fired on a coincidence and, being a substring test rather than a reference
    # match, told the reader nothing about which reference it meant. Match the reference forms
    # this repository actually uses.
    if _GOVERNANCE_ISSUE_REFERENCE.search(path.read_text(encoding="utf-8")):
        problems.append("PyPI publishing gap must not be conflated with governance issue #105")
    return problems


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    generate = subparsers.add_parser("generate-sbom")
    generate.add_argument("--artifact", type=Path, required=True)
    generate.add_argument("--output", type=Path, required=True)
    validate = subparsers.add_parser("validate-sbom")
    validate.add_argument("paths", nargs="+", type=Path)
    notes = subparsers.add_parser("release-notes")
    notes.add_argument("--version", required=True)
    notes.add_argument("--output", type=Path, required=True)
    provenance = subparsers.add_parser("provenance-bundle")
    provenance.add_argument("--asset", action="append", type=Path, required=True, dest="assets")
    provenance.add_argument("--attestations-directory", type=Path, required=True)
    provenance.add_argument("--output", type=Path, required=True)
    provenance.add_argument("--version", required=True)
    provenance.add_argument("--commit", required=True)
    provenance.add_argument("--repository", required=True)
    extract = subparsers.add_parser("extract-provenance")
    extract.add_argument("--bundle", type=Path, required=True)
    extract.add_argument("--directory", type=Path, required=True)
    publishing = subparsers.add_parser("validate-publishing-gap")
    publishing.add_argument("path", type=Path)
    verify = subparsers.add_parser("verify-download")
    verify.add_argument("--directory", type=Path, required=True)
    verify.add_argument("--version", required=True)
    return parser


def _print_findings(findings: list[str]) -> int:
    for finding in findings:
        print(f"  [FAIL] {finding}")
    return 1


def _command_generate_sbom(args: argparse.Namespace) -> int:
    write_sbom(args.artifact, args.output)
    print(f"sbom: wrote CycloneDX 1.7 {args.output}")
    return 0


def _command_validate_sbom(args: argparse.Namespace) -> int:
    findings = [f"{path}: {problem}" for path in args.paths for problem in validate_sbom(path)]
    if findings:
        return _print_findings(findings)
    print(f"sbom: {len(args.paths)} CycloneDX 1.7 document(s) passed portfolio validation")
    return 0


def _command_release_notes(args: argparse.Namespace) -> int:
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(changelog_section(args.version), encoding="utf-8")
    print(f"release-notes: wrote {args.output}")
    return 0


def _command_provenance(args: argparse.Namespace) -> int:
    build_provenance_bundle(
        assets=args.assets,
        attestations_directory=args.attestations_directory,
        output=args.output,
        version=args.version,
        commit=args.commit,
        repository=args.repository,
    )
    print(f"provenance: wrote deterministic downloadable bundle {args.output}")
    return 0


def _command_extract(args: argparse.Namespace) -> int:
    extract_provenance_bundle(args.bundle, args.directory)
    print(f"provenance: safely extracted {args.bundle} to {args.directory}")
    return 0


def _command_publishing_gap(args: argparse.Namespace) -> int:
    """Block the release, and say which of the two reasons is blocking it.

    Both outcomes exit 1, which is correct: the PyPI gap is release-blocking whether or not the
    evidence file describing it is well formed. What was wrong is that both outcomes printed the
    same shape of ``[FAIL]`` line, so every assertion in ``validate_publishing_gap`` -- schema
    version, channel, state, blocking flag, prerequisite list, owner, review date -- made no
    observable difference: a corrupted, truncated, or semantically wrong evidence file read
    exactly like the healthy tracked gap. A validator whose result cannot be told from its
    absence is not validating.
    """
    findings = validate_publishing_gap(args.path)
    if findings:
        print(
            f"publishing-gap: {args.path} does not state a valid release-blocking gap "
            "(these findings are about the evidence file, not about PyPI)"
        )
        return _print_findings(findings)
    print(f"publishing-gap: {args.path} is a valid, tracked, release-blocking gap")
    return _print_findings(
        [
            "PyPI Trusted Publishing and its protected environment are pending; "
            "the portfolio release standard blocks this release"
        ]
    )


def _command_verify_download(args: argparse.Namespace) -> int:
    findings = verify_download(args.directory, args.version)
    if findings:
        return _print_findings(findings)
    print(f"release-consumer: payload for {args.version} is complete and internally linked")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    handlers = {
        "generate-sbom": _command_generate_sbom,
        "validate-sbom": _command_validate_sbom,
        "release-notes": _command_release_notes,
        "provenance-bundle": _command_provenance,
        "extract-provenance": _command_extract,
        "validate-publishing-gap": _command_publishing_gap,
        "verify-download": _command_verify_download,
    }
    return handlers[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
