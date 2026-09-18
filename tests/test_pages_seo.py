"""Technical-SEO build output stays route-, source-, and license-correct."""

from __future__ import annotations

import importlib
import json
import re
import shutil
import struct
import sys
import xml.etree.ElementTree as ET
from dataclasses import replace
from html import escape
from html.parser import HTMLParser
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

import pytest

from swelter.cli import PUBLISH_FILES

ROOT = Path(__file__).resolve().parent.parent
if TYPE_CHECKING:
    from scripts import pages_seo
else:
    # Pytest's importlib mode intentionally omits the repository root from sys.path. The build
    # script is not an installed runtime module, so load it from the checkout just as CI does.
    sys.path.insert(0, str(ROOT))
    pages_seo = importlib.import_module("scripts.pages_seo")

BASE = "https://chelseakr.github.io/swelter/"


class _MetadataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[dict[str, str]] = []
        self.metas: list[dict[str, str]] = []
        self.json_ld: list[str] = []
        self._json_parts: list[str] | None = None
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key: value or "" for key, value in attrs}
        if tag == "link":
            self.links.append(values)
        elif tag == "meta":
            self.metas.append(values)
        elif tag == "script" and values.get("type") == "application/ld+json":
            self._json_parts = []
        elif tag == "title":
            self._in_title = True

    def handle_data(self, data: str) -> None:
        if self._json_parts is not None:
            self._json_parts.append(data)
        elif self._in_title:
            self.title += data

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._json_parts is not None:
            self.json_ld.append("".join(self._json_parts))
            self._json_parts = None
        elif tag == "title":
            self._in_title = False


def _built_page(tmp_path: Path) -> Path:
    web_dir = tmp_path / "page"
    web_dir.mkdir()
    shutil.copyfile(ROOT / "web" / "index.html", web_dir / "index.html")
    surface = {
        "interval": "hour",
        "buckets": ["2026-07-08T11:00:00Z", "2026-07-08T12:00:00Z"],
        "cells": [
            {"parameter": "pm25_ugm3"},
            {"parameter": "temp_c"},
            {"parameter": "pm25_ugm3"},
        ],
    }
    (web_dir / "sample-surface.json").write_text(json.dumps(surface), encoding="utf-8")
    return web_dir


def _parse(web_dir: Path) -> tuple[_MetadataParser, dict[str, Any]]:
    parser = _MetadataParser()
    parser.feed((web_dir / "index.html").read_text(encoding="utf-8"))
    assert len(parser.json_ld) == 1
    document: dict[str, Any] = json.loads(parser.json_ld[0])
    return parser, document


def _graph_item(document: dict[str, Any], item_type: str) -> dict[str, Any]:
    return next(item for item in document["@graph"] if item["@type"] == item_type)


