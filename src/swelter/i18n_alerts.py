"""Server-side EN/ES catalog for the neighborhood-alerts feed (:mod:`swelter.alerts`).

The dashboard's own strings live in ``web/i18n/{en,es}.json`` and are rendered client-side. The
alerts feed is different: its headlines, the Atom feed's title/subtitle, and the JSON feed's
``note`` are baked server-side into ``alerts.json`` / ``alerts.xml`` (and, with this module,
``alerts.es.xml``) so a reader, webhook bridge, or RSS client sees Spanish text with no
client-side rendering step at all. This module is that catalog — the same shape as the
dashboard's, kept in Python because it templates server-rendered, not DOM-rendered, strings.

Key names mirror ``web/i18n`` where the same concept exists (``aa-air`` / ``aa-heat`` /
``aa-exposure`` name the same three headline kinds the dashboard's own alert cards use), so a
translator working either catalog recognizes the string.

Every Spanish value here is machine-drafted, not human-reviewed — swelter has no in-house
translation review process yet. :data:`MACHINE_TRANSLATED` records that fact in code, and every
surface that renders these strings (the JSON feed's ``"translation"`` field, the Atom feed's
``<generator>``) labels it too, so a Spanish-speaking reader is never told machine output is a
vetted human translation (the same honesty ``provisional: true`` gives an uncalibrated reading).

``scripts/i18n_parity.py`` loads :data:`ALERT_STRINGS` alongside the dashboard catalogs and runs
the same EN/ES key-parity and non-empty-ES checks against it, so a key added to one language and
not the other fails CI here exactly as it would for the dashboard.
"""

from __future__ import annotations

from typing import Final, Protocol

#: Every Spanish string in this module is machine-drafted (no human translation review exists
#: yet for swelter). Surfaces that render ES output must label it — see ``note()`` / the Atom
#: ``<generator>`` written by :meth:`swelter.alerts.AlertFeed.to_atom` — never present as reviewed.
MACHINE_TRANSLATED: Final[bool] = True

#: The label surfaced alongside any ES output (JSON ``"translation"`` field, Atom generator note).
TRANSLATION_LABEL: Final[str] = "machine"

#: Languages this catalog ships. English is the reference; every other key must reach parity.
LANGUAGES: Final[tuple[str, ...]] = ("en", "es")

#: Server-side alert strings, keyed by language then by template name. ``{area}``, ``{severity}``,
#: ``{aqi}``, ``{value}``, ``{bucket}``, ``{network}`` are filled in by :func:`headline` /
#: :func:`feed_title` / :func:`feed_subtitle`; ``{prov}`` and ``{when}`` are the provisional and
#: as-of suffixes, already rendered, so the three headline templates share one shape.
ALERT_STRINGS: Final[dict[str, dict[str, str]]] = {
    "en": {
        "aa-air": "{area}: air quality is {severity} (AQI {aqi}){prov}{when}",
        "aa-heat": "{area}: heat index is in the {severity} range ({value} °C){prov}{when}",
        "aa-exposure": "{area}: combined heat-and-air exposure is {severity}{prov}{when}",
        "aa-prov-suffix": " (provisional, not yet calibrated)",
        "aa-as-of": ", as of {bucket}.",
        "aa-json-note": (
            "Public, aggregate environmental alerts — no account, no PII. Subscribe via the "
            "Atom feed at /api/alerts.xml in any reader; live servers accept ?area=<area_id>."
        ),
        "aa-feed-title": "{network} — heat & air-quality alerts",
        "aa-feed-subtitle": (
            "Areas where heat or air quality has crossed a public-health danger threshold. "
            "Aggregate environmental data, no PII."
        ),
    },
    "es": {
        "aa-air": "{area}: la calidad del aire es {severity} (AQI {aqi}){prov}{when}",
        "aa-heat": (
            "{area}: el índice de calor está en el rango {severity} ({value} °C){prov}{when}"
        ),
        "aa-exposure": "{area}: la exposición combinada de calor y aire es {severity}{prov}{when}",
        "aa-prov-suffix": " (provisional, aún sin calibrar)",
        "aa-as-of": ", a partir de {bucket}.",
        "aa-json-note": (
            "Alertas ambientales públicas y agregadas — sin cuenta, sin datos "
            "personales. Suscríbete al feed Atom en /api/alerts.xml con cualquier lector; "
            "los servidores en vivo aceptan ?area=<area_id>."
        ),
        "aa-feed-title": "{network} — alertas de calor y calidad del aire",
        "aa-feed-subtitle": (
            "Zonas donde el calor o la calidad del aire superó un umbral de peligro de salud "
            "pública. Datos ambientales agregados, sin datos personales."
        ),
    },
}


class _AlertLike(Protocol):
    """The subset of :class:`swelter.alerts.Alert` this module needs, kept structural (not a
    direct import) so the two modules don't form an import cycle. Declared as read-only
    properties (not plain attributes) so a frozen dataclass's read-only fields satisfy it."""

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


def _strings(lang: str) -> dict[str, str]:
    """The catalog for ``lang``, falling back to English for an unrecognised code."""
    return ALERT_STRINGS.get(lang, ALERT_STRINGS["en"])


def headline(alert: _AlertLike, lang: str = "en") -> str:
    """The plain-language headline for one alert, in ``lang`` (default English).

    Mirrors :meth:`swelter.alerts.Alert.headline`'s EN wording exactly, so switching languages
    never changes which facts are stated — only their language.
    """
    strings = _strings(lang)
    prov = strings["aa-prov-suffix"] if alert.provisional else ""
    when = strings["aa-as-of"].format(bucket=alert.bucket)
    if alert.parameter == "pm25_ugm3":
        return strings["aa-air"].format(
            area=alert.area, severity=alert.severity, aqi=alert.aqi, prov=prov, when=when
        )
    if alert.parameter == "heat_index_c":
        return strings["aa-heat"].format(
            area=alert.area, severity=alert.severity, value=alert.value, prov=prov, when=when
        )
    return strings["aa-exposure"].format(
        area=alert.area, severity=alert.severity, prov=prov, when=when
    )


def note(lang: str = "en") -> str:
    """The JSON feed's ``note`` field, in ``lang`` (default English)."""
    return _strings(lang)["aa-json-note"]


def feed_title(network: str, lang: str = "en") -> str:
    """The Atom feed's ``<title>``, in ``lang``."""
    return _strings(lang)["aa-feed-title"].format(network=network)


def feed_subtitle(lang: str = "en") -> str:
    """The Atom feed's ``<subtitle>``, in ``lang``."""
    return _strings(lang)["aa-feed-subtitle"]
