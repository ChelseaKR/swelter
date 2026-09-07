"""``swelter package`` — a snapshot rendered as a Frictionless Data Package and a DCAT record.

``swelter snapshot`` freezes a citable release. What it does not produce is a *catalog record*:
the thing a CKAN instance (``data.ca.gov``) or a Socrata portal harvests before a dataset is
findable by anyone who was not sent the link. Those portals read two well-known descriptors — a
Frictionless ``datapackage.json`` (resources, a Table Schema, licences, digests) and a DCAT
record (``dcat:Dataset`` with ``dcat:distribution``) — and this module writes both from a
snapshot that already exists.

Four rules shape it, and each of them is a way this could have published something untrue.

**The digests are the manifest's, and a snapshot that does not match its own manifest is
refused.** Every resource this package publishes is copied out of the snapshot and its SHA-256 is
compared against ``MANIFEST.json`` *before* anything is written. Re-hashing the bytes on the way
past would have been one line shorter and would have handed a tampered snapshot a clean,
portal-ready catalog record with a digest that agreed with the tampering. The refusal names the
file. A manifest listing no files is refused too, for the same reason
:func:`swelter.reproduce._check_frozen_digests` refuses one: a digest check that covers nothing
reports clean over a release whose every byte was replaced.

**A per-location source does not get an SPDX id it never had.** OpenAQ redistributes other
providers' data under terms that differ location by location (hard rule 6), so a package built
from such a snapshot sets its ``licenses`` entry to the snapshot's own licence *statement* and
points ``path`` at the retained ``source-license-ledger.json``, rather than flattening a mixed
rights position into one identifier a harvester would then republish as fact. Only the licence
strings this project can map with certainty (``CC0-1.0``, ``CC-BY-4.0``) get an SPDX ``name``.

**The Table Schema is generated from the data dictionary, and refuses to guess.** Fields come
from :func:`swelter.dictionary.build_data_dictionary`, in the exact column order
:data:`swelter.export._CSV_FIELDS` writes. A CSV column the dictionary does not describe is a
hard error, not a column emitted with an empty description: the alternative is a schema that
silently stops describing the file it claims to describe the moment the export grows a column.

**Absence stays absent, and a measured empty set stays a measurement.** The table's
``missingValues`` is ``[""]``, so a portal preview renders an unmeasured ``uncertainty`` as a gap
rather than as zero — but ``qc_flags`` overrides it to ``[]``, because an empty cell there means
QC ran and found nothing suspicious, and the table rule would have published that completed check
as an unperformed one. A snapshot whose manifest records no observation window gets no
``dct:temporal`` — not an interval with null endpoints. Without a ``--base-url`` the distributions
carry no ``dcat:accessURL``, and the record says so in ``swelter:note`` rather than inventing a
host.

Everything here is offline, stdlib-only, and free of the wall clock: ``dct:issued`` is the
snapshot's own ``created_at``, so two runs against one snapshot are byte-identical.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, cast

from . import dictionary as dictionary_module
from . import export
from .dictionary import DATA_SCHEMA_VERSION
from .reproduce import ReproduceError, observations_from_export
from .snapshot import (
    AGGREGATE_FILENAME,
    DATA_LICENSE_FILENAME,
    MANIFEST_FILENAME,
    RAW_OBSERVATIONS_FILENAME,
    SOURCE_LICENSE_LEDGER_FILENAME,
)

__all__ = [
    "DATAPACKAGE_FILENAME",
    "DCAT_FILENAME",
    "EXPORT_CSV_FILENAME",
    "PackageError",
    "PackageResult",
    "build_package",
]

DATAPACKAGE_FILENAME: Final = "datapackage.json"
DCAT_FILENAME: Final = "dcat.jsonld"
EXPORT_CSV_FILENAME: Final = "export.csv"

#: The Frictionless specification version the descriptor declares. Version 2, not the older
#: ``profile: tabular-data-package``, for one concrete reason: v2 allows ``missingValues`` per
#: field. The package needs an empty cell to mean *absent* in ``uncertainty`` and *the empty set*
#: in ``qc_flags``, and under v1 one table-wide rule has to serve both — which would publish
#: "this reading carried no spike or flatline verdict" as "nobody recorded whether it did".
_PROFILE_URL: Final = "https://datapackage.org/profiles/2.0/datapackage.json"
_TABULAR_RESOURCE_PROFILE_URL: Final = (
    "https://datapackage.org/profiles/2.0/tabulardataresource.json"
)

#: Licence strings this project can map to an SPDX identifier without interpreting anything. A
#: string absent from here is published as a statement with no ``name``, never as a guess: see the
#: per-location rule in the module docstring.
_SPDX_BY_LICENSE: Final[dict[str, str]] = {
    "CC0-1.0": "CC0-1.0",
    "CC-BY-4.0": "CC-BY-4.0",
    "CC BY 4.0 (Copernicus CAMS via Open-Meteo)": "CC-BY-4.0",
    "ODbL-1.0": "ODbL-1.0",
}

#: Frictionless Table Schema types for the dictionary's own type vocabulary. ``array`` is
#: deliberately absent: the JSON export writes ``qc_flags`` as an array and the CSV writes the
#: same field as a space-joined string, so the CSV's Table Schema must say ``string`` (see
#: :data:`_CSV_TYPE_OVERRIDES`) rather than promising a reader an array that is not in the file.
_FRICTIONLESS_TYPE: Final[dict[str, str]] = {
    "string": "string",
    "number": "number",
    "boolean": "boolean",
    "integer": "integer",
}

#: Where the CSV's shape genuinely differs from the observation field's shape, with the reason.
_CSV_TYPE_OVERRIDES: Final[dict[str, tuple[str, str]]] = {
    "qc_flags": (
        "string",
        "Space-separated QC verdicts ('spike', 'flatline'), empty when the reading carried none. "
        "The JSON representation of this same field is an array; a CSV cell is a scalar, so the "
        "array is flattened here and a consumer must split on whitespace rather than parse JSON. "
        "An empty cell in this column is the empty set of verdicts — a measured result — and not "
        "a missing value, which is why this field overrides the table's missingValues.",
    ),
}

#: Fields where an empty cell is a *value*, not an absence, and the table-wide ``missingValues``
#: must therefore not apply. ``qc_flags`` is written for every row: blank means "QC ran and found
#: nothing suspicious". Letting the table rule reach it would publish a completed check as an
#: unperformed one — the same class of error as a failed read counted as a zero, pointing the
#: other way.
_FIELD_MISSING_VALUES: Final[dict[str, list[str]]] = {"qc_flags": []}

#: The two provenance columns ``export.to_csv`` writes that are not observation fields. They are
#: described here rather than in the data dictionary because they are a property of the *export*
#: (the terms under which these rows were released), not of the measurement. Every other CSV
#: column must resolve against the dictionary or :func:`_table_schema` refuses.
_EXPORT_ONLY_COLUMNS: Final[dict[str, dict[str, object]]] = {
    "data_license": {
        "type": "string",
        "description": (
            "The licence this row is released under. Repeated per row so an extracted subset "
            "stays self-describing; for a per-location source it may differ between rows, which "
            "is why it is a column and not a single package-level identifier."
        ),
        "required": True,
    },
    "data_attribution": {
        "type": "string",
        "description": (
            "The attribution statement that must travel with this row. May be empty when the "
            "source records none."
        ),
        "required": False,
    },
}

#: What ``dct:conformsTo`` points a harvester at. Deliberately the document that *defines* what a
#: data-schema version means and what moving it implies, rather than a heading anchor inside the
#: API reference: an anchor is generated from a heading's text and silently stops resolving when
#: the heading is reworded, which would leave the record pointing at a page rather than a
#: definition without anything failing. The version integer itself travels beside it in
#: ``swelter:data_schema_version``, where it can be read without parsing a URL.
_SCHEMA_DOC_URL: Final = "https://github.com/ChelseaKR/swelter/blob/main/docs/VERSIONING.md"

_JSONLD_CONTEXT: Final[dict[str, str]] = {
    "dcat": "http://www.w3.org/ns/dcat#",
    "dct": "http://purl.org/dc/terms/",
    "spdx": "http://spdx.org/rdf/terms#",
    "swelter": "https://github.com/ChelseaKR/swelter/ns#",
}


class PackageError(Exception):
    """A snapshot that cannot honestly be packaged — refused, never worked around."""


@dataclass(frozen=True)
class PackageResult:
    """What :func:`build_package` wrote, for the CLI to report without re-reading the directory."""

    out_dir: Path
    resources: tuple[str, ...]
    record_count: int
    notes: tuple[str, ...]


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_manifest(snapshot_dir: Path) -> dict[str, Any]:
    path = snapshot_dir / MANIFEST_FILENAME
    try:
        doc = json.loads(path.read_bytes().decode("utf-8"))
    except FileNotFoundError as exc:
        raise PackageError(f"{path} not found — this is not a swelter snapshot") from exc
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PackageError(f"{path} is not readable JSON: {exc}") from exc
    if not isinstance(doc, dict):
        raise PackageError(f"{path} is not a JSON object")
    return doc


def _manifest_digests(doc: dict[str, Any]) -> dict[str, str]:
    """``name`` → recorded SHA-256, refusing a manifest that records nothing to check against.

    An empty or malformed ``files`` list is a failure rather than an empty mapping: every
    verification below is a lookup into this dictionary, so an empty one would make each of them
    pass over a file it had never seen. That is the same shape as a coverage glob matching no
    files, and it is refused here for the same reason.
    """
    entries = doc.get("files")
    if not isinstance(entries, list) or not entries:
        raise PackageError(
            f"{MANIFEST_FILENAME} lists no files — a package built from it would carry digests "
            "nothing had verified"
        )
    digests: dict[str, str] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise PackageError(f"{MANIFEST_FILENAME} has a malformed file entry")
        name, recorded = entry.get("name"), entry.get("sha256")
        if not isinstance(name, str) or not isinstance(recorded, str):
            raise PackageError(f"{MANIFEST_FILENAME} has a file entry with no name or digest")
        digests[name] = recorded
    return digests


def _verified_bytes(snapshot_dir: Path, name: str, digests: dict[str, str]) -> bytes:
    """The file's bytes, or a refusal naming it — never bytes whose digest was not checked."""
    recorded = digests.get(name)
    if recorded is None:
        raise PackageError(
            f"{name} is present in the snapshot but not recorded in {MANIFEST_FILENAME}; "
            "an unmanifested file is not publishable evidence"
        )
    try:
        payload = (snapshot_dir / name).read_bytes()
    except OSError as exc:
        raise PackageError(
            f"{name} is recorded in {MANIFEST_FILENAME} but unreadable: {exc}"
        ) from exc
    actual = _sha256(payload)
    if actual != recorded:
        raise PackageError(
            f"{name} does not match the SHA-256 recorded in {MANIFEST_FILENAME} "
            f"({actual[:12]}… vs {recorded[:12]}…); refusing to publish a catalog record over it"
        )
    return payload


