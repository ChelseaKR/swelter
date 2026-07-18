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
* ``DATA-LICENSE``       — the terms and attribution for the store being frozen. Fetched stores
  carry the source terms written by :command:`swelter fetch`; native community observations use
  the repository's CC0 default.

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
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from . import export
from .models import (
    KNOWN_SOURCES,
    RAW,
    SOURCE_NATIVE,
    SOURCE_OPENAQ,
    SOURCE_OPENMETEO,
    SOURCE_SENSOR_COMMUNITY,
    Observation,
    format_timestamp,
)
from .store import open_store, store_paths

MANIFEST_FILENAME = "MANIFEST.json"
DATA_CITATION_FILENAME = "DATA-CITATION.cff"
CITATION_TXT_FILENAME = "CITATION.txt"
RAW_OBSERVATIONS_FILENAME = "observations-raw.json"
CORRECTIONS_FILENAME = "corrections.yaml"
AGGREGATE_FILENAME = "aggregate.geojson"
DATA_LICENSE_FILENAME = "DATA-LICENSE"
SOURCE_METADATA_FILENAME = "source-metadata.json"
SOURCE_LICENSE_LEDGER_FILENAME = "source-license-ledger.json"

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

DEFAULT_DATA_LICENSE = "CC0-1.0"
DEFAULT_DATA_SOURCE = "Community-operated swelter network"
DEFAULT_DATA_ATTRIBUTION = "Contributed by the network's participating sensor stewards."


@dataclass(frozen=True)
class DataTerms:
    """Source, license, and attribution that must travel with a data snapshot."""

    source: str
    license: str
    attribution: str
    license_url: str | None = None
    # Validated provider evidence is retained as immutable bytes, not as a path. A path would
    # create a time-of-check/time-of-use gap: the file could change after validation but before an
    # export, HTTP response, or snapshot copied it. Consumers must use these exact validated bytes.
    ledger_content: bytes | None = None
    metadata_content: bytes | None = None


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
    data_source: str
    data_license: str
    data_attribution: str
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
            "data_source": self.data_source,
            "data_license": self.data_license,
            "data_attribution": self.data_attribution,
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


def write_source_metadata(
    store: Path,
    *,
    source: str,
    license: str,
    attribution: str,
    license_url: str | None,
    recorded_at: str,
) -> Path:
    """Record fetched-store terms beside the database so later exports cannot silently use CC0."""
    required = {"source": source, "license": license, "attribution": attribution}
    empty = [name for name, value in required.items() if not value.strip()]
    if empty:
        raise ValueError(f"source metadata has empty required field(s): {', '.join(empty)}")
    doc: dict[str, object] = {
        "schema_version": 1,
        "source": source,
        "license": license,
        "attribution": attribution,
        "recorded_at": recorded_at,
    }
    if license_url:
        doc["license_url"] = license_url
    path = Path(store) / SOURCE_METADATA_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _read_source_metadata(content: bytes) -> DataTerms:
    try:
        doc = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid {SOURCE_METADATA_FILENAME}: {exc}") from exc
    if not isinstance(doc, dict) or doc.get("schema_version") != 1:
        raise ValueError(f"invalid {SOURCE_METADATA_FILENAME}: expected schema_version 1")
    values = {name: doc.get(name) for name in ("source", "license", "attribution")}
    if any(
        not isinstance(value, str) or not value.strip() or value != value.strip()
        for value in values.values()
    ):
        raise ValueError(
            f"invalid {SOURCE_METADATA_FILENAME}: source/license/attribution are required"
        )
    raw_url = doc.get("license_url")
    if raw_url is not None and (
        not isinstance(raw_url, str)
        or raw_url != raw_url.strip()
        or not raw_url.startswith("https://")
    ):
        raise ValueError(f"invalid {SOURCE_METADATA_FILENAME}: license_url must use https")
    return DataTerms(
        source=str(values["source"]),
        license=str(values["license"]),
        attribution=str(values["attribution"]),
        license_url=raw_url,
    )


