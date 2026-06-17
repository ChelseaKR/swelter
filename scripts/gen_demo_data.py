#!/usr/bin/env python3
"""Generate the committed demo dataset: a recorded week of synthetic sensor readings.

Deterministic by construction — a fixed seed, sorted iteration, rounded values — so the
committed ``data/demo/*.jsonl`` and ``network.yaml`` are reproducible byte-for-byte and the
calibration-replay test can reproduce the published corrections. There is no hardware and no
clock in the loop: ``make demo`` replays whatever this writes.

The synthetic field has the biases real low-cost sensors have, on purpose, so calibration has
something true to recover:

* PM optical counts inflate with humidity and carry a per-node offset.
* Temperature reads high in sun because the enclosure heats (a per-node offset).
* Twelve nodes have a co-location record against a reference monitor (they calibrate); six do
  not (they stay raw-flagged) — matching the README's "12 calibrated, 6 raw-flagged".
* A node goes offline (the longest gap), one PM reading spikes out of range, and one humidity
  sensor flatlines, so QC has something to catch.

Run: ``uv run python scripts/gen_demo_data.py``
"""

from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DEMO = ROOT / "data" / "demo"
SEED = 20260601
START = datetime(2026, 6, 1, 0, 0, 0, tzinfo=UTC)
HOURS = 385  # 2026-06-01T00 .. 2026-06-17T00 inclusive
TRAINING_HOURS = 72  # first three days are the co-location window
N_NODES = 18
N_CALIBRATED = 12

# A fictional downtown grid (Sacramento-ish, to sit beside the portfolio's regional work).
CENTER_LAT = 38.5816
CENTER_LON = -121.4944


@dataclass
class Node:
    node_id: str
    lat: float
    lon: float
    canopy: float  # 0 bare .. 1 shaded; less canopy ⇒ hotter (heat island)
    enclosure_offset: float  # °C the raw temp reads high in full sun
    pm_offset: float  # additive raw PM bias
    pm_humidity_gain: float  # fractional PM inflation per unit relative humidity
    humidity_bias: float
    calibrated: bool


def build_nodes(rng: random.Random) -> list[Node]:
    nodes: list[Node] = []
    for i in range(N_NODES):
        node_id = f"node-{i + 1:02d}"
        # Lay nodes on a rough 6×3 grid spanning ~2 km.
        col, row = i % 6, i // 6
        lat = round(CENTER_LAT + (row - 1) * 0.006 + rng.uniform(-0.001, 0.001), 6)
        lon = round(CENTER_LON + (col - 2.5) * 0.006 + rng.uniform(-0.001, 0.001), 6)
        nodes.append(
            Node(
                node_id=node_id,
                lat=lat,
                lon=lon,
                canopy=round(rng.uniform(0.05, 0.9), 3),
                enclosure_offset=round(rng.uniform(1.2, 3.6), 3),
                pm_offset=round(rng.uniform(-1.5, 4.0), 3),
                pm_humidity_gain=round(rng.uniform(0.25, 0.8), 3),
                humidity_bias=round(rng.uniform(-3.0, 3.0), 3),
                calibrated=i < N_CALIBRATED,
            )
        )
    return nodes


def true_field(t: datetime, node: Node) -> tuple[float, float, float, float]:
    """Return the *true* (temp_c, humidity_pct, pm25, pm10) at a node and time."""
    h = t.hour + t.minute / 60.0
    day = (t - START).days
    diurnal = math.sin(2 * math.pi * (h - 9) / 24)  # peak mid-afternoon
    heat_wave = 0.35 * day  # a slow June warming ramp
    urban = 3.2 * (1 - node.canopy)  # heat island where canopy is thin
    temp = 27.0 + 7.5 * diurnal + heat_wave + urban
    humidity = max(12.0, min(96.0, 68.0 - 1.6 * (temp - 27.0)))

    rush = max(0.0, math.sin(2 * math.pi * (h - 7) / 24)) + max(
        0.0, math.sin(2 * math.pi * (h - 18) / 24)
    )
    smoke = 32.0 if 6 <= day <= 8 else 0.0  # a wildfire-smoke episode mid-window
    pm25 = 7.0 + 6.0 * rush + 0.4 * urban + smoke
    pm10 = pm25 * 1.7 + 4.0
    return temp, humidity, pm25, pm10


def raw_readings(
    t: datetime, node: Node, rng: random.Random
) -> tuple[float, float, float, float, float]:
    """The node's *biased, noisy* readings (temp, humidity, pm25, pm10, heat_index)."""
    temp, humidity, pm25, pm10 = true_field(t, node)
    h = t.hour
    sun = max(0.0, math.sin(2 * math.pi * (h - 12) / 24))

    temp_raw = temp + node.enclosure_offset * sun + rng.gauss(0, 0.3)
    humidity_raw = max(0.0, min(100.0, humidity + node.humidity_bias + rng.gauss(0, 1.0)))
    inflation = 1 + node.pm_humidity_gain * (humidity_raw / 100.0)
    pm25_raw = max(0.0, pm25 * inflation + node.pm_offset + rng.gauss(0, 1.5))
    pm10_raw = max(0.0, pm10 * inflation + node.pm_offset + rng.gauss(0, 2.5))
    hi_raw = heat_index_c(temp_raw, humidity_raw)
    return (
        round(temp_raw, 2),
        round(humidity_raw, 2),
        round(pm25_raw, 2),
        round(pm10_raw, 2),
        hi_raw,
    )


