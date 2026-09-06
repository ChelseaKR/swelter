"""The OpenAQ real-sensor adapter: the pure mapping from /latest results to observations.

The live fetch needs an API key and a network, so it is not unit-tested; these tests exercise the
deterministic mapping with hand-built OpenAQ-v3-shaped payloads — including the honesty-critical bit
that real-but-uncalibrated sensors stay RAW (→ provisional).
"""

from __future__ import annotations

import copy
from dataclasses import FrozenInstanceError
from typing import Any
from unittest import mock

import pytest

from swelter.models import RAW, Observation
from swelter.sources import _california_boundary as california_boundary
from swelter.sources import openaq
from swelter.sources._geometry import contains_point, decode_multipolygon
from swelter.sources._http import SourceError


def _row(
    sid: int,
    value: float,
    when: str = "2026-06-17T23:00:00Z",
    *,
    location_id: object = 7,
) -> dict[str, Any]:
    return {
        "locationsId": location_id,
        "sensorsId": sid,
        "value": value,
        "datetime": {"utc": when},
    }


SENSOR_PARAM = {
    1: ("pm25_ugm3", "ug/m3"),
    2: ("temp_c", "degC"),
    3: ("humidity_pct", "%"),
}


def test_parse_latest_maps_and_stays_raw() -> None:
    obs = openaq.parse_latest(7, [_row(1, 12.3), _row(2, 28.0), _row(3, 40.0)], SENSOR_PARAM)
    params = {o.parameter for o in obs}
    # + derived heat index and estimated WBGT
    assert params == {"pm25_ugm3", "temp_c", "humidity_pct", "heat_index_c", "wbgt_c"}
    assert all(o.calibration == RAW for o in obs)  # real, but not swelter-calibrated → provisional
    assert all(o.node_id == "oaq-7" for o in obs)
    assert all(o.timestamp.endswith("Z") for o in obs)
    pm = next(o for o in obs if o.parameter == "pm25_ugm3")
    assert pm.value == 12.3 and pm.unit == "ug/m3"


def test_parse_latest_derives_no_heat_metric_from_a_rejected_input() -> None:
    """A reference monitor can still report an impossible value. Its heat index and estimated
    WBGT would land back inside their own ranges and publish as clean readings, so they are not
    derived at all (ADR 0041); the raw rows still travel for QC to label."""
    obs = openaq.parse_latest(7, [_row(1, 12.3), _row(2, -145.7), _row(3, 40.0)], SENSOR_PARAM)
    params = {o.parameter for o in obs}
    assert "heat_index_c" not in params and "wbgt_c" not in params
    assert params == {"pm25_ugm3", "temp_c", "humidity_pct"}


def test_parse_latest_skips_unknown_or_null() -> None:
    rows = [
        _row(99, 5.0, location_id=1),  # sensor not in the parameter map
        {
            "locationsId": 1,
            "sensorsId": 1,
            "value": None,
            "datetime": {"utc": "2026-06-17T23:00:00Z"},
        },  # null value
        {"locationsId": 1, "sensorsId": 1, "value": 9.0},  # no datetime
    ]
    assert openaq.parse_latest(1, rows, SENSOR_PARAM) == []


def test_parse_latest_rejects_missing_mismatched_or_boolean_location_identity() -> None:
    rows = [
        _row(1, 1.0, location_id=8),
        _row(1, 2.0, location_id=True),
        {"sensorsId": 1, "value": 3.0, "datetime": {"utc": "2026-06-17T23:00:00Z"}},
        _row(1, 4.0, location_id=7),
    ]
    observations = openaq.parse_latest(7, rows, SENSOR_PARAM)
    assert [(observation.node_id, observation.value) for observation in observations] == [
        ("oaq-7", 4.0)
    ]


def test_sensor_parameters_indexes_by_sensor_id() -> None:
    locations = [
        {
            "id": 5,
            "sensors": [
                {"id": 10, "parameter": {"name": "pm25", "units": "ug/m3"}},
                {"id": True, "parameter": {"name": "pm25", "units": "ug/m3"}},
                {"id": 11, "parameter": {"name": "co", "units": "ppm"}},  # not a swelter parameter
            ],
        }
    ]
    sp = openaq._sensor_parameters(locations)
    assert sp == {10: ("pm25_ugm3", "ug/m3")}  # co dropped, pm25 mapped


