"""Background service: power base stations on/off together with SteamVR.

SteamVR on Linux always runs a `vrserver` process while it is up, so we simply
watch /proc for it. No OpenVR bindings needed.

If a station can't be reached when SteamVR exits (out of range, interference,
the machine went to sleep mid-way, ...) it is remembered and powered down
later in the background, as long as SteamVR stays closed.
"""

from __future__ import annotations

import logging
import os
import signal
import time

from . import actions, config

log = logging.getLogger(__name__)

VR_PROCESS_NAMES = {"vrserver"}
POLL_INTERVAL = 2.0
# SteamVR restarts briefly drop vrserver; wait this many polls before powering down
OFF_DEBOUNCE_POLLS = 3

# Background retries for stations that could not be powered down.
# Wall-clock based, so a retry is due right after the machine wakes from sleep.
RETRY_DELAYS = (60, 120, 300, 600)   # then every 600 s
RETRY_GIVE_UP = 6 * 3600             # stop trying after 6 h
RETRY_BUDGET = 30.0                  # seconds per station per background attempt


def steamvr_running() -> bool:
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            with open(f"/proc/{pid}/comm") as f:
                if f.read().strip() in VR_PROCESS_NAMES:
                    return True
        except OSError:
            continue
    return False


class PendingPowerDown:
    """Stations whose power-down failed, with their retry schedule."""

    def __init__(self):
        self.items: dict[str, dict] = {}  # address -> {"since", "next", "tries"}

    def add(self, address: str):
        now = time.time()
        item = self.items.setdefault(address, {"since": now, "tries": 0})
        delay = RETRY_DELAYS[min(item["tries"], len(RETRY_DELAYS) - 1)]
        item["next"] = now + delay
        log.info("%s: will retry power-down in %d min", address, delay // 60)

    def clear(self):
        if self.items:
            log.info("Dropping %d pending power-down(s)", len(self.items))
        self.items.clear()

    def due(self) -> list[str]:
        now = time.time()
        for addr, item in list(self.items.items()):
            if now - item["since"] > RETRY_GIVE_UP:
                log.warning("%s: giving up on powering down after %d h", addr, RETRY_GIVE_UP // 3600)
                del self.items[addr]
        return [a for a, i in self.items.items() if now >= i["next"]]

    def retry(self, stop_check) -> None:
        due = self.due()
        if not due:
            return
        s = config.load()
        if not s.power_management:
            self.clear()
            return
        for addr in due:
            if stop_check():
                return
            dev = next((d for d in s.managed if d.address == addr), None)
            if dev is None:  # no longer managed / forgotten
                del self.items[addr]
                continue
            item = self.items[addr]
            item["tries"] += 1
            try:
                actions.power_down(dev, s.power_down_mode, budget=RETRY_BUDGET)
                log.info("%s: powered down on retry %d", dev.display_name, item["tries"])
                del self.items[addr]
            except Exception as e:  # noqa: BLE001
                log.info("%s: retry %d failed (%s)", dev.display_name, item["tries"], e)
                self.add(addr)


def _apply(turn_on: bool, pending: PendingPowerDown):
    s = config.load()
    if not s.power_management:
        log.info("Power management disabled, ignoring")
        return
    devs = s.managed
    if not devs:
        log.info("No managed base stations configured")
        return
    failed: list[str] = []
    if turn_on:
        log.info("SteamVR started -> powering on %d base station(s)", len(devs))
        fn = actions.power_on
    else:
        log.info("SteamVR stopped -> %s %d base station(s)", s.power_down_mode, len(devs))
        fn = lambda d: actions.power_down(d, s.power_down_mode)  # noqa: E731
    failures = actions.run_all(devs, fn, s.send_simultaneously,
                               lambda d, e: e is not None and failed.append(d.address))
    log.info("Done (%d failed)", failures)
    if not turn_on:
        for addr in failed:
            pending.add(addr)


def run():
    stop = False

    def handle(_sig, _frm):
        nonlocal stop
        stop = True

    signal.signal(signal.SIGTERM, handle)
    signal.signal(signal.SIGINT, handle)

    pending = PendingPowerDown()
    log.info("Watching for SteamVR (%s)", ", ".join(VR_PROCESS_NAMES))
    running = steamvr_running()
    if running:
        log.info("SteamVR already running")
        _apply(True, pending)
    missing = 0
    while not stop:
        time.sleep(POLL_INTERVAL)
        now = steamvr_running()
        if now:
            missing = 0
            if not running:
                running = True
                pending.clear()  # stations are about to be powered on anyway
                _apply(True, pending)
        elif running:
            missing += 1
            if missing >= OFF_DEBOUNCE_POLLS:
                running = False
                missing = 0
                _apply(False, pending)
        elif pending.items:
            pending.retry(lambda: stop or steamvr_running())
    log.info("Stopping")
