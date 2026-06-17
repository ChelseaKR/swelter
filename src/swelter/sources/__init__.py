"""Real open-data sources swelter can ingest, as an alternative to the synthetic demo.

The synthetic generator (``scripts/gen_demo_data.py``) is the deterministic fixture the tests and
the calibration-reproducibility check need. These adapters instead pull *real* readings from open
data so the dashboard can show real conditions for real places. The pipeline downstream — QC,
aggregation, the map/table/list, the API, export — is identical; only the source of the
observations changes.
"""

from __future__ import annotations
