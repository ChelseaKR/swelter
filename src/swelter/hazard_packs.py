"""Hazard packs: the versioned, cited data that decides what a network alerts on.

swelter began as a heat-and-air tool, with one hard-wired set of danger floors in
:mod:`swelter.alerts`. But the same frontline block that overheats in July freezes in January and
chokes in fire season, and a network that only speaks "heat" goes dark for half the year. A
**hazard pack** generalizes the alert layer without weakening any invariant: it is *data* — like a
calibration correction (ADR 0002) — not code. A pack names the parameters it watches, the floor a
reading crosses to raise an alert on each, and a public-source citation for every floor, so the
"why this number" always travels with the number (invariant 4).

Enabling a pack is a ``network.yaml`` change (``hazard_pack: cold``), never a fork or a deploy.
The **heat pack is the default**: a config that names no pack behaves exactly as swelter always
has, byte for byte, so this abstraction adds a capability without changing a single existing
network's output.

What a pack deliberately is *not*: it is not personal safety advice. A floor is a documented
public-health/meteorological boundary (an EPA AQI category edge, an NWS chart line), and the
severity name attached to a crossing is the source's own label for that band — never a swelter
instruction to a resident. Resident-facing guidance *copy* (translated, plain-language, wired to
the dashboard) is a separate, review-gated surface and is not shipped here; see ADR 0031.

The band-naming and danger *direction* for each parameter live in :func:`swelter.alerts.crossing`
(heat/air/exposure cross upward; wind chill crosses downward — colder is worse), which every pack
shares, so two packs can never disagree about what "Danger" means for the same reading.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

#: The derived combined heat-and-air exposure layer's parameter name. Duplicated here as a plain
#: string (it also lives in ``aggregate.EXPOSURE``) so this leaf module needs no import from
#: :mod:`swelter.aggregate` — the dependency only ever points the other way.
EXPOSURE: Final = "exposure"


@dataclass(frozen=True)
class Citation:
    """Where a threshold comes from, so a caveat can travel with it (invariant 4).

    ``detail`` states, in the source's own terms, what the cited value/band means — not swelter's
    interpretation of it and never a safety instruction.
    """

    source: str  # the publishing authority, e.g. "US EPA", "US NWS"
    detail: str  # what the cited value/band is, in the source's own language
    url: str  # a public, stable link to the source
    last_verified: str  # ISO date this citation was last checked against the source


@dataclass(frozen=True)
class HazardThreshold:
    """One alert floor: the surface field it tests, the value that crosses it, and its citation."""

    key: str  # the floors-mapping key ``alerts.resolve_thresholds``/``crossing`` read
    parameter: str  # the surface parameter this floor is tested on (may differ from ``key``)
    floor: float  # a reading meeting/crossing this raises an alert (direction is per-parameter)
    citation: Citation


@dataclass(frozen=True)
class HazardPack:
    """A named, versioned set of alert floors plus the observed parameters they need aggregated.

    A pack is reviewable, diffable data. The heat pack reproduces swelter's original heat/air
    behaviour exactly; a network that names no pack gets it, so nothing changes when unspecified.
    """

    pack_id: str  # the ``network.yaml: hazard_pack`` value that selects this pack
    version: str  # bumped when a floor or its citation changes, like a correction version
    label: str  # a short human name for the pack
    thresholds: tuple[HazardThreshold, ...]
    #: Sourced, non-prescriptive pointers to the authority's own public guidance for this hazard —
    #: provenance, not resident-facing copy. Wiring translated guidance text to the dashboard is a
    #: review-gated follow-up (ADR 0031), so nothing here is presented to a resident as advice.
    guidance: tuple[Citation, ...] = ()

    def default_floors(self) -> dict[str, float]:
        """``key`` → ``floor`` for every threshold — the mapping alerts merges overrides onto."""
        return {t.key: t.floor for t in self.thresholds}

    def alerting_parameters(self) -> tuple[str, ...]:
        """The surface parameters this pack raises alerts on, in declared order (deduplicated)."""
        seen: dict[str, None] = {}
        for threshold in self.thresholds:
            seen.setdefault(threshold.parameter, None)
        return tuple(seen)

    def surface_parameters(self) -> tuple[str, ...]:
        """Observed parameters this pack needs rolled up before it can alert.

        ``exposure`` is excluded: it is derived by ``aggregate`` from the heat-index and PM2.5
        cells, not rolled up from an observation, so a pack never asks for it as an input.
        """
        return tuple(t.parameter for t in self.thresholds if t.parameter != EXPOSURE)

    def threshold_keys(self) -> frozenset[str]:
        """The floor keys a network may override for this pack (validated by ``swelter doctor``)."""
        return frozenset(t.key for t in self.thresholds)


# US-EPA PM2.5 AQI floor — the same air-quality danger boundary both packs watch, because unhealthy
# air is not a seasonal hazard. Shared so the two packs can never quietly disagree about it.
_EPA_PM25_FLOOR: Final = HazardThreshold(
    key="pm25_aqi",
    parameter="pm25_ugm3",
    floor=101.0,
    citation=Citation(
        source="US EPA",
        detail='AQI 101 = "Unhealthy for Sensitive Groups" boundary (2024 PM2.5 breakpoints)',
        url="https://www.airnow.gov/aqi/aqi-basics/",
        last_verified="2026-07-16",
    ),
)

#: The default pack: swelter's original heat/air danger floors, unchanged. A network that names no
#: ``hazard_pack`` gets this, so existing behaviour is preserved exactly.
HEAT_PACK: Final = HazardPack(
    pack_id="heat",
    version="1",
    label="Heat & air quality",
    thresholds=(
        _EPA_PM25_FLOOR,
        HazardThreshold(
            key="heat_index_c",
            parameter="heat_index_c",
            floor=39.4,
            citation=Citation(
                source="US NWS",
                detail='Heat-index "Danger" tier floor (103 °F / 39.4 °C)',
                url="https://www.weather.gov/safety/heat-index",
                last_verified="2026-07-16",
            ),
        ),
        HazardThreshold(
            key="exposure",
            parameter=EXPOSURE,
            floor=3.0,
            citation=Citation(
                source="swelter",
                detail='Combined heat-and-air exposure level 3 = "High" (ADR 0009)',
                url=(
                    "https://github.com/ChelseaKR/swelter/blob/main/docs/adr/"
                    "0009-compound-heat-air-exposure-surface.md"
                ),
                last_verified="2026-07-16",
            ),
        ),
    ),
    guidance=(
        Citation(
            source="US NWS",
            detail="Heat safety information",
            url="https://www.weather.gov/safety/heat",
            last_verified="2026-07-16",
        ),
        Citation(
            source="US EPA / AirNow",
            detail="Air Quality Index (AQI) basics",
            url="https://www.airnow.gov/aqi/aqi-basics/",
            last_verified="2026-07-16",
        ),
    ),
)

#: The cold pack: wind chill in place of heat, air quality retained. A collective serving a place
#: with real winters enables it by config alone, and the same pipeline runs seasonally correct.
COLD_PACK: Final = HazardPack(
    pack_id="cold",
    version="1",
    label="Cold & air quality",
    thresholds=(
        _EPA_PM25_FLOOR,
        HazardThreshold(
            key="wind_chill_c",
            parameter="wind_chill_c",
            # Colder is worse: a reading at or below this floor crosses (see ``alerts.crossing``).
            # -19 °F is the one frostbite-time boundary the NWS Wind Chill Chart states numerically
            # (0 °F air, 15 mph wind → -19 °F wind chill, "exposed skin can freeze in 30 minutes").
            floor=-28.3,
            citation=Citation(
                source="US NWS",
                detail=(
                    "Wind Chill Chart frostbite boundary — exposed skin can freeze in 30 minutes "
                    "at a wind chill of -19 °F / -28.3 °C"
                ),
                url="https://www.weather.gov/safety/cold-wind-chill-chart",
                last_verified="2026-07-18",
            ),
        ),
    ),
    guidance=(
        Citation(
            source="US NWS",
            detail="Cold and wind-chill safety information",
            url="https://www.weather.gov/safety/cold",
            last_verified="2026-07-18",
        ),
        Citation(
            source="US EPA / AirNow",
            detail="Air Quality Index (AQI) basics",
            url="https://www.airnow.gov/aqi/aqi-basics/",
            last_verified="2026-07-16",
        ),
    ),
)

#: The pack a network gets when it names none.
DEFAULT_PACK_ID: Final = "heat"

#: Every shipped pack, keyed by its ``network.yaml: hazard_pack`` id.
PACKS: Final[dict[str, HazardPack]] = {
    HEAT_PACK.pack_id: HEAT_PACK,
    COLD_PACK.pack_id: COLD_PACK,
}


def resolve_pack(pack_id: str | None) -> HazardPack:
    """The pack a network selected, or the default heat pack for an unset or unknown id.

    Fail-safe on purpose, exactly like :func:`swelter.alerts.resolve_thresholds`: an unknown id
    never crashes a build here — it falls back to heat — because ``config.config_concerns`` /
    ``swelter doctor`` already rejects an unknown ``hazard_pack`` as a hard error *before* any
    build runs, so this branch is only ever reached with a valid id in normal operation.
    """
    if not pack_id:
        return PACKS[DEFAULT_PACK_ID]
    return PACKS.get(pack_id, PACKS[DEFAULT_PACK_ID])
