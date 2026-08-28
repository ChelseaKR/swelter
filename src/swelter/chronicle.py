"""Post-event chronicle: a citable, descriptive account of one heat/air event window.

Officials and health departments act on *events*, not dashboards. This module answers, for a
closed ``[from, to]`` UTC window and per published cell: how many cell-hours the heat index reached
the NWS "Danger"/"Extreme Danger" tier, how many cell-hours had both heat *and* air elevated
(compound exposure), what share of the published cell-hour readings were calibrated rather than
provisional, and how much of the Danger count itself rests on readings the pipeline does not trust
as measurements. It is the institution-facing, event-scoped sibling of :mod:`swelter.exposure_brief`
(the resident-facing historical brief): different audience, same honesty discipline.

It composes existing pipeline outputs and adds no new measurement of its own — the surface comes
from :func:`swelter.aggregate.aggregate`, the reporting gaps from :func:`swelter.qc.detect_gaps`,
the per-cell calibration coverage from :func:`swelter.qc.coverage_equity`, and the "Danger" tier
and compound flag from :mod:`swelter.models` (via the aggregated heat-index and derived exposure
cells). The only I/O is reading the store passed to :func:`build_chronicle`; everything else is a
pure function over already-parsed observations, so the whole thing is testable offline.

**Two hard limits, by design.** A chronicle reports *counts and hours only*. It never attributes a
health outcome to an exposure, and it never ranks, scores, or compares neighborhoods — the same
refusal :func:`swelter.qc.coverage_equity` already encodes (whether a coverage gap lands on a
frontline block needs external context swelter does not hold, and is a governance judgment, not a
number emitted here; see ADR 0009 and ADR 0018). And uncertainty is not a footnote: the calibrated-
vs-provisional share, the Danger hours resting on untrusted readings, and the "what the network
could not see" section are first-class, and the last is *always rendered* — a chronicle with zero
gaps still says so, so "we saw nothing wrong" and "we could not see" are never collapsed by
omission (ADR 0046).
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

from . import aggregate, qc
from .aggregate import AQI_WINDOW_NOWCAST, EXPOSURE, CellReading, Surface
from .config import NetworkConfig
from .models import RAW, Observation, heat_index_category
from .store import Store

#: The parameter the NWS "Danger" tiers are read off — the same one the alerts feed and the
#: exposure brief count "Danger" on, so the three views can never quietly disagree about it.
DANGER_PARAMETER = "heat_index_c"

#: Heat-index concern level (from :func:`swelter.models.heat_index_category`) at or above which the
#: NWS name is "Danger" (3) or, higher still, "Extreme Danger" (4).
_DANGER_LEVEL = 3
_EXTREME_DANGER_LEVEL = 4


@dataclass(frozen=True)
class CellChronicle:
    """One published cell's descriptive event record over the chronicle window.

    Every field is a plain count of hours or readings — never a rank, a score, or an attribution.
    ``observed_hours`` is the count of distinct hourly buckets in which the cell published any
    directly-measured reading; ``danger_hours`` and ``compound_hours`` are subsets of those hours.

    ``danger_hours_provisional`` and ``danger_hours_qc_flagged`` are subsets of ``danger_hours``
    saying how much of that count swelter vouches for. ``extreme_danger_hours`` is itself a subset
    of ``danger_hours``, so those two caveats bound it as well.
    """

    cell_id: str
    label: str
    lat: float
    lon: float
    observed_hours: int
    danger_hours: int
    extreme_danger_hours: int
    compound_hours: int
    calibrated_readings: int
    provisional_readings: int
    danger_hours_provisional: int = 0  # of danger_hours, how many came from a provisional reading
    danger_hours_qc_flagged: int = 0  # of those, how many were QC flagged (spike/flatline)

    @property
    def total_readings(self) -> int:
        return self.calibrated_readings + self.provisional_readings

    @property
    def calibrated_share(self) -> float | None:
        """Fraction of this cell's published readings that were calibrated, or ``None`` if none."""
        total = self.total_readings
        return self.calibrated_readings / total if total else None


