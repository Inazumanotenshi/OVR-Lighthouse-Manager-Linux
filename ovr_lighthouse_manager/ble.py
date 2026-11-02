"""Minimal BlueZ (D-Bus) BLE client for SteamVR base stations.

Uses only dbus-python, which ships with SteamOS / most desktop distros.
Every public helper opens its own private bus connection so it is safe to
call from several threads at once.
"""

from __future__ import annotations

import logging
import time
from typing import Callable

import dbus

log = logging.getLogger(__name__)

BLUEZ = "org.bluez"
OBJ_MANAGER = "org.freedesktop.DBus.ObjectManager"
PROPS = "org.freedesktop.DBus.Properties"
ADAPTER_IF = "org.bluez.Adapter1"
DEVICE_IF = "org.bluez.Device1"
CHAR_IF = "org.bluez.GattCharacteristic1"

# GATT UUIDs (taken from the original OVR Lighthouse Manager)
V1_CONTROL_SERVICE = "0000cb00-0000-1000-8000-00805f9b34fb"
V1_POWER_CHAR = "0000cb01-0000-1000-8000-00805f9b34fb"
V2_CONTROL_SERVICE = "00001523-1212-efde-1523-785feabcd124"
V2_POWER_CHAR = "00001525-1212-efde-1523-785feabcd124"
V2_CHANNEL_CHAR = "00001524-1212-efde-1523-785feabcd124"
V2_IDENTIFY_CHAR = "00008421-1212-efde-1523-785feabcd124"

LIGHTHOUSE_PREFIXES = ("LHB-", "HTC BS")


class BleError(Exception):
    pass


def is_lighthouse_name(name: str | None) -> bool:
    return bool(name) and name.startswith(LIGHTHOUSE_PREFIXES)


def _dbus_name(exc: dbus.DBusException) -> str:
    try:
        return exc.get_dbus_name() or ""
    except Exception:
        return ""


class Bluez:
    def __init__(self, adapter: str | None = None):
        try:
            self.bus = dbus.SystemBus(private=True)
            self.om = dbus.Interface(self.bus.get_object(BLUEZ, "/"), OBJ_MANAGER)
            self.adapter_path = self._find_adapter(adapter)
        except dbus.DBusException as e:
            raise BleError(f"BlueZ not available: {e}") from e
        self._discovering = False

    # -- basics ---------------------------------------------------------
    def close(self):
        try:
            if self._discovering:
                self.stop_discovery()
            self.bus.close()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def objects(self) -> dict:
        return self.om.GetManagedObjects()

    def _find_adapter(self, wanted: str | None) -> str:
        for path, ifaces in self.objects().items():
            if ADAPTER_IF not in ifaces:
                continue
            if wanted is None or str(path).endswith(wanted) or ifaces[ADAPTER_IF].get("Address") == wanted:
                if not ifaces[ADAPTER_IF].get("Powered", False):
                    raise BleError(f"Bluetooth adapter {path} is powered off")
                return str(path)
        raise BleError("No Bluetooth adapter found")

    def _props(self, path: str):
        return dbus.Interface(self.bus.get_object(BLUEZ, path), PROPS)

    # -- discovery ------------------------------------------------------
    def start_discovery(self):
        adapter = dbus.Interface(self.bus.get_object(BLUEZ, self.adapter_path), ADAPTER_IF)
        try:
            adapter.SetDiscoveryFilter(dbus.Dictionary({"Transport": "le"}, signature="sv"))
        except dbus.DBusException as e:
            log.debug("SetDiscoveryFilter failed: %s", e)
        for i in range(3):
            try:
                adapter.StartDiscovery()
                self._discovering = True
                return
            except dbus.DBusException as e:
                if "InProgress" in _dbus_name(e):
                    return
                # several clients starting discovery at once can briefly fail
                log.debug("StartDiscovery failed (%s), retrying", _dbus_name(e) or e)
                time.sleep(0.3 + 0.3 * i)
        log.warning("Could not start discovery, continuing without it")

    def stop_discovery(self):
        adapter = dbus.Interface(self.bus.get_object(BLUEZ, self.adapter_path), ADAPTER_IF)
        try:
            adapter.StopDiscovery()
        except dbus.DBusException:
            pass
        self._discovering = False

    def lighthouses(self) -> list[tuple[str, str, str]]:
        """Return (object_path, name, address) for every known base station."""
        out = []
        for path, ifaces in self.objects().items():
            dev = ifaces.get(DEVICE_IF)
            if not dev or str(dev.get("Adapter", "")) != self.adapter_path:
                continue
            name = str(dev.get("Name", dev.get("Alias", "")))
            if is_lighthouse_name(name):
                out.append((str(path), name, str(dev.get("Address", "")).upper()))
        return out

    def find_device(self, address: str, timeout: float = 15.0) -> str:
        """Return the BlueZ object path of a device, scanning for it if needed.

        Leaves discovery running if it was started here; callers that want
        it stopped call stop_discovery() (close() does it too).
        """
        address = address.upper()

        def lookup():
            for path, ifaces in self.objects().items():
                dev = ifaces.get(DEVICE_IF)
                if dev and str(dev.get("Address", "")).upper() == address \
                        and str(dev.get("Adapter", "")) == self.adapter_path:
                    return str(path)
            return None

        path = lookup()
        if path:
            return path
        log.debug("%s not cached by BlueZ, scanning", address)
        self.start_discovery()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            time.sleep(0.5)
            path = lookup()
            if path:
                return path
        raise BleError(f"Base station {address} not found")

    # -- GATT -----------------------------------------------------------
    def connect(self, path: str, timeout: float = 20.0):
        props = self._props(path)
        dev = dbus.Interface(self.bus.get_object(BLUEZ, path), DEVICE_IF)
        if not props.Get(DEVICE_IF, "Connected"):
            try:
                dev.Connect(timeout=timeout)
            except dbus.DBusException as e:
                if "AlreadyConnected" not in _dbus_name(e):
                    raise BleError(f"Connect failed: {e.get_dbus_message()}") from e
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if props.Get(DEVICE_IF, "ServicesResolved"):
                return
            if not props.Get(DEVICE_IF, "Connected"):
                raise BleError("Device disconnected during service discovery")
            time.sleep(0.1)
        raise BleError("Timed out waiting for GATT services")

    def disconnect(self, path: str):
        try:
            dbus.Interface(self.bus.get_object(BLUEZ, path), DEVICE_IF).Disconnect()
        except dbus.DBusException:
            pass

    def find_characteristic(self, dev_path: str, uuid: str, timeout: float = 5.0) -> str:
        uuid = uuid.lower()
        deadline = time.monotonic() + timeout
        while True:
            for path, ifaces in self.objects().items():
                c = ifaces.get(CHAR_IF)
                if c and str(path).startswith(dev_path + "/") and str(c.get("UUID", "")).lower() == uuid:
                    return str(path)
            if time.monotonic() > deadline:
                raise BleError(f"Characteristic {uuid} not found")
            time.sleep(0.2)

    def write(self, char_path: str, data: bytes):
        char = dbus.Interface(self.bus.get_object(BLUEZ, char_path), CHAR_IF)
        try:
            char.WriteValue(dbus.Array([dbus.Byte(b) for b in data], signature="y"),
                            dbus.Dictionary({}, signature="sv"), timeout=10)
        except dbus.DBusException as e:
            raise BleError(f"Write failed: {e.get_dbus_message()}") from e

    def read(self, char_path: str) -> bytes:
        char = dbus.Interface(self.bus.get_object(BLUEZ, char_path), CHAR_IF)
        try:
            return bytes(char.ReadValue(dbus.Dictionary({}, signature="sv"), timeout=10))
        except dbus.DBusException as e:
            raise BleError(f"Read failed: {e.get_dbus_message()}") from e


