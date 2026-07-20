"""Quality control: range, spike, and flatline checks, gap detection, and node health.

QC never deletes a reading. It *labels* one. A value outside the physically plausible range,
an isolated spike, or a stuck-sensor flatline is tagged so the map and the export can show it
as provisional instead of dressing it up as fact. The only thing that is ever discarded is a
payload too malformed to parse — and that is quarantined by ``ingest``, not here.

Every check is a pure function over already-parsed observations, so the whole QC layer is
unit-testable offline against recorded streams with no hardware and no clock.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from itertools import pairwise
from pathlib import Path
from statistics import median, pstdev

from . import integrity
from .calibrate import CorrectionRegistry
from .config import TwinWindow
from .models import (
    PARAMETERS,
    QC_FLATLINE,
    QC_OK,
    QC_RANGE,
    QC_REJECTED,
    QC_SPIKE,
    RAW,
    Observation,
    parse_timestamp,
)

# Per-parameter spike threshold: a reading that departs from the median of its immediate
# neighbours by more than this (in the parameter's unit) is an isolated spike. Conservative
# on purpose — real heat and smoke events are gradual at a five-minute cadence.
_SPIKE_THRESHOLD: dict[str, float] = {
    "temp_c": 8.0,
    "humidity_pct": 30.0,
    "pm25_ugm3": 150.0,
    "pm10_ugm3": 250.0,
    "no2_ppb": 200.0,
    "heat_index_c": 10.0,
    "wbgt_c": 10.0,
}

#: A run of this many identical consecutive values reads as a stuck sensor.
FLATLINE_RUN = 6


def range_flag(obs: Observation) -> str:
    """``QC_RANGE`` if the value is outside the parameter's plausible bounds, else ``QC_OK``."""
    param = PARAMETERS.get(obs.parameter)
    if param is None:
        return QC_OK
    if obs.value < param.valid_min or obs.value > param.valid_max:
        return QC_RANGE
    return QC_OK


def _flag_spikes(series: list[Observation], flags: list[str], n: int) -> None:
    """Mark isolated departures from the local median of the two neighbours, in place.

    Only QC-clean neighbours count — an already-flagged out-of-range neighbour would drag the
    median and mislabel a perfectly valid reading next to a fault as a spike.
    """
    threshold = _SPIKE_THRESHOLD.get(series[0].parameter) if series else None
    if threshold is None:
        return
    for i in range(1, n - 1):
        if flags[i] != QC_OK:
            continue
        neighbours = [series[j].value for j in (i - 1, i + 1) if flags[j] == QC_OK]
        if not neighbours:
            continue  # both neighbours are faulty — no clean baseline to judge against
        local = median(neighbours)
        if abs(series[i].value - local) > threshold:
            flags[i] = QC_SPIKE


def _flag_flatline(series: list[Observation], flags: list[str], n: int) -> None:
    """Mark a run of ``FLATLINE_RUN`` identical values as a stuck sensor, in place."""
    run_start = 0
    for i in range(1, n + 1):
        if i < n and series[i].value == series[run_start].value:
            continue
        if i - run_start >= FLATLINE_RUN:
            for j in range(run_start, i):
                if flags[j] == QC_OK:
                    flags[j] = QC_FLATLINE
        run_start = i


def _series_flags(series: list[Observation]) -> list[str]:
    """Flag one node/parameter series (assumed timestamp-sorted)."""
    n = len(series)
    flags = [range_flag(o) for o in series]
    _flag_spikes(series, flags, n)
    _flag_flatline(series, flags, n)
    return flags


def apply(observations: Iterable[Observation]) -> list[Observation]:
    """Return the observations with QC verdicts set, evaluated per node/parameter series."""
    grouped: dict[tuple[str, str], list[Observation]] = defaultdict(list)
    for obs in observations:
        grouped[(obs.node_id, obs.parameter)].append(obs)

    out: list[Observation] = []
    for series in grouped.values():
        series.sort(key=lambda o: parse_timestamp(o.timestamp))
        flags = _series_flags(series)
        out.extend(obs.with_qc(flag) for obs, flag in zip(series, flags, strict=True))
    out.sort(key=lambda o: (o.node_id, o.parameter, o.timestamp))
    return out


