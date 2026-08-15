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
    # Wind chill runs colder than air temp, so the floor is well below temp_c's; the ceiling
    # matches temp_c because the estimate passes air temperature through unchanged when wind chill
    # is not defined (warm or nearly calm — see `wind_chill_c`).
    "wind_chill_c": Parameter("wind_chill_c", "degC", -100.0, 60.0),
}

# QC verdicts. A reading is published with exactly one of these, never silently dropped.
QC_OK: Final = "ok"
QC_RANGE: Final = "range"
QC_SPIKE: Final = "spike"
QC_FLATLINE: Final = "flatline"
#: Reserved, and **never emitted by the shipped pipeline** (issue #147). swelter represents an
#: absent reading by the absence of a row: nothing writes an observation to say one did not happen,
#: and `qc.detect_gaps` reports gaps as their own artifact from the timestamps that *are* present.
#: The constant is kept because it is the verdict an ingest path that genuinely knows a reading was
#: expected would use, and because `QC_UNMAPPABLE` must reject it if one ever arrives. It stays out
#: of `QC_EMITTED`, and the published data dictionary says so, so a consumer writing
#: ``if row.qc == "missing"`` is told plainly that the branch is dead rather than discovering it.
QC_MISSING: Final = "missing"

#: The verdicts `qc` can actually put on a reading. `QC_MISSING` is deliberately absent — see above.
QC_EMITTED: Final[frozenset[str]] = frozenset({QC_OK, QC_RANGE, QC_SPIKE, QC_FLATLINE})

#: Verdicts that mean "this is not a measurement" — physically impossible or absent. A cell never
#: places one, even provisionally (see ADR 0029).
QC_UNMAPPABLE: Final[frozenset[str]] = frozenset({QC_RANGE, QC_MISSING})

#: Verdicts that mean "this looks suspicious" — a heuristic spike or a stuck-sensor flatline. The
#: onset of a real smoke front or a calm noise-floor stretch looks like these, so the value is kept
#: and shown *provisional and flagged* rather than dropped (ADR 0029). It is never trusted.
QC_SUSPICIOUS: Final[frozenset[str]] = frozenset({QC_SPIKE, QC_FLATLINE})

#: QC verdicts that mean "do not trust this value as a measurement" — the union of the two above.
#: ``node_health`` counts these as flagged: a suspicious reading is still node-trouble evidence.
QC_REJECTED: Final[frozenset[str]] = QC_UNMAPPABLE | QC_SUSPICIOUS

ISO_FORMAT: Final = "%Y-%m-%dT%H:%M:%SZ"


@dataclass(frozen=True)
class Observation:
    """One measurement of one parameter by one node at one instant.

    Frozen on purpose: observations are written once and never mutated. ``with_qc`` and
    ``calibrated`` return new records, so provenance is additive and auditable.

    One invariant is enforced here rather than trusted to every writer: **a calibrated observation
    carries a 1-sigma.** A correction is fitted from recorded co-location evidence and always has a
    ``residual_std``, so a calibrated value with no uncertainty is not a legitimate state — it is a
    row that would go on to be published as fact with no error bar, or (before issue #147) read as
    a perfect instrument in the cell rollup. `calibrate.apply` never produced one, but nothing
    stopped an import path, a restored archive, or a future adapter from doing so. It is refused at
    construction, which is the only boundary every one of those paths passes through.
    """

    node_id: str
    timestamp: str  # ISO 8601, UTC, e.g. "2026-06-01T00:00:00Z"
    parameter: str
    value: float
    unit: str
    source: str = SOURCE_NATIVE
    calibration: str = RAW
    qc: str = QC_OK
    uncertainty: float | None = None  # 1-sigma in `unit`, required once calibrated

    def __post_init__(self) -> None:
        if self.calibration != RAW and self.uncertainty is None:
            raise ValueError(
                f"calibrated observation {self.node_id}/{self.parameter}@{self.timestamp} "
                f"(calibration={self.calibration!r}) has no uncertainty; a correction is fitted "
                "with a residual_std, so an absent 1-sigma is a broken row, not a zero one"
            )

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


def wind_chill_c(temp_c: float, wind_kph: float) -> float:
    """Wind-chill temperature, Celsius in and out, from air temperature and wind speed (km/h).

    This is the standard NWS/Environment-Canada wind-chill index (the 2001 North American revision),
    metric form: ``WCT = 13.12 + 0.6215*T - 11.37*V^0.16 + 0.3965*T*V^0.16`` with ``T`` in °C and
    ``V`` the 10-metre wind speed in km/h. It is a **documented approximation of how cold exposed
    skin feels**, not a measured quantity: it models convective and evaporative heat loss from bare
    skin for an average adult walking into the wind, and it says nothing about a person's actual
    core temperature, clothing, sun, or health. Producers must label it "wind chill," never present
    it as an air temperature.

    The index is only defined for ``temp_c <= 10`` and ``wind_kph > 4.8`` (≈3 mph); outside that
    domain wind chill is not meaningful, so the air temperature is returned unchanged — the same
    passthrough convention :func:`heat_index_c` uses below its own floor. NaN inputs propagate to a
    NaN result rather than raising (a missing reading is a missing derived reading).

    Wind speed is not a parameter any current swelter source adapter supplies, so — unlike
    :func:`heat_index_c` — this is not auto-derived in the fetch path; it is the reference
    implementation for a node (or an operator with a wind feed) that reports ``wind_chill_c``
    directly. See ``docs/adr/0031-multi-hazard-packs.md``.
    """
    if temp_c > 10.0 or wind_kph <= 4.8:
        return round(temp_c, 2)
    v = math.pow(wind_kph, 0.16)
    return round(13.12 + 0.6215 * temp_c - 11.37 * v + 0.3965 * temp_c * v, 2)


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


# NWS Wind Chill Chart frostbite-time boundary. The published chart states exactly one frostbite
# boundary numerically — exposed skin can develop frostbite within 30 minutes at a wind chill of
# -19 °F (-28.3 °C) — so that is the only band asserted here. The chart's colder 10- and 5-minute
# frostbite zones are not published as numeric wind-chill cutoffs, so no band is invented for them
# (a graduated cold scale would need those values sourced first). Ordered warmest-ceiling-first so
# `wind_chill_category` can extend to colder bands later the way `_HEAT_BANDS` does for hotter ones.
# https://www.weather.gov/safety/cold-wind-chill-chart
_WIND_CHILL_BANDS: Final[tuple[tuple[float, str], ...]] = ((-28.3, "Frostbite in 30 min"),)


def wind_chill_category(wind_chill_c: float) -> tuple[int, str]:
    """NWS wind-chill frostbite category as a concern level and its name.

    Colder is worse, so a reading crosses a band by falling **at or below** its ceiling — the
    mirror of :func:`heat_index_category`. 0 is ``"None"`` (above the documented -28.3 °C / -19 °F
    frostbite boundary); 1 is the NWS chart's "frostbite in 30 minutes" zone. NaN is rejected so a
    missing reading cannot pose as a measurement.
    """
    if math.isnan(wind_chill_c):
        raise ValueError("wind chill is NaN")
    level = 0
    name = "None"
    for ceiling, label in _WIND_CHILL_BANDS:
        if wind_chill_c <= ceiling:
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