def heat_index_c(temp_c: float, humidity_pct: float) -> float:
    if temp_c < 26.7:
        return round(temp_c, 2)
    t = temp_c * 9 / 5 + 32
    r = humidity_pct
    hi = (
        -42.379
        + 2.04901523 * t
        + 10.14333127 * r
        - 0.22475541 * t * r
        - 0.00683783 * t * t
        - 0.05481717 * r * r
        + 0.00122874 * t * t * r
        + 0.00085282 * t * r * r
        - 0.00000199 * t * t * r * r
    )
    return round((hi - 32) * 5 / 9, 2)


def generate() -> None:
    rng = random.Random(SEED)
    nodes = build_nodes(rng)
    timestamps = [START + timedelta(hours=i) for i in range(HOURS)]

    # node-07 drops offline for a stretch — the longest gap in the export banner.
    offline = {
        nodes[6].node_id: {
            START + timedelta(hours=i)
            for i in range(216, 268)  # ~2 days mid-window
        }
    }

    DEMO.mkdir(parents=True, exist_ok=True)
    obs_lines: list[str] = []
    colo_lines: list[str] = []

    for t in timestamps:
        iso = t.strftime("%Y-%m-%dT%H:%M:%SZ")
        for node in nodes:
            if iso_in(offline.get(node.node_id), t):
                continue
            temp_raw, hum_raw, pm25_raw, pm10_raw, hi_raw = raw_readings(t, node, rng)

            # Inject a couple of QC-catchable faults into the observation stream.
            if node.node_id == "node-04" and t == START + timedelta(hours=130):
                pm25_raw = 1500.0  # out-of-range spike
            if node.node_id == "node-15" and 50 <= (t - START) // timedelta(hours=1) < 58:
                hum_raw = 41.0  # a stuck (flatlined) humidity sensor

            obs_lines.append(
                json.dumps(
                    {
                        "node_id": node.node_id,
                        "timestamp": iso,
                        "temp_c": temp_raw,
                        "humidity_pct": hum_raw,
                        "pm25_ugm3": pm25_raw,
                        "pm10_ugm3": pm10_raw,
                        "heat_index_c": hi_raw,
                    },
                    separators=(",", ":"),
                )
            )

    # Co-location training records for the calibrated nodes (training window only).
    for t in timestamps[:TRAINING_HOURS]:
        iso = t.strftime("%Y-%m-%dT%H:%M:%SZ")
        for node in nodes:
            if not node.calibrated:
                continue
            temp, humidity, pm25, pm10 = true_field(t, node)
            temp_raw, hum_raw, pm25_raw, pm10_raw, _ = raw_readings(t, node, rng)
            for parameter, raw, ref in (
                ("temp_c", temp_raw, round(temp + rng.gauss(0, 0.1), 2)),
                ("pm25_ugm3", pm25_raw, round(pm25 + rng.gauss(0, 0.4), 2)),
                ("pm10_ugm3", pm10_raw, round(pm10 + rng.gauss(0, 0.6), 2)),
            ):
                colo_lines.append(
                    json.dumps(
                        {
                            "node_id": node.node_id,
                            "parameter": parameter,
                            "timestamp": iso,
                            "raw": raw,
                            "reference": ref,
                            "humidity": hum_raw,
                        },
                        separators=(",", ":"),
                    )
                )

    (DEMO / "observations.jsonl").write_text("\n".join(obs_lines) + "\n", encoding="utf-8")
    (DEMO / "colocation.jsonl").write_text("\n".join(colo_lines) + "\n", encoding="utf-8")
    write_network_yaml(nodes)
    print(
        f"wrote {len(obs_lines)} observation payloads, {len(colo_lines)} co-location pairs, "
        f"and network.yaml for {len(nodes)} nodes"
    )


def iso_in(window: set[datetime] | None, t: datetime) -> bool:
    return window is not None and t in window


def write_network_yaml(nodes: list[Node]) -> None:
    doc = {
        "name": "swelter demo network (downtown)",
        "grid_resolution_m": 150,
        "languages": ["en", "es"],
        "reference_monitors": [
            {
                "monitor_id": "ref-aqs-0010",
                "label": "Regulatory AQS station (downtown)",
                "source": "US EPA AQS site 06-067-0010",
            }
        ],
        "nodes": [
            {
                "node_id": n.node_id,
                "label": f"Node {n.node_id[-2:]}",
                "lat": n.lat,
                "lon": n.lon,
                "location": "coarse",
            }
            for n in nodes
        ],
        "calibration_windows": [
            {
                "node_id": n.node_id,
                "reference": "ref-aqs-0010",
                "parameter": p,
                "start": "2026-06-01T00:00:00Z",
                "end": "2026-06-03T23:00:00Z",
            }
            for n in nodes
            if n.calibrated
            for p in ("temp_c", "pm25_ugm3", "pm10_ugm3")
        ],
    }
    (ROOT / "network.yaml").write_text(
        "# Generated by scripts/gen_demo_data.py — the worked example network.\n"
        "# A community stands up its own instance by editing a copy of this file.\n"
        + yaml.safe_dump(doc, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )


if __name__ == "__main__":
    generate()