def test_root_metadata_is_absolute_source_aware_and_valid_json_ld(tmp_path: Path) -> None:
    web_dir = _built_page(tmp_path)
    pages_seo.write_page_metadata(web_dir, route="/", source="openaq")
    parser, document = _parse(web_dir)
    built_html = (web_dir / "index.html").read_text(encoding="utf-8")

    canonical = "https://chelseakr.github.io/swelter/"
    canonical_links = [link for link in parser.links if link.get("rel") == "canonical"]
    assert canonical_links == [{"rel": "canonical", "href": canonical}]
    assert parser.title == pages_seo.SOURCE_SPECS["openaq"].page_title
    # Build-time source truth wins the initial document metadata. Removing the template's runtime
    # i18n attributes prevents the default catalog from overwriting it on first paint.
    assert "<title data-i18n" not in built_html
    assert 'data-i18n-attr="content:meta-description"' not in built_html
    assert {meta.get("content") for meta in parser.metas if meta.get("name") == "description"} == {
        pages_seo.SOURCE_SPECS["openaq"].page_description
    }
    assert {meta.get("content") for meta in parser.metas if meta.get("name") == "robots"} == {
        "index,follow,max-image-preview:large"
    }
    assert {meta.get("content") for meta in parser.metas if meta.get("property") == "og:url"} == {
        canonical
    }
    assert [link["href"] for link in parser.links if link.get("rel") == "icon"] == [
        f"{canonical}icon.svg"
    ]
    assert [link["href"] for link in parser.links if link.get("rel") == "apple-touch-icon"] == [
        f"{canonical}icon-512.png"
    ]
    assert {meta.get("content") for meta in parser.metas if meta.get("property") == "og:image"} == {
        f"{canonical}social-card.png"
    }
    assert {meta.get("content") for meta in parser.metas if meta.get("name") == "twitter:card"} == {
        "summary_large_image"
    }

    assert document["@context"] == "https://schema.org"
    software = _graph_item(document, "SoftwareApplication")
    dataset = _graph_item(document, "Dataset")
    assert software["codeRepository"] == "https://github.com/ChelseaKR/swelter"
    assert software["license"] == "https://www.apache.org/licenses/LICENSE-2.0"
    assert software["author"]["@type"] == "Organization"
    # OpenAQ publishers carry varying terms; the graph must not flatten them into CC0/CC BY.
    assert dataset["license"] == "https://docs.openaq.org/about/terms"
    assert dataset["isBasedOn"]["license"] == dataset["license"]
    assert "vary by provider" in dataset["conditionsOfAccess"]
    assert dataset["dateModified"] == "2026-07-08T12:00:00Z"
    assert dataset["temporalCoverage"] == ("2026-07-08T11:00:00Z/2026-07-08T12:00:00Z")
    assert {item["propertyID"] for item in dataset["variableMeasured"]} == {
        "pm25_ugm3",
        "temp_c",
    }
    assert [item["contentUrl"] for item in dataset["distribution"]] == [
        f"{canonical}sample-surface.json",
        f"{canonical}export.csv",
    ]


def test_sensor_route_replaces_metadata_idempotently(tmp_path: Path) -> None:
    web_dir = _built_page(tmp_path)
    pages_seo.write_page_metadata(web_dir, route="/sensors/", source="openmeteo")
    pages_seo.write_page_metadata(web_dir, route="/sensors/", source="sensor-community")
    once = (web_dir / "index.html").read_text(encoding="utf-8")
    pages_seo.write_page_metadata(web_dir, route="/sensors/", source="sensor-community")
    assert (web_dir / "index.html").read_text(encoding="utf-8") == once

    parser, document = _parse(web_dir)
    canonical = "https://chelseakr.github.io/swelter/sensors/"
    assert [link["href"] for link in parser.links if link.get("rel") == "canonical"] == [canonical]
    dataset = _graph_item(document, "Dataset")
    assert dataset["url"] == canonical
    assert dataset["license"] == "https://opendatacommons.org/licenses/dbcl/1-0/"
    assert dataset["spatialCoverage"]["name"] == "Stuttgart region, Germany"
    assert "Open-Meteo" not in once


def test_generated_metadata_is_literal_not_a_regex_replacement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    web_dir = _built_page(tmp_path)
    original = pages_seo.SOURCE_SPECS["openaq"]
    literal = replace(
        original,
        page_title=r"swelter — source \1",
        page_description=r"Source path C:\data\hourly",
        dataset_description=r"Literal \g<1> metadata and a safe </script> boundary.",
    )
    monkeypatch.setitem(pages_seo.SOURCE_SPECS, "openaq", literal)

    pages_seo.write_page_metadata(web_dir, route="/", source="openaq")
    parser, document = _parse(web_dir)

    assert parser.title == literal.page_title
    assert {meta.get("content") for meta in parser.metas if meta.get("name") == "description"} == {
        literal.page_description
    }
    assert _graph_item(document, "Dataset")["description"] == literal.dataset_description


