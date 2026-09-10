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

Thresholds are public-health bands, not swelter inventions, and they are supplied by a **hazard
pack** (:mod:`swelter.hazard_packs`) — versioned, cited data a network selects with
``hazard_pack:`` in ``network.yaml``. The default pack is heat, so a network that names none behaves
exactly as before: the PM2.5 floor is the US-EPA AQI 101 ("Unhealthy for Sensitive Groups")
boundary, the heat floor is the NWS heat-index "Danger" tier (39.4 °C / 103 °F), and the exposure
floor is the level-3 "High" tier of the combined surface (ADR 0009). The cold pack swaps heat for
NWS wind-chill and keeps air quality, so the same pipeline serves winter (ADR 0031). A collective
can still raise or lower a pack's floors via ``alert_thresholds`` in ``network.yaml``. Provisional
(uncalibrated) readings can still cross a threshold; an alert built
from one is published but carries ``provisional: true`` and says so, the same honesty the map
keeps — suppressing a real danger because the sensor is not yet calibrated would be worse.

An alert is only ever about *now*: a cell's latest reading raises one only if it lands in the
surface's newest bucket (ADR 0035), so a node that has gone dark cannot keep broadcasting the danger
crossing it was in when it stopped. Because an alerts feed that goes quiet about a block would be
read as an all-clear for that block, the blocks swelter can no longer see are published too, as
:class:`StaleArea` records carrying no value — "no current reading here, last heard from at T"
(ADR 0036). The feed says what it does not know instead of leaving it to be inferred from silence.

Everything here is derived from the data: the feed's timestamps come from the surface's hour
buckets, never the wall clock, so re-running the pipeline on the same store reproduces the same feed
byte for byte (the static demo artifact stays deterministic).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final
from xml.sax.saxutils import escape

from . import hazard_packs, i18n_alerts
from .aggregate import EXPOSURE, CellReading, HistoryAbsence, HistoryContext, Surface
from .config import NetworkConfig
from .models import EXPOSURE_LEVELS, heat_index_category, wind_chill_category

#: The default network's documented danger floors — the **heat pack** (``hazard_packs.HEAT_PACK``),
#: kept under this long-standing name for the callers that import it (``config`` validation,
#: ``exposure_brief``): they resolve the floors of a network that names no ``hazard_pack``, and that
#: network is the heat pack, unchanged (``pm25_aqi`` ≥ 101 EPA, ``heat_index_c`` ≥ 39.4 NWS Danger,
#: ``exposure`` ≥ 3 High). A network on another pack (e.g. ``cold``) resolves *that* pack's cited
#: floors instead — see :func:`resolve_thresholds` and :func:`build_feed`. Each floor's public
#: source lives with it in :mod:`swelter.hazard_packs`.
DEFAULT_THRESHOLDS: Final[Mapping[str, float]] = hazard_packs.HEAT_PACK.default_floors()

#: The Atom ``<category term=...>`` that marks an entry as a "no current reading" record rather than
#: a danger crossing, so a reader or a bridge can filter the two apart without parsing the title.
STALE_CATEGORY: Final[str] = "no-current-reading"

#: The PM2.5 averaging window every feed read before hazard packs could choose one. A feed on this
#: window serializes no ``aqi_window`` key, so an existing consumer sees exactly the bytes it
#: always saw (ADR 0031, ADR 0050).
_DEFAULT_AQI_WINDOW: Final[str] = hazard_packs.AQI_WINDOW_HOURLY_MEAN


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
    # Copied from the cell this alert was raised on: where this hour sits in the area's own
    # recorded distribution for the same calendar month, or why there is no such baseline (#241).
    # Exactly one is set, always — an alert never simply omits the question.
    history_context: HistoryContext | None = None
    history_context_reason: HistoryAbsence | None = None

    @property
    def history_line(self) -> str:
        """The historical-percentile sentence, in English — or the absence, in its own words."""
        return self.history_line_in("en")

    @property
    def history_line_es(self) -> str:
        """The Spanish history sentence — machine-drafted, see :mod:`swelter.i18n_alerts`."""
        return self.history_line_in("es")

    def history_line_in(self, lang: str) -> str:
        """The history sentence in ``lang``. One renderer, so the feed and the brief agree."""
        return i18n_alerts.history_line(
            self.area,
            self.history_context,
            None if self.history_context_reason is None else self.history_context_reason.code,
            lang,
        )

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
            # Both keys always written, never omitted: a consumer reads one stable shape and can
            # tell "no baseline here, and here is why" from "this build predates the field".
            "history_context": (
                None if self.history_context is None else self.history_context.as_record()
            ),
            "history_context_reason": (
                None
                if self.history_context_reason is None
                else self.history_context_reason.as_record()
            ),
            "history_line": self.history_line,
            "history_line_es": self.history_line_es,
        }
        if self.aqi is not None:
            record["aqi"] = self.aqi
        if self.nodes:
            record["nodes"] = list(self.nodes)
        return record


