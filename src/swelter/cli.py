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
    health = qc.node_health(raw, latest, offline_after_s=args.interval * 3)
    _err(f"swelter: {len(health)} nodes, {len(gaps)} gaps over interval {int(args.interval)}s")
    for node in health:
        status = "online" if node.online else "OFFLINE"
        _err(
            f"  {node.node_id:>10}  {status:<7}  {node.observations:>6} obs  "
            f"{node.flagged_fraction * 100:5.1f}% flagged  last {node.last_seen}"
        )
    return 0


def cmd_calibrate(args: argparse.Namespace) -> int:
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

    p_qc = sub.add_parser("qc", help="report node health and data gaps")
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
