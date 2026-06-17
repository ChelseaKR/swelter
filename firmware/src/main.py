"""The node loop: sample, compute heat index, buffer, forward, repeat.

On a MicroPython board this is the entry point (`main.py` runs at boot after `boot.py`). It wires a
:class:`~sampler.Sampler` to a :class:`~store_and_forward.StoreAndForward` buffer and one transport
(MQTT or HTTP), then loops: take a sample, append it to flash, and try to flush the backlog. If the
network is down the sample is still buffered and the flush is a no-op that retries next cycle, so an
outage backfills when the link returns.

Everything that touches hardware (`machine`, `network`, the radios, the MQTT client, sockets) is
imported at call time inside a guard, so this module imports cleanly on desktop CPython and passes
``python -m compileall firmware/src``. The loop logic itself is plain Python and is exercised
off-hardware with fakes.

Config lives in ``config.py`` next to this file on the node (not committed: it holds the network's
endpoint and the host-assigned ``node_id``). A reference shape is shown in ``DEFAULT_CONFIG`` below
and documented in ``firmware/hardware/assembly.md``.

Privacy facts that hold here: the only identifier in a payload is the host-assigned ``node_id``; the
radio is used for Wi-Fi station mode to reach the endpoint and nothing else; the firmware never
initialises Bluetooth, never scans for Wi-Fi clients, and reads no microphone or camera — there are
no such drivers in this firmware.
"""

from __future__ import annotations

from sampler import PmSensor, Sampler, Sht31
from store_and_forward import StoreAndForward, TransportError

# Reference config shape. On the node, the real values live in an uncommitted config.py and are
# loaded by load_config(); node_id is assigned by the hosting collective, never derived from the
# chip. No secrets are committed to the repo.
DEFAULT_CONFIG = {
    "node_id": "node-XX",  # host-assigned; the only identifier that ever leaves the node
    "sample_interval_s": 300,  # 5 minutes
    "transport": "https",  # "https" or "mqtt"
    "ingest_url": "https://ingest.example.org/v1/observations",  # HTTP forwarder POST target
    "mqtt_host": "ingest.example.org",
    "mqtt_port": 8883,
    "mqtt_topic": "swelter/observations",
    "wifi_ssid": "",
    "wifi_password": "",
    "buffer_path": "buffer.jsonl",
    "buffer_max_records": 20000,
}


def load_config():
    """Load the node's config.py, falling back to DEFAULT_CONFIG for review and tests."""
    try:
        import config as node_config  # uncommitted, present on the node

        cfg = dict(DEFAULT_CONFIG)
        cfg.update(getattr(node_config, "CONFIG", {}))
        return cfg
    except Exception:
        return dict(DEFAULT_CONFIG)


# -- transports: each implements send(payload) and raises TransportError when it cannot deliver ----


class HttpForwarder:
    """Forward one payload per HTTP POST as JSON. Idempotent on the server's store key."""

    def __init__(self, url):
        self.url = url

    def send(self, payload):
        try:
            import json

            import urequests  # MicroPython HTTP client

            response = urequests.post(
                self.url,
                data=json.dumps(payload),
                headers={"Content-Type": "application/json"},
            )
            status = response.status_code
            response.close()
            if status >= 300:
                raise TransportError("ingest returned HTTP %s" % status)
        except TransportError:
            raise
        except Exception as exc:  # network down, DNS failure, TLS error: keep the payload buffered
            raise TransportError("HTTP forward failed: %s" % exc)


class MqttForwarder:
    """Publish one payload per MQTT message as JSON to the ingest topic."""

    def __init__(self, host, port, topic, client_id):
        self.host = host
        self.port = port
        self.topic = topic
        self.client_id = client_id
        self._client = None

    def _connect(self):
        if self._client is not None:
            return self._client
        import json as _json  # noqa: F401  (used by send; imported here to fail fast if missing)

        from umqtt.simple import MQTTClient  # MicroPython MQTT client

        client = MQTTClient(self.client_id, self.host, port=self.port)
        client.connect()
        self._client = client
        return client

    def send(self, payload):
        try:
            import json

            client = self._connect()
            client.publish(self.topic, json.dumps(payload))
        except TransportError:
            raise
        except Exception as exc:  # broker unreachable: drop the client and keep the payload
            self._client = None
            raise TransportError("MQTT forward failed: %s" % exc)


