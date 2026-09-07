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

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

#: The derived combined heat-and-air exposure layer's parameter name. Duplicated here as a plain
#: string (it also lives in ``aggregate.EXPOSURE``) so this leaf module needs no import from
#: :mod:`swelter.aggregate` — the dependency only ever points the other way.
EXPOSURE: Final = "exposure"

#: The two PM2.5 averaging windows, duplicated here as plain strings for the same reason as
#: :data:`EXPOSURE` -- this leaf module imports nothing from :mod:`swelter.aggregate`, and the
#: dependency only ever points the other way. They must equal ``aggregate.AQI_WINDOW`` and
#: ``aggregate.AQI_WINDOW_NOWCAST``, and a test asserts they do.
AQI_WINDOW_HOURLY_MEAN: Final = "hourly-mean"
AQI_WINDOW_NOWCAST: Final = "nowcast"


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
class EventRule:
    """When several cells rising together stop being several readings and become one event.

    A single node reading 300 ug/m3 is a node, not a smoke day: it might be a barbecue under the
    sensor, or a failing ADC. What distinguishes a wildfire-smoke episode from a spiking node is
    that it happens *across* a neighbourhood at once. So an event needs ``minimum_cells`` distinct
    published cells at or above ``floor`` in the same hour, each of which has risen by at least
    ``rise`` against its own reading ``lookback_hours`` earlier.

    The rise is per-cell and against that cell's own past, deliberately. An absolute floor alone
    would declare an event every hour of a week-long episode, and a network in a chronically poor
    airshed would sit permanently "in an event" -- which tells a resident nothing.

    Every number here is pack data, not code, so changing what counts as an event is a reviewable
    diff in this file with a citation attached, exactly like a threshold.
    """

    parameter: str  # the surface parameter the rule watches
    #: The averaging window the rule reads, which is deliberately its own field and not the
    #: pack's. A rule that measures a *rise* needs a series, and the EPA NowCast is not one:
    #: :func:`swelter.aggregate._nowcast_cells` derives exactly one NowCast row per cell, at that
    #: cell's most recent bucket, so there is no NowCast reading three hours ago to compare
    #: against and never will be. So the smoke pack alerts on NowCast (the "right now" tier a
    #: resident needs) and detects its event on the hourly means (the series a rise is measurable
    #: in). The two windows are different questions, and the published record names the one it
    #: used rather than leaving a reader to assume they match.
    aqi_window: str
    floor: float  # a cell at or above this, in ``parameter``'s own units, is a candidate
    rise: float  # ... and must have risen at least this much against its own earlier reading
    lookback_hours: int  # how far back that earlier reading is taken from
    minimum_cells: int  # how many candidate cells make it an event rather than a node
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
    #: Which PM2.5 averaging window this pack's alerts read. Heat and cold read the hourly mean,
    #: which is what they have always read. Smoke reads the EPA NowCast, because an hourly mean
    #: lags a plume by design and a resident deciding whether to go outside needs the "right now"
    #: number. A pack never *falls back* to the other window: a cell without a reading in the
    #: pack's window raises no alert rather than an alert in a window the feed did not promise.
    aqi_window: str = AQI_WINDOW_HOURLY_MEAN
    #: The rule, if any, that turns several cells rising together into one named event.
    event_rule: EventRule | None = None
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