def test_parse_latest_rejects_boolean_sensor_identity() -> None:
    assert openaq.parse_latest(7, [_row(True, 12.3)], SENSOR_PARAM) == []


def test_build_license_ledger_preserves_per_location_terms() -> None:
    locations = [
        {
            "id": 2178,
            "name": "Del Norte",
            "provider": {"id": 119, "name": "AirNow"},
            "licenses": [
                {
                    "id": 33,
                    "name": "US Public Domain",
                    "attribution": {
                        "name": "Unknown Governmental Organization",
                        "url": None,
                    },
                    "dateFrom": "2016-01-30",
                    "dateTo": None,
                }
            ],
        }
    ]
    catalog = {
        33: {
            "id": 33,
            "name": "US Public Domain",
            "sourceUrl": "https://www.usa.gov/government-copyright",
        }
    }
    ledger = openaq.build_license_ledger(locations, catalog, fetched_at="2026-07-16T12:00:00Z")
    assert openaq.validate_license_ledger(ledger)
    [entry] = ledger["entries"]
    assert entry["location_id"] == 2178
    assert entry["license_id"] == 33
    assert entry["provider"] == "AirNow"
    assert entry["license_name"] == "US Public Domain"
    assert entry["license_url"] == "https://www.usa.gov/government-copyright"
    assert entry["attribution"] == "Unknown Governmental Organization"
    assert entry["upstream_url"] == f"{openaq.API}/locations/2178"


def test_build_license_ledger_discloses_and_excludes_missing_terms() -> None:
    ledger = openaq.build_license_ledger(
        [{"id": 9, "name": "Unknown", "licenses": []}],
        {},
        fetched_at="2026-07-16T12:00:00Z",
    )
    assert ledger["entries"] == []
    assert ledger["excluded_locations"][0]["location_id"] == 9
    assert not openaq.validate_license_ledger(ledger)


def test_network_doc_marks_uncalibrated_coarse_and_california_only() -> None:
    doc = openaq.network_doc(
        "California",
        {
            "oaq-5": ("Downtown LA", 34.05, -118.24),
            "oaq-6": ("Yuma", 32.6927, -114.6277),
        },
    )
    node = doc["nodes"][0]
    assert [candidate["node_id"] for candidate in doc["nodes"]] == ["oaq-5"]
    assert node["location"] == "coarse"  # upstream publication is not swelter host consent
    assert doc["calibration_windows"] == []  # real, but not swelter-calibrated
    assert doc["geographic_scope"]["id"] == "US-CA"
    assert "OpenAQ" in doc["name"]


@pytest.mark.parametrize(
    ("name", "lat", "lon", "expected"),
    [
        ("Sacramento", 38.5816, -121.4944, True),
        ("South Lake Tahoe", 38.9399, -119.9772, True),
        ("Avalon on Santa Catalina Island", 33.3428, -118.3278, True),
        ("Yuma, Arizona", 32.6927, -114.6277, False),
        ("Sparks, Nevada", 39.5349, -119.7527, False),
        ("Brookings, Oregon", 42.0526, -124.2839, False),
    ],
)
def test_california_boundary_rejects_bbox_spillover(
    name: str, lat: float, lon: float, expected: bool
) -> None:
    assert california_boundary.contains(lat, lon) is expected, name


def test_multipolygon_holes_and_boundaries() -> None:
    geometry = decode_multipolygon(
        {
            "type": "MultiPolygon",
            "coordinates": [
                [
                    [[0, 0], [4, 0], [4, 4], [0, 4], [0, 0]],
                    [[2, 2], [3, 2], [3, 3], [2, 3], [2, 2]],
                ],
                [[[10, 10], [11, 10], [11, 11], [10, 11], [10, 10]]],
            ],
        }
    )
    assert contains_point(geometry, 1.0, 1.0)  # first polygon interior
    assert not contains_point(geometry, 2.5, 2.5)  # hole interior is excluded
    assert contains_point(geometry, 2.0, 2.5)  # hole boundary belongs to the polygon boundary
    assert contains_point(geometry, 0.0, 1.0)  # exterior boundary is included
    assert contains_point(geometry, 10.5, 10.5)  # second polygon is included
    assert not contains_point(geometry, 8.0, 8.0)
    assert not contains_point(geometry, float("nan"), 1.0)


