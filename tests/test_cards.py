"""Printable bilingual neighborhood cards (EXP-11): one door-flyer/fridge card per published
cell, self-describing (data-hour + provisional) and single-sourced from the committed i18n
catalogs, like every other swelter surface."""

from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path

from swelter import aggregate, cards
from swelter.cli import main
from swelter.config import NetworkConfig, NodeConfig
from swelter.cooling_centers import CoolingCenter, CoolingCenterSet, empty, from_features
from swelter.models import Observation
from swelter.store import store_paths

from .conftest import make_obs

_NODE = NodeConfig(
    node_id="node-01", label="Oak & 4th", lat=38.5816, lon=-121.4944, location="precise"
)
_CONFIG = NetworkConfig(grid_resolution_m=150.0, nodes=(_NODE,))


class _LinkCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            self.hrefs.extend(
                value for name, value in attrs if name == "href" and value is not None
            )


def _surface(*obs: Observation) -> aggregate.Surface:
    return aggregate.aggregate(obs, _CONFIG)


def test_card_contains_the_cell_label() -> None:
    surface = _surface(make_obs(parameter="heat_index_c", value=41.0, calibration="v1"))
    html = cards.render_cards(surface, empty(), lang="en", feed_url="")
    assert "Oak &amp; 4th" in html  # the card HTML-escapes the host-assigned label


def test_lang_es_swaps_guidance_strings_for_en() -> None:
    # 40 ug/m3 -> AQI ~112, "Unhealthy for Sensitive Groups" -> guide-usg.
    surface = _surface(make_obs(parameter="pm25_ugm3", unit="ug/m3", value=40.0, calibration="v1"))
    en_strings = cards.load_strings("en")
    es_strings = cards.load_strings("es")
    assert en_strings["guide-usg"] != es_strings["guide-usg"]

    en_html = cards.render_cards(surface, empty(), lang="en", feed_url="")
    es_html = cards.render_cards(surface, empty(), lang="es", feed_url="")

    assert en_strings["guide-usg"] in en_html
    assert es_strings["guide-usg"] in es_html
    assert es_strings["guide-usg"] not in en_html
    assert en_strings["guide-usg"] not in es_html


def test_large_type_variant_sets_the_bigger_base_font_rule() -> None:
    surface = _surface(make_obs(parameter="temp_c", value=25.0, calibration="v1"))
    normal = cards.render_cards(surface, empty(), large_type=False, feed_url="")
    big = cards.render_cards(surface, empty(), large_type=True, feed_url="")
    assert 'class="large-type"' in big
    assert 'class="large-type"' not in normal
    # The CSS rule that actually bumps the font size is always shipped (it's a static class rule);
    # what changes is whether <body> wears the class.
    assert "body.large-type" in normal
    assert "body.large-type" in big


def test_feed_qr_and_link_are_present_per_cell() -> None:
    surface = _surface(make_obs(parameter="temp_c", value=25.0, calibration="v1"))
    html = cards.render_cards(surface, empty(), feed_url="https://example.org/api/alerts.xml")
    assert "<svg" in html
    assert "https://example.org/api/alerts.xml?area=" in html


def test_no_feed_url_omits_the_qr_block() -> None:
    surface = _surface(make_obs(parameter="temp_c", value=25.0, calibration="v1"))
    html = cards.render_cards(surface, empty(), feed_url="")
    assert "<svg" not in html


def test_a_feed_url_too_long_for_the_qr_encoder_degrades_to_link_only() -> None:
    # A verbose --feed-url (or a long cell_id folded into ?area=) can push the per-cell URL past
    # what qr.qr_svg can encode; the page must still render — just without that cell's QR image —
    # rather than let one long URL take down the whole cards run (cards.py:_render_qr).
    surface = _surface(make_obs(parameter="temp_c", value=25.0, calibration="v1"))
    long_feed_url = "https://example.org/" + "a" * 300 + "/api/alerts.xml"
    html = cards.render_cards(surface, empty(), feed_url=long_feed_url)
    assert "<svg" not in html  # QR omitted for the too-long URL …
    links = _LinkCollector()
    links.feed(html)
    expected = cards._feed_url_for_cell(long_feed_url, surface.cells[0].cell_id)
    assert links.hrefs == [expected]  # … but the complete, correctly scoped text link still renders


