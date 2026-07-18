"""Human release evidence is schema-checked and bound to reviewed source bytes."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

ROOT = Path(__file__).resolve().parent.parent
if TYPE_CHECKING:
    from scripts import release_review_check
else:
    sys.path.insert(0, str(ROOT))
    release_review_check = importlib.import_module("scripts.release_review_check")


def _manifest(root: Path) -> dict[str, Any]:
    artifacts: list[dict[str, Any]] = []
    for identifier in sorted(release_review_check.REQUIRED_ATTESTATIONS):
        artifact = root / f"{identifier}.md"
        artifact.write_text(f"# {identifier}\n", encoding="utf-8")
        artifacts.append(
            {
                "id": identifier,
                "artifact": artifact.name,
                "outcome": "pass",
                "reviewer": "Jordan Human",
                "reviewed": "2026-07-17",
                "independent": identifier in {"accessibility", "spanish-language"},
                "notes": "All named tasks passed; no unresolved release blocker remains.",
            }
        )
    return {
        "schema_version": 1,
        "release_version": "0.1.0",
        "tracking_issue": None,
        "reviewed_source_sha256": "a" * 64,
        "attestations": artifacts,
    }


def test_pending_committed_manifest_is_honest_but_not_release_complete() -> None:
    path = ROOT / "docs" / "audits" / "release-review-attestations.json"
    assert release_review_check.validate_manifest(path) == []
    problems = release_review_check.validate_manifest(path, require_complete=True)
    assert any("still pending" in problem for problem in problems)
    assert "completed release review has no source digest" in problems


def test_complete_manifest_rejects_non_human_and_stale_digest(tmp_path: Path) -> None:
    import subprocess

    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)  # noqa: S603,S607 (#107)
    document = _manifest(tmp_path)
    document["attestations"][0]["reviewer"] = "OpenAI Codex"
    path = tmp_path / "review.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    problems = release_review_check.validate_manifest(path, root=tmp_path, require_complete=True)
    assert any("human reviewer" in problem for problem in problems)
    assert "reviewed source digest is stale" in problems


def test_complete_manifest_accepts_exact_reviewed_tree(tmp_path: Path) -> None:
    # Initialize a tiny Git source set because the digest deliberately follows Git visibility.
    import subprocess

    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)  # noqa: S603,S607 (#107)
    document = _manifest(tmp_path)
    path = tmp_path / "review.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    document["reviewed_source_sha256"] = release_review_check.source_digest(tmp_path, path)
    path.write_text(json.dumps(document), encoding="utf-8")
    assert (
        release_review_check.validate_manifest(
            path, root=tmp_path, expected_version="0.1.0", require_complete=True
        )
        == []
    )

    (tmp_path / "ethics.md").write_text("changed\n", encoding="utf-8")
    assert "reviewed source digest is stale" in release_review_check.validate_manifest(
        path, root=tmp_path, require_complete=True
    )
