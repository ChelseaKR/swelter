"""Read the node's sensors and assemble one wide payload per sample.

This module is the only place the firmware touches sensor hardware. Everything it returns is
already in the shape ``src/swelter/ingest.py`` expects: a flat dict with ``node_id``,
``timestamp`` (ISO-8601 UTC, ``...Z``), and the parameters the node sampled, named and united
exactly as ``swelter.models.PARAMETERS`` defines them.

The node emits **raw** values only. It never applies calibration — correcting a low-cost sensor
against a reference monitor is the pipeline's job, and keeping it out of the firmware is what
keeps calibrated and raw distinguishable downstream.

Hardware-only imports (``machine`` and the sensor drivers) are deferred to call time and guarded,
so this module imports cleanly on desktop CPython for review and for ``python -m compileall``. On
the node, MicroPython supplies them; off the node, a sampler runs against an injected fake or a
constant reading.
"""

from __future__ import annotations

# Parameter keys and units, copied to match swelter.models.PARAMETERS. Kept here so the firmware
# has no dependency on the server package; a drift between the two is a review failure.
PARAM_UNITS = {
    "temp_c": "degC",
    "humidity_pct": "%",
    "pm25_ugm3": "ug/m3",
    "pm10_ugm3": "ug/m3",
    "heat_index_c": "degC",
}

# Below this temperature the NWS heat-index regression is not meaningful; return air temperature.
_HEAT_INDEX_FLOOR_C = 26.7


def heat_index_c(temp_c, humidity_pct):
    """NWS heat index (Rothfusz regression), Celsius in and out.

    Identical to ``swelter.models.heat_index_c`` so the on-device value and the pipeline fallback
    agree to the rounding. Below 26.7 degC the air temperature is returned unchanged.
    """
    if temp_c < _HEAT_INDEX_FLOOR_C:
        return round(temp_c, 2)
    t = temp_c * 9 / 5 + 32  # the regression is defined in Fahrenheit
    r = humidity_pct
    hi = (
        -42.379
        + 2.04901523 * t
        + 10.14333127 * r
        - 0.22475541 * t * r
        - 0.00683783 * t * t
        - 0.05481717 * r * r
        + 0.00122874 * t * t * r
        + 0.00085282 * t * r * r
        - 0.00000199 * t * t * r * r
    )
    return round((hi - 32) * 5 / 9, 2)


def _utc_timestamp():
    """Return the current time as ``YYYY-MM-DDTHH:MM:SSZ``.

    On the node this reads the RTC, kept in UTC and disciplined by SNTP at boot (see main.py).
    On CPython it falls back to the standard library so the module is testable off-hardware.
    """
    try:
        import time as _time

        # MicroPython exposes gmtime(); both runtimes return a 9-tuple starting (Y, M, D, h, m, s).
        y, mo, d, h, mi, s = _time.gmtime()[:6]
    except Exception:  # pragma: no cover - defensive; gmtime exists on both runtimes
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        y, mo, d, h, mi, s = (now.year, now.month, now.day, now.hour, now.minute, now.second)
    return "%04d-%02d-%02dT%02d:%02d:%02dZ" % (y, mo, d, h, mi, s)


class SensorError(Exception):
    """A sensor read failed. The caller drops the parameter rather than reporting a guess."""


class Sht31:
    """SHT31 temperature/humidity over I2C, backed by the real driver in ``drivers/sht31.py``.

    The driver module is imported lazily inside :meth:`read`, not at module load, so this file
    stays import-safe on desktop CPython and passes ``python -m compileall``. With no I2C bus
    (off-hardware review/CI) the sensor reports a clean :class:`SensorError`, which the sampler
    treats as "this parameter is absent this cycle" — never an invented value.
    """

    def __init__(self, i2c=None, address=0x44):
        self._i2c = i2c
        self._address = address

    def read(self):
        """Return ``(temp_c, humidity_pct)``. Raises :class:`SensorError` on a bus failure."""
        if self._i2c is None:
            raise SensorError("no I2C bus configured for SHT31")
        try:
            # Bound to the checked-in SHT31 driver. Imported here, not at module load, so the
            # import only runs on the node where the driver module is present alongside this one.
            from sht31 import Sht31 as Sht31Driver

            return Sht31Driver(self._i2c, self._address).read()
        except SensorError:
            raise
        except Exception as exc:  # CRC mismatch, bus error, missing driver module
            # The driver raises Sht31Error on a CRC failure; surface every failure as SensorError
            # so the sampler drops the parameter rather than reporting a guess.
            raise SensorError("SHT31 read failed: %s" % exc)


class PmSensor:
    """Plantower PMS5003 particulate sensor over UART, backed by ``drivers/pms5003.py``.

    Returns atmospheric-environment mass concentrations in ug/m3. The PMS5003 (and the SDS011
    alternative in the BOM) expose PM2.5 and PM10 in a fixed-length UART frame; this binds the
    checked-in PMS5003 driver. The import is deferred to :meth:`read` so the module stays
    import-safe on CPython; with no UART the sensor reports a clean :class:`SensorError`.
    """

    def __init__(self, uart=None):
        self._uart = uart

    def read(self):
        """Return ``(pm25_ugm3, pm10_ugm3)``. Raises :class:`SensorError` on a read failure."""
        if self._uart is None:
            raise SensorError("no UART configured for PM sensor")
        try:
            # Bound to the checked-in PMS5003 driver, imported lazily for the same reason as above.
            from pms5003 import Pms5003 as Pms5003Driver

            return Pms5003Driver(self._uart).read()
        except SensorError:
            raise
        except Exception as exc:  # bad header, checksum mismatch, UART timeout, missing module
            raise SensorError("PM read failed: %s" % exc)


class Sampler:
    """Assemble one wide payload per call from the configured sensors.

    ``th`` reads temperature and humidity; ``pm`` reads particulates. Either may be ``None`` (the
    node simply omits those parameters), and either may be a fake with a ``read()`` method for
    off-hardware testing. A sensor that errors drops its parameters for that sample rather than
    reporting a stale or invented value — ingest tolerates a missing parameter, not a wrong one.
    """

    def __init__(self, node_id, th=None, pm=None, clock=_utc_timestamp):
        if not node_id:
            raise ValueError("node_id is required and is assigned by the hosting collective")
        self.node_id = node_id
        self._th = th
        self._pm = pm
        self._clock = clock

    def sample(self):
        """Return one wide payload dict, or ``None`` if no sensor produced a reading."""
        payload = {"node_id": self.node_id, "timestamp": self._clock()}
        got_reading = False

        temp = humidity = None
        if self._th is not None:
            try:
                temp, humidity = self._th.read()
                payload["temp_c"] = round(float(temp), 2)
                payload["humidity_pct"] = round(float(humidity), 2)
                got_reading = True
            except SensorError:
                temp = humidity = None

        if self._pm is not None:
            try:
                pm25, pm10 = self._pm.read()
                payload["pm25_ugm3"] = round(float(pm25), 2)
                payload["pm10_ugm3"] = round(float(pm10), 2)
                got_reading = True
            except SensorError:
                pass

        # Compute the heat index on device when both inputs are present, matching the pipeline.
        if temp is not None and humidity is not None:
            payload["heat_index_c"] = heat_index_c(float(temp), float(humidity))

        if not got_reading:
            return None
        return payload
