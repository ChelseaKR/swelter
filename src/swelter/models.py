"""Core data model: immutable observations, the parameter registry, AQI, integrity hashing.

Everything downstream — ingest, QC, calibration, aggregation, export — speaks in
`Observation` records. Observations are long-format (one parameter per record), which is
what the OGC SensorThings model and the CSV export both want, and what lets a value carry
its *own* calibration provenance and uncertainty rather than inheriting a row's.

Three invariants live here because the rest of the system relies on them:

* An observation is immutable (a frozen dataclass) and content-addressable
  (`content_hash`), so the store can be append-only and an edit is a new record.
* `calibration` is never empty: it is either ``RAW`` or a correction version id. The map
  and the export can therefore always tell calibrated from raw — they never have to guess.
* The schema has no field that can hold a person. There is no device id, no MAC, no owner,
  no precise coordinate; node location lives in config and is snapped before publication.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Final

#: Calibration sentinel for an uncorrected reading.
RAW: Final = "raw"


@dataclass(frozen=True)
class Parameter:
    """A measurable quantity and the physically plausible range QC holds it to."""

    name: str
    unit: str
    valid_min: float
    valid_max: float


#: The full set of quantities a node may report. Adding a parameter is a one-line change
#: here plus a calibration model; nothing else in the pipeline is parameter-specific.
PARAMETERS: Final[dict[str, Parameter]] = {
    "temp_c": Parameter("temp_c", "degC", -40.0, 60.0),
    "humidity_pct": Parameter("humidity_pct", "%", 0.0, 100.0),
    "pm25_ugm3": Parameter("pm25_ugm3", "ug/m3", 0.0, 1000.0),
    "pm10_ugm3": Parameter("pm10_ugm3", "ug/m3", 0.0, 2000.0),
    "no2_ppb": Parameter("no2_ppb", "ppb", 0.0, 2000.0),
    "heat_index_c": Parameter("heat_index_c", "degC", -40.0, 60.0),  # ~137 °F NWS ceiling
}

# QC verdicts. A reading is published with exactly one of these, never silently dropped.
QC_OK: Final = "ok"
QC_RANGE: Final = "range"
QC_SPIKE: Final = "spike"
QC_FLATLINE: Final = "flatline"
QC_MISSING: Final = "missing"

#: QC verdicts that mean "do not trust this value as a measurement".
QC_REJECTED: Final[frozenset[str]] = frozenset({QC_RANGE, QC_SPIKE, QC_FLATLINE, QC_MISSING})

ISO_FORMAT: Final = "%Y-%m-%dT%H:%M:%SZ"


@dataclass(frozen=True)
class Observation:
    """One measurement of one parameter by one node at one instant.

    Frozen on purpose: observations are written once and never mutated. ``with_qc`` and
    ``calibrated`` return new records, so provenance is additive and auditable.
    """

    node_id: str
    timestamp: str  # ISO 8601, UTC, e.g. "2026-06-01T00:00:00Z"
    parameter: str
    value: float
    unit: str
    calibration: str = RAW
    qc: str = QC_OK
    uncertainty: float | None = None  # 1-sigma in `unit`, set when calibrated

    def key(self) -> tuple[str, str, str, str]:
        """Identity for idempotent storage: same key ⇒ same logical observation."""
        return (self.node_id, self.timestamp, self.parameter, self.calibration)

    def content_hash(self) -> str:
        """Stable SHA-256 over the value-bearing fields, for integrity (dedup is key-based)."""
        payload = json.dumps(
            [
                self.node_id,
                self.timestamp,
                self.parameter,
                self.value,
                self.unit,
                self.calibration,
                self.qc,
                self.uncertainty,
            ],
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @property
    def is_calibrated(self) -> bool:
        return self.calibration != RAW

    @property
    def is_trustworthy(self) -> bool:
        """Calibrated and not QC-rejected. The map shows everything else as provisional."""
        return self.is_calibrated and self.qc not in QC_REJECTED

    def with_qc(self, flag: str) -> Observation:
        return replace(self, qc=flag)

    def calibrated(self, version: str, value: float, uncertainty: float) -> Observation:
        """Return a new, corrected observation tagged with the correction version."""
        return replace(self, value=value, calibration=version, uncertainty=uncertainty)


def parse_timestamp(value: str) -> datetime:
    """Parse an ISO-8601 UTC timestamp (``...Z``) into an aware ``datetime``."""
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def format_timestamp(dt: datetime) -> str:
    """Render an aware ``datetime`` as canonical ``YYYY-MM-DDTHH:MM:SSZ``."""
    return dt.astimezone(UTC).strftime(ISO_FORMAT)


# US EPA PM2.5 AQI breakpoints (2024 revision), 24-hour averages, micrograms per cubic
# metre. Each tuple is (concentration low, concentration high, AQI low, AQI high, category).
_PM25_AQI: Final[tuple[tuple[float, float, int, int, str], ...]] = (
    (0.0, 9.0, 0, 50, "Good"),
    (9.1, 35.4, 51, 100, "Moderate"),
    (35.5, 55.4, 101, 150, "Unhealthy for Sensitive Groups"),
    (55.5, 125.4, 151, 200, "Unhealthy"),
    (125.5, 225.4, 201, 300, "Very Unhealthy"),
    (225.5, 325.4, 301, 500, "Hazardous"),
)


def pm25_aqi(concentration: float) -> tuple[int, str]:
    """Convert a PM2.5 concentration to an integer AQI value and its category name.

    Follows the EPA convention of truncating the concentration to one decimal place before the
    breakpoint lookup, so the value always lands exactly on a breakpoint — the EPA table has
    intentional gaps between bands (…9.0 then 9.1…), and scanning a raw float would fall into a
    gap and wrongly report the top of the scale. Negatives clamp to 0/"Good"; values above the
    top band clamp to 500/"Hazardous". NaN is rejected: a missing reading must never masquerade
    as a measurement.
    """
    if math.isnan(concentration):
        raise ValueError("PM2.5 concentration is NaN")
    if concentration <= 0:
        return 0, "Good"
    c = math.floor(concentration * 10) / 10  # EPA: truncate to 0.1 ug/m3 before the lookup
    for c_lo, c_hi, a_lo, a_hi, label in _PM25_AQI:
        if c_lo <= c <= c_hi:
            aqi = (a_hi - a_lo) / (c_hi - c_lo) * (c - c_lo) + a_lo
            return round(aqi), label
    return 500, "Hazardous"


def heat_index_c(temp_c: float, humidity_pct: float) -> float:
    """NWS heat index (Rothfusz regression), Celsius in and out.

    Below 26.7 °C the regression is not meaningful, so the air temperature is returned
    unchanged. Used by the demo generator and as a fallback when a node does not report an
    on-device heat index.
    """
    if temp_c < 26.7:
        return round(temp_c, 2)
    t = temp_c * 9 / 5 + 32  # the regression is defined in Fahrenheit
    r = humidity_pct
    hi = (
        -42.379
        + 2.04901523 * t
        + 10.14333127 * r
        - 0.22475541 * t * r
        - 0.00683783 * t * t
        - 0.05481717 * r * r
        + 0.00122874 * t * t * r
        + 0.00085282 * t * r * r
        - 0.00000199 * t * t * r * r
    )
    return round((hi - 32) * 5 / 9, 2)
