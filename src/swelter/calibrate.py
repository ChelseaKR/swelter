"""The calibration engine: co-location fit, a versioned correction registry, honest error bars.

A low-cost PM sensor can read double the true concentration on a humid morning, and a sensor
baking in a black enclosure reports the box's temperature, not the air's. A network that
ignores this draws a map that is precise and wrong. swelter treats calibration as the core
feature.

The method is intentionally plain and inspectable — ordinary least squares, in pure Python,
no opaque library:

* **Co-location fit.** A node sits beside a reference-grade monitor for a training window.
  ``fit`` regresses the node's raw readings onto the reference values. For PM it fits a
  humidity-aware correction (``corrected = a·raw + b·humidity + c``) in the lineage of the
  US-EPA PurpleAir model; for temperature it fits an enclosure-offset (``corrected = a·raw +
  c``). It records the window, the reference source, the fitted coefficients, the residual
  standard deviation, and R².
* **Versioned registry.** Corrections are *data*, not code — a YAML registry keyed by node and
  parameter, each entry naming the version that produced it. Recalibrating a node is a data
  change with a diff and an audit trail.
* **Honest error bars.** Every calibrated value carries the residual standard deviation as its
  1-σ uncertainty. A node with no correction stays raw, and the map shows it as provisional.
* **Reproducible.** Coefficients are rounded to a fixed precision, so re-running ``fit`` on the
  committed co-location data reproduces the published registry byte-for-byte. Anyone can check
  the calibration instead of trusting it.
* **Sensor-model-aware families.** A node's optional ``sensor_model`` (public hardware family,
  e.g. "PMS5003", "SDS011", "SPS30") selects a ``(parameter, model)`` correction family when one
  is known — falling back to the per-parameter default for a node with no model or an
  unrecognized one, so this never changes the fit for the demo network. Still fit only from that
  node's own co-location evidence: a model changes which regression form is fit, never whether a
  node has a correction, and never promotes a node past raw/provisional on its own (see
  ``docs/calibration.md`` "Per-model bias").
* **Heat index derived, not fitted.** There is no field reference for heat index to co-locate
  against, so it is never fit. Instead, ``apply`` recomputes it from a node's *already-calibrated*
  temperature plus co-timed humidity, using the same NWS Rothfusz function the demo generator uses.
  It is calibrated exactly where temperature is, and stays raw/provisional everywhere else — see
  ADR 0014 and the "Heat index: derived, not fitted" section of ``calibration.md``.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .models import QC_REJECTED, RAW, Observation
from .models import heat_index_c as _heat_index_c

#: Decimal places coefficients/metrics are rounded to. Fixed precision is what makes the
#: fitted registry reproducible byte-for-byte across machines and runs.
PRECISION = 6


def _round(value: float) -> float:
    """Round to PRECISION and collapse -0.0 to 0.0 so the registry stays byte-for-byte stable.

    The sign of a coefficient that lands at the floating-point noise floor depends on the order
    of operations during elimination; without this, a re-fit on another machine could emit
    ``-0.0`` where the committed file has ``0.0`` and fail the reproducibility replay.
    """
    return round(value, PRECISION) + 0.0


# Which predictors each parameter regresses on (the intercept is always added). PM is
# humidity-aware; everything else is a simple linear/offset correction.
_PREDICTORS: dict[str, tuple[str, ...]] = {
    "pm25_ugm3": ("raw", "humidity"),
    "pm10_ugm3": ("raw", "humidity"),
}
_DEFAULT_PREDICTORS: tuple[str, ...] = ("raw",)

_METHOD: dict[str, str] = {
    "pm25_ugm3": "epa-humidity",
    "pm10_ugm3": "epa-humidity",
    "temp_c": "enclosure-offset",
}
_DEFAULT_METHOD = "linear"

# Sensor-model-aware families: known PM sensor hardware has different humidity responses, so a
# node whose model is known (``NodeConfig.sensor_model``) gets a family-specific predictor set
# and/or method label instead of the per-parameter default. Keyed by (parameter, model); a
# (parameter, model) pair absent here falls back to `_PREDICTORS`/`_METHOD` by parameter, then to
# the defaults above — so a node with no model, or an unrecognized one, fits exactly as before.
# This is *never* a change to the raw/calibrated boundary (hard rule #3): a model-aware correction
# is still fit from that node's own co-location data; the model only picks which regression form
# to fit. See docs/calibration.md "Per-model bias" for the documented rationale per family.
#
# - PMS5003 / SDS011 (no onboard humidity compensation): the same humidity-aware EPA-PurpleAir-
#   lineage predictor set as the per-parameter default, but recorded under a model-specific method
#   id so the registry and version id trace which family's bias the fit corrected.
# - SPS30 (Sensirion firmware applies its own onboard RH compensation before the reading ever
#   reaches swelter): the residual humidity dependence left to fit is small enough that a plain
#   linear correction (no humidity term) is the appropriate family — an extra humidity predictor
#   here would just add noise to an already-compensated signal.
_MODEL_PREDICTORS: dict[tuple[str, str], tuple[str, ...]] = {
    ("pm25_ugm3", "SPS30"): ("raw",),
    ("pm10_ugm3", "SPS30"): ("raw",),
}
_MODEL_METHOD: dict[tuple[str, str], str] = {
    ("pm25_ugm3", "PMS5003"): "epa-humidity-pms5003",
    ("pm10_ugm3", "PMS5003"): "epa-humidity-pms5003",
    ("pm25_ugm3", "SDS011"): "epa-humidity-sds011",
    ("pm10_ugm3", "SDS011"): "epa-humidity-sds011",
    ("pm25_ugm3", "SPS30"): "linear-onboard-rh-sps30",
    ("pm10_ugm3", "SPS30"): "linear-onboard-rh-sps30",
}

#: Method id for a heat-index observation derived from a node's calibrated temperature plus
#: co-timed humidity, rather than fit against a reference — there is no field heat-index
#: reference to co-locate against (see ADR 0014). Kept out of `_METHOD` above because that map
#: names methods a co-location *fit* can produce; heat index is never fit.
_DERIVED_HEAT_INDEX_METHOD = "derived-enclosure"


@dataclass(frozen=True)
class TrainingPair:
    """One co-located measurement: the node's raw value against the reference's true value."""

    node_id: str
    parameter: str
    timestamp: str
    raw: float
    reference: float
    humidity: float | None = None


@dataclass(frozen=True)
class Correction:
    """A fitted per-node, per-parameter correction and its provenance."""

    version: str
    node_id: str
    parameter: str
    method: str
    predictors: tuple[str, ...]
    coefficients: tuple[float, ...]  # one per predictor, then the intercept
    intercept: float
    residual_std: float
    r2: float
    n: int
    reference: str
    window_start: str
    window_end: str
    #: The sensor hardware family this correction was fit for, e.g. "PMS5003", "SDS011", "SPS30" —
    #: empty when the node's model is unknown/unspecified, in which case the correction used the
    #: per-parameter default family. Never changes the raw/calibrated boundary; it is provenance,
    #: not a promotion (see docs/calibration.md "Per-model bias").
    model: str = ""

    def predict(self, raw: float, humidity: float | None) -> float:
        total = self.intercept
        for name, coef in zip(self.predictors, self.coefficients, strict=True):
            if name == "raw":
                total += coef * raw
            elif name == "humidity":
                total += coef * (humidity if humidity is not None else 0.0)
        return round(total, PRECISION)


def predictors_for(parameter: str, model: str | None = None) -> tuple[str, ...]:
    """The predictor set for ``parameter``, preferring a (parameter, model) family when known.

    Falls back to the per-parameter default, then to ``_DEFAULT_PREDICTORS``, so a node with no
    model or an unrecognized one fits exactly as it did before model-awareness existed.
    """
    if model:
        found = _MODEL_PREDICTORS.get((parameter, model))
        if found is not None:
            return found
    return _PREDICTORS.get(parameter, _DEFAULT_PREDICTORS)


def _method_for(parameter: str, model: str | None) -> str:
    """The method id for ``parameter``, preferring a (parameter, model) family when known.

    Same fallback order as :func:`predictors_for`: (parameter, model) → parameter → default.
    """
    if model:
        found = _MODEL_METHOD.get((parameter, model))
        if found is not None:
            return found
    return _METHOD.get(parameter, _DEFAULT_METHOD)


def _design_row(pair: TrainingPair, predictors: tuple[str, ...]) -> list[float]:
    row: list[float] = []
    for name in predictors:
        if name == "raw":
            row.append(pair.raw)
        elif name == "humidity":
            row.append(pair.humidity if pair.humidity is not None else 0.0)
    row.append(1.0)  # intercept
    return row


def _solve(matrix: list[list[float]], rhs: list[float]) -> list[float]:
    """Solve a small linear system by Gaussian elimination with partial pivoting."""
    n = len(rhs)
    a = [row[:] + [rhs[i]] for i, row in enumerate(matrix)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(a[r][col]))
        if abs(a[pivot][col]) < 1e-12:
            raise ValueError("singular system: co-location data has no variation to fit")
        a[col], a[pivot] = a[pivot], a[col]
        pivot_val = a[col][col]
        for r in range(n):
            if r == col:
                continue
            factor = a[r][col] / pivot_val
            for c in range(col, n + 1):
                a[r][c] -= factor * a[col][c]
    return [a[i][n] / a[i][i] for i in range(n)]


def _ols(design: list[list[float]], targets: list[float]) -> list[float]:
    """Ordinary least squares via the normal equations ``(XᵀX)β = Xᵀy``."""
    cols = len(design[0])
    xtx = [[0.0] * cols for _ in range(cols)]
    xty = [0.0] * cols
    for row, y in zip(design, targets, strict=True):
        for i in range(cols):
            xty[i] += row[i] * y
            for j in range(cols):
                xtx[i][j] += row[i] * row[j]
    return _solve(xtx, xty)


def fit_one(
    node_id: str,
    parameter: str,
    pairs: list[TrainingPair],
    reference: str,
    model: str = "",
) -> Correction:
    """Fit a single node/parameter correction from its co-location pairs.

    ``model`` is the node's sensor hardware family (``NodeConfig.sensor_model``), if known. When
    given, it selects a (parameter, model) predictor set and method label if one is registered
    (see ``_MODEL_PREDICTORS``/``_MODEL_METHOD``); otherwise the fit falls back to the
    per-parameter default exactly as before model-awareness existed.
    """
    if len(pairs) < 3:
        raise ValueError(f"need at least 3 co-location pairs for {node_id}/{parameter}")
    pairs = sorted(pairs, key=lambda p: p.timestamp)
    predictors = predictors_for(parameter, model or None)
    design = [_design_row(p, predictors) for p in pairs]
    targets = [p.reference for p in pairs]
    beta = _ols(design, targets)
    coefficients = tuple(_round(b) for b in beta[:-1])
    intercept = _round(beta[-1])

    residuals = [
        p.reference - (intercept + sum(c * x for c, x in zip(coefficients, row[:-1], strict=True)))
        for p, row in zip(pairs, design, strict=True)
    ]
    n = len(pairs)
    mean_ref = sum(targets) / n
    ss_res = sum(r * r for r in residuals)
    ss_tot = sum((t - mean_ref) ** 2 for t in targets) or 1e-12
    residual_std = _round((ss_res / n) ** 0.5)
    r2 = _round(1 - ss_res / ss_tot)
    method = _method_for(parameter, model or None)

    return Correction(
        version=f"{parameter}.{method}.{node_id}",
        node_id=node_id,
        parameter=parameter,
        method=method,
        predictors=predictors,
        coefficients=coefficients,
        intercept=intercept,
        residual_std=residual_std,
        r2=r2,
        n=n,
        reference=reference,
        window_start=pairs[0].timestamp,
        window_end=pairs[-1].timestamp,
        model=model,
    )


class CorrectionRegistry:
    """The versioned set of fitted corrections, persisted as committed YAML."""

    def __init__(self, corrections: dict[str, Correction] | None = None) -> None:
        self._by_key: dict[str, Correction] = dict(corrections or {})

    @staticmethod
    def _key(node_id: str, parameter: str) -> str:
        return f"{node_id}:{parameter}"

    def add(self, correction: Correction) -> None:
        self._by_key[self._key(correction.node_id, correction.parameter)] = correction

    def get(self, node_id: str, parameter: str) -> Correction | None:
        return self._by_key.get(self._key(node_id, parameter))

    def all(self) -> list[Correction]:
        return [self._by_key[k] for k in sorted(self._by_key)]

    def __len__(self) -> int:
        return len(self._by_key)

    def to_dict(self) -> dict[str, Any]:
        corrections: list[dict[str, Any]] = []
        for c in self.all():
            entry: dict[str, Any] = {
                "version": c.version,
                "node_id": c.node_id,
                "parameter": c.parameter,
                "method": c.method,
                "predictors": list(c.predictors),
                "coefficients": list(c.coefficients),
                "intercept": c.intercept,
                "residual_std": c.residual_std,
                "r2": c.r2,
                "n": c.n,
                "reference": c.reference,
                "window_start": c.window_start,
                "window_end": c.window_end,
            }
            # Only serialized when non-empty, so a registry with no model-aware corrections (every
            # demo node) rebuilds byte-for-byte identical to the pre-model-awareness schema.
            if c.model:
                entry["model"] = c.model
            corrections.append(entry)
        return {"version": 1, "corrections": corrections}

    def to_yaml(self, path: str | Path) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(
            yaml.safe_dump(self.to_dict(), sort_keys=False, default_flow_style=False),
            encoding="utf-8",
        )

    @classmethod
    def from_dict(cls, doc: dict[str, Any]) -> CorrectionRegistry:
        registry = cls()
        for entry in doc.get("corrections", []) or []:
            registry.add(
                Correction(
                    version=str(entry["version"]),
                    node_id=str(entry["node_id"]),
                    parameter=str(entry["parameter"]),
                    method=str(entry.get("method", _DEFAULT_METHOD)),
                    predictors=tuple(entry.get("predictors", _DEFAULT_PREDICTORS)),
                    coefficients=tuple(float(c) for c in entry["coefficients"]),
                    intercept=float(entry["intercept"]),
                    residual_std=float(entry["residual_std"]),
                    r2=float(entry["r2"]),
                    n=int(entry["n"]),
                    reference=str(entry.get("reference", "")),
                    window_start=str(entry.get("window_start", "")),
                    window_end=str(entry.get("window_end", "")),
                    model=str(entry.get("model", "")),
                )
            )
        return registry

    @classmethod
    def from_yaml(cls, path: str | Path) -> CorrectionRegistry:
        doc: Any = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(doc if isinstance(doc, dict) else {})


def fit(pairs: Iterable[TrainingPair], models: dict[str, str] | None = None) -> CorrectionRegistry:
    """Fit every node/parameter that has co-location data into a registry.

    ``models`` maps node_id → sensor hardware family (``NodeConfig.sensor_model``), typically built
    from a loaded ``NetworkConfig``. Omitted or empty (the default), every node fits the
    per-parameter default family exactly as it did before model-awareness existed — this is what
    keeps the committed demo registry reproducible byte-for-byte, since none of its nodes carry a
    ``sensor_model``.
    """
    models = models or {}
    grouped: dict[tuple[str, str], list[TrainingPair]] = defaultdict(list)
    references: dict[tuple[str, str], str] = {}
    for pair in pairs:
        grouped[(pair.node_id, pair.parameter)].append(pair)
    registry = CorrectionRegistry()
    for (node_id, parameter), group in sorted(grouped.items()):
        reference = references.get((node_id, parameter), "reference-monitor")
        model = models.get(node_id, "")
        try:
            registry.add(fit_one(node_id, parameter, group, reference, model=model))
        except ValueError as exc:
            # A singular / no-variation co-location group (e.g. constant or absent humidity)
            # cannot be fit. Skip it — that node/parameter stays raw/provisional — rather than
            # aborting the whole network's calibration on one bad group.
            print(f"swelter: skipping {parameter}/{node_id}: {exc}", file=sys.stderr)
    return registry


def read_colocation(path: str | Path) -> list[TrainingPair]:
    """Load co-location training pairs from a JSONL file.

    Each line is ``{"node_id", "parameter", "timestamp", "raw", "reference"[, "humidity"]}``.
    This is the recorded evidence a calibration is fit from; committing it is what makes the
    fit reproducible and auditable by anyone.
    """
    pairs: list[TrainingPair] = []
    for row in _read_jsonl(path):
        humidity = row.get("humidity")
        pairs.append(
            TrainingPair(
                node_id=str(row["node_id"]),
                parameter=str(row["parameter"]),
                timestamp=str(row["timestamp"]),
                raw=float(row["raw"]),
                reference=float(row["reference"]),
                humidity=None if humidity is None else float(humidity),
            )
        )
    return pairs


def _read_jsonl(path: str | Path) -> Iterator[dict[str, Any]]:
    with Path(path).open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    yield obj


def humidity_index(observations: Iterable[Observation]) -> dict[tuple[str, str], float]:
    """Map (node_id, timestamp) → humidity for the PM correction's humidity term.

    Only RAW, QC-passing humidity readings count: a range/spike/flatline humidity must never
    feed a calibration (a 999% reading would wildly skew the correction). The canonical store is
    deduped by key; if a caller passes a non-deduped stream, the last reading for a key wins.
    """
    return {
        (o.node_id, o.timestamp): o.value
        for o in observations
        if o.parameter == "humidity_pct" and o.calibration == RAW and o.qc not in QC_REJECTED
    }


def apply(observations: Iterable[Observation], registry: CorrectionRegistry) -> list[Observation]:
    """Produce calibrated observations for every raw reading that has a correction.

    Raw readings are passed through unchanged (so the immutable record stays intact); for each
    raw reading with a registered correction, an additional calibrated observation is emitted,
    tagged with the correction version and carrying its uncertainty. A node with no correction
    yields only raw observations, which the map renders as provisional.

    Heat index is a second pass, not a registered correction: there is no field heat-index
    reference to co-locate against, so `heat_index_c` is never fit (ADR 0014). Instead, once the
    first pass above has produced every calibrated `temp_c` this call will produce, a raw
    `heat_index_c` observation whose (node_id, timestamp) has *both* a calibrated temperature and
    co-timed humidity is recomputed from those calibrated inputs with `models.heat_index_c` and
    emitted as an additional, calibrated observation. A node whose temperature stayed raw, or
    whose humidity at that instant is missing/QC-rejected, gets no derived heat index — it stays
    raw/provisional, honestly, rather than being promoted on an uncalibrated input.
    """
    observations = list(observations)
    humidity = humidity_index(observations)
    calibrated_temp: dict[tuple[str, str], tuple[float, float]] = {}
    out: list[Observation] = []
    for obs in observations:
        out.append(obs)
        if obs.calibration != RAW:
            continue
        correction = registry.get(obs.node_id, obs.parameter)
        if correction is None:
            continue
        rh = humidity.get((obs.node_id, obs.timestamp))
        if "humidity" in correction.predictors and rh is None:
            # A humidity-aware PM correction without co-timed humidity would silently zero the
            # humidity term and publish a badly-wrong value as trustworthy. Leave it raw.
            continue
        corrected_value = correction.predict(obs.value, rh)
        out.append(obs.calibrated(correction.version, corrected_value, correction.residual_std))
        if obs.parameter == "temp_c":
            calibrated_temp[(obs.node_id, obs.timestamp)] = (
                corrected_value,
                correction.residual_std,
            )

    # Second pass: derive heat index from calibrated temp + co-timed humidity. This runs after
    # the loop above so every calibrated temp_c this call can produce is already indexed —
    # a raw heat_index_c earlier in the stream than its node's calibrated temp_c must still see it.
    for obs in observations:
        if obs.parameter != "heat_index_c" or obs.calibration != RAW:
            continue
        temp = calibrated_temp.get((obs.node_id, obs.timestamp))
        rh = humidity.get((obs.node_id, obs.timestamp))
        if temp is None or rh is None:
            continue
        temp_value, temp_residual_std = temp
        derived_value = _heat_index_c(temp_value, rh)
        version = f"heat_index_c.{_DERIVED_HEAT_INDEX_METHOD}.{obs.node_id}"
        # Heat index is monotonic in temperature over the operating range; carrying the temp
        # correction's residual_std forward as the derived value's 1-sigma is the simplest
        # defensible propagation (see ADR 0014) rather than a fitted uncertainty of its own.
        out.append(obs.calibrated(version, derived_value, temp_residual_std))
    return out
