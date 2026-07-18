"""Assemble calibration training pairs from stored raw node data and a reference-monitor series.

``swelter colocate`` turns "a node sat beside a reference monitor for a window" into the
:class:`~swelter.calibrate.TrainingPair` evidence a correction is fit from, without anyone hand-
building a co-location file. This module is the pure, offline core of that: given a node's raw
samples and a reference series, it produces the pairs. It touches no network and no clock, so the
pairing rule is fully testable and reproducible (see ADR 0032).

Resampling rule (documented on purpose — timestamp alignment is where a co-location goes subtly
wrong). A reference monitor reports **hourly**; a swelter node samples about **every five minutes**.
So the reference series is the sparser one, and pairing is driven by it: each reference reading is
matched to the single nearest node sample within ``tolerance_s``. This downsamples the dense node
series to the reference cadence — one pair per reference hour — so no single hour is over-weighted
in the least-squares fit. The default tolerance (30 minutes) is far smaller than the reference
spacing, so a node running at normal cadence always has a sample well inside the window, while a
reference hour with no node sample in range yields no pair rather than a guessed one. Ties (a
reference exactly between two node samples) resolve to the earlier node sample, deterministically.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from .calibrate import TrainingPair
from .models import parse_timestamp
from .sources.airnow import ReferenceReading

#: Default pairing tolerance in seconds (±30 min). See the module resampling rule above.
DEFAULT_TOLERANCE_S = 1800.0


@dataclass(frozen=True)
class Sample:
    """A timestamped scalar reading — the common shape both sides reduce to before pairing."""

    timestamp: str
    value: float


def _epoch(timestamp: str) -> float:
    return parse_timestamp(timestamp).timestamp()


def reference_samples(readings: Iterable[ReferenceReading]) -> list[Sample]:
    """Reduce reference readings to timestamp/value samples for pairing."""
    return [Sample(reading.timestamp, reading.value) for reading in readings]


def _nearest_within(
    target: float, node: Sequence[tuple[float, Sample]], tolerance_s: float
) -> Sample | None:
    """The node sample nearest ``target`` (epoch seconds) within ``tolerance_s``.

    ``node`` is pre-sorted ascending by epoch; iterating in order with a strict ``<`` comparison
    keeps the earlier sample when two are equidistant, so the tie-break is deterministic.
    """
    best: Sample | None = None
    best_delta = 0.0
    for epoch, sample in node:
        delta = abs(epoch - target)
        if delta > tolerance_s:
            continue
        if best is None or delta < best_delta:
            best, best_delta = sample, delta
    return best


def pair_reference(
    node_id: str,
    parameter: str,
    node_samples: Sequence[Sample],
    reference: Sequence[Sample],
    *,
    tolerance_s: float = DEFAULT_TOLERANCE_S,
    humidity: Mapping[str, float] | None = None,
    monitor: str = "",
) -> list[TrainingPair]:
    """Pair each reference reading to the nearest node sample within ``tolerance_s`` (pure/offline).

    Returns one :class:`~swelter.calibrate.TrainingPair` per reference reading that has a node
    sample in range, in ascending time order — ``calibrate.read_colocation`` format plus the
    reference ``monitor`` id. Each pair's timestamp is the node sample's own measurement instant
    (what the fit window bounds record). ``humidity`` maps a node timestamp to its humidity,
    attaching the term the PM correction regresses on; a node instant with none carries ``None``.
    """
    indexed = sorted(((_epoch(s.timestamp), s) for s in node_samples), key=lambda item: item[0])
    pairs: list[TrainingPair] = []
    for ref in sorted(reference, key=lambda s: _epoch(s.timestamp)):
        match = _nearest_within(_epoch(ref.timestamp), indexed, tolerance_s)
        if match is None:
            continue
        pairs.append(
            TrainingPair(
                node_id=node_id,
                parameter=parameter,
                timestamp=match.timestamp,
                raw=match.value,
                reference=ref.value,
                humidity=None if humidity is None else humidity.get(match.timestamp),
                monitor=monitor,
            )
        )
    return pairs


def training_pair_to_row(pair: TrainingPair) -> dict[str, object]:
    """Serialize a pair to a ``read_colocation`` JSONL row, omitting absent humidity/monitor.

    Keeping the humidity and monitor keys optional means a temperature co-location with no humidity,
    or a pairing with no named monitor, round-trips through ``calibrate.read_colocation`` unchanged.
    """
    row: dict[str, object] = {
        "node_id": pair.node_id,
        "parameter": pair.parameter,
        "timestamp": pair.timestamp,
        "raw": pair.raw,
        "reference": pair.reference,
    }
    if pair.humidity is not None:
        row["humidity"] = pair.humidity
    if pair.monitor:
        row["monitor"] = pair.monitor
    return row