def _measured_reading(cell: CellReading) -> bool:
    """A directly-measured surface reading — not the derived exposure layer, not a NowCast alt.

    The exposure layer is an ordinal combination (counted separately for compound hours) and the
    NowCast row is an alternate view of the same PM2.5 bucket, so counting either as a distinct
    published reading would double-count the cell-hour.
    """
    return cell.parameter != EXPOSURE and cell.aqi_window != AQI_WINDOW_NOWCAST


class _Tally:
    """Per-cell accumulators for one pass over the surface (used by :func:`_cell_chronicles`)."""

    def __init__(self) -> None:
        self.observed: dict[str, set[str]] = defaultdict(set)
        self.danger: dict[str, set[str]] = defaultdict(set)
        self.extreme: dict[str, set[str]] = defaultdict(set)
        self.compound: dict[str, set[str]] = defaultdict(set)
        self.danger_provisional: dict[str, set[str]] = defaultdict(set)
        self.danger_flagged: dict[str, set[str]] = defaultdict(set)
        self.calibrated: dict[str, int] = defaultdict(int)
        self.provisional: dict[str, int] = defaultdict(int)
        self.meta: dict[str, CellReading] = {}

    def add(self, cell: CellReading) -> None:
        cid = cell.cell_id
        self.meta.setdefault(cid, cell)
        if cell.parameter == EXPOSURE:
            if cell.compound:
                self.compound[cid].add(cell.bucket)
            return
        if not _measured_reading(cell):
            return
        self.observed[cid].add(cell.bucket)
        if cell.provisional:
            self.provisional[cid] += 1
        else:
            self.calibrated[cid] += 1
        if cell.parameter == DANGER_PARAMETER:
            level = heat_index_category(cell.mean)[0]
            if level >= _DANGER_LEVEL:
                self.danger[cid].add(cell.bucket)
                # A Danger hour is still counted whatever its QC state (ADR 0029: a suspicious
                # reading during a real event is exactly what a chronicle must not lose). What
                # gets recorded beside it is how much of the count rests on evidence the pipeline
                # does not trust as a measurement.
                if cell.provisional:
                    self.danger_provisional[cid].add(cell.bucket)
                if cell.qc_flags:
                    self.danger_flagged[cid].add(cell.bucket)
            if level >= _EXTREME_DANGER_LEVEL:
                self.extreme[cid].add(cell.bucket)


def _cell_chronicles(surface: Surface) -> list[CellChronicle]:
    """Reduce a surface to one :class:`CellChronicle` per published cell, sorted by cell id."""
    tally = _Tally()
    for cell in surface.cells:
        tally.add(cell)
    out: list[CellChronicle] = []
    for cid in sorted(tally.meta):
        meta = tally.meta[cid]
        out.append(
            CellChronicle(
                cell_id=cid,
                label=meta.label,
                lat=meta.lat,
                lon=meta.lon,
                observed_hours=len(tally.observed[cid]),
                danger_hours=len(tally.danger[cid]),
                extreme_danger_hours=len(tally.extreme[cid]),
                compound_hours=len(tally.compound[cid]),
                calibrated_readings=tally.calibrated[cid],
                provisional_readings=tally.provisional[cid],
                danger_hours_provisional=len(tally.danger_provisional[cid]),
                danger_hours_qc_flagged=len(tally.danger_flagged[cid]),
            )
        )
    return out


def _summary_int(coverage: dict[str, object], key: str) -> int:
    summary = coverage.get("summary")
    if isinstance(summary, dict):
        value = summary.get(key)
        if isinstance(value, int):
            return value
    return 0


