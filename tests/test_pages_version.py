"""Deployment identity remains exact, public, and safe to regenerate."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

ROOT = Path(__file__).resolve().parent.parent
if TYPE_CHECKING:
    from scripts import stamp_pages_version
else:
    sys.path.insert(0, str(ROOT))
    stamp_pages_version = importlib.import_module("scripts.stamp_pages_version")

COMMIT = "a" * 40


def test_stamp_route_writes_version_and_meta_idempotently(tmp_path: Path) -> None:
    route = tmp_path / "web"
    route.mkdir()
    index = route / "index.html"
    index.write_text(
        "<!doctype html><html><head><title>x</title></head></html>\n", encoding="utf-8"
    )

    kwargs = {
        "commit": COMMIT,
        "ref": "refs/heads/main",
        "repository": "ChelseaKR/swelter",
        "run_id": "42",
        "source_timestamp": "2026-07-17T01:02:03+00:00",
    }
    stamp_pages_version.stamp_route(route, **kwargs)
    stamp_pages_version.stamp_route(route, **kwargs)

    version = json.loads((route / "version.json").read_text(encoding="utf-8"))
    assert version == {
        "schema_version": 1,
        "repository": "ChelseaKR/swelter",
        "commit": COMMIT,
        "ref": "refs/heads/main",
        "workflow_run_id": 42,
        "source_timestamp": "2026-07-17T01:02:03+00:00",
    }
    markup = index.read_text(encoding="utf-8")
    assert markup.count('name="swelter-build-commit"') == 1
    assert f'content="{COMMIT}"' in markup


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("commit", "HEAD"),
        ("ref", "main"),
        ("repository", "swelter"),
        ("run_id", "0"),
        ("source_timestamp", "yesterday"),
    ],
)
def test_version_document_rejects_ambiguous_identity(field: str, value: str) -> None:
    kwargs = {
        "commit": COMMIT,
        "ref": "refs/heads/main",
        "repository": "ChelseaKR/swelter",
        "run_id": "42",
        "source_timestamp": "2026-07-17T01:02:03Z",
    }
    kwargs[field] = value
    with pytest.raises(ValueError):
        stamp_pages_version.version_document(**kwargs)