def test_demo_contract_is_authoritative_when_present(tmp_path: Path) -> None:
    web_dir = _built_page(tmp_path)
    contract = {
        "schema_version": 1,
        "source": {
            "id": "openmeteo",
            "name": {"en": "Contract source name", "es": "Fuente del contrato"},
            "tagline": {"en": "Contract tagline.", "es": "Lema del contrato."},
            "calibration": {"en": "Contract calibration.", "es": "Calibración del contrato."},
            "geography": {"en": "Contract geography.", "es": "Geografía del contrato."},
            "upstream": [
                {"name": "Open-Meteo", "url": "https://open-meteo.com/"},
                {"name": "Copernicus CAMS", "url": "https://atmosphere.copernicus.eu/"},
            ],
            "license": {
                "name": "CC BY 4.0",
                "url": "https://open-meteo.com/en/licence",
                "conditions_of_access": {
                    "en": "Contract reuse conditions.",
                    "es": "Condiciones de reutilización del contrato.",
                },
                "credit_text": {
                    "en": "Contract credit text.",
                    "es": "Atribución del contrato.",
                },
            },
        },
    }
    (web_dir / "demo.json").write_text(json.dumps(contract), encoding="utf-8")

    resolved = pages_seo.write_page_metadata(web_dir, route="/")
    parser, document = _parse(web_dir)
    dataset = _graph_item(document, "Dataset")
    assert resolved == "openmeteo"
    assert parser.title == "swelter — Contract source name"
    assert dataset["license"] == "https://open-meteo.com/en/licence"
    assert dataset["conditionsOfAccess"] == "Contract reuse conditions."
    assert dataset["creditText"] == "Contract credit text."
    assert [item["name"] for item in dataset["isBasedOn"]] == [
        "Open-Meteo",
        "Copernicus CAMS",
    ]

    with pytest.raises(ValueError, match="conflicts with demo contract"):
        pages_seo.resolve_source(web_dir, "openaq")


def test_pre_contract_artifact_uses_unambiguous_surface_attribution(tmp_path: Path) -> None:
    web_dir = _built_page(tmp_path)
    surface_path = web_dir / "sample-surface.json"
    surface = json.loads(surface_path.read_text(encoding="utf-8"))
    surface["attribution"] = "Copernicus CAMS air quality via Open-Meteo."
    surface_path.write_text(json.dumps(surface), encoding="utf-8")

    resolved = pages_seo.write_page_metadata(web_dir, route="/")
    assert resolved == "openmeteo"
    _, document = _parse(web_dir)
    assert _graph_item(document, "Dataset")["license"] == "https://open-meteo.com/en/licence"


@pytest.mark.parametrize(
    ("source", "license_url"),
    [
        ("openaq", "https://docs.openaq.org/about/terms"),
        ("openmeteo", "https://open-meteo.com/en/licence"),
        ("sensor-community", "https://opendatacommons.org/licenses/dbcl/1-0/"),
        ("synthetic", "https://creativecommons.org/publicdomain/zero/1.0/"),
    ],
)
def test_every_fallback_has_an_absolute_source_license(source: str, license_url: str) -> None:
    spec = pages_seo.SOURCE_SPECS[source]
    assert spec.license_url == license_url
    for url in (spec.license_url, *(item.url for item in spec.upstream)):
        parts = urlsplit(url)
        assert parts.scheme == "https"
        assert parts.netloc


def test_synthetic_metadata_does_not_claim_real_geography(tmp_path: Path) -> None:
    web_dir = _built_page(tmp_path)
    pages_seo.write_page_metadata(web_dir, route="/", source="synthetic")
    _, document = _parse(web_dir)
    dataset = _graph_item(document, "Dataset")
    assert "synthetic" in dataset["name"].lower()
    assert "real-world conditions" in dataset["description"]
    assert "spatialCoverage" not in dataset