@dataclass(frozen=True)
class StaleArea:
    """One published cell/parameter that has stopped reporting: an explicit "we cannot tell".

    ADR 0035 stopped a dead node from broadcasting its last danger crossing forever. Suppression
    alone, though, leaves the feed *silent* about that block, and silence in an alerts feed reads
    as an all-clear — the reassuring answer, which is exactly the one swelter must not give when
    it does not know. ADR 0036 therefore publishes the absence itself: for every cell/parameter
    whose latest reading predates the feed's bucket, one of these records, saying when the block
    last reported and that swelter has no current reading for it.

    Deliberately carries **no value**. The last reading is not a measurement of now, so
    republishing it — even labelled — would hand a consumer a number to plot in the "current"
    column. What travels instead is when it was last heard from (``last_bucket``,
    ``hours_since_last_reading``) and whether an alert published from that last reading is being
    withdrawn (``withdrawn``).

    Like :class:`Alert`, this is aggregate and public: a cell id, a centroid, a host-assigned area
    label, and the node id(s) feeding the cell. No field can name or locate a person.
    """

    area_id: str  # the published grid-cell id (lat,lon of the cell centre)
    area: str  # the host-assigned place name, or the cell id when a cell is unlabelled
    lat: float
    lon: float
    parameter: str
    last_bucket: str  # the newest hour this cell/parameter did report (ISO-8601 UTC)
    # Whole hours from `last_bucket` to the feed's bucket. ``None`` only when a bucket is not
    # parseable as a timestamp — the gap is then reported without a size, never as zero.
    hours_since_last_reading: int | None
    # True when this cell's last reading *did* cross a danger floor. The alert built from it is no
    # longer published (ADR 0035), so this record is a withdrawal, not a clearance: swelter is not
    # saying the danger passed, it is saying it can no longer see.
    withdrawn: bool
    nodes: tuple[str, ...] = ()

    @property
    def id(self) -> str:
        """The same area+parameter identity an :class:`Alert` for this cell would carry.

        Deliberate: an Atom reader keys entries by id, so publishing this record under the id of
        the alert it supersedes *updates* the entry a subscriber is already looking at. A Danger
        headline from a node that has since gone dark is replaced in the reader by the withdrawal,
        instead of sitting there as the last thing the feed ever said about that block.
        """
        return f"{self.area_id}|{self.parameter}"

    def headline(self, lang: str = "en") -> str:
        """A plain-language "no current reading" line for the feed body, in ``lang``."""
        return i18n_alerts.stale_headline(self, lang)

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
            # Self-describing, so a consumer that flattens the feed's arrays can never mistake one
            # of these for a reading: there is no `value` key to read.
            "status": "no-current-reading",
            "last_bucket": self.last_bucket,
            "hours_since_last_reading": self.hours_since_last_reading,
            "withdrawn": self.withdrawn,
            "headline": self.headline(),
            "headline_es": self.headline_es,
        }
        if self.nodes:
            record["nodes"] = list(self.nodes)
        return record


