"""swelter — a community heat and air-quality sensing network with open, calibrated data.

The public Python API mirrors the pipeline the README describes, one module per stage:

* :mod:`swelter.ingest`    — validate node payloads and write immutable raw observations
* :mod:`swelter.qc`        — range/spike/flatline checks, gap detection, node health
* :mod:`swelter.calibrate` — co-location fit, the versioned correction registry, error bars
* :mod:`swelter.aggregate` — gridded heat-island and AQI surfaces
* :mod:`swelter.export` / :mod:`swelter.api` — CSV/JSON and the OGC SensorThings subset
* :mod:`swelter.store`     — the pluggable, Datasette-openable time-series store

Everything is importable and corpus-agnostic, so the calibration and QC layers are reusable
outside this CLI.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from .config import NetworkConfig, load_config, snap_to_grid
from .models import PARAMETERS, Observation, heat_index_c, pm25_aqi, wbgt_c

try:
    # Single source of truth: `pyproject.toml`'s `[project] version`, read back from the
    # installed package's metadata rather than hand-duplicated here (REL-02).
    __version__ = version("swelter")
except PackageNotFoundError:  # pragma: no cover -- only when running from source, uninstalled
    __version__ = "0.0.0+unknown"

__all__ = [
    "PARAMETERS",
    "NetworkConfig",
    "Observation",
    "__version__",
    "heat_index_c",
    "load_config",
    "pm25_aqi",
    "snap_to_grid",
    "wbgt_c",
]