@pytest.mark.parametrize(
    "geometry",
    [
        None,
        {"type": "Polygon", "coordinates": []},
        {"type": "MultiPolygon", "coordinates": []},
        {"type": "MultiPolygon", "coordinates": [[]]},
        {"type": "MultiPolygon", "coordinates": [[None]]},
        {"type": "MultiPolygon", "coordinates": [[[[0]]]]},
        {
            "type": "MultiPolygon",
            "coordinates": [[[[0, 0], [1, 0], [1, 1], [0, 1]]]],
        },
        {
            "type": "MultiPolygon",
            "coordinates": [[[[True, 0], [1, 0], [1, 1], [True, 0]]]],
        },
        {
            "type": "MultiPolygon",
            "coordinates": [[[[float("inf"), 0], [1, 0], [1, 1], [float("inf"), 0]]]],
        },
    ],
)
def test_multipolygon_decoder_rejects_malformed_geometry(geometry: object) -> None:
    with pytest.raises(ValueError):
        decode_multipolygon(geometry)


def test_california_boundary_rejects_non_finite_coordinates() -> None:
    assert not california_boundary.contains(float("nan"), -121.49)
    assert not california_boundary.contains(38.58, float("inf"))


def test_california_boundary_includes_points_on_its_actual_edge() -> None:
    lon, lat = california_boundary._boundary()[0][0][0]
    assert california_boundary.contains(lat, lon)


@pytest.mark.parametrize(
    "location",
    [
        {},
        {"coordinates": []},
        {"coordinates": {"latitude": 38.5}},
        {"coordinates": {"latitude": "invalid", "longitude": -121.5}},
        {"coordinates": {"latitude": float("nan"), "longitude": -121.5}},
    ],
)
def test_openaq_coordinates_reject_malformed_or_non_finite(location: dict[str, Any]) -> None:
    assert openaq._coordinates(location) is None


def _pm(node: str, ts: str, value: float) -> Observation:
    return Observation(node_id=node, timestamp=ts, parameter="pm25_ugm3", value=value, unit="ug/m3")


def _ledger(
    location_id: int,
    *,
    license_id: int,
    license_name: str,
    fetched_at: str,
    valid_from: str | None = None,
    valid_to: str | None = None,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "source": "OpenAQ v3",
        "generated_at": fetched_at,
        "entries": [
            {
                "location_id": location_id,
                "license_id": license_id,
                "location_name": f"Site {location_id}",
                "provider": "Provider",
                "license_name": license_name,
                "license_url": "https://example.org/license",
                "attribution": "Provider",
                "attribution_url": "https://example.org/provider",
                "valid_from": valid_from,
                "valid_to": valid_to,
                "upstream_url": f"{openaq.API}/locations/{location_id}",
                "fetched_at": fetched_at,
                "unavailable_fields": [],
            }
        ],
        "excluded_locations": [],
    }


def _first_ledger_entry(ledger: dict[str, object]) -> dict[str, Any]:
    entries = ledger["entries"]
    assert isinstance(entries, list) and entries and isinstance(entries[0], dict)
    return entries[0]


def _attempt_attribute_change(target: object, name: str, value: object) -> None:
    setattr(target, name, value)


@pytest.mark.parametrize(
    ("field", "value"), [("location_id", True), ("location_id", 0), ("license_id", -1)]
)
def test_license_ledger_rejects_boolean_or_nonpositive_ids(field: str, value: object) -> None:
    ledger = _ledger(1, license_id=7, license_name="Terms A", fetched_at="2026-06-01T12:00:00Z")
    _first_ledger_entry(ledger)[field] = value
    assert not openaq.validate_license_ledger(ledger)