@dataclass(frozen=True)
class Gap:
    """A stretch where a node reported nothing for longer than the sampling interval."""

    node_id: str
    parameter: str
    start: str
    end: str
    seconds: float


def detect_gaps(
    observations: Iterable[Observation], expected_interval_s: float, tolerance: float = 1.5
) -> list[Gap]:
    """Find gaps longer than ``expected_interval_s * tolerance`` in each node/parameter series."""
    grouped: dict[tuple[str, str], list[Observation]] = defaultdict(list)
    for obs in observations:
        grouped[(obs.node_id, obs.parameter)].append(obs)

    gaps: list[Gap] = []
    limit = expected_interval_s * tolerance
    for (node_id, parameter), series in grouped.items():
        series.sort(key=lambda o: parse_timestamp(o.timestamp))
        for prev, cur in pairwise(series):
            delta = (
                parse_timestamp(cur.timestamp) - parse_timestamp(prev.timestamp)
            ).total_seconds()
            if delta > limit:
                gaps.append(Gap(node_id, parameter, prev.timestamp, cur.timestamp, delta))
    gaps.sort(key=lambda g: g.seconds, reverse=True)
    return gaps


@dataclass(frozen=True)
class TwinAgreement:
    """Inter-sensor agreement between two co-located low-cost nodes over a :class:`TwinWindow`.

    This bounds **precision**, never accuracy: two twins that agree tightly rule out sensor
    noise as the dominant source of disagreement, but say nothing about whether either twin
    reads *true* — that needs a reference monitor (``calibrate.py``). QC/health metadata only;
    see ``twin_agreement`` and ``docs/calibration.md`` for the "cross-checked ≠ calibrated"
    framing.
    """

    node_a: str
    node_b: str
    parameter: str
    n_pairs: int
    residual_spread: float
    window: TwinWindow


def _window_series(
    obs: list[Observation],
    node_id: str,
    parameter: str,
    start: datetime | None,
    end: datetime | None,
) -> list[Observation]:
    """This node's readings of this parameter within [start, end], timestamp-sorted."""
    series = [
        o
        for o in obs
        if o.node_id == node_id
        and o.parameter == parameter
        and (start is None or parse_timestamp(o.timestamp) >= start)
        and (end is None or parse_timestamp(o.timestamp) <= end)
    ]
    series.sort(key=lambda o: parse_timestamp(o.timestamp))
    return series


def _pair_by_nearest_timestamp(
    series_a: list[Observation], series_b: list[Observation], tol_s: float
) -> list[float]:
    """Greedily pair two timestamp-sorted series by nearest match within ``tol_s`` seconds.

    A merge-style walk (mirrors ``detect_gaps``'s sorted-series approach): each reading pairs
    with at most one reading from the other series, so a twin with a denser cadence than its
    partner does not inflate ``n_pairs`` by matching the same partner reading twice.
    """
    residuals: list[float] = []
    i = j = 0
    while i < len(series_a) and j < len(series_b):
        delta = parse_timestamp(series_b[j].timestamp) - parse_timestamp(series_a[i].timestamp)
        delta_s = delta.total_seconds()
        if abs(delta_s) <= tol_s:
            residuals.append(series_a[i].value - series_b[j].value)
            i += 1
            j += 1
        elif delta_s < 0:
            j += 1
        else:
            i += 1
    return residuals


def twin_agreement(
    observations: Iterable[Observation],
    twin_windows: Iterable[TwinWindow],
    *,
    tol_s: float = 300.0,
) -> list[TwinAgreement]:
    """Cross-checked precision tier: how well co-located low-cost twins agree with each other.

    For each configured :class:`TwinWindow`, both nodes' readings of the same parameter within
    ``[start, end]`` are paired by nearest timestamp (within ``tol_s`` seconds) and the spread
    of the paired residuals (``value_a - value_b``) is reported alongside how many pairs
    matched. A tight spread bounds **precision** — the twins agree with each other — never
    **accuracy** — whether either twin reads true, which only a reference-monitor co-location
    (``calibrate.py``) can establish. This is annotation only: no :class:`Observation` value is
    touched and no calibration version is assigned (hard rule #3 — values stay raw).
    """
    obs = list(observations)
    results: list[TwinAgreement] = []
    for window in twin_windows:
        start = parse_timestamp(window.start) if window.start else None
        end = parse_timestamp(window.end) if window.end else None
        series_a = _window_series(obs, window.node_a, window.parameter, start, end)
        series_b = _window_series(obs, window.node_b, window.parameter, start, end)
        residuals = _pair_by_nearest_timestamp(series_a, series_b, tol_s)
        spread = round(pstdev(residuals), 6) if residuals else 0.0
        results.append(
            TwinAgreement(
                node_a=window.node_a,
                node_b=window.node_b,
                parameter=window.parameter,
                n_pairs=len(residuals),
                residual_spread=spread,
                window=window,
            )
        )
    return results


