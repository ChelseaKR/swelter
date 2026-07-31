"""Technical-SEO build output stays route-, source-, and license-correct."""

from __future__ import annotations

import importlib
import json
import shutil
import struct
import sys
import xml.etree.ElementTree as ET
from dataclasses import replace
from html.parser import HTMLParser
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

import pytest

ROOT = Path(__file__).resolve().parent.parent
if TYPE_CHECKING:
    from scripts import pages_seo
else:
    # Pytest's importlib mode intentionally omits the repository root from sys.path. The build
    # script is not an installed runtime module, so load it from the checkout just as CI does.
    sys.path.insert(0, str(ROOT))
    pages_seo = importlib.import_module("scripts.pages_seo")


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
    assert [element.text for element in root.findall("s:url/s:loc", namespace)] == [
        "https://chelseakr.github.io/swelter/",
        "https://chelseakr.github.io/swelter/sensors/",
    ]


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
