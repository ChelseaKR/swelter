"""``swelter cards``: printable bilingual neighborhood cards — the paper channel (EXP-11).

The dashboard and the alerts feed (ADR 0010) both assume a screen and a connection. The residents
most exposed to heat and bad air — isolated elders chief among them — are the least likely to have
either. This module composes one self-contained, print-ready HTML page: one card per published grid
cell, showing this hour's heat-index tier and PM2.5 AQI, the matching R1 guidance copy, the nearest
cooling center, and a QR code that scans to that cell's own alerts feed (``?area=<cell_id>``, the
same query parameter :mod:`swelter.alerts` already serves). Bilingual copy comes straight from the
committed ``web/i18n`` catalogs, so it stays single-sourced and covered by the i18n parity gate
(``tests/test_i18n.py``) — a Spanish card is never a second-class translation, it is the same
guidance string every other surface shows.

Framework-free like the rest of swelter's web surface: one HTML string, no JavaScript, all CSS
inline, print rules mirroring ``web/styles.css``'s ``@media print`` block. Every card is
self-describing — the data-hour and the provisional flag ride along — the same honesty discipline
the map and the alerts feed keep.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from html import escape
from math import asin, cos, radians, sin, sqrt
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from . import aggregate
from .aggregate import CellReading, Surface
from .cooling_centers import CoolingCenter, CoolingCenterSet
from .models import heat_index_category
from .qr import QRTooLargeError, qr_svg

ROOT = Path(__file__).resolve().parents[2]
I18N_DIR = ROOT / "web" / "i18n"

# Mirrors CAT_SLUG / HEAT_SLUG in web/app.js — the i18n key slugs for each published category name.
# Kept in sync by hand (JS and Python can't share a literal); tests/test_i18n.py guards the catalogs
# these slugs point into, so a drift here shows up as a missing-guidance string, not a silent gap.
_CAT_SLUG: dict[str, str] = {
    "Good": "good",
    "Moderate": "moderate",
    "Unhealthy for Sensitive Groups": "usg",
    "Unhealthy": "unhealthy",
    "Very Unhealthy": "vu",
    "Hazardous": "haz",
}
_HEAT_SLUG: dict[str, str] = {
    "None": "none",
    "Caution": "caution",
    "Extreme Caution": "xcaution",
    "Danger": "danger",
    "Extreme Danger": "xdanger",
}
_COOL_TYPE_SLUGS = (
    "library",
    "community-center",
    "senior-center",
    "cooling-center",
    "public",
)


def load_strings(lang: str) -> dict[str, str]:
    """Load one shipped i18n catalog (``web/i18n/{lang}.json``), same repo-relative path
    :mod:`tests.test_i18n` uses, so a card's copy and the parity gate read the same file."""
    path = I18N_DIR / f"{lang}.json"
    data: dict[str, str] = json.loads(path.read_text(encoding="utf-8"))
    return data


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km. Mirrors ``haversine()`` in web/app.js exactly (same formula,
    same 6371 km earth radius) so a card's distance and the dashboard's agree."""
    d_lat = radians(lat2 - lat1)
    d_lon = radians(lon2 - lon1)
    a = sin(d_lat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(d_lon / 2) ** 2
    return 6371.0 * 2 * asin(sqrt(a))


def nearest_cooling_center(
    lat: float, lon: float, centers: CoolingCenterSet
) -> tuple[CoolingCenter, float] | None:
    """The closest cooling center to ``(lat, lon)`` and its distance in km, or ``None`` if the
    dataset is empty."""
    best: tuple[CoolingCenter, float] | None = None
    for center in centers.centers:
        d = _haversine_km(lat, lon, center.lat, center.lon)
        if best is None or d < best[1]:
            best = (center, d)
    return best


def _feed_url_for_cell(feed_url: str, cell_id: str) -> str:
    """``feed_url`` narrowed to one cell via ``?area=<cell_id>`` — the same per-neighborhood
    subscription query :meth:`swelter.alerts.AlertFeed.for_area` and the live server accept."""
    if not feed_url:
        return ""
    parts = urlsplit(feed_url)
    query = dict(parse_qsl(parts.query))
    query["area"] = cell_id
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def _t(strings: dict[str, str], key: str, default: str = "") -> str:
    return strings.get(key, default)


def _guidance(
    strings: dict[str, str], *, heat_tier: str | None, air_category: str | None
) -> list[str]:
    """The matching R1 guidance strings for whichever hazard(s) this cell reports."""
    lines: list[str] = []
    air_slug = _CAT_SLUG.get(air_category or "")
    if air_slug:
        text = _t(strings, f"guide-{air_slug}")
        if text:
            lines.append(text)
    heat_slug = _HEAT_SLUG.get(heat_tier or "")
    if heat_slug and heat_slug != "none":
        text = _t(strings, f"heat-guide-{heat_slug}")
        if text:
            lines.append(text)
    return lines


def _local_category(strings: dict[str, str], category: str | None) -> str:
    slug = _CAT_SLUG.get(category or "")
    return _t(strings, f"cat-{slug}", category or "") if slug else (category or "")


def _local_heat_tier(strings: dict[str, str], tier: str | None) -> str:
    slug = _HEAT_SLUG.get(tier or "")
    return _t(strings, f"heat-{slug}", tier or "") if slug else (tier or "")


def _local_cooling_type(strings: dict[str, str], center_type: str) -> str:
    slug = center_type if center_type in _COOL_TYPE_SLUGS else "public"
    return _t(strings, f"cool-type-{slug}", center_type)


@dataclass(frozen=True)
class _CellReadings:
    cell_id: str
    label: str
    lat: float
    lon: float
    bucket: str
    provisional: bool
    heat: CellReading | None
    air: CellReading | None
    exposure: CellReading | None


def _collect(by_param: dict[str, CellReading]) -> _CellReadings:
    any_reading = next(iter(by_param.values()))
    buckets = [r.bucket for r in by_param.values()]
    return _CellReadings(
        cell_id=any_reading.cell_id,
        label=any_reading.label or any_reading.cell_id,
        lat=any_reading.lat,
        lon=any_reading.lon,
        bucket=max(buckets),
        provisional=any(r.provisional for r in by_param.values()),
        heat=by_param.get("heat_index_c"),
        air=by_param.get("pm25_ugm3"),
        exposure=by_param.get(aggregate.EXPOSURE),
    )


def _heat_tier(cell: _CellReadings) -> str | None:
    if cell.exposure is not None and cell.exposure.heat_category:
        return cell.exposure.heat_category
    if cell.heat is not None:
        return heat_index_category(cell.heat.mean)[1]
    return None


def _air_category(cell: _CellReadings) -> str | None:
    if cell.exposure is not None and cell.exposure.air_category:
        return cell.exposure.air_category
    if cell.air is not None:
        return cell.air.category
    return None


def _render_readings(strings: dict[str, str], cell: _CellReadings) -> str:
    rows: list[str] = []
    if cell.heat is not None:
        tier = _heat_tier(cell)
        tier_label = _local_heat_tier(strings, tier)
        value = f"{cell.heat.mean:.1f}°C"
        rows.append(
            f'<div class="reading reading-heat"><span class="reading-label">'
            f"{escape(_t(strings, 'param-hi', 'Heat index'))}</span> "
            f'<span class="reading-value">{escape(value)}</span>'
            f' <span class="reading-cat">{escape(tier_label)}</span></div>'
        )
    if cell.air is not None:
        category = _air_category(cell)
        cat_label = _local_category(strings, category)
        aqi = cell.air.aqi
        rows.append(
            f'<div class="reading reading-air"><span class="reading-label">'
            f"{escape(_t(strings, 'param-pm25', 'PM2.5'))}</span> "
            f'<span class="reading-value">AQI {aqi if aqi is not None else "—"}</span>'
            f' <span class="reading-cat">{escape(cat_label)}</span></div>'
        )
    if cell.exposure is not None and cell.exposure.compound:
        rows.append(
            f'<div class="reading reading-compound">{escape(_t(strings, "exp-compound", ""))}</div>'
        )
    if not rows:
        rows.append(
            f'<div class="reading reading-none">{escape(_t(strings, "no-data", "No data"))}</div>'
        )
    return "".join(rows)


def _render_guidance(strings: dict[str, str], cell: _CellReadings) -> str:
    lines = _guidance(strings, heat_tier=_heat_tier(cell), air_category=_air_category(cell))
    if not lines:
        return ""
    items = "".join(f"<li>{escape(line)}</li>" for line in lines)
    return f'<ul class="guidance">{items}</ul>'


def _render_cooling(
    strings: dict[str, str], cell: _CellReadings, cooling_centers: CoolingCenterSet
) -> str:
    found = nearest_cooling_center(cell.lat, cell.lon, cooling_centers)
    if found is None:
        return ""
    center, km = found
    heading = escape(_t(strings, "cooling-heading", "Cooling centers"))
    name = escape(center.name)
    type_label = escape(_local_cooling_type(strings, center.type))
    distance = escape(
        _t(strings, "cool-distance", "about {km} km away").replace("{km}", f"{km:.1f}")
    )
    parts = [f'<div class="cooling"><p class="cooling-heading">{heading}</p>']
    parts.append(
        f'<p class="cooling-name">{name} <span class="cooling-type">({type_label})</span></p>'
    )
    parts.append(f'<p class="cooling-distance">{distance}</p>')
    if center.hours:
        hours = escape(_t(strings, "cool-hours", "Hours: {hours}").replace("{hours}", center.hours))
        parts.append(f'<p class="cooling-hours">{hours}</p>')
    if center.accessible is not None:
        key = "cool-accessible" if center.accessible else "cool-not-accessible"
        parts.append(f'<p class="cooling-accessible">{escape(_t(strings, key, key))}</p>')
    if center.air_conditioned is not None:
        key = "cool-ac" if center.air_conditioned else "cool-no-ac"
        parts.append(f'<p class="cooling-ac">{escape(_t(strings, key, key))}</p>')
    parts.append("</div>")
    return "".join(parts)


def _render_provenance(strings: dict[str, str], cell: _CellReadings) -> str:
    state_key = "state-provisional" if cell.provisional else "state-calibrated"
    state = escape(_t(strings, state_key, state_key))
    cls = "provenance provisional" if cell.provisional else "provenance confirmed"
    return f'<p class="{cls}">{escape(cell.bucket)} · {state}</p>'


def _render_qr(cell: _CellReadings, feed_url: str) -> str:
    url = _feed_url_for_cell(feed_url, cell.cell_id)
    if not url:
        return ""
    try:
        svg = qr_svg(url, module_px=3)
    except QRTooLargeError:
        # A long --feed-url (or a verbose cell_id) can push the per-cell URL past the QR encoder's
        # capacity. Degrade to a text-only link for this one cell rather than let the whole cards
        # page fail to render — the same graceful-omission pattern as the `if not url` case above.
        svg = ""
    return (
        '<div class="qr">'
        f"{svg}"
        f'<p class="qr-url"><a href="{escape(url)}">{escape(url)}</a></p>'
        "</div>"
    )


def _render_card(
    strings: dict[str, str], cell: _CellReadings, cooling_centers: CoolingCenterSet, feed_url: str
) -> str:
    return (
        '<section class="card">'
        f'<h2 class="card-label">{escape(cell.label)}</h2>'
        f"{_render_readings(strings, cell)}"
        f"{_render_guidance(strings, cell)}"
        f"{_render_cooling(strings, cell, cooling_centers)}"
        f"{_render_qr(cell, feed_url)}"
        f"{_render_provenance(strings, cell)}"
        "</section>"
    )


_STYLE = """
:root { color-scheme: light; }
* { box-sizing: border-box; }
body {
  margin: 0;
  padding: 1rem;
  font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
  font-size: 14px;
  color: #111;
  background: #fff;
}
body.large-type { font-size: 20px; }
.cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 1rem;
}
.card {
  border: 2px solid #111;
  border-radius: 6px;
  padding: 1rem;
  break-inside: avoid;
  page-break-inside: avoid;
}
.card-label { margin: 0 0 0.5rem; font-size: 1.3em; }
.reading { margin: 0.25rem 0; }
.reading-label { font-weight: 600; }
.reading-cat { font-style: italic; }
.guidance { margin: 0.5rem 0; padding-left: 1.25em; }
.guidance li { margin: 0.25rem 0; }
.cooling { margin: 0.5rem 0; border-top: 1px dashed #111; padding-top: 0.5rem; }
.cooling-heading { font-weight: 600; margin: 0 0 0.25rem; }
.cooling p { margin: 0.15rem 0; }
.qr { margin: 0.5rem 0; text-align: center; }
.qr svg { width: 96px; height: 96px; }
.qr-url { font-family: monospace; font-size: 0.75em; word-break: break-all; }
.provenance { margin: 0.5rem 0 0; font-size: 0.8em; color: #333; }
.provenance.provisional { font-style: italic; }
@media print {
  @page { margin: 1.2cm; }
  body { background: #fff; color: #000; }
  .cards { display: block; }
  .card {
    break-inside: avoid;
    page-break-inside: avoid;
    margin: 0 0 1cm;
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
  }
}
"""


def render_cards(
    surface: Surface,
    cooling_centers: CoolingCenterSet,
    *,
    lang: str = "en",
    area: str | None = None,
    large_type: bool = False,
    feed_url: str = "",
) -> str:
    """Render one self-contained, print-ready HTML page: one bilingual card per published grid
    cell (or just ``area`` if given), each self-describing with its data-hour and provisional
    flag like every other swelter surface."""
    strings = load_strings(lang)
    by_cell = surface.latest_by_cell()
    if area:
        by_cell = {area: by_cell[area]} if area in by_cell else {}
    cells = [_collect(by_param) for _cell_id, by_param in sorted(by_cell.items()) if by_param]

    body_class = "large-type" if large_type else ""
    if cells:
        cards_html = "".join(_render_card(strings, c, cooling_centers, feed_url) for c in cells)
    else:
        cards_html = f'<p class="no-data">{escape(_t(strings, "no-data", "No data"))}</p>'

    title = escape(_t(strings, "tagline", "swelter"))
    return (
        "<!doctype html>"
        f'<html lang="{escape(lang)}">'
        "<head>"
        '<meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{title}</title>"
        f"<style>{_STYLE}</style>"
        "</head>"
        f'<body class="{body_class}">'
        f'<main class="cards">{cards_html}</main>'
        "</body></html>"
    )
