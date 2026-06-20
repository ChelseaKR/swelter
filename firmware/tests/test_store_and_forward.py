"""Hardware-free tests for the node's store-and-forward buffer and sampler robustness.

The firmware is MicroPython source copied flat onto a node, not an installed package, so the
modules are loaded directly from ``firmware/src`` by file path (the same importlib trick the
driver test uses). Everything here runs on desktop CPython: the buffer's persistence, its
bounded retry-and-backoff, atomic rewrite, and the sampler's tolerate-a-failing-sensor path.

These tests are run by the CI ``firmware`` job alongside ``compileall``; they have no dependency
on the ``swelter`` package and need no hardware.
"""

from __future__ import annotations

import importlib.util
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

_FIRMWARE_SRC = Path(__file__).resolve().parents[1] / "src"


def _load(name: str) -> ModuleType:
    """Load a firmware module from ``firmware/src`` by file path."""
    path = _FIRMWARE_SRC / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"_fw_{name}", path)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise ImportError(f"could not load firmware module {name} from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_saf = _load("store_and_forward")
_sampler = _load("sampler")

StoreAndForward: Any = _saf.StoreAndForward
TransportError: type[Exception] = _saf.TransportError
Sampler: Any = _sampler.Sampler
SensorError: type[Exception] = _sampler.SensorError


# -- test doubles ---------------------------------------------------------------------------------


class _RecordingTransport:
    """Confirms every send and records the payloads, in order."""

    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    def send(self, payload: dict[str, Any]) -> None:
        self.sent.append(payload)


class _FlakyTransport:
    """Raises ``TransportError`` for the first ``fail_times`` calls, then confirms."""

    def __init__(self, fail_times: int) -> None:
        self.fail_times = fail_times
        self.calls = 0
        self.sent: list[dict[str, Any]] = []

    def send(self, payload: dict[str, Any]) -> None:
        self.calls += 1
        if self.calls <= self.fail_times:
            raise TransportError("simulated link down")
        self.sent.append(payload)


class _DeadTransport:
    """Always fails; counts how many times it was asked to send."""

    def __init__(self) -> None:
        self.calls = 0

    def send(self, payload: dict[str, Any]) -> None:
        self.calls += 1
        raise TransportError("permanently down")


def _payload(node_id: str = "node-07", ts: str = "2026-06-16T18:00:00Z") -> dict[str, Any]:
    return {"node_id": node_id, "timestamp": ts, "temp_c": 31.4, "humidity_pct": 58.2}


def _recording_sleep(log: list[float]) -> Callable[[float], None]:
    def _sleep(seconds: float) -> None:
        log.append(seconds)

    return _sleep


# -- buffering and persistence --------------------------------------------------------------------


def test_append_persists_across_a_new_instance(tmp_path: Path) -> None:
    # A reboot is modelled as a fresh StoreAndForward over the same on-flash file.
    path = str(tmp_path / "buffer.jsonl")
    buf = StoreAndForward(path, transport=_RecordingTransport())
    buf.append(_payload(ts="2026-06-16T18:00:00Z"))
    buf.append(_payload(ts="2026-06-16T18:05:00Z"))

    after_reboot = StoreAndForward(path, transport=_RecordingTransport())
    assert after_reboot.pending() == 2


def test_flush_forwards_oldest_first_and_empties_the_buffer(tmp_path: Path) -> None:
    path = str(tmp_path / "buffer.jsonl")
    transport = _RecordingTransport()
    buf = StoreAndForward(path, transport=transport)
    buf.append(_payload(ts="2026-06-16T18:00:00Z"))
    buf.append(_payload(ts="2026-06-16T18:05:00Z"))

    sent = buf.flush()
    assert sent == 2
    assert [p["timestamp"] for p in transport.sent] == [
        "2026-06-16T18:00:00Z",
        "2026-06-16T18:05:00Z",
    ]
    assert buf.pending() == 0


def test_outage_then_recovery_backfills_the_gap(tmp_path: Path) -> None:
    # Link down: the payload buffers and the flush is a no-op that keeps the backlog.
    path = str(tmp_path / "buffer.jsonl")
    dead = _DeadTransport()
    buf = StoreAndForward(path, transport=dead, max_attempts=1)
    buf.append(_payload(ts="2026-06-16T18:00:00Z"))
    buf.append(_payload(ts="2026-06-16T18:05:00Z"))
    assert buf.flush() == 0
    assert buf.pending() == 2  # nothing lost while the link was down

    # Link back: a fresh transport drains the whole backlog oldest-first.
    transport = _RecordingTransport()
    buf.transport = transport
    assert buf.flush() == 2
    assert [p["timestamp"] for p in transport.sent] == [
        "2026-06-16T18:00:00Z",
        "2026-06-16T18:05:00Z",
    ]


def test_corrupt_line_is_dropped_not_forwarded(tmp_path: Path) -> None:
    path = str(tmp_path / "buffer.jsonl")
    # A torn trailing line from a power loss mid-append, plus one good record.
    with open(path, "w") as handle:
        handle.write("{not valid json")
        handle.write("\n")
        handle.write('{"node_id": "node-07", "timestamp": "2026-06-16T18:05:00Z"}\n')
    transport = _RecordingTransport()
    buf = StoreAndForward(path, transport=transport)
    sent = buf.flush()
    assert sent == 1  # only the good record forwarded
    assert len(transport.sent) == 1
    assert buf.pending() == 0  # the corrupt line is gone, not stuck at the head


def test_a_payload_missing_required_keys_is_treated_as_corrupt(tmp_path: Path) -> None:
    path = str(tmp_path / "buffer.jsonl")
    with open(path, "w") as handle:
        handle.write('{"timestamp": "2026-06-16T18:00:00Z"}\n')  # no node_id
    transport = _RecordingTransport()
    buf = StoreAndForward(path, transport=transport)
    assert buf.flush() == 0
    assert transport.sent == []


# -- bounded retry and backoff --------------------------------------------------------------------


def test_flush_retries_within_a_cycle_then_succeeds(tmp_path: Path) -> None:
    path = str(tmp_path / "buffer.jsonl")
    waits: list[float] = []
    transport = _FlakyTransport(fail_times=2)
    buf = StoreAndForward(
        path,
        transport=transport,
        max_attempts=3,
        backoff_base_s=1.0,
        backoff_cap_s=30.0,
        sleep=_recording_sleep(waits),
    )
    buf.append(_payload())
    assert buf.flush() == 1
    assert transport.calls == 3  # two failures, then the confirming send
    assert waits == [1.0, 2.0]  # exponential backoff between the two retries
    assert buf.pending() == 0


def test_retry_count_is_bounded_by_max_attempts(tmp_path: Path) -> None:
    path = str(tmp_path / "buffer.jsonl")
    waits: list[float] = []
    dead = _DeadTransport()
    buf = StoreAndForward(
        path,
        transport=dead,
        max_attempts=4,
        backoff_base_s=1.0,
        backoff_cap_s=5.0,
        sleep=_recording_sleep(waits),
    )
    buf.append(_payload())
    assert buf.flush() == 0
    assert dead.calls == 4  # exactly max_attempts, not unbounded
    assert waits == [1.0, 2.0, 4.0]  # one wait fewer than attempts
    assert buf.pending() == 1  # kept buffered for the next cycle


def test_backoff_is_capped(tmp_path: Path) -> None:
    path = str(tmp_path / "buffer.jsonl")
    waits: list[float] = []
    dead = _DeadTransport()
    buf = StoreAndForward(
        path,
        transport=dead,
        max_attempts=5,
        backoff_base_s=10.0,
        backoff_cap_s=15.0,
        sleep=_recording_sleep(waits),
    )
    buf.append(_payload())
    buf.flush()
    # 10, 20->cap 15, 40->cap 15, 80->cap 15
    assert waits == [10.0, 15.0, 15.0, 15.0]


def test_flush_stops_at_first_unrecoverable_payload_preserving_order(tmp_path: Path) -> None:
    path = str(tmp_path / "buffer.jsonl")
    transport = _DeadTransport()
    buf = StoreAndForward(path, transport=transport, max_attempts=1)
    buf.append(_payload(ts="2026-06-16T18:00:00Z"))
    buf.append(_payload(ts="2026-06-16T18:05:00Z"))
    assert buf.flush() == 0
    # Only the head was attempted; the link is dead so we do not hammer it down the whole backlog.
    assert transport.calls == 1
    assert buf.pending() == 2


# -- cap enforcement and atomic rewrite -----------------------------------------------------------


def test_cap_drops_oldest_and_keeps_recent(tmp_path: Path) -> None:
    path = str(tmp_path / "buffer.jsonl")
    buf = StoreAndForward(path, transport=_RecordingTransport(), max_records=10)
    for i in range(25):
        buf.append(_payload(ts="2026-06-16T18:%02d:00Z" % i))
    # Never exceeds the cap; keeps the most recent readings.
    assert buf.pending() <= 10
    transport = _RecordingTransport()
    buf.transport = transport
    buf.flush()
    kept = [p["timestamp"] for p in transport.sent]
    assert "2026-06-16T18:24:00Z" in kept  # newest survived
    assert "2026-06-16T18:00:00Z" not in kept  # oldest dropped


def test_rewrite_leaves_no_leftover_temp_file(tmp_path: Path) -> None:
    path = str(tmp_path / "buffer.jsonl")
    buf = StoreAndForward(path, transport=_RecordingTransport())
    buf.append(_payload())
    buf.flush()
    assert not (tmp_path / "buffer.jsonl.tmp").exists()


# -- sampler tolerates a single failing sensor ----------------------------------------------------


class _OkTh:
    def read(self) -> tuple[float, float]:
        return (31.4, 58.2)


class _FailTh:
    def read(self) -> tuple[float, float]:
        raise SensorError("SHT31 bus error")


class _OkPm:
    def read(self) -> tuple[float, float]:
        return (19.7, 33.1)


class _FailPm:
    def read(self) -> tuple[float, float]:
        raise SensorError("PM UART timeout")


def _clock() -> str:
    return "2026-06-16T18:00:00Z"


def test_sampler_drops_only_the_failing_sensor() -> None:
    # PM fails; temp/humidity (and the derived heat index) still ship.
    sampler = Sampler("node-07", th=_OkTh(), pm=_FailPm(), clock=_clock)
    payload = sampler.sample()
    assert payload is not None
    assert payload["temp_c"] == 31.4
    assert payload["humidity_pct"] == 58.2
    assert "heat_index_c" in payload
    assert "pm25_ugm3" not in payload  # the failed sensor is absent, not invented
    assert "pm10_ugm3" not in payload


def test_sampler_keeps_pm_when_temp_humidity_fail() -> None:
    sampler = Sampler("node-07", th=_FailTh(), pm=_OkPm(), clock=_clock)
    payload = sampler.sample()
    assert payload is not None
    assert payload["pm25_ugm3"] == 19.7
    assert payload["pm10_ugm3"] == 33.1
    assert "temp_c" not in payload
    assert "heat_index_c" not in payload  # not computed without both inputs


def test_sampler_returns_none_when_every_sensor_fails() -> None:
    sampler = Sampler("node-07", th=_FailTh(), pm=_FailPm(), clock=_clock)
    assert sampler.sample() is None


def test_sampler_only_identifier_is_node_id() -> None:
    # Guards hard rule #1 at the firmware boundary: the payload carries node_id and nothing that
    # could identify or locate a person.
    sampler = Sampler("node-07", th=_OkTh(), pm=_OkPm(), clock=_clock)
    payload = sampler.sample()
    assert payload is not None
    forbidden = {"mac", "mac_address", "bssid", "ssid", "lat", "lon", "latitude", "longitude"}
    assert forbidden.isdisjoint(payload.keys())
    assert payload["node_id"] == "node-07"


if __name__ == "__main__":  # pragma: no cover - convenience for running off-CI
    raise SystemExit(pytest.main([__file__, "-q"]))
