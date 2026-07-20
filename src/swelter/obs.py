"""Structured observability: JSON-lines pipeline event logs and per-run manifests.

Tier C (library/CLI) per ``docs/standards/OBSERVABILITY-STANDARD.md`` §3: OTel tracing and
metrics are out of scope for a local-only CLI (no network surface between services). What IS
in scope — and what this module provides — is the PII-in-logs gate that applies to *every*
repo that logs anything ("the one non-tiered control", §3) plus a lightweight run-manifest so
any published surface can name the pipeline run that built it.

Two things live here:

* :class:`JsonLinesFormatter`, a structlog-JSON-backed :class:`logging.Formatter` — one JSON object
  per line using the repository Tier-C schema: ``timestamp``, ``severity``, ``service.name``,
  ``service.version``, ``trace_id``, ``span_id``, ``message``, ``stage``, plus counter fields
  passes. Attach it via :func:`configure_json_logging`; nothing is emitted unless a caller
  opts in — the CLI's existing human-readable ``_err`` banners are unchanged.
* :class:`RunManifest` — an accumulator a pipeline invocation (``ingest`` → ``calibrate`` →
  ``aggregate``, or ``swelter demo``) fills in as it runs, and :func:`write_manifest`
  persists as ``run-manifest.json`` beside the store, so ``/api/health.json`` can name the
  run that built the currently-published surface.

Hard rule 1 (no person-shaped data, no IPs): everything this module writes is a count, a
timestamp, a run id, or a version string. :func:`_scrub` is a defensive last line, not the
first line of the guarantee — nothing here should ever be *handed* a name, an address, or a
network address to begin with.
"""

from __future__ import annotations

import json
import logging
import re
import sys
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

import structlog

from . import __version__

#: Field names never allowed into a log line or the manifest, even by accident. Substring
#: match, case-insensitive, so `ip`, `ip_address`, `client_ip`, `remote_addr` all match.
_FORBIDDEN_FIELD_SUBSTRINGS: Final = (
    "ip",
    "addr",
    "email",
    "e_mail",
    "phone",
    "name",
    "lat",
    "lon",
    "password",
    "token",
    "secret",
    "api_key",
    "ssn",
    "dob",
    "credit_card",
)

#: `node_id` is a device identifier, not a person — the schema-wide invariant models.py
#: documents ("no device id, no MAC, no owner ... that can hold a person"). It is exempted
#: from the substring scrub so pipeline events can still say *which* node without tripping
#: the (deliberately broad) "name"/"addr" match.
_ALLOWED_DESPITE_SUBSTRING: Final = frozenset({"node_id"})

LOGGER_NAME: Final = "swelter"

_ISO_FORMAT: Final = "%Y-%m-%dT%H:%M:%SZ"

_SENSITIVE_VALUE_PATTERNS: Final = (
    re.compile(r"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b"),
    re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
    # A coordinate pair embedded in a free-form diagnostic is sensitive even when the field is
    # named only ``detail`` or ``message``. Broad matching is intentional: a harmless numeric pair
    # is safer to hide than a resident's exact location is to retain.
    re.compile(r"(?<![\d.])[+-]?\d{1,2}(?:\.\d+)?\s*,\s*[+-]?\d{1,3}(?:\.\d+)?(?![\d.])"),
    re.compile(
        r"\b(?:bearer\s+|api[_-]?key[=: ]+|password[=: ]+|token[=: ]+)[^\s,;]+",
        re.IGNORECASE,
    ),
    re.compile(r"(?:[?&](?:token|key|secret|password)=)[^&#\s]+", re.IGNORECASE),
)

_JSON_RENDERER: Final = structlog.processors.JSONRenderer(sort_keys=True)


def _utcnow_iso() -> str:
    return datetime.now(UTC).strftime(_ISO_FORMAT)


def _scrub_value(value: Any) -> Any:
    """Redact common PII, coordinate, and credential shapes while preserving value types."""
    if isinstance(value, str):
        clean = value
        for pattern in _SENSITIVE_VALUE_PATTERNS:
            clean = pattern.sub("[REDACTED]", clean)
        return clean
    if isinstance(value, list):
        return [_scrub_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_scrub_value(item) for item in value)
    if isinstance(value, dict):
        return _scrub(value)
    return value


def _scrub(fields: dict[str, Any]) -> dict[str, Any]:
    """Drop unsafe field names and redact unsafe values (hard rule 1, defense-in-depth)."""
    clean: dict[str, Any] = {}
    for key, value in fields.items():
        lowered = key.lower()
        if key in _ALLOWED_DESPITE_SUBSTRING:
            clean[key] = _scrub_value(value)
            continue
        if any(bad in lowered for bad in _FORBIDDEN_FIELD_SUBSTRINGS):
            continue
        clean[key] = _scrub_value(value)
    return clean