def build_transport(cfg):
    """Construct the configured transport. ``client_id`` is the node_id, the only identifier sent."""
    if cfg.get("transport") == "mqtt":
        return MqttForwarder(
            cfg["mqtt_host"], cfg["mqtt_port"], cfg["mqtt_topic"], cfg["node_id"]
        )
    return HttpForwarder(cfg["ingest_url"])


# -- hardware bring-up (guarded; no-ops off the node) ----------------------------------------------


def connect_wifi(cfg):
    """Bring up Wi-Fi *station* mode only, to reach the ingest endpoint.

    Station mode joins one configured access point. The firmware never enables access-point mode,
    never scans for or records nearby clients, and never enables Bluetooth.
    """
    try:
        import network

        station = network.WLAN(network.STA_IF)
        station.active(True)
        if not station.isconnected() and cfg.get("wifi_ssid"):
            station.connect(cfg["wifi_ssid"], cfg.get("wifi_password", ""))
        return station.isconnected()
    except Exception:
        # Off-hardware (CPython review/CI) there is no WLAN; report "not connected" and move on.
        return False


def sync_clock():
    """Discipline the RTC to UTC via SNTP so timestamps are correct ISO-8601 UTC."""
    try:
        import ntptime

        ntptime.settime()  # sets the RTC to UTC
        return True
    except Exception:
        return False


def build_sampler(cfg):
    """Wire the I2C temp/humidity sensor and the UART PM sensor to a Sampler.

    The sensors are backed by the real drivers in ``drivers/`` (SHT31 over I2C, PMS5003 over UART).
    Bus setup is guarded: on the node it opens the real I2C/UART; off the node there is no bus, so a
    read surfaces as a missing parameter rather than an invented value, and the loop still runs.
    """
    i2c = uart = None
    try:
        from machine import I2C, UART, Pin

        i2c = I2C(0, scl=Pin(22), sda=Pin(21))
        uart = UART(1, baudrate=9600, tx=Pin(17), rx=Pin(16))
    except Exception:
        i2c = uart = None  # CPython / no hardware
    return Sampler(cfg["node_id"], th=Sht31(i2c), pm=PmSensor(uart))


def sleep_seconds(seconds):
    """Sleep between cycles. On the node a deep sleep would save power; this keeps RAM state."""
    try:
        import time

        time.sleep(seconds)
    except Exception:  # pragma: no cover
        pass


# -- the loop --------------------------------------------------------------------------------------


def run_once(sampler, buffer):
    """One cycle: sample, persist before send, then flush the backlog oldest-first.

    Returns ``(sampled, forwarded)``: whether a reading was taken and how many payloads the flush
    confirmed. Pulled out of :func:`run` so the cycle is unit-testable with fakes off-hardware.
    """
    payload = sampler.sample()
    if payload is not None:
        buffer.append(payload)  # persist to flash before any network attempt
    try:
        forwarded = buffer.flush()
    except TransportError:
        forwarded = 0  # link down: everything stays buffered for the next cycle
    return (payload is not None, forwarded)


def run(cfg=None):  # pragma: no cover - the node entry point; the body is exercised via run_once
    """Boot the node and loop forever."""
    cfg = cfg or load_config()
    connect_wifi(cfg)
    sync_clock()

    sampler = build_sampler(cfg)
    buffer = StoreAndForward(
        cfg["buffer_path"],
        transport=build_transport(cfg),
        max_records=cfg["buffer_max_records"],
    )

    while True:
        if not connect_wifi(cfg):
            # No link: keep sampling and buffering; the flush inside run_once is a no-op.
            pass
        run_once(sampler, buffer)
        sleep_seconds(cfg["sample_interval_s"])


if __name__ == "__main__":
    run()
