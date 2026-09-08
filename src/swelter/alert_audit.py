"""``swelter audit-alerts`` — score every published alert against a reference monitor.

Calibration publishes evidence for *values* (ADR 0002). Nothing published evidence for *alerts*,
and an alert is the loudest claim swelter makes: it goes onto a lobby card, into an Atom feed, and
in front of a resident deciding whether to go outside. A collective handing that to a public-health
partner (#229) will be asked how often it was wrong, and until now the honest answer was that
nobody had checked.

This module checks it. For every hour in the store, every cell reading that crossed the active
hazard pack's floor is a historical alert. Each one is paired with the nearest reference-grade
reading for the same parameter, hour and place, and classified.

Three rules, and the third is the whole point.

**The crossing test is the live one, not a copy of it.** A historical alert is
:func:`swelter.alerts.crossing` applied to a stored cell — the same function the live feed and
``exposure_brief``'s danger-day count call. A second implementation of "what counts as Danger"
would let the audit and the feed drift apart silently, and the audit would then be scoring
something the network never published.

**Only a reference for the same parameter can verify an alert.** AirNow publishes regulatory
PM2.5. It says nothing about a heat index, a wind chill, or the derived exposure level, so an
alert on any of those is unverifiable *by construction* and is reported as such rather than
quietly dropped from the denominator or, worse, counted as correct.

**Unverifiable is a first-class outcome and never a score.** An alert with no reference in range
was not confirmed and was not contradicted; it was not checked. It is counted in its own column,
excluded from precision, and when a parameter has no scored alerts at all the precision field is
``None`` with the reason stated — never ``0.0``, and never ``1.0``. Publishing a rate over an
empty denominator is exactly the defect ADR 0037 exists to prevent, in an accuracy metric's
clothing.

Two things this deliberately does not do. It does not claim **recall**: reference coverage is far
too sparse to say how many real episodes the network missed, and the rendered document says so
rather than leaving a reader to assume the precision table is the whole picture. And it never
changes a threshold: the audit is evidence for a steward, not a controller.

Everything is offline and free of the wall clock — the window comes from ``--since``/``--until``
or from the data, so two runs over an unchanged store are byte-identical.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Final

from . import hazard_packs
from .aggregate import AQI_WINDOW_NOWCAST, EXPOSURE, CellReading, Surface
from .alerts import crossing, resolve_thresholds
from .colocate import DEFAULT_TOLERANCE_S
from .config import NetworkConfig, haversine_m
from .models import parse_timestamp, pm25_aqi
from .sources.airnow import ReferenceReading

__all__ = [
    "AUDIT_SCHEMA_VERSION",
    "CLASS_CONFIRMED",
    "CLASS_CONTRADICTED",
    "CLASS_UNVERIFIABLE",
    "DEFAULT_MAX_DISTANCE_M",
    "AlertAudit",
    "AuditedAlert",
    "ParameterScore",
    "audit_alerts",
    "render_markdown",
    "wilson_interval",
]

AUDIT_SCHEMA_VERSION: Final = "swelter.alert-audit/1"

#: The alert was checked against a reference reading that also crossed the same floor.
CLASS_CONFIRMED: Final = "confirmed"
#: The alert was checked against a reference reading that did not cross the floor.
CLASS_CONTRADICTED: Final = "contradicted"
#: The alert could not be checked at all. Not a failure and not a pass — an unmeasured claim.
CLASS_UNVERIFIABLE: Final = "unverifiable"

#: How far a regulatory monitor may sit from a published cell and still be treated as speaking
#: about it, in metres. **This is swelter's own choice, not a standard**, and it is stated as such
#: wherever it is published: no published rule says at what distance a PM2.5 monitor stops
#: representing an airshed, because it depends on terrain, sources and the day's meteorology. It is
#: a parameter for exactly that reason, and a run records the value it used.
DEFAULT_MAX_DISTANCE_M: Final = 10_000.0

#: z for a two-sided 95% interval. A constant of the interval's definition, not a tuning knob.
_Z_95: Final = 1.959963984540054

#: Reasons an alert could not be checked. Each is a distinct sentence because they lead a steward
#: somewhere different: buy a reference feed, site a monitor closer, or accept that this hazard has
#: no regulatory counterpart at all.
_NO_REFERENCE_PARAMETER: Final = (
    "no reference reading in this run is for {parameter}; a regulatory monitor that measures "
    "another parameter cannot confirm or contradict this alert"
)
_NO_DECLARED_MONITOR: Final = (
    "{parameter} reference readings are present, but none of them is from a monitor this "
    "network declares in reference_monitors ({declared}); the readings and the configuration "
    "disagree about which monitor this is"
)
_NO_MONITOR_COORDINATE: Final = (
    "the nearest reference monitor for {parameter} publishes no coordinate, so its distance to "
    "this cell is unknown rather than zero"
)
_NO_MONITOR_IN_RANGE: Final = (
    "no reference monitor for {parameter} is within {max_distance_m:.0f} m of this cell"
)
_NO_READING_IN_WINDOW: Final = (
    "reference monitor {monitor_id} is in range but published no {parameter} reading within "
    "{tolerance_s:.0f} s of this hour"
)


@dataclass(frozen=True)
class AuditedAlert:
    """One historical alert and the verdict on it, with everything the verdict rests on."""

    area_id: str
    area: str
    lat: float
    lon: float
    parameter: str
    bucket: str
    value: float
    unit: str
    severity: str
    threshold: float
    provisional: bool
    classification: str
    #: Present only on ``unverifiable`` — which of the four distinct reasons applies.
    reason: str | None = None
    monitor_id: str | None = None
    monitor_label: str | None = None
    monitor_distance_m: float | None = None
    reference_timestamp: str | None = None
    reference_value: float | None = None
    #: Whether the reference reading itself crossed the same floor. ``None`` when unverifiable.
    reference_crossed: bool | None = None
    #: The calibration method(s) behind the alerting cell and the reference(s) they were fitted
    #: against, carried **verbatim** from :class:`~swelter.aggregate.CellReading`. A contradiction
    #: can then be traced to how the value was produced rather than to whatever fit happens to be
    #: current when the audit runs.
    #:
    #: Deliberately the cell's own strings and not a re-parsed list. The first version of this
    #: field re-split ``cell.method`` on ``", "`` and called the result "calibration versions" --
    #: two errors at once. ``aggregate`` joins those methods with ``" / "``, so the split never
    #: split and published a single joined string as if it were one method; and they are method
    #: names (``ols``), not correction version ids. Re-deriving a list from a display string is
    #: the fragile step, so it is not done at all.
    #:
    #: Worth recording what a control measured here, because it is not what one would guess.
    #: Re-introducing *only* the round-trip -- ``", ".join(method.split(", "))`` -- leaves the
    #: suite **green**, because that round-trip is the identity on any string not containing
    #: ``", "``. The wrong separator is genuinely unobservable on its own. What the guard test
    #: catches is the *shape and the name*: a tuple published under a key that claims versions.
    #: So this is a case where the obvious sabotage cannot fail and the useful one is a different
    #: mutation entirely.
    calibration_method: str | None = None
    calibrated_against: str | None = None
    nodes: tuple[str, ...] = ()

    def as_record(self) -> dict[str, object]:
        record: dict[str, object] = {
            "area_id": self.area_id,
            "area": self.area,
            "lat": self.lat,
            "lon": self.lon,
            "parameter": self.parameter,
            "bucket": self.bucket,
            "value": self.value,
            "unit": self.unit,
            "severity": self.severity,
            "threshold": self.threshold,
            "provisional": self.provisional,
            "classification": self.classification,
            # Published as an explicit null rather than omitted, so a consumer reads one stable
            # shape and can tell "checked" from "this build predates the field".
            "reason": self.reason,
            "monitor_id": self.monitor_id,
            "monitor_label": self.monitor_label,
            "monitor_distance_m": self.monitor_distance_m,
            "reference_timestamp": self.reference_timestamp,
            "reference_value": self.reference_value,
            "reference_crossed": self.reference_crossed,
            "calibration_method": self.calibration_method,
            "calibrated_against": self.calibrated_against,
        }
        if self.nodes:
            record["nodes"] = list(self.nodes)
        return record


@dataclass(frozen=True)
class ParameterScore:
    """The per-parameter tally, and a precision only where one is defined."""

    parameter: str
    confirmed: int
    contradicted: int
    unverifiable: int
    #: ``confirmed / (confirmed + contradicted)``, or ``None`` when that denominator is zero.
    precision: float | None
    #: The two-sided 95% Wilson interval on ``precision``, or ``None`` alongside it.
    interval: tuple[float, float] | None
    #: Why there is no precision, when there is none. ``None`` when there is one.
    precision_note: str | None

    @property
    def scored(self) -> int:
        return self.confirmed + self.contradicted

    @property
    def total(self) -> int:
        return self.scored + self.unverifiable

    def as_record(self) -> dict[str, object]:
        return {
            "parameter": self.parameter,
            "confirmed": self.confirmed,
            "contradicted": self.contradicted,
            "unverifiable": self.unverifiable,
            "scored": self.scored,
            "total": self.total,
            "precision": self.precision,
            "precision_interval": list(self.interval) if self.interval is not None else None,
            "precision_note": self.precision_note,
        }


@dataclass(frozen=True)
class AlertAudit:
    """Every historical alert in the window, classified, plus the per-parameter tallies."""

    schema_version: str
    pack_id: str
    pack_version: str
    thresholds: Mapping[str, float]
    window: tuple[str, str] | None
    max_distance_m: float
    tolerance_s: float
    alerts: tuple[AuditedAlert, ...]
    scores: tuple[ParameterScore, ...]
    notes: tuple[str, ...]

    def as_record(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "pack_id": self.pack_id,
            "pack_version": self.pack_version,
            "thresholds": dict(sorted(self.thresholds.items())),
            "window": (
                {"start": self.window[0], "end": self.window[1]}
                if self.window is not None
                else None
            ),
            "max_distance_m": self.max_distance_m,
            "tolerance_s": self.tolerance_s,
            "scores": [score.as_record() for score in self.scores],
            "alerts": [alert.as_record() for alert in self.alerts],
            "notes": list(self.notes),
        }

    @property
    def contradicted(self) -> tuple[AuditedAlert, ...]:
        return tuple(a for a in self.alerts if a.classification == CLASS_CONTRADICTED)


def wilson_interval(successes: int, trials: int, *, z: float = _Z_95) -> tuple[float, float]:
    """The two-sided Wilson score interval for a binomial proportion.

    Wilson rather than the normal approximation because an alert audit's counts are small and
    often near 1.0, exactly where the normal interval runs past 100% and reports an upper bound
    that cannot happen.

    ``trials`` of zero has no interval and is a caller error here: :func:`_score` never calls this
    without a scored alert, because a proportion over nothing is the thing this module exists to
    refuse.
    """
    if trials <= 0:
        raise ValueError("a proportion over zero trials is undefined, not 0.0")
    proportion = successes / trials
    denominator = 1.0 + z * z / trials
    centre = (proportion + z * z / (2 * trials)) / denominator
    spread = (
        z
        * math.sqrt(proportion * (1 - proportion) / trials + z * z / (4 * trials * trials))
        / denominator
    )
    return (max(0.0, centre - spread), min(1.0, centre + spread))


@dataclass(frozen=True)
class _Monitor:
    """A reference monitor reduced to what pairing needs, plus whether it can be located."""

    monitor_id: str
    label: str
    lat: float | None
    lon: float | None


def _monitors(config: NetworkConfig) -> list[_Monitor]:
    return [
        _Monitor(
            monitor_id=m.monitor_id,
            label=m.label or m.monitor_id,
            lat=m.lat,
            lon=m.lon,
        )
        for m in config.reference_monitors
        if m.monitor_id
    ]


def _readings_by_monitor_parameter(
    readings: Iterable[ReferenceReading],
) -> dict[tuple[str, str], list[ReferenceReading]]:
    grouped: dict[tuple[str, str], list[ReferenceReading]] = {}
    for reading in readings:
        grouped.setdefault((reading.monitor_id, reading.parameter), []).append(reading)
    for series in grouped.values():
        series.sort(key=lambda r: r.timestamp)
    return grouped


def _nearest_reading(
    series: Sequence[ReferenceReading], bucket: str, tolerance_s: float
) -> ReferenceReading | None:
    """The reading nearest ``bucket`` within ``tolerance_s``, earlier one winning a tie."""
    target = parse_timestamp(bucket).timestamp()
    best: ReferenceReading | None = None
    best_delta = 0.0
    for reading in series:
        delta = abs(parse_timestamp(reading.timestamp).timestamp() - target)
        if delta > tolerance_s:
            continue
        if best is None or delta < best_delta:
            best, best_delta = reading, delta
    return best


def _crossings(
    surface: Surface, pack: hazard_packs.HazardPack, floors: Mapping[str, float]
) -> list[tuple[CellReading, tuple[str, float]]]:
    """Every stored cell reading that crossed its floor, with the crossing it made.

    NowCast rows are skipped for the same reason :meth:`Surface.latest_by_cell` skips them: they
    are an alternate view of a bucket the hourly-mean row already covers, and auditing both would
    score one hour twice under two different numbers.
    """
    alerting = set(pack.alerting_parameters())
    out: list[tuple[CellReading, tuple[str, float]]] = []
    for cell in surface.cells:
        if cell.aqi_window == AQI_WINDOW_NOWCAST or cell.parameter not in alerting:
            continue
        crossed = crossing(cell.parameter, cell, floors)
        if crossed is not None:
            out.append((cell, crossed))
    out.sort(key=lambda item: (item[0].bucket, item[0].cell_id, item[0].parameter))
    return out


def _unit_for(cell: CellReading) -> str:
    if cell.parameter == "pm25_ugm3":
        return "AQI" if cell.aqi is not None else "ug/m3"
    if cell.parameter == EXPOSURE:
        return "level"
    return "degC"


@dataclass(frozen=True)
class _Pairing:
    """The outcome of looking for a reference reading for one alert: a match, or why not."""

    monitor: _Monitor | None
    reading: ReferenceReading | None
    distance_m: float | None
    reason: str | None


def _pair(
    cell: CellReading,
    monitors: Sequence[_Monitor],
    series: Mapping[tuple[str, str], list[ReferenceReading]],
    *,
    max_distance_m: float,
    tolerance_s: float,
) -> _Pairing:
    """Find the reference reading that can check this alert, or the reason none can.

    Five distinct refusals, kept distinct because they lead a steward somewhere different. The
    monitor-with-no-coordinate case is separated deliberately: treating a missing ``lat``/``lon``
    as ``0, 0`` would put a monitor in the Gulf of Guinea and rule it out on distance, which reads
    as "checked, too far" when the truth is "not locatable".
    """
    parameter = cell.parameter
    for_parameter = [m for m in monitors if (m.monitor_id, parameter) in series]
    if not for_parameter:
        # Two very different problems, separated because they send a steward somewhere else. If
        # no reading anywhere is for this parameter, the hazard simply has no regulatory
        # counterpart in this run (AirNow measures no heat index). If readings for it exist but
        # under a monitor id the network never declared, the fixture and `network.yaml` disagree
        # about which monitor this is -- which is a configuration error, not a coverage gap, and
        # collapsing the two would hide it behind a sentence that reads as "nothing to be done".
        if any(key[1] == parameter for key in series):
            declared = ", ".join(sorted(m.monitor_id for m in monitors)) or "none declared"
            return _Pairing(
                None,
                None,
                None,
                _NO_DECLARED_MONITOR.format(parameter=parameter, declared=declared),
            )
        return _Pairing(None, None, None, _NO_REFERENCE_PARAMETER.format(parameter=parameter))

    located = [m for m in for_parameter if m.lat is not None and m.lon is not None]
    if not located:
        return _Pairing(None, None, None, _NO_MONITOR_COORDINATE.format(parameter=parameter))

    ranked = sorted(
        (
            (haversine_m(cell.lat, cell.lon, m.lat, m.lon), m.monitor_id, m)
            for m in located
            if m.lat is not None and m.lon is not None
        ),
        key=lambda item: (item[0], item[1]),
    )
    distance, _, nearest = ranked[0]
    if distance > max_distance_m:
        return _Pairing(
            None,
            None,
            None,
            _NO_MONITOR_IN_RANGE.format(parameter=parameter, max_distance_m=max_distance_m),
        )

    reading = _nearest_reading(series[(nearest.monitor_id, parameter)], cell.bucket, tolerance_s)
    if reading is None:
        return _Pairing(
            nearest,
            None,
            distance,
            _NO_READING_IN_WINDOW.format(
                monitor_id=nearest.monitor_id, parameter=parameter, tolerance_s=tolerance_s
            ),
        )
    return _Pairing(nearest, reading, distance, None)


def _reference_crosses(
    cell: CellReading, reading: ReferenceReading, floors: Mapping[str, float]
) -> bool:
    """Whether the reference reading itself meets the floor this alert crossed.

    Built by putting the reference concentration through the *same* ``crossing`` call the alert
    went through, on a cell that differs from the alerting one only in its value. Re-deriving the
    AQI breakpoints here instead would let the audit and the feed disagree about where "Unhealthy
    for Sensitive Groups" begins, and the audit would then be scoring a threshold nobody ships.
    """
    reference_cell = replace(
        cell,
        mean=reading.value,
        aqi=pm25_aqi(reading.value)[0] if cell.parameter == "pm25_ugm3" else cell.aqi,
        category=pm25_aqi(reading.value)[1] if cell.parameter == "pm25_ugm3" else cell.category,
    )
    return crossing(cell.parameter, reference_cell, floors) is not None


def _score(parameter: str, audited: Sequence[AuditedAlert]) -> ParameterScore:
    confirmed = sum(1 for a in audited if a.classification == CLASS_CONFIRMED)
    contradicted = sum(1 for a in audited if a.classification == CLASS_CONTRADICTED)
    unverifiable = sum(1 for a in audited if a.classification == CLASS_UNVERIFIABLE)
    scored = confirmed + contradicted
    if scored == 0:
        # The refusal this module exists for. A precision of 0.0 here would read as "every alert
        # was wrong" and a precision of 1.0 as "every alert was right", when the measurement is
        # that none of them was checked.
        return ParameterScore(
            parameter=parameter,
            confirmed=confirmed,
            contradicted=contradicted,
            unverifiable=unverifiable,
            precision=None,
            interval=None,
            precision_note=(
                f"no {parameter} alert could be checked against a reference monitor, so this "
                f"run measures no precision for it; {unverifiable} alert(s) are unverifiable"
            ),
        )
    return ParameterScore(
        parameter=parameter,
        confirmed=confirmed,
        contradicted=contradicted,
        unverifiable=unverifiable,
        precision=confirmed / scored,
        interval=wilson_interval(confirmed, scored),
        precision_note=None,
    )


def audit_alerts(
    surface: Surface,
    config: NetworkConfig,
    references: Iterable[ReferenceReading],
    *,
    since: str | None = None,
    until: str | None = None,
    max_distance_m: float = DEFAULT_MAX_DISTANCE_M,
    tolerance_s: float = DEFAULT_TOLERANCE_S,
) -> AlertAudit:
    """Classify every historical alert in the window against the supplied reference readings."""
    pack = hazard_packs.resolve_pack(config.hazard_pack)
    floors = resolve_thresholds(config.alert_thresholds, pack)
    series = _readings_by_monitor_parameter(references)
    monitors = _monitors(config)

    audited: list[AuditedAlert] = []
    for cell, (severity, threshold) in _crossings(surface, pack, floors):
        if since is not None and cell.bucket < since:
            continue
        if until is not None and cell.bucket > until:
            continue
        pairing = _pair(
            cell,
            monitors,
            series,
            max_distance_m=max_distance_m,
            tolerance_s=tolerance_s,
        )
        if pairing.reading is None:
            classification, crossed = CLASS_UNVERIFIABLE, None
        else:
            crossed = _reference_crosses(cell, pairing.reading, floors)
            classification = CLASS_CONFIRMED if crossed else CLASS_CONTRADICTED
        audited.append(
            AuditedAlert(
                area_id=cell.cell_id,
                area=cell.label or cell.cell_id,
                lat=cell.lat,
                lon=cell.lon,
                parameter=cell.parameter,
                bucket=cell.bucket,
                value=round(cell.mean, 3),
                unit=_unit_for(cell),
                severity=severity,
                threshold=threshold,
                provisional=cell.provisional,
                classification=classification,
                reason=pairing.reason,
                monitor_id=pairing.monitor.monitor_id if pairing.monitor is not None else None,
                monitor_label=pairing.monitor.label if pairing.monitor is not None else None,
                monitor_distance_m=(
                    round(pairing.distance_m, 1) if pairing.distance_m is not None else None
                ),
                reference_timestamp=(
                    pairing.reading.timestamp if pairing.reading is not None else None
                ),
                reference_value=(
                    round(pairing.reading.value, 3) if pairing.reading is not None else None
                ),
                reference_crossed=crossed,
                calibration_method=cell.method,
                calibrated_against=cell.reference,
                nodes=cell.nodes,
            )
        )

    parameters = sorted({a.parameter for a in audited})
    scores = tuple(_score(p, [a for a in audited if a.parameter == p]) for p in parameters)
    buckets = sorted(a.bucket for a in audited)
    window = (buckets[0], buckets[-1]) if buckets else None

    notes = [
        "Recall is not measured. Reference coverage is far too sparse to say how many real "
        "episodes the network failed to alert on, and a precision table alone must not be read "
        "as one.",
        f"A monitor is treated as speaking about a cell within {max_distance_m:.0f} m and "
        f"{tolerance_s:.0f} s. Both are swelter's own parameters, not a published standard: no "
        "rule states the distance at which a regulatory monitor stops representing an airshed.",
    ]
    if not audited:
        notes.append(
            "No cell reading in this window crossed a floor, so there are no alerts to score. "
            "That is not a precision of 1.0."
        )
    return AlertAudit(
        schema_version=AUDIT_SCHEMA_VERSION,
        pack_id=pack.pack_id,
        pack_version=pack.version,
        thresholds=dict(floors),
        window=window,
        max_distance_m=max_distance_m,
        tolerance_s=tolerance_s,
        alerts=tuple(audited),
        scores=scores,
        notes=tuple(notes),
    )


def _precision_cell(score: ParameterScore) -> str:
    if score.precision is None or score.interval is None:
        return "not measured"
    low, high = score.interval
    return f"{score.precision * 100:.1f}% ({low * 100:.1f} to {high * 100:.1f}%)"


def render_markdown(audit: AlertAudit) -> str:
    """Render the audit as a document a steward or a partner can read."""
    lines: list[str] = [
        "# Alert hindcast audit",
        "",
        f"Hazard pack: `{audit.pack_id}` v{audit.pack_version}. ",
    ]
    if audit.window is not None:
        lines.append(f"Window audited: {audit.window[0]} to {audit.window[1]} (UTC).")
    else:
        lines.append("Window audited: no alert was raised in the requested window.")
    lines.extend(
        [
            "",
            "## Precision by parameter",
            "",
            "| Parameter | Confirmed | Contradicted | Unverifiable | Precision (95% Wilson) |",
            "| --- | ---: | ---: | ---: | --- |",
        ]
    )
    for score in audit.scores:
        lines.append(
            f"| `{score.parameter}` | {score.confirmed} | {score.contradicted} | "
            f"{score.unverifiable} | {_precision_cell(score)} |"
        )
    if not audit.scores:
        lines.append("| _no alerts in window_ | 0 | 0 | 0 | not measured |")

    unexplained = [s for s in audit.scores if s.precision_note]
    if unexplained:
        lines.extend(["", "### Why a precision is missing", ""])
        lines.extend(f"- {s.precision_note}" for s in unexplained)

    lines.extend(["", "## Contradicted alerts", ""])
    contradicted = audit.contradicted
    if not contradicted:
        lines.append(
            "None in this window. That means none of the alerts that *could* be checked was "
            "contradicted; it says nothing about the ones that could not."
        )
    else:
        lines.extend(
            [
                "| Hour (UTC) | Area | Parameter | Published | Reference | Monitor | Distance |",
                "| --- | --- | --- | ---: | ---: | --- | ---: |",
            ]
        )
        for alert in contradicted:
            distance = (
                f"{alert.monitor_distance_m:.0f} m"
                if alert.monitor_distance_m is not None
                else "unknown"
            )
            lines.append(
                f"| {alert.bucket} | {alert.area} | `{alert.parameter}` | "
                f"{alert.value} {alert.unit} | {alert.reference_value} "
                f"({alert.reference_timestamp}) | {alert.monitor_label} | {distance} |"
            )

    lines.extend(["", "## What this audit does not say", ""])
    lines.extend(f"- {note}" for note in audit.notes)
    lines.append("")
    return "\n".join(lines)
