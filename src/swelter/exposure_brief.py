"""Plain-language neighborhood exposure brief: "this block ran Danger N days this period,"
with sourced canopy/AC-access/redlining context alongside it.

This is the historical, per-area sibling of :mod:`swelter.alerts` — alerts answer "is this cell
in danger *right now*"; this module answers "how often has it been" over whatever history the
store holds, using the exact same danger-threshold definitions (:func:`swelter.alerts.crossing`,
:data:`swelter.alerts.DEFAULT_THRESHOLDS`) so the two views of "danger" can never quietly drift
apart. It reuses the copy-a-summary pattern the merged network-brief feature
(``web/app.js`` — "Copy a summary of the whole network") established for the *network* scale, at
the *neighborhood* scale, and adds the sourced context an organizer needs for testimony or a
funding ask: how much tree canopy an area has, whether area households may lack AC, and whether
the area was historically redlined — each claim citing a real, named public dataset.

**What this deliberately does not do.** It does not blend the day-count with the context layers
into a single computed "risk" number, does not claim the redlining grade *causes* today's
readings, and does not editorialize. Every context sentence is of the shape "X is true of this
area, per [source], as of [date]" — a citation, not an argument. Advocacy framing beyond that is
a `[HUMAN]`-gated editorial decision the roadmap (F4, F6) deliberately keeps out of swelter's own
copy; this module hands an organizer sourced facts to build that case with, not the case itself.

Context is optional and additive: a cell with no canopy/AC-access/redlining coverage for its area
still gets a danger-day count, just without that sentence — an absent context layer is left out,
never estimated or defaulted to a number swelter did not receive from a source.

The day count is not the whole claim, either. Every brief also states how many of its Danger days
rest only on readings the pipeline does not trust as measurements — provisional (uncalibrated) or
QC flagged as a spike or a flatline — so a well-evidenced count and a shaky one never read the
same. Those days are counted, never dropped: dropping them would blank exactly the hours ADR 0029
exists to keep visible. See ADR 0046.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from .ac_access_layer import ACAccessCell, ACAccessLayerSet
from .aggregate import EXPOSURE, CellReading, Surface
from .alerts import crossing, resolve_thresholds
from .context_layers import ContextCell, ContextLayerSet
from .models import EXPOSURE_LEVELS, parse_timestamp
from .redlining_layer import RedliningCell, RedliningLayerSet

#: The parameter this module counts "Danger" days on. Heat is the tier the roadmap item names
#: ("this block ran Danger N days this month") and the one NWS name that means the same thing in
#: both the live alerts feed and this historical count.
DEFAULT_PARAMETER: Final = "heat_index_c"


def _calendar_date(bucket: str) -> str:
    """The UTC calendar date (``YYYY-MM-DD``) an hourly bucket timestamp falls on."""
    return parse_timestamp(bucket).date().isoformat()


def _floor_and_band(parameter: str, floors: Mapping[str, float]) -> tuple[float, str]:
    """The configured danger floor and the named band it represents for a parameter.

    Independent of any single reading, so a cell with zero danger days still reports what floor
    and band it was measured against (the same floors `alerts.crossing` tests).
    """
    if parameter == "pm25_ugm3":
        return floors["pm25_aqi"], "Unhealthy for Sensitive Groups"
    if parameter == "heat_index_c":
        return floors["heat_index_c"], "Danger"
    if parameter == EXPOSURE:
        floor = floors["exposure"]
        level = min(int(floor), len(EXPOSURE_LEVELS) - 1)
        return floor, EXPOSURE_LEVELS[level]
    raise ValueError(f"{parameter!r} has no documented danger floor")


@dataclass(frozen=True)
class DangerDayCount:
    """How many calendar days one published cell crossed a danger threshold, over its history."""

    cell_id: str
    label: str
    lat: float
    lon: float
    parameter: str
    floor: float
    severity: str  # the named band the floor represents (e.g. "Danger")
    period_start: str  # earliest calendar date (UTC) with data for this cell/parameter
    period_end: str  # latest calendar date (UTC) with data for this cell/parameter
    days_observed: int  # distinct calendar days with at least one reading
    danger_days: int  # of those, how many had at least one hour at/above the floor
    # Of `danger_days`, how many rest *entirely* on readings the pipeline does not trust as
    # measurements. A day with even one calibrated, unflagged crossing is not counted here: that
    # day's Danger verdict already stands on evidence swelter vouches for. Both are subsets of
    # `danger_days`, and `danger_days_qc_flagged` is a subset of `danger_days_provisional` in turn,
    # because a QC-flagged cell is always provisional (ADR 0029).
    danger_days_provisional: int = 0  # every crossing that day was provisional (uncalibrated)
    danger_days_qc_flagged: int = 0  # every crossing that day was QC flagged (spike/flatline)

    def as_record(self) -> dict[str, object]:
        return {
            "cell_id": self.cell_id,
            "label": self.label,
            "lat": self.lat,
            "lon": self.lon,
            "parameter": self.parameter,
            "floor": self.floor,
            "severity": self.severity,
            "period_start": self.period_start,
            "period_end": self.period_end,
            "days_observed": self.days_observed,
            "danger_days": self.danger_days,
            "danger_days_provisional": self.danger_days_provisional,
            "danger_days_qc_flagged": self.danger_days_qc_flagged,
        }


def count_danger_days(
    surface: Surface,
    *,
    parameter: str = DEFAULT_PARAMETER,
    thresholds: Mapping[str, float] | None = None,
) -> dict[str, DangerDayCount]:
    """For every published cell, count how many calendar days a parameter crossed its danger floor.

    Reuses :func:`swelter.alerts.crossing` and :func:`swelter.alerts.resolve_thresholds` — the
    exact "Danger" definition the live alerts feed raises on — instead of re-deriving a second
    threshold table. A day counts once it has *any* hour at or above the floor. A cell that never
    reported this parameter is simply absent from the result (not zero-filled): "zero Danger
    days" and "no data" are different claims, and collapsing them would be dishonest.

    A crossing is counted whatever its QC state — a spike that turns out to be the onset of a real
    event is exactly the hour a resident needs to see, and dropping it would repeat the mistake
    ADR 0029 corrected. What travels with the count instead is *how much of it swelter vouches
    for*: `danger_days_provisional` and `danger_days_qc_flagged` record the days whose danger
    verdict rests entirely on readings the pipeline does not trust as measurements.
    """
    floors = resolve_thresholds(thresholds)
    floor_value, severity = _floor_and_band(parameter, floors)

    by_cell: dict[str, list[CellReading]] = defaultdict(list)
    for cell in surface.cells:
        if cell.parameter == parameter:
            by_cell[cell.cell_id].append(cell)

    out: dict[str, DangerDayCount] = {}
    for cell_id, readings in by_cell.items():
        by_date: dict[str, list[CellReading]] = defaultdict(list)
        for reading in readings:
            by_date[_calendar_date(reading.bucket)].append(reading)
        danger_dates: set[str] = set()
        provisional_dates: set[str] = set()
        flagged_dates: set[str] = set()
        for date, day_readings in by_date.items():
            crossings = [r for r in day_readings if crossing(parameter, r, floors) is not None]
            if not crossings:
                continue
            danger_dates.add(date)
            # "Entirely", not "any": one calibrated, unflagged crossing is enough for the day's
            # Danger verdict to stand on evidence swelter vouches for, and calling such a day
            # provisional would overstate the doubt as badly as omitting it understates it.
            if all(r.provisional for r in crossings):
                provisional_dates.add(date)
            if all(r.qc_flags for r in crossings):
                flagged_dates.add(date)
        dates_sorted = sorted(by_date)
        any_reading = readings[0]
        out[cell_id] = DangerDayCount(
            cell_id=cell_id,
            label=any_reading.label,
            lat=any_reading.lat,
            lon=any_reading.lon,
            parameter=parameter,
            floor=floor_value,
            severity=severity,
            period_start=dates_sorted[0],
            period_end=dates_sorted[-1],
            days_observed=len(dates_sorted),
            danger_days=len(danger_dates),
            danger_days_provisional=len(provisional_dates),
            danger_days_qc_flagged=len(flagged_dates),
        )
    return out


@dataclass(frozen=True)
class ExposureBrief:
    """A plain-language, sourced brief for one published cell: its Danger-day count plus
    whatever canopy/AC-access/redlining context is available for that same cell.

    Each context field is ``None`` when the source dataset has no coverage for this cell — the
    brief renders fewer sentences rather than a guessed or interpolated one.
    """

    area_id: str
    area: str
    lat: float
    lon: float
    danger: DangerDayCount
    canopy: ContextCell | None = None
    ac_access: ACAccessCell | None = None
    redlining: RedliningCell | None = None

    def lines(self) -> list[str]:
        """Plain-language, factual, sourced lines — no framing beyond what each source states."""
        d = self.danger
        lines = [
            f"{self.area}: heat index reached the {d.severity} range (≥{d.floor:g} °C) on "
            f"{d.danger_days} of {d.days_observed} day(s) measured, {d.period_start} to "
            f"{d.period_end}."
        ]
        if d.danger_days:
            # Rendered whenever there is a Danger verdict to qualify, including when nothing is
            # in doubt: "0 of 3" is a statement about the evidence, and leaving it out would make
            # a well-evidenced count and a shaky one look identical (the same reason the event
            # chronicle always renders its "what the network could not see" section).
            lines.append(
                f"Of those {d.danger_days} day(s), {d.danger_days_provisional} rest only on "
                f"provisional readings, which swelter publishes but has not calibrated, and "
                f"{d.danger_days_qc_flagged} rest only on readings QC flagged as suspicious "
                f"(a spike or a flatline)."
            )
        if self.canopy is not None:
            c = self.canopy
            cite = f" {c.source_url}" if c.source_url else ""
            lines.append(
                f"Tree-canopy coverage in this area is {c.canopy_pct:g}% per {c.source} "
                f"(as of {c.last_verified}).{cite}".rstrip()
            )
        if self.ac_access is not None:
            a = self.ac_access
            cite = f" {a.source_url}" if a.source_url else ""
            lines.append(
                f"An estimated {a.no_ac_pct:g}% of households in this area may lack air "
                f"conditioning, per {a.source} (as of {a.last_verified}).{cite}".rstrip()
            )
        if self.redlining is not None:
            r = self.redlining
            cite = f" {r.source_url}" if r.source_url else ""
            lines.append(
                f'This area was rated grade {r.holc_grade} ("{r.grade_label}") by the federal '
                f"Home Owners' Loan Corporation in a 1930s residential security survey, per "
                f"{r.source} (as of {r.last_verified}).{cite}".rstrip()
            )
        return lines

    def to_text(self) -> str:
        return "\n".join(self.lines())

    def as_record(self) -> dict[str, object]:
        record: dict[str, object] = {
            "area_id": self.area_id,
            "area": self.area,
            "lat": self.lat,
            "lon": self.lon,
            "danger": self.danger.as_record(),
            "text": self.lines(),
        }
        if self.canopy is not None:
            record["canopy"] = {
                "canopy_pct": self.canopy.canopy_pct,
                "source": self.canopy.source,
                "source_url": self.canopy.source_url,
                "last_verified": self.canopy.last_verified,
            }
        if self.ac_access is not None:
            record["ac_access"] = {
                "no_ac_pct": self.ac_access.no_ac_pct,
                "source": self.ac_access.source,
                "source_url": self.ac_access.source_url,
                "last_verified": self.ac_access.last_verified,
            }
        if self.redlining is not None:
            record["redlining"] = {
                "holc_grade": self.redlining.holc_grade,
                "holc_grade_label": self.redlining.grade_label,
                "source": self.redlining.source,
                "source_url": self.redlining.source_url,
                "last_verified": self.redlining.last_verified,
            }
        return record


def build_briefs(
    surface: Surface,
    *,
    parameter: str = DEFAULT_PARAMETER,
    thresholds: Mapping[str, float] | None = None,
    canopy: ContextLayerSet | None = None,
    ac_access: ACAccessLayerSet | None = None,
    redlining: RedliningLayerSet | None = None,
) -> dict[str, ExposureBrief]:
    """Build one sourced :class:`ExposureBrief` per published cell that reported ``parameter``.

    ``canopy``, ``ac_access``, and ``redlining`` are optional, independently — a caller with only
    a canopy dataset still gets briefs, just without the AC-access/redlining sentences (ADR 0014).
    """
    danger_counts = count_danger_days(surface, parameter=parameter, thresholds=thresholds)
    canopy_by_cell = canopy.by_cell_id() if canopy is not None else {}
    ac_by_cell = ac_access.by_cell_id() if ac_access is not None else {}
    redlining_by_cell = redlining.by_cell_id() if redlining is not None else {}

    briefs: dict[str, ExposureBrief] = {}
    for cell_id, danger in danger_counts.items():
        briefs[cell_id] = ExposureBrief(
            area_id=cell_id,
            area=danger.label or cell_id,
            lat=danger.lat,
            lon=danger.lon,
            danger=danger,
            canopy=canopy_by_cell.get(cell_id),
            ac_access=ac_by_cell.get(cell_id),
            redlining=redlining_by_cell.get(cell_id),
        )
    return briefs


def build_brief(
    cell_id: str,
    surface: Surface,
    *,
    parameter: str = DEFAULT_PARAMETER,
    thresholds: Mapping[str, float] | None = None,
    canopy: ContextLayerSet | None = None,
    ac_access: ACAccessLayerSet | None = None,
    redlining: RedliningLayerSet | None = None,
) -> ExposureBrief | None:
    """The brief for one published cell, or ``None`` if it never reported ``parameter``."""
    return build_briefs(
        surface,
        parameter=parameter,
        thresholds=thresholds,
        canopy=canopy,
        ac_access=ac_access,
        redlining=redlining,
    ).get(cell_id)