@dataclass(frozen=True)
class HazardEvent:
    """Whether several cells rising together currently constitute one named hazard event.

    Published whether or not an event is running, and that is the point. A feed that carried this
    record only during a smoke episode would let its absence mean two different things -- "checked,
    no event" and "this pack does not look for events" -- and the reassuring reading is the one
    swelter must never give by default. So ``active`` is a field, ``qualifying_cells`` states how
    many cells met the rule when the answer is no, and ``evaluated`` says whether the rule could be
    evaluated at all.

    ``evaluated=False`` is not ``active=False``. A surface with no readings in the rule's window,
    or with no bucket ``lookback_hours`` back to compare against, cannot answer the question, and
    saying "no event" there would be an absence rendered as an all-clear.
    """

    rule_id: str  # the pack whose rule produced this record
    parameter: str
    aqi_window: str  # the averaging window the rule read; the feed names it rather than implying it
    evaluated: bool
    active: bool
    qualifying_cells: int
    minimum_cells: int
    floor: float
    rise: float
    lookback_hours: int
    bucket: str  # the hour evaluated
    reason: str  # why the answer is what it is, in one sentence
    areas: tuple[str, ...] = ()  # the cell ids that qualified, sorted

    def as_record(self) -> dict[str, object]:
        return {
            "rule_id": self.rule_id,
            "parameter": self.parameter,
            "aqi_window": self.aqi_window,
            "evaluated": self.evaluated,
            "active": self.active,
            "qualifying_cells": self.qualifying_cells,
            "minimum_cells": self.minimum_cells,
            "floor": self.floor,
            "rise": self.rise,
            "lookback_hours": self.lookback_hours,
            "bucket": self.bucket,
            "reason": self.reason,
            "areas": list(self.areas),
        }


@dataclass(frozen=True)
class PackSelection:
    """Which pack produced this feed, and what chose it — published only when something chose it.

    A feed built by a network that names one pack needs no such record: the pack is the
    configuration, and a reader who wants it reads ``network.yaml``. A feed built under
    ``auto-season`` is different, because the pack changed without the configuration changing, and
    an alert whose floors moved for a reason nothing on the surface records is an unexplained
    change in what the network calls dangerous.

    ``month`` is the month of ``bucket`` -- the data's month, not today's. It is published beside
    the pack id precisely so a reader can check that the switch followed the data.
    """

    pack_id: str
    selected_by: str  # "season-calendar"
    month: int

    def as_record(self) -> dict[str, object]:
        return {"pack": self.pack_id, "selected_by": self.selected_by, "month": self.month}


