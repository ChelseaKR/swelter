"""The Open-Meteo real-data adapter: the pure mapping from API arrays to observations.

The network fetch itself is not unit-tested (it would be flaky and hit a live service); these tests
exercise the deterministic mapping with hand-built Open-Meteo-shaped payloads.
"""

from __future__ import annotations

from swelter.sources import openmeteo


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