def _validated_provider_ledger(
    store: Path, terms: DataTerms, observations: Iterable[Observation]
) -> bytes | None:
    if terms.source.casefold() != "openaq" and not terms.license.startswith("Provider-specific"):
        return None
    from .sources import openaq

    candidate = store / SOURCE_LICENSE_LEDGER_FILENAME
    try:
        content = candidate.read_bytes()
        ledger = json.loads(content)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("provider-specific data requires source-license-ledger.json") from exc
    if not openaq.validate_license_ledger(ledger, observations=observations):
        raise ValueError("source-license-ledger.json failed validation")
    return content


def _nonempty_override(value: str | None, *, field: str, fallback: str) -> str:
    if value is None:
        return fallback
    if not value.strip():
        raise ValueError(f"data {field} override must not be empty")
    return value


def _identified_third_party_source(observations: Iterable[Observation]) -> str | None:
    """Infer source identities that are deliberately encoded in stored observations.

    This is a fail-closed backstop for a missing metadata sidecar, not a replacement for that
    sidecar. A mixed set is invalid because one blanket metadata document cannot describe it.
    """
    labels = {
        SOURCE_OPENAQ: "OpenAQ",
        SOURCE_OPENMETEO: "Copernicus CAMS via Open-Meteo",
        SOURCE_SENSOR_COMMUNITY: "Sensor.Community",
    }
    sources: set[str] = set()
    for observation in observations:
        if observation.source not in KNOWN_SOURCES:
            raise ValueError(f"unknown stored observation source identity: {observation.source}")
        if observation.source != SOURCE_NATIVE:
            sources.add(labels[observation.source])
        elif observation.node_id.startswith("oaq-"):
            sources.add("OpenAQ")
        elif observation.node_id.startswith("sc-"):
            sources.add("Sensor.Community")
        elif observation.calibration == "copernicus-cams":
            sources.add("Copernicus CAMS via Open-Meteo")
    if len(sources) > 1:
        raise ValueError("stored observations identify multiple third-party sources")
    return next(iter(sources), None)


def _canonical_builtin_terms(source: str) -> DataTerms | None:
    """Return immutable adapter claims for a built-in source label, if recognized."""
    from .sources import openaq, openmeteo, sensor_community

    canonical = (
        DataTerms("OpenAQ", openaq.LICENSE, openaq.ATTRIBUTION, openaq.LICENSE_URL),
        DataTerms(
            "Copernicus CAMS via Open-Meteo",
            openmeteo.LICENSE,
            openmeteo.ATTRIBUTION,
            openmeteo.LICENSE_URL,
        ),
        DataTerms(
            "Sensor.Community",
            sensor_community.LICENSE,
            sensor_community.ATTRIBUTION,
            sensor_community.LICENSE_URL,
        ),
    )
    matches = [terms for terms in canonical if terms.source.casefold() == source.casefold()]
    return matches[0] if matches else None