#: The smoke pack: PM2.5 read on the EPA NowCast window, with an event rule.
#:
#: For a California network this is the hazard after heat season. It watches only PM2.5, because
#: that is the parameter a low-cost network measures well and the one a smoke day is about; heat
#: and wind chill are not silently carried over, so a network that selects smoke is told exactly
#: what it is now alerting on.
SMOKE_PACK: Final = HazardPack(
    pack_id="smoke",
    version="1",
    label="Wildfire smoke",
    aqi_window=AQI_WINDOW_NOWCAST,
    thresholds=(
        HazardThreshold(
            key="pm25_aqi",
            parameter="pm25_ugm3",
            floor=101.0,
            citation=Citation(
                source="US EPA",
                detail=(
                    'AQI 101 = "Unhealthy for Sensitive Groups" boundary (2024 PM2.5 '
                    "breakpoints), read on the NowCast window AirNow publishes as the current "
                    "hour's air quality"
                ),
                url="https://document.airnow.gov/technical-assistance-document-for-the-reporting-of-daily-air-quailty.pdf",
                last_verified="2026-09-07",
            ),
        ),
    ),
    event_rule=EventRule(
        parameter="pm25_ugm3",
        # Hourly means, not NowCast, and not because hourly means are better: NowCast exists
        # only at each cell's newest bucket, so a rise across three hours cannot be measured in
        # it at all. See ``EventRule.aqi_window``.
        aqi_window=AQI_WINDOW_HOURLY_MEAN,
        # 35.5 ug/m3 is the EPA breakpoint where the 2024 PM2.5 AQI leaves "Moderate"; a cell at or
        # above it is a candidate. The rise and the cell count are swelter's own, and are stated as
        # such rather than dressed up as an EPA rule: no published standard says how many sensors
        # make a smoke event, because that depends on a network's own density.
        floor=35.5,
        rise=20.0,
        lookback_hours=3,
        minimum_cells=3,
        citation=Citation(
            source="US EPA",
            detail=(
                "35.5 ug/m3 is the 2024 PM2.5 breakpoint where the AQI leaves the Moderate band. "
                "The 20 ug/m3 three-hour rise and the three-cell minimum are swelter's own, "
                "chosen so one spiking node cannot declare an event; no published standard sets "
                "them, because they depend on a network's own sensor density"
            ),
            url="https://www.epa.gov/system/files/documents/2024-02/pm-naaqs-air-quality-index-fact-sheet.pdf",
            last_verified="2026-09-07",
        ),
    ),
    guidance=(
        Citation(
            source="US EPA / AirNow",
            detail="Wildfire smoke and your health",
            url="https://www.airnow.gov/air-quality-and-health/wildfires/",
            last_verified="2026-09-07",
        ),
        Citation(
            source="US EPA / AirNow",
            detail="Air Quality Index (AQI) basics",
            url="https://www.airnow.gov/aqi/aqi-basics/",
            last_verified="2026-09-07",
        ),
    ),
)

#: The pack a network gets when it names none.
DEFAULT_PACK_ID: Final = "heat"

#: ``hazard_pack: auto-season`` — not a pack, a *selector*. It names no thresholds of its own; it
#: says "read the calendar this network declared and use whichever pack covers the month the data
#: is about". EXP-13 proposed it and ADR 0050 deferred it, for a reason worth restating: switching
#: by the wall clock would make the published output depend on the day the pipeline ran, which puts
#: ``scripts/demo_artifact_check.py`` and the committed artifacts in disagreement across a month
#: boundary — a calendar bomb inside the merge gate. See :func:`resolve_pack` for what replaced the
#: wall clock.
AUTO_SEASON_PACK_ID: Final = "auto-season"


@dataclass(frozen=True)
class SeasonWindow:
    """One entry in a network's season calendar: which months get which pack.

    A **network** declares this, not swelter. A calendar is a claim about a place's climate — that
    smoke season runs June to November, that winter is a hazard here at all — and shipping one
    would mean asserting a climatology for everywhere the software runs. The collective in Fresno
    and the collective in Duluth do not have the same year, and neither of them needs swelter's
    opinion about it. So the pack ids are swelter's (they carry the cited thresholds) and the
    months are the network's.
    """

    #: Months of the year this window covers, 1-12. Every month must appear exactly once across a
    #: network's whole calendar; ``config.config_concerns`` rejects a gap or an overlap rather than
    #: letting an uncovered month fall back to heat in a place that has no summer.
    months: tuple[int, ...]
    #: The ``PACKS`` id to use in those months.
    pack: str


class SeasonCalendarError(ValueError):
    """A calendar that cannot select a pack for some month — refused, never defaulted."""


def season_calendar_problems(calendar: Sequence[SeasonWindow]) -> list[str]:
    """Everything wrong with a season calendar, or an empty list.

    Checked here rather than in ``config`` so the rule lives beside the packs it selects, and so a
    caller building a calendar in code gets the same refusals a ``network.yaml`` does.
    """
    problems: list[str] = []
    if not calendar:
        return [
            "season_calendar: hazard_pack 'auto-season' selects a pack by month, so the network "
            "must declare which months get which pack; swelter ships no calendar because a "
            "calendar is a claim about a particular place's climate"
        ]
    seen: dict[int, str] = {}
    for window in calendar:
        if window.pack not in PACKS:
            problems.append(
                f"season_calendar: unknown pack {window.pack!r}; recognized packs: "
                f"{', '.join(sorted(PACKS))}"
            )
        for month in window.months:
            if not 1 <= month <= 12:
                problems.append(f"season_calendar: month {month} is not in 1-12")
                continue
            if month in seen:
                problems.append(
                    f"season_calendar: month {month} is claimed by both {seen[month]!r} and "
                    f"{window.pack!r}; a month must select exactly one pack"
                )
            else:
                seen[month] = window.pack
    missing = sorted(set(range(1, 13)) - set(seen))
    if missing:
        problems.append(
            "season_calendar: no pack covers month(s) "
            f"{', '.join(str(m) for m in missing)}; an uncovered month would fall back to heat, "
            "which is the wrong answer in a place whose calendar deliberately omits it"
        )
    return problems