@pytest.mark.parametrize(
    ("target", "value"),
    [
        ("generated_at", "not-a-time"),
        ("generated_at", "2026-06-01T12:00:00+00:00"),
        ("generated_at", " 2026-06-01T12:00:00Z"),
        ("fetched_at", "2026-06-01"),
        ("fetched_at", "2026-06-01T12:00:00.123Z"),
    ],
)
def test_license_ledger_requires_canonical_utc_evidence_timestamps(target: str, value: str) -> None:
    ledger = _ledger(1, license_id=7, license_name="Terms A", fetched_at="2026-06-01T12:00:00Z")
    if target == "generated_at":
        ledger[target] = value
    else:
        _first_ledger_entry(ledger)[target] = value
    assert not openaq.validate_license_ledger(ledger)


def test_license_ledger_rejects_entry_fetched_after_document_generation() -> None:
    ledger = _ledger(1, license_id=7, license_name="Terms A", fetched_at="2026-06-01T12:00:00Z")
    _first_ledger_entry(ledger)["fetched_at"] = "2026-06-01T12:00:01Z"
    assert not openaq.validate_license_ledger(ledger)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("license_url", "http://example.org/license"),
        ("license_url", "https://"),
        ("upstream_url", "https://user@example.org/location"),
        ("attribution_url", "http://example.org/provider"),
        ("attribution_url", None),
    ],
)
def test_license_ledger_requires_typed_absolute_https_urls(field: str, value: object) -> None:
    ledger = _ledger(1, license_id=7, license_name="Terms A", fetched_at="2026-06-01T12:00:00Z")
    _first_ledger_entry(ledger)[field] = value
    assert not openaq.validate_license_ledger(ledger)


def test_license_ledger_requires_date_only_validity_boundaries() -> None:
    ledger = _ledger(1, license_id=7, license_name="Terms A", fetched_at="2026-06-01T12:00:00Z")
    _first_ledger_entry(ledger)["valid_from"] = "2026-06-01T00:00:00Z"
    assert not openaq.validate_license_ledger(ledger)


@pytest.mark.parametrize(
    "excluded",
    [
        None,
        {},
        [{"location_id": True, "location_name": "Site", "reason": "Missing terms"}],
        [{"location_id": 2, "location_name": "Site"}],
        [{"location_id": 2, "location_name": "Site", "reason": ""}],
        [
            {
                "location_id": 2,
                "location_name": "Site",
                "reason": "Missing terms",
                "unexpected": True,
            }
        ],
    ],
)
def test_license_ledger_rejects_malformed_excluded_locations(excluded: object) -> None:
    ledger = _ledger(1, license_id=7, license_name="Terms A", fetched_at="2026-06-01T12:00:00Z")
    ledger["excluded_locations"] = excluded
    assert not openaq.validate_license_ledger(ledger)


def test_normalized_license_ledger_is_immutable() -> None:
    ledger = _ledger(1, license_id=7, license_name="Terms A", fetched_at="2026-06-01T12:00:00Z")
    normalized = openaq._normalized_ledger(copy.deepcopy(ledger))
    assert normalized is not None
    with pytest.raises(FrozenInstanceError):
        _attempt_attribute_change(normalized, "generated_at", "2026-06-02T00:00:00Z")
    with pytest.raises(FrozenInstanceError):
        _attempt_attribute_change(normalized.entries[0], "license_name", "Changed")


def test_license_ledger_is_bound_to_location_identity_and_observation_time() -> None:
    ledger = _ledger(
        1,
        license_id=7,
        license_name="Terms A",
        fetched_at="2026-06-01T12:00:00Z",
        valid_from="2026-06-01",
        valid_to="2026-06-01",
    )
    assert openaq.validate_license_ledger(
        ledger, observations=[_pm("oaq-1", "2026-06-01T23:59:59Z", 10.0)]
    )
    assert not openaq.validate_license_ledger(
        ledger, observations=[_pm("oaq-2", "2026-06-01T12:00:00Z", 10.0)]
    )
    assert not openaq.validate_license_ledger(
        ledger, observations=[_pm("oaq-yuma", "2026-06-01T12:00:00Z", 10.0)]
    )
    assert not openaq.validate_license_ledger(
        ledger, observations=[_pm("oaq-1", "2026-06-02T00:00:00Z", 10.0)]
    )


