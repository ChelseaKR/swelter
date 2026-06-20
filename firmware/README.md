# swelter node firmware (reference)

Firmware for a build-it-yourself swelter sensor node. The node samples temperature, relative
humidity, and particulate matter (PM2.5 and PM10), computes a heat index on the device, buffers
readings to flash when it cannot reach the network, and forwards them to the swelter ingest
endpoint by MQTT or HTTP. It speaks the same wide-payload shape that `src/swelter/ingest.py`
explodes into observations, so a node and the pipeline agree on the record without a translation
layer.

This is **reference firmware**, not a certified product. It demonstrates a node that satisfies the
project's hard rules and is honest about what a low-cost sensor can and cannot do. Build it, read
it, change it. There is no warranty and no claim of regulatory-grade measurement; raw node readings
are corrected against a reference monitor by `swelter calibrate` before they are published as
trustworthy.

Last verified: 2026-06-16. Recheck cadence: on any change to the ingest payload shape in
`src/swelter/ingest.py` or `src/swelter/models.py`, the parameter set in `models.PARAMETERS`, or
the sensors in `firmware/hardware/BOM.md`; otherwise every 12 months.

## What the node does

- **Samples** four environmental quantities on a fixed interval: air temperature (`temp_c`),
  relative humidity (`humidity_pct`), PM2.5 (`pm25_ugm3`), and PM10 (`pm10_ugm3`). Units match
  `models.PARAMETERS` exactly.
- **Computes a heat index on device** (`heat_index_c`) from temperature and humidity using the NWS
  Rothfusz regression, the same formula `models.heat_index_c()` uses, so the on-device value and the
  pipeline fallback agree. Below 26.7 degC the regression is not meaningful and the air temperature
  is returned unchanged.
- **Store-and-forward buffering that survives power and network loss.** Every reading is appended to
  a flash-backed buffer, flushed to flash, before any attempt to send it. A node that loses
  connectivity keeps sampling and keeps buffering; when it reconnects it flushes the backlog
  oldest-first, so an outage becomes a backfilled gap rather than lost data. The buffer survives an
  abrupt reset: appends are flushed before they return, and the buffer is compacted by writing a
  temp file and renaming it over the old one (atomic on flash), so a crash mid-housekeeping leaves a
  complete buffer, never a truncated one. A torn trailing line from a power loss mid-write is
  rejected on read, not forwarded. Payloads are idempotent — re-sending one the ingest already
  stored is a no-op on the server's idempotent store key, so a flush that overlaps an earlier partial
  send cannot duplicate.
- **Bounded upload retry with backoff.** A send that fails (link down, endpoint error) is retried in
  place a bounded number of times (`upload_max_attempts`, default 3) with exponential backoff
  (`upload_backoff_base_s`, capped at `upload_backoff_cap_s`). If it still fails, that payload and
  everything after it stay buffered and the flush stops, to be retried whole on the next cycle —
  so one dead link never spins the radio for the whole sample interval, and the backlog is preserved
  in order. Retries are safe because the payload is idempotent on the server's store key.
- **Tolerates a single sensor failing.** A sensor read that errors drops only its own parameters for
  that cycle; the rest of the payload still ships. A node whose PM sensor dies keeps reporting
  temperature and humidity (and the derived heat index), and vice versa, rather than dropping the
  whole reading — and never reports a stale or invented value in place of the failed sensor.
- **Forwards by MQTT or HTTP.** One transport is chosen in config. The payload is the same either
  way: one JSON object per timestamp carrying `node_id`, `timestamp` (ISO-8601 UTC, `...Z`), and the
  parameters sampled at that timestamp.

## The payload shape

One object per timestamp, every parameter the node sampled inline, matching the wide payload
`ingest.explode()` reads:

```json
{
  "node_id": "node-07",
  "timestamp": "2026-06-16T18:00:00Z",
  "temp_c": 31.4,
  "humidity_pct": 58.2,
  "pm25_ugm3": 19.7,
  "pm10_ugm3": 33.1,
  "heat_index_c": 35.23
}
```

Notes that keep the node and the pipeline in agreement:

- The node sends **raw** values only. It does not apply calibration; that is the pipeline's job
  against a reference monitor, and keeping correction out of the firmware is what makes calibrated
  versus raw distinguishable downstream.
- `node_id` is the only identifier in the payload, and it is assigned by the hosting collective —
  not derived from a MAC address, a chip id, or anything tied to a device or a person.
- Unknown extra fields are ignored by ingest and a payload missing `node_id` or `timestamp` is
  quarantined, so a firmware revision that adds a sensor does not break intake.

## Privacy guarantees (firmware facts, not policy)

These are properties of the code in `firmware/src/`, not promises in a document. They hold because
the firmware has no way to do otherwise:

- **No microphone.** The firmware contains no audio capture, no I2S/PDM microphone driver, and the
  BOM specifies no microphone part.
- **No camera.** No image sensor driver, no camera, no frame buffer. The BOM specifies no camera.
- **No Bluetooth.** The radio is used for Wi-Fi station mode to reach the ingest endpoint and for
  nothing else. The firmware never initialises the Bluetooth/BLE stack.
- **No Wi-Fi client scanning.** The node connects to one configured access point to forward its
  readings. It never scans for, enumerates, or records nearby Wi-Fi clients, access points, or
  probe requests. It cannot be used to count or track devices.
