"""Neighborhood heat/AQI alerts: a generated, public feed of areas crossing a danger threshold.

swelter deploys as a static site (GitHub Pages) with a read-only, scale-to-zero server. There is no
backend that could hold a subscriber list, and a list of who-asked-to-be-told-about-where would be
exactly the kind of person-shaped record the hard rules forbid (ADR 0010). So an alert is not a
message sent to a person — it is a *published artifact*. This module scans the latest hour of the
aggregated :class:`~swelter.aggregate.Surface` and emits, for every published cell whose heat or air
reading has crossed a documented danger threshold, one alert. The result renders two ways:

* ``to_json()`` — a small JSON document a page, a script, or a webhook bridge can poll.
* ``to_atom()`` — a standards Atom 1.0 feed, so a resident "subscribes to their neighborhood" by
  adding the feed (optionally filtered to one area) to any ordinary RSS/Atom reader. No account, no
  email on file, no PII, no tracking — the subscription lives in the reader's own tooling.

Thresholds are public-health bands, not swelter inventions: the PM2.5 floor is the US-EPA AQI 101
("Unhealthy for Sensitive Groups") boundary, the heat floor is the NWS heat-index "Danger" tier
(39.4 °C / 103 °F), and the exposure floor is the level-3 "High" tier of the combined surface
(ADR 0009). A collective can raise or lower them per network via ``alert_thresholds`` in
``network.yaml``. Provisional (uncalibrated) readings can still cross a threshold; an alert built
from one is published but carries ``provisional: true`` and says so, the same honesty the map
keeps — suppressing a real danger because the sensor is not yet calibrated would be worse.

Everything here is derived from the data: the feed's timestamps come from the surface's hour
buckets, never the wall clock, so re-running the pipeline on the same store reproduces the same feed
byte for byte (the static demo artifact stays deterministic).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final
from xml.sax.saxutils import escape

from . import i18n_alerts
from .aggregate import EXPOSURE, CellReading, Surface
from .models import EXPOSURE_LEVELS, heat_index_category

#: Documented danger floors. Keys are the surface fields they test. A reading at or above the floor
#: raises an alert. Overridable per network via ``network.yaml: alert_thresholds``.
DEFAULT_THRESHOLDS: Final[Mapping[str, float]] = {
    "pm25_aqi": 101.0,  # US-EPA AQI 101 = "Unhealthy for Sensitive Groups" boundary
    "heat_index_c": 39.4,  # NWS heat-index "Danger" tier floor (103 °F)
    "exposure": 3.0,  # combined-surface level 3 = "High" (ADR 0009)
}

#: The parameters an alert can be raised on, longest-standing first for stable ordering.
_ALERTING_PARAMETERS: Final[tuple[str, ...]] = ("pm25_ugm3", "heat_index_c", EXPOSURE)


@dataclass(frozen=True)
class Alert:
    """One area crossing one danger threshold, in the most recent hour it reported.

    Carries only public, aggregate fields — the published cell id and centroid, the host-assigned
    area label, the node id(s) feeding the cell, and the reading. There is no field that can name or
    locate a person; an alert is an environmental fact about a block, not a record about anyone.
    """

    area_id: str  # the published grid-cell id (lat,lon of the cell centre)
    area: str  # the host-assigned place name, or the cell id when a cell is unlabelled
    lat: float
    lon: float
    parameter: str
    bucket: str  # the hour the reading is for (ISO-8601 UTC); the alert's "as of"
    value: float
    unit: str
    severity: str  # the named band crossed (AQI category / NWS heat tier / exposure level)
    threshold: float  # the floor this reading met or passed
    provisional: bool  # built from an uncalibrated reading — published, but flagged
    aqi: int | None = None
    nodes: tuple[str, ...] = ()

    @property
    def id(self) -> str:
        """A stable identity per area+parameter so a reader updates an entry, not duplicates it."""
        return f"{self.area_id}|{self.parameter}"

    def headline(self, lang: str = "en") -> str:
        """A plain-language summary line for the feed body and the webhook bridge, in ``lang``
        (default English). Delegates to the :mod:`swelter.i18n_alerts` catalog so the wording for
        every language lives in one place; kept as a method here (not moved wholesale) for
        back-compat with callers that expect ``Alert.headline()`` to just work."""
        return i18n_alerts.headline(self, lang)

    @property
    def headline_es(self) -> str:
        """The Spanish headline — machine-drafted, see :mod:`swelter.i18n_alerts`."""
        return self.headline("es")

    def as_record(self) -> dict[str, object]:
        record: dict[str, object] = {
            "id": self.id,
            "area_id": self.area_id,
            "area": self.area,
            "lat": self.lat,
            "lon": self.lon,
            "parameter": self.parameter,
            "bucket": self.bucket,
            "value": round(self.value, 3),
            "unit": self.unit,
            "severity": self.severity,
            "threshold": self.threshold,
            "provisional": self.provisional,
            "headline": self.headline(),
            "headline_es": self.headline_es,
        }
        if self.aqi is not None:
            record["aqi"] = self.aqi
        if self.nodes:
            record["nodes"] = list(self.nodes)
        return record


@dataclass(frozen=True)
class AlertFeed:
    """The set of currently-active alerts, plus the metadata a feed needs."""

    network: str
    bucket: str  # the latest hour the surface covers; the feed's "updated"
    thresholds: Mapping[str, float]
    alerts: tuple[Alert, ...]
    base_url: str = "http://localhost:8000"

    def for_area(self, area_id: str) -> AlertFeed:
        """A feed narrowed to one published cell — the per-neighborhood subscription view."""
        kept = tuple(a for a in self.alerts if a.area_id == area_id)
        return AlertFeed(
            network=self.network,
            bucket=self.bucket,
            thresholds=self.thresholds,
            alerts=kept,
            base_url=self.base_url,
        )

    def to_json(self) -> dict[str, object]:
        return {
            "network": self.network,
            "generated": self.bucket,  # derived from the data, not the wall clock (deterministic)
            "self": f"{self.base_url.rstrip('/')}/api/alerts.json",
            "thresholds": dict(self.thresholds),
            "count": len(self.alerts),
            "alerts": [a.as_record() for a in self.alerts],
            "note": i18n_alerts.note("en"),
            # headline_es (above, per alert) and note_es are machine-drafted, not human-reviewed —
            # labeled here so a consumer never mistakes ES output for a vetted translation.
            "note_es": i18n_alerts.note("es"),
            "translation": i18n_alerts.TRANSLATION_LABEL,
        }

    def to_atom(self, lang: str = "en") -> str:
        """Render the feed as Atom 1.0 with a GeoRSS point per entry, in ``lang`` (default English).

        Timestamps are the surface's hour buckets (already ``...Z``), so the feed is reproducible.
        ``lang="es"`` renders entry titles/summaries and the feed title/subtitle in Spanish via the
        :mod:`swelter.i18n_alerts` catalog; that Spanish text is machine-drafted, so the feed root
        carries a ``<generator>`` note saying so — never presented as a reviewed translation.
        """
        base = self.base_url.rstrip("/")
        self_path = "/api/alerts.xml" if lang == "en" else "/api/alerts.es.xml"
        alt_lang, alt_path = (
            ("es", "/api/alerts.es.xml") if lang == "en" else ("en", "/api/alerts.xml")
        )
        self_url = f"{base}{self_path}"
        alt_url = f"{base}{alt_path}"
        updated = self.bucket or "1970-01-01T00:00:00Z"
        lines = [
            '<?xml version="1.0" encoding="utf-8"?>',
            (
                '<feed xmlns="http://www.w3.org/2005/Atom" '
                'xmlns:georss="http://www.georss.org/georss" '
                f'xml:lang="{lang}">'
            ),
            f"  <title>{escape(i18n_alerts.feed_title(self.network, lang))}</title>",
            f"  <id>{escape(self_url)}</id>",
            f'  <link rel="self" href="{escape(self_url)}"/>',
            f'  <link rel="alternate" hreflang="{escape(alt_lang)}" href="{escape(alt_url)}"/>',
            f"  <updated>{escape(updated)}</updated>",
            f"  <subtitle>{escape(i18n_alerts.feed_subtitle(lang))}</subtitle>",
        ]
        if lang != "en":
            lines.append(
                f"  <generator>swelter i18n_alerts ({escape(i18n_alerts.TRANSLATION_LABEL)}-"
                "translated, not human-reviewed)</generator>"
            )
        for alert in self.alerts:
            entry_id = f"{self_url}#{alert.id}"
            headline = alert.headline(lang)
            lines.extend(
                [
                    "  <entry>",
                    f"    <title>{escape(headline)}</title>",
                    f"    <id>{escape(entry_id)}</id>",
                    f"    <updated>{escape(alert.bucket)}</updated>",
                    f'    <category term="{escape(alert.parameter)}"/>',
                    f'    <category term="{escape(alert.severity)}"/>',
                    f"    <summary>{escape(headline)}</summary>",
                    f"    <georss:point>{alert.lat} {alert.lon}</georss:point>",
                    "  </entry>",
                ]
            )
        lines.append("</feed>")
        return "\n".join(lines) + "\n"


def _resolve_thresholds(overrides: Mapping[str, float] | None) -> dict[str, float]:
    merged = dict(DEFAULT_THRESHOLDS)
    if overrides:
        for key, value in overrides.items():
            if key in DEFAULT_THRESHOLDS:
                merged[key] = float(value)
    return merged


def build_feed(
    surface: Surface,
    *,
    network: str = "swelter network",
    base_url: str = "http://localhost:8000",
    thresholds: Mapping[str, float] | None = None,
) -> AlertFeed:
    """Scan the most recent hour of every cell and raise an alert for each danger crossing.

    Only the latest reading per (cell, parameter) is considered — an alert is about now, not an hour
    last week. A cell can raise more than one alert (hot *and* smoky); each is its own entry. The
    feed's bucket is the newest hour present in the surface, so the artifact is deterministic.
    """
    floors = _resolve_thresholds(thresholds)
    latest = surface.latest_by_cell()
    alerts: list[Alert] = []
    newest = ""
    for area_id in sorted(latest):
        by_param = latest[area_id]
        for parameter in _ALERTING_PARAMETERS:
            reading = by_param.get(parameter)
            if reading is None:
                continue
            # The feed's "updated" is the latest hour the surface covers, even on a calm day with no
            # crossings, so an empty feed still has a meaningful, data-derived timestamp.
            newest = max(newest, reading.bucket)
            crossed = _crossing(parameter, reading, floors)
            if crossed is None:
                continue
            severity, threshold = crossed
            area = reading.label or area_id
            alerts.append(
                Alert(
                    area_id=area_id,
                    area=area,
                    lat=reading.lat,
                    lon=reading.lon,
                    parameter=parameter,
                    bucket=reading.bucket,
                    value=round(reading.mean, 3),
                    unit=_unit_for(parameter, reading.aqi),
                    severity=severity,
                    threshold=threshold,
                    provisional=reading.provisional,
                    aqi=reading.aqi if parameter == "pm25_ugm3" else None,
                    nodes=reading.nodes,
                )
            )
    return AlertFeed(
        network=network,
        bucket=newest,
        thresholds=floors,
        alerts=tuple(alerts),
        base_url=base_url,
    )


def _crossing(
    parameter: str, reading: CellReading, floors: Mapping[str, float]
) -> tuple[str, float] | None:
    """Return ``(severity_name, floor)`` if this reading crosses its threshold, else ``None``."""
    aqi = reading.aqi
    category = reading.category
    mean = reading.mean
    if parameter == "pm25_ugm3":
        floor = floors["pm25_aqi"]
        if aqi is not None and aqi >= floor:
            return (category or "Unhealthy for Sensitive Groups"), floor
        return None
    if parameter == "heat_index_c":
        floor = floors["heat_index_c"]
        if mean >= floor:
            return heat_index_category(mean)[1], floor
        return None
    if parameter == EXPOSURE:
        floor = floors["exposure"]
        level = int(round(mean))
        if level >= floor:
            name = category or EXPOSURE_LEVELS[min(level, len(EXPOSURE_LEVELS) - 1)]
            return name, floor
        return None
    return None


def _unit_for(parameter: str, aqi: int | None) -> str:
    if parameter == "heat_index_c":
        return "degC"
    if parameter == "pm25_ugm3":
        return "AQI"
    return "level"