def test_license_ledger_gaps_names_which_reading_and_why() -> None:  # #179
    ledger = _ledger(
        1,
        license_id=7,
        license_name="Terms A",
        fetched_at="2026-06-01T12:00:00Z",
        valid_from="2026-06-01",
        valid_to="2026-06-01",
    )
    # Covered: no gap reported at all.
    covered = [_pm("oaq-1", "2026-06-01T23:59:59Z", 10.0)]
    assert openaq.license_ledger_gaps(ledger, observations=covered) == []
    # A location the ledger has never heard of.
    [gap] = openaq.license_ledger_gaps(
        ledger, observations=[_pm("oaq-2", "2026-06-01T12:00:00Z", 10.0)]
    )
    assert "location 2" in gap and "no license entry at all" in gap
    # A malformed node id, distinguished from a missing-entry location.
    [gap] = openaq.license_ledger_gaps(
        ledger, observations=[_pm("oaq-yuma", "2026-06-01T12:00:00Z", 10.0)]
    )
    assert "oaq-yuma" in gap and "not an OpenAQ node id" in gap
    # A real entry for this location that doesn't cover this reading's date.
    [gap] = openaq.license_ledger_gaps(
        ledger, observations=[_pm("oaq-1", "2026-06-02T00:00:00Z", 10.0)]
    )
    assert "location 1" in gap and "2026-06-02T00:00:00Z" in gap and "none covers" in gap
    # A malformed ledger (not per-observation) gets its own, distinct message -- and says which
    # rule refused it, rather than one blanket sentence for every possible cause (#179).
    assert openaq.license_ledger_gaps(None, observations=[_pm("oaq-1", "x", 10.0)]) == [
        "ledger is not publishable: ledger is NoneType, not an object"
    ]
    # Repeat gaps from the same dead location collapse to one line, not one per reading.
    gaps = openaq.license_ledger_gaps(
        ledger,
        observations=[
            _pm("oaq-2", "2026-06-01T12:00:00Z", 10.0),
            _pm("oaq-2", "2026-06-01T13:00:00Z", 11.0),
        ],
    )
    assert len(gaps) == 1


def test_merge_license_ledgers_preserves_changed_historical_terms() -> None:
    first = _ledger(
        1,
        license_id=7,
        license_name="Terms A",
        fetched_at="2026-06-01T12:00:00Z",
        valid_from="2026-06-01",
        valid_to="2026-06-01",
    )
    second = _ledger(
        1,
        license_id=8,
        license_name="Terms B",
        fetched_at="2026-06-02T12:00:00Z",
        valid_from="2026-06-02",
    )
    merged = openaq.merge_license_ledgers(first, second)
    assert {entry["license_id"] for entry in merged["entries"]} == {7, 8}
    assert openaq.validate_license_ledger(
        merged,
        observations=[
            _pm("oaq-1", "2026-06-01T12:00:00Z", 10.0),
            _pm("oaq-1", "2026-06-02T12:00:00Z", 11.0),
        ],
    )


def test_to_snapshot_keeps_source_timestamps_and_drops_stale() -> None:
    # /latest readings arrive on each sensor's own clock. Stale rows are removed, but factual
    # timestamps remain unchanged so data and license-period provenance stay intact.
    obs = [
        _pm("oaq-1", "2026-06-17T21:50:00Z", 10.0),
        _pm("oaq-2", "2026-06-17T21:05:00Z", 20.0),
        _pm("oaq-3", "2026-06-17T10:00:00Z", 99.0),  # >6h older than newest → dropped
    ]
    snap = openaq._to_snapshot(obs)
    assert {o.timestamp for o in snap} == {
        "2026-06-17T21:50:00Z",
        "2026-06-17T21:05:00Z",
    }
    assert {o.node_id for o in snap} == {"oaq-1", "oaq-2"}  # the stale site is gone