- **No per-device identifiers beyond a host-assigned node id.** The only identifier that leaves the
  node is `node_id`, set by the hosting collective in the node's config. The firmware does not put a
  MAC address, chip id, serial number, or any hardware fingerprint into a payload.

There is nothing in the payload that locates a person, because there is no field that could carry
one — the schema (`models.Observation`) has no such field, and the firmware emits nothing the schema
cannot hold. A change that added any of the above would fail review, the same hard rule the rest of
the project is held to.

## Sensor drivers (checked in, not stubs)

The two sensors in `firmware/hardware/BOM.md` have real, documented drivers in
`firmware/src/drivers/`:

- **`drivers/sht31.py` — Sensirion SHT31 temperature/humidity over I2C.** Issues the single-shot
  high-repeatability measurement command (`0x2C 0x06`), reads the 6-byte response, verifies the
  CRC-8 of each 2-byte word (polynomial `0x31`, init `0xFF`), and converts per the datasheet
  (`temp_c = -45 + 175*raw/65535`, `rh = 100*raw/65535`). A CRC mismatch raises rather than
  returning a corrupted reading.
- **`drivers/pms5003.py` — Plantower PMS5003 PM2.5/PM10 over UART.** Syncs to the `0x42 0x4D`
  header, parses the 32-byte big-endian frame, verifies the trailing checksum, and returns the
  atmospheric-environment PM2.5 and PM10 concentrations in ug/m3. `parse_frame()` is a pure
  function so the protocol is unit-tested on desktop CPython.

`sampler.py` binds these drivers to its `Sht31`/`PmSensor` sensor slots automatically when a bus is
present. The CRC- and checksum-verification logic is split into pure functions and exercised by
`tests/test_firmware_drivers.py`, which runs in CI on desktop CPython — so the drivers are tested
without hardware. Each driver's wire protocol is deferred to call time and guarded, so the modules
still import cleanly on CPython and pass `python -m compileall firmware/src`. Off the node (review or
CI) there is no I2C/UART bus, so a read raises a clean `SensorError`, the sampler drops that
parameter for the cycle, and the end-to-end ingest demo still runs against injected fakes — a node
never reports an invented value.

The reference build defaults to the PMS5003. An SDS011 is also listed in the BOM; if you choose it,
add an SDS011 frame parser alongside `pms5003.py` and bind it in `PmSensor` the same way.

## OTA updates: NOT IMPLEMENTED in this reference firmware

**Over-the-air updates are not implemented here.** Signed/staged OTA is described below as the
*intended design*, not something this firmware ships. The reference sources in `firmware/src/` do
**not** verify a signature, do **not** write a second OTA slot, and do **not** roll back — they are
the application an OTA image would carry, nothing more. To update a node today you re-flash it over
USB with the steps in `firmware/hardware/assembly.md`. Do not assume any OTA safety property is in
force until a real bootloader-integrated implementation lands and is reviewed.

The intended design, for when it is built:

- **Signed.** An update image is signed with the network's release key. The node verifies the
  signature against a public key baked into the running firmware before it writes the image. An
  unsigned or mis-signed image is rejected and never applied.
- **Staged.** A verified image is written to a second OTA slot and booted as a trial. If the new
  firmware does not confirm itself healthy within a boot window, the bootloader rolls back to the
  previous slot. A bad update degrades to the last good firmware rather than bricking the node.

This is the standard two-slot OTA bootloader pattern, configured with the network's public key. It
is the planned update path, not a property of the code as shipped.

## Target and scope

- **MicroPython on an ESP32-class board.** Written for MicroPython; the application logic is plain
  Python. Hardware-only imports (`machine`, `network`) and the sensor-bus access in the drivers are
  guarded or deferred to call time, so every module imports cleanly on desktop CPython for offline
  review and CI (`python -m compileall firmware/src`). The drivers' pure protocol logic (CRC,
  checksum, datasheet conversion) is unit-tested on CPython in `tests/test_firmware_drivers.py`.
- **Off-the-shelf, repairable parts.** Every component in `firmware/hardware/BOM.md` is a commodity
  part a builder can source, replace, and repair without a proprietary tool or a vendor lock-in.
  Sensors connect over standard I2C/UART headers and unplug for service.
- **Reference, not certified.** Use it to build a node and to read how a node stays honest. It is not
  a calibrated instrument and makes no regulatory claim.

## Files

- `firmware/src/main.py` — the node loop: sample, compute heat index, buffer, forward, repeat.
- `firmware/src/sampler.py` — reads the sensors and computes the heat index into a wide payload.
- `firmware/src/drivers/sht31.py` — Sensirion SHT31 temp/humidity driver over I2C (CRC-checked).
- `firmware/src/drivers/pms5003.py` — Plantower PMS5003 PM2.5/PM10 driver over UART (checksummed).
- `firmware/src/store_and_forward.py` — the flash-backed buffer; appends readings durably and flushes
  them oldest-first on reconnect with bounded retry/backoff and idempotent payloads.
- `firmware/tests/test_store_and_forward.py` — hardware-free tests for the buffer (persistence,
  retry/backoff, atomic rewrite, cap) and the sampler's tolerate-a-failing-sensor path; run on
  desktop CPython in the CI `firmware` job.
- `firmware/hardware/BOM.md` — the bill of materials with rough per-node cost and the reason for
  each part.
- `firmware/hardware/assembly.md` — wiring, enclosure, and flashing guide.
