"""The Open-Meteo real-data adapter: the pure mapping from API arrays to observations.

The network fetch itself is not unit-tested (it would be flaky and hit a live service); these tests
exercise the deterministic mapping with hand-built Open-Meteo-shaped payloads.
"""

from __future__ import annotations

import time
import urllib.request
from typing import Any

import pytest

from swelter.sources import openmeteo


class _FakeResp:
    """A minimal stand-in for an http response context manager."""

    def __init__(self, body: bytes) -> None:
        self._body = body

    def __enter__(self) -> _FakeResp:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def read(self) -> bytes:
        return self._body


def test_to_observations_maps_arrays() -> None:
    places = (openmeteo.Neighborhood("Oak Park", 38.547, -121.463),)
    air = [
        {
            "hourly": {
                "time": ["2026-06-16T00:00", "2026-06-16T01:00"],
                "pm2_5": [12.3, 14.1],
                "pm10": [20.0, 22.5],
            }
        }
    ]
    weather = [
        {
            "hourly": {
                "time": ["2026-06-16T00:00", "2026-06-16T01:00"],
                "temperature_2m": [30.0, 31.0],
                "relative_humidity_2m": [55.0, 50.0],
            }
        }
    ]
    obs = openmeteo.to_observations(places, air, weather)
    assert {o.parameter for o in obs} == {
        "temp_c",
        "humidity_pct",
        "pm25_ugm3",
        "pm10_ugm3",
        "heat_index_c",
    }
    assert all(o.node_id == "oak-park" for o in obs)
    assert all(
        o.calibration == openmeteo.SOURCE for o in obs
    )  # provenance travels with every value
    assert all(o.timestamp.endswith("Z") for o in obs)  # normalised to canonical UTC
    pm = next(
        o for o in obs if o.parameter == "pm25_ugm3" and o.timestamp == "2026-06-16T00:00:00Z"
    )
    assert pm.value == 12.3
    assert pm.unit == "ug/m3"


def test_to_observations_skips_nulls() -> None:
    places = (openmeteo.Neighborhood("Test Place", 1.0, 2.0),)
    air = [{"hourly": {"time": ["2026-06-16T00:00"], "pm2_5": [None], "pm10": [None]}}]
    weather = [
        {
            "hourly": {
                "time": ["2026-06-16T00:00"],
                "temperature_2m": [None],
                "relative_humidity_2m": [None],
            }
        }
    ]
    assert openmeteo.to_observations(places, air, weather) == []  # nothing to emit from all-null


def test_network_doc_uses_precise_real_centroids() -> None:
    doc = openmeteo.network_doc((openmeteo.Neighborhood("Oak Park", 38.547, -121.463),))
    node = doc["nodes"][0]
    assert node["label"] == "Oak Park"
    assert node["location"] == "precise"  # public neighborhood centroids, shown exactly
    assert doc["calibration_windows"] == []  # this source is not swelter-calibrated


def test_get_json_retries_transient_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    def fake_urlopen(url: str, timeout: float = 0.0) -> _FakeResp:
        calls["n"] += 1
        if calls["n"] < 3:
            raise TimeoutError("handshake timed out")  # the failure that dropped the live demo
        return _FakeResp(b'{"ok": 1}')

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(time, "sleep", lambda *_: None)
    assert openmeteo._get_json("https://example.test") == {"ok": 1}
    assert calls["n"] == 3  # two transient failures, then success


def test_get_json_raises_after_exhausting_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(url: str, timeout: float = 0.0) -> _FakeResp:
        raise TimeoutError("down")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(time, "sleep", lambda *_: None)
    with pytest.raises(OSError):
        openmeteo._get_json("https://example.test", retries=2)


def test_fetch_tolerates_a_failed_chunk(monkeypatch: pytest.MonkeyPatch) -> None:
    # A statewide fetch is many chunks; one failing must not lose the rest (nor fall to synthetic).
    places = (
        openmeteo.Neighborhood("Aville", 38.0, -121.0),
        openmeteo.Neighborhood("Bville", 37.0, -122.0),
    )

    def fake_get(url: str) -> Any:
        if "37.0" in url:  # the Bville chunk fails outright
            raise TimeoutError("down")
        if "air-quality" in url:
            return [{"hourly": {"time": ["2026-06-16T00:00"], "pm2_5": [10.0], "pm10": [20.0]}}]
        return [
            {
                "hourly": {
                    "time": ["2026-06-16T00:00"],
                    "temperature_2m": [25.0],
                    "relative_humidity_2m": [40.0],
                }
            }
        ]

    monkeypatch.setattr(openmeteo, "_get_json", fake_get)
    obs = openmeteo.fetch(places, chunk=1)
    assert {o.node_id for o in obs} == {"aville"}  # Bville skipped, Aville survived