# -- the ledger the whole state was refused over (#179) -----------------------
#
# `build_license_ledger` and `validate_license_ledger` used to disagree: the builder emitted
# entries the ledger normalizer refuses, and because normalization is all-or-nothing, one such
# location made every *other* California location's terms unpublishable too. Every `demo` run
# from 2026-08-16 onward then refused with a message that named nothing at all.


def _catalog(license_id: int = 33) -> dict[int, dict[str, Any]]:
    return {
        license_id: {
            "id": license_id,
            "name": "US Public Domain",
            "sourceUrl": "https://www.usa.gov/government-copyright",
        }
    }


def _location(location_id: int, **overrides: Any) -> dict[str, Any]:
    location: dict[str, Any] = {
        "id": location_id,
        "name": f"Site {location_id}",
        "coordinates": {"latitude": 38.58, "longitude": -121.49},  # Sacramento, inside CA
        "provider": {"id": 119, "name": "AirNow"},
        "licenses": [{"id": 33, "attribution": {"name": "AirNow", "url": None}}],
    }
    location.update(overrides)
    return location


def test_one_unlicensable_location_no_longer_voids_every_other_location() -> None:
    """The regression #179 is actually about: a per-location refusal, not a statewide one."""
    ledger = openaq.build_license_ledger(
        [
            _location(1),
            # OpenAQ named a license but neither a provider nor an attribution to credit. The
            # builder used to emit this as an entry, which the normalizer then refused --
            # taking location 1's perfectly good terms down with it.
            _location(2, provider={}, licenses=[{"id": 33, "attribution": {}}]),
        ],
        _catalog(),
        fetched_at="2026-09-01T00:00:00Z",
    )
    assert [entry["location_id"] for entry in ledger["entries"]] == [1]
    [excluded] = ledger["excluded_locations"]
    assert excluded["location_id"] == 2
    assert "provider" in excluded["reason"] and "attribution" in excluded["reason"]
    # Location 1 is publishable, and its reading is covered.
    assert openaq.validate_license_ledger(
        ledger, observations=[_pm("oaq-1", "2026-09-01T00:00:00Z", 10.0)]
    )
    # Location 2 is still refused -- by name, and only for itself.
    [gap] = openaq.license_ledger_gaps(
        ledger, observations=[_pm("oaq-2", "2026-09-01T00:00:00Z", 10.0)]
    )
    assert "location 2" in gap and "no license entry at all" in gap


@pytest.mark.parametrize(
    "licenses",
    [
        # A license validity boundary that is a timestamp rather than a date.
        [{"id": 33, "dateFrom": "2016-01-30T00:00:00Z"}],
        # A license whose canonical source URL is not HTTPS (catalog id 44, below).
        [{"id": 44}],
        # Validity that ends before it starts.
        [{"id": 33, "dateFrom": "2026-02-01", "dateTo": "2026-01-01"}],
    ],
)
def test_a_location_openaq_describes_unusably_is_excluded_not_emitted(
    licenses: list[dict[str, Any]],
) -> None:
    catalog = _catalog() | {44: {"id": 44, "name": "Terms", "sourceUrl": "http://x.example/terms"}}
    ledger = openaq.build_license_ledger(
        [_location(1), _location(2, licenses=licenses)], catalog, fetched_at="2026-09-01T00:00:00Z"
    )
    assert [entry["location_id"] for entry in ledger["entries"]] == [1]
    assert [item["location_id"] for item in ledger["excluded_locations"]] == [2]
    assert openaq.validate_license_ledger(ledger)


def test_build_license_ledger_never_emits_an_entry_its_own_validator_refuses() -> None:
    """The invariant that makes the statewide blackout unreachable, stated once."""
    ledger = openaq.build_license_ledger(
        [
            _location(1),
            _location(2, provider={}, licenses=[{"id": 33, "attribution": {}}]),
            _location(3, name="  Padded Name  ", provider={"name": " AirNow "}),
            _location(4, licenses=[]),
            _location(5, licenses=[{"id": 33}, {"id": 33}]),  # same license listed twice
        ],
        _catalog(),
        fetched_at="2026-09-01T00:00:00Z",
    )
    assert ledger["entries"], "at least one location must survive"
    assert openaq.validate_license_ledger(ledger)
    # Upstream whitespace is trimmed, not treated as a reason to refuse the state.
    [padded] = [e for e in ledger["entries"] if e["location_id"] == 3]
    assert padded["location_name"] == "Padded Name"
    assert padded["provider"] == "AirNow"
    # A license listed twice collapses rather than tripping the duplicate-identity rule.
    assert len([e for e in ledger["entries"] if e["location_id"] == 5]) == 1