def test_sitemap_lists_only_stable_absolute_routes(tmp_path: Path) -> None:
    sitemap = tmp_path / "sitemap.xml"
    pages_seo.write_sitemap(sitemap)
    # This is trusted XML generated in-process by the function under test.
    root = ET.parse(sitemap).getroot()  # noqa: S314 (#107)
    namespace = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    listed = [element.text for element in root.findall("s:url/s:loc", namespace)]
    assert listed == [
        "https://chelseakr.github.io/swelter/",
        "https://chelseakr.github.io/swelter/sensors/",
        # The planner was live and crawlable with no sitemap entry, which did not keep it
        # private, only undiscovered. It is a stable page, not application state.
        "https://chelseakr.github.io/swelter/planner/",
    ]
    # And the list is DERIVED from the published routes rather than maintained beside them.
    # The planner was added to the pa11y URL list and to nothing else, so it shipped with no
    # canonical, no card and no sitemap entry; a sitemap kept as a second hand-written list
    # is how that happens a second time.
    assert set(listed) == {
        pages_seo.canonical_url(pages_seo.DEFAULT_BASE_URL, route)
        for route in pages_seo.PUBLISHED_ROUTES
    }


def _planner_template(tmp_path: Path) -> Path:
    web_dir = tmp_path / "planner"
    web_dir.mkdir()
    shutil.copy(ROOT / "web" / "planner" / "index.html", web_dir / "index.html")
    return web_dir


def test_the_planner_gets_a_canonical_and_a_card_but_no_dataset(tmp_path: Path) -> None:
    """A published page that is not a data surface still has to say which page it is.

    ``/planner/`` shipped live with no canonical, no Open Graph and no Twitter tags: every
    one of those was reached only through the source-aware path, which needs a data source
    the planner does not have. Sharing a link to it previewed as a bare URL.

    It must not carry the Dataset graph. The only structured data this project emits
    describes readings and their license, and the planner publishes no readings; claiming
    otherwise would be a claim the page cannot support.
    """
    web_dir = _planner_template(tmp_path)
    pages_seo.write_static_page_metadata(web_dir, route="/planner/")
    html = (web_dir / "index.html").read_text(encoding="utf-8")

    canonical = "https://chelseakr.github.io/swelter/planner/"
    assert f'<link rel="canonical" href="{canonical}" />' in html
    assert f'<meta property="og:url" content="{canonical}" />' in html
    for tag in ("og:type", "og:title", "og:description", "og:image", "og:site_name"):
        assert f'property="{tag}"' in html, tag
    for tag in ("twitter:card", "twitter:title", "twitter:description", "twitter:image"):
        assert f'name="{tag}"' in html, tag

    # No Dataset, and no JSON-LD at all: the planner has no readings to describe.
    assert "application/ld+json" not in html
    assert "Dataset" not in html

    # This is one of six project sites sharing an origin on paths, so the canonical must
    # name this project, never the bare origin all six would otherwise claim.
    assert canonical.rstrip("/") != "https://chelseakr.github.io"
    assert "/swelter/planner/" in canonical


def test_the_planner_card_repeats_the_page_rather_than_inventing_copy(
    tmp_path: Path,
) -> None:
    """The card is built from the page's own title and description, not from new prose.

    Those two strings were written and reviewed for the page. A card that restates them
    cannot describe the planner as something it is not, and in particular cannot drift into
    describing a heat and air-quality page as offering health guidance or a safety
    threshold, which this project does not do (``docs/governance.md`` non-goals).
    """
    web_dir = _planner_template(tmp_path)
    source = (web_dir / "index.html").read_text(encoding="utf-8")
    title = re.sub(r"<[^>]+>", "", pages_seo._TITLE_PATTERN.findall(source)[0]).strip()
    described = re.search(r'content="([^"]*)"', pages_seo._DESCRIPTION_PATTERN.findall(source)[0])
    assert described is not None
    description = " ".join(described.group(1).split())

    pages_seo.write_static_page_metadata(web_dir, route="/planner/")
    html = (web_dir / "index.html").read_text(encoding="utf-8")

    assert f'<meta property="og:title" content="{escape(title, quote=True)}" />' in html
    assert f'<meta property="og:description" content="{escape(description, quote=True)}" />' in html
    # The page keeps the title and description it shipped with; nothing was rewritten.
    assert f"<title>{escape(title)}</title>" in html