@dataclass(frozen=True)
class NodeHealth:
    """A node's liveness and data-quality summary, for the operator dashboard."""

    node_id: str
    observations: int
    last_seen: str
    ok: int
    flagged: int
    online: bool
    completeness: float = 1.0  # observed / expected readings over the node's reporting span

    @property
    def flagged_fraction(self) -> float:
        return self.flagged / self.observations if self.observations else 0.0

    @property
    def status(self) -> str:
        """``offline`` / ``degraded`` / ``ok`` — a node that backfilled but missed a stretch, or
        flags many readings, reads as degraded even though its last reading is recent."""
        if not self.online:
            return "offline"
        if self.completeness < 0.95 or self.flagged_fraction > 0.1:
            return "degraded"
        return "ok"


def _twin_agreement_json(agreements: list[TwinAgreement]) -> list[dict[str, object]]:
    return [
        {
            "node_a": a.node_a,
            "node_b": a.node_b,
            "parameter": a.parameter,
            "n_pairs": a.n_pairs,
            "residual_spread": a.residual_spread,
            "window_start": a.window.start,
            "window_end": a.window.end,
        }
        for a in agreements
    ]


#: Default drift horizon, in days, past a correction's co-location ``window_end`` after which the
#: health report flags its output as *aging*. Low-cost sensors drift within months, so a correction
#: fit from a window that closed over a year ago is stale evidence for a value published today —
#: see ``docs/RESEARCH-ROADMAP.md`` **[drift]** (long-term low-cost-sensor evaluation; NYC mesonet
#: network re-calibration; community-network data discontinuity). This is a *descriptive* horizon:
#: crossing it never changes a calibrated value or demotes it to provisional (hard rule #3) — it
#: only marks the correction behind that value as due for re-co-location.
CALIBRATION_DRIFT_HORIZON_DAYS = 365.0


@dataclass(frozen=True)
class CorrectionAge:
    """How old one node/parameter correction is, measured against the latest observation.

    ``age_days`` is the gap in days between the correction's co-location ``window_end`` and the most
    recent observation in the data; ``aging`` is True once that gap exceeds the drift horizon. This
    is drift *surveillance* only — it never touches an :class:`Observation`'s value or its
    ``calibration`` state (hard rule #3), so a node's readings stay exactly as calibrated (or raw)
    as they were; it merely reports how old the evidence behind them is.
    """

    node_id: str
    parameter: str
    version: str
    window_end: str
    age_days: float
    aging: bool


def correction_ages(
    observations: Iterable[Observation],
    registry: CorrectionRegistry,
    *,
    horizon_days: float = CALIBRATION_DRIFT_HORIZON_DAYS,
) -> list[CorrectionAge]:
    """Report each registered correction's age against the latest observation, flagging drift.

    For every correction in ``registry`` (one per calibrated node/parameter) that carries a
    co-location ``window_end``, the age is ``latest_observation - window_end`` in days and ``aging``
    is True when that age exceeds ``horizon_days`` (default :data:`CALIBRATION_DRIFT_HORIZON_DAYS`,
    365 days, cited to ``docs/RESEARCH-ROADMAP.md`` **[drift]**: low-cost sensors drift within
    months, so a correction fit long ago is stale evidence for a value published today). Corrections
    with no recorded ``window_end`` are skipped — there is no anchor to measure their age from.

    Read-side and descriptive only. It finally *consults* ``window_end`` (stored since calibration
    shipped in Phase 2, never read until now) but changes no value and assigns no calibration state:
    a correction being ``aging`` does not demote its output to provisional (hard rule #3), and it is
    never a ranking of neighborhoods — it is a per-correction maintenance signal, ordered by the
    registry's own sorted node/parameter key. Returns ``[]`` when there is no observation to anchor
    "how long ago" against.
    """
    obs = list(observations)
    if not obs:
        return []
    latest = parse_timestamp(max(o.timestamp for o in obs))
    ages: list[CorrectionAge] = []
    for c in registry.all():
        if not c.window_end:
            continue
        age = (latest - parse_timestamp(c.window_end)).total_seconds() / 86400.0
        ages.append(
            CorrectionAge(
                node_id=c.node_id,
                parameter=c.parameter,
                version=c.version,
                window_end=c.window_end,
                age_days=round(age, 1),
                aging=age > horizon_days,
            )
        )
    return ages


