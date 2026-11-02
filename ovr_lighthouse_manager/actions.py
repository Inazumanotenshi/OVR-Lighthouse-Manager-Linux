"""Base station commands (protocol identical to the Windows OVR Lighthouse Manager)."""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Iterable

from . import ble
from .config import Device

log = logging.getLogger(__name__)

V2_POWER_STATES = {
    0x00: "sleep",
    0x01: "booting",
    0x02: "standby",
    0x08: "booting",
    0x09: "booting",
    0x0B: "on",
}


def _v1_payload(dev: Device, power_on: bool) -> bytes:
    if not dev.id or len(dev.id) != 8:
        raise ble.BleError(f"{dev.display_name}: V1 base stations need the 8-character ID from the back label "
                           f"(set it with: ovr-lighthouse-manager set-id {dev.address} XXXXXXXX)")
    head = bytes([0x12, 0x00, 0x00, 0x00]) if power_on else bytes([0x12, 0x02, 0x00, 0x01])
    id_bytes = bytes.fromhex(dev.id)[::-1]
    return head + id_bytes + bytes(12)


def power_on(dev: Device):
    if dev.version == 1:
        ble.write_characteristic(dev.address, ble.V1_POWER_CHAR, _v1_payload(dev, True), label="power on")
    else:
        ble.write_characteristic(dev.address, ble.V2_POWER_CHAR, b"\x01", label="power on")


def sleep(dev: Device, budget: float = 90.0):
    if dev.version == 1:
        ble.write_characteristic(dev.address, ble.V1_POWER_CHAR, _v1_payload(dev, False), budget, label="sleep")
    else:
        ble.write_characteristic(dev.address, ble.V2_POWER_CHAR, b"\x00", budget, label="sleep")


def standby(dev: Device, budget: float = 90.0):
    if dev.version == 1:
        raise ble.BleError("Standby is not supported on V1 base stations")
    ble.write_characteristic(dev.address, ble.V2_POWER_CHAR, b"\x02", budget, label="standby")


def identify(dev: Device):
    if dev.version == 1:
        raise ble.BleError("Identify is not supported on V1 base stations")
    ble.write_characteristic(dev.address, ble.V2_IDENTIFY_CHAR, b"\x01", label="identify")


def power_down(dev: Device, mode: str, budget: float = 90.0):
    if mode == "sleep" or dev.version == 1:
        sleep(dev, budget)
    else:
        standby(dev, budget)


def status(dev: Device) -> str:
    if dev.version != 2:
        return "unknown (V1)"
    data = ble.read_characteristic(dev.address, ble.V2_POWER_CHAR, label="status")
    if not data:
        return "unknown"
    return V2_POWER_STATES.get(data[0], f"0x{data[0]:02x}")


def channel(dev: Device) -> int | None:
    if dev.version != 2:
        return None
    data = ble.read_characteristic(dev.address, ble.V2_CHANNEL_CHAR, label="channel")
    if not data:
        return None
    return int.from_bytes(data[:4], "big") if len(data) >= 4 else data[0]


def run_all(devices: Iterable[Device], fn: Callable[[Device], None], simultaneous: bool,
            on_result: Callable[[Device, Exception | None], None] | None = None) -> int:
    """Run fn on every device. Returns number of failures."""
    devices = list(devices)
    failures = 0
    lock = threading.Lock()

    def one(d: Device):
        nonlocal failures
        err = None
        try:
            fn(d)
        except Exception as e:  # noqa: BLE001
            err = e
            log.error("%s: %s", d.display_name, e)
            with lock:
                failures += 1
        if on_result:
            on_result(d, err)

    if simultaneous:
        threads = [threading.Thread(target=one, args=(d,), daemon=True) for d in devices]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
    else:
        for i, d in enumerate(devices):
            if i:
                time.sleep(0.2)
            one(d)
    return failures
