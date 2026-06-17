"""Sensirion SHT31 temperature/humidity driver over I2C.

The SHT31-D is the temp/humidity part in ``firmware/hardware/BOM.md``. This is a real,
documented driver for it, not a stub: it issues the single-shot high-repeatability
measurement command, reads the 6-byte response, verifies the CRC-8 of each 2-byte word, and
converts the raw counts to engineering units per the datasheet.

The logic is split so it is testable on desktop CPython without any hardware:

* :func:`crc8` and :func:`convert_raw` are pure functions — given bytes/ints they return
  numbers, with no I2C anywhere — so the CRC verification and the datasheet conversion are
  exercised directly by ``tests/test_firmware_drivers.py``.
* :class:`Sht31` is the bound driver. Its constructor takes a MicroPython ``machine.I2C``
  bus object (anything with ``writeto`` and ``readfrom``), so it imports cleanly on CPython
  and only touches hardware when :meth:`read` is actually called on a node.

Datasheet references (Sensirion SHT3x-DIS, rev. 6):

* Single-shot, clock-stretching disabled, high repeatability: command ``0x2C 0x06``.
* Response: 6 bytes — ``[T_msb, T_lsb, T_crc, RH_msb, RH_lsb, RH_crc]``.
* CRC-8: polynomial ``0x31`` (x^8 + x^5 + x^4 + 1), initialisation ``0xFF``, no final XOR,
  MSB-first, computed over the two preceding data bytes.
* Temperature: ``temp_c = -45 + 175 * raw / 65535``.
* Relative humidity: ``rh = 100 * raw / 65535``.
"""

from __future__ import annotations

# Single-shot, high-repeatability, clock stretching disabled (datasheet table "Measurement
# Commands for Single Shot Data Acquisition Mode"). Sent MSB first as two bytes.
MEASURE_HIGH_REPEATABILITY = b"\x2c\x06"

# Default 7-bit I2C address with the ADDR pin tied low (0x44); 0x45 if tied high.
DEFAULT_ADDRESS = 0x44

# Datasheet conversion constants.
_TEMP_OFFSET_C = -45.0
_TEMP_SPAN_C = 175.0
_RH_SPAN_PCT = 100.0
_RAW_FULL_SCALE = 65535.0

# CRC-8 parameters (datasheet section "Checksum Calculation").
_CRC_POLYNOMIAL = 0x31
_CRC_INIT = 0xFF


class Sht31Error(Exception):
    """An SHT31 read failed — a CRC mismatch, a short read, or a bus error."""


def crc8(data: bytes) -> int:
    """Return the SHT31 CRC-8 of ``data`` (polynomial 0x31, init 0xFF, MSB-first).

    Pure Python on purpose: the checksum the sensor sends with each 2-byte word is verified
    by recomputing it here, and this same function is unit-tested on CPython against the
    datasheet's worked example (``0xBE 0xEF`` checksums to ``0x92``).
    """
    crc = _CRC_INIT
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x80:
                crc = ((crc << 1) ^ _CRC_POLYNOMIAL) & 0xFF
            else:
                crc = (crc << 1) & 0xFF
    return crc


def _word(msb: int, lsb: int, crc: int) -> int:
    """Verify the CRC of one 2-byte word and return it as a 16-bit unsigned int."""
    if crc8(bytes((msb, lsb))) != crc:
        raise Sht31Error("SHT31 CRC mismatch on data word")
    return (msb << 8) | lsb


def convert_raw(raw_temp: int, raw_humidity: int) -> tuple[float, float]:
    """Convert raw 16-bit counts to ``(temp_c, humidity_pct)`` per the datasheet.

    ``temp_c = -45 + 175 * raw / 65535`` and ``rh = 100 * raw / 65535``. Relative humidity is
    clamped to ``[0, 100]`` because rounding at the rails can otherwise nudge it a hair past
    100 %, which the pipeline's range QC would reject.
    """
    temp_c = _TEMP_OFFSET_C + _TEMP_SPAN_C * raw_temp / _RAW_FULL_SCALE
    humidity_pct = _RH_SPAN_PCT * raw_humidity / _RAW_FULL_SCALE
    humidity_pct = min(100.0, max(0.0, humidity_pct))
    return (temp_c, humidity_pct)


def parse_measurement(buf: bytes) -> tuple[float, float]:
    """Parse and CRC-check a 6-byte SHT31 measurement into ``(temp_c, humidity_pct)``.

    Pure function over the raw response bytes so the whole parse-and-verify path is testable
    off-hardware. Raises :class:`Sht31Error` on a short buffer or a CRC mismatch.
    """
    if len(buf) != 6:
        raise Sht31Error("SHT31 expected 6 bytes, got %d" % len(buf))
    raw_temp = _word(buf[0], buf[1], buf[2])
    raw_humidity = _word(buf[3], buf[4], buf[5])
    return convert_raw(raw_temp, raw_humidity)


class Sht31:
    """SHT31 temperature/humidity sensor on a MicroPython ``machine.I2C`` bus.

    Parameters
    ----------
    i2c:
        A MicroPython I2C bus (``machine.I2C``) — any object exposing ``writeto(addr, buf)``
        and ``readfrom(addr, n) -> bytes``. Passed in by ``main.build_sampler`` on the node.
    address:
        7-bit I2C address; ``0x44`` (ADDR low) by default, ``0x45`` if ADDR is tied high.

    The constructor does no I/O, so creating one on CPython for review is harmless; the bus is
    only touched in :meth:`read`.
    """

    def __init__(self, i2c: object, address: int = DEFAULT_ADDRESS) -> None:
        self._i2c = i2c
        self._address = address

    def read(self) -> tuple[float, float]:
        """Take one high-repeatability measurement and return ``(temp_c, humidity_pct)``.

        Sends the measurement command, waits the datasheet's worst-case 15 ms conversion time,
        reads the 6-byte response, verifies both CRCs, and converts to engineering units.
        Raises :class:`Sht31Error` on a CRC mismatch or any bus error.
        """
        try:
            self._i2c.writeto(self._address, MEASURE_HIGH_REPEATABILITY)
            self._sleep_ms(15)  # high-repeatability conversion: ~12.5 ms typ, 15 ms max
            buf = bytes(self._i2c.readfrom(self._address, 6))
        except Sht31Error:
            raise
        except Exception as exc:  # bus error, NACK, wiring fault
            raise Sht31Error("SHT31 I2C transfer failed: %s" % exc)
        return parse_measurement(buf)

    @staticmethod
    def _sleep_ms(ms: int) -> None:
        """Block for ``ms`` milliseconds, using whichever sleep the runtime provides."""
        try:
            import time

            sleep_ms = getattr(time, "sleep_ms", None)
            if sleep_ms is not None:  # MicroPython
                sleep_ms(ms)
            else:  # CPython
                time.sleep(ms / 1000.0)
        except Exception:  # pragma: no cover - a missing clock should not break a read
            pass