def calibration_block(
    observations: Iterable[Observation],
    registry: CorrectionRegistry,
    *,
    horizon_days: float = CALIBRATION_DRIFT_HORIZON_DAYS,
) -> dict[str, object]:
    """The JSON-able ``calibration`` block of :func:`health_report`: per-correction drift ages.

    Wraps :func:`correction_ages` with a fresh/aging count and the standing "descriptive, never a
    ranking, never a value change" caveat, so the same block can ride along in the health report and
    in ``swelter qc --json`` without either surface restating its shape.
    """
    ages = correction_ages(observations, registry, horizon_days=horizon_days)
    aging = sum(1 for a in ages if a.aging)
    return {
        "horizon_days": horizon_days,
        "summary": {"corrections": len(ages), "aging": aging, "fresh": len(ages) - aging},
        "corrections": [
            {
                "node_id": a.node_id,
                "parameter": a.parameter,
                "version": a.version,
                "window_end": a.window_end,
                "age_days": a.age_days,
                "aging": a.aging,
            }
            for a in ages
        ],
        "note": (
            "Descriptive drift surveillance — the age of each correction's co-location evidence "
            "against the latest observation. It never changes a calibrated value or its state "
            "(hard rule #3: a correction being aging does not demote its output to provisional), "
            "and it is never a ranking of neighborhoods, only a per-correction recalibration "
            "signal."
        ),
    }


def _attach_side_blocks(
    report: dict[str, object],
    obs: list[Observation],
    *,
    coverage: dict[str, object] | None,
    store_dir: str | Path | None,
    twins: list[TwinWindow],
    registry: CorrectionRegistry | None,
    calibration_horizon_days: float,
) -> None:
    """Attach the optional side-reads that ride along in :func:`health_report` when their input is
    given — coverage-equity, the integrity chain head, twin agreement, and calibration drift. Each
    is additive and absent by default, so a caller configuring none gets the base health JSON, and
    both the empty-observations and populated code paths share exactly one attach implementation."""
    if coverage is not None:
        report["coverage_equity"] = coverage
    if store_dir is not None:
        report["integrity"] = _integrity_block(store_dir)
    if twins:
        report["twin_agreement"] = _twin_agreement_json(twin_agreement(obs, twins))
    if registry is not None:
        report["calibration"] = calibration_block(
            obs, registry, horizon_days=calibration_horizon_days
        )


