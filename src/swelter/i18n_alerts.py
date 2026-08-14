"""gettext-backed EN/ES messages for the generated neighborhood-alert feeds.

The browser dashboard and the generated feed are separate localization surfaces. Feed text is
rendered by Python before it reaches JSON or Atom clients, so it uses the portfolio's canonical
Python stack: gettext PO source catalogs compiled to MO files. ``babel.cfg`` and
``scripts/gettext_catalog_check.py`` keep the committed POT template extractable and prove that
both locale catalogs compile, have identical message ids, and preserve placeholders.

Spanish remains machine-drafted pending the independent review tracked in issue #106. Every
Spanish feed surface carries :data:`TRANSLATION_LABEL`; moving the storage format does not upgrade
the translation's review status.
"""

from __future__ import annotations

import gettext
from functools import lru_cache
from pathlib import Path
from typing import Final, Protocol

MACHINE_TRANSLATED: Final[bool] = True
TRANSLATION_LABEL: Final[str] = "machine"
LANGUAGES: Final[tuple[str, ...]] = ("en", "es")

_DOMAIN: Final[str] = "alerts"
_LOCALE_DIR: Final[Path] = Path(__file__).with_name("locales")


class _AlertLike(Protocol):
    """Read-only alert fields needed to render a localized headline."""

    @property
    def area(self) -> str: ...

    @property
    def parameter(self) -> str: ...

    @property
    def severity(self) -> str: ...

    @property
    def bucket(self) -> str: ...

    @property
    def value(self) -> float: ...

    @property
    def provisional(self) -> bool: ...

    @property
    def aqi(self) -> int | None: ...


class _StaleLike(Protocol):
    """Read-only stale-area fields needed to render a localized "no current reading" line."""

    @property
    def area(self) -> str: ...

    @property
    def parameter(self) -> str: ...

    @property
    def last_bucket(self) -> str: ...

    @property
    def hours_since_last_reading(self) -> int | None: ...

    @property
    def withdrawn(self) -> bool: ...


@lru_cache(maxsize=len(LANGUAGES))
def get_translation(lang: str) -> gettext.NullTranslations:
    """Return the compiled translation for ``lang``, with a safe English fallback."""

    language = lang if lang in LANGUAGES else "en"
    return gettext.translation(
        _DOMAIN,
        localedir=_LOCALE_DIR,
        languages=[language],
        fallback=True,
    )


def headline(alert: _AlertLike, lang: str = "en") -> str:
    """Return one alert's plain-language headline in ``lang`` (English by default)."""

    _ = get_translation(lang).gettext
    provisional = _(" (provisional, not yet calibrated)") if alert.provisional else ""
    as_of = _(", as of {bucket}.").format(bucket=alert.bucket)
    if alert.parameter == "pm25_ugm3":
        template = _("{area}: air quality is {severity} (AQI {aqi}){provisional}{as_of}")
        return template.format(
            area=alert.area,
            severity=alert.severity,
            aqi=alert.aqi,
            provisional=provisional,
            as_of=as_of,
        )
    if alert.parameter == "heat_index_c":
        template = _(
            "{area}: heat index is in the {severity} range ({value} °C){provisional}{as_of}"
        )
        return template.format(
            area=alert.area,
            severity=alert.severity,
            value=alert.value,
            provisional=provisional,
            as_of=as_of,
        )
    if alert.parameter == "wind_chill_c":
        template = _("{area}: wind chill is {value} °C ({severity}){provisional}{as_of}")
        return template.format(
            area=alert.area,
            severity=alert.severity,
            value=alert.value,
            provisional=provisional,
            as_of=as_of,
        )
    template = _("{area}: combined heat-and-air exposure is {severity}{provisional}{as_of}")
    return template.format(
        area=alert.area,
        severity=alert.severity,
        provisional=provisional,
        as_of=as_of,
    )


def stale_headline(area: _StaleLike, lang: str = "en") -> str:
    """Return one stale area's "no current reading" line in ``lang`` (English by default).

    Deliberately states the gap and stops. There is no value in the sentence because there is no
    current measurement to report, and the last one is not a measurement of now.
    """

    _ = get_translation(lang).gettext
    if area.hours_since_last_reading is None:
        # The gap's size is unknown; say only when it last reported, never "0 h ago".
        age = _(" (last reported {bucket})").format(bucket=area.last_bucket)
    else:
        age = _(" (last reported {bucket}, {hours} h before this feed)").format(
            bucket=area.last_bucket, hours=area.hours_since_last_reading
        )
    withdrawn = (
        _(
            " The danger alert published for this area is withdrawn, not cleared: swelter has no "
            "current reading there."
        )
        if area.withdrawn
        else ""
    )
    if area.parameter == "pm25_ugm3":
        template = _(
            "{area}: no current air-quality reading{age}. swelter cannot tell whether the air "
            "there is dangerous now.{withdrawn}"
        )
    elif area.parameter == "heat_index_c":
        template = _(
            "{area}: no current heat-index reading{age}. swelter cannot tell whether the heat "
            "there is dangerous now.{withdrawn}"
        )
    elif area.parameter == "wind_chill_c":
        template = _(
            "{area}: no current wind-chill reading{age}. swelter cannot tell whether the cold "
            "there is dangerous now.{withdrawn}"
        )
    else:
        template = _(
            "{area}: no current heat-and-air exposure reading{age}. swelter cannot tell whether "
            "the exposure there is dangerous now.{withdrawn}"
        )
    return template.format(area=area.area, age=age, withdrawn=withdrawn)


def stale_note(lang: str = "en") -> str:
    """Return the JSON feed's note about what the ``stale`` list means, in ``lang``."""

    return get_translation(lang).gettext(
        "Areas listed under 'stale' have stopped reporting: swelter cannot tell whether they are "
        "safe. An empty 'alerts' list means no currently reporting area crossed a danger floor, "
        "not that every area is fine."
    )


def note(lang: str = "en") -> str:
    """Return the JSON feed's explanatory note in ``lang``."""

    return get_translation(lang).gettext(
        "Public, aggregate environmental alerts — no account, no PII. Subscribe via the "
        "Atom feed at /api/alerts.xml in any reader; live servers accept ?area=<area_id>."
    )


def feed_title(network: str, lang: str = "en") -> str:
    """Return the Atom feed title in ``lang``."""

    return (
        get_translation(lang)
        .gettext("{network} — heat & air-quality alerts")
        .format(network=network)
    )


def feed_subtitle(lang: str = "en") -> str:
    """Return the Atom feed subtitle in ``lang``."""

    return get_translation(lang).gettext(
        "Areas where heat or air quality has crossed a public-health danger threshold. "
        "Aggregate environmental data, no PII."
    )