def _source_digest(observations: Iterable[Observation]) -> str:
    """A deterministic sha256 over the window's observations, so every number is citable.

    Hashing the sorted per-observation content hashes makes the digest order-independent and
    reproducible: the same window of the same store always yields the same digest, and any changed,
    added, or removed reading changes it — the anchor a memo can cite the chronicle's figures to.
    """
    digest = hashlib.sha256()
    for content_hash in sorted(o.content_hash() for o in observations):
        digest.update(content_hash.encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


@dataclass(frozen=True)
class Chronicle:
    """A citable, descriptive chronicle of one ``[from, to]`` UTC heat/air event window.

    Holds per-cell counts, the reporting gaps and calibration-coverage the network could *not*
    resolve, and a content digest of the source observations. :meth:`to_markdown` renders it.
    """

    network: str
    window_start: str
    window_end: str
    interval_s: float
    cells: tuple[CellChronicle, ...]
    gaps: tuple[qc.Gap, ...]
    published_cells: int
    provisional_cells: int
    coverage_note: str
    source_digest: str

    @property
    def danger_hours(self) -> int:
        return sum(c.danger_hours for c in self.cells)

    @property
    def extreme_danger_hours(self) -> int:
        return sum(c.extreme_danger_hours for c in self.cells)

    @property
    def danger_hours_provisional(self) -> int:
        return sum(c.danger_hours_provisional for c in self.cells)

    @property
    def danger_hours_qc_flagged(self) -> int:
        return sum(c.danger_hours_qc_flagged for c in self.cells)

    @property
    def compound_hours(self) -> int:
        return sum(c.compound_hours for c in self.cells)

    @property
    def calibrated_readings(self) -> int:
        return sum(c.calibrated_readings for c in self.cells)

    @property
    def provisional_readings(self) -> int:
        return sum(c.provisional_readings for c in self.cells)

    @property
    def total_readings(self) -> int:
        return self.calibrated_readings + self.provisional_readings

    @property
    def calibrated_share(self) -> float | None:
        total = self.total_readings
        return self.calibrated_readings / total if total else None

    def _headline(self) -> list[str]:
        share = self.calibrated_share
        share_txt = f"{share * 100:.0f}%" if share is not None else "not applicable"
        return [
            "## Headline",
            "",
            (
                f"Across {len(self.cells)} published cell(s), the heat index reached the NWS "
                f"Danger or Extreme Danger tier in {self.danger_hours} cell-hour(s) "
                f"({self.extreme_danger_hours} of them at Extreme Danger); {self.compound_hours} "
                f"cell-hour(s) had both heat and air elevated (compound exposure). "
                f"{self.calibrated_readings} of {self.total_readings} published cell-hour "
                f"reading(s) were calibrated ({share_txt}); the remaining "
                f"{self.provisional_readings} are provisional (uncalibrated). "
                f"{self.danger_hours_provisional} of the Danger cell-hour(s) came from a "
                f"provisional reading, and {self.danger_hours_qc_flagged} of those from a reading "
                "QC flagged as suspicious (a spike or a flatline). These are descriptive counts "
                "of measured hours — not a health-outcome estimate, and not a ranking, score, or "
                "comparison of any neighborhood."
            ),
            "",
            f"Source digest (sha256 of the window's observations): `{self.source_digest}`.",
        ]

    def _per_cell_table(self) -> list[str]:
        lines = [
            "## Per published cell",
            "",
            (
                "| Cell | Danger hours | Danger hours provisional | Danger hours QC-flagged "
                "| Extreme Danger hours | Compound hours | Observed hours | Calibrated share |"
            ),
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
        for cell in self.cells:
            share = cell.calibrated_share
            share_txt = f"{share * 100:.0f}%" if share is not None else "—"
            name = (cell.label or cell.cell_id).replace("|", "\\|")
            lines.append(
                f"| {name} | {cell.danger_hours} | {cell.danger_hours_provisional} "
                f"| {cell.danger_hours_qc_flagged} | {cell.extreme_danger_hours} "
                f"| {cell.compound_hours} | {cell.observed_hours} | {share_txt} |"
            )
        if not self.cells:
            lines.append(
                "| (no published cells reported in this window) | 0 | 0 | 0 | 0 | 0 | 0 | — |"
            )
        return lines

    def _could_not_see(self) -> list[str]:
        """The always-present "what the network could not see" section (never empty by omission)."""
        total = self.total_readings
        prov_pct = f"{self.provisional_readings / total * 100:.0f}%" if total else "0%"
        lines = [
            "## What the network could not see",
            "",
            (
                f"- Provisional coverage: {self.provisional_readings} of {total} published "
                f"cell-hour reading(s) ({prov_pct}) were not calibrated and are shown provisional."
            ),
            (
                f"- Uncalibrated cells: {self.provisional_cells} of {self.published_cells} "
                "published cell(s) had no calibrated node in this window."
            ),
            (
                "- Danger hours resting on untrusted readings: "
                f"{self.danger_hours_provisional} of {self.danger_hours} Danger cell-hour(s) "
                f"came from a provisional reading, and {self.danger_hours_qc_flagged} of those "
                "from a reading QC flagged as a spike or a flatline. Those hours are counted, "
                "not dropped (ADR 0029) — this line says how much of the count is evidence the "
                "pipeline vouches for."
            ),
        ]
        if self.gaps:
            lines.append(
                f"- Reporting gaps ({len(self.gaps)}): a node stopped reporting for longer than "
                f"the {self.interval_s:.0f}s sampling interval —"
            )
            lines.extend(
                f"  - {g.node_id}/{g.parameter}: {g.start} to {g.end} ({round(g.seconds / 60)} min)"
                for g in self.gaps
            )
        else:
            lines.append("- Reporting gaps: none longer than the sampling interval were detected.")
        if self.coverage_note:
            lines.extend(["", f"_{self.coverage_note}_"])
        lines.extend(
            [
                "",
                "_This chronicle reports measured counts and hours only. It does not attribute "
                "health outcomes to any exposure and does not rank, score, or compare "
                "neighborhoods (ADR 0009, ADR 0018)._",
            ]
        )
        return lines

    def to_markdown(self) -> str:
        """Render the chronicle as a self-contained Markdown document a staffer can attach."""
        lines = [
            f"# Event chronicle — {self.network or 'unnamed network'}",
            "",
            f"Window: {self.window_start} to {self.window_end} (UTC), hourly cell rollups.",
            "",
            *self._headline(),
            "",
            *self._per_cell_table(),
            "",
            *self._could_not_see(),
        ]
        return "\n".join(lines) + "\n"


def chronicle_from_observations(
    observations: Iterable[Observation],
    config: NetworkConfig,
    *,
    start: str,
    end: str,
    interval_s: float = 3600.0,
) -> Chronicle:
    """Build a :class:`Chronicle` from already-windowed observations (the pure core).

    ``observations`` are assumed to already fall in ``[start, end]`` (``build_chronicle`` reads
    them from the store with exactly that window). The surface, reporting gaps, and per-cell
    calibration coverage are all derived from these observations alone — no new measurement, no
    external state, no clock.
    """
    obs = list(observations)
    surface = aggregate.aggregate(obs, config)
    raw = [o for o in obs if o.calibration == RAW]
    gaps = qc.detect_gaps(raw, interval_s)
    coverage = qc.coverage_equity(obs, aggregate.node_cell_map(config))
    note = coverage.get("note")
    return Chronicle(
        network=config.name,
        window_start=start,
        window_end=end,
        interval_s=interval_s,
        cells=tuple(_cell_chronicles(surface)),
        gaps=tuple(gaps),
        published_cells=_summary_int(coverage, "cells"),
        provisional_cells=_summary_int(coverage, "provisional_cells"),
        coverage_note=note if isinstance(note, str) else "",
        source_digest=_source_digest(obs),
    )


def build_chronicle(
    store: Store,
    config: NetworkConfig,
    *,
    start: str,
    end: str,
    interval_s: float = 3600.0,
) -> Chronicle:
    """Read the ``[start, end]`` window from ``store`` and build its :class:`Chronicle`.

    The only I/O in the module: it reads observations through the :class:`~swelter.store.Store`
    seam (``since``/``until`` bound the window) and hands them to
    :func:`chronicle_from_observations`.
    """
    observations = store.read(since=start, until=end)
    return chronicle_from_observations(
        observations, config, start=start, end=end, interval_s=interval_s
    )
