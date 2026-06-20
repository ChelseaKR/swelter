"""Failure-path tests for the shared source fetch/retry and the three real-data adapters.

No real network: every test stubs ``urllib.request.urlopen`` (or the adapter's ``_get_json``) and
no-ops ``time.sleep``, so these run offline and deterministically. They cover the resilience the
live demo depends on — a flaky connection, an HTTP 429 that then succeeds, malformed JSON, an
empty result, and a non-retryable HTTP error — without ever touching a live service.
"""

from __future__ import annotations

import io
import time
import urllib.error
import urllib.request
from email.message import Message
from typing import Any

import pytest

from swelter.sources import _http, openaq, openmeteo, sensor_community
from swelter.sources._http import SourceError, get_json


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


def _http_error(code: int, *, retry_after: str | None = None) -> urllib.error.HTTPError:
    headers: Message = Message()
    if retry_after is not None:
        headers["Retry-After"] = retry_after
    return urllib.error.HTTPError(
        url="https://example.test",
        code=code,
        msg="boom",
        hdrs=headers,
        fp=io.BytesIO(b""),
    )


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make backoff instant so the retry tests do not actually wait."""
    monkeypatch.setattr(time, "sleep", lambda *_: None)


# --- shared _http.get_json ------------------------------------------------------------------


def test_get_json_succeeds_first_try(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(urllib.request, "urlopen", lambda *_a, **_k: _FakeResp(b'{"ok": 1}'))
    assert get_json("https://example.test") == {"ok": 1}


def test_get_json_retries_on_429_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    def fake_urlopen(*_a: Any, **_k: Any) -> _FakeResp:
        calls["n"] += 1
        if calls["n"] == 1:
            raise _http_error(429, retry_after="0")  # rate-limited, then it clears
        return _FakeResp(b'{"ok": 1}')

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    assert get_json("https://example.test") == {"ok": 1}
    assert calls["n"] == 2  # one 429, then success


def test_get_json_retries_on_malformed_json_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    bodies = [b"<html>not json</html>", b'{"ok": 1}']

    def fake_urlopen(*_a: Any, **_k: Any) -> _FakeResp:
        return _FakeResp(bodies.pop(0))

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    assert get_json("https://example.test") == {"ok": 1}  # bad body retried, good body wins


def test_get_json_wraps_network_error_as_source_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(*_a: Any, **_k: Any) -> _FakeResp:
        raise TimeoutError("down")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(SourceError) as exc:
        get_json("https://example.test", retries=2)
    assert isinstance(exc.value.__cause__, TimeoutError)  # original cause preserved
    assert isinstance(exc.value, OSError)  # still an OSError for legacy `except OSError` callers


def test_get_json_does_not_retry_non_retryable_http(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    def fake_urlopen(*_a: Any, **_k: Any) -> _FakeResp:
        calls["n"] += 1
        raise _http_error(404)  # a 404 is a caller error, not transient

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(SourceError):
        get_json("https://example.test", retries=4)
    assert calls["n"] == 1  # raised immediately, no wasted retries


def test_get_json_exhausts_retries_on_5xx(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    def fake_urlopen(*_a: Any, **_k: Any) -> _FakeResp:
        calls["n"] += 1
        raise _http_error(503)  # server-side, retryable

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(SourceError):
        get_json("https://example.test", retries=3)
    assert calls["n"] == 3  # tried every attempt before giving up


def test_retry_after_seconds_parses_and_caps() -> None:
    assert _http._retry_after_seconds(_http_error(429, retry_after="2")) == 2.0
    assert (
        _http._retry_after_seconds(_http_error(429, retry_after="9999")) == _http._MAX_RETRY_AFTER_S
    )
    assert _http._retry_after_seconds(_http_error(429, retry_after="Wed, 21 Oct")) == 0.0
    assert _http._retry_after_seconds(_http_error(429)) == 0.0


# --- openaq: pagination and per-location resilience -----------------------------------------


def test_openaq_locations_survives_a_failing_page(monkeypatch: pytest.MonkeyPatch) -> None:
    # First page returns a full page; the second page fails -> keep what we already have.
    page1 = {"results": [{"id": i} for i in range(1000)]}

    def fake_get(url: str, api_key: str, **_k: Any) -> Any:
        if "page=1" in url:
            return page1
        raise SourceError("page 2 down")

    monkeypatch.setattr(openaq, "_get_json", fake_get)
    locs = openaq._locations(openaq.CALIFORNIA_BBOX, "key", max_locations=5000)
    assert len(locs) == 1000  # page 1 kept, page 2's failure did not crash the run


def test_openaq_fetch_skips_a_failing_location(monkeypatch: pytest.MonkeyPatch) -> None:
    locations = [
        {
            "id": 1,
            "coordinates": {"latitude": 34.0, "longitude": -118.0},
            "name": "Good Site",
            "sensors": [{"id": 10, "parameter": {"name": "pm25"}}],
        },
        {
            "id": 2,
            "coordinates": {"latitude": 34.1, "longitude": -118.1},
            "name": "Bad Site",
            "sensors": [{"id": 20, "parameter": {"name": "pm25"}}],
        },
    ]
    monkeypatch.setattr(openaq, "_locations", lambda *_a, **_k: locations)

    def fake_latest(url: str, api_key: str, **_k: Any) -> Any:
        if "/locations/2/" in url:
            raise SourceError("site 2 down")  # one flaky location
        return {
            "results": [
                {"sensorsId": 10, "value": 12.0, "datetime": {"utc": "2026-06-17T23:00:00Z"}}
            ]
        }

    monkeypatch.setattr(openaq, "_get_json", fake_latest)
    obs, nodes = openaq.fetch("key", throttle_s=0.0)
    assert set(nodes) == {"oaq-1"}  # the good site survived, the bad one was skipped
    assert obs and all(o.node_id == "oaq-1" for o in obs)


# --- sensor.community: empty + failure --------------------------------------------------------


def test_sensor_community_fetch_empty_area(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sensor_community, "_get_json", lambda *_a, **_k: [])
    obs, nodes = sensor_community.fetch()
    assert obs == [] and nodes == {}  # an empty area is a clean empty result, not an error


def test_sensor_community_fetch_non_list_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    # A malformed top-level payload (object instead of the expected array) yields nothing, no crash.
    monkeypatch.setattr(sensor_community, "_get_json", lambda *_a, **_k: {"error": "rate limited"})
    obs, nodes = sensor_community.fetch()
    assert obs == [] and nodes == {}


def test_sensor_community_fetch_propagates_source_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_a: Any, **_k: Any) -> Any:
        raise SourceError("network down")

    monkeypatch.setattr(sensor_community, "_get_json", boom)
    with pytest.raises(SourceError):  # the CLI catches this and prints a clean message
        sensor_community.fetch()


def test_sensor_community_parse_skips_one_bad_record(monkeypatch: pytest.MonkeyPatch) -> None:
    # A single malformed row (non-numeric value) is skipped; the good row still produces readings.
    rows = [
        {
            "sensor": {"id": 1},
            "timestamp": "2026-06-17 23:00:00",
            "location": {"latitude": "48.0", "longitude": "9.0"},
            "sensordatavalues": [{"value_type": "P2", "value": "not-a-number"}],
        },
        {
            "sensor": {"id": 2},
            "timestamp": "2026-06-17 23:00:00",
            "location": {"latitude": "48.1", "longitude": "9.1"},
            "sensordatavalues": [{"value_type": "P2", "value": "12.0"}],
        },
    ]
    obs, nodes = sensor_community.parse_measurements(rows)
    assert "sc-2" in nodes  # the good sensor produced a reading
    assert any(o.node_id == "sc-2" and o.parameter == "pm25_ugm3" for o in obs)
    assert not any(o.node_id == "sc-1" for o in obs)  # the bad value was skipped, not crashed on


# --- openmeteo: empty + malformed chunk -------------------------------------------------------


def test_openmeteo_fetch_empty_when_all_chunks_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(_url: str) -> Any:
        raise SourceError("down")

    monkeypatch.setattr(openmeteo, "_get_json", boom)
    places = (openmeteo.Neighborhood("Aville", 38.0, -121.0),)
    assert openmeteo.fetch(places, chunk=1) == []  # every chunk down -> empty, never raises


def test_openmeteo_to_observations_tolerates_short_arrays() -> None:
    # The weather array is shorter than the time array; the missing hour is skipped, not crashed on.
    places = (openmeteo.Neighborhood("Aville", 38.0, -121.0),)
    air = [
        {
            "hourly": {
                "time": ["2026-06-16T00:00", "2026-06-16T01:00"],
                "pm2_5": [10.0, 11.0],
                "pm10": [20.0, 21.0],
            }
        }
    ]
    weather = [
        {
            "hourly": {
                "time": ["2026-06-16T00:00"],
                "temperature_2m": [25.0],
                "relative_humidity_2m": [40.0],
            }
        }
    ]
    obs = openmeteo.to_observations(places, air, weather)
    # Both hours of PM emit; only the first hour has temp/humidity/heat-index.
    assert sum(o.parameter == "pm25_ugm3" for o in obs) == 2
    assert sum(o.parameter == "temp_c" for o in obs) == 1
