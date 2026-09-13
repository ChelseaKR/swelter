#!/usr/bin/env python3
"""Build source-aware search metadata for the GitHub Pages demo.

The dashboard template is also used by self-hosted Swelter instances, so it must not carry a
canonical URL for the GitHub project site in source control.  The Pages workflow calls this script
after it knows which data-source fallback succeeded.  That is the point where an absolute canonical
URL, social metadata, and a license-correct Dataset description can be generated truthfully.
"""

from __future__ import annotations

import argparse
import io
import json
import posixpath
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from html import escape
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

DEFAULT_BASE_URL = "https://chelseakr.github.io/swelter/"
REPOSITORY_URL = "https://github.com/ChelseaKR/swelter"
SEO_START = "<!-- pages-seo:start -->"
SEO_END = "<!-- pages-seo:end -->"
KNOWN_ROUTES = ("/", "/sensors/")
# Routes that are published and stable but are not data surfaces. The planner answers a
# project question and reads no readings, so it has no source, no `sample-surface.json` and
# no Dataset to describe. It was live and crawlable with no canonical, no social metadata and
# no sitemap entry, because every one of those was reached only through the source-aware path
# above. Giving it the Dataset graph would be worse than leaving it out: it would describe
# observations that page does not publish.
STATIC_ROUTES = ("/planner/",)
PUBLISHED_ROUTES = KNOWN_ROUTES + STATIC_ROUTES

#: Routes the deploy builds by copying the root page instead of from a committed directory, with
#: the subdirectories it copies alongside the top-level files. `.github/workflows/pages.yml`
#: ("Page 2") runs `find web -maxdepth 1 -type f -exec cp {} web/sensors/`, then `cp -r web/i18n`
#: and `cp -r web/vendor`, then publishes that route's own data files into it. Every one of those
#: routes therefore serves the *same document one directory deeper*, which is why an href written
#: relative to the site root is correct on `/` and a 404 on the copy. Before a deploy there is no
#: built directory to read, so this states what the deploy will put there; once one exists, the
#: built directory is read instead and this is not consulted.
SYNTHESIZED_ROUTES: dict[str, tuple[str, ...]] = {"/sensors/": ("i18n", "vendor")}

#: Anchors in the dashboard shell that point at another published route, and the route each
#: reaches. `web/app.js` (`wireSourceSwitch`) recomputes the first two at runtime; a crawler, a
#: reader with JavaScript off, and every reader before boot get the static markup, so the build
#: has to write the right href for the route the copy is served from.
ROUTE_LINKS: dict[str, str] = {
    "switch-cams": "/",
    "switch-sensors": "/sensors/",
    "footer-planner-link": "/planner/",
}

#: Build outputs and installed trees that are not part of the published artifact.
IGNORED_WEB_DIRECTORIES = frozenset({".lighthouseci", "node_modules", "test-results"})

#: Element attributes that carry a URL the reader's browser will actually request.
_URL_ATTRIBUTES: dict[str, str] = {
    "a": "href",
    "iframe": "src",
    "img": "src",
    "link": "href",
    "script": "src",
    "source": "src",
}

#: Resolution result for an href that names something outside this project site's own path —
#: a root-absolute path on a shared origin, or a `../` chain that walks above the site root.
#: It is a different failure from "the file is not there", and is reported as one.
UNRESOLVABLE = "«outside this project site»"

_TITLE_PATTERN = re.compile(r"<title(?:\s[^>]*)?>.*?</title>", re.DOTALL)
_DESCRIPTION_PATTERN = re.compile(
    r'<meta\s+name="description"[^>]*\scontent="[^"]*"[^>]*/?>', re.DOTALL
)


@dataclass(frozen=True)
class UpstreamSpec:
    """One upstream dataset or service represented in the deployed surface."""

    name: str
    url: str


@dataclass(frozen=True)
class SourceSpec:
    """Public metadata for one possible Pages data source."""

    page_title: str
    page_description: str
    dataset_name: str
    dataset_description: str
    upstream: tuple[UpstreamSpec, ...]
    license_url: str
    conditions_of_access: str
    credit_text: str
    spatial_name: str | None


