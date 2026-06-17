# Assembly and flashing guide

How to build a swelter node from the parts in `BOM.md`, flash the reference firmware in
`../src/`, and confirm its readings reach the ingest endpoint. This is a reference build; it
produces a working node, not a certified instrument. A node's raw readings are corrected against a
reference monitor by `swelter calibrate` before they are published as trustworthy — see
`docs/calibration.md`.

Last verified: 2026-06-16. Recheck cadence: whenever the firmware in `../src/`, the parts in
`BOM.md`, or the MicroPython flashing tools change; otherwise every 12 months.

## What you need

- The parts in `BOM.md` (ESP32 dev board, SHT31, an SDS011 or PMS5003 PM sensor, a radiation shield
  and enclosure, and a USB or solar power source).
- A computer with Python and `pip`, a USB cable, and the node's host-assigned `node_id` and the
  network's ingest endpoint from whoever runs the network.

## 1. Wire it up

All sensors run off the ESP32's 3V3 and GND. Keep wires short and let each sensor unplug for service.

- **SHT31 (I2C):** `VIN→3V3`, `GND→GND`, `SCL→GPIO22`, `SDA→GPIO21`. These pins match
  `build_sampler()` in `main.py`; change both if you wire differently. If your SHT31 breakout has no
  I2C pull-ups, add 4.7 kΩ from SDA and SCL to 3V3. The reference firmware ships a working SHT31
  driver (`../src/drivers/sht31.py`) at I2C address `0x44` (`0x45` if your breakout ties ADDR high).
- **PM sensor (UART):** `5V→VIN/5V`, `GND→GND`, sensor `TX→GPIO16` (ESP32 RX), sensor `RX→GPIO17`
  (ESP32 TX). The reference firmware ships a working **Plantower PMS5003** driver
  (`../src/drivers/pms5003.py`): it parses the 32-byte UART frame at 9600 baud and verifies the
  checksum. If you fit an **SDS011** instead, add an SDS011 frame parser next to it and bind it in
  `PmSensor` the same way — both speak a fixed-length frame at 9600 baud.
- **Power:** for a wired node, a USB supply into the dev board is enough. For an off-grid node, wire
  the solar panel and battery through the charge controller per its datasheet, then feed the board's
  5V input. Add the PM sensor on the 5V rail; the SHT31 stays on 3V3.

Mount the SHT31 inside the louvred radiation shield so air moves across it and direct sun does not.
The PM sensor goes in the vented enclosure with its inlet facing down so rain does not pool in it.
Seal the cable entry with a gland. A shield that lets the sensor see the sun makes the
enclosure-offset correction larger and less stable, so this step matters for data quality.

## 2. Flash MicroPython

Install the tools and put MicroPython on the board.

```console
$ pip install esptool mpremote
# Erase, then write the MicroPython ESP32 build you downloaded from micropython.org:
$ esptool.py --chip esp32 --port /dev/ttyUSB0 erase_flash
$ esptool.py --chip esp32 --port /dev/ttyUSB0 --baud 460800 \
    write_flash -z 0x1000 ESP32_GENERIC-<version>.bin
```

Replace `/dev/ttyUSB0` with your port (`/dev/tty.usbserial-*` on macOS, `COMx` on Windows). After a
reset the board runs MicroPython.

## 3. Configure the node

Create a `config.py` for the node. It is **not committed** — it holds the network's endpoint and the
host-assigned `node_id`, and it carries no secret beyond the Wi-Fi password and the endpoint. Use
`DEFAULT_CONFIG` in `main.py` as the template:

```python
# config.py (on the node, uncommitted)
CONFIG = {
    "node_id": "node-07",            # assigned by the hosting collective; the ONLY identifier sent
    "sample_interval_s": 300,        # 5 minutes
    "transport": "https",            # "https" or "mqtt"
    "ingest_url": "https://ingest.example.org/v1/observations",
    "wifi_ssid": "<your-wifi-ssid>",
    "wifi_password": "<your-wifi-password>",  # a placeholder — never commit a real password
    "buffer_path": "buffer.jsonl",
    "buffer_max_records": 20000,     # size for your worst expected outage (see below)
}
```

