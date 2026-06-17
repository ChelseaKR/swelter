"""Plantower PMS5003 particulate-matter driver over UART.

The PMS5003 is one of the two PM sensors in ``firmware/hardware/BOM.md`` (the other is the
SDS011). In its default active mode it streams a 32-byte frame at 9600 baud; this module
parses that frame, verifies its checksum, and exposes the atmospheric-environment PM2.5 and
PM10 mass concentrations in µg/m³ — the values the pipeline ingests.

As with the SHT31 driver, the protocol logic is a pure function so it is testable on desktop
CPython:

* :func:`parse_frame` takes a 32-byte ``bytes`` buffer and returns a dict of every field (or
  raises on a bad header or checksum). ``tests/test_firmware_drivers.py`` builds a valid frame
  by hand and a checksum-broken one and asserts both paths.
* :class:`Pms5003` is the bound driver. It reads from a MicroPython ``machine.UART`` object,
  finds frame alignment in the byte stream, and returns ``(pm2.5, pm10)``.

Frame layout (Plantower PMS5003 datasheet, "Transport Protocol — Active Mode"), all 16-bit
fields big-endian:

==========  ======================================================================
Bytes       Meaning
==========  ======================================================================
0–1         Start characters ``0x42 0x4D`` ("BM")
2–3         Frame length = 2 * 13 + 2 = 28 (bytes after this field)
4–5         PM1.0  µg/m³, CF=1 (standard particle)
6–7         PM2.5  µg/m³, CF=1 (standard particle)
8–9         PM10   µg/m³, CF=1 (standard particle)
10–11       PM1.0  µg/m³, atmospheric environment
12–13       PM2.5  µg/m³, atmospheric environment   <- returned
14–15       PM10   µg/m³, atmospheric environment    <- returned
16–17       particles >0.3 µm per 0.1 L air
18–19       particles >0.5 µm
20–21       particles >1.0 µm
22–23       particles >2.5 µm
24–25       particles >5.0 µm
26–27       particles >10  µm
28          version
29          error code
30–31       checksum = sum of bytes 0..29, big-endian
==========  ======================================================================
"""

from __future__ import annotations

# Frame constants.
START_BYTE_1 = 0x42
START_BYTE_2 = 0x4D
FRAME_LENGTH = 32
_CHECKSUM_OFFSET = 30  # checksum covers bytes [0, 30)


class Pms5003Error(Exception):
    """A PMS5003 read failed — a bad header, a checksum mismatch, or a UART timeout."""


def _u16(buf: bytes, offset: int) -> int:
    """Read a big-endian unsigned 16-bit value at ``offset``."""
    return (buf[offset] << 8) | buf[offset + 1]


def parse_frame(buf: bytes) -> dict[str, int]:
    """Parse a 32-byte PMS5003 frame into a dict of its fields.

    Verifies the two start bytes (``0x42 0x4D``) and the trailing checksum (the big-endian
    sum of the first 30 bytes). Returns every decoded field, including the atmospheric-
    environment concentrations under the keys ``pm25_ugm3`` and ``pm10_ugm3`` that the rest of
    the firmware uses. Raises :class:`Pms5003Error` on a wrong length, bad header, or checksum
    mismatch — a pure function with no hardware, so it is unit-testable on CPython.
    """
    if len(buf) != FRAME_LENGTH:
        raise Pms5003Error("PMS5003 expected %d bytes, got %d" % (FRAME_LENGTH, len(buf)))
    if buf[0] != START_BYTE_1 or buf[1] != START_BYTE_2:
        raise Pms5003Error("PMS5003 bad start bytes 0x%02X 0x%02X" % (buf[0], buf[1]))

    expected = _u16(buf, _CHECKSUM_OFFSET)
    actual = sum(buf[:_CHECKSUM_OFFSET]) & 0xFFFF
    if actual != expected:
        raise Pms5003Error(
            "PMS5003 checksum mismatch: got 0x%04X, computed 0x%04X" % (expected, actual)
        )

    return {
        "frame_length": _u16(buf, 2),
        "pm1_0_cf1": _u16(buf, 4),
        "pm2_5_cf1": _u16(buf, 6),
        "pm10_cf1": _u16(buf, 8),
        # Atmospheric-environment concentrations — the values the pipeline ingests.
        "pm1_0_ugm3": _u16(buf, 10),
        "pm25_ugm3": _u16(buf, 12),
        "pm10_ugm3": _u16(buf, 14),
        "particles_0_3um": _u16(buf, 16),
        "particles_0_5um": _u16(buf, 18),
        "particles_1_0um": _u16(buf, 20),
        "particles_2_5um": _u16(buf, 22),
        "particles_5_0um": _u16(buf, 24),
        "particles_10um": _u16(buf, 26),
        "version": buf[28],
        "error_code": buf[29],
        "checksum": expected,
    }


class Pms5003:
    """PMS5003 PM sensor on a MicroPython ``machine.UART`` bus (9600 baud, active mode).

    Parameters
    ----------
    uart:
        A MicroPython UART (``machine.UART``) — any object exposing ``read(n) -> bytes`` and,
        for alignment, ``read(1)``. Passed in by ``main.build_sampler`` on the node.
    read_attempts:
        How many bytes to scan looking for the ``0x42 0x4D`` start sequence before giving up.
        At 9600 baud a fresh frame arrives roughly every second; the default comfortably spans
        more than one frame so a mid-frame start still syncs.

    The constructor does no I/O; the UART is only touched in :meth:`read`.
    """

    def __init__(self, uart: object, read_attempts: int = 64) -> None:
        self._uart = uart
        self._read_attempts = read_attempts

    def read(self) -> tuple[float, float]:
        """Read one frame and return ``(pm25_ugm3, pm10_ugm3)`` atmospheric concentrations.

        Scans the UART stream for the ``0x42 0x4D`` header, reads the remaining 30 bytes,
        verifies the checksum via :func:`parse_frame`, and returns the PM2.5/PM10 values.
        Raises :class:`Pms5003Error` if no frame can be synced or the checksum is bad.
        """
        try:
            frame = self._read_frame()
        except Pms5003Error:
            raise
        except Exception as exc:  # UART timeout, wiring fault
            raise Pms5003Error("PMS5003 UART read failed: %s" % exc)
        fields = parse_frame(frame)
        return (float(fields["pm25_ugm3"]), float(fields["pm10_ugm3"]))

    def _read_frame(self) -> bytes:
        """Find the start header in the UART stream and return the full 32-byte frame."""
        prev = -1
        for _ in range(self._read_attempts):
            chunk = self._uart.read(1)
            if not chunk:
                continue
            byte = chunk[0]
            if prev == START_BYTE_1 and byte == START_BYTE_2:
                rest = self._uart.read(FRAME_LENGTH - 2)
                if rest is None or len(rest) != FRAME_LENGTH - 2:
                    raise Pms5003Error("PMS5003 short frame after header")
                return bytes((START_BYTE_1, START_BYTE_2)) + bytes(rest)
            prev = byte
        raise Pms5003Error("PMS5003 frame header not found in stream")