def _exclusion_reason(ledger: dict[str, Any], location_id: int) -> str:
    [excluded] = [
        item for item in ledger["excluded_locations"] if item["location_id"] == location_id
    ]
    return str(excluded["reason"])


def test_a_url_refusal_names_the_field_and_the_rule_it_broke() -> None:
    """Which of the three URL fields, and how -- the evidence #179 could not get otherwise.

    On 2026-09-06 the scheduled `demo` run (34036381920) refused all 250 California locations
    with "250 x OpenAQ license metadata is not publishable: OpenAQ ledger URLs must be absolute
    credential-free HTTPS URLs". OpenAQ *was* returning license metadata; something about a URL
    in it stopped being publishable. But `license_url` comes from the license catalog,
    `attribution_url` comes from the location, and `upstream_url` swelter builds itself, and one
    sentence covered all three -- so the log could not say which one the provider changed, or
    how, and the issue's next step was "reproduce it with the API key".
    """
    catalog = _catalog() | {
        44: {"id": 44, "name": "Terms", "sourceUrl": "http://x.example/terms"},
        45: {"id": 45, "name": "Terms", "sourceUrl": "/licenses/45"},
    }
    ledger = openaq.build_license_ledger(
        [
            _location(1),
            _location(2, licenses=[{"id": 44, "attribution": {"name": "AirNow", "url": None}}]),
            _location(3, licenses=[{"id": 45, "attribution": {"name": "AirNow", "url": None}}]),
            _location(
                4,
                licenses=[
                    {"id": 33, "attribution": {"name": "AirNow", "url": "http://x.example/who"}}
                ],
            ),
        ],
        catalog,
        fetched_at="2026-09-01T00:00:00Z",
    )

    assert [entry["location_id"] for entry in ledger["entries"]] == [1]
    assert openaq.validate_license_ledger(ledger)

    not_https = _exclusion_reason(ledger, 2)
    assert "license_url" in not_https and "attribution_url" not in not_https
    assert "'http'" in not_https

    relative = _exclusion_reason(ledger, 3)
    assert "license_url" in relative and "relative" in relative

    attribution = _exclusion_reason(ledger, 4)
    assert "attribution_url" in attribution and "license_url" not in attribution
    assert "'http'" in attribution


def test_a_url_refusal_never_echoes_the_url_it_refused() -> None:
    """The one refusal that must stay categorical: a URL rejected for carrying credentials.

    CLAUDE.md forbids logging credential-bearing URLs, and this reason is written into the
    published ledger's `excluded_locations`, so echoing the offending value would put a secret
    in a public artifact. Name the field and the rule; never the URL.
    """
    catalog = _catalog() | {
        46: {"id": 46, "name": "Terms", "sourceUrl": "https://user:hunter2@x.example/terms"}
    }
    ledger = openaq.build_license_ledger(
        [
            _location(1),
            _location(2, licenses=[{"id": 46, "attribution": {"name": "AirNow", "url": None}}]),
        ],
        catalog,
        fetched_at="2026-09-01T00:00:00Z",
    )

    reason = _exclusion_reason(ledger, 2)
    assert "license_url" in reason and "embeds credentials" in reason
    for secret in ("hunter2", "user:", "x.example", "https://user"):
        assert secret not in reason, reason


