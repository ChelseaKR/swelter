"""Sensor drivers for the swelter reference node.

These are real, documented drivers for the sensors in ``firmware/hardware/BOM.md`` — not
stubs. Each splits its wire protocol into a pure, hardware-free parse/convert path (unit-
tested on desktop CPython by ``tests/test_firmware_drivers.py``) and a thin bound class that
talks to the MicroPython ``machine`` bus on the node.

* :class:`~drivers.sht31.Sht31` — Sensirion SHT31 temperature/humidity over I2C.
* :class:`~drivers.pms5003.Pms5003` — Plantower PMS5003 PM2.5/PM10 over UART.

``sampler.py`` binds these to its ``Sht31``/``PmSensor`` sensor slots when a bus is present,
and falls back gracefully (no reading rather than an invented value) when it is not.
"""

from __future__ import annotations

from pms5003 import Pms5003, Pms5003Error, parse_frame
from sht31 import Sht31, Sht31Error, convert_raw, crc8, parse_measurement

__all__ = [
    "Pms5003",
    "Pms5003Error",
    "Sht31",
    "Sht31Error",
    "convert_raw",
    "crc8",
    "parse_frame",
    "parse_measurement",
]