def test_a_static_page_without_a_marker_or_a_description_is_refused(
    tmp_path: Path,
) -> None:
    """Refuse rather than invent. A page missing either is a build error, not a default."""
    web_dir = tmp_path / "planner"
    web_dir.mkdir()

    (web_dir / "index.html").write_text(
        "<html><head><title>T</title>"
        '<meta name="description" content="D" /></head><body></body></html>',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="exactly one"):
        pages_seo.write_static_page_metadata(web_dir, route="/planner/")

    (web_dir / "index.html").write_text(
        f"<html><head>{pages_seo.SEO_START}{pages_seo.SEO_END}</head><body></body></html>",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="exactly one title and meta description"):
        pages_seo.write_static_page_metadata(web_dir, route="/planner/")


def test_a_data_route_is_not_accepted_as_a_static_page(tmp_path: Path) -> None:
    """The dashboard must keep going through the source-aware path, graph and all."""
    web_dir = _planner_template(tmp_path)
    with pytest.raises(ValueError, match="not a static public route"):
        pages_seo.write_static_page_metadata(web_dir, route="/")


def test_raster_icon_has_the_declared_dimensions() -> None:
    image = (ROOT / "web" / "icon-512.png").read_bytes()
    assert image[:8] == b"\x89PNG\r\n\x1a\n"
    assert struct.unpack(">II", image[16:24]) == (512, 512)


def test_social_card_has_the_declared_dimensions() -> None:
    image = (ROOT / "web" / "social-card.png").read_bytes()
    assert image[:8] == b"\x89PNG\r\n\x1a\n"
    assert struct.unpack(">II", image[16:24]) == (1280, 640)
    assert len(image) < 1_000_000


def test_unknown_route_and_non_https_base_are_rejected() -> None:
    with pytest.raises(ValueError, match="unknown public route"):
        pages_seo.canonical_url(pages_seo.DEFAULT_BASE_URL, "/invented/")
    with pytest.raises(ValueError, match="absolute HTTPS"):
        pages_seo.normalize_base_url("http://example.test/swelter/")


def test_missing_contract_and_attribution_fail_closed(tmp_path: Path) -> None:
    web_dir = _built_page(tmp_path)
    with pytest.raises(ValueError, match="cannot identify exactly one Pages source"):
        pages_seo.resolve_source(web_dir)


def test_gate_rejects_project_path_robots_file(tmp_path: Path) -> None:
    web_dir = _built_page(tmp_path)
    assert pages_seo.check_template(web_dir / "index.html") == []
    (web_dir / "robots.txt").write_text("User-agent: *\nAllow: /\n", encoding="utf-8")
    errors = pages_seo.check_template(web_dir / "index.html")
    assert len(errors) == 1
    assert "cannot control this GitHub Pages project site" in errors[0]


# --------------------------------------------------------------------------------------------
# The internal link graph.
#
# Two discoverability defects reached the live site because nothing checked either of them.
# `/sensors/` served the root page's own `href="sensors/"`, which resolves to
# `/sensors/sensors/` and returns 404; and `/planner/` was in `sitemap.xml`, fully marked up,
# with no page on the site linking to it. Both are invisible to every metadata check above,
# because both pages' metadata was correct.
# --------------------------------------------------------------------------------------------

_ANCHOR_IDS = re.compile(r'<a\b[^>]*\bid="([^"]+)"[^>]*\bhref="([^"]*)"')