class JsonLinesFormatter(logging.Formatter):
    """One JSON object per line using the committed Tier-C observability schema.

    Counter fields ride in on ``record.counters`` (a dict), set via the ``extra=`` kwarg of
    the stdlib logging call — never via ``%``-style message interpolation, so a structured
    field is always a real JSON value, never baked into a string.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).strftime(_ISO_FORMAT),
            "severity": record.levelname,
            "service.name": "swelter",
            "service.version": __version__,
            "trace_id": _scrub_value(getattr(record, "trace_id", None)),
            "span_id": _scrub_value(getattr(record, "span_id", None)),
            "stage": _scrub_value(getattr(record, "stage", None)),
            "message": _scrub_value(record.getMessage()),
        }
        counters = getattr(record, "counters", None)
        if counters:
            payload.update(_scrub(dict(counters)))
        return str(_JSON_RENDERER(None, record.levelname.lower(), payload))


def configure_json_logging(stream: Any = None, *, level: int = logging.INFO) -> logging.Logger:
    """Attach a JSON-lines handler to the ``swelter`` logger and return it.

    Idempotent: calling it more than once (e.g. once per CLI invocation in tests) does not
    stack duplicate handlers. Opt-in only — nothing calls this at import time.
    """
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(level)
    logger.propagate = False
    for handler in list(logger.handlers):
        if isinstance(handler, logging.StreamHandler) and isinstance(
            handler.formatter, JsonLinesFormatter
        ):
            logger.removeHandler(handler)
    handler = logging.StreamHandler(stream or sys.stderr)
    handler.setFormatter(JsonLinesFormatter())
    logger.addHandler(handler)
    return logger


def get_logger() -> logging.Logger:
    """The module logger, unconfigured (no handler) until :func:`configure_json_logging` runs."""
    return logging.getLogger(LOGGER_NAME)


def disable_json_logging() -> None:
    """Remove JSON handlers so captured/rotated stderr streams cannot leak across invocations."""
    logger = get_logger()
    for handler in list(logger.handlers):
        if isinstance(handler.formatter, JsonLinesFormatter):
            logger.removeHandler(handler)
            handler.close()


def log_event(stage: str, event: str, **counters: Any) -> None:
    """Emit one JSON-lines event on the ``swelter`` logger, if a handler is attached.

    A no-op (correct, cheap) when JSON logging was never opted into — ``logging`` swallows a
    call to a logger with no handlers attached (beyond the library's `lastResort` fallback),
    so callers do not need to guard every call site with an ``if logging enabled`` check.
    """
    get_logger().info(event, extra={"stage": stage, "counters": counters})


#: The counters a :class:`RunManifest` tracks, mirroring the pipeline stages named in
#: docs/standards/OBSERVABILITY-STANDARD.md's Tier-C wire-in: ingest → calibrate → aggregate.
_COUNTER_FIELDS: Final = (
    "payloads_accepted",
    "payloads_quarantined",
    "corrections_applied",
    "corrections_skipped_stale",
    "cells_built",
    "cells_provisional",
)


@dataclass
class RunManifest:
    """Per-pipeline-invocation accumulator: counters, a run id, and start/finish timestamps.

    One manifest covers one invocation of ``swelter ingest`` / ``calibrate`` / ``aggregate``
    (or all three via ``swelter demo``/``fetch``/``rebuild``) against one store directory.
    :meth:`record` both increments a counter and emits the matching JSON-lines event, so the
    manifest and the log stream never drift apart.
    """

    run_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    started_at: str = field(default_factory=_utcnow_iso)
    finished_at: str | None = None
    pipeline_versions: dict[str, str] = field(default_factory=lambda: {"swelter": __version__})
    stages: list[str] = field(default_factory=list)

    payloads_accepted: int = 0
    payloads_quarantined: int = 0
    corrections_applied: int = 0
    corrections_skipped_stale: int = 0
    cells_built: int = 0
    cells_provisional: int = 0

    def record(self, stage: str, event: str, **counters: int) -> None:
        """Increment the named counters (must be one of :data:`_COUNTER_FIELDS`) and log."""
        if stage not in self.stages:
            self.stages.append(stage)
        for key, delta in counters.items():
            if key not in _COUNTER_FIELDS:
                raise ValueError(f"unknown RunManifest counter: {key!r}")
            setattr(self, key, getattr(self, key) + delta)
        log_event(stage, event, **counters)

    def finish(self) -> None:
        """Stamp completion. Idempotent: a later call just moves the timestamp forward."""
        self.finished_at = _utcnow_iso()

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "pipeline_versions": dict(self.pipeline_versions),
            "stages": list(self.stages),
            "counters": {name: getattr(self, name) for name in _COUNTER_FIELDS},
        }


def write_manifest(store_dir: str | Path, manifest: RunManifest) -> Path:
    """Persist ``manifest`` as ``run-manifest.json`` inside ``store_dir``. Returns the path.

    Called once, at the end of a pipeline invocation, after :meth:`RunManifest.finish`. The
    store directory is created if it does not already exist (mirrors ``store.open_store``'s
    own lazy-create behaviour), so a first-ever ``swelter ingest`` on a fresh ``--store`` path
    does not need a separate mkdir step.
    """
    base = Path(store_dir)
    base.mkdir(parents=True, exist_ok=True)
    path = base / "run-manifest.json"
    path.write_text(json.dumps(manifest.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    return path


def read_manifest(store_dir: str | Path) -> dict[str, Any] | None:
    """Read back the latest ``run-manifest.json`` for ``store_dir``, or ``None`` if absent/invalid.

    Backs the ``run`` block in ``/api/health.json`` (``server.py``): a store a pipeline has
    never run against (or one predating this feature) simply omits the block rather than
    erroring the whole health endpoint.
    """
    path = Path(store_dir) / "run-manifest.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None