`node_id` is whatever the collective registered for this node in `network.yaml`. Do not derive it
from the chip's MAC or serial — the firmware never sends a hardware identifier, and using one here
would defeat that.

**Sizing the buffer.** `buffer_max_records` caps how many readings flash holds during an outage.
At one reading every 5 minutes that is 288/day; 20000 records covers about 69 days offline before
the oldest readings start dropping. Raise it for longer expected outages if flash allows, or shorten
the sample interval and it fills faster.

## 4. Copy the firmware to the board

The node imports modules flat from its filesystem root, so the two driver modules in
`../src/drivers/` are copied to the root as `sht31.py` and `pms5003.py` (next to `sampler.py`),
which is the layout `sampler.py` expects when it binds them.

```console
$ mpremote connect /dev/ttyUSB0 cp ../src/sampler.py :sampler.py
$ mpremote connect /dev/ttyUSB0 cp ../src/store_and_forward.py :store_and_forward.py
$ mpremote connect /dev/ttyUSB0 cp ../src/main.py :main.py
$ mpremote connect /dev/ttyUSB0 cp ../src/drivers/sht31.py :sht31.py
$ mpremote connect /dev/ttyUSB0 cp ../src/drivers/pms5003.py :pms5003.py
$ mpremote connect /dev/ttyUSB0 cp ./config.py :config.py
```

`ampy` works the same way if you prefer it (`ampy --port /dev/ttyUSB0 put ../src/drivers/sht31.py
sht31.py`, and so on).

Both sensor drivers are checked in and bound automatically by `sampler.py` once the bus is wired —
nothing to fill in. The SHT31 driver CRC-checks each reading and the PMS5003 driver verifies the
frame checksum, so a bad transfer raises rather than returning a corrupt value. (If you fit an
SDS011 instead of the PMS5003, copy your SDS011 parser too and bind it in `PmSensor`.)

`main.py` runs automatically at boot. Reset the board (or power-cycle it) and it begins the loop:
sample, append to the flash buffer, then flush the backlog to the endpoint.

## 5. Confirm it works

- Watch the console with `mpremote connect /dev/ttyUSB0 repl` and look for the node connecting to
  Wi-Fi, syncing the clock over SNTP, and sampling. Timestamps must be UTC ISO-8601 (`...Z`).
- On the server side, the node's `node_id` should start appearing in the store. A node's first
  readings ingest as **raw** and show **provisional** on the dashboard until it has been co-located
  and calibrated.
- Pull the Wi-Fi for a few minutes, then restore it. The readings taken during the outage should
  backfill — that is the store-and-forward buffer flushing oldest-first. Because payloads are
  idempotent on the server's store key, an overlapping re-send does not duplicate.

## 6. Updates (re-flash over USB; OTA NOT IMPLEMENTED)

**Over-the-air updates are not implemented in this reference firmware.** To update a node today,
re-flash it over USB: connect it, re-copy the changed module(s) with `mpremote`/`ampy` as in
step 4, and reset the board. You do not need to re-flash MicroPython itself (step 2) unless you are
changing the MicroPython version.

Signed-and-staged OTA — verifying an image's signature against the network's public key, writing it
to a second slot, booting it as a trial, and rolling back if it fails to confirm healthy — is the
*intended* update path described in `../README.md`, **not** a property of the code as shipped. The
sources in `../src/` do not perform OTA. Do not assume any OTA safety guarantee is in force; until a
reviewed bootloader-integrated implementation lands, USB re-flash is the only update mechanism.

## Field service

- **PM sensor failure** is the most common: the fan or laser wears out. QC flags the node
  (out-of-range or flatline); unplug the PM sensor and swap in a spare. Keep one or two per cluster.
- **Drift** is expected and handled by recalibration, not by replacing hardware. A node whose
  residuals widen at re-co-location is flagged for service in the calibration record.
- **Power on an off-grid node:** the battery and charge controller are standard, replaceable parts.
  If a solar node browns out in winter, shorten the sample interval is the wrong fix — the buffer
  holds the gap; check the panel, battery, and charge controller.
