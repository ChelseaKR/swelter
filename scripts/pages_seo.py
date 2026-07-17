#!/usr/bin/env python3
"""Build source-aware search metadata for the GitHub Pages demo.

The dashboard template is also used by self-hosted Swelter instances, so it must not carry a
canonical URL for the GitHub project site in source control.  The Pages workflow calls this script
after it knows which data-source fallback succeeded.  That is the point where an absolute canonical
URL, social metadata, and a license-correct Dataset description can be generated truthfully.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

DEFAULT_BASE_URL = "https://chelseakr.github.io/swelter/"
REPOSITORY_URL = "https://github.com/ChelseaKR/swelter"
SEO_START = "<!-- pages-seo:start -->"
SEO_END = "<!-- pages-seo:end -->"
KNOWN_ROUTES = ("/", "/sensors/")
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

    if route not in KNOWN_ROUTES:
        raise ValueError(f"unknown public route: {route}")
    base = normalize_base_url(base_url)
    return base if route == "/" else f"{base}{route.strip('/')}/"


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
            f'    <meta property="og:image" content="{attr(icon)}" />',
            '    <meta property="og:image:width" content="512" />',
            '    <meta property="og:image:height" content="512" />',
            '    <meta property="og:image:alt" content="swelter sun and heat-wave logo" />',
            '    <meta name="twitter:card" content="summary" />',
            f'    <meta name="twitter:title" content="{attr(spec.page_title)}" />',
            f'    <meta name="twitter:description" content="{attr(spec.page_description)}" />',
            f'    <meta name="twitter:image" content="{attr(icon)}" />',
            '    <meta name="twitter:image:alt" content="swelter sun and heat-wave logo" />',
            '    <script type="application/ld+json">',
            indented_json,
            "    </script>",
            f"    {SEO_END}",
        ]
    )


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


def write_sitemap(output: Path, *, base_url: str = DEFAULT_BASE_URL) -> None:
    """Write the two stable, crawlable routes; transient application state is never a URL."""

    namespace = "http://www.sitemaps.org/schemas/sitemap/0.9"
    ET.register_namespace("", namespace)
    root = ET.Element(f"{{{namespace}}}urlset")
    for route in KNOWN_ROUTES:
        url = ET.SubElement(root, f"{{{namespace}}}url")
        ET.SubElement(url, f"{{{namespace}}}loc").text = canonical_url(base_url, route)
    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    output.parent.mkdir(parents=True, exist_ok=True)
    tree.write(output, encoding="utf-8", xml_declaration=True)


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

    sitemap = subparsers.add_parser("sitemap", help="write the stable Pages sitemap")
    sitemap.add_argument("--output", type=Path, required=True)
    sitemap.add_argument("--base-url", default=DEFAULT_BASE_URL)

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
    if args.command == "sitemap":
        write_sitemap(args.output, base_url=args.base_url)
        print(f"pages-seo: wrote {args.output}")
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