# -- high level ------------------------------------------------------------

def scan(duration: float = 10.0, on_found: Callable[[str, str], None] | None = None,
         should_stop: Callable[[], bool] | None = None) -> dict[str, str]:
    """Scan for base stations. Returns {address: name}."""
    found: dict[str, str] = {}
    with Bluez() as bz:
        bz.start_discovery()
        deadline = time.monotonic() + duration
        while time.monotonic() < deadline:
            for _path, name, addr in bz.lighthouses():
                if addr not in found:
                    found[addr] = name
                    log.info("Found %s (%s)", name, addr)
                    if on_found:
                        on_found(name, addr)
            if should_stop and should_stop():
                break
            time.sleep(0.5)
        bz.stop_discovery()
    return found


def _with_connection(address: str, char_uuid: str, fn, budget: float, label: str):
    """Connect, run fn(bluez, characteristic_path), disconnect - with retries.

    Discovery is kept running *while* connecting. Tested on SteamOS: stopping
    discovery first connects faster (~3 s) but a single stuck connect then
    wedges the controller and every following attempt hangs for 30 s+.
    With discovery active the kernel connects at the end of its scan cycle
    (~10-13 s), and it has never wedged.
    """
    last: Exception | None = None
    deadline = time.monotonic() + budget
    attempt = 0
    # 'le-connection-abort-by-local' fails within ~2 s, so retry on a time
    # budget rather than a fixed count, backing off a little each time.
    while attempt < 3 or time.monotonic() < deadline:
        attempt += 1
        bz = None
        path = None
        try:
            bz = Bluez()
            bz.start_discovery()
            path = bz.find_device(address)
            bz.connect(path, timeout=35.0)
            char = bz.find_characteristic(path, char_uuid)
            result = fn(bz, char)
            log.info("%s %s: ok (attempt %d)", label, address, attempt)
            return result
        except (BleError, dbus.DBusException) as e:
            last = e
            log.warning("%s %s: attempt %d failed: %s", label, address, attempt, e)
            time.sleep(min(1.0 + 0.5 * attempt, 4.0))
        finally:
            if bz is not None:
                bz.stop_discovery()
                if path:
                    bz.disconnect(path)
                bz.close()
    raise BleError(f"{label} {address} failed after {attempt} attempts: {last}")


def write_characteristic(address: str, char_uuid: str, data: bytes, budget: float = 90.0, label: str = "write"):
    _with_connection(address, char_uuid, lambda bz, c: bz.write(c, data), budget, label)


def read_characteristic(address: str, char_uuid: str, budget: float = 45.0, label: str = "read") -> bytes:
    return _with_connection(address, char_uuid, lambda bz, c: bz.read(c), budget, label)


def adapter_available() -> bool:
    try:
        Bluez().close()
        return True
    except BleError:
        return False