def _with_field_missing_values(field: dict[str, object]) -> dict[str, object]:
    """Attach a field-level ``missingValues`` override where an empty cell is a real value."""
    override = _FIELD_MISSING_VALUES.get(str(field["name"]))
    if override is not None:
        field["missingValues"] = list(override)
    return field


def _table_schema() -> dict[str, object]:
    """A Frictionless Table Schema for ``export.csv``, generated from the data dictionary.

    Column order is :data:`swelter.export._CSV_FIELDS` as published in the dictionary's
    ``csv_columns``, so the schema and the file it describes cannot disagree about order. A column
    with no described field raises: a Table Schema that quietly omitted a column would tell a
    portal the file has fewer columns than it has, and a portal that trusts it would misparse
    every row after the missing one.
    """
    dictionary = dictionary_module.build_data_dictionary()
    observation_fields = cast("list[dict[str, object]]", dictionary["observation_fields"])
    csv_columns = cast("list[str]", dictionary["csv_columns"])
    described = {str(field["name"]): field for field in observation_fields}
    fields: list[dict[str, object]] = []
    for column in csv_columns:
        name = str(column)
        provenance = _EXPORT_ONLY_COLUMNS.get(name)
        if provenance is not None:
            fields.append(
                _with_field_missing_values(
                    {
                        "name": name,
                        "type": provenance["type"],
                        "description": provenance["description"],
                        "constraints": {"required": provenance["required"]},
                    }
                )
            )
            continue
        source = described.get(name)
        if source is None:
            raise PackageError(
                f"CSV column {name!r} is described neither by the data dictionary nor as an "
                "export-only provenance column; refusing to emit a Table Schema that does not "
                "describe the file it names"
            )
        override = _CSV_TYPE_OVERRIDES.get(name)
        if override is not None:
            field_type, description = override
        else:
            declared = str(source["type"])
            resolved = _FRICTIONLESS_TYPE.get(declared)
            if resolved is None:
                raise PackageError(
                    f"CSV column {name!r} has dictionary type {declared!r}, which has no "
                    "Frictionless equivalent in this writer"
                )
            field_type, description = resolved, str(source["description"])
        constraints: dict[str, object] = {"required": not bool(source["nullable"])}
        enum = source.get("enum")
        if enum is not None and override is None:
            constraints["enum"] = list(cast("list[str]", enum))
        field: dict[str, object] = {
            "name": name,
            "type": field_type,
            "description": description,
            "constraints": constraints,
        }
        unit = source.get("unit")
        if unit:
            field["unit"] = str(unit)
        fields.append(_with_field_missing_values(field))
    return {
        "fields": fields,
        # An empty cell is an absent measurement, not a zero. Without this a portal preview reads
        # a blank `uncertainty` as 0 and renders a raw reading as a perfectly precise one.
        "missingValues": [""],
    }