def test_nearest_cooling_center_is_selected_over_a_farther_one() -> None:
    near = CoolingCenter(name="Near Library", lat=38.5816, lon=-121.4944)  # same spot as the node
    far = CoolingCenter(name="Far Center", lat=39.5, lon=-122.5)
    dataset: CoolingCenterSet = from_features([far, near])
    surface = _surface(make_obs(parameter="temp_c", value=25.0, calibration="v1"))
    html = cards.render_cards(surface, dataset, feed_url="")
    assert "Near Library" in html
    assert "Far Center" not in html


def test_nearest_cooling_center_helper_picks_the_minimum_distance() -> None:
    near = CoolingCenter(name="Near", lat=38.58, lon=-121.49)
    far = CoolingCenter(name="Far", lat=40.0, lon=-124.0)
    dataset = from_features([far, near])
    found = cards.nearest_cooling_center(38.5816, -121.4944, dataset)
    assert found is not None
    center, km = found
    assert center.name == "Near"
    assert km < 5.0


def test_provisional_cell_renders_the_provisional_flag() -> None:
    # No `calibration=` -> RAW -> provisional.
    surface = _surface(make_obs(parameter="pm25_ugm3", unit="ug/m3", value=40.0))
    strings = cards.load_strings("en")
    html = cards.render_cards(surface, empty(), lang="en", feed_url="")
    assert strings["state-provisional"] in html
    assert 'class="provenance provisional"' in html


def test_confirmed_cell_does_not_render_the_provisional_flag() -> None:
    surface = _surface(make_obs(parameter="pm25_ugm3", unit="ug/m3", value=40.0, calibration="v1"))
    html = cards.render_cards(surface, empty(), lang="en", feed_url="")
    assert 'class="provenance provisional"' not in html


def test_area_filter_limits_to_one_cell() -> None:
    other_node = NodeConfig(
        node_id="node-02", label="Cedar & 4th", lat=38.60, lon=-121.55, location="precise"
    )
    config = NetworkConfig(grid_resolution_m=150.0, nodes=(_NODE, other_node))
    surface = aggregate.aggregate(
        [
            make_obs(node_id="node-01", parameter="temp_c", value=25.0, calibration="v1"),
            make_obs(node_id="node-02", parameter="temp_c", value=25.0, calibration="v1"),
        ],
        config,
    )
    by_cell = surface.latest_by_cell()
    one_cell_id = next(iter(by_cell))
    html = cards.render_cards(surface, empty(), area=one_cell_id, feed_url="")
    assert html.count('class="card"') == 1


def test_load_strings_reads_the_shipped_catalogs() -> None:
    en = cards.load_strings("en")
    es = cards.load_strings("es")
    assert en["tagline"]
    assert es["tagline"]
    assert en["tagline"] != es["tagline"]


def test_cli_cards_writes_html_to_out(tmp_path: Path) -> None:
    store_dir = tmp_path / "store"
    config_path = tmp_path / "network.yaml"
    config_path.write_text(
        "name: Test Network\n"
        "grid_resolution_m: 150\n"
        "nodes:\n"
        "- node_id: node-01\n"
        "  label: Oak & 4th\n"
        "  lat: 38.5816\n"
        "  lon: -121.4944\n"
        "  location: precise\n",
        encoding="utf-8",
    )
    paths = store_paths(str(store_dir))
    from swelter.store import SqliteStore

    with SqliteStore(paths["db"]) as store:
        store.write([make_obs(parameter="heat_index_c", value=41.0, calibration="v1")])

    out = tmp_path / "cards.html"
    rc = main(
        [
            "cards",
            "--store",
            str(store_dir),
            "--config",
            str(config_path),
            "--cooling-centers",
            str(tmp_path / "missing.geojson"),  # absent dataset -> empty overlay, no crash
            "--lang",
            "es",
            "--large-type",
            "--feed-url",
            "https://example.org/feed",
            "--out",
            str(out),
        ]
    )
    assert rc == 0
    html = out.read_text(encoding="utf-8")
    assert "Oak &amp; 4th" in html
    assert 'class="large-type"' in html