def load_data_terms(
    store: Path,
    *,
    license_override: str | None = None,
    attribution_override: str | None = None,
    observations: Iterable[Observation] = (),
) -> DataTerms:
    """Resolve terms from fetched-store metadata or the native-data default, with overrides.

    OpenAQ's deliberately non-blanket terms are usable only with a validated per-location ledger;
    a snapshot or publish fails closed rather than stripping that evidence.
    """
    store_dir = Path(store)
    observation_list = list(observations)
    metadata_path = store_dir / SOURCE_METADATA_FILENAME
    try:
        metadata_content = metadata_path.read_bytes()
    except FileNotFoundError:
        metadata_content = None
    except OSError as exc:
        raise ValueError(f"invalid {SOURCE_METADATA_FILENAME}: {exc}") from exc
    has_metadata = metadata_content is not None
    identified_source = _identified_third_party_source(observation_list)
    if identified_source is not None and not has_metadata:
        raise ValueError(
            f"{identified_source} observations require {SOURCE_METADATA_FILENAME}; "
            "CC0 cannot be assumed"
        )
    terms = (
        _read_source_metadata(metadata_content)
        if metadata_content is not None
        else DataTerms(DEFAULT_DATA_SOURCE, DEFAULT_DATA_LICENSE, DEFAULT_DATA_ATTRIBUTION)
    )
    canonical_terms = _canonical_builtin_terms(terms.source)
    if canonical_terms is not None and terms != canonical_terms:
        raise ValueError(
            f"{canonical_terms.source} metadata does not match the built-in adapter terms"
        )
    if identified_source is not None and terms.source.casefold() != identified_source.casefold():
        raise ValueError(
            f"stored observations identify {identified_source}, but source metadata names "
            f"{terms.source}"
        )
    if has_metadata and license_override is not None and license_override != terms.license:
        raise ValueError("a fetched store's recorded data license cannot be overridden")
    if (
        has_metadata
        and attribution_override is not None
        and attribution_override != terms.attribution
    ):
        raise ValueError("a fetched store's recorded attribution cannot be overridden")
    data_license = _nonempty_override(license_override, field="license", fallback=terms.license)
    attribution = _nonempty_override(
        attribution_override, field="attribution", fallback=terms.attribution
    )
    effective = DataTerms(terms.source, data_license, attribution, terms.license_url)
    ledger_content = _validated_provider_ledger(store_dir, effective, observation_list)
    return DataTerms(
        effective.source,
        effective.license,
        effective.attribution,
        effective.license_url,
        ledger_content,
        metadata_content,
    )


def export_terms_by_observation(
    terms: DataTerms, observations: Iterable[Observation]
) -> dict[export.TermsKey, dict[str, str]]:
    """Return timestamp-specific in-band terms for a provider-ledger-backed export."""
    if terms.ledger_content is None:
        return {}
    from .sources import openaq

    document = json.loads(terms.ledger_content)
    resolved: dict[export.TermsKey, dict[str, str]] = {}
    for key, value in openaq.license_terms_by_observation(document, observations).items():
        resolved[key] = value
    return resolved


def rights_envelope(
    terms: DataTerms,
    *,
    license_href: str = "/DATA-LICENSE",
    ledger_href: str = "/source-license-ledger.json",
) -> dict[str, object]:
    """Return a small, additive rights/provenance envelope for JSON and GeoJSON artifacts."""
    links: list[dict[str, str]] = [{"rel": "license", "href": license_href}]
    if terms.ledger_content is not None:
        links.append({"rel": "describedby", "href": ledger_href})
    envelope: dict[str, object] = {
        "schema_version": 1,
        "source": terms.source,
        "license": terms.license,
        "attribution": terms.attribution,
        "links": links,
    }
    if terms.license_url:
        envelope["upstream_license_url"] = terms.license_url
    return envelope


def _cff_license_fields(terms: DataTerms) -> dict[str, object]:
    """Return valid CFF 1.2 license fields without inventing one blanket OpenAQ license."""
    spdx = {
        "CC0-1.0": "CC0-1.0",
        "CC BY 4.0 (Copernicus CAMS via Open-Meteo)": "CC-BY-4.0",
        "CC-BY-4.0": "CC-BY-4.0",
    }.get(terms.license)
    if spdx:
        return {"license": spdx}
    if terms.license_url:
        return {"license-url": terms.license_url}
    return {}


def render_data_license(terms: DataTerms) -> str:
    lines = [
        "swelter data snapshot terms",
        f"Source: {terms.source}",
        f"License: {terms.license}",
        f"Attribution: {terms.attribution}",
    ]
    if terms.license_url:
        lines.append(f"License URL: {terms.license_url}")
    if terms.ledger_content is not None:
        lines.append(
            f"Per-location license and attribution evidence: {SOURCE_LICENSE_LEDGER_FILENAME}"
        )
    lines.append("swelter source code is Apache-2.0 and is not relicensed by this data notice.")
    return "\n".join(lines) + "\n"


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
    *,
    version: str,
    date_released: str,
    authors: list[dict[str, Any]],
    doi: str | None,
    terms: DataTerms,
) -> str:
    doc: dict[str, object] = {
        "cff-version": "1.2.0",
        "message": "If you use this data snapshot, please cite it using this metadata.",
        "title": f"swelter observation snapshot {version}",
        "type": "dataset",
        "authors": authors,
        "version": version,
        "date-released": date_released,
        "identifiers": [_doi_identifier(doi)],
        **_cff_license_fields(terms),
    }
    header = (
        "# Generated by `swelter snapshot` — do not hand-edit; re-run the command instead.\n"
        f"# Cites the DATA in this release ({terms.license}). For the complete terms and\n"
        "# attribution, see DATA-LICENSE and any source-license-ledger.json.\n"
        "# To cite the SOFTWARE, see the repository CITATION.cff (software, Apache-2.0).\n"
    )
    return header + yaml.safe_dump(
        doc, sort_keys=False, default_flow_style=False, allow_unicode=True
    )