def _licenses(manifest: dict[str, Any], *, has_ledger: bool) -> list[dict[str, object]]:
    """The package's ``licenses`` array — an SPDX id only where one is certain."""
    statement = str(manifest.get("data_license", "")).strip()
    if not statement:
        raise PackageError(
            f"{MANIFEST_FILENAME} records no data_license; a package without terms is not "
            "publishable"
        )
    entry: dict[str, object] = {"title": statement}
    spdx = _SPDX_BY_LICENSE.get(statement)
    if spdx is not None:
        entry["name"] = spdx
    if has_ledger:
        # A per-location source has no single licence. `path` sends a harvester to the retained
        # per-location evidence instead of letting `title` be read as one blanket grant.
        entry["path"] = SOURCE_LICENSE_LEDGER_FILENAME
    return [entry]


def _temporal(manifest: dict[str, Any]) -> dict[str, str] | None:
    window = manifest.get("observation_window")
    if not isinstance(window, dict):
        return None
    start, end = window.get("start"), window.get("end")
    if not isinstance(start, str) or not isinstance(end, str) or not start or not end:
        return None
    return {"start": start, "end": end}


def _distribution(
    resource: dict[str, object], *, base_url: str | None, dataset_id: str
) -> dict[str, object]:
    name = str(resource["path"])
    entry: dict[str, object] = {
        "@type": "dcat:Distribution",
        "@id": f"{dataset_id}#{name}",
        "dct:title": str(resource["title"]),
        "dcat:mediaType": str(resource["mediatype"]),
        "dcat:byteSize": resource["bytes"],
        "spdx:checksum": {
            "@type": "spdx:Checksum",
            "spdx:algorithm": "spdx:checksumAlgorithm_sha256",
            "spdx:checksumValue": str(resource["hash"]).removeprefix("sha256:"),
        },
    }
    if base_url is not None:
        entry["dcat:accessURL"] = f"{base_url.rstrip('/')}/{name}"
        entry["dcat:downloadURL"] = f"{base_url.rstrip('/')}/{name}"
    return entry


