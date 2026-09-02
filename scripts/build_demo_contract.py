#!/usr/bin/env python3
"""Build the static demo's source-of-truth contract from its baked surface.

GitHub Pages chooses among several sources at build time.  This script makes the winning source,
its limits, its reuse terms, and the measurements/statuses actually present in the surface into one
machine-readable artifact.  The dashboard reads that artifact before deciding whether to call a
live API, so a static deployment never has to guess which fallback won.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _text(en: str, es: str) -> dict[str, str]:
    return {"en": en, "es": es}


PROFILES: dict[str, dict[str, Any]] = {
    "openaq": {
        "name": _text("OpenAQ physical sensors", "Sensores físicos de OpenAQ"),
        "attribution": _text(
            "Data accessed through OpenAQ; original providers vary by location.",
            "Datos obtenidos mediante OpenAQ; los proveedores originales varían según la "
            "ubicación.",
        ),
        "upstream": [{"name": "OpenAQ", "url": "https://openaq.org/"}],
        "navigation_label": _text(
            "California region · OpenAQ sensors", "Región de California · sensores OpenAQ"
        ),
        "tagline": _text(
            "Physical air-sensor readings, published provisional with their source shown.",
            "Lecturas de sensores físicos de aire, publicadas como provisionales y con su fuente.",
        ),
        "geography": _text(
            "California sites accepted against the packaged 2025 U.S. Census state boundary.",
            "Sitios de California aceptados según el límite estatal de 2025 del Censo de "
            "EE. UU. incluido en el paquete.",
        ),
        "calibration": _text(
            "Not calibrated by Swelter. Every displayed reading is provisional.",
            "Sin calibración de Swelter. Cada lectura mostrada es provisional.",
        ),
        "uncertainty": _text(
            "Provisional readings do not carry Swelter calibration uncertainty.",
            "Las lecturas provisionales no llevan incertidumbre de calibración de Swelter.",
        ),
        "location": _text(
            "Published sensor locations snap to a roughly 150 m grid.",
            "Las ubicaciones publicadas de los sensores se ajustan a una cuadrícula de "
            "aproximadamente 150 m.",
        ),
        "expected_mode": "all_provisional",
        "license": {
            "summary": _text(
                "OpenAQ data carries provider-specific licenses and terms. Credit OpenAQ and each "
                "original provider, and review provider metadata before reuse.",
                "Los datos de OpenAQ llevan licencias y condiciones específicas de cada proveedor. "
                "Atribuya a OpenAQ y a cada proveedor original, y revise sus metadatos antes de "
                "reutilizarlos.",
            ),
            "name": "Provider-specific OpenAQ terms",
            "url": "https://docs.openaq.org/about/terms",
            "conditions_of_access": _text(
                "Comply with every original provider's terms and the OpenAQ Terms of Use.",
                "Cumpla las condiciones de cada proveedor original y las condiciones de uso de "
                "OpenAQ.",
            ),
            "credit_text": _text(
                "Credit OpenAQ and every original data provider represented in the export.",
                "Atribuya a OpenAQ y a cada proveedor de datos original representado en la "
                "exportación.",
            ),
            "links": [
                {
                    "label": _text("OpenAQ terms", "Condiciones de OpenAQ"),
                    "href": "https://docs.openaq.org/about/terms",
                },
                {
                    "label": _text("OpenAQ license metadata", "Metadatos de licencia de OpenAQ"),
                    "href": "https://docs.openaq.org/resources/licenses",
                },
                {
                    "label": _text(
                        "This release's source-license ledger",
                        "Registro de licencias de fuentes de esta versión",
                    ),
                    "href": "source-license-ledger.json",
                },
            ],
        },
    },
    "openmeteo": {
        "name": _text("Copernicus CAMS via Open-Meteo", "Copernicus CAMS mediante Open-Meteo"),
        "attribution": _text(
            "Copernicus CAMS air-quality and Open-Meteo weather data via Open-Meteo.",
            "Datos de calidad del aire de Copernicus CAMS y meteorológicos de Open-Meteo mediante "
            "Open-Meteo.",
        ),
        "upstream": [
            {"name": "Open-Meteo", "url": "https://open-meteo.com/"},
            {"name": "Copernicus CAMS", "url": "https://atmosphere.copernicus.eu/"},
        ],
        "navigation_label": _text("California · CAMS model", "California · modelo CAMS"),
        "tagline": _text(
            "Hourly heat and air model output, with its source limits shown.",
            "Datos horarios modelados de calor y aire, con los límites de la fuente visibles.",
        ),
        "geography": _text(
            "California city centroids snapped to atmospheric model grid cells.",
            "Centroides de ciudades de California ajustados a celdas del modelo atmosférico.",
        ),
        "calibration": _text(
            "Upstream atmospheric model output, not a Swelter-calibrated sensor network. "
            "Every displayed reading is provisional.",
            "Datos de un modelo atmosférico externo, no de una red de sensores calibrada por "
            "Swelter. Cada lectura mostrada es provisional.",
        ),
        "uncertainty": _text(
            "No Swelter calibration uncertainty is published for this upstream model surface.",
            "No se publica incertidumbre de calibración de Swelter para esta superficie de un "
            "modelo externo.",
        ),
        "location": _text(
            "City centroids identify model grid cells; the displayed points do not imply "
            "neighborhood-scale measurements.",
            "Los centroides de las ciudades identifican celdas del modelo; los puntos mostrados "
            "no implican mediciones a escala de vecindario.",
        ),
        "terminology": {
            "non_provisional_label": _text("Upstream model", "Modelo externo"),
            "non_provisional_explanation": _text(
                "Upstream CAMS model output; not a Swelter sensor calibration.",
                "Datos del modelo externo CAMS; no son una calibración de sensores de Swelter.",
            ),
            "overview_counts": _text(
                "{$n} locations — {$provisional} provisional upstream model readings.",
                "{$n} ubicaciones — {$provisional} lecturas provisionales del modelo externo.",
            ),
            # ADR 0040: a city centroid identifies a model grid cell, not a host — so there is no
            # device to be "reporting", "good", or "offline". Describe data availability instead of
            # inventing device health for a fleet that does not exist.
            "coverage": _text(
                "Model cells with values this hour: {$now} of {$total}.",
                "Celdas del modelo con valores esta hora: {$now} de {$total}.",
            ),
            "health_status": _text(
                "Model cell values at {$time}: {$ok} present · {$degraded} sparse · "
                "{$offline} missing.",
                "Valores de celdas del modelo a las {$time}: {$ok} presentes · {$degraded} "
                "escasos · {$offline} ausentes.",
            ),
            "network_intro": _text(
                "Model cell coverage, value availability, and alerts.",
                "Cobertura de celdas del modelo, disponibilidad de valores y alertas.",
            ),
            "headline_worst": _text(
                "Highest modeled air right now: {$place} — AQI {$aqi}, {$category}.",
                "Mayor nivel de aire modelado ahora: {$place} — ICA {$aqi}, {$category}.",
            ),
            "headline_none": _text(
                "No modeled air-quality values are available for this hour.",
                "No hay valores modelados de calidad del aire para esta hora.",
            ),
            "overview_none": _text(
                "No upstream model values this hour.",
                "No hay valores del modelo externo esta hora.",
            ),
            "overview_worst_label": _text("Highest modeled now:", "Mayor valor modelado ahora:"),
        },
        "expected_mode": "all_provisional",
        "license": {
            "summary": _text(
                "Copernicus CAMS data via Open-Meteo is reused under CC BY 4.0 with attribution.",
                "Los datos de Copernicus CAMS mediante Open-Meteo se reutilizan bajo CC BY 4.0 "
                "con atribución.",
            ),
            "name": "CC BY 4.0",
            "url": "https://open-meteo.com/en/licence",
            "conditions_of_access": _text(
                "Give appropriate credit, link the license, and indicate changes.",
                "Dé el crédito correspondiente, enlace la licencia e indique los cambios.",
            ),
            "credit_text": _text(
                "Weather data by Open-Meteo.com; air-quality data from Copernicus CAMS via "
                "Open-Meteo.",
                "Datos meteorológicos de Open-Meteo.com; datos de calidad del aire de Copernicus "
                "CAMS mediante Open-Meteo.",
            ),
            "links": [
                {
                    "label": _text("Open-Meteo license", "Licencia de Open-Meteo"),
                    "href": "https://open-meteo.com/en/licence",
                }
            ],
        },
    },
    "sensor-community": {
        "name": _text(
            "Sensor.Community low-cost sensors", "Sensores de bajo costo de Sensor.Community"
        ),
        "attribution": _text(
            "Environmental observations from Sensor.Community.",
            "Observaciones ambientales de Sensor.Community.",
        ),
        "upstream": [{"name": "Sensor.Community", "url": "https://sensor.community/"}],
        "navigation_label": _text(
            "Stuttgart · community sensors", "Stuttgart · sensores comunitarios"
        ),
        "tagline": _text(
            "Community low-cost sensor readings, published provisional with their source shown.",
            "Lecturas de sensores comunitarios de bajo costo, publicadas como provisionales y "
            "con su fuente.",
        ),
        "geography": _text(
            "A 30 km radius around Stuttgart, Germany; precise public sensor coordinates.",
            "Un radio de 30 km alrededor de Stuttgart, Alemania; coordenadas públicas precisas "
            "de los sensores.",
        ),
        "calibration": _text(
            "Not calibrated by Swelter. Every displayed reading is provisional.",
            "Sin calibración de Swelter. Cada lectura mostrada es provisional.",
        ),
        "uncertainty": _text(
            "Provisional readings do not carry Swelter calibration uncertainty.",
            "Las lecturas provisionales no llevan incertidumbre de calibración de Swelter.",
        ),
        "location": _text(
            "Published sensor locations snap to a roughly 150 m grid.",
            "Las ubicaciones publicadas de los sensores se ajustan a una cuadrícula de "
            "aproximadamente 150 m.",
        ),
        "expected_mode": "all_provisional",
        "license": {
            "summary": _text(
                "Sensor.Community database contents use the Open Data Commons DbCL 1.0. Follow "
                "the ODbL conditions incorporated by that license.",
                "El contenido de la base de datos de Sensor.Community usa Open Data Commons DbCL "
                "1.0. Siga las condiciones de ODbL incorporadas por esa licencia.",
            ),
            "name": "Open Data Commons DbCL 1.0",
            "url": "https://opendatacommons.org/licenses/dbcl/1-0/",
            "conditions_of_access": _text(
                "The DbCL requires compliance with the ODbL covering the database.",
                "La DbCL exige cumplir la ODbL que cubre la base de datos.",
            ),
            "credit_text": _text(
                "Environmental observations from Sensor.Community.",
                "Observaciones ambientales de Sensor.Community.",
            ),
            "links": [
                {
                    "label": _text("DbCL 1.0", "DbCL 1.0"),
                    "href": "https://opendatacommons.org/licenses/dbcl/1-0/",
                }
            ],
        },
    },
    "synthetic": {
        "name": _text("Swelter synthetic worked example", "Ejemplo práctico sintético de Swelter"),
        "attribution": _text(
            "Synthetic demonstration data generated by Swelter; no real sensors.",
            "Datos sintéticos de demostración generados por Swelter; no hay sensores reales.",
        ),
        "upstream": [{"name": "Swelter", "url": "https://github.com/ChelseaKR/swelter"}],
        "navigation_label": _text("Synthetic calibrated example", "Ejemplo sintético calibrado"),
        "tagline": _text(
            "A reproducible calibration example — not real current conditions.",
            "Un ejemplo reproducible de calibración — no son condiciones actuales reales.",
        ),
        "geography": _text(
            "A statewide California preview at public place centroids. All readings are synthetic.",
            "Una vista previa estatal de California en centroides de lugares públicos. Todas las "
            "lecturas son sintéticas.",
        ),
        "calibration": _text(
            "A synthetic worked example containing both calibrated and provisional readings. "
            "No reading is real.",
            "Un ejemplo práctico sintético con lecturas calibradas y provisionales. Ninguna "
            "lectura es real.",
        ),
        "uncertainty": _text(
            "Calibrated synthetic readings carry a published 1-sigma uncertainty; provisional "
            "ones do not.",
            "Las lecturas sintéticas calibradas llevan una incertidumbre publicada de 1 sigma; "
            "las provisionales no.",
        ),
        "location": _text(
            "The static preview maps the worked-example records to public California place "
            "centroids; it does not report conditions at those places.",
            "La vista previa estática asigna los registros del ejemplo a centroides de lugares "
            "públicos de California; no informa condiciones en esos lugares.",
        ),
        "expected_mode": "mixed",
        "license": {
            "summary": _text(
                "Swelter's synthetic demonstration observations are dedicated to the public "
                "domain under CC0-1.0.",
                "Las observaciones sintéticas de demostración de Swelter se dedican al dominio "
                "público bajo CC0-1.0.",
            ),
            "name": "CC0-1.0",
            "url": "https://creativecommons.org/publicdomain/zero/1.0/",
            "conditions_of_access": _text(
                "No attribution is legally required; citing Swelter preserves provenance.",
                "No se exige atribución legal; citar a Swelter conserva la procedencia.",
            ),
            "credit_text": _text(
                "Synthetic demonstration data generated by Swelter.",
                "Datos sintéticos de demostración generados por Swelter.",
            ),
            "links": [
                {
                    "label": _text("CC0-1.0", "CC0-1.0"),
                    "href": "https://creativecommons.org/publicdomain/zero/1.0/",
                }
            ],
        },
    },
}

# Distinct markers written into sample-surface.json by the source adapters (or
# cmd_demo). Calibration mode alone cannot distinguish two raw sensor sources,
# so the contract also verifies the baked surface's own provenance before it
# names a source to residents.
SURFACE_ATTRIBUTION_MARKERS = {
    "openaq": "Real readings accessed via OpenAQ;",
    "openmeteo": "Real hourly readings for California cities from the Copernicus Atmosphere",
    "sensor-community": "Real readings from the Sensor.Community network",
    "synthetic": "Synthetic demonstration data — no real sensors",
}

PARAMETER_ORDER = (
    "pm25_ugm3",
    "exposure",
    "temp_c",
    "heat_index_c",
    "wbgt_c",
    "pm10_ugm3",
)


def _surface_facts(surface: Any) -> dict[str, Any]:
    if not isinstance(surface, dict) or not isinstance(surface.get("cells"), list):
        raise ValueError("surface must be a JSON object with a cells array")
    cells = surface["cells"]
    if not cells:
        raise ValueError("surface contains no cells")
    if not all(isinstance(cell, dict) for cell in cells):
        raise ValueError("every surface cell must be an object")

    parameters = {cell.get("parameter") for cell in cells}
    if not all(isinstance(parameter, str) for parameter in parameters):
        raise ValueError("every surface cell must name a parameter")
    unsupported = parameters - set(PARAMETER_ORDER)
    if unsupported:
        raise ValueError(f"dashboard has no label/control for parameters: {sorted(unsupported)}")

    provisional = sum(cell.get("provisional") is True for cell in cells)
    confirmed = sum(cell.get("provisional") is False for cell in cells)
    if provisional + confirmed != len(cells):
        raise ValueError("every surface cell must carry a boolean provisional state")
    if provisional and confirmed:
        mode = "mixed"
    elif provisional:
        mode = "all_provisional"
    else:
        mode = "all_confirmed"
    return {
        "parameters": [parameter for parameter in PARAMETER_ORDER if parameter in parameters],
        "calibration_mode": mode,
        "provisional_records": provisional,
        "confirmed_records": confirmed,
        "latest_bucket": max(surface.get("buckets") or [cell.get("bucket", "") for cell in cells]),
    }


def build_contract(source: str, surface: Any, *, fallback_for: str | None = None) -> dict[str, Any]:
    """Return a validated, deterministic contract for one baked static surface."""
    profile = PROFILES[source]
    facts = _surface_facts(surface)
    expected = profile["expected_mode"]
    if facts["calibration_mode"] != expected:
        raise ValueError(
            f"{source} claims {expected}, but the baked surface is {facts['calibration_mode']}"
        )
    input_attribution = str(surface.get("attribution") or "")
    marker = SURFACE_ATTRIBUTION_MARKERS[source]
    if marker not in input_attribution:
        raise ValueError(
            f"{source} does not match the baked surface attribution {input_attribution!r}"
        )

    source_doc = {key: value for key, value in profile.items() if key != "expected_mode"}
    contract: dict[str, Any] = {
        "schema_version": 1,
        "runtime": "static",
        "source": {"id": source, **source_doc},
        "surface": facts,
        "attribution": profile["attribution"]["en"],
        "build_input_attribution": input_attribution,
    }
    if fallback_for:
        contract["fallback"] = {
            "requested_source": fallback_for,
            "message": _text(
                "The requested community-sensor feed was unavailable when this site was built. "
                "This route is showing the fallback source named above.",
                "La fuente solicitada de sensores comunitarios no estaba disponible cuando se "
                "creó este sitio. Esta ruta muestra la fuente alternativa indicada arriba.",
            ),
        }
    return contract


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, choices=sorted(PROFILES))
    parser.add_argument("--surface", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--fallback-for", choices=sorted(PROFILES))
    args = parser.parse_args()

    try:
        surface = json.loads(args.surface.read_text(encoding="utf-8"))
        contract = build_contract(args.source, surface, fallback_for=args.fallback_for)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        parser.exit(status=2, message=f"{parser.prog}: error: {exc}\n")
    args.output.write_text(
        json.dumps(contract, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
