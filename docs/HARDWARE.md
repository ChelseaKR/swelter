# Hardware build — the swelter sensor node

This is the build doc for a swelter sensor node: what parts it takes, how they wire together, where
to put it, and how a reading gets from a porch to the ingest endpoint without being lost. It is
written for a community collective building its own nodes, not for a factory. Build it, read it,
change it.

A node is a **reference** build from off-the-shelf, repairable parts, not a certified instrument. A
node's raw readings are corrected against a reference monitor by `swelter calibrate` before they are
published as trustworthy — the hardware's job is to measure honestly and forward reliably, not to be
laboratory-grade. The deeper part references are the firmware tree:

- [`firmware/hardware/BOM.md`](../firmware/hardware/BOM.md) — the full bill of materials with rough
  per-part cost and the reason for each part.
- [`firmware/hardware/assembly.md`](../firmware/hardware/assembly.md) — step-by-step wiring,
  flashing, and field-service guide.
- [`firmware/README.md`](../firmware/README.md) — what the firmware does and the privacy guarantees
  it holds by construction.

This page is the orientation; those three are the detail. Where a decision belongs to the people who
host the sensors — siting, whether to share a precise location, who owns the data — this doc points
at [`governance.md`](governance.md) and the afternoon setup guide
[`ADD-YOUR-NEIGHBORHOOD.md`](ADD-YOUR-NEIGHBORHOOD.md).

Last verified: 2026-06-20. Recheck cadence: whenever the parts in
[`firmware/hardware/BOM.md`](../firmware/hardware/BOM.md), the firmware in `firmware/src/`, or the
ingest payload shape in `src/swelter/ingest.py` change; otherwise every 12 months.

## What a node measures

A node samples four environmental quantities on a fixed interval (5 minutes by default) and computes
a fifth on the device:

| Parameter | Unit | Sensor | Notes |
| --- | --- | --- | --- |
| `temp_c` | degC | SHT31 (I2C) | Air temperature. |
| `humidity_pct` | % | SHT31 (I2C) | Relative humidity. |
| `pm25_ugm3` | ug/m3 | PMS5003 or SDS011 (UART) | PM2.5 mass concentration. |
| `pm10_ugm3` | ug/m3 | PMS5003 or SDS011 (UART) | PM10 mass concentration. |
| `heat_index_c` | degC | derived | NWS Rothfusz regression from temp + humidity, computed on device. |

It measures the environment and nothing else. There is no microphone, no camera, no GPS, no
Bluetooth use, and no Wi-Fi client scanning — those are not parts on the BOM and not drivers in the
firmware, by construction, because hard rule #1 forbids any field or sensor that could identify or
locate a person. The only identifier a node ever sends is the `node_id` the hosting collective
assigns it.

## Bill of materials (overview)

The order of magnitude is **tens of dollars per node**, not hundreds. Full costs and sourcing notes
are in [`firmware/hardware/BOM.md`](../firmware/hardware/BOM.md); this is the shape of it.

| Group | Part | Interface | Why |
| --- | --- | --- | --- |
| MCU / radio | ESP32 dev board (ESP32-WROOM-32 class) | — | Cheap, widely stocked, runs MicroPython, Wi-Fi station mode to forward, enough flash for the store-and-forward buffer. |
| Temp / humidity | Sensirion SHT31-D breakout | I2C | Accurate, low-drift digital temp/humidity; two wires; swaps in for service. |
| Particulate | Plantower PMS5003 **or** SDS011 | UART | Optical PM2.5/PM10 with a documented frame and a known humidity bias the pipeline corrects. Pick one. |
| Enclosure | Louvred radiation shield + vented project box | — | Keeps direct sun and rain off the sensor so the enclosure-offset correction stays small and stable. |
| Power | USB 5 V supply **or** small solar panel + LiPo + charge controller | — | Wired from any USB; off-grid from a small panel and battery for a node on a fence with no outlet. |
| Small parts | Jumper/JST leads, optional 4.7 kΩ I2C pull-ups, mounting hardware, weatherproof gland, USB cable | — | Let each sensor unplug for service; seal the cable entry. |

Every part is a commodity item a builder can source from more than one vendor, unplug, and replace
without a proprietary tool. Field service is swapping a board, not scrapping a node.

## Wiring overview

All sensors run off the ESP32's 3V3 and GND (the PM sensor takes 5 V). Keep wires short and let each
sensor unplug. The pins below match `build_sampler()` in `firmware/src/main.py`; change both if you
wire differently. Full steps, including the SDS011 alternative and I2C pull-up notes, are in
[`firmware/hardware/assembly.md`](../firmware/hardware/assembly.md).

```
ESP32                         SHT31 (I2C)              PM sensor (UART, PMS5003)
-----                         -----------              ------------------------
3V3  ───────────────────────  VIN
GND  ───────────────────────  GND ───────────────────  GND
GPIO22 (SCL) ───────────────  SCL
GPIO21 (SDA) ───────────────  SDA
5V   ─────────────────────────────────────────────────  VIN/5V
GPIO16 (RX)  ◄────────────────────────────────────────  TX
GPIO17 (TX)  ─────────────────────────────────────────► RX
```

- **SHT31 (I2C):** `VIN→3V3`, `GND→GND`, `SCL→GPIO22`, `SDA→GPIO21`. Address `0x44` (`0x45` if ADDR
  is tied high). Add 4.7 kΩ pull-ups from SDA and SCL to 3V3 if the breakout lacks them.