# License URLs deliberately describe the upstream observations, not Swelter's Apache-2.0 code.
# OpenAQ is the nuanced case: it aggregates publishers with different terms, so claiming one
# Creative Commons license would be false.  Its own terms are the rights/usage document and require
# users to honor the original provider terms exposed by OpenAQ.
SOURCE_SPECS: dict[str, SourceSpec] = {
    "openaq": SourceSpec(
        page_title="swelter — California-region air-quality observations from OpenAQ",
        page_description=(
            "Physical-sensor air-quality observations selected from OpenAQ for Swelter's "
            "California-region demo. Readings are uncalibrated by Swelter, timestamped, and shown "
            "provisional."
        ),
        dataset_name="Swelter California-region air-quality surface (OpenAQ-derived)",
        dataset_description=(
            "An hourly Swelter surface derived from physical-sensor observations accessed through "
            "OpenAQ. Swelter does not calibrate these source readings, so they remain provisional."
        ),
        upstream=(UpstreamSpec("OpenAQ air-quality data", "https://openaq.org/"),),
        license_url="https://docs.openaq.org/about/terms",
        conditions_of_access=(
            "Use requires attribution to OpenAQ and compliance with the terms of each original "
            "data provider; licenses can vary by provider."
        ),
        credit_text="OpenAQ and the original data providers identified by OpenAQ.",
        spatial_name="California region, United States",
    ),
    "openmeteo": SourceSpec(
        page_title="swelter — California air quality from Copernicus CAMS",
        page_description=(
            "Hourly California air-quality model data from Copernicus CAMS via Open-Meteo, shown "
            "with weather context. These are model values, not neighborhood sensor readings."
        ),
        dataset_name="Swelter California air-quality surface (CAMS via Open-Meteo)",
        dataset_description=(
            "An hourly Swelter surface for California places derived from Copernicus Atmosphere "
            "Monitoring Service model data delivered by Open-Meteo. It is not a physical-sensor "
            "map."
        ),
        upstream=(
            UpstreamSpec("Open-Meteo", "https://open-meteo.com/"),
            UpstreamSpec("Copernicus CAMS", "https://atmosphere.copernicus.eu/"),
        ),
        license_url="https://open-meteo.com/en/licence",
        conditions_of_access=(
            "CC BY 4.0 attribution is required to Open-Meteo and the Copernicus Atmosphere "
            "Monitoring Service."
        ),
        credit_text="Open-Meteo and Copernicus Atmosphere Monitoring Service (CAMS).",
        spatial_name="California, United States",
    ),
    "sensor-community": SourceSpec(
        page_title="swelter — Stuttgart community air-quality sensors",
        page_description=(
            "Timestamped low-cost air-sensor observations from Sensor.Community near Stuttgart. "
            "Swelter has not calibrated these readings, so they are shown provisional."
        ),
        dataset_name="Swelter Stuttgart air-quality surface (Sensor.Community-derived)",
        dataset_description=(
            "An hourly Swelter surface derived from current community low-cost sensor observations "
            "near Stuttgart. Swelter does not calibrate these source readings."
        ),
        upstream=(
            UpstreamSpec(
                "Sensor.Community environmental observations", "https://sensor.community/"
            ),
        ),
        license_url="https://opendatacommons.org/licenses/dbcl/1-0/",
        conditions_of_access=(
            "Sensor.Community licenses database contents under the Database Contents License 1.0, "
            "whose conditions require compliance with the Open Database License."
        ),
        credit_text="Sensor.Community contributors.",
        spatial_name="Stuttgart region, Germany",
    ),
    "synthetic": SourceSpec(
        page_title="swelter — synthetic heat and air-quality demonstration",
        page_description=(
            "A clearly labeled synthetic Swelter demonstration used only when live data sources "
            "are unavailable. It contains no real sensor observations."
        ),
        dataset_name="Swelter synthetic demonstration surface",
        dataset_description=(
            "Generated demonstration observations for exercising Swelter's heat and air-quality "
            "interface. The values are synthetic and do not describe real-world conditions."
        ),
        upstream=(
            UpstreamSpec(
                "Swelter synthetic demonstration generator",
                f"{REPOSITORY_URL}/blob/main/scripts/gen_demo_data.py",
            ),
        ),
        license_url="https://creativecommons.org/publicdomain/zero/1.0/",
        conditions_of_access="Synthetic demonstration data are dedicated to the public domain.",
        credit_text="Swelter contributors; synthetic demonstration data, not real observations.",
        spatial_name=None,
    ),
}

_PARAMETERS: dict[str, tuple[str, str | None]] = {
    "exposure": ("Heat and air exposure level", None),
    "heat_index_c": ("Heat index", "°C"),
    "humidity_pct": ("Relative humidity", "%"),
    "no2_ppb": ("Nitrogen dioxide", "ppb"),
    "pm10_ugm3": ("PM10", "µg/m³"),
    "pm25_ugm3": ("PM2.5", "µg/m³"),
    "temp_c": ("Temperature", "°C"),
}


def normalize_base_url(value: str) -> str:
    """Return one canonical HTTPS project-site base URL with a trailing slash."""

    parts = urlsplit(value)
    if parts.scheme != "https" or not parts.netloc or parts.query or parts.fragment:
        raise ValueError("base URL must be an absolute HTTPS URL without query or fragment")
    path = f"{parts.path.rstrip('/')}/"
    return urlunsplit((parts.scheme, parts.netloc, path, "", ""))


def canonical_url(base_url: str, route: str) -> str:
    """Join a known route without letting a leading slash discard the Pages project path."""

    if route not in PUBLISHED_ROUTES:
        raise ValueError(f"unknown public route: {route}")
    base = normalize_base_url(base_url)
    return base if route == "/" else f"{base}{route.strip('/')}/"


def relative_route_href(from_route: str, to_route: str) -> str:
    """Return the href that reaches ``to_route`` from a document served at ``from_route``.

    Base-path-agnostic, like the runtime equivalent in ``web/app.js``: the deployed site lives
    under ``/swelter/`` on a shared origin, and a self-hosted instance does not, so neither the
    markup nor this may name an absolute path. Depth is the whole problem — ``sensors/`` is the
    right href from ``/`` and resolves to ``/sensors/sensors/`` from ``/sensors/``.
    """
    for value in (from_route, to_route):
        if value not in PUBLISHED_ROUTES:
            raise ValueError(f"unknown public route: {value}")
    if from_route == to_route:
        return "./"
    up = "../" * len([segment for segment in from_route.split("/") if segment])
    tail = to_route.strip("/")
    return f"{up}{tail}/" if tail else up