def health_report(
    observations: Iterable[Observation],
    *,
    expected_interval_s: float = 3600.0,
    max_gaps: int = 10,
    coverage: dict[str, object] | None = None,
    store_dir: str | Path | None = None,
    twin_windows: Iterable[TwinWindow] = (),
    registry: CorrectionRegistry | None = None,
    calibration_horizon_days: float = CALIBRATION_DRIFT_HORIZON_DAYS,
) -> dict[str, object]:
    """A JSON-able network-health summary — per-node status, a count by status, and the worst gaps.

    Backs the ``/api/health.json`` route and the dashboard's coverage panel; computed over raw
    readings. An optional ``coverage`` block (from :func:`coverage_equity`) rides along under
    ``coverage_equity`` so the calibration-coverage read travels with the liveness read. An
    optional ``integrity`` block rides along too when ``store_dir`` is given: the current
    tamper-evidence chain head, read cheaply from ``digests.jsonl`` (:func:`swelter.integrity.
    read_head`) rather than re-hashing the whole store on every request — ``available`` is false
    until a steward runs ``swelter verify-archive --write`` at least once.

    ``twin_windows`` is optional and defaults to empty, so callers that do not configure sensor
    twins get exactly the JSON shape they always have — no ``twin_agreement`` key at all. When
    given, the cross-checked precision tier (:func:`twin_agreement`) rides along under
    ``twin_agreement``. This is QC/health metadata only: it never touches an observation's value
    (hard rule #3) and it bounds precision, never accuracy — see ``docs/calibration.md``.

    ``registry`` is optional too and defaults to ``None``, so callers that pass no correction
    registry get the JSON shape they always had — no ``calibration`` key. When a
    :class:`~swelter.calibrate.CorrectionRegistry` is given, a ``calibration`` block
    (:func:`calibration_block`) rides along: each calibrated node/parameter's correction version,
    its co-location ``window_end``, its age in days against the latest observation, and an ``aging``
    flag once that age passes ``calibration_horizon_days`` (default
    :data:`CALIBRATION_DRIFT_HORIZON_DAYS`). This is descriptive drift surveillance only — it reads
    ``window_end`` but changes no value and demotes nothing to provisional (hard rule #3), and it is
    never a ranking of neighborhoods (see :func:`correction_ages`).
    """
    obs = list(observations)
    twins = list(twin_windows)
    if not obs:
        report: dict[str, object] = {
            "interval_s": expected_interval_s,
            "summary": {"total": 0, "ok": 0, "degraded": 0, "offline": 0},
            "nodes": [],
            "gaps": [],
        }
        _attach_side_blocks(
            report,
            obs,
            coverage=coverage,
            store_dir=store_dir,
            twins=twins,
            registry=registry,
            calibration_horizon_days=calibration_horizon_days,
        )
        return report
    latest = max(o.timestamp for o in obs)
    gaps = detect_gaps(obs, expected_interval_s)
    health = node_health(
        obs,
        latest,
        offline_after_s=expected_interval_s * 3,
        expected_interval_s=expected_interval_s,
    )
    summary = {"total": len(health), "ok": 0, "degraded": 0, "offline": 0}
    for h in health:
        summary[h.status] = summary.get(h.status, 0) + 1
    report = {
        "interval_s": expected_interval_s,
        "latest": latest,
        "summary": summary,
        "nodes": [
            {
                "node_id": h.node_id,
                "status": h.status,
                "observations": h.observations,
                "completeness": h.completeness,
                "flagged_fraction": round(h.flagged_fraction, 3),
                "online": h.online,
                "last_seen": h.last_seen,
            }
            for h in health
        ],
        "gaps": [
            {
                "node_id": g.node_id,
                "parameter": g.parameter,
                "start": g.start,
                "end": g.end,
                "minutes": round(g.seconds / 60),
            }
            for g in gaps[:max_gaps]
        ],
    }
    _attach_side_blocks(
        report,
        obs,
        coverage=coverage,
        store_dir=store_dir,
        twins=twins,
        registry=registry,
        calibration_horizon_days=calibration_horizon_days,
    )
    return report


def _integrity_block(store_dir: str | Path) -> dict[str, object]:
    """The ``integrity`` block of :func:`health_report`: current chain head, cheaply."""
    head = integrity.read_head(store_dir)
    if head is None:
        return {"available": False}
    return {
        "available": True,
        "head": head.get("head"),
        "last_verified_day": head.get("last_day"),
        "days": head.get("days"),
    }


