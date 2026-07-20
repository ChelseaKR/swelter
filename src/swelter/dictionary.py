"""Machine-readable data dictionary + the data-schema version signal.

Everything here is *derived*, never restated: the parameter list comes from
:data:`swelter.models.PARAMETERS`, the QC verdicts from the ``QC_*`` constants in
:mod:`swelter.models`, and the CSV column order from :data:`swelter.export._CSV_FIELDS`. There is
exactly one source of truth for each of those; this module only describes it. That is what lets
:data:`DATA_SCHEMA_VERSION` be a promise an integrator can pin against — the dictionary the
running code serves can never drift from the running code's actual shape, because it is built
from the same constants, not a hand-maintained copy of them.

See ``docs/VERSIONING.md`` ("Data schema — what counts as breaking") for what changes require
bumping :data:`DATA_SCHEMA_VERSION`, and ``docs/api.md`` for the served ``/api/schema.json``
endpoint this module backs.
"""

from __future__ import annotations

from . import __version__
from .export import _CSV_FIELDS
from .models import (
    KNOWN_SOURCES,
    PARAMETERS,
    QC_FLATLINE,
    QC_MISSING,
    QC_OK,
    QC_RANGE,
    QC_REJECTED,
    QC_SPIKE,
    RAW,
)

#: The data schema's own format version — independent of the package's semver. Bump this,
#: following the "Data schema — what counts as breaking" rules in ``docs/VERSIONING.md``, whenever
#: an observation field, the CSV column set/order, or a QC verdict's meaning changes in a way that
#: rule marks breaking. Start at 1.
DATA_SCHEMA_VERSION: int = 1

_UNRESOLVED_DATA_SOURCE = "Source-specific; resolve from the serving store."
_UNRESOLVED_DATA_LICENSE = "Source-specific; see the serving store's rights envelope."

#: Every QC verdict, in the order the pipeline can produce it, paired with a human note. Kept as a
#: tuple of (name, description) so :func:`build_data_dictionary` can compute the `rejected` flag
#: from the single source of truth (`QC_REJECTED`) rather than restating it per entry.
_QC_VERDICTS: tuple[tuple[str, str], ...] = (
    (QC_OK, "The reading passed every QC check: in-range, not a spike, not a flatline."),
    (QC_RANGE, "The value fell outside the parameter's physically plausible range."),
    (QC_SPIKE, "The value jumped implausibly relative to the node's recent readings."),
    (QC_FLATLINE, "The node reported an implausibly constant value for too long."),
    (QC_MISSING, "An expected reading was absent for the interval (a gap, not a bad value)."),
)

#: Field-by-field description of :class:`swelter.models.Observation`, drawn from its docstring and
#: from ``docs/VERSIONING.md``'s "Observation fields" section. Order matches the dataclass.
_OBSERVATION_FIELDS: tuple[dict[str, object], ...] = (
    {
        "name": "node_id",
        "type": "string",
        "unit": None,
        "nullable": False,
        "description": (
            "The reporting node's public identifier. Not a MAC, not a device serial, not a "
            "person — the schema has no field that can hold one (see ADR: no-identifier rule)."
        ),
    },
    {
        "name": "timestamp",
        "type": "string",
        "unit": "ISO-8601 UTC (YYYY-MM-DDTHH:MM:SSZ)",
        "nullable": False,
        "description": "The instant of the measurement, always UTC and always the ...Z form.",
    },
    {
        "name": "parameter",
        "type": "string",
        "unit": None,
        "nullable": False,
        "description": "The measured quantity's key into PARAMETERS, e.g. 'pm25_ugm3'.",
    },
    {
        "name": "value",
        "type": "number",
        "unit": "the parameter's unit",
        "nullable": False,
        "description": "The measurement itself, in the parameter's unit. Never NaN/Infinity.",
    },
    {
        "name": "unit",
        "type": "string",
        "unit": None,
        "nullable": False,
        "description": "The unit `value` is expressed in (matches the parameter's registered unit)",
    },
    {
        "name": "source",
        "type": "string",
        "unit": None,
        "nullable": False,
        "enum": sorted(KNOWN_SOURCES),
        "description": (
            "The observation's origin identity. Source-specific license and attribution terms "
            "must be resolved from the representation's rights envelope."
        ),
    },
    {
        "name": "calibration",
        "type": "string",
        "unit": None,
        "nullable": False,
        "description": (
            f"Calibration provenance. Never empty: it is either the RAW sentinel ({RAW!r}, an "
            "uncorrected reading) or a correction version id of the form "
            "'{parameter}.{method}.{node_id}' (a corrected reading). This is how a consumer "
            "always tells calibrated from raw without guessing."
        ),
    },
    {
        "name": "qc",
        "type": "string",
        "unit": None,
        "nullable": False,
        "description": "One of the qc_verdicts entries below. Never silently dropped.",
    },
    {
        "name": "uncertainty",
        "type": "number",
        "unit": "1-sigma, in the parameter's unit",
        "nullable": True,
        "description": "Set when calibrated; null on a raw (uncorrected) reading.",
    },
    {
        "name": "trustworthy",
        "type": "boolean",
        "unit": None,
        "nullable": False,
        "description": (
            "Derived, not stored: calibrated AND not QC-rejected. Exported/served explicitly so "
            "a downloader needn't infer trust from the calibration string. See qc_verdicts for "
            "which verdicts count as rejected."
        ),
    },
)


def _parameters() -> list[dict[str, object]]:
    return [
        {
            "name": p.name,
            "unit": p.unit,
            "valid_min": p.valid_min,
            "valid_max": p.valid_max,
        }
        for p in PARAMETERS.values()
    ]


def _qc_verdicts() -> list[dict[str, object]]:
    return [
        {"name": name, "description": description, "rejected": name in QC_REJECTED}
        for name, description in _QC_VERDICTS
    ]


def build_data_dictionary(
    *,
    data_source: str | None = None,
    data_license: str | None = None,
    data_attribution: str | None = None,
    data_license_url: str | None = None,
) -> dict[str, object]:
    """Assemble the published data dictionary from the running code's own source-of-truth constants.

    Every list here is generated, never hand-copied, so it cannot drift from the pipeline it
    describes: `parameters` from `models.PARAMETERS`, `qc_verdicts` from the `QC_*` constants,
    and `csv_columns` from `export._CSV_FIELDS` (the exact list `export.to_csv` writes).
    """
    document: dict[str, object] = {
        "data_schema_version": DATA_SCHEMA_VERSION,
        "package_version": __version__,
        "generated_from": "swelter",
        "data_source": data_source or _UNRESOLVED_DATA_SOURCE,
        "license": data_license or _UNRESOLVED_DATA_LICENSE,
        "observation_fields": [dict(field) for field in _OBSERVATION_FIELDS],
        "csv_columns": list(_CSV_FIELDS),
        "parameters": _parameters(),
        "qc_verdicts": _qc_verdicts(),
        "calibration": {
            "raw_sentinel": RAW,
            "correction_version_format": "{parameter}.{method}.{node_id}",
            "description": (
                "A value's `calibration` field is either the raw sentinel above (uncorrected) "
                "or a correction version id in the format shown — the map and export can "
                "therefore always tell calibrated from raw without guessing."
            ),
        },
    }
    if data_attribution is not None:
        document["attribution"] = data_attribution
    if data_license_url is not None:
        document["license_url"] = data_license_url
    return document