def _publish_into(directory: Path) -> None:
    """Write what ``swelter publish`` bakes into one route directory, from its own list."""

    surface = {
        "interval": "hour",
        "buckets": ["2026-07-08T11:00:00Z", "2026-07-08T12:00:00Z"],
        "cells": [{"parameter": "pm25_ugm3"}, {"parameter": "temp_c"}],
        "attribution": "Synthetic demonstration data — no real sensors.",
    }
    contract = {
        "schema_version": 1,
        "source": {
            "id": "synthetic",
            "name": {"en": "Synthetic demonstration"},
            "tagline": {"en": "A clearly labeled synthetic demonstration."},
            "calibration": {"en": "No calibration; the values are generated."},
            "geography": {"en": "No real geography."},
            "upstream": [{"name": "Swelter demo generator", "url": "https://example.invalid/"}],
            "license": {
                "url": "https://creativecommons.org/publicdomain/zero/1.0/",
                "conditions_of_access": {"en": "Public domain."},
                "credit_text": {"en": "Swelter contributors; synthetic data."},
            },
        },
    }
    written = {
        "sample-surface.json": json.dumps(surface),
        "demo.json": json.dumps(contract),
    }
    for name in PUBLISH_FILES:
        (directory / name).write_text(written.get(name, "placeholder\n"), encoding="utf-8")
    # Its presence is how `rendered_paths` knows this directory was really published, and that
    # only what is on disk counts for it.
    (directory / "publish-manifest.json").write_text(
        json.dumps({"files": [{"path": name} for name in PUBLISH_FILES]}), encoding="utf-8"
    )


def _deployed_site(tmp_path: Path) -> Path:
    """Build the artifact ``.github/workflows/pages.yml`` uploads, from the committed sources.

    Page 2 has no committed directory: the deploy copies the root page's own top-level files
    into ``web/sensors/`` and publishes that route's data into it. That copy is the whole reason
    a link written relative to the site root breaks, so a check that never renders it would be
    checking a layout this project does not publish.
    """

    web = tmp_path / "web"
    shutil.copytree(
        ROOT / "web",
        web,
        ignore=shutil.ignore_patterns(*sorted(pages_seo.IGNORED_WEB_DIRECTORIES)),
    )
    sensors = web / "sensors"
    sensors.mkdir()
    for entry in sorted(web.iterdir()):
        if entry.is_file():
            shutil.copyfile(entry, sensors / entry.name)
    shutil.copytree(web / "i18n", sensors / "i18n")
    _publish_into(web)
    _publish_into(sensors)
    pages_seo.write_page_metadata(web, route="/")
    pages_seo.write_page_metadata(sensors, route="/sensors/")
    pages_seo.write_static_page_metadata(web / "planner", route="/planner/")
    pages_seo.write_sitemap(web / "sitemap.xml")
    return web


def _anchor_hrefs(page: Path) -> dict[str, str]:
    html = page.read_text(encoding="utf-8")
    return {
        anchor_id: href
        for anchor_id, href in _ANCHOR_IDS.findall(html)
        if anchor_id in pages_seo.ROUTE_LINKS
    }


def _urls(html: str) -> list[str]:
    parser = pages_seo._LinkParser()
    parser.feed(html)
    return parser.urls


def test_every_internal_link_in_the_published_artifact_resolves(tmp_path: Path) -> None:
    """Every href on every rendered page must reach a file the deploy actually serves."""

    web = _deployed_site(tmp_path)
    documents = pages_seo.route_documents(web)
    paths = pages_seo.rendered_paths(web)
    internal = [
        target
        for route, html in documents.items()
        for href in _urls(html)
        if (target := pages_seo.resolve_internal_link(route, href, base_url=BASE)) is not None
    ]

    # A gate whose input silently became empty passes forever, so none of these three numbers
    # is taken on trust just because the code that produced it ran.
    assert len(documents) > 1, "the page sweep collapsed; it would prove nothing"
    assert len(paths) > len(documents), "the file sweep collapsed; it would prove nothing"
    assert len(internal) > 1, "the link sweep collapsed; it would prove nothing"
    assert set(documents) == set(pages_seo.PUBLISHED_ROUTES)

    assert pages_seo.crawl_problems(web) == []


