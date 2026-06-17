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
- **Store-and-forward buffering.** Every reading is appended to a flash-backed buffer before any
  attempt to send it. A node that loses connectivity keeps sampling and keeps buffering; when it
  reconnects it flushes the backlog oldest-first, so an outage becomes a backfilled gap rather than
  lost data. Payloads are idempotent — re-sending one the ingest already stored is a no-op on the
  server's idempotent store key, so a flush that overlaps an earlier partial send cannot duplicate.
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
  "heat_index_c": 33.9
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

## OTA updates: signed and staged

Over-the-air firmware updates are **signed and staged**, not pushed blind:

- **Signed.** An update image is signed with the network's release key. The node verifies the
  signature against a public key baked into the running firmware before it writes the image. An
  unsigned or mis-signed image is rejected and never applied.
- **Staged.** A verified image is written to a second OTA slot and booted as a trial. If the new
  firmware does not confirm itself healthy within a boot window, the bootloader rolls back to the
  previous slot. A bad update degrades to the last good firmware rather than bricking the node.

This firmware ships the **payload-and-buffer contract and the privacy guarantees**; the OTA
signing-and-staging mechanism is described here as the intended update path and is provided by the
board's standard two-slot OTA bootloader, configured with the network's public key. The reference
sources in `firmware/src/` do not perform OTA; they are the application that an OTA image carries.

## Target and scope

- **MicroPython on an ESP32-class board.** Written for MicroPython; the application logic is plain
  Python. Hardware-only imports (`machine`, `network`, sensor drivers) are guarded so the modules
  import cleanly on desktop CPython for offline review and CI (`python -m compileall firmware/src`).
- **Off-the-shelf, repairable parts.** Every component in `firmware/hardware/BOM.md` is a commodity
  part a builder can source, replace, and repair without a proprietary tool or a vendor lock-in.
  Sensors connect over standard I2C/UART headers and unplug for service.
- **Reference, not certified.** Use it to build a node and to read how a node stays honest. It is not
  a calibrated instrument and makes no regulatory claim.

## Files

- `firmware/src/main.py` — the node loop: sample, compute heat index, buffer, forward, repeat.
- `firmware/src/sampler.py` — reads the sensors and computes the heat index into a wide payload.
- `firmware/src/store_and_forward.py` — the flash-backed buffer; appends readings and flushes them
  oldest-first on reconnect with idempotent payloads.
- `firmware/hardware/BOM.md` — the bill of materials with rough per-node cost and the reason for
  each part.
- `firmware/hardware/assembly.md` — wiring, enclosure, and flashing guide.