@dataclass(frozen=True)
class AlertFeed:
    """The set of currently-active alerts, the areas that have gone quiet, and the feed metadata."""

    network: str
    bucket: str  # the latest hour the surface covers; the feed's "updated"
    thresholds: Mapping[str, float]
    alerts: tuple[Alert, ...]
    base_url: str = "http://localhost:8000"
    # Cells that reported before but not in `bucket` — published so absence is stated, not implied
    # by an empty `alerts` list (ADR 0036).
    stale: tuple[StaleArea, ...] = ()
    # The pack's event verdict, when the pack defines an event rule. `None` means this pack looks
    # for no events at all, which is a different statement from "no event is running" and is why
    # the two are not collapsed into one falsy value.
    event: HazardEvent | None = None
    # The PM2.5 averaging window this feed's own alerts were read on, so a consumer never has to
    # infer it from the numbers. Serialized only when it is not the default -- see `to_json`.
    aqi_window: str = _DEFAULT_AQI_WINDOW
    # Present only when something other than the configuration chose the pack -- i.e. a season
    # calendar. `None` on every other feed, and serialized nowhere, so ADR 0031's byte-identity
    # promise to a network that named no pack still holds.
    pack_selection: PackSelection | None = None

    def for_area(self, area_id: str) -> AlertFeed:
        """A feed narrowed to one published cell — the per-neighborhood subscription view.

        Narrows the stale records too. A resident who subscribes to one block must still be told
        when that block stops reporting; handing them an empty feed instead would be the same silent
        all-clear at the level of a single subscription.
        """
        kept = tuple(a for a in self.alerts if a.area_id == area_id)
        kept_stale = tuple(s for s in self.stale if s.area_id == area_id)
        return AlertFeed(
            network=self.network,
            bucket=self.bucket,
            thresholds=self.thresholds,
            alerts=kept,
            base_url=self.base_url,
            stale=kept_stale,
            # The event is network-wide by construction -- it is about several blocks at once --
            # so it travels into a single-area view unchanged rather than being narrowed away. A
            # resident subscribed to one block is still in the smoke.
            event=self.event,
            aqi_window=self.aqi_window,
            pack_selection=self.pack_selection,
        )

    def to_json(self) -> dict[str, object]:
        return {
            "network": self.network,
            "generated": self.bucket,  # derived from the data, not the wall clock (deterministic)
            "self": f"{self.base_url.rstrip('/')}/api/alerts.json",
            "thresholds": dict(self.thresholds),
            "count": len(self.alerts),
            "alerts": [a.as_record() for a in self.alerts],
            # `count`/`alerts` are crossings only. An empty `alerts` list does not mean every block
            # is fine — it means no *currently reporting* block crossed a floor. `stale` is where
            # the blocks swelter cannot currently see are named (ADR 0036).
            "stale_count": len(self.stale),
            "stale": [s.as_record() for s in self.stale],
            # Present only for a pack that looks for events. Absent is "this pack has no event
            # rule"; `{"active": false, ...}` is "checked, and no". Collapsing the two would let a
            # heat feed's silence read as an all-clear about smoke.
            **(
                {
                    "event": self.event.as_record(),
                    "event_headline": i18n_alerts.event_headline(self.event, "en"),
                    "event_headline_es": i18n_alerts.event_headline(self.event, "es"),
                }
                if self.event is not None
                else {}
            ),
            # Emitted only when this feed read a window other than the long-standing hourly
            # mean. ADR 0031's promise is that a network naming no hazard pack produces a
            # byte-identical feed, and adding a key to every feed would break that for every
            # existing consumer. Always naming the window would be the better surface and is a
            # published-surface change with a data-schema decision behind it, not a side effect
            # of adding a pack.
            **({"aqi_window": self.aqi_window} if self.aqi_window != _DEFAULT_AQI_WINDOW else {}),
            # Same rule, same reason: emitted only when a calendar chose the pack. A network that
            # names one pack, or none, serializes exactly what it always has.
            **(
                {"pack_selection": self.pack_selection.as_record()}
                if self.pack_selection is not None
                else {}
            ),
            "stale_note": i18n_alerts.stale_note("en"),
            "stale_note_es": i18n_alerts.stale_note("es"),
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

        Every stale area (:class:`StaleArea`) is rendered as an entry too, under the same ``id`` the
        alert for that cell/parameter would use and stamped with the *feed's* bucket, so a reader
        updates the entry in place: a Danger headline from a node that has since gone dark is
        replaced by the withdrawal rather than left standing as the feed's last word on that block.
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
            # The title stays exactly the crossing, so an existing reader's entry list does not
            # change shape; the local baseline is a second sentence in the summary, which is where
            # a reader looks for context rather than for the verdict.
            summary = f"{headline} {alert.history_line_in(lang)}"
            lines.extend(
                [
                    "  <entry>",
                    f"    <title>{escape(headline)}</title>",
                    f"    <id>{escape(entry_id)}</id>",
                    f"    <updated>{escape(alert.bucket)}</updated>",
                    f'    <category term="{escape(alert.parameter)}"/>',
                    f'    <category term="{escape(alert.severity)}"/>',
                    f"    <summary>{escape(summary)}</summary>",
                    f"    <georss:point>{alert.lat} {alert.lon}</georss:point>",
                    "  </entry>",
                ]
            )
        for area in self.stale:
            entry_id = (
                f"{self_url}#{area.id}"  # the id an alert for this cell would use, on purpose
            )
            headline = area.headline(lang)
            lines.extend(
                [
                    "  <entry>",
                    f"    <title>{escape(headline)}</title>",
                    f"    <id>{escape(entry_id)}</id>",
                    # The *feed's* bucket, not the block's last one: a reader ignores an update
                    # stamped older than the entry it already holds, and this entry has to land.
                    f"    <updated>{escape(updated)}</updated>",
                    f'    <category term="{escape(area.parameter)}"/>',
                    f'    <category term="{escape(STALE_CATEGORY)}"/>',
                    f"    <summary>{escape(headline)}</summary>",
                    f"    <georss:point>{area.lat} {area.lon}</georss:point>",
                    "  </entry>",
                ]
            )
        lines.append("</feed>")
        return "\n".join(lines) + "\n"


def resolve_thresholds(
    overrides: Mapping[str, float] | None,
    pack: hazard_packs.HazardPack | None = None,
) -> dict[str, float]:
    """Merge network-level `alert_thresholds` overrides onto a hazard pack's cited floors.

    ``pack`` defaults to the heat pack, so an existing caller that passes only ``overrides``
    (e.g. :mod:`swelter.exposure_brief`'s danger-day count) resolves exactly the floors it always
    has. A caller on another pack passes it, and the overrides land on that pack's floors instead.
    Either way the override-merge rule lives in one place, so the live alerts feed and a historical
    view can never re-derive it differently.

    Unknown keys are ignored here on purpose — a build must never crash mid-pipeline on a typo.
    But an ignored key is a silent safety failure (a host who typos ``heat_index_c`` as
    ``heat_index`` believes they lowered the danger floor and did not), so that same mistake is a
    **hard error** at load time: see ``config.config_concerns`` and ``swelter doctor``, which check
    every ``alert_thresholds`` key against the *active* pack's floors before a build ever gets here.
    """
    active = pack or hazard_packs.HEAT_PACK
    merged = active.default_floors()
    if overrides:
        for key, value in overrides.items():
            if key in merged:
                merged[key] = float(value)
    return merged


def pack_for_surface(
    config: NetworkConfig, surface: Surface
) -> tuple[hazard_packs.HazardPack, PackSelection | None]:
    """The pack this surface's alerts are read under, and the record of what chose it.

    One place, so every caller that builds a feed -- the CLI, the publish path and the live server
    -- resolves the season identically. The month comes from
    :meth:`~swelter.aggregate.Surface.newest_bucket`: the same reference instant the feed stamps
    itself with, the map's ``latestBucket()``, and the hour ``build_feed`` calls "now". Reading a
    wall clock here instead would make a replay of a fixed store produce different alerts on
    different days, which is exactly what ADR 0050 refused to ship.

    A surface with no cells at all has no month, so an ``auto-season`` network falls back to the
    default pack and publishes **no** selection record -- an honest absence. Publishing a month
    nothing was measured in would be a date invented to fill a field.
    """
    if config.hazard_pack != hazard_packs.AUTO_SEASON_PACK_ID:
        return hazard_packs.resolve_pack(config.hazard_pack), None
    newest = surface.newest_bucket()
    if newest is None:
        return hazard_packs.resolve_pack(None), None
    month = hazard_packs.month_of(newest)
    pack = hazard_packs.resolve_pack(
        config.hazard_pack, calendar=config.season_calendar, month=month
    )
    return pack, PackSelection(pack_id=pack.pack_id, selected_by="season-calendar", month=month)


def build_feed(
    surface: Surface,
    *,
    network: str = "swelter network",
    base_url: str = "http://localhost:8000",
    thresholds: Mapping[str, float] | None = None,
    pack: hazard_packs.HazardPack | None = None,
    pack_selection: PackSelection | None = None,
) -> AlertFeed:
    """Scan the surface's newest bucket and raise an alert for each danger crossing in it.

    An alert is about now, not an hour last week: a cell/parameter's *latest* reading only raises an
    alert if that reading's bucket equals the surface's newest bucket
    (:meth:`~swelter.aggregate.Surface.newest_bucket`) — the same reference instant
    ``web/app.js``'s ``latestBucket()`` uses to decide what counts as current on the map. A node
    that stops reporting keeps its last reading in ``latest_by_cell()``, but once a newer bucket
    exists anywhere on the surface, that stale reading no longer clears the bound and cannot raise
    an alert — it can no longer broadcast a danger crossing from before the node went dark. This
    needs no wall clock: "now" is derived entirely from the data present, so the artifact stays
    reproducible. A cell can raise more than one alert (hot *and* smoky); each is its own entry. The
    feed's bucket is the newest hour present in the surface, so an empty feed still carries a
    meaningful, data-derived timestamp.

    Suppressing the stale crossing is only half of it. An alerts feed that simply stops mentioning a
    block reads as an all-clear for that block, and "no alert" is the reassuring answer — the one
    swelter must never give by default when it cannot see. So every cell/parameter whose latest
    reading predates the newest bucket is published as a :class:`StaleArea` in ``feed.stale``: no
    value, an explicit "no current reading", when the block last reported, and whether an alert
    built from that last reading is being withdrawn (ADR 0036). Absence is stated, never implied.

    ``pack`` selects the hazard pack (:mod:`swelter.hazard_packs`) whose parameters and cited floors
    are checked; it defaults to the heat pack, so a caller that passes none gets the original
    heat/air behaviour unchanged. The cold pack, for example, checks wind chill instead of heat.
    """
    active = pack or hazard_packs.HEAT_PACK
    floors = resolve_thresholds(thresholds, active)
    latest = surface.latest_by_cell(aqi_window=active.aqi_window)
    newest = surface.newest_bucket() or ""
    alerts: list[Alert] = []
    stale: list[StaleArea] = []
    for area_id in sorted(latest):
        by_param = latest[area_id]
        for parameter in active.alerting_parameters():
            reading = by_param.get(parameter)
            if reading is None:
                continue
            if reading.bucket != newest:
                # This cell's latest reading for this parameter predates the surface's newest
                # bucket — the node behind it has gone quiet (or was never this recent). Its last
                # reading stays visible to anyone browsing history, but it does not get to keep
                # broadcasting a danger crossing into a feed stamped as current (issue #148). It is
                # published as an absence instead, so the block is not silently dropped from the
                # feed: `withdrawn` records whether the alert it would have raised is being pulled.
                stale.append(
                    StaleArea(
                        area_id=area_id,
                        area=reading.label or area_id,
                        lat=reading.lat,
                        lon=reading.lon,
                        parameter=parameter,
                        last_bucket=reading.bucket,
                        hours_since_last_reading=_hours_between(reading.bucket, newest),
                        withdrawn=crossing(parameter, reading, floors) is not None,
                        nodes=reading.nodes,
                    )
                )
                continue
            crossed = crossing(parameter, reading, floors)
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
                    history_context=reading.history_context,
                    history_context_reason=reading.history_context_reason,
                )
            )
    return AlertFeed(
        network=network,
        bucket=newest,
        thresholds=floors,
        alerts=tuple(alerts),
        stale=tuple(stale),
        base_url=base_url,
        event=detect_event(surface, active),
        aqi_window=active.aqi_window,
        pack_selection=pack_selection,
    )