def test_each_route_gets_the_cross_route_hrefs_for_its_own_depth(tmp_path: Path) -> None:
    """Both routes serve the same shell one directory apart, so the hrefs cannot be the same."""

    web = _deployed_site(tmp_path)
    assert _anchor_hrefs(web / "index.html") == {
        "switch-cams": "./",
        "switch-sensors": "sensors/",
        "footer-planner-link": "planner/",
    }
    assert _anchor_hrefs(web / "sensors" / "index.html") == {
        "switch-cams": "../",
        "switch-sensors": "./",
        "footer-planner-link": "../planner/",
    }


def test_a_root_relative_cross_route_href_on_the_copy_fails_the_crawl(tmp_path: Path) -> None:
    """The defect exactly as it shipped: /sensors/ carried the root page's own href."""

    web = _deployed_site(tmp_path)
    assert pages_seo.crawl_problems(web) == []

    copy = web / "sensors" / "index.html"
    before = copy.read_bytes()
    copy.write_text(
        copy.read_text(encoding="utf-8").replace(
            '<a id="switch-sensors" href="./"', '<a id="switch-sensors" href="sensors/"'
        ),
        encoding="utf-8",
    )
    # A sabotage that silently no-ops reads exactly like a pass, so prove it landed first.
    assert copy.read_bytes() != before
    assert '<a id="switch-sensors" href="sensors/"' in copy.read_text(encoding="utf-8")

    problems = pages_seo.crawl_problems(web)
    assert any("sensors/sensors/index.html" in problem for problem in problems), problems

    copy.write_bytes(before)
    assert pages_seo.crawl_problems(web) == []


def test_a_page_only_the_sitemap_links_to_fails_the_crawl(tmp_path: Path) -> None:
    """The planner's inbound links are its only ones; dropping them must turn this red."""

    web = _deployed_site(tmp_path)
    assert pages_seo.crawl_problems(web) == []

    pages = (web / "index.html", web / "sensors" / "index.html")
    originals = {page: page.read_bytes() for page in pages}
    for page in pages:
        html = page.read_text(encoding="utf-8")
        stripped = re.sub(r'<a id="footer-planner-link".*?</a>', "", html, flags=re.DOTALL)
        assert stripped != html, f"the sabotage did not apply to {page}"
        page.write_text(stripped, encoding="utf-8")
    for page in pages:
        assert 'id="footer-planner-link"' not in page.read_text(encoding="utf-8")

    problems = pages_seo.crawl_problems(web)
    assert any("/planner/" in problem and "sitemap" in problem for problem in problems), problems

    for page, data in originals.items():
        page.write_bytes(data)
    assert pages_seo.crawl_problems(web) == []


def test_a_rendered_page_no_route_list_knows_about_is_reported(tmp_path: Path) -> None:
    """How /planner/ shipped with no canonical, no card and no sitemap entry: nobody listed it."""

    web = _deployed_site(tmp_path)
    extra = web / "guide"
    extra.mkdir()
    (extra / "index.html").write_text(
        '<html lang="en"><body><a href="../">Home</a></body></html>', encoding="utf-8"
    )
    problems = pages_seo.crawl_problems(web)
    assert any("/guide/" in problem and "sitemap entry" in problem for problem in problems), (
        problems
    )


def test_the_crawl_refuses_a_sweep_whose_input_collapsed() -> None:
    """Neither an empty page set nor an empty file set is evidence of anything."""

    assert pages_seo._sweep_problems({}, set()) != []
    assert any(
        "page sweep collapsed" in problem
        for problem in pages_seo._sweep_problems({"/": "<html></html>"}, {"index.html"})
    )
    assert any(
        "file sweep collapsed" in problem
        for problem in pages_seo._sweep_problems(
            dict.fromkeys(pages_seo.PUBLISHED_ROUTES, "<html></html>"), {"index.html"}
        )
    )


