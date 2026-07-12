---
title: 'swelter: a community-owned heat and air-quality sensing network with reproducible calibration and accessible open data'
tags:
  - Python
  - air quality
  - urban heat island
  - low-cost sensors
  - sensor calibration
  - environmental justice
  - open data
  - accessibility
authors:
  - name: Chelsea Kelly-Reif
    corresponding: true
    affiliation: 1
affiliations:
  - name: Independent Researcher, United States
    index: 1
date: 9 July 2026
bibliography: paper.bib
---

<!--
DRAFT — not yet submitted. JOSS requires a tagged release archived with a DOI
(e.g., via the Zenodo GitHub integration) before submission, and an author who
will respond to reviewers during the review. Submission timing is the
maintainer's call. See docs/citability.md for the staged steps.
-->

# Summary

`swelter` is a Python package for running a community-owned network of low-cost
heat and air-quality sensors: the ingest pipeline, quality control, per-node
calibration, spatial aggregation, open API, and accessible public dashboard
that make low-cost readings trustworthy enough to publish. Nodes measure
temperature, humidity, PM2.5/PM10, optional NO2, and a derived heat index
[@rothfusz1990]. A one-way pipeline validates and stores immutable raw
observations, flags range, spike, and flatline faults, fits per-node
corrections against co-located reference monitors, aggregates hourly surfaces
on a coarse published grid, and serves the result as a map, a sortable table,
and a plain list in English and Spanish behind a structural WCAG 2.2 AA merge
gate.

Three properties are enforced by construction rather than by convention.
First, calibrated and raw values are never silently mixed: every observation
carries either the literal `"raw"` or a versioned correction identifier, the
storage key includes the calibration state, and uncalibrated nodes are
published as provisional rather than promoted to fact. Second, calibration is
reproducible: the fit is pure-Python ordinary least squares with coefficients
rounded to six decimal places, so re-running it on the committed co-location
data rebuilds the published correction registry byte-for-byte. The PM
correction is humidity-aware, following the form of the US EPA's
nationwide PurpleAir correction [@barkjohn2021], and every calibrated value
carries its residual standard deviation as a 1-sigma uncertainty. Third, the
data is open and portable: observations are CC0-1.0 and export as CSV, JSON, a
read-only subset of the OGC SensorThings API [@ogc2021], and a SQLite store a
resident can open directly in Datasette, with no account or key.

The package is standard-library Python (one runtime dependency, PyYAML), ships
a deterministic synthetic demo that replays a recorded multi-week network
through the full pipeline with no hardware, and includes adapters that pull
real current data from OpenAQ [@openaq], Open-Meteo, and the Sensor.Community
network [@sensorcommunity] through the identical pipeline, labeled with their
provenance and calibration state.

# Statement of need

Extreme heat is the deadliest weather hazard in the United States, and both
heat and air-pollution exposure are distributed unevenly within cities:
formerly redlined neighborhoods are measurably hotter than their neighbors
[@hoffman2020], and people of color live in census tracts with higher surface
urban heat island intensity in nearly all large US urbanized areas
[@hsu2021]. The official record does not resolve these block-scale
differences. The regulatory PM2.5 monitoring network leaves large monitored
gaps — an estimated 44% of urban areas exceeding the 2024 PM2.5 standard,
about 20 million people, would go undetected by the current network
[@wang2024] — and forecast products such as the NWS/CDC HeatRisk index
[@heatrisk] operate at community scale, not at the resolution of a block or a
porch. Guidance for measuring and mitigating urban heat islands exists
[@epaheatislands], but it is guidance, not runnable infrastructure.

Low-cost sensors can fill the spatial gap, but they drift, and optical PM
sensors read high in humid air; publishing their raw output as fact misleads
the neighborhoods the data is meant to serve [@barkjohn2021]. Existing
platforms each solve part of the problem: PurpleAir [@purpleair] provides
dense low-cost PM hardware and a hosted map, Sensor.Community
[@sensorcommunity] coordinates a large volunteer sensor network publishing
raw values, and OpenAQ [@openaq] aggregates and redistributes heterogeneous
open air-quality data. What a neighborhood collective cannot get from any of
them is a self-hosted, auditable pipeline it owns end to end: reference-based
per-node calibration with published uncertainty, an explicit raw-versus-
calibrated distinction that survives storage, aggregation, API, and export,
location privacy for sensor hosts (published coordinates snap to a ~150 m
grid unless a host opts into precision), and an accessible bilingual
dashboard in which the map is never the only way into the data. `swelter` is
that missing piece, packaged so a hosting collective — or a researcher
studying intra-urban heat and air-quality disparities — can run, audit, fork,
and leave with the data.

# Functionality

- **Ingest and QC** (`swelter ingest`, `swelter qc`): wide sensor payloads are
  exploded into immutable, content-hashed observations; malformed payloads are
  quarantined, duplicates are idempotently ignored; range, spike, flatline,
  and gap checks label data without deleting it.
- **Calibration** (`swelter calibrate`): per-node OLS corrections fit on
  co-location windows against reference monitors — humidity-aware for PM
  [@barkjohn2021], enclosure-offset for temperature — with versioned
  correction identifiers, 1-sigma residual uncertainty, and a YAML registry
  that rebuilds byte-for-byte from committed data.
- **Aggregation** (`swelter aggregate`): hourly rollups on the published
  coarse grid, preferring calibrated QC-clean values and marking cells
  provisional otherwise; PM2.5 cells carry the US EPA AQI, and heat-index
  values follow the NWS Rothfusz regression [@rothfusz1990].
- **Serving and export** (`swelter serve`, `swelter export`): a read-only OGC
  SensorThings 1.1 subset [@ogc2021], GeoJSON surfaces, CSV/JSON dumps
  (CC0-1.0), and a Datasette-openable SQLite store.
- **Dashboard**: framework-free static web app; map, sortable table, and
  plain list as three equal views; English and Spanish; WCAG 2.2 AA checked
  by a structural gate in CI; severity never conveyed by color alone.
- **Demo and real data** (`swelter demo`, `swelter fetch`): a deterministic
  synthetic network for a no-hardware walkthrough, and adapters for OpenAQ,
  Open-Meteo, and Sensor.Community that run real current data through the
  same pipeline, ingested raw and displayed provisional.

The full merge gate (`make verify`) runs formatting, lint, strict typing,
the accessibility and internationalization checks, and a 257-test suite with
a 90% branch-coverage floor.

# Acknowledgements

`swelter` builds on open data and open infrastructure: OpenAQ, Open-Meteo
(Copernicus CAMS), Sensor.Community, US EPA air-sensor correction research,
and the OGC SensorThings API specification. This is an independent personal
open-source project; it received no external funding and is unaffiliated with
any employer or client.

# References
