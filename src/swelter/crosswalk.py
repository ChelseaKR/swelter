"""Outbound parameter crosswalk: swelter's vocabulary → OpenAQ / Sensor.Community.

swelter *ingests* real readings from OpenAQ and Sensor.Community (see
:mod:`swelter.sources.openaq` and :mod:`swelter.sources.sensor_community`), mapping their
parameter names into swelter's own vocabulary (``pm25_ugm3``, ``temp_c``, ...). This module is
the inverse direction: it tells a consumer of swelter's export — SensorThings JSON, CSV, or the
flat JSON dump — what the *same* quantity is called in those two commons networks, so a value
swelter publishes can be reasoned about in the vocabulary a downstream tool already knows. That
closes the loop: swelter feeds the commons it draws from, not just the other way round.

This module is honest about being a **label/vocabulary crosswalk, not a unit-conversion
service**: it maps a swelter parameter name to the corresponding OpenAQ parameter name (or
Sensor.Community ``value_type``) and reports the unit each network *would* attach to it, but it
never converts a numeric value between units. Two things follow from that:

* Every OpenAQ/Sensor.Community unit recorded here matches the unit that network's inbound
  adapter already assumes (``sources/openaq.py`` ``_PARAM``, ``sources/sensor_community.py``
  ``_MAP``) — the crosswalk is the exact inverse of those maps, so it is provably symmetric.
* ``no2_ppb`` is a case where that symmetry breaks honestly: swelter stores nitrogen dioxide in
  ppb, but OpenAQ v3 typically reports NO2 in µg/m³ (or ppm depending on the sensor). There is no
  inbound swelter adapter for OpenAQ NO2 today, so there is nothing to invert against; this
  module names the OpenAQ parameter (``no2``) and records swelter's own unit as a label only,
  **without pretending a conversion was performed** — a consumer must convert before comparing
  a swelter NO2 reading against an OpenAQ NO2 reading in µg/m³.
* Where a swelter parameter has no equivalent in a network at all (``heat_index_c`` is
  swelter-derived — combining temperature and humidity — and neither network publishes it, and
  Sensor.Community has no NO2 sensor), the crosswalk says so plainly: ``None``, not a guess.
"""

from __future__ import annotations

from typing import NamedTuple

from .models import PARAMETERS


class CrosswalkEntry(NamedTuple):
    """One parameter's outbound mapping: swelter name/unit, plus OpenAQ and Sensor.Community
    equivalents (name/unit), each ``None`` when the network has no equivalent quantity."""

    swelter_param: str
    swelter_unit: str
    openaq: tuple[str, str] | None
    sensor_community: tuple[str, str] | None


#: swelter parameter name → its outbound crosswalk entry. This is the inverse of
#: ``sources/openaq.py`` ``_PARAM`` and ``sources/sensor_community.py`` ``_MAP`` for every
#: parameter that has an inbound adapter; entries with no inbound adapter (``no2_ppb`` against
#: OpenAQ) are named honestly but not asserted symmetric, and entries with no commons equivalent
#: at all (``heat_index_c``; ``no2_ppb`` against Sensor.Community) map to ``None``.
_CROSSWALK: dict[str, CrosswalkEntry] = {
    "pm25_ugm3": CrosswalkEntry("pm25_ugm3", "ug/m3", ("pm25", "ug/m3"), ("P2", "ug/m3")),
    "pm10_ugm3": CrosswalkEntry("pm10_ugm3", "ug/m3", ("pm10", "ug/m3"), ("P1", "ug/m3")),
    "temp_c": CrosswalkEntry("temp_c", "degC", ("temperature", "degC"), ("temperature", "degC")),
    "humidity_pct": CrosswalkEntry(
        "humidity_pct", "%", ("relativehumidity", "%"), ("humidity", "%")
    ),
    "no2_ppb": CrosswalkEntry(
        # OpenAQ v3 typically reports NO2 in µg/m³ or ppm, not ppb — recorded honestly as
        # swelter's own unit label, since no unit conversion is performed here and there is no
        # inbound OpenAQ NO2 adapter to invert against. Sensor.Community has no NO2 sensor.
        "no2_ppb",
        "ppb",
        ("no2", "ppb"),
        None,
    ),
    "heat_index_c": CrosswalkEntry(
        # swelter-derived (from temp_c + humidity_pct via the NWS heat index formula) — neither
        # network publishes a heat index, so there is honestly nothing to map to.
        "heat_index_c",
        "degC",
        None,
        None,
    ),
}

assert set(_CROSSWALK) == set(PARAMETERS), (  # noqa: S101 (module-load invariant)
    "crosswalk must cover every swelter parameter"
)


def to_openaq(swelter_param: str) -> tuple[str, str] | None:
    """The (OpenAQ parameter name, unit) for a swelter parameter. ``None`` covers two distinct
    honest cases the caller cannot tell apart from the return value alone (and does not need
    to): ``swelter_param`` names a real swelter parameter with no OpenAQ equivalent
    (``heat_index_c``), or it is not a recognised swelter parameter at all."""
    entry = _CROSSWALK.get(swelter_param)
    return entry.openaq if entry is not None else None


def to_sensor_community(swelter_param: str) -> tuple[str, str] | None:
    """The (Sensor.Community ``value_type``, unit) for a swelter parameter. ``None`` covers two
    distinct honest cases the caller cannot tell apart from the return value alone (and does not
    need to): ``swelter_param`` names a real swelter parameter with no Sensor.Community
    equivalent (``heat_index_c``, ``no2_ppb``), or it is not a recognised swelter parameter at
    all."""
    entry = _CROSSWALK.get(swelter_param)
    return entry.sensor_community if entry is not None else None


def crosswalk_table() -> list[dict[str, str | None]]:
    """The full crosswalk as flat rows, for docs and the ``swelter crosswalk`` CLI command.

    Each row names the swelter parameter and unit, and the OpenAQ/Sensor.Community name+unit
    (``None`` fields render as empty/absent where a network has no equivalent).
    """
    rows: list[dict[str, str | None]] = []
    for name in PARAMETERS:  # PARAMETERS order, so the table reads in the model's own order
        entry = _CROSSWALK[name]
        openaq_name, openaq_unit = entry.openaq if entry.openaq else (None, None)
        sc_name, sc_unit = entry.sensor_community if entry.sensor_community else (None, None)
        rows.append(
            {
                "swelter_param": entry.swelter_param,
                "swelter_unit": entry.swelter_unit,
                "openaq_param": openaq_name,
                "openaq_unit": openaq_unit,
                "sensor_community_value_type": sc_name,
                "sensor_community_unit": sc_unit,
            }
        )
    return rows