def test_a_refused_ledger_says_which_rule_refused_it() -> None:
    """A refusal an operator can act on, instead of one blanket sentence for every cause."""
    good = _ledger(1, license_id=7, license_name="Terms A", fetched_at="2026-06-01T12:00:00Z")
    reading = [_pm("oaq-1", "2026-06-01T12:00:00Z", 10.0)]

    def reason(ledger: object) -> str:
        [line] = openaq.license_ledger_gaps(ledger, observations=reading)
        assert line.startswith("ledger is not publishable: ")
        return line

    assert "not an object" in reason(None)
    assert "schema_version" in reason({**good, "schema_version": 2})
    assert "source" in reason({**good, "source": "OpenAQ v2"})
    assert "no entries at all" in reason({**good, "entries": []})
    assert "top-level fields" in reason({k: v for k, v in good.items() if k != "entries"})
    # The one that matters most: a single bad entry names its own location, not the document.
    entries = good["entries"]
    assert isinstance(entries, list)
    broken = copy.deepcopy(entries[0])
    assert isinstance(broken, dict)
    broken["license_url"] = "http://example.org/license"
    detail = reason({**good, "entries": [broken]})
    assert "location 1" in detail and "HTTPS" in detail
    # Duplicate identities are distinguished from a malformed entry.
    assert "repeats an entry identity" in reason(
        {**good, "entries": [copy.deepcopy(entries[0]), copy.deepcopy(entries[0])]}
    )


def test_licensing_all_of_california_out_is_a_refusal_not_an_empty_dataset() -> None:
    """A licensing refusal must not reach the operator as "no readings returned" (#179).

    Observed live on 2026-09-02, run 33584560625: after per-location exclusion landed, OpenAQ
    excluded every California location, so nothing was requested, `fetch` returned `[]`, and the
    CLI reported `swelter: no readings returned from OpenAQ` in 3.3s. That is false -- OpenAQ
    returned locations and swelter declined to publish them. The refusal has to say so, and say
    which rule declined them, or a licensing problem is indistinguishable from an outage.
    """
    unlicensable = [
        _location(i, provider={}, licenses=[{"id": 33, "attribution": {}}]) for i in (1, 2, 3)
    ]

    def _no_network(*_: object, **__: object) -> object:  # pragma: no cover - must never run
        raise AssertionError("no per-location request may be made once every location is excluded")

    with (
        mock.patch.object(openaq, "_locations", return_value=unlicensable),
        mock.patch.object(openaq, "_license_catalog", return_value=_catalog()),
        mock.patch.object(openaq, "_get_json", _no_network),
        pytest.raises(SourceError) as refusal,
    ):
        openaq.fetch("key", throttle_s=0)
    message = str(refusal.value)
    assert "licensed none of its 3 California locations" in message
    # The rule, tallied, rather than one line per location.
    assert "3 x " in message and "provider/attribution availability evidence" in message


def test_a_partly_licensed_state_still_fetches_the_licensed_part() -> None:
    """The refusal above must not fire whenever *any* location is excluded."""
    locations = [
        _location(1),
        _location(2, provider={}, licenses=[{"id": 33, "attribution": {}}]),
    ]
    requested: list[str] = []

    def _payload(url: str, *_: object, **__: object) -> dict[str, Any]:
        requested.append(url)
        return {"results": []}

    with (
        mock.patch.object(openaq, "_locations", return_value=locations),
        mock.patch.object(openaq, "_license_catalog", return_value=_catalog()),
        mock.patch.object(openaq, "_get_json", _payload),
    ):
        observations, nodes = openaq.fetch("key", throttle_s=0)
    assert observations == [] and nodes == {}
    # Location 1 was asked for; location 2, excluded, never was.
    assert any("/locations/1/latest" in url for url in requested)
    assert not any("/locations/2/latest" in url for url in requested)


def test_exclusion_summary_ranks_reasons_by_how_many_locations_hit_them() -> None:
    ledger = {
        "excluded_locations": [
            {"location_id": 1, "location_name": "A", "reason": "rule one"},
            {"location_id": 2, "location_name": "B", "reason": "rule two"},
            {"location_id": 3, "location_name": "C", "reason": "rule one"},
        ]
    }
    assert openaq._exclusion_summary(ledger) == "2 x rule one; 1 x rule two"
    assert openaq._exclusion_summary(ledger, limit=1) == "2 x rule one (+1 other reason(s))"
    assert openaq._exclusion_summary({"excluded_locations": []}) == (
        "no exclusion reasons were recorded"
    )
