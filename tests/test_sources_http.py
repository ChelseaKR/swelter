"""Failure-path tests for the shared source fetch/retry and the three real-data adapters.

No real network: every test stubs the shared HTTPS request boundary (or an adapter's
``_get_json``) and no-ops ``time.sleep``, so these run offline and deterministically. They cover
the resilience the live demo depends on — a flaky connection, an HTTP 429 that then succeeds,
malformed JSON, an empty result, and a non-retryable HTTP error — without touching a live service.
"""

from __future__ import annotations

import http.client
import json
import time
from typing import Any, ClassVar

import pytest

from swelter.sources import _http, openaq, openmeteo, sensor_community
from swelter.sources._http import SourceError, get_json


def _http_error(code: int, *, retry_after: str | None = None) -> _http._HTTPStatusError:
    headers: dict[str, str] = {}
    if retry_after is not None:
        headers["Retry-After"] = retry_after
    return _http._HTTPStatusError(code, headers)


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make backoff instant so the retry tests do not actually wait."""
    monkeypatch.setattr(time, "sleep", lambda *_: None)


# --- shared _http.get_json ------------------------------------------------------------------


def test_get_json_succeeds_first_try(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_http, "_request_json", lambda *_a, **_k: {"ok": 1})
    assert get_json("https://example.test") == {"ok": 1}


def test_get_json_retries_on_429_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    def fake_request(*_a: Any, **_k: Any) -> dict[str, int]:
        calls["n"] += 1
        if calls["n"] == 1:
            raise _http_error(429, retry_after="0")  # rate-limited, then it clears
        return {"ok": 1}

    monkeypatch.setattr(_http, "_request_json", fake_request)
    assert get_json("https://example.test") == {"ok": 1}
    assert calls["n"] == 2  # one 429, then success


def test_get_json_retries_on_malformed_json_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    responses: list[object] = [json.JSONDecodeError("not JSON", "<html>", 0), {"ok": 1}]

    def fake_request(*_a: Any, **_k: Any) -> object:
        response = responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr(_http, "_request_json", fake_request)
    assert get_json("https://example.test") == {"ok": 1}  # bad body retried, good body wins


def test_get_json_wraps_network_error_as_source_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_request(*_a: Any, **_k: Any) -> object:
        raise TimeoutError("down")

    monkeypatch.setattr(_http, "_request_json", fake_request)
    with pytest.raises(SourceError) as exc:
        get_json("https://example.test", retries=2)
    assert isinstance(exc.value.__cause__, TimeoutError)  # original cause preserved
    assert isinstance(exc.value, OSError)  # still an OSError for legacy `except OSError` callers


def test_get_json_does_not_retry_non_retryable_http(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    def fake_request(*_a: Any, **_k: Any) -> object:
        calls["n"] += 1
        raise _http_error(404)  # a 404 is a caller error, not transient

    monkeypatch.setattr(_http, "_request_json", fake_request)
    with pytest.raises(SourceError):
        get_json("https://example.test", retries=4)
    assert calls["n"] == 1  # raised immediately, no wasted retries


def test_get_json_exhausts_retries_on_5xx(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    def fake_request(*_a: Any, **_k: Any) -> object:
        calls["n"] += 1
        raise _http_error(503)  # server-side, retryable

    monkeypatch.setattr(_http, "_request_json", fake_request)
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


def test_openaq_locations_filters_before_the_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    pages = {
        1: [
            {"id": 1, "coordinates": {"latitude": 32.6927, "longitude": -114.6277}},
            {"id": 2, "coordinates": {"latitude": 39.5349, "longitude": -119.7527}},
        ],
        2: [
            {"id": 3, "coordinates": {"latitude": 34.0522, "longitude": -118.2437}},
            {"id": 4, "coordinates": {"latitude": 38.5816, "longitude": -121.4944}},
        ],
    }
    requested_pages: list[int] = []

    def fake_get(url: str, api_key: str, **_kwargs: Any) -> Any:
        page = int(url.rsplit("page=", 1)[1])
        requested_pages.append(page)
        return {"results": pages.get(page, [])}

    monkeypatch.setattr(openaq, "_get_json", fake_get)
    locations = openaq._locations(
        openaq.CALIFORNIA_BBOX,
        "key",
        max_locations=2,
        per_page=2,
        include=openaq._in_california,
    )
    assert [location["id"] for location in locations] == [3, 4]
    assert requested_pages == [1, 2]  # bbox spillover did not consume the two-site cap


def test_openaq_fetch_skips_a_failing_location(monkeypatch: pytest.MonkeyPatch) -> None:
    locations = [
        {
            "id": 1,
            "coordinates": {"latitude": 34.0, "longitude": -118.0},
            "name": "Good Site",
            "provider": {"id": 7, "name": "Good Provider"},
            "licenses": [
                {
                    "id": 33,
                    "name": "US Public Domain",
                    "attribution": {"name": "Good Provider", "url": None},
                    "dateFrom": "2020-01-01",
                    "dateTo": None,
                }
            ],
            "sensors": [{"id": 10, "parameter": {"name": "pm25"}}],
        },
        {
            "id": 2,
            "coordinates": {"latitude": 34.1, "longitude": -118.1},
            "name": "Bad Site",
            "provider": {"id": 7, "name": "Good Provider"},
            "licenses": [
                {
                    "id": 33,
                    "name": "US Public Domain",
                    "attribution": {"name": "Good Provider", "url": None},
                }
            ],
            "sensors": [{"id": 20, "parameter": {"name": "pm25"}}],
        },
    ]
    monkeypatch.setattr(openaq, "_locations", lambda *_a, **_k: locations)

    def fake_latest(url: str, api_key: str, **_k: Any) -> Any:
        if "/licenses/33" in url:
            return {
                "results": [
                    {
                        "id": 33,
                        "name": "US Public Domain",
                        "sourceUrl": "https://www.usa.gov/government-copyright",
                    }
                ]
            }
        if "/locations/2/" in url:
            raise SourceError("site 2 down")  # one flaky location
        return {
            "results": [
                {
                    "locationsId": 1,
                    "sensorsId": 10,
                    "value": 12.0,
                    "datetime": {"utc": "2026-06-17T23:00:00Z"},
                }
            ]
        }

    monkeypatch.setattr(openaq, "_get_json", fake_latest)
    obs, nodes = openaq.fetch("key", throttle_s=0.0)
    assert set(nodes) == {"oaq-1"}  # the good site survived, the bad one was skipped
    assert obs and all(o.node_id == "oaq-1" for o in obs)


def test_openaq_fetch_never_requests_out_of_state_latest(monkeypatch: pytest.MonkeyPatch) -> None:
    locations = [
        {
            "id": 1,
            "coordinates": {"latitude": 32.6927, "longitude": -114.6277},
            "name": "Yuma",
            "provider": {"id": 7, "name": "Provider"},
            "licenses": [
                {
                    "id": 33,
                    "name": "US Public Domain",
                    "attribution": {"name": "Provider", "url": None},
                }
            ],
            "sensors": [{"id": 10, "parameter": {"name": "pm25"}}],
        },
        {
            "id": 2,
            "coordinates": {"latitude": 34.0522, "longitude": -118.2437},
            "name": "Los Angeles",
            "provider": {"id": 7, "name": "Provider"},
            "licenses": [
                {
                    "id": 33,
                    "name": "US Public Domain",
                    "attribution": {"name": "Provider", "url": None},
                }
            ],
            "sensors": [{"id": 20, "parameter": {"name": "pm25"}}],
        },
    ]
    monkeypatch.setattr(openaq, "_locations", lambda *_args, **_kwargs: locations)
    requested: list[str] = []

    def fake_latest(url: str, api_key: str, **_kwargs: Any) -> Any:
        requested.append(url)
        if "/licenses/33" in url:
            return {
                "results": [
                    {
                        "id": 33,
                        "name": "US Public Domain",
                        "sourceUrl": "https://www.usa.gov/government-copyright",
                    }
                ]
            }
        return {
            "results": [
                {
                    "locationsId": 2,
                    "sensorsId": 20,
                    "value": 12.0,
                    "datetime": {"utc": "2026-06-17T23:00:00Z"},
                }
            ]
        }

    monkeypatch.setattr(openaq, "_get_json", fake_latest)
    observations, nodes = openaq.fetch("key", throttle_s=0.0)
    assert set(nodes) == {"oaq-2"}
    assert observations and {observation.node_id for observation in observations} == {"oaq-2"}
    assert requested == [
        f"{openaq.API}/licenses/33",
        f"{openaq.API}/locations/2/latest",
    ]


# --- sensor.community: empty + failure --------------------------------------------------------


def test_sensor_community_fetch_empty_area(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sensor_community, "_get_json", lambda *_a, **_k: [])
    obs, nodes = sensor_community.fetch()
    assert obs == [] and nodes == {}  # an empty area is a clean empty result, not an error


def test_sensor_community_fetch_non_list_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    """A malformed top-level payload raises rather than becoming an empty area.

    This test used to assert the opposite — that ``{"error": ...}`` "yields nothing, no crash" —
    and that guarantee is what let a refused fetch pass as thin coverage for seven weeks. Note
    that the payload it chose to prove tolerance with was itself an error document. Swallowing a
    crash and swallowing a refusal look identical from inside the adapter; only the caller can
    tell them apart, and only if we let it.
    """
    monkeypatch.setattr(sensor_community, "_get_json", lambda *_a, **_k: {"error": "rate limited"})
    with pytest.raises(SourceError):
        sensor_community.fetch()


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


# --- identifying ourselves, and hearing a refusal -------------------------------------------
#
# These two cover the failure that took Sensor.Community offline for swelter between 2026-06-19
# and 2026-08-06 without a single red run. Note where they have to sit: the tests above stub
# `_request_json`, which is where the header is built, so no test above this line can see whether
# a request carries a User-Agent at all. That is precisely why the regression survived.


class _CapturingConnection:
    """Stand-in for ``http.client.HTTPSConnection`` that records the request it was handed."""

    sent: ClassVar[dict[str, str]] = {}

    def __init__(self, *_a: Any, **_k: Any) -> None:
        self._body = b"[]"

    def request(self, _method: str, _target: str, headers: dict[str, str]) -> None:
        type(self).sent = dict(headers)

    def getresponse(self) -> Any:
        body = self._body

        class _Response:
            status = 200

            @staticmethod
            def read() -> bytes:
                return body

            @staticmethod
            def getheaders() -> list[tuple[str, str]]:
                return []

        return _Response()

    def close(self) -> None:
        return None


def test_every_request_identifies_swelter(monkeypatch: pytest.MonkeyPatch) -> None:
    """A fetch must carry a non-empty User-Agent.

    Sensor.Community declines an anonymous client with HTTP 200 and a JSON error document, so an
    unidentified request is not a loud failure — it is a quiet empty map.
    """
    monkeypatch.setattr(http.client, "HTTPSConnection", _CapturingConnection)
    get_json("https://example.test/data")
    agent = _CapturingConnection.sent.get("User-Agent", "")
    assert agent.strip(), "requests must identify swelter; an anonymous fetch is silently refused"
    assert "swelter" in agent.lower()


def test_caller_may_override_the_user_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(http.client, "HTTPSConnection", _CapturingConnection)
    get_json("https://example.test/data", headers={"User-Agent": "custom/1.0"})
    assert _CapturingConnection.sent["User-Agent"] == "custom/1.0"


def test_expect_records_keeps_an_empty_area_as_a_real_answer() -> None:
    # Zero sensors in an area is a measurement, not a fault. It must stay quiet.
    assert _http.expect_records([], source="Sensor.Community") == []


def test_expect_records_raises_on_a_200_error_document() -> None:
    """The exact payload Sensor.Community serves an anonymous client."""
    payload = ['"error": "empty user agent not allowed"']
    with pytest.raises(SourceError) as caught:
        _http.expect_records(payload, source="Sensor.Community")
    # The operator gets to see what actually arrived, not a guess about coverage.
    assert "empty user agent not allowed" in str(caught.value)


def test_expect_records_raises_when_the_payload_is_not_a_list() -> None:
    with pytest.raises(SourceError):
        _http.expect_records({"error": "nope"}, source="Sensor.Community")


def test_sensor_community_fetch_refuses_to_report_a_refusal_as_no_sensors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End to end through the adapter: a refusal raises instead of returning zero observations."""
    monkeypatch.setattr(
        sensor_community,
        "_get_json",
        lambda *_a, **_k: ['"error": "empty user agent not allowed"'],
    )
    with pytest.raises(SourceError):
        sensor_community.fetch(sensor_community.STUTTGART)
