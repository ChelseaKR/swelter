"""Tests for release evidence, mutation reporting, and workflow hardening gates."""

from __future__ import annotations

import importlib
import json
import shutil
import sys
import tomllib
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import yaml

ROOT = Path(__file__).resolve().parent.parent
if TYPE_CHECKING:
    from scripts import mutation_report, release_artifacts, workflow_policy_check
else:
    sys.path.insert(0, str(ROOT))
    mutation_report = importlib.import_module("scripts.mutation_report")
    release_artifacts = importlib.import_module("scripts.release_artifacts")
    workflow_policy_check = importlib.import_module("scripts.workflow_policy_check")

# release_artifacts.build_sbom reads the version out of pyproject.toml, so the release fixture
# below has to read the same source instead of hard-coding a number. When these were two separate
# literals, bumping the package version failed these tests for the wrong reason: the payload was
# correct and the fixture was stale.
PACKAGE_VERSION: str = cast(
    str,
    tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"],
)


def _write_release_fixture(directory: Path) -> list[Path]:
    wheel = directory / f"swelter-{PACKAGE_VERSION}-py3-none-any.whl"
    sdist = directory / f"swelter-{PACKAGE_VERSION}.tar.gz"
    frontend = directory / f"swelter-observatory-{PACKAGE_VERSION}.tgz"
    wheel.write_bytes(b"wheel payload")
    sdist.write_bytes(b"source payload")
    frontend.write_bytes(b"frontend payload")
    assets = [wheel, sdist, frontend]
    for artifact in (wheel, sdist, frontend):
        sbom = directory / f"{artifact.name}.cdx.json"
        release_artifacts.write_sbom(artifact, sbom)
        assets.append(sbom)
    notes = directory / "RELEASE_NOTES.md"
    notes.write_text(f"# swelter {PACKAGE_VERSION}\n", encoding="utf-8")
    assets.append(notes)
    attestations = directory / "provenance-inputs"
    attestations.mkdir()
    (attestations / "trusted_root.jsonl").write_text("{}\n", encoding="utf-8")
    for asset in assets:
        (attestations / f"{asset.name}.intoto.jsonl").write_text("{}\n", encoding="utf-8")
    provenance = directory / release_artifacts.PROVENANCE_BUNDLE
    release_artifacts.build_provenance_bundle(
        assets=assets,
        attestations_directory=attestations,
        output=provenance,
        version=PACKAGE_VERSION,
        commit="a" * 40,
        repository="ChelseaKR/swelter",
    )
    assets.append(provenance)
    manifest = directory / "SHA256SUMS"
    manifest.write_text(
        "".join(f"{release_artifacts.sha256_path(path)}  {path.name}\n" for path in assets),
        encoding="utf-8",
    )
    for asset in [*assets, manifest]:
        Path(f"{asset}.sigstore.json").write_text(
            json.dumps(
                {
                    "mediaType": release_artifacts.SIGSTORE_BUNDLE_MEDIA_TYPE,
                    "verificationMaterial": {},
                    "messageSignature": {},
                }
            )
            + "\n",
            encoding="utf-8",
        )
    return assets