def _dcat_record(
    manifest: dict[str, Any],
    resources: list[dict[str, object]],
    *,
    base_url: str | None,
    licenses: list[dict[str, object]],
    notes: list[str],
) -> dict[str, object]:
    release = str(manifest.get("release_version", ""))
    doi = manifest.get("doi")
    dataset_id = f"urn:swelter:snapshot:{release}" if release else "urn:swelter:snapshot"
    title = f"{manifest.get('data_source', 'swelter')} — {release}".strip(" —")
    record: dict[str, object] = {
        "@context": dict(_JSONLD_CONTEXT),
        "@id": dataset_id,
        "@type": "dcat:Dataset",
        "dct:identifier": str(doi) if isinstance(doi, str) and doi else dataset_id,
        # Tagged `en` rather than published untagged: the record deliberately carries no Spanish
        # title or description, because it has no independently reviewed Spanish text (issue #106)
        # and a portal republishes a harvested title as the dataset's own name. An untagged
        # string would let a Spanish-language portal present English prose as its translation.
        "dct:title": {"@value": title, "@language": "en"},
        "dct:description": {
            "@value": (
                f"{manifest.get('record_count', 0)} immutable raw observations from a "
                f"community-operated swelter heat and air-quality network, with the calibration "
                f"corrections fitted against them and the gridded surface derived from them. "
                f"Source: {manifest.get('data_source', 'unknown')}. "
                f"Terms: {manifest.get('data_license', 'unknown')}."
            ),
            "@language": "en",
        },
        "dct:issued": str(manifest.get("created_at", "")),
        "dct:conformsTo": _SCHEMA_DOC_URL,
        "swelter:data_schema_version": manifest.get("data_schema_version", DATA_SCHEMA_VERSION),
        "dct:license": licenses[0].get("name", licenses[0]["title"]),
        "dct:publisher": {"@type": "dct:Agent", "dct:title": str(manifest.get("data_source", ""))},
        "dcat:distribution": [
            _distribution(resource, base_url=base_url, dataset_id=dataset_id)
            for resource in resources
        ],
    }
    temporal = _temporal(manifest)
    if temporal is not None:
        record["dct:temporal"] = {
            "@type": "dct:PeriodOfTime",
            "dcat:startDate": temporal["start"],
            "dcat:endDate": temporal["end"],
        }
    if notes:
        record["swelter:note"] = list(notes)
    return record