def test_the_sitemap_check_refuses_an_empty_url_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Inbound-link coverage over zero URLs is not inbound-link coverage."""

    monkeypatch.setattr(pages_seo, "PUBLISHED_ROUTES", ())
    problems = pages_seo._sitemap_problems(tmp_path, {}, base_url=BASE)
    assert any("found no URLs" in problem for problem in problems), problems


def test_a_sitemap_that_drifts_from_the_published_routes_is_reported(tmp_path: Path) -> None:
    """The deployed file is compared against what the routes generate, not read as the truth."""

    web = _deployed_site(tmp_path)
    sitemap = web / "sitemap.xml"
    before = sitemap.read_bytes()
    sitemap.write_text(
        sitemap.read_text(encoding="utf-8").replace(f"{BASE}planner/", f"{BASE}invented/"),
        encoding="utf-8",
    )
    assert sitemap.read_bytes() != before
    problems = pages_seo.crawl_problems(web)
    assert any("regenerate it" in problem for problem in problems), problems

    sitemap.write_bytes(before)
    assert pages_seo.crawl_problems(web) == []


@pytest.mark.parametrize(
    ("from_route", "to_route", "href"),
    [
        ("/", "/", "./"),
        ("/", "/sensors/", "sensors/"),
        ("/", "/planner/", "planner/"),
        ("/sensors/", "/", "../"),
        ("/sensors/", "/sensors/", "./"),
        ("/sensors/", "/planner/", "../planner/"),
        ("/planner/", "/sensors/", "../sensors/"),
    ],
)
def test_cross_route_hrefs_are_derived_from_route_depth(
    from_route: str, to_route: str, href: str
) -> None:
    assert pages_seo.relative_route_href(from_route, to_route) == href


def test_the_committed_shell_is_already_correct_as_served_at_the_site_root() -> None:
    """The template's own hrefs are the root's. Only the copies need rewriting."""

    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    assert pages_seo.rewrite_route_links(html, "/") == html
    assert pages_seo.rewrite_route_links(html, "/sensors/") != html


def test_rewrite_route_links_refuses_a_template_that_lost_an_anchor() -> None:
    """A rewrite that quietly no-ops looks like a correct page until someone clicks the link."""

    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    renamed = html.replace('id="footer-planner-link"', 'id="footer-planner-gone"')
    assert renamed != html
    with pytest.raises(ValueError, match="exactly one"):
        pages_seo.rewrite_route_links(renamed, "/sensors/")

    hrefless = html.replace('<a id="switch-sensors" href="sensors/"', '<a id="switch-sensors"')
    assert hrefless != html
    with pytest.raises(ValueError, match="no href to rewrite"):
        pages_seo.rewrite_route_links(hrefless, "/sensors/")


@pytest.mark.parametrize(
    ("route", "href", "target"),
    [
        ("/", "#explore", None),
        ("/", "https://ko-fi.com/T6T6GMYTU", None),
        ("/", "sensors/", "sensors/index.html"),
        ("/sensors/", "sensors/", "sensors/sensors/index.html"),
        ("/sensors/", "../", "index.html"),
        ("/sensors/", "../planner/", "planner/index.html"),
        ("/sensors/", "export.csv", "sensors/export.csv"),
        ("/planner/", f"{BASE}icon.svg", "icon.svg"),
        # A project site is one path on a shared origin: neither of these reaches it.
        ("/", "/planner/", pages_seo.UNRESOLVABLE),
        ("/", "https://chelseakr.github.io/afterward/", pages_seo.UNRESOLVABLE),
        ("/sensors/", "../../", pages_seo.UNRESOLVABLE),
    ],
)
def test_internal_links_resolve_against_the_route_that_serves_them(
    route: str, href: str, target: str | None
) -> None:
    assert pages_seo.resolve_internal_link(route, href, base_url=BASE) == target
