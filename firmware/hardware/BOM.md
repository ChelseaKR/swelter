# Bill of materials — swelter sensor node

A build-it-yourself node from off-the-shelf, repairable parts. Every component is a commodity item
a builder can source from more than one vendor, unplug, and replace without a proprietary tool. The
sensors connect over standard I2C and UART headers; nothing is glued or potted, so field service is
swapping a board, not scrapping a node.

This is a **reference** build, not a certified instrument. Prices are rough single-unit estimates in
USD as of the verification date and fall with quantity; they are here to show the order of magnitude
(a node is built for tens of dollars, not hundreds), not as a quote.

Last verified: 2026-06-16. Recheck cadence: every 6 months, or whenever a listed part goes
end-of-life. Prices and availability drift; re-price before a build.

## Core parts

| Part | Example | Interface | Rough cost | Why this part |
| --- | --- | --- | ---: | --- |
| Microcontroller | ESP32 dev board (ESP32-WROOM-32 DevKitC class) | — | $6–10 | Cheap, widely stocked, runs MicroPython, has Wi-Fi station mode for forwarding and enough flash for the store-and-forward buffer and two OTA slots. Dual-vendor, easy to replace. |
| Temp / humidity sensor | Sensirion SHT31-D breakout | I2C | $7–12 | Accurate, low-drift digital temp/humidity with a calibrated digital output, far better than a DHT-class part for a heat-island map. I2C means two wires and a swap-in replacement. |
| Particulate sensor | SDS011 (laser, UART) **or** Plantower PMS5003 (UART) | UART | $15–25 | Optical PM2.5/PM10 mass sensors with a documented UART frame and a known humidity bias the pipeline corrects. Both are repairable: the SDS011's fan and laser diode are the wear parts and are replaceable; the PMS5003 is smaller and lower-power for solar builds. Pick one. |
| Enclosure with radiation shielding | Stevenson-style louvred radiation shield (stacked plates) + vented project box | — | $8–20 | A bare sensor in the sun reads the box, not the air. A louvred shield lets air move across the temp/humidity sensor while blocking direct sun and rain, which is what keeps the enclosure-offset correction small and stable. Off-the-shelf plate shields are cheap; a 3D-printed shield is a documented alternative. |
| Power | USB 5 V supply **or** small solar panel (5–10 W) + LiPo + charge controller (e.g. TP4056-class or a solar charge board) | — | $5 (USB) / $20–35 (solar) | A wired node runs from any USB supply. An off-grid node runs from a small panel and battery so it can sit on a fence with no outlet; the charge controller and battery are standard, replaceable parts. Solar is optional — start with USB and add solar where there is no power. |

## Consumables and small parts

| Part | Rough cost | Notes |
| --- | --- | --- |
| Dupont jumper wires / JST leads | $2–4 | Connect sensors to the dev board headers; let a sensor unplug for service. |
| Pull-up resistors (4.7 kΩ, if the SHT31 breakout lacks them) | <$1 | Many breakouts include I2C pull-ups; check before adding. |
| Mounting hardware (zip ties, bracket, weatherproof gland) | $3–6 | For siting on a porch, fence, or pole, and sealing the cable entry. |
| MicroUSB/USB-C cable | $2–4 | Flashing and, on a wired node, power. |

## Rough per-node total

- **Wired (USB), SDS011:** ~$45–70.
- **Off-grid (solar + battery):** add ~$20–35.

These are order-of-magnitude figures. The point the README makes is that a neighborhood collective
can build a node at low per-node cost from parts it can re-source and repair, not that any single
price is fixed.

## Deliberately not on this list

These are firmware facts backed by hardware: the node carries no parts that could surveil.

- **No microphone** — no I2S/PDM mic, no audio anything.
- **No camera** — no image sensor, no optics beyond the PM sensor's internal laser/photodiode, which
  faces its own measurement chamber and sees only the air sample.
- **No Bluetooth radio use** — the ESP32 has a BLE radio, but the firmware never initialises it; the
  radio is used for Wi-Fi station mode only.
- **No GPS** — the node's location is set by the host in `network.yaml` and published snapped to a
  coarse grid; the node does not sense or report its own position.

## Sourcing and repair notes

- Buy the SHT31 and the PM sensor from a reputable distributor; counterfeit SHT31s and clone PM
  sensors are common and read poorly. A bad sensor is caught at co-location, but it wastes a
  calibration window.
- Keep one or two spare PM sensors per cluster. The PM sensor's fan is the most likely field
  failure; QC flags a flatlined or out-of-range node and the assembly guide covers the swap.
- Prefer boards with castellated or pin-header sensors over soldered-down modules so a builder can
  replace one sensor without reworking the node.