def _replace_href(tag: str, href: str) -> str:
    """Swap one tag's href for a literal value.

    A callable replacement keeps the href literal; passing it as a template would read a
    backslash sequence in it as a group reference.
    """

    return re.sub(r'href="[^"]*"', lambda _match: f'href="{href}"', tag, count=1)


def rewrite_route_links(html: str, route: str) -> str:
    """Point every cross-route anchor in one built page at the route it actually reaches.

    Fails closed. An anchor this cannot find, or one with no href to replace, is a template
    change that silently turns the rewrite into a no-op, and a rewrite that no-ops looks exactly
    like a correct page until someone clicks the link.
    """
    for anchor_id, target in ROUTE_LINKS.items():
        pattern = re.compile(rf'<a\b[^>]*\bid="{re.escape(anchor_id)}"[^>]*?>')
        tags = pattern.findall(html)
        if len(tags) != 1:
            raise ValueError(
                f'template must carry exactly one <a id="{anchor_id}">, found {len(tags)}'
            )
        if 'href="' not in tags[0]:
            raise ValueError(f'<a id="{anchor_id}"> carries no href to rewrite')
        rewritten = _replace_href(tags[0], relative_route_href(route, target))
        html = html.replace(tags[0], rewritten, 1)
    return html


def resolve_source(web_dir: Path, explicit_source: str | None = None) -> str:
    """Resolve the deployed source from its contract, with an origin/main compatibility fallback.

    The build-generated ``demo.json`` is authoritative when present. Older artifacts predate that
    contract, so this branch can still deploy independently by reading the explicit attribution
    written into ``sample-surface.json``. Ambiguous or conflicting metadata fails the build instead
    of publishing a confident but false Dataset claim.
    """

    contract_path = web_dir / "demo.json"
    if contract_path.is_file():
        try:
            contract = json.loads(contract_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"cannot read demo contract {contract_path}: {exc}") from exc
        if not isinstance(contract, dict):
            raise ValueError(f"invalid or unsupported demo contract: {contract_path}")
        source_doc = contract.get("source")
        contract_source = source_doc.get("id") if isinstance(source_doc, dict) else None
        if contract.get("schema_version") != 1 or contract_source not in SOURCE_SPECS:
            raise ValueError(f"invalid or unsupported demo contract: {contract_path}")
        if explicit_source is not None and explicit_source != contract_source:
            raise ValueError(
                f"explicit source {explicit_source!r} conflicts with demo contract "
                f"source {contract_source!r}"
            )
        return str(contract_source)

    if explicit_source is not None:
        if explicit_source not in SOURCE_SPECS:
            raise ValueError(f"unknown Pages data source: {explicit_source}")
        return explicit_source

    surface_path = web_dir / "sample-surface.json"
    try:
        surface = json.loads(surface_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot identify source from {surface_path}: {exc}") from exc
    attribution = (
        str(surface.get("attribution") or "").casefold() if isinstance(surface, dict) else ""
    )
    markers = {
        "openaq": ("openaq",),
        "openmeteo": ("copernicus", "open-meteo"),
        "sensor-community": ("sensor.community",),
        "synthetic": ("synthetic demonstration",),
    }
    matches = [
        source
        for source, tokens in markers.items()
        if any(token in attribution for token in tokens)
    ]
    if len(matches) != 1:
        raise ValueError(
            f"cannot identify exactly one Pages source from {surface_path} attribution: "
            f"{surface.get('attribution') if isinstance(surface, dict) else None!r}"
        )
    return matches[0]


def _english(value: Any, field: str) -> str:
    """Read a required English contract value."""

    text = value.get("en") if isinstance(value, dict) else value
    if not isinstance(text, str) or not text.strip():
        raise ValueError(f"demo contract field {field} must carry non-empty English text")
    return text.strip()


def _required_https(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"demo contract field {field} must be a URL")
    parts = urlsplit(value)
    if parts.scheme != "https" or not parts.netloc:
        raise ValueError(f"demo contract field {field} must be absolute HTTPS")
    return value


def _contract_upstream(value: Any) -> tuple[UpstreamSpec, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError("demo contract must identify at least one upstream source")
    upstream: list[UpstreamSpec] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise ValueError(f"demo contract upstream[{index}] must be an object")
        name = item.get("name")
        if not isinstance(name, str) or not name:
            raise ValueError(f"demo contract upstream[{index}] must carry a name")
        upstream.append(
            UpstreamSpec(name, _required_https(item.get("url"), f"source.upstream[{index}].url"))
        )
    return tuple(upstream)


def _contract_source_spec(web_dir: Path, source: str) -> SourceSpec:
    """Overlay SEO fields from the source-truth contract when that artifact is present."""

    contract_path = web_dir / "demo.json"
    if not contract_path.is_file():
        return SOURCE_SPECS[source]
    try:
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read demo contract {contract_path}: {exc}") from exc
    source_doc = contract.get("source") if isinstance(contract, dict) else None
    if not isinstance(source_doc, dict) or source_doc.get("id") != source:
        raise ValueError(f"demo contract source changed while generating metadata: {contract_path}")

    upstream = _contract_upstream(source_doc.get("upstream"))

    license_doc = source_doc.get("license")
    if not isinstance(license_doc, dict):
        raise ValueError(f"demo contract must carry source license metadata: {contract_path}")
    license_url = _required_https(license_doc.get("url"), "source.license.url")

    name = _english(source_doc.get("name"), "source.name")
    tagline = _english(source_doc.get("tagline"), "source.tagline")
    calibration = _english(source_doc.get("calibration"), "source.calibration")
    geography = _english(source_doc.get("geography"), "source.geography")
    return SourceSpec(
        page_title=f"swelter — {name}",
        page_description=f"{tagline} {calibration}",
        dataset_name=f"Swelter deployed surface — {name}",
        dataset_description=f"{tagline} {calibration} Geography: {geography}",
        upstream=upstream,
        license_url=license_url,
        conditions_of_access=_english(
            license_doc.get("conditions_of_access"), "source.license.conditions_of_access"
        ),
        credit_text=_english(license_doc.get("credit_text"), "source.license.credit_text"),
        spatial_name=geography,
    )


def _timestamp(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return value


def _surface_facts(surface_path: Path) -> tuple[list[str], list[dict[str, str]]]:
    """Read temporal coverage and measured variables from the actual deployed surface."""

    try:
        document = json.loads(surface_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"cannot read deployed surface metadata from {surface_path}: {exc}"
        ) from exc
    if not isinstance(document, dict):
        raise ValueError(f"deployed surface must be a JSON object: {surface_path}")

    buckets = sorted(
        timestamp
        for raw in document.get("buckets", [])
        if (timestamp := _timestamp(raw)) is not None
    )
    parameters = sorted(
        {
            str(cell["parameter"])
            for cell in document.get("cells", [])
            if isinstance(cell, dict) and isinstance(cell.get("parameter"), str)
        }
    )
    variables: list[dict[str, str]] = []
    for parameter in parameters:
        name, unit = _PARAMETERS.get(parameter, (parameter, None))
        variable = {"@type": "PropertyValue", "name": name, "propertyID": parameter}
        if unit is not None:
            variable["unitText"] = unit
        variables.append(variable)
    return buckets, variables


def structured_data(
    *,
    base_url: str,
    route: str,
    source: str,
    surface_path: Path,
    source_spec: SourceSpec | None = None,
) -> dict[str, object]:
    """Build the SoftwareApplication + deployed Dataset JSON-LD graph."""

    if source not in SOURCE_SPECS:
        raise ValueError(f"unknown Pages data source: {source}")
    base = normalize_base_url(base_url)
    canonical = canonical_url(base, route)
    spec = source_spec or SOURCE_SPECS[source]
    buckets, variables = _surface_facts(surface_path)

    project: dict[str, str] = {
        "@type": "Organization",
        "name": "Swelter open-source project",
        "url": REPOSITORY_URL,
    }
    software: dict[str, object] = {
        "@type": "SoftwareApplication",
        "@id": f"{base}#software",
        "name": "swelter",
        "url": base,
        "codeRepository": REPOSITORY_URL,
        "license": "https://www.apache.org/licenses/LICENSE-2.0",
        "applicationCategory": "Environmental monitoring",
        "operatingSystem": "Any modern web browser",
        "description": (
            "Open-source software for community heat and air-quality sensing, calibration, "
            "quality control, and accessible publishing."
        ),
        "author": project,
    }
    upstream: list[dict[str, object]] = [
        {
            "@type": "Dataset",
            "name": item.name,
            "url": item.url,
            "license": spec.license_url,
        }
        for item in spec.upstream
    ]
    dataset: dict[str, object] = {
        "@type": "Dataset",
        "@id": f"{canonical}#dataset",
        "name": spec.dataset_name,
        "description": spec.dataset_description,
        "url": canonical,
        "license": spec.license_url,
        "usageInfo": spec.license_url,
        "conditionsOfAccess": spec.conditions_of_access,
        "creditText": spec.credit_text,
        "creator": project,
        "isBasedOn": upstream[0] if len(upstream) == 1 else upstream,
        "distribution": [
            {
                "@type": "DataDownload",
                "name": "Current dashboard surface",
                "contentUrl": f"{canonical}sample-surface.json",
                "encodingFormat": "application/json",
            },
            {
                "@type": "DataDownload",
                "name": "Observation history",
                "contentUrl": f"{canonical}export.csv",
                "encodingFormat": "text/csv",
            },
        ],
        "variableMeasured": variables,
    }
    if spec.spatial_name is not None:
        dataset["spatialCoverage"] = {"@type": "Place", "name": spec.spatial_name}
    if buckets:
        dataset["dateModified"] = buckets[-1]
        dataset["temporalCoverage"] = f"{buckets[0]}/{buckets[-1]}"
    return {"@context": "https://schema.org", "@graph": [software, dataset]}


def _metadata_block(
    *,
    base_url: str,
    route: str,
    source: str,
    surface_path: Path,
    source_spec: SourceSpec | None = None,
) -> str:
    base = normalize_base_url(base_url)
    canonical = canonical_url(base, route)
    spec = source_spec or SOURCE_SPECS[source]
    icon = f"{base}icon-512.png"
    social_image = f"{base}social-card.png"
    social_alt = "swelter beside a California county map with one measured grid cell"
    graph = structured_data(
        base_url=base,
        route=route,
        source=source,
        surface_path=surface_path,
        source_spec=spec,
    )
    json_ld = json.dumps(graph, ensure_ascii=False, indent=2).replace("</", "<\\/")
    indented_json = "\n".join(f"    {line}" for line in json_ld.splitlines())

    def attr(value: str) -> str:
        return escape(value, quote=True)

    return "\n".join(
        [
            f"    {SEO_START}",
            f'    <link rel="canonical" href="{attr(canonical)}" />',
            f'    <link rel="icon" href="{attr(base)}icon.svg" type="image/svg+xml" />',
            f'    <link rel="apple-touch-icon" href="{attr(icon)}" />',
            '    <meta name="robots" content="index,follow,max-image-preview:large" />',
            '    <meta property="og:type" content="website" />',
            '    <meta property="og:site_name" content="swelter" />',
            '    <meta property="og:locale" content="en_US" />',
            f'    <meta property="og:url" content="{attr(canonical)}" />',
            f'    <meta property="og:title" content="{attr(spec.page_title)}" />',
            f'    <meta property="og:description" content="{attr(spec.page_description)}" />',
            f'    <meta property="og:image" content="{attr(social_image)}" />',
            '    <meta property="og:image:width" content="1280" />',
            '    <meta property="og:image:height" content="640" />',
            f'    <meta property="og:image:alt" content="{attr(social_alt)}" />',
            '    <meta name="twitter:card" content="summary_large_image" />',
            f'    <meta name="twitter:title" content="{attr(spec.page_title)}" />',
            f'    <meta name="twitter:description" content="{attr(spec.page_description)}" />',
            f'    <meta name="twitter:image" content="{attr(social_image)}" />',
            f'    <meta name="twitter:image:alt" content="{attr(social_alt)}" />',
            '    <script type="application/ld+json">',
            indented_json,
            "    </script>",
            f"    {SEO_END}",
        ]
    )


def _static_metadata_block(*, base_url: str, route: str, title: str, description: str) -> str:
    """Discovery metadata for a published page that is not a data surface.

    Deliberately narrower than :func:`_metadata_block`. It carries no JSON-LD, because the
    only graph this project emits describes readings and their licence, and a page that
    publishes no readings must not claim to. It also does NOT rewrite the page's title or
    description: those are correct in source for a static page, whereas a data surface's are
    only truthful once the deployed fallback is known.
    """

    base = normalize_base_url(base_url)
    canonical = canonical_url(base, route)
    social_image = f"{base}social-card.png"
    social_alt = "swelter beside a California county map with one measured grid cell"

    def attr(value: str) -> str:
        return escape(value, quote=True)

    return "\n".join(
        [
            f"    {SEO_START}",
            f'    <link rel="canonical" href="{attr(canonical)}" />',
            f'    <link rel="icon" href="{attr(base)}icon.svg" type="image/svg+xml" />',
            f'    <link rel="apple-touch-icon" href="{attr(base)}icon-512.png" />',
            '    <meta name="robots" content="index,follow,max-image-preview:large" />',
            '    <meta property="og:type" content="website" />',
            '    <meta property="og:site_name" content="swelter" />',
            '    <meta property="og:locale" content="en_US" />',
            f'    <meta property="og:url" content="{attr(canonical)}" />',
            f'    <meta property="og:title" content="{attr(title)}" />',
            f'    <meta property="og:description" content="{attr(description)}" />',
            f'    <meta property="og:image" content="{attr(social_image)}" />',
            '    <meta property="og:image:width" content="1280" />',
            '    <meta property="og:image:height" content="640" />',
            f'    <meta property="og:image:alt" content="{attr(social_alt)}" />',
            '    <meta name="twitter:card" content="summary_large_image" />',
            f'    <meta name="twitter:title" content="{attr(title)}" />',
            f'    <meta name="twitter:description" content="{attr(description)}" />',
            f'    <meta name="twitter:image" content="{attr(social_image)}" />',
            f'    <meta name="twitter:image:alt" content="{attr(social_alt)}" />',
            f"    {SEO_END}",
        ]
    )


def write_static_page_metadata(
    web_dir: Path,
    *,
    route: str,
    base_url: str = DEFAULT_BASE_URL,
) -> str:
    """Inject discovery metadata into one published page that is not a data surface.

    The page keeps the title and description it already carries; this reads them so the card
    repeats the page rather than describing it a second time, and refuses rather than invent
    either of them.
    """

    if route not in STATIC_ROUTES:
        raise ValueError(f"not a static public route: {route}")
    index = web_dir / "index.html"
    try:
        html = index.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"cannot read Pages HTML template {index}: {exc}") from exc
    pattern = re.compile(rf"[ \t]*{re.escape(SEO_START)}.*?{re.escape(SEO_END)}", re.DOTALL)
    if len(pattern.findall(html)) != 1:
        raise ValueError(f"{index} must contain exactly one {SEO_START}/{SEO_END} block")
    titles = _TITLE_PATTERN.findall(html)
    descriptions = _DESCRIPTION_PATTERN.findall(html)
    if len(titles) != 1 or len(descriptions) != 1:
        raise ValueError(f"{index} must contain exactly one title and meta description")
    title = re.sub(r"<[^>]+>", "", titles[0]).strip()
    described = re.search(r'content="([^"]*)"', descriptions[0])
    description = " ".join(described.group(1).split()) if described else ""
    if not title or not description:
        raise ValueError(f"{index} must carry a non-empty title and meta description")
    block = _static_metadata_block(
        base_url=base_url, route=route, title=title, description=description
    )
    index.write_text(pattern.sub(lambda _match: block, html), encoding="utf-8")
    return route


def write_page_metadata(
    web_dir: Path,
    *,
    route: str,
    source: str | None = None,
    base_url: str = DEFAULT_BASE_URL,
) -> str:
    """Replace the template marker with deterministic metadata for one deployed route."""

    source = resolve_source(web_dir, source)
    index = web_dir / "index.html"
    surface = web_dir / "sample-surface.json"
    try:
        html = index.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"cannot read Pages HTML template {index}: {exc}") from exc
    pattern = re.compile(rf"[ \t]*{re.escape(SEO_START)}.*?{re.escape(SEO_END)}", re.DOTALL)
    if len(pattern.findall(html)) != 1:
        raise ValueError(f"{index} must contain exactly one {SEO_START}/{SEO_END} block")
    if len(_TITLE_PATTERN.findall(html)) != 1 or len(_DESCRIPTION_PATTERN.findall(html)) != 1:
        raise ValueError(f"{index} must contain exactly one title and meta description")
    # Every deployed route serves this same shell from a different depth, so the cross-route
    # anchors have to be written for the directory this copy is served from before anything
    # else is injected. `/sensors/index.html` shipped with the root page's `href="sensors/"`,
    # which resolves to `/sensors/sensors/` and 404s.
    html = rewrite_route_links(html, route)
    spec = _contract_source_spec(web_dir, source)
    title = f"<title>{escape(spec.page_title)}</title>"
    html = _TITLE_PATTERN.sub(lambda _match: title, html)
    description = escape(spec.page_description, quote=True)
    description_tag = f'<meta name="description" content="{description}" />'
    html = _DESCRIPTION_PATTERN.sub(lambda _match: description_tag, html)
    block = _metadata_block(
        base_url=base_url,
        route=route,
        source=source,
        surface_path=surface,
        source_spec=spec,
    )
    # Callable replacements keep backslashes in truthful source metadata and JSON-LD literal.
    # Passing generated text directly as a replacement template would interpret values such as
    # ``\1`` as regex group references or reject other backslash sequences.
    index.write_text(pattern.sub(lambda _match: block, html), encoding="utf-8")
    return source


def sitemap_document(base_url: str = DEFAULT_BASE_URL) -> bytes:
    """Render every stable, crawlable route; transient application state is never a URL.

    That includes the static routes. The planner is a stable public URL that Pages has been
    serving all along, and leaving it out of the sitemap did not keep it private, only
    undiscovered. What stays out is application state, not pages.
    """

    namespace = "http://www.sitemaps.org/schemas/sitemap/0.9"
    ET.register_namespace("", namespace)
    root = ET.Element(f"{{{namespace}}}urlset")
    for route in PUBLISHED_ROUTES:
        url = ET.SubElement(root, f"{{{namespace}}}url")
        ET.SubElement(url, f"{{{namespace}}}loc").text = canonical_url(base_url, route)
    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    rendered = io.BytesIO()
    tree.write(rendered, encoding="utf-8", xml_declaration=True)
    return rendered.getvalue()


def write_sitemap(output: Path, *, base_url: str = DEFAULT_BASE_URL) -> None:
    """Write the stable Pages sitemap."""

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(sitemap_document(base_url))


class _LinkParser(HTMLParser):
    """Collect every URL the browser will request while rendering one page."""

    def __init__(self) -> None:
        super().__init__()
        self.urls: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attribute = _URL_ATTRIBUTES.get(tag)
        if attribute is None:
            return
        self.urls.extend(value for key, value in attrs if key == attribute and value)


def _publish_filenames() -> frozenset[str]:
    """The files ``swelter publish`` bakes into a route directory, read from the publisher.

    ``export.csv`` and ``DATA-LICENSE`` are linked from the dashboard footer and exist only
    after a deploy has run, so a crawl of the committed tree has to know they are coming.
    Reading the list from ``swelter.cli`` rather than restating it here keeps this check from
    carrying a second copy that can fall quietly behind the thing it describes.
    """

    from swelter.cli import PUBLISH_FILES

    return frozenset(PUBLISH_FILES)


def _files_under(directory: Path) -> set[str]:
    """Every file under ``directory``, relative and POSIX, skipping non-published trees."""

    found: set[str] = set()
    if not directory.is_dir():
        return found
    stack = [directory]
    while stack:
        for entry in stack.pop().iterdir():
            if entry.is_dir():
                if entry.name not in IGNORED_WEB_DIRECTORIES:
                    stack.append(entry)
            elif entry.is_file():
                found.add(entry.relative_to(directory).as_posix())
    return found


def route_documents(web_dir: Path) -> dict[str, str]:
    """Return the HTML served at every published route, read from the tree itself.

    A committed directory contributes the route its own ``index.html`` serves. A synthesized
    route serves the root document until a deploy has actually copied it, at which point the
    copy on disk is authoritative. Nothing here reads a list of routes maintained beside the
    site: a page that exists is a page this crawl has to account for, and a page nobody listed
    is exactly how ``/planner/`` shipped live with no canonical, no card and no sitemap entry.
    """

    root = web_dir / "index.html"
    if not root.is_file():
        raise ValueError(f"no published site to crawl: {root} does not exist")
    documents = {"/": root.read_text(encoding="utf-8")}
    for entry in sorted(web_dir.iterdir()):
        if not entry.is_dir() or entry.name in IGNORED_WEB_DIRECTORIES:
            continue
        index = entry / "index.html"
        if index.is_file():
            documents[f"/{entry.name}/"] = index.read_text(encoding="utf-8")
    for route in SYNTHESIZED_ROUTES:
        if route in documents:
            continue
        # Not built yet. What the deploy will serve here is the root document with its
        # cross-route anchors rewritten for this depth, which is exactly what
        # write_page_metadata does to the copy — so that is what gets crawled. Once a deploy
        # has run, the copy is on disk and no model is applied to it at all.
        documents[route] = rewrite_route_links(documents["/"], route)
    return documents


def rendered_paths(web_dir: Path) -> set[str]:
    """Every site-root-relative file path the deployed artifact serves.

    The tree is the source of truth. A directory the publisher has already written carries
    ``publish-manifest.json``, and then only what is really on disk counts; a directory it has
    not written yet gets the publisher's own declared output added, because that is what the
    deploy will put there.
    """

    baked = _publish_filenames()
    paths = _files_under(web_dir)
    if "publish-manifest.json" not in paths:
        paths |= baked
    for route, copied in SYNTHESIZED_ROUTES.items():
        prefix = route.strip("/")
        if f"{prefix}/index.html" in paths:
            continue  # a real deploy built this route; the walk above already holds the truth
        names = {entry.name for entry in web_dir.iterdir() if entry.is_file()}
        for subtree in copied:
            names |= {f"{subtree}/{name}" for name in _files_under(web_dir / subtree)}
        paths |= {f"{prefix}/{name}" for name in names | baked}
    return paths


def resolve_internal_link(route: str, href: str, *, base_url: str) -> str | None:
    """Return the file ``href`` reaches from ``route``, relative to the site root.

    ``None`` means the link leaves this site — a fragment, a ``mailto:``, an absolute URL on
    another host — and is not this gate's business. :data:`UNRESOLVABLE` means it names
    something this project site cannot serve at all. A directory target resolves to the
    ``index.html`` the host serves for it, because that is the file that has to exist.
    """

    href = href.strip()
    if not href or href.startswith("#"):
        return None
    parts = urlsplit(href)
    base = urlsplit(normalize_base_url(base_url))
    if parts.scheme or parts.netloc:
        if (parts.scheme, parts.netloc) != (base.scheme, base.netloc):
            return None
        if not parts.path.startswith(base.path):
            return UNRESOLVABLE  # a sibling project site's path on this shared origin
        target = parts.path[len(base.path) :]
    elif parts.path.startswith("/"):
        # Root-absolute on a project site drops the `/swelter/` prefix the whole site lives
        # under, so it lands on the shared origin rather than on this project.
        return UNRESOLVABLE
    else:
        target = posixpath.join(route.lstrip("/"), parts.path)
    directory = target in ("", ".", "..") or target.endswith(("/", "/.", "/.."))
    normalized = posixpath.normpath(target) if target else ""
    if normalized in (".", "/"):
        normalized = ""
    if normalized == ".." or normalized.startswith("../"):
        return UNRESOLVABLE
    if directory:
        return f"{normalized}/index.html" if normalized else "index.html"
    return normalized


def _index_path(route: str) -> str:
    """The file a static host serves for one route."""

    return "index.html" if route == "/" else f"{route.strip('/')}/index.html"


def _sweep_problems(documents: dict[str, str], paths: set[str]) -> list[str]:
    """Refuse a crawl whose inputs collapsed, or whose page set is not the published one.

    A gate whose input silently became empty passes forever, and a page nobody listed in
    ``PUBLISHED_ROUTES`` gets no canonical, no card and no sitemap entry.
    """

    problems: list[str] = []
    if len(documents) <= 1:
        problems.append(
            f"the page sweep collapsed to {len(documents)} rendered page(s); a crawl over one "
            "page or none would prove nothing"
        )
    if len(paths) <= len(documents):
        problems.append(
            f"the file sweep collapsed to {len(paths)} file(s) for {len(documents)} page(s); a "
            "link check against that set would prove nothing"
        )
    for route in sorted(set(PUBLISHED_ROUTES) - set(documents)):
        problems.append(f"published route {route} renders no page")
    for route in sorted(set(documents) - set(PUBLISHED_ROUTES)):
        problems.append(
            f"{route} renders a page but is not in PUBLISHED_ROUTES, so it gets no canonical "
            "URL, no social card and no sitemap entry"
        )
    return problems


def _link_problems(
    documents: dict[str, str], paths: set[str], *, base_url: str
) -> tuple[list[str], dict[str, set[str]]]:
    """Check every internal link, and record which routes link to which."""

    problems: list[str] = []
    routes_by_index = {_index_path(route): route for route in documents}
    inbound: dict[str, set[str]] = {route: set() for route in documents}
    for route in sorted(documents):
        parser = _LinkParser()
        parser.feed(documents[route])
        internal = 0
        for href in parser.urls:
            target = resolve_internal_link(route, href, base_url=base_url)
            if target is None:
                continue
            internal += 1
            if target == UNRESOLVABLE:
                problems.append(f"{route} links to {href!r}, which is not on this project site")
            elif target not in paths:
                problems.append(
                    f"{route} links to {href!r}, which resolves to /{target} — nothing is "
                    "rendered there"
                )
            elif target in routes_by_index:
                inbound[routes_by_index[target]].add(route)
        if internal == 0:
            problems.append(f"{route} carries no internal links; the link sweep found nothing")
    return problems, inbound


def _sitemap_problems(web_dir: Path, inbound: dict[str, set[str]], *, base_url: str) -> list[str]:
    """Every sitemap URL must be reachable by following links from another rendered page."""

    problems: list[str] = []
    urls = {canonical_url(base_url, route): route for route in PUBLISHED_ROUTES}
    sitemap = web_dir / "sitemap.xml"
    # The deployed file is compared against what `write_sitemap` produces rather than parsed
    # for its URLs: reading a committed list back and checking that list against itself is how
    # a gate ends up unable to fail. A drifted or hand-edited sitemap is the finding.
    if sitemap.is_file() and sitemap.read_bytes() != sitemap_document(base_url):
        problems.append(
            f"{sitemap} is not what the published routes generate; regenerate it with "
            "`pages_seo.py sitemap` rather than editing it"
        )
    if not urls:
        return [*problems, "the sitemap sweep found no URLs to check for inbound links"]
    for url, route in urls.items():
        if not inbound.get(route, set()) - {route}:
            problems.append(
                f"{url} is in the sitemap and no other rendered page links to it; a page "
                "reachable only from the sitemap gets no readers and no internal link equity"
            )
    return problems


def crawl_problems(web_dir: Path, *, base_url: str = DEFAULT_BASE_URL) -> list[str]:
    """Return every broken internal link and every orphaned sitemap URL in a rendered site.

    Two defects shipped to the live site because nothing checked either of them: ``/sensors/``
    served the root page's ``href="sensors/"``, which resolves to ``/sensors/sensors/`` and
    404s, and ``/planner/`` was in the sitemap with no page on the site linking to it.
    """

    documents = route_documents(web_dir)
    paths = rendered_paths(web_dir)
    problems = _sweep_problems(documents, paths)
    link_problems, inbound = _link_problems(documents, paths, base_url=base_url)
    return [*problems, *link_problems, *_sitemap_problems(web_dir, inbound, base_url=base_url)]


def check_template(template: Path) -> list[str]:
    """Return configuration errors caught before the Pages job ever runs."""

    errors: list[str] = []
    try:
        html = template.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"cannot read {template}: {exc}"]
    if html.count(SEO_START) != 1 or html.count(SEO_END) != 1:
        errors.append(f"{template} must contain exactly one Pages SEO marker block")
    elif html.find(SEO_START) > html.find(SEO_END):
        errors.append(f"{template} has its Pages SEO marker block in the wrong order")
    if len(_TITLE_PATTERN.findall(html)) != 1 or len(_DESCRIPTION_PATTERN.findall(html)) != 1:
        errors.append(f"{template} must contain exactly one title and meta description")
    # A project-path robots.txt would live at /swelter/robots.txt. Crawlers only apply the file at
    # the origin root (/robots.txt), which this project repository cannot publish.
    if (template.parent / "robots.txt").exists():
        errors.append(
            "web/robots.txt cannot control this GitHub Pages project site; use page-level robots "
            "metadata until the origin root or a custom domain is controlled"
        )
    for key, spec in SOURCE_SPECS.items():
        urls = [("license", spec.license_url)]
        urls.extend((f"upstream {item.name}", item.url) for item in spec.upstream)
        for label, value in urls:
            parts = urlsplit(value)
            if parts.scheme != "https" or not parts.netloc:
                errors.append(f"{key} {label} URL must be absolute HTTPS: {value}")
    return errors


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    page = subparsers.add_parser("page", help="inject metadata into one built dashboard route")
    page.add_argument("--web-dir", type=Path, required=True)
    page.add_argument("--route", choices=KNOWN_ROUTES, required=True)
    page.add_argument("--source", choices=tuple(SOURCE_SPECS))
    page.add_argument("--base-url", default=DEFAULT_BASE_URL)

    static = subparsers.add_parser(
        "static-page", help="inject metadata into one published page that is not a data surface"
    )
    static.add_argument("--web-dir", type=Path, required=True)
    static.add_argument("--route", choices=STATIC_ROUTES, required=True)
    static.add_argument("--base-url", default=DEFAULT_BASE_URL)

    sitemap = subparsers.add_parser("sitemap", help="write the stable Pages sitemap")
    sitemap.add_argument("--output", type=Path, required=True)
    sitemap.add_argument("--base-url", default=DEFAULT_BASE_URL)

    crawl = subparsers.add_parser(
        "crawl", help="resolve every internal link and find pages nothing links to"
    )
    crawl.add_argument("--web-dir", type=Path, required=True)
    crawl.add_argument("--base-url", default=DEFAULT_BASE_URL)

    check = subparsers.add_parser("check", help="validate the source template and crawl policy")
    check.add_argument("--template", type=Path, default=Path("web/index.html"))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "page":
        source = write_page_metadata(
            args.web_dir, route=args.route, source=args.source, base_url=args.base_url
        )
        print(f"pages-seo: wrote {canonical_url(args.base_url, args.route)} ({source})")
        return 0
    if args.command == "static-page":
        write_static_page_metadata(args.web_dir, route=args.route, base_url=args.base_url)
        print(f"pages-seo: wrote {canonical_url(args.base_url, args.route)} (static)")
        return 0
    if args.command == "sitemap":
        write_sitemap(args.output, base_url=args.base_url)
        print(f"pages-seo: wrote {args.output}")
        return 0
    if args.command == "crawl":
        problems = crawl_problems(args.web_dir, base_url=args.base_url)
        if problems:
            for problem in problems:
                print(f"pages-seo: FAIL: {problem}", file=sys.stderr)
            return 1
        pages = len(route_documents(args.web_dir))
        print(f"pages-seo: every internal link on {pages} rendered pages resolves, none orphaned")
        return 0

    errors = check_template(args.template)
    if errors:
        for error in errors:
            print(f"pages-seo: FAIL: {error}", file=sys.stderr)
        return 1
    print("pages-seo: template, source URLs, and project-site crawl policy are valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
