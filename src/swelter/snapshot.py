"""Snapshot: a frozen, identified data release a researcher or journalist can publish against.

``swelter snapshot`` freezes the store's *immutable* raw observations, the correction registry
that was fitted against them, and the latest gridded surface into a self-contained folder, plus
three small files that make the release citable:

* ``MANIFEST.json``      — release version, creation time, package version, per-file SHA-256,
  record count, and the observation time-window, so a consumer can verify what they downloaded.
* ``DATA-CITATION.cff``  — Citation File Format 1.2.0, ``type: dataset`` (the repository's
  ``CITATION.cff`` at the root is ``type: software`` and stays that way; the two are deliberately
  separate files because software and data are different things to cite).
* ``CITATION.txt``       — the same citation rendered as a ready-to-paste plain-text string.

Only local artifacts are used — there is no call to an external DOI service. A collective that
has minted a DOI (Zenodo, DataCite, an institutional repository, ...) passes it with ``--doi``;
otherwise the release carries an honest, clearly-labelled placeholder so nothing is silently
mistaken for a real identifier.

This module never reads or mutates the raw log: it opens the store read-only and copies
(``corrections.yaml``, ``aggregate.geojson``) or re-exports through :mod:`swelter.export`
(the raw observations), so the calibrated-vs-raw distinction that the rest of swelter enforces
travels into the snapshot as clearly labelled, separate files rather than a mixed dump.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from . import export
from .models import RAW, format_timestamp
from .store import open_store, store_paths

MANIFEST_FILENAME = "MANIFEST.json"
DATA_CITATION_FILENAME = "DATA-CITATION.cff"
CITATION_TXT_FILENAME = "CITATION.txt"
RAW_OBSERVATIONS_FILENAME = "observations-raw.json"
CORRECTIONS_FILENAME = "corrections.yaml"
AGGREGATE_FILENAME = "aggregate.geojson"

#: Where a snapshot looks for the software citation to mirror authors from, relative to the
#: working directory — the same convention `network.yaml` / `data/demo` defaults use elsewhere
#: in the CLI (this tool is run from a repo checkout, not installed standalone).
DEFAULT_CITATION_PATH = Path("CITATION.cff")

#: Used only if the repo's CITATION.cff cannot be found/parsed, so a snapshot never fails outright
#: for want of author metadata. Keep in sync with the root CITATION.cff's `authors:` block.
_FALLBACK_AUTHORS: tuple[dict[str, str], ...] = (
    {"given-names": "Chelsea", "family-names": "Kelly-Reif", "alias": "ChelseaKR"},
)

#: An honestly-labelled placeholder, never presented as if it were a real, resolvable DOI.
DOI_PLACEHOLDER = "10.0000/swelter-snapshot-doi-not-yet-assigned"

DATA_LICENSE = "CC0-1.0"


@dataclass(frozen=True)
class ManifestFile:
    """One file inside the snapshot, as recorded in ``MANIFEST.json``."""

    name: str
    description: str
    sha256: str
    bytes: int

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "description": self.description,
            "sha256": self.sha256,
            "bytes": self.bytes,
        }


@dataclass(frozen=True)
class SnapshotManifest:
    """The parsed contents of ``MANIFEST.json`` for a built snapshot."""

    release_version: str
    created_at: str
    swelter_version: str
    record_count: int
    observation_window: tuple[str, str] | None
    files: tuple[ManifestFile, ...]
    doi: str | None
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        window: dict[str, str] | None = None
        if self.observation_window is not None:
            window = {"start": self.observation_window[0], "end": self.observation_window[1]}
        return {
            "release_version": self.release_version,
            "created_at": self.created_at,
            "swelter_version": self.swelter_version,
            "record_count": self.record_count,
            "observation_window": window,
            "doi": self.doi,
            "files": [f.to_dict() for f in self.files],
            "notes": list(self.notes),
        }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _swelter_version() -> str:
    """The installed package version, falling back to the in-tree constant for an editable
    checkout that `importlib.metadata` cannot resolve (e.g. run without `uv sync`/install)."""
    try:
        return importlib.metadata.version("swelter")
    except importlib.metadata.PackageNotFoundError:
        from . import __version__ as fallback

        return fallback


def _load_citation_authors(citation_path: Path) -> list[dict[str, Any]]:
    """Mirror the `authors:` block of the repo's software CITATION.cff, so the dataset citation
    names the same people without hand-duplicating them."""
    if citation_path.is_file():
        try:
            doc = yaml.safe_load(citation_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            doc = {}
        authors = doc.get("authors") if isinstance(doc, dict) else None
        if isinstance(authors, list) and authors:
            return [dict(a) for a in authors if isinstance(a, dict)]
    return [dict(a) for a in _FALLBACK_AUTHORS]


def _author_citation_name(author: dict[str, Any]) -> str:
    """Render one CFF author as a short citation-style name: 'Family, G.'"""
    family = str(author.get("family-names", "")).strip()
    given = str(author.get("given-names", "")).strip()
    if family and given:
        return f"{family}, {given[0]}."
    if family:
        return family
    alias = author.get("alias")
    if alias:
        return str(alias)
    name = author.get("name")
    if name:
        return str(name)
    return "Unknown"


def _join_author_names(names: list[str]) -> str:
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} & {names[1]}"
    return ", ".join(names[:-1]) + f", & {names[-1]}"


def _doi_identifier(doi: str | None) -> dict[str, str]:
    if doi:
        return {
            "type": "doi",
            "value": doi,
            "description": "Canonical identifier for this data release.",
        }
    return {
        "type": "doi",
        "value": DOI_PLACEHOLDER,
        "description": (
            "Placeholder — this release has not yet been registered with a DOI provider "
            "(e.g. Zenodo/DataCite). Replace with the assigned DOI and re-run "
            "`swelter snapshot --doi <doi>`."
        ),
    }


def _render_data_citation_cff(
    *, version: str, date_released: str, authors: list[dict[str, Any]], doi: str | None
) -> str:
    doc: dict[str, object] = {
        "cff-version": "1.2.0",
        "message": "If you use this data snapshot, please cite it using this metadata.",
        "title": f"swelter observation snapshot {version}",
        "type": "dataset",
        "authors": authors,
        "version": version,
        "date-released": date_released,
        "license": DATA_LICENSE,
        "identifiers": [_doi_identifier(doi)],
    }
    header = (
        "# Generated by `swelter snapshot` — do not hand-edit; re-run the command instead.\n"
        "# Cites the DATA in this release (CC0-1.0). For citing the swelter SOFTWARE, see\n"
        "# the repository's CITATION.cff (type: software, Apache-2.0).\n"
    )
    return header + yaml.safe_dump(
        doc, sort_keys=False, default_flow_style=False, allow_unicode=True
    )


def _render_citation_txt(
    *, version: str, date_released: str, authors: list[dict[str, Any]], doi: str | None
) -> str:
    author_str = _join_author_names([_author_citation_name(a) for a in authors])
    year = date_released[:4]
    locator = (
        f"https://doi.org/{doi}"
        if doi
        else f"DOI pending — see DATA-CITATION.cff (placeholder {DOI_PLACEHOLDER})"
    )
    return (
        f"{author_str} ({year}). swelter observation snapshot {version} [Data set]. "
        f"{DATA_LICENSE}. {locator}\n"
    )


def build_snapshot(
    store: Path,
    out: Path,
    version: str,
    doi: str | None,
    *,
    citation_path: Path = DEFAULT_CITATION_PATH,
    now: datetime | None = None,
) -> SnapshotManifest:
    """Freeze the store's raw observations, corrections, and surface into ``out/``.

    ``now`` is injectable so a caller (a test, or a reproducible-build script) can pin
    ``created_at`` and get byte-identical output across runs against an unchanged store.
    """
    store_dir = Path(store)
    out_dir = Path(out)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = store_paths(store_dir)

    notes: list[str] = []

    with open_store(store_dir) as db:
        raw = db.read(calibration=RAW)

    (out_dir / RAW_OBSERVATIONS_FILENAME).write_text(
        export.to_json(raw, indent=2), encoding="utf-8"
    )
    manifested: list[tuple[str, str]] = [
        (RAW_OBSERVATIONS_FILENAME, "immutable raw observations (calibration=raw), as JSON"),
    ]

    if paths["registry"].is_file():
        shutil.copy2(paths["registry"], out_dir / CORRECTIONS_FILENAME)
        manifested.append(
            (
                CORRECTIONS_FILENAME,
                "calibration correction registry fitted against these raw readings",
            )
        )
    else:
        notes.append("no corrections.yaml in the store — this release holds raw observations only")

    if paths["aggregate"].is_file():
        shutil.copy2(paths["aggregate"], out_dir / AGGREGATE_FILENAME)
        manifested.append(
            (AGGREGATE_FILENAME, "gridded heat/AQI surface, latest cell-hour per cell")
        )
    else:
        notes.append(
            "no aggregate.geojson in the store — run `swelter aggregate` before snapshotting "
            "for a surface release"
        )

    files = tuple(
        ManifestFile(
            name=name,
            description=description,
            sha256=_sha256_file(out_dir / name),
            bytes=(out_dir / name).stat().st_size,
        )
        for name, description in manifested
    )

    created_at = format_timestamp(now if now is not None else datetime.now(UTC))
    timestamps = sorted(o.timestamp for o in raw)
    window = (timestamps[0], timestamps[-1]) if timestamps else None

    manifest = SnapshotManifest(
        release_version=version,
        created_at=created_at,
        swelter_version=_swelter_version(),
        record_count=len(raw),
        observation_window=window,
        files=files,
        doi=doi,
        notes=tuple(notes),
    )
    (out_dir / MANIFEST_FILENAME).write_text(
        json.dumps(manifest.to_dict(), indent=2) + "\n", encoding="utf-8"
    )

    authors = _load_citation_authors(Path(citation_path))
    date_released = created_at[:10]
    (out_dir / DATA_CITATION_FILENAME).write_text(
        _render_data_citation_cff(
            version=version, date_released=date_released, authors=authors, doi=doi
        ),
        encoding="utf-8",
    )
    (out_dir / CITATION_TXT_FILENAME).write_text(
        _render_citation_txt(
            version=version, date_released=date_released, authors=authors, doi=doi
        ),
        encoding="utf-8",
    )

    return manifest