@dataclass(frozen=True)
class _VerifiedInputs:
    """Every snapshot file this package republishes, already checked against the manifest.

    Held as bytes rather than paths for the same reason :class:`swelter.snapshot.DataTerms` holds
    its ledger as bytes: a path would reopen a time-of-check/time-of-use gap between the digest
    verification and the copy.
    """

    raw: bytes
    license_text: bytes
    aggregate: bytes | None
    ledger: bytes | None

    def copies(self) -> list[tuple[str, bytes]]:
        """The snapshot files to write into the package directory, verified copies only."""
        out: list[tuple[str, bytes]] = [
            (RAW_OBSERVATIONS_FILENAME, self.raw),
            (DATA_LICENSE_FILENAME, self.license_text),
        ]
        if self.aggregate is not None:
            out.append((AGGREGATE_FILENAME, self.aggregate))
        if self.ledger is not None:
            out.append((SOURCE_LICENSE_LEDGER_FILENAME, self.ledger))
        return out


def _verified_inputs(snapshot_dir: Path, digests: dict[str, str]) -> _VerifiedInputs:
    """Read and verify every file the package will carry, before anything is written."""
    if not (snapshot_dir / DATA_LICENSE_FILENAME).is_file():
        raise PackageError(
            f"{snapshot_dir / DATA_LICENSE_FILENAME} is missing; a snapshot with no recorded "
            "terms cannot be published to a catalog"
        )
    return _VerifiedInputs(
        raw=_verified_bytes(snapshot_dir, RAW_OBSERVATIONS_FILENAME, digests),
        license_text=_verified_bytes(snapshot_dir, DATA_LICENSE_FILENAME, digests),
        aggregate=(
            _verified_bytes(snapshot_dir, AGGREGATE_FILENAME, digests)
            if AGGREGATE_FILENAME in digests
            else None
        ),
        ledger=(
            _verified_bytes(snapshot_dir, SOURCE_LICENSE_LEDGER_FILENAME, digests)
            if SOURCE_LICENSE_LEDGER_FILENAME in digests
            else None
        ),
    )


def _notes(*, base_url: str | None, has_surface: bool) -> list[str]:
    """What this package does not carry, said out loud rather than left to be inferred."""
    notes: list[str] = []
    if base_url is None:
        notes.append(
            "no --base-url was given, so no distribution carries an access URL; a harvester must "
            "be pointed at this directory out of band"
        )
    if not has_surface:
        notes.append(
            f"the snapshot records no {AGGREGATE_FILENAME}, so this package publishes the raw "
            "observations without the gridded surface derived from them"
        )
    return notes


def _resource(
    *, name: str, path: str, title: str, mediatype: str, payload: bytes, fmt: str
) -> dict[str, object]:
    return {
        "name": name,
        "path": path,
        "title": title,
        "format": fmt,
        "mediatype": mediatype,
        "encoding": "utf-8",
        "bytes": len(payload),
        "hash": f"sha256:{_sha256(payload)}",
    }


def _resources(inputs: _VerifiedInputs, csv_bytes: bytes) -> list[dict[str, object]]:
    """The package's resource list, digests computed over the exact bytes just written."""
    tabular = _resource(
        name="observations-csv",
        path=EXPORT_CSV_FILENAME,
        title="Immutable raw observations (tabular)",
        mediatype="text/csv",
        payload=csv_bytes,
        fmt="csv",
    )
    tabular["$schema"] = _TABULAR_RESOURCE_PROFILE_URL
    tabular["dialect"] = {"delimiter": ",", "header": True}
    tabular["schema"] = _table_schema()
    resources = [
        tabular,
        _resource(
            name="observations-json",
            path=RAW_OBSERVATIONS_FILENAME,
            title="Immutable raw observations with their rights envelope (JSON)",
            mediatype="application/json",
            payload=inputs.raw,
            fmt="json",
        ),
        _resource(
            name="data-license",
            path=DATA_LICENSE_FILENAME,
            title="Source-specific terms and attribution for these observations",
            mediatype="text/plain",
            payload=inputs.license_text,
            fmt="txt",
        ),
    ]
    if inputs.aggregate is not None:
        resources.append(
            _resource(
                name="surface-geojson",
                path=AGGREGATE_FILENAME,
                title="Gridded heat and air-quality surface, latest cell-hour per cell",
                mediatype="application/geo+json",
                payload=inputs.aggregate,
                fmt="geojson",
            )
        )
    if inputs.ledger is not None:
        resources.append(
            _resource(
                name="source-license-ledger",
                path=SOURCE_LICENSE_LEDGER_FILENAME,
                title="Per-location upstream licence and attribution evidence",
                mediatype="application/json",
                payload=inputs.ledger,
                fmt="json",
            )
        )
    return resources