def detect_event(surface: Surface, pack: hazard_packs.HazardPack) -> HazardEvent | None:
    """Evaluate the pack's event rule against the surface's newest hour, or ``None`` if it has none.

    Pure and data-derived: "now" is the surface's newest bucket, never the wall clock, so the
    verdict is reproducible from the same store.

    A cell qualifies when it has a reading in the newest bucket, in the rule's own window, at or
    above the floor, **and** a reading exactly ``lookback_hours`` earlier that it has risen at
    least ``rise`` above. Both halves are required, and both are per-cell. One node spiking with
    flat neighbours therefore produces one qualifying cell and no event, which is the whole reason
    the rule counts cells rather than readings.

    A cell whose earlier bucket is missing does not qualify, and is not treated as a rise from
    zero: an absent reading is not a low reading. If *no* cell has a comparable earlier bucket the
    rule reports ``evaluated=False`` rather than ``active=False``, because a question that could
    not be asked has not been answered "no".
    """
    rule = pack.event_rule
    if rule is None:
        return None
    newest = surface.newest_bucket() or ""
    history = surface.readings_for(rule.parameter, aqi_window=rule.aqi_window)
    earlier_bucket = _shift_hours(newest, -rule.lookback_hours)

    qualifying: list[str] = []
    comparable = 0
    for cell_id in sorted(history):
        by_bucket = history[cell_id]
        current = by_bucket.get(newest)
        previous = by_bucket.get(earlier_bucket) if earlier_bucket is not None else None
        if current is None or previous is None:
            continue
        comparable += 1
        if current.mean >= rule.floor and (current.mean - previous.mean) >= rule.rise:
            qualifying.append(cell_id)

    if earlier_bucket is None or comparable == 0:
        return HazardEvent(
            rule_id=pack.pack_id,
            parameter=rule.parameter,
            aqi_window=rule.aqi_window,
            evaluated=False,
            active=False,
            qualifying_cells=0,
            minimum_cells=rule.minimum_cells,
            floor=rule.floor,
            rise=rule.rise,
            lookback_hours=rule.lookback_hours,
            bucket=newest,
            reason=(
                f"not evaluated: no cell has a {rule.aqi_window} reading in both the current hour "
                f"and the hour {rule.lookback_hours} earlier, so no rise could be measured"
            ),
        )

    active = len(qualifying) >= rule.minimum_cells
    return HazardEvent(
        rule_id=pack.pack_id,
        parameter=rule.parameter,
        aqi_window=rule.aqi_window,
        evaluated=True,
        active=active,
        qualifying_cells=len(qualifying),
        minimum_cells=rule.minimum_cells,
        floor=rule.floor,
        rise=rule.rise,
        lookback_hours=rule.lookback_hours,
        bucket=newest,
        reason=(
            f"{len(qualifying)} of {comparable} comparable cells rose at least {rule.rise:g} to "
            f"{rule.floor:g} or above on the {rule.aqi_window} window over {rule.lookback_hours}h; "
            f"{rule.minimum_cells} are required"
        ),
        areas=tuple(qualifying),
    )


