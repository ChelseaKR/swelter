"""Pure-function tests for the checked-in node firmware sensor drivers (F19).

The reference firmware used to ship two unbound stub drivers — ``Sht31.read()`` and
``PmSensor.read()`` both raised "driver not bound", so a freshly built node read nothing.
Real drivers now live in ``firmware/src/drivers/`` (``sht31.py``, ``pms5003.py``), and this
test exercises their hardware-free logic on desktop CPython:

* the SHT31 CRC-8 against the datasheet's worked example, plus the datasheet conversion;
* ``pms5003.parse_frame`` on a hand-built valid frame and a checksum-broken one.

The firmware is not an installed package (it is MicroPython source copied flat to a node), so
the two driver modules are loaded directly from ``firmware/src`` with importlib. Only the pure
functions are touched here, so nothing hardware-only is imported and mypy ``--strict`` stays
green with the dynamically loaded symbols pinned to typed locals.
"""

from __future__ import annotations

import importlib.util
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import pytest

_FIRMWARE_DRIVERS = Path(__file__).resolve().parents[1] / "firmware" / "src" / "drivers"


def _load_firmware_module(name: str) -> ModuleType:
    """Load a firmware driver module from ``firmware/src`` by file path."""
    path = _FIRMWARE_DRIVERS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"_firmware_{name}", path)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise ImportError(f"could not load firmware module {name} from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_sht31 = _load_firmware_module("sht31")
_pms5003 = _load_firmware_module("pms5003")

# Pin the dynamically loaded callables/classes to typed locals so mypy --strict can check use.
_crc8: Callable[[bytes], int] = _sht31.crc8
_convert_raw: Callable[[int, int], tuple[float, float]] = _sht31.convert_raw
_parse_measurement: Callable[[bytes], tuple[float, float]] = _sht31.parse_measurement
_Sht31Error: type[Exception] = _sht31.Sht31Error

_parse_frame: Callable[[bytes], dict[str, int]] = _pms5003.parse_frame
_Pms5003Error: type[Exception] = _pms5003.Pms5003Error


# -- SHT31 ----------------------------------------------------------------------------------------


def test_sht31_crc8_matches_datasheet_example() -> None:
    # Sensirion SHT3x datasheet worked example: CRC of 0xBE 0xEF is 0x92.
    assert _crc8(bytes((0xBE, 0xEF))) == 0x92


def test_sht31_convert_raw_rails() -> None:
    # Raw 0 -> minimum of each scale; raw full-scale -> the datasheet maxima.
    temp_lo, rh_lo = _convert_raw(0, 0)
    assert temp_lo == pytest.approx(-45.0)
    assert rh_lo == pytest.approx(0.0)

    temp_hi, rh_hi = _convert_raw(65535, 65535)
    assert temp_hi == pytest.approx(130.0)  # -45 + 175
    assert rh_hi == pytest.approx(100.0)


def test_sht31_convert_raw_midscale() -> None:
    # Half-scale: temp_c = -45 + 175 * 0.5 = 42.5; rh = 50.0.
    temp_c, rh = _convert_raw(0x8000, 0x8000)
    assert temp_c == pytest.approx(-45.0 + 175.0 * 0x8000 / 65535.0)
    assert rh == pytest.approx(100.0 * 0x8000 / 65535.0)
    assert 42.0 < temp_c < 43.0


def _sht31_frame(raw_temp: int, raw_humidity: int) -> bytes:
    """Build a valid 6-byte SHT31 response with correct per-word CRCs."""
    t_msb, t_lsb = (raw_temp >> 8) & 0xFF, raw_temp & 0xFF
    h_msb, h_lsb = (raw_humidity >> 8) & 0xFF, raw_humidity & 0xFF
    return bytes(
        (
            t_msb,
            t_lsb,
            _crc8(bytes((t_msb, t_lsb))),
            h_msb,
            h_lsb,
            _crc8(bytes((h_msb, h_lsb))),
        )
    )


def test_sht31_parse_measurement_roundtrip() -> None:
    # ~25 C, ~50 %RH chosen via the inverse of the datasheet conversion.
    raw_temp = round((25.0 + 45.0) / 175.0 * 65535.0)
    raw_humidity = round(50.0 / 100.0 * 65535.0)
    temp_c, humidity_pct = _parse_measurement(_sht31_frame(raw_temp, raw_humidity))
    assert temp_c == pytest.approx(25.0, abs=0.01)
    assert humidity_pct == pytest.approx(50.0, abs=0.01)


def test_sht31_parse_measurement_rejects_bad_crc() -> None:
    frame = bytearray(_sht31_frame(0x6400, 0x8000))
    frame[2] ^= 0xFF  # corrupt the temperature word's CRC
    with pytest.raises(_Sht31Error):
        _parse_measurement(bytes(frame))


def test_sht31_parse_measurement_rejects_short_buffer() -> None:
    with pytest.raises(_Sht31Error):
        _parse_measurement(b"\x00\x00\x00")


# -- PMS5003 --------------------------------------------------------------------------------------


def _pms5003_frame(pm1_0: int, pm2_5: int, pm10: int) -> bytes:
    """Build a valid 32-byte PMS5003 frame with the given atmospheric concentrations.

    Bytes 4-9 are the CF=1 fields (left zero), 10-15 the atmospheric fields, and the final two
    bytes are the big-endian sum of the first 30. Particle-count fields are left zero.
    """
    body = bytearray(30)
    body[0] = 0x42
    body[1] = 0x4D
    body[2] = 0x00  # frame length high
    body[3] = 28  # frame length low (28 bytes follow this field)
    # Atmospheric-environment concentrations at offsets 10, 12, 14.
    body[10], body[11] = (pm1_0 >> 8) & 0xFF, pm1_0 & 0xFF
    body[12], body[13] = (pm2_5 >> 8) & 0xFF, pm2_5 & 0xFF
    body[14], body[15] = (pm10 >> 8) & 0xFF, pm10 & 0xFF
    checksum = sum(body) & 0xFFFF
    return bytes(body) + bytes(((checksum >> 8) & 0xFF, checksum & 0xFF))


def test_pms5003_parse_frame_reads_atmospheric_concentrations() -> None:
    frame = _pms5003_frame(pm1_0=10, pm2_5=19, pm10=33)
    fields = _parse_frame(frame)
    assert fields["pm25_ugm3"] == 19
    assert fields["pm10_ugm3"] == 33
    assert fields["pm1_0_ugm3"] == 10
    assert fields["frame_length"] == 28


def test_pms5003_parse_frame_rejects_bad_checksum() -> None:
    frame = bytearray(_pms5003_frame(pm1_0=10, pm2_5=19, pm10=33))
    frame[-1] ^= 0xFF  # corrupt the checksum low byte
    with pytest.raises(_Pms5003Error):
        _parse_frame(bytes(frame))


def test_pms5003_parse_frame_rejects_bad_header() -> None:
    frame = bytearray(_pms5003_frame(pm1_0=10, pm2_5=19, pm10=33))
    frame[0] = 0x00  # break the start byte; checksum no longer matters
    with pytest.raises(_Pms5003Error):
        _parse_frame(bytes(frame))


def test_pms5003_parse_frame_rejects_wrong_length() -> None:
    with pytest.raises(_Pms5003Error):
        _parse_frame(b"\x42\x4d\x00\x1c")
