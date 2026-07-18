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
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Final

#: Calibration sentinel for an uncorrected reading.
RAW: Final = "raw"
SOURCE_NATIVE: Final = "native"
SOURCE_OPENAQ: Final = "openaq"
SOURCE_OPENMETEO: Final = "openmeteo"
SOURCE_SENSOR_COMMUNITY: Final = "sensor-community"
KNOWN_SOURCES: Final[frozenset[str]] = frozenset(
    {SOURCE_NATIVE, SOURCE_OPENAQ, SOURCE_OPENMETEO, SOURCE_SENSOR_COMMUNITY}
)


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
    "wbgt_c": Parameter("wbgt_c", "degC", -40.0, 60.0),
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
    source: str = SOURCE_NATIVE
    calibration: str = RAW
    qc: str = QC_OK
    uncertainty: float | None = None  # 1-sigma in `unit`, set when calibrated

    def key(self) -> tuple[str, str, str, str, str]:
        """Identity for idempotent storage: same key ⇒ same logical observation."""
        return (self.node_id, self.timestamp, self.parameter, self.source, self.calibration)

    def content_hash(self) -> str:
        """Stable SHA-256 over the value-bearing fields, for integrity (dedup is key-based)."""
        payload = json.dumps(
            [
                self.node_id,
                self.timestamp,
                self.parameter,
                self.value,
                self.unit,
                self.source,
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


def nowcast_concentration(concentrations: Sequence[float]) -> float | None:
    """EPA NowCast-weighted PM2.5 concentration from trailing hourly means.

    ``concentrations`` is **most-recent-first** (index 0 = the current hour); only the leading 12
    entries are used (EPA's NowCast window), and at least 3 are required — fewer is too noisy to
    publish, so this returns ``None`` rather than a shaky estimate. The weight ``w = max(c_min /
    c_max, 0.5)`` is the range ratio over the window, floored at 0.5 so a single old low reading
    can't collapse the trend to noise; the NowCast is the w-weighted average
    ``sum(w**i * c_i) / sum(w**i)`` for ``i`` counted in hours-ago from the most recent reading
    (``i = 0``), so older hours are discounted relative to the current one.

    See EPA/AirNow's "Technical Assistance Document for the Reporting of Daily Air Quality - the
    Air Quality Index (AQI)" (NowCast appendix) and the AirNow NowCast formula description
    (airnow.gov). This is decision-support, matching the AQI's non-regulatory framing (ADR 0009),
    not the official 24-hour AQI.
    """
    window = list(concentrations)[:12]
    if len(window) < 3:
        return None
    c_min, c_max = min(window), max(window)
    weight = max(c_min / c_max, 0.5) if c_max > 0 else 1.0
    numerator = sum((weight**i) * c for i, c in enumerate(window))
    denominator = sum(weight**i for i in range(len(window)))
    return numerator / denominator


def nowcast_aqi(concentrations: Sequence[float]) -> tuple[int, str] | None:
    """Convert trailing hourly PM2.5 means (most-recent-first) to an EPA NowCast AQI + category.

    Thin wrapper: :func:`nowcast_concentration` does the EPA NowCast weighting, then
    :func:`pm25_aqi` supplies the breakpoint table and truncation convention — so a NowCast AQI
    and an hourly-mean AQI are always read off the exact same EPA bands, just from a differently
    weighted concentration. Returns ``None`` when fewer than 3 hourly means are available
    (mirrors :func:`nowcast_concentration`).
    """
    nowcast = nowcast_concentration(concentrations)
    if nowcast is None:
        return None
    return pm25_aqi(nowcast)


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


def wbgt_c(temp_c: float, humidity_pct: float) -> float:
    """**Estimated** wet-bulb globe temperature, Celsius in and out — shade approximation only.

    This is not a measured WBGT: it has no black-globe radiometer and no solar-radiation term, so
    it will read cooler than the true outdoor WBGT in direct sun and must never be presented as
    equivalent to a black-globe instrument reading. It is the natural-wet-bulb approximation from
    air temperature and relative humidity (Stull, R., 2011, "Wet-Bulb Temperature from Relative
    Humidity and Air Temperature," *Journal of Applied Meteorology and Climatology* 50(11):
    2267-2269), combined into the *shade* (indoor/outdoor-no-sun) WBGT form from ISO 7243
    (``WBGT = 0.7*Tw + 0.3*Td``, the two-term shade equation that drops the missing globe term).
    Every caller-facing label for this value must say "estimated WBGT," never bare "WBGT" — the
    occupational-heat guidance the metric is used for (e.g. OSHA/NIOSH heat standards) is written
    against a radiometer-measured value this approximation does not reproduce in direct sun.

    NaN inputs propagate to a NaN result (matching :func:`heat_index_c`) rather than raising —
    a missing reading is a missing derived reading, not an error.
    """
    tw = (
        temp_c * math.atan(0.151977 * math.sqrt(humidity_pct + 8.313659))
        + math.atan(temp_c + humidity_pct)
        - math.atan(humidity_pct - 1.676331)
        + 0.00391838 * math.pow(humidity_pct, 1.5) * math.atan(0.023101 * humidity_pct)
        - 4.686035
    )
    return round(0.7 * tw + 0.3 * temp_c, 2)


# NWS heat-index categories. The thresholds are the NWS band floors in °C, converted from the
# published °F values: 80 °F (Caution), 90 °F (Extreme Caution), 103 °F (Danger), 125 °F
# (Extreme Danger). Below the first floor there is no elevated heat risk.
_HEAT_BANDS: Final[tuple[tuple[float, str], ...]] = (
    (26.7, "Caution"),
    (32.2, "Extreme Caution"),
    (39.4, "Danger"),
    (51.1, "Extreme Danger"),
)

#: PM2.5 AQI category → a 0-to-4 air concern level, matched to the heat scale so the two hazards sit
#: on one ordinal. "Very Unhealthy" and "Hazardous" both top out at 4 (the scale's ceiling).
_AIR_CONCERN: Final[dict[str, int]] = {
    "Good": 0,
    "Moderate": 1,
    "Unhealthy for Sensitive Groups": 2,
    "Unhealthy": 3,
    "Very Unhealthy": 4,
    "Hazardous": 4,
}

#: The five combined heat-and-air exposure levels, indexed by the 0-to-4 ordinal.
EXPOSURE_LEVELS: Final[tuple[str, ...]] = ("Minimal", "Low", "Elevated", "High", "Extreme")


def heat_index_category(heat_index_c: float) -> tuple[int, str]:
    """NWS heat-index category as a 0-to-4 concern level and its name.

    0 is ``"None"`` (below the 26.7 °C / 80 °F Caution floor); 1 to 4 are Caution, Extreme Caution,
    Danger, Extreme Danger. NaN is rejected so a missing reading cannot pose as a measurement.
    """
    if math.isnan(heat_index_c):
        raise ValueError("heat index is NaN")
    level = 0
    name = "None"
    for floor, label in _HEAT_BANDS:
        if heat_index_c >= floor:
            level += 1
            name = label
    return level, name


def _component_levels(heat_index_c: float, aqi_category: str) -> tuple[int, int]:
    """(heat concern level, air concern level) — the shared input to `exposure_level` and
    `exposure_bounding_component`, so the two never disagree about which axis is driving."""
    return heat_index_category(heat_index_c)[0], _AIR_CONCERN.get(aqi_category, 0)


def exposure_level(heat_index_c: float, aqi_category: str) -> tuple[int, str, bool]:
    """Combine a heat-index value and a PM2.5 AQI category into one exposure level.

    Returns ``(level, name, compound)``: ``level`` is the 0-to-4 ordinal, ``name`` the matching
    :data:`EXPOSURE_LEVELS` entry. The level is the **higher** of the heat and air concern — the
    two hazards are placed on one ordinal, never blended into a fabricated number — and
    ``compound`` is true when heat *and* air are each at least the mid (level-2) tier, the joint
    case the evidence flags as worse than either hazard alone. This is decision-support, not a
    validated health index (see ADR 0009).
    """
    heat, air = _component_levels(heat_index_c, aqi_category)
    level = max(heat, air)
    compound = heat >= 2 and air >= 2
    return level, EXPOSURE_LEVELS[level], compound


def exposure_bounding_component(heat_index_c: float, aqi_category: str) -> str:
    """Which axis determines `exposure_level`'s ordinal: ``"heat"``, ``"air"``, or ``"both"``.

    Exposure's ``mean`` is an ordinal level, not a physical quantity with its own sigma —
    fabricating a sigma for it would misrepresent that. So instead of a number, the exposure cell
    publishes *which* component bounds the level, letting a reader go look at that component's
    real uncertainty (or provisional flag) directly. ``"both"`` marks a tie, which is also exactly
    the ``compound`` condition's boundary.
    """
    heat, air = _component_levels(heat_index_c, aqi_category)
    if heat == air:
        return "both"
    return "heat" if heat > air else "air"
