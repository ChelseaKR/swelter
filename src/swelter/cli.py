"""The ``swelter`` command line: ingest, qc, calibrate, aggregate, export, serve, demo, rebuild.

This is the one-command surface a neighbourhood collective actually touches. Every subcommand
is a thin wrapper over the library functions, so anything the CLI does is equally scriptable
and testable. ``swelter demo`` is the keystone: it replays the recorded week in ``data/demo``
through the whole pipeline — ingest → calibrate → aggregate → export — and optionally serves
the dashboard, with no hardware in the loop.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

import yaml

from . import __version__, aggregate, calibrate, export, ingest, qc
from .config import NetworkConfig, load_config
from .models import RAW
from .server import ServerContext, serve
from .store import SqliteStore, open_store, store_paths

DEFAULT_STORE = "store"
DEFAULT_CONFIG = "network.yaml"
DEFAULT_WEB = "web"
DEFAULT_DATA = "data/demo"
DEFAULT_INTERVAL_S = 3600.0


def _err(message: str) -> None:
    print(message, file=sys.stderr)


def _load_config(path: str) -> NetworkConfig:
    if Path(path).is_file():
        return load_config(path)
    _err(f"swelter: config {path} not found; using an empty network")
    return NetworkConfig()


# -- subcommands -------------------------------------------------------------


def cmd_ingest(args: argparse.Namespace) -> int:
    if not Path(args.input).is_file():
        _err(f"swelter: input {args.input} not found")
        return 1
    paths = store_paths(args.store)
    with open_store(args.store) as store:
        result = ingest.ingest_file(args.input, store, quarantine_path=paths["quarantine"])
    _err(
        f"swelter: ingested {result.accepted_payloads} payloads → "
        f"{result.observations_written} new observations "
        f"({result.duplicates} duplicates, {result.quarantined} quarantined)"
    )
    return 0


def cmd_qc(args: argparse.Namespace) -> int:
    with open_store(args.store) as store:
        raw = store.read(calibration=RAW)
    if not raw:
        _err("swelter: store is empty")
        return 0
    latest = max(o.timestamp for o in raw)
    gaps = qc.detect_gaps(raw, args.interval)
    health = qc.node_health(
        raw, latest, offline_after_s=args.interval * 3, expected_interval_s=args.interval
    )
    if args.json:
        payload = {
            "nodes": [
                {
                    "node_id": n.node_id,
                    "status": n.status,
                    "observations": n.observations,
                    "completeness": n.completeness,
                    "flagged_fraction": round(n.flagged_fraction, 3),
                    "online": n.online,
                    "last_seen": n.last_seen,
                }
                for n in health
            ],
            "gaps": [
                {
                    "node_id": g.node_id,
                    "parameter": g.parameter,
                    "start": g.start,
                    "end": g.end,
                    "minutes": round(g.seconds / 60),
                }
                for g in gaps
            ],
        }
        print(json.dumps(payload, indent=2))
        return 0
    not_ok = sum(1 for n in health if n.status != "ok")
    _err(
        f"swelter: {len(health)} nodes ({not_ok} degraded/offline), {len(gaps)} gaps "
        f"over interval {int(args.interval)}s"
    )
    for gap in gaps[:10]:
        _err(
            f"  gap  {gap.node_id}/{gap.parameter}  {gap.start} → {gap.end}  "
            f"({round(gap.seconds / 60)} min)"
        )
    for node in health:
        _err(
            f"  {node.node_id:>10}  {node.status.upper():<8}  {node.observations:>6} obs  "
            f"{node.completeness * 100:5.1f}% complete  {node.flagged_fraction * 100:5.1f}% flagged"
        )
    return 0


def cmd_calibrate(args: argparse.Namespace) -> int:
    if not Path(args.colocation).is_file():
        _err(f"swelter: colocation {args.colocation} not found")
        return 1
    pairs = calibrate.read_colocation(args.colocation)
    registry = calibrate.fit(pairs)
    paths = store_paths(args.store)
    registry.to_yaml(paths["registry"])
    _err(f"swelter: fit {len(registry)} corrections → {paths['registry']}")
    for c in registry.all():
        _err(f"  {c.version:<28} n={c.n:<4} R²={c.r2:.3f}  ±{c.residual_std} {c.parameter}")
    if not args.fit_only:
        with open_store(args.store) as store:
            raw = store.read(calibration=RAW)
            store.drop_calibrated()
            calibrated = [o for o in calibrate.apply(raw, registry) if o.calibration != RAW]
            written = store.write(calibrated)
        _err(f"swelter: applied corrections → {written.written} calibrated observations")
    return 0


def cmd_aggregate(args: argparse.Namespace) -> int:
    config = _load_config(args.config)
    with open_store(args.store) as store:
        surface = aggregate.aggregate(store.all(), config)
    out = Path(args.out or store_paths(args.store)["aggregate"])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(surface.snapshot_geojson(), indent=2), encoding="utf-8")
    _err(f"swelter: {len(surface.cells)} cell-hours → {out}")
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    with open_store(args.store) as store:
        observations = store.read(
            parameter=args.parameter, node_id=args.node, since=args.since, until=args.until
        )
        raw = store.read(calibration=RAW)
    gaps = qc.detect_gaps(raw, args.interval)
    if args.format == "json":
        sys.stdout.write(export.to_json(observations, indent=2))
    else:
        sys.stdout.write(export.to_csv(observations))
    _err(export.summarize(observations, gaps=gaps))
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    config = _load_config(args.config)
    store = open_store(args.store)
    base = f"http://{args.host}:{args.port}"
    ctx = ServerContext(store=store, config=config, web_dir=Path(args.web), base_url=base)
    _err(f"swelter: serving dashboard + API at {base}  (Ctrl-C to stop)")
    _err(f"  dashboard {base}/   ·   SensorThings {base}/v1.1   ·   export {base}/export.csv")
    try:
        serve(ctx, host=args.host, port=args.port)
    finally:
        store.close()
    return 0


def cmd_demo(args: argparse.Namespace) -> int:
    data = Path(args.data)
    config = _load_config(args.config)
    paths = store_paths(args.store)
    paths["db"].unlink(missing_ok=True)  # a fresh demo store every run; replay is idempotent

    with SqliteStore(paths["db"]) as store:
        result = ingest.ingest_file(
            data / "observations.jsonl", store, quarantine_path=paths["quarantine"]
        )
        _err(f"swelter demo: replayed {result.observations_seen} observations from recorded data")

        colocation = data / "colocation.jsonl"
        if colocation.is_file():
            registry = calibrate.fit(calibrate.read_colocation(colocation))
            registry.to_yaml(paths["registry"])
            raw = store.read(calibration=RAW)
            calibrated = [o for o in calibrate.apply(raw, registry) if o.calibration != RAW]
            store.write(calibrated)
            _err(
                f"swelter demo: fit {len(registry)} corrections, wrote {len(calibrated)} calibrated"
            )

        surface = aggregate.aggregate(store.all(), config)
        paths["aggregate"].write_text(
            json.dumps(surface.snapshot_geojson(), indent=2), encoding="utf-8"
        )
        _write_web_sample(
            Path(args.web),
            surface,
            attribution="Synthetic demonstration data — no real sensors (gen_demo_data.py).",
        )
        all_obs = list(store.all())
        gaps = qc.detect_gaps(store.read(calibration=RAW), args.interval)
        _err(export.summarize(all_obs, gaps=gaps))

    if args.serve:
        store = open_store(args.store)
        base = f"http://{args.host}:{args.port}"
        ctx = ServerContext(store=store, config=config, web_dir=Path(args.web), base_url=base)
        _err(f"swelter demo: serving at {base}  (Ctrl-C to stop)")
        try:
            serve(ctx, host=args.host, port=args.port)
        finally:
            store.close()
    return 0


def _write_web_sample(
    web_dir: Path, surface: aggregate.Surface, *, attribution: str = "", max_cells: int = 4000
) -> None:
    """Refresh the dashboard's offline fallback if web/ exists, capped to keep the static payload
    light on a host like GitHub Pages — the most recent hourly buckets up to ~``max_cells`` cells,
    so a large network does not bloat the committed sample (the live API has the full history)."""
    if not web_dir.is_dir():
        return
    per_bucket: dict[str, int] = {}
    for cell in surface.cells:
        per_bucket[cell.bucket] = per_bucket.get(cell.bucket, 0) + 1
    chosen: list[str] = []
    total = 0
    for bucket in sorted(per_bucket, reverse=True):  # newest first
        if chosen and total + per_bucket[bucket] > max_cells:
            break
        chosen.append(bucket)
        total += per_bucket[bucket]
    keep = set(chosen)
    buckets = sorted(keep)
    records = [c.as_record() for c in surface.cells if c.bucket in keep]
    payload = {
        "interval": surface.interval,
        "attribution": attribution,
        "buckets": buckets,
        "cells": records,
    }
    (web_dir / "sample-surface.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


def cmd_fetch(args: argparse.Namespace) -> int:
    """Fetch REAL readings from Open-Meteo (Copernicus CAMS + weather) for real neighborhoods,
    build the surface and the dashboard sample, and optionally serve. No API key, no hardware —
    real current data, attributed to its source, not swelter-calibrated."""
    from .sources import openmeteo

    places = openmeteo.SACRAMENTO
    _err(
        f"swelter: fetching real readings for {len(places)} Sacramento neighborhoods "
        "from Open-Meteo (Copernicus CAMS air quality + weather)…"
    )
    try:
        observations = openmeteo.fetch(
            places, past_days=args.past_days, forecast_days=args.forecast_days
        )
    except OSError as exc:
        _err(f"swelter: fetch failed ({exc}); check your network connection")
        return 1
    if not observations:
        _err("swelter: no readings returned")
        return 1
    observations = qc.apply(observations)

    Path(args.config).write_text(
        yaml.safe_dump(openmeteo.network_doc(places), sort_keys=False), encoding="utf-8"
    )
    config = load_config(args.config)

    paths = store_paths(args.store)
    paths["db"].unlink(missing_ok=True)  # a fresh snapshot each fetch; re-running is idempotent
    with SqliteStore(paths["db"]) as store:
        written = store.write(observations)
        surface = aggregate.aggregate(store.all(), config)
        paths["aggregate"].write_text(
            json.dumps(surface.snapshot_geojson(), indent=2), encoding="utf-8"
        )
        _write_web_sample(
            Path(args.web),
            surface,
            attribution=(
                "Real hourly readings for Sacramento neighborhoods from the Copernicus "
                "Atmosphere Monitoring Service (CAMS) via Open-Meteo — atmospheric model data, "
                "not physical sensors, and not swelter-calibrated."
            ),
        )
        all_obs = list(store.all())
        _err(
            f"swelter: stored {written.written} real observations from {len(config.nodes)} "
            "neighborhoods (source: Copernicus CAMS via Open-Meteo)"
        )
        _err(export.summarize(all_obs, gaps=qc.detect_gaps(all_obs, args.interval)))

    if args.serve:
        store = open_store(args.store)
        base = f"http://{args.host}:{args.port}"
        ctx = ServerContext(store=store, config=config, web_dir=Path(args.web), base_url=base)
        _err(f"swelter: serving REAL Sacramento data at {base}  (Ctrl-C to stop)")
        try:
            serve(ctx, host=args.host, port=args.port)
        finally:
            store.close()
    return 0


def cmd_rebuild(args: argparse.Namespace) -> int:
    config = _load_config(args.config)
    paths = store_paths(args.store)
    with open_store(args.store) as store:
        dropped = store.drop_calibrated()
        raw = store.read(calibration=RAW)
        if paths["registry"].is_file():
            registry = calibrate.CorrectionRegistry.from_yaml(paths["registry"])
            calibrated = [o for o in calibrate.apply(raw, registry) if o.calibration != RAW]
            store.write(calibrated)
            _err(f"swelter: dropped {dropped} derived rows, rebuilt {len(calibrated)} from raw")
        else:
            _err(f"swelter: dropped {dropped} derived rows; no registry to reapply")
        surface = aggregate.aggregate(store.all(), config)
    paths["aggregate"].write_text(
        json.dumps(surface.snapshot_geojson(), indent=2), encoding="utf-8"
    )
    _err(f"swelter: rebuilt surface ({len(surface.cells)} cell-hours)")
    return 0


def cmd_version(_: argparse.Namespace) -> int:
    print(f"swelter {__version__}")
    return 0


# -- parser ------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="swelter",
        description="Community heat and air-quality sensing network with open, calibrated data.",
    )
    parser.add_argument("--version", action="version", version=f"swelter {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_store(p: argparse.ArgumentParser) -> None:
        p.add_argument("--store", default=DEFAULT_STORE, help="store directory")

    def add_config(p: argparse.ArgumentParser) -> None:
        p.add_argument("--config", default=DEFAULT_CONFIG, help="network.yaml path")

    def add_interval(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--interval", type=float, default=DEFAULT_INTERVAL_S, help="sampling interval, seconds"
        )

    p_ingest = sub.add_parser("ingest", help="ingest a JSONL file of node payloads")
    p_ingest.add_argument("input", help="JSONL file of node payloads")
    add_store(p_ingest)
    p_ingest.set_defaults(func=cmd_ingest)

    p_qc = sub.add_parser("qc", help="report node health, completeness, and data gaps")
    p_qc.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    add_store(p_qc)
    add_interval(p_qc)
    p_qc.set_defaults(func=cmd_qc)

    p_cal = sub.add_parser("calibrate", help="fit corrections from co-location data and apply them")
    p_cal.add_argument("--colocation", default=f"{DEFAULT_DATA}/colocation.jsonl")
    p_cal.add_argument(
        "--fit-only", action="store_true", help="fit and write registry, do not apply"
    )
    add_store(p_cal)
    p_cal.set_defaults(func=cmd_calibrate)

    p_agg = sub.add_parser("aggregate", help="build the gridded heat/AQI surface")
    p_agg.add_argument("--out", default="", help="GeoJSON output path")
    add_store(p_agg)
    add_config(p_agg)
    p_agg.set_defaults(func=cmd_aggregate)

    p_exp = sub.add_parser("export", help="export observations as CSV or JSON to stdout")
    p_exp.add_argument("--format", choices=("csv", "json"), default="csv")
    p_exp.add_argument("--since", default=None)
    p_exp.add_argument("--until", default=None)
    p_exp.add_argument("--node", default=None)
    p_exp.add_argument("--parameter", default=None)
    p_exp.add_argument("--bbox", default=None, help="named area (reserved; see docs/api.md)")
    add_store(p_exp)
    add_interval(p_exp)
    p_exp.set_defaults(func=cmd_export)

    p_serve = sub.add_parser("serve", help="serve the dashboard, API, and exports (read-only)")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8000)
    p_serve.add_argument("--web", default=DEFAULT_WEB)
    add_store(p_serve)
    add_config(p_serve)
    p_serve.set_defaults(func=cmd_serve)

    p_demo = sub.add_parser("demo", help="replay recorded data through the whole pipeline")
    p_demo.add_argument("--data", default=DEFAULT_DATA)
    p_demo.add_argument("--store", default=f"{DEFAULT_STORE}/demo")
    p_demo.add_argument("--serve", action="store_true", help="serve the dashboard after replaying")
    p_demo.add_argument("--host", default="127.0.0.1")
    p_demo.add_argument("--port", type=int, default=8000)
    p_demo.add_argument("--web", default=DEFAULT_WEB)
    add_config(p_demo)
    add_interval(p_demo)
    p_demo.set_defaults(func=cmd_demo)

    p_fetch = sub.add_parser(
        "fetch",
        help="fetch REAL readings from Open-Meteo (Copernicus CAMS) and build the dashboard",
    )
    p_fetch.add_argument("--store", default=f"{DEFAULT_STORE}/real")
    p_fetch.add_argument("--config", default="network.real.yaml", help="where to write the network")
    p_fetch.add_argument("--web", default=DEFAULT_WEB)
    p_fetch.add_argument("--past-days", type=int, default=2)
    p_fetch.add_argument("--forecast-days", type=int, default=1)
    p_fetch.add_argument("--serve", action="store_true", help="serve the dashboard after fetching")
    p_fetch.add_argument("--host", default="127.0.0.1")
    p_fetch.add_argument("--port", type=int, default=8000)
    add_interval(p_fetch)
    p_fetch.set_defaults(func=cmd_fetch)

    p_rebuild = sub.add_parser("rebuild", help="rebuild calibrated + surface from immutable raw")
    add_store(p_rebuild)
    add_config(p_rebuild)
    p_rebuild.set_defaults(func=cmd_rebuild)

    p_version = sub.add_parser("version", help="print the swelter version")
    p_version.set_defaults(func=cmd_version)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    func = args.func
    result: int = func(args)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
