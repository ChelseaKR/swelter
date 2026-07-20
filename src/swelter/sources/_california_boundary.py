"""California jurisdiction test backed by a checked-in U.S. Census boundary.

The geometry is the U.S. Census Bureau TIGERweb States layer, January 1, 2025 vintage, simplified
to 0.0002 degrees (at most about 22 metres of latitude) for a small deterministic runtime asset.
It is a seven-part MultiPolygon, so coastal islands are represented instead of being approximated
by the statewide bounding box.
"""

from __future__ import annotations

import json
import math
from functools import lru_cache
from importlib.resources import (  # nosemgrep: python.lang.compatibility.python37.python37-compatibility-importlib2  # noqa: E501 (#107)
    files,
)

from ._geometry import MultiPolygon, contains_point, decode_multipolygon

# The inline Semgrep waiver is narrow: project metadata requires Python >=3.12, so a rule warning
# that importlib.resources cannot run on Python 3.6 does not apply to a supported installation.
SCOPE_ID = "US-CA:census-tigerweb-2025-01-01:0.0002deg"


@lru_cache(maxsize=1)
def _boundary() -> MultiPolygon:
    document: object = json.loads(
        files("swelter.sources").joinpath("california_boundary.geojson").read_text(encoding="utf-8")
    )
    if not isinstance(document, dict):
        raise ValueError("California boundary asset must be a GeoJSON Feature")
    return decode_multipolygon(document.get("geometry"))


def contains(lat: float, lon: float) -> bool:
    """Return whether a finite latitude/longitude lies in or on California's boundary."""
    if not math.isfinite(lat) or not math.isfinite(lon):
        return False
    return contains_point(_boundary(), lon, lat)
