"""The Open-Meteo real-data adapter: the pure mapping from API arrays to observations.

The network fetch itself is not unit-tested (it would be flaky and hit a live service); these tests
exercise the deterministic mapping with hand-built Open-Meteo-shaped payloads.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from swelter.config import consent_concerns, parse_config
from swelter.sources import _http, openmeteo
from swelter.sources._http import SourceError


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
        "wbgt_c",
    }
    assert all(o.node_id == "oak-park" for o in obs)
    assert all(o.source == openmeteo.SOURCE for o in obs)  # provenance travels with every value
    assert all(not o.is_trustworthy for o in obs)  # an upstream model is not swelter-calibrated
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


def _straddling_payload(
    reference: datetime, offsets: tuple[int, ...] = (-2, -1, 0, 1, 2)
) -> tuple[tuple[openmeteo.Neighborhood, ...], list[dict[str, Any]], list[dict[str, Any]]]:
    """An hourly response spanning ``offsets`` hours around ``reference``, as Open-Meteo returns it.

    Open-Meteo answers `past_days` + `forecast_days` in one array, so a live response really does
    straddle the current hour like this; nothing in the payload marks which side an hour is on.
    """
    hours = [
        (reference + timedelta(hours=h)).replace(minute=0, second=0, microsecond=0) for h in offsets
    ]
    times = [h.strftime("%Y-%m-%dT%H:00") for h in hours]
    n = len(times)
    places = (openmeteo.Neighborhood("Calexico", 32.6789, -115.4989),)
    air = [{"hourly": {"time": times, "pm2_5": [8.0] * n, "pm10": [12.0] * n}}]
    weather = [
        {
            "hourly": {
                "time": times,
                "temperature_2m": [40.0] * n,
                "relative_humidity_2m": [35.0] * n,
            }
        }
    ]
    return places, air, weather


def test_to_observations_never_emits_an_hour_that_has_not_happened() -> None:
    # The live defect (issue #168): CAMS forecast hours entered the store as ordinary
    # observations, so `newest_bucket()` — swelter's whole definition of "now" (ADR 0035) — landed
    # on an hour that had not occurred, and the map, the Now card and the alerts feed followed it.
    reference = datetime(2026, 8, 15, 14, 40, 49, tzinfo=UTC)
    places, air, weather = _straddling_payload(reference)
    obs = openmeteo.to_observations(places, air, weather, now=reference)

    assert obs, "the elapsed hours must still be ingested"
    cutoff = reference.strftime("%Y-%m-%dT%H:%M:%SZ")
    assert max(o.timestamp for o in obs) <= cutoff
    assert {o.timestamp for o in obs} == {
        "2026-08-15T12:00:00Z",
        "2026-08-15T13:00:00Z",
        "2026-08-15T14:00:00Z",
    }


def test_to_observations_clips_against_the_wall_clock_when_no_reference_is_given() -> None:
    # The default has to be the safe one: a caller that forgets `now` must not silently publish
    # predictions as readings.
    reference = datetime.now(UTC)
    places, air, weather = _straddling_payload(reference)
    obs = openmeteo.to_observations(places, air, weather)

    assert obs
    assert max(o.timestamp for o in obs) <= reference.strftime("%Y-%m-%dT%H:%M:%SZ")


def test_fetch_does_not_let_a_forecast_hour_become_the_newest_reading(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # End to end through the fetch path the Pages workflow actually runs, because the CLI passes
    # `--past-days` and no forecast argument, so `forecast_days=1` stands and the response
    # straddles the current hour on every run.
    reference = datetime(2026, 8, 15, 14, 40, 49, tzinfo=UTC)
    places, air, weather = _straddling_payload(reference)

    def fake_get(url: str) -> Any:
        return air if "air-quality" in url else weather

    monkeypatch.setattr(openmeteo, "_get_json", fake_get)
    obs = openmeteo.fetch(places, now=reference)

    assert obs
    assert max(o.timestamp for o in obs) == "2026-08-15T14:00:00Z"
    assert not [o for o in obs if o.timestamp > reference.strftime("%Y-%m-%dT%H:%M:%SZ")]


def test_network_doc_declares_exact_centroids_that_have_no_host() -> None:
    doc = openmeteo.network_doc((openmeteo.Neighborhood("Oak Park", 38.547, -121.463),))
    node = doc["nodes"][0]
    assert node["label"] == "Oak Park"
    # Exact, and hostless: shown as given, with nobody whose consent could be on record (#166).
    assert node["location"] == "public-place"
    assert doc["calibration_windows"] == []  # this source is not swelter-calibrated


def test_the_open_meteo_place_list_raises_no_host_consent_warnings() -> None:
    # The whole California list used to emit one unfixable consent warning per place, per route,
    # per deploy — several hundred lines a day naming nobody who could act on them, which is how
    # the one warning that would matter gets trained into background noise (issue #166).
    doc = openmeteo.network_doc(openmeteo.CALIFORNIA[:25])
    config = parse_config(doc)

    assert len(config.nodes) == 25
    assert consent_concerns(config) == []
    # The exemption is from the consent question, not from disclosure: these still publish exactly.
    node = config.nodes[0]
    assert node.public_location(config.grid_resolution_m) == (node.lat, node.lon)


def test_a_hosted_node_with_no_consent_ref_is_still_flagged_beside_them() -> None:
    # The signal the noise was burying. A real host location with no governance-log entry has to
    # stay loud, in the same config as any number of hostless public places.
    doc = openmeteo.network_doc(openmeteo.CALIFORNIA[:25])
    doc["nodes"].append(
        {
            "node_id": "node-07",
            "label": "Elm & 9th",
            "lat": 38.61,
            "lon": -121.46,
            "location": "precise",
        }
    )
    concerns = consent_concerns(parse_config(doc))

    assert len(concerns) == 1
    assert "node-07" in concerns[0]


def test_get_json_retries_transient_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    def fake_request(url: str, headers: dict[str, str], timeout: float) -> Any:
        calls["n"] += 1
        if calls["n"] < 3:
            raise TimeoutError("handshake timed out")  # the failure that dropped the live demo
        return {"ok": 1}

    monkeypatch.setattr(_http, "_request_json", fake_request)
    monkeypatch.setattr(time, "sleep", lambda *_: None)
    assert openmeteo._get_json("https://example.test") == {"ok": 1}
    assert calls["n"] == 3  # two transient failures, then success


def test_get_json_raises_after_exhausting_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_request(url: str, headers: dict[str, str], timeout: float) -> Any:
        raise TimeoutError("down")

    monkeypatch.setattr(_http, "_request_json", fake_request)
    monkeypatch.setattr(time, "sleep", lambda *_: None)
    with pytest.raises(SourceError):
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