def pack_for_month(calendar: Sequence[SeasonWindow], month: int) -> HazardPack:
    """The pack a validated calendar selects for ``month``.

    Raises rather than defaulting. ``config_concerns`` rejects an incomplete calendar before any
    build runs, so reaching this with an uncovered month means the validation was bypassed — and
    silently alerting on heat in a month a network said was smoke season is exactly the safety
    surprise :func:`resolve_pack`'s fallback comment warns about.
    """
    for window in calendar:
        if month in window.months:
            pack = PACKS.get(window.pack)
            if pack is None:
                raise SeasonCalendarError(f"season calendar names unknown pack {window.pack!r}")
            return pack
    raise SeasonCalendarError(f"season calendar covers no pack for month {month}")


def season_surface_parameters(calendar: Sequence[SeasonWindow]) -> tuple[str, ...]:
    """Every observed parameter any pack in the calendar might need rolled up.

    The union, not the current month's pack alone, and deliberately so: the rollup happens before
    the month is known (the month comes from the surface, and the surface is what is being built),
    and a cell that was never aggregated cannot be alerted on later. A network on a smoke/cold
    calendar therefore carries wind chill through the whole year — a wider surface, not a wrong
    one, and the alternative is a January in which the cold pack has nothing to read.
    """
    seen: dict[str, None] = {}
    for window in calendar:
        pack = PACKS.get(window.pack)
        if pack is None:
            continue
        for parameter in pack.surface_parameters():
            seen.setdefault(parameter, None)
    return tuple(seen)


#: Every shipped pack, keyed by its ``network.yaml: hazard_pack`` id.
PACKS: Final[dict[str, HazardPack]] = {
    HEAT_PACK.pack_id: HEAT_PACK,
    COLD_PACK.pack_id: COLD_PACK,
    SMOKE_PACK.pack_id: SMOKE_PACK,
}


def resolve_pack(
    pack_id: str | None,
    *,
    calendar: Sequence[SeasonWindow] = (),
    month: int | None = None,
) -> HazardPack:
    """The pack a network selected, or the default heat pack for an unset or unknown id.

    Fail-safe on purpose, exactly like :func:`swelter.alerts.resolve_thresholds`: an unknown id
    never crashes a build here — it falls back to heat — because ``config.config_concerns`` /
    ``swelter doctor`` already rejects an unknown ``hazard_pack`` as a hard error *before* any
    build runs, so this branch is only ever reached with a valid id in normal operation.

    ``auto-season`` is the one id that is not a pack. It selects one from ``calendar`` using
    ``month`` — **the month of the data**, which every caller derives from
    :meth:`swelter.aggregate.Surface.newest_bucket`, never from the wall clock. That is the whole
    difference between this and the version ADR 0050 declined to ship: a wall-clock switch makes
    the published output depend on the day the pipeline ran, so a committed artifact and a fresh
    replay disagree the moment a month boundary passes, and ``demo-artifacts`` goes red on a
    calendar rather than on a change. Deriving the month from the data keeps a replay of a fixed
    store byte-identical forever.

    With no ``month`` — a caller asking "which pack, in general?", such as ``doctor`` validating
    override keys — an ``auto-season`` network resolves to the default rather than guessing a
    month; :func:`season_threshold_keys` is what such a caller should use instead.
    """
    if not pack_id:
        return PACKS[DEFAULT_PACK_ID]
    if pack_id == AUTO_SEASON_PACK_ID:
        if month is None or not calendar:
            return PACKS[DEFAULT_PACK_ID]
        return pack_for_month(calendar, month)
    return PACKS.get(pack_id, PACKS[DEFAULT_PACK_ID])


def season_threshold_keys(calendar: Sequence[SeasonWindow]) -> frozenset[str]:
    """Every floor key any pack in the calendar defines — the keys an auto-season network may set.

    A seasonal network legitimately overrides ``heat_index_c`` *and* ``wind_chill_c``: it uses both
    packs, in different months. Validating its overrides against a single pack would reject one of
    them as unknown, which is how a host ends up believing they lowered a danger floor and did not.
    """
    keys: set[str] = set()
    for window in calendar:
        pack = PACKS.get(window.pack)
        if pack is not None:
            keys |= pack.threshold_keys()
    return frozenset(keys)


def month_of(bucket: str) -> int:
    """The calendar month of an hour bucket (``YYYY-MM-DDTHH:MM:SSZ``).

    Parsed positionally rather than through ``datetime``: every bucket in this project is already
    canonical UTC written by :func:`swelter.aggregate.hour_bucket`, and a timezone conversion here
    could only introduce a way for the month to differ from the one printed in the timestamp a
    reader sees beside it.
    """
    return int(bucket[5:7])