def _descriptor(
    manifest: dict[str, Any],
    resources: list[dict[str, object]],
    *,
    licenses: list[dict[str, object]],
    notes: list[str],
) -> dict[str, object]:
    """The Frictionless ``datapackage.json`` document."""
    release = str(manifest.get("release_version", ""))
    descriptor: dict[str, object] = {
        "$schema": _PROFILE_URL,
        "name": f"swelter-snapshot-{release}" if release else "swelter-snapshot",
        "title": f"{manifest.get('data_source', 'swelter')} — {release}".strip(" —"),
        "description": (
            "A frozen swelter data release: immutable raw observations, their rights envelope, "
            "and the gridded surface derived from them. Digests are the snapshot manifest's own."
        ),
        "created": str(manifest.get("created_at", "")),
        "version": release,
        "licenses": licenses,
        "sources": [{"title": str(manifest.get("data_source", ""))}],
        "contributors": [
            {"title": str(manifest.get("data_attribution", "")), "role": "contributor"}
        ],
        "swelter:data_schema_version": manifest.get("data_schema_version", DATA_SCHEMA_VERSION),
        "swelter:swelter_version": manifest.get("swelter_version"),
        "resources": resources,
    }
    temporal = _temporal(manifest)
    if temporal is not None:
        descriptor["temporal"] = temporal
    doi = manifest.get("doi")
    if isinstance(doi, str) and doi:
        descriptor["id"] = doi
    if notes:
        descriptor["swelter:notes"] = list(notes)
    return descriptor


def build_package(
    snapshot_dir: Path,
    out: Path,
    *,
    base_url: str | None = None,
) -> PackageResult:
    """Write a self-contained Frictionless package and DCAT record for ``snapshot_dir``.

    The output directory is self-contained on purpose. A portal harvests a directory, and
    Frictionless resource paths may not escape the package root, so the snapshot's data files are
    copied in rather than referenced with ``../``. Every copy is verified against the snapshot's
    own ``MANIFEST.json`` before it is written, so the duplication carries the release's integrity
    claim with it instead of quietly starting a second, unverified copy of the data.
    """
    snapshot_dir = Path(snapshot_dir)
    out_dir = Path(out)
    manifest = _read_manifest(snapshot_dir)
    digests = _manifest_digests(manifest)
    inputs = _verified_inputs(snapshot_dir, digests)

    try:
        observations = observations_from_export(inputs.raw)
    except ReproduceError as exc:
        raise PackageError(f"{RAW_OBSERVATIONS_FILENAME} cannot be tabulated: {exc}") from exc

    csv_bytes = export.to_csv(
        observations,
        license=str(manifest.get("data_license", "")) or None,
        attribution=str(manifest.get("data_attribution", "")),
    ).encode("utf-8")

    notes = _notes(base_url=base_url, has_surface=inputs.aggregate is not None)

    out_dir.mkdir(parents=True, exist_ok=True)
    for name, payload in [(EXPORT_CSV_FILENAME, csv_bytes), *inputs.copies()]:
        (out_dir / name).write_bytes(payload)

    resources = _resources(inputs, csv_bytes)
    licenses = _licenses(manifest, has_ledger=inputs.ledger is not None)
    descriptor = _descriptor(manifest, resources, licenses=licenses, notes=notes)

    (out_dir / DATAPACKAGE_FILENAME).write_text(
        json.dumps(descriptor, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (out_dir / DCAT_FILENAME).write_text(
        json.dumps(
            _dcat_record(manifest, resources, base_url=base_url, licenses=licenses, notes=notes),
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    return PackageResult(
        out_dir=out_dir,
        resources=tuple(str(resource["path"]) for resource in resources),
        record_count=len(observations),
        notes=tuple(notes),
    )
