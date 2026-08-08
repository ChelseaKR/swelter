"""Shared fixtures: a throwaway store, an observation factory, and paths to the demo data."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from swelter.models import RAW, SOURCE_NATIVE, Observation
from swelter.store import SqliteStore

ROOT = Path(__file__).resolve().parents[1]
# Under mutmut the tests are copied into `mutants/`, so parents[1] lands on the
# sandbox rather than the repository. Only source and the selected tests are
# copied there, never `data/`, so committed fixtures have to be read from the
# real root or the mutation gate cannot run at all.
if ROOT.name == "mutants":
    ROOT = ROOT.parent
DEMO = ROOT / "data" / "demo"


@pytest.fixture
def store(tmp_path: Path) -> Iterator[SqliteStore]:
    db = SqliteStore(tmp_path / "obs.db")
    try:
        yield db
    finally:
        db.close()


def make_obs(
    *,
    node_id: str = "node-01",
    timestamp: str = "2026-06-01T00:00:00Z",
    parameter: str = "temp_c",
    value: float = 25.0,
    unit: str = "degC",
    source: str = SOURCE_NATIVE,
    calibration: str = RAW,
    qc: str = "ok",
    uncertainty: float | None = None,
) -> Observation:
    return Observation(
        node_id=node_id,
        timestamp=timestamp,
        parameter=parameter,
        value=value,
        unit=unit,
        source=source,
        calibration=calibration,
        qc=qc,
        uncertainty=uncertainty,
    )