def _shift_hours(bucket: str, hours: int) -> str | None:
    """``bucket`` moved by whole hours, in the same format, or ``None`` if it is not a timestamp.

    ``None`` rather than a guess: an unparseable bucket must not silently become "the same hour",
    which would compare a cell against itself and report a rise of zero as a measurement.
    """
    try:
        moment = datetime.fromisoformat(bucket.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (moment + timedelta(hours=hours)).strftime("%Y-%m-%dT%H:00:00Z")


def _hours_between(earlier: str, later: str) -> int | None:
    """Whole hours from ``earlier`` to ``later``, or ``None`` when either is not a timestamp.

    Both arguments are surface hour buckets, so this stays data-derived — no wall clock. ``None``
    means "the size of this gap is unknown": an unparseable bucket must not be reported as a gap of
    zero hours, which would read as "it reported just now".
    """
    try:
        start = datetime.fromisoformat(earlier.replace("Z", "+00:00"))
        end = datetime.fromisoformat(later.replace("Z", "+00:00"))
    except ValueError:
        return None
    return int((end - start).total_seconds() // 3600)


def crossing(
    parameter: str, reading: CellReading, floors: Mapping[str, float]
) -> tuple[str, float] | None:
    """Return ``(severity_name, floor)`` if this reading crosses its threshold, else ``None``.

    Public so other modules can reuse the exact same danger-threshold *test* instead of re-deriving
    it — :mod:`swelter.exposure_brief` calls this once per hour to build the historical "N Danger
    days" count, and :mod:`swelter.alert_audit` calls it once per stored reading rather than
    reimplementing a second comparison the audit could then score a threshold nobody ships against.

    **The test is shared; the floor table is the caller's**, and that is the whole of what this
    guarantees. This docstring used to add that the two views of danger "can never silently drift
    apart", which was one claim too many: ``exposure_brief`` resolves the *heat* pack's floors
    whatever pack the network runs, so on a smoke network the feed raises no heat-index alert on an
    hour the brief counts as a Danger day. Sharing the comparison stops the two from disagreeing
    about *where* a band begins; it cannot stop them being handed different tables. See
    ``count_danger_days``, which now states which table it uses.

    One asymmetry worth knowing before adding a parameter here. The ``wind_chill_c`` branch reads
    its floor with ``.get`` and returns ``None`` when the key is absent, deliberately, so a caller
    reusing a heat-pack floor table gets no crossing rather than a crash. The other three branches
    subscript directly and raise ``KeyError`` on a floor table without their key. That is currently
    unreachable — ``build_feed`` iterates ``pack.alerting_parameters()``, ``alert_audit._crossings``
    filters to the same set, and ``exposure_brief`` only ever passes heat-pack floors, which carry
    all three keys — so it is a hazard for the next caller, not a live defect, and it is recorded
    here rather than "fixed" into a silent ``None`` that would publish "no danger" for a table that
    simply had no floor to check.
    """
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
        level = round(mean)
        if level >= floor:
            name = category or EXPOSURE_LEVELS[min(level, len(EXPOSURE_LEVELS) - 1)]
            return name, floor
        return None
    if parameter == "wind_chill_c":
        # Cold crosses *downward*: colder is worse, so a reading at or below the floor is the
        # danger, the mirror of the heat/air/exposure tests above. ``.get`` guards the case where a
        # caller reuses a heat-pack floor table (no ``wind_chill_c`` key) — no crossing, no crash.
        wind_chill_floor = floors.get("wind_chill_c")
        if wind_chill_floor is not None and mean <= wind_chill_floor:
            return wind_chill_category(mean)[1], wind_chill_floor
        return None
    return None


def _unit_for(parameter: str, aqi: int | None) -> str:
    if parameter in ("heat_index_c", "wind_chill_c"):
        return "degC"
    if parameter == "pm25_ugm3":
        return "AQI"
    return "level"