def coverage_equity(
    observations: Iterable[Observation],
    node_cells: Mapping[str, tuple[str, str]],
) -> dict[str, object]:
    """Calibrated-vs-raw node counts per published cell — the coverage-equity read.

    The fairness stake in a community network is geographic: *which cells get a calibrated
    (trustworthy) reading and which get only a provisional (raw / uncalibrated) one?* If the
    calibrated nodes cluster in one part of the network and the raw nodes in another, the map
    splits into a confident half and a provisional half. This surfaces that distribution from
    data already on hand — per published grid cell (``node_cells`` maps each placed node to its
    cell id and label), how many of its nodes are calibrated vs still raw, and whether the cell
    has any calibrated node at all — so a steward can see where the next co-location should go
    (Responsible-tech audit B3).

    It is **descriptive coverage of calibration, not a ranking of neighborhoods** and not a claim
    about who is most exposed. Whether a coverage gap correlates with the frontline blocks the
    network is for (audit B4) needs demographic/redlining context swelter deliberately does not
    hold, and is a governance judgment, never a number emitted here. A node is counted calibrated
    when it has at least one calibrated (non-``raw``) observation in the data passed in.
    """
    calibrated_nodes = {o.node_id for o in observations if o.calibration != RAW}
    counts: dict[str, list[int]] = {}  # cell_id -> [nodes, calibrated, raw]
    label_of: dict[str, str] = {}
    for node_id, (cell_id, label) in node_cells.items():
        if cell_id not in counts:
            counts[cell_id] = [0, 0, 0]
            label_of[cell_id] = label
        tally = counts[cell_id]
        tally[0] += 1
        if node_id in calibrated_nodes:
            tally[1] += 1
        else:
            tally[2] += 1

    cells: list[dict[str, object]] = []
    for cell_id in sorted(counts):
        nodes, calibrated, raw = counts[cell_id]
        cells.append(
            {
                "cell_id": cell_id,
                "label": label_of[cell_id],
                "nodes": nodes,
                "calibrated_nodes": calibrated,
                "raw_nodes": raw,
                "confirmed": calibrated > 0,
            }
        )

    n_cells = len(counts)
    confirmed_cells = sum(1 for t in counts.values() if t[1] > 0)
    n_nodes = sum(t[0] for t in counts.values())
    calibrated_total = sum(t[1] for t in counts.values())
    summary: dict[str, object] = {
        "cells": n_cells,
        "confirmed_cells": confirmed_cells,
        "provisional_cells": n_cells - confirmed_cells,
        "nodes": n_nodes,
        "calibrated_nodes": calibrated_total,
        "raw_nodes": n_nodes - calibrated_total,
        "calibrated_node_fraction": round(calibrated_total / n_nodes, 3) if n_nodes else 0.0,
        "confirmed_cell_fraction": round(confirmed_cells / n_cells, 3) if n_cells else 0.0,
        # True when at least one cell has no calibrated node yet — a coverage gap to close, not a
        # statement about which neighborhood it lands on (see the docstring and audit B4).
        "coverage_gap": confirmed_cells < n_cells,
    }
    return {
        "summary": summary,
        "cells": cells,
        "note": (
            "Descriptive coverage of calibration, not a ranking of neighborhoods. Whether a "
            "coverage gap correlates with frontline blocks (audit B4) needs external context "
            "swelter does not hold and is a governance decision."
        ),
    }


def node_health(
    observations: Iterable[Observation],
    latest_timestamp: str,
    offline_after_s: float,
    *,
    expected_interval_s: float = 3600.0,
) -> list[NodeHealth]:
    """Summarise each node: how much it reported, how clean, whether it is live, and how complete
    its record is (so a mid-window outage shows as degraded, not silently healthy)."""
    by_node: dict[str, list[Observation]] = defaultdict(list)
    for obs in observations:
        by_node[obs.node_id].append(obs)

    now = parse_timestamp(latest_timestamp)
    health: list[NodeHealth] = []
    for node_id, obs_list in sorted(by_node.items()):
        times = sorted(parse_timestamp(o.timestamp) for o in obs_list)
        last_seen = max(obs_list, key=lambda o: parse_timestamp(o.timestamp)).timestamp
        flagged = sum(1 for o in obs_list if o.qc in QC_REJECTED)
        silent_for = (now - parse_timestamp(last_seen)).total_seconds()
        span = (times[-1] - times[0]).total_seconds()
        n_params = len({o.parameter for o in obs_list}) or 1
        expected = (span / expected_interval_s + 1) * n_params
        completeness = min(1.0, len(obs_list) / expected) if expected else 1.0
        health.append(
            NodeHealth(
                node_id=node_id,
                observations=len(obs_list),
                last_seen=last_seen,
                ok=len(obs_list) - flagged,
                flagged=flagged,
                online=silent_for <= offline_after_s,
                completeness=round(completeness, 3),
            )
        )
    return health