def _release_jobs() -> dict[str, Any]:
    document = yaml.safe_load((ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    jobs = document.get("jobs")
    assert isinstance(jobs, dict)
    return cast(dict[str, Any], jobs)


def test_cyclonedx_release_sbom_is_bound_to_artifact(tmp_path: Path) -> None:
    artifact = tmp_path / f"swelter-{PACKAGE_VERSION}-py3-none-any.whl"
    artifact.write_bytes(b"immutable artifact")
    document = release_artifacts.build_sbom(artifact)
    assert release_artifacts.validate_sbom_document(document) == []
    assert document["specVersion"] == "1.7"
    assert document["metadata"]["component"]["hashes"] == [
        {"alg": "SHA-256", "content": release_artifacts.sha256_path(artifact)}
    ]
    assert all(component["purl"] for component in document["components"])


def test_release_consumer_verifies_complete_payload_and_detects_tampering(
    tmp_path: Path,
) -> None:
    assets = _write_release_fixture(tmp_path)
    assert release_artifacts.verify_download(tmp_path, PACKAGE_VERSION) == []
    assets[0].write_bytes(b"tampered")
    assert any(
        "checksum mismatch" in problem
        for problem in release_artifacts.verify_download(tmp_path, PACKAGE_VERSION)
    )


def test_release_consumer_rejects_legacy_or_malformed_signature_evidence(tmp_path: Path) -> None:
    assets = _write_release_fixture(tmp_path)
    bundle = Path(f"{assets[0]}.sigstore.json")
    bundle.write_text("{}\n", encoding="utf-8")
    findings = release_artifacts.verify_download(tmp_path, PACKAGE_VERSION)
    assert any("not the v0.3 format" in finding for finding in findings)
    bundle.unlink()
    Path(f"{assets[0]}.sig").write_text("legacy signature\n", encoding="utf-8")
    Path(f"{assets[0]}.pem").write_text("legacy certificate\n", encoding="utf-8")
    findings = release_artifacts.verify_download(tmp_path, PACKAGE_VERSION)
    assert any("Sigstore bundle is missing" in finding for finding in findings)
    assert "release contains missing or unexpected downloadable assets" in findings


def test_release_signing_credentials_are_isolated_from_repository_execution() -> None:
    jobs = _release_jobs()
    build = jobs["build"]
    signer = jobs["attest-sign"]
    publisher = jobs["publish-draft"]
    draft_verifier = jobs["draft-verification"]
    consumer = jobs["consumer-verification"]
    promoter = jobs["promote-release"]
    assert build["permissions"] == {"contents": "read"}
    assert signer["permissions"] == {
        "attestations": "write",
        "contents": "read",
        "id-token": "write",
    }
    assert publisher["permissions"] == {"contents": "write"}
    assert draft_verifier["permissions"] == {"attestations": "read", "contents": "read"}
    assert consumer["permissions"] == {"attestations": "read", "contents": "read"}
    assert promoter["permissions"] == {"contents": "write"}

    for isolated_job in (signer, publisher, draft_verifier, promoter):
        steps = isolated_job["steps"]
        uses = "\n".join(str(step.get("uses", "")) for step in steps)
        runs = "\n".join(str(step.get("run", "")) for step in steps)
        assert "actions/checkout" not in uses
        assert "setup-node" not in uses
        assert "setup-uv" not in uses
        for forbidden in ("scripts/", "make ", "npm ", "node ", "python ", "pip ", "uv "):
            assert forbidden not in runs

    consumer_runs = "\n".join(str(step.get("run", "")) for step in consumer["steps"])
    promoter_runs = "\n".join(str(step.get("run", "")) for step in promoter["steps"])
    assert "gh release edit" not in consumer_runs
    assert "gh release edit" in promoter_runs
    assert "draft-verification" in promoter["needs"]
    assert "EXPECTED_ASSET_SET_SHA256" in promoter["steps"][0]["env"]
    assert "actual_asset_set_sha256" in promoter_runs


def test_release_toolchain_and_cosign_bundle_format_are_exactly_pinned() -> None:
    jobs = _release_jobs()
    build_steps = jobs["build"]["steps"]
    setup_uv = next(step for step in build_steps if "astral-sh/setup-uv" in step.get("uses", ""))
    setup_node = next(step for step in build_steps if "actions/setup-node" in step.get("uses", ""))
    assert setup_uv["with"]["version"] == "0.11.28"
    assert setup_node["with"]["node-version"] == "22.12.0"
    signer_steps = jobs["attest-sign"]["steps"]
    cosign = next(
        step for step in signer_steps if "sigstore/cosign-installer" in step.get("uses", "")
    )
    assert cosign["with"]["cosign-release"] == "v3.1.1"
    signer_runs = "\n".join(str(step.get("run", "")) for step in signer_steps)
    assert 'cosign sign-blob --yes --bundle "${asset}.sigstore.json"' in signer_runs
    assert '--bundle "${asset}.sigstore.json"' in signer_runs
    assert "--output-signature" not in signer_runs
    assert "--output-certificate" not in signer_runs


def test_release_notes_are_extracted_from_dated_changelog_section() -> None:
    notes = release_artifacts.changelog_section("0.1.0")
    assert notes.startswith("# swelter 0.1.0\n")
    assert "## [0.1.0] - 2026-07-16" in notes
    assert "## [Unreleased]" not in notes


def test_mutation_report_scores_selected_core_modules(tmp_path: Path) -> None:
    mutants = tmp_path / "mutants" / "src" / "swelter"
    mutants.mkdir(parents=True)
    for module in mutation_report.DEFAULT_MODULES:
        (mutants / f"{module}.py.meta").write_text(
            json.dumps(
                {
                    "exit_code_by_key": {
                        f"swelter.{module}.x_a__mutmut_1": 1,
                        f"swelter.{module}.x_b__mutmut_1": 1,
                        f"swelter.{module}.x_c__mutmut_1": 1,
                        f"swelter.{module}.x_d__mutmut_1": 1,
                        f"swelter.{module}.x_e__mutmut_1": 0,
                    },
                    "hash_by_function_name": {},
                }
            ),
            encoding="utf-8",
        )
    counts, non_killed = mutation_report.collect(
        tmp_path / "mutants", mutation_report.DEFAULT_MODULES
    )
    assert mutation_report.mutation_score(counts) == 80.0
    assert len(non_killed) == 3
    assert mutation_report.incomplete_statuses(counts) == []


def test_mutation_timeout_is_not_a_kill_and_fails_completeness() -> None:
    counts = Counter({"killed": 8, "survived": 1, "timeout": 1})
    assert mutation_report.mutation_score(counts) == 80.0
    assert mutation_report.incomplete_statuses(counts) == ["timeout"]


def test_mutation_baseline_binds_source_config_tests_and_tool_lock(tmp_path: Path) -> None:
    for relative in (
        *mutation_report.SOURCE_FILES,
        *mutation_report.TEST_FILES,
        Path("pyproject.toml"),
        Path("uv.lock"),
    ):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    counts = Counter({"killed": 12, "survived": 3})
    non_killed = [
        {"id": f"swelter.models.mutant_{index}", "status": "survived"} for index in range(3)
    ]
    result = mutation_report.report(counts, non_killed, mutation_report.DEFAULT_MODULES)
    baseline = mutation_report.build_baseline(result, "2026-07-16", 80.0, tmp_path)
    assert mutation_report.verify_baseline(baseline, tmp_path) == []
    (tmp_path / mutation_report.SOURCE_FILES[0]).write_text("changed\n", encoding="utf-8")
    assert "source_sha256 is stale" in mutation_report.verify_baseline(baseline, tmp_path)


def test_provenance_bundle_detects_subject_mismatch(tmp_path: Path) -> None:
    _write_release_fixture(tmp_path)
    findings = release_artifacts.verify_provenance_bundle(
        tmp_path / release_artifacts.PROVENANCE_BUNDLE,
        version=PACKAGE_VERSION,
        expected_artifacts={"different.whl": "0" * 64},
    )
    assert "provenance subjects do not exactly match release payloads" in findings


def test_pypi_gap_is_explicit_and_machine_readable() -> None:
    assert (
        release_artifacts.validate_publishing_gap(ROOT / "docs/audits/release-publishing-gap.json")
        == []
    )
    assert (
        release_artifacts.main(
            [
                "validate-publishing-gap",
                str(ROOT / "docs/audits/release-publishing-gap.json"),
            ]
        )
        == 1
    )


def test_workflow_policy_rejects_mutable_or_major_only_action_refs(tmp_path: Path) -> None:
    workflow = tmp_path / "bad.yml"
    workflow.write_text(
        "permissions:\n  contents: read\njobs:\n  test:\n    steps:\n"
        "      - uses: actions/checkout@v4 # v4\n",
        encoding="utf-8",
    )
    findings = workflow_policy_check.scan_workflow(workflow)
    assert any("40-character SHA" in finding for finding in findings)
    assert any("exact trailing semver" in finding for finding in findings)


def _gap_document() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "channel": "PyPI",
        "state": "pending_external_configuration",
        "release_blocking": True,
        "canonical_distribution": "GitHub Releases",
        "required_external_configuration": ["Configure PyPI.", "Protect the environment."],
        "owner": "Owner Name",
        "reviewed": "2026-07-16",
        "tracking_issue": 108,
    }


def test_a_corrupt_publishing_gap_does_not_read_like_the_tracked_one(
    tmp_path: Path, capsys: Any
) -> None:
    """Both outcomes exit 1, which is right: the PyPI gap blocks the release either way. What was
    wrong is that both printed the same shape of ``[FAIL]`` line, so every assertion in
    ``validate_publishing_gap`` -- schema version, channel, state, blocking flag, prerequisites,
    owner, review date -- made no observable difference. A corrupt file read exactly like the
    healthy tracked gap."""
    import argparse

    healthy = tmp_path / "gap.json"
    healthy.write_text(json.dumps(_gap_document()), encoding="utf-8")
    assert release_artifacts.validate_publishing_gap(healthy) == []
    assert release_artifacts._command_publishing_gap(argparse.Namespace(path=healthy)) == 1
    good_output = capsys.readouterr().out
    assert "is a valid, tracked, release-blocking gap" in good_output

    broken = tmp_path / "broken.json"
    document = _gap_document()
    document["release_blocking"] = False
    del document["owner"]
    broken.write_text(json.dumps(document), encoding="utf-8")
    assert release_artifacts.validate_publishing_gap(broken)
    assert release_artifacts._command_publishing_gap(argparse.Namespace(path=broken)) == 1
    bad_output = capsys.readouterr().out
    assert "does not state a valid release-blocking gap" in bad_output
    assert "is a valid, tracked, release-blocking gap" not in bad_output


def test_the_governance_issue_rule_matches_a_reference_not_three_digits(tmp_path: Path) -> None:
    """``"105" in text`` could not tell an issue reference from any other occurrence of those
    digits, so it would fire on a byte count or a run id and told the reader nothing about which
    reference it meant."""
    coincidence = tmp_path / "coincidence.json"
    document = _gap_document()
    document["owner"] = "Owner Name (desk 105)"
    coincidence.write_text(json.dumps(document), encoding="utf-8")
    assert "105" in coincidence.read_text(encoding="utf-8")
    assert release_artifacts.validate_publishing_gap(coincidence) == []

    conflated = tmp_path / "conflated.json"
    document = _gap_document()
    document["owner"] = "Owner Name, tracked alongside #105"
    conflated.write_text(json.dumps(document), encoding="utf-8")
    assert any(
        "governance issue #105" in problem
        for problem in release_artifacts.validate_publishing_gap(conflated)
    )
