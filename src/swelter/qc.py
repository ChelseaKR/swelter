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
from collections.abc import Iterable
from dataclasses import dataclass
from statistics import median

from .models import (
    PARAMETERS,
    QC_FLATLINE,
    QC_OK,
    QC_RANGE,
    QC_REJECTED,
    QC_SPIKE,
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


def _series_flags(series: list[Observation]) -> list[str]:
    """Flag one node/parameter series (assumed timestamp-sorted)."""
    n = len(series)
    flags = [range_flag(o) for o in series]

    # Spike: isolated departure from the local median of the two neighbours.
    threshold = _SPIKE_THRESHOLD.get(series[0].parameter) if series else None
    if threshold is not None:
        for i in range(1, n - 1):
            if flags[i] != QC_OK:
                continue
            local = median([series[i - 1].value, series[i + 1].value])
            if abs(series[i].value - local) > threshold:
                flags[i] = QC_SPIKE

    # Flatline: a run of FLATLINE_RUN identical values means the sensor is stuck.
    run_start = 0
    for i in range(1, n + 1):
        if i < n and series[i].value == series[run_start].value:
            continue
        if i - run_start >= FLATLINE_RUN:
            for j in range(run_start, i):
                if flags[j] == QC_OK:
                    flags[j] = QC_FLATLINE
        run_start = i
    return flags


def apply(observations: Iterable[Observation]) -> list[Observation]:
    """Return the observations with QC verdicts set, evaluated per node/parameter series."""
    grouped: dict[tuple[str, str], list[Observation]] = defaultdict(list)
    for obs in observations:
        grouped[(obs.node_id, obs.parameter)].append(obs)

    out: list[Observation] = []
    for series in grouped.values():
        series.sort(key=lambda o: o.timestamp)
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
        series.sort(key=lambda o: o.timestamp)
        for prev, cur in zip(series, series[1:], strict=False):
            delta = (
                parse_timestamp(cur.timestamp) - parse_timestamp(prev.timestamp)
            ).total_seconds()
            if delta > limit:
                gaps.append(Gap(node_id, parameter, prev.timestamp, cur.timestamp, delta))
    gaps.sort(key=lambda g: g.seconds, reverse=True)
    return gaps


@dataclass(frozen=True)
class NodeHealth:
    """A node's liveness and data-quality summary, for the operator dashboard."""

    node_id: str
    observations: int
    last_seen: str
    ok: int
    flagged: int
    online: bool

    @property
    def flagged_fraction(self) -> float:
        return self.flagged / self.observations if self.observations else 0.0


def node_health(
    observations: Iterable[Observation],
    latest_timestamp: str,
    offline_after_s: float,
) -> list[NodeHealth]:
    """Summarise each node: how much it reported, how clean, and whether it is still live."""
    by_node: dict[str, list[Observation]] = defaultdict(list)
    for obs in observations:
        by_node[obs.node_id].append(obs)

    now = parse_timestamp(latest_timestamp)
    health: list[NodeHealth] = []
    for node_id, obs_list in sorted(by_node.items()):
        last_seen = max(o.timestamp for o in obs_list)
        flagged = sum(1 for o in obs_list if o.qc in QC_REJECTED)
        silent_for = (now - parse_timestamp(last_seen)).total_seconds()
        health.append(
            NodeHealth(
                node_id=node_id,
                observations=len(obs_list),
                last_seen=last_seen,
                ok=len(obs_list) - flagged,
                flagged=flagged,
                online=silent_for <= offline_after_s,
            )
        )
    return health
