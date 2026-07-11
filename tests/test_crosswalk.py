"""The outbound crosswalk (swelter → OpenAQ / Sensor.Community) is complete and provably
symmetric with the inbound adapters it inverts.
"""

from __future__ import annotations

from swelter import crosswalk
from swelter.models import PARAMETERS
from swelter.sources import openaq, sensor_community


def test_every_swelter_parameter_is_covered() -> None:
    table = crosswalk.crosswalk_table()
    covered = {row["swelter_param"] for row in table}
    assert covered == set(PARAMETERS)


def test_table_rows_carry_swelter_unit() -> None:
    table = crosswalk.crosswalk_table()
    units = {row["swelter_param"]: row["swelter_unit"] for row in table}
    for name, param in PARAMETERS.items():
        assert units[name] == param.unit


def test_to_openaq_inverts_the_inbound_openaq_map() -> None:
    # Invert sources/openaq.py _PARAM: openaq name -> (swelter param, unit). For every swelter
    # param that map produces, to_openaq must round-trip back to that exact (name, unit).
    inbound = {
        swelter_param: (oaq_name, unit) for oaq_name, (swelter_param, unit) in openaq._PARAM.items()
    }
    for swelter_param, (oaq_name, unit) in inbound.items():
        assert crosswalk.to_openaq(swelter_param) == (oaq_name, unit)


def test_to_sensor_community_inverts_the_inbound_sensor_community_map() -> None:
    inbound = {
        swelter_param: (value_type, unit)
        for value_type, (swelter_param, unit) in sensor_community._MAP.items()
    }
    for swelter_param, (value_type, unit) in inbound.items():
        assert crosswalk.to_sensor_community(swelter_param) == (value_type, unit)


def test_heat_index_has_no_commons_equivalent() -> None:
    assert crosswalk.to_openaq("heat_index_c") is None
    assert crosswalk.to_sensor_community("heat_index_c") is None


def test_no2_has_no_sensor_community_equivalent() -> None:
    assert crosswalk.to_sensor_community("no2_ppb") is None
    # OpenAQ does name NO2, but the unit is recorded honestly (no conversion performed) —
    # there is no inbound OpenAQ NO2 adapter to invert against, so just confirm it resolves.
    assert crosswalk.to_openaq("no2_ppb") is not None


def test_unknown_parameter_returns_none() -> None:
    assert crosswalk.to_openaq("not_a_real_param") is None
    assert crosswalk.to_sensor_community("not_a_real_param") is None


def test_crosswalk_table_row_shape() -> None:
    table = crosswalk.crosswalk_table()
    row = next(r for r in table if r["swelter_param"] == "pm25_ugm3")
    assert row == {
        "swelter_param": "pm25_ugm3",
        "swelter_unit": "ug/m3",
        "openaq_param": "pm25",
        "openaq_unit": "ug/m3",
        "sensor_community_value_type": "P2",
        "sensor_community_unit": "ug/m3",
    }
    hi_row = next(r for r in table if r["swelter_param"] == "heat_index_c")
    assert hi_row["openaq_param"] is None
    assert hi_row["sensor_community_value_type"] is None