def _render_citation_txt(
    *,
    version: str,
    date_released: str,
    authors: list[dict[str, Any]],
    doi: str | None,
    terms: DataTerms,
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
        f"{terms.license}. {locator}\n"
    )


def build_snapshot(
    store: Path,
    out: Path,
    version: str,
    doi: str | None,
    *,
    citation_path: Path = DEFAULT_CITATION_PATH,
    now: datetime | None = None,
    data_license: str | None = None,
    data_attribution: str | None = None,
) -> SnapshotManifest:
    """Freeze the store's raw observations, corrections, and surface into ``out/``.

    ``now`` is injectable so a caller (a test, or a reproducible-build script) can pin
    ``created_at`` and get byte-identical output across runs against an unchanged store.
    """
    store_dir = Path(store)
    out_dir = Path(out)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = store_paths(store_dir)

    with open_store(store_dir) as db:
        raw = db.read(calibration=RAW)

    terms = load_data_terms(
        store_dir,
        license_override=data_license,
        attribution_override=data_attribution,
        observations=raw,
    )

    notes: list[str] = []

    (out_dir / RAW_OBSERVATIONS_FILENAME).write_text(
        export.to_json(
            raw,
            indent=2,
            license=terms.license,
            attribution=terms.attribution,
            terms_by_observation=export_terms_by_observation(terms, raw),
        ),
        encoding="utf-8",
    )
    manifested: list[tuple[str, str]] = [
        (RAW_OBSERVATIONS_FILENAME, "immutable raw observations (calibration=raw), as JSON"),
    ]

    (out_dir / DATA_LICENSE_FILENAME).write_text(render_data_license(terms), encoding="utf-8")
    manifested.append((DATA_LICENSE_FILENAME, "source-specific data license and attribution"))
    metadata_target = out_dir / SOURCE_METADATA_FILENAME
    if terms.metadata_content is not None:
        metadata_target.write_bytes(terms.metadata_content)
        manifested.append((SOURCE_METADATA_FILENAME, "source identity, terms, and attribution"))
    else:
        metadata_target.unlink(missing_ok=True)
    ledger_target = out_dir / SOURCE_LICENSE_LEDGER_FILENAME
    if terms.ledger_content is not None:
        ledger_target.write_bytes(terms.ledger_content)
        manifested.append(
            (
                SOURCE_LICENSE_LEDGER_FILENAME,
                "per-location upstream license and attribution evidence",
            )
        )
    else:
        ledger_target.unlink(missing_ok=True)

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
        data_source=terms.source,
        data_license=terms.license,
        data_attribution=terms.attribution,
        notes=tuple(notes),
    )
    (out_dir / MANIFEST_FILENAME).write_text(
        json.dumps(manifest.to_dict(), indent=2) + "\n", encoding="utf-8"
    )

    authors = _load_citation_authors(Path(citation_path))
    date_released = created_at[:10]
    (out_dir / DATA_CITATION_FILENAME).write_text(
        _render_data_citation_cff(
            version=version,
            date_released=date_released,
            authors=authors,
            doi=doi,
            terms=terms,
        ),
        encoding="utf-8",
    )
    (out_dir / CITATION_TXT_FILENAME).write_text(
        _render_citation_txt(
            version=version,
            date_released=date_released,
            authors=authors,
            doi=doi,
            terms=terms,
        ),
        encoding="utf-8",
    )

    return manifest