- **PM sensor (UART):** `5V→VIN/5V`, `GND→GND`, sensor `TX→GPIO16` (ESP32 RX), sensor `RX→GPIO17`
  (ESP32 TX), 9600 baud. The reference firmware ships a working PMS5003 driver; an SDS011 needs an
  SDS011 frame parser bound the same way.
- **Power:** a USB supply into the dev board for a wired node; for off-grid, the solar panel and
  battery through the charge controller per its datasheet, feeding the board's 5 V input.

Both sensor drivers (`firmware/src/drivers/sht31.py`, `firmware/src/drivers/pms5003.py`) CRC- or
checksum-verify each transfer, so a bad read raises rather than returning a corrupt value — and the
firmware drops that one parameter for the cycle rather than reporting a guess.

## Enclosure and siting

Siting is a data-quality decision **and** a privacy decision. The collective decides where nodes go;
see [`governance.md`](governance.md).

**For good data:**

- **Shade and airflow.** A bare sensor in the sun reads the box, not the air. Mount the SHT31 inside
  a louvred (Stevenson-style) radiation shield so air moves across it while direct sun and rain stay
  off. A shield that lets the sensor see the sun makes the enclosure-offset correction larger and
  less stable — this is the single siting choice that most affects whether the node calibrates well.
- **PM inlet down.** Put the PM sensor in the vented enclosure with its inlet facing down so rain
  does not pool in it. Seal the cable entry with a gland.
- **Representative spot.** Mount at roughly head height in a spot that represents the block's
  exposure — over a porch, fence, or pole — not in a sheltered corner or directly above a heat
  source like an AC condenser or a grill.

**For privacy — the coarse-location point:**

A sensor sits on someone's porch or fence, so its exact coordinates would reveal where a person
lives. swelter never publishes that. A node does **not** sense or report its own position — there is
no GPS on the BOM. The node's location is set by the host in `network.yaml`, and published
coordinates are **snapped to a coarse grid** (default ~150 m) by `config.public_location()` unless
the host explicitly opts a node into a precise location. The precise value is never required to use
the system. This is hard rule #2: hosting a sensor must not expose where a person lives. The decision
to share a precise location for any node rests with the collective, recorded in
[`governance.md`](governance.md).

## How a reading gets home: store-and-forward

The firmware is built so a node loses a reading neither to a dropped network nor to a power cut. The
loop in `firmware/src/main.py` is: sample → append to a flash buffer → try to flush the backlog →
sleep, repeat.

1. **Sample.** `sampler.py` reads the sensors into one wide JSON payload per timestamp:
   `node_id`, `timestamp` (ISO-8601 UTC, `...Z`), and the parameters sampled. A sensor that fails
   drops only its own parameters for that cycle; the rest of the payload still ships.
2. **Persist before send.** The payload is appended to a flash-backed buffer
   (`store_and_forward.py`) and flushed to flash **before** any network attempt. A node that loses
   connectivity keeps sampling and keeps buffering.
3. **Flush oldest-first.** When the link is up, the buffer flushes oldest-first. A failed send is
   retried in place with bounded exponential backoff; if it still fails, that payload and the rest of
   the backlog stay buffered and the flush stops, to be retried whole next cycle — so one dead link
   never spins the radio for the whole interval.
4. **Idempotent on the server.** Each first-party payload receives the `native` source marker and is
   idempotent on `(node_id, timestamp, parameter, source, calibration)` with an
   `INSERT OR IGNORE` write, so a re-send of a payload the server already stored is a no-op. A flush
   that overlaps an earlier partial send cannot duplicate.

The result: an outage — network or power — becomes a backfilled gap in the record, not a hole. The
buffer survives an abrupt reset because appends are flushed before they return and compaction is
done by writing a temp file and renaming it over the old one (atomic on flash), so a crash mid-write
leaves a complete buffer, never a truncated one.

**Sizing the buffer.** `buffer_max_records` (default 20000) caps how many readings flash holds during
an outage. At one reading every 5 minutes that is 288/day, so 20000 covers about 69 days offline
before the oldest readings start dropping. Raise it for longer expected outages if flash allows. See
[`firmware/hardware/assembly.md`](../firmware/hardware/assembly.md) for the configuration and flashing
steps.

## Updates

Over-the-air updates are **not implemented** in this reference firmware. To update a node today you
re-flash it over USB with the steps in
[`firmware/hardware/assembly.md`](../firmware/hardware/assembly.md). Signed-and-staged OTA is the
*intended* design described in [`firmware/README.md`](../firmware/README.md), not a property of the
code as shipped — do not assume any OTA safety guarantee is in force until a reviewed implementation
lands.

## Where to go next

- Standing up a network and registering nodes in `network.yaml`:
  [`ADD-YOUR-NEIGHBORHOOD.md`](ADD-YOUR-NEIGHBORHOOD.md).
- Who decides siting, location precision, and data sharing: [`governance.md`](governance.md).
- Building and flashing a physical node: [`firmware/hardware/assembly.md`](../firmware/hardware/assembly.md)
  and [`firmware/hardware/BOM.md`](../firmware/hardware/BOM.md).
- How raw readings become trustworthy: [`calibration.md`](calibration.md).

Author: Chelsea Kelly-Reif. Year: 2026.
