from __future__ import annotations

import argparse
import logging
import os
import sys

from . import __version__, actions, ble, config


def _targets(s: config.Settings, names: list[str], use_all: bool) -> list[config.Device]:
    if use_all:
        return list(s.devices)
    if not names:
        if not s.managed:
            sys.exit("No managed base stations. Run `scan` and `manage`, or pass names / --all.")
        return s.managed
    out = []
    for n in names:
        d = s.find(n)
        if not d:
            sys.exit(f"Unknown base station: {n} (run `scan` first)")
        out.append(d)
    return out


def cmd_scan(a):
    s = config.load()
    print(f"Scanning for {a.time:.0f}s ...")
    found = ble.scan(a.time, on_found=lambda n, addr: print(f"  found {n}  {addr}"))
    for addr, name in found.items():
        s.upsert(name, addr)
    config.save(s)
    print(f"{len(found)} base station(s) found, {len(s.devices)} known.")


def cmd_list(a):
    s = config.load()
    print(f"Power management: {'on' if s.power_management else 'off'} | "
          f"power down: {s.power_down_mode} | simultaneous: {'on' if s.send_simultaneously else 'off'}")
    if not s.devices:
        print("No base stations known. Run `scan`.")
    for d in s.devices:
        flag = "[x]" if d.managed else "[ ]"
        extra = f"  id={d.id}" if d.version == 1 else ""
        name = d.display_name + (f" ({d.name})" if d.custom_name else "")
        print(f"{flag} V{d.version}  {d.address}  {name}{extra}")


def _set_managed(a, value: bool):
    s = config.load()
    for d in _targets(s, a.names, a.all or not a.names):
        d.managed = value
        print(f"{'managing' if value else 'not managing'} {d.display_name}")
    config.save(s)


def _run(a, fn, verb):
    s = config.load()
    devs = _targets(s, a.names, a.all)

    def res(d, err):
        print(f"{d.display_name}: {verb} " + ("OK" if err is None else f"FAILED ({err})"), flush=True)

    fails = actions.run_all(devs, fn, s.send_simultaneously, res)
    sys.exit(1 if fails else 0)


def cmd_status(a):
    s = config.load()
    for d in _targets(s, a.names, a.all):
        try:
            print(f"{d.display_name}: {actions.status(d)}", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"{d.display_name}: error ({e})", flush=True)


def cmd_set_id(a):
    s = config.load()
    d = s.find(a.name)
    if not d:
        sys.exit(f"Unknown base station: {a.name}")
    try:
        bytes.fromhex(a.id)
        assert len(a.id) == 8
    except (ValueError, AssertionError):
        sys.exit("ID must be 8 hex characters")
    d.id = a.id.upper()
    config.save(s)
    print(f"{d.display_name}: id set to {d.id}")


def cmd_rename(a):
    s = config.load()
    d = s.find(a.name)
    if not d:
        sys.exit(f"Unknown base station: {a.name}")
    d.custom_name = a.new_name or None
    config.save(s)
    print(f"{d.name} -> {d.display_name}")


def cmd_forget(a):
    s = config.load()
    d = s.find(a.name)
    if not d:
        sys.exit(f"Unknown base station: {a.name}")
    s.devices.remove(d)
    config.save(s)
    print(f"forgot {d.display_name}")


def _onoff(v: str) -> bool:
    if v.lower() in ("on", "1", "true", "yes"):
        return True
    if v.lower() in ("off", "0", "false", "no"):
        return False
    raise argparse.ArgumentTypeError("expected on/off")


def cmd_config(a):
    s = config.load()
    if a.power_management is not None:
        s.power_management = a.power_management
    if a.power_down is not None:
        s.power_down_mode = a.power_down
    if a.simultaneous is not None:
        s.send_simultaneously = a.simultaneous
    config.save(s)
    cmd_list(a)


def cmd_daemon(a):
    from . import watcher
    watcher.run()


def cmd_gui(a):
    from . import gui
    sys.exit(gui.main())


def main(argv=None):
    p = argparse.ArgumentParser(prog="ovr-lighthouse-manager",
                                description="SteamVR base station power manager for Linux")
    p.add_argument("--version", action="version", version=__version__)
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd")

    sp = sub.add_parser("scan", help="scan for base stations and remember them")
    sp.add_argument("-t", "--time", type=float, default=10)
    sp.set_defaults(func=cmd_scan)

    sub.add_parser("list", help="list known base stations and settings").set_defaults(func=cmd_list)

    def targets(sp, all_help="all known base stations (default: managed ones)"):
        sp.add_argument("names", nargs="*", help="name, custom name or MAC address")
        sp.add_argument("-a", "--all", action="store_true", help=all_help)
        return sp

    targets(sub.add_parser("manage", help="link base stations to SteamVR (no names = all)"),
            "all known").set_defaults(func=lambda a: _set_managed(a, True))
    targets(sub.add_parser("unmanage", help="unlink base stations from SteamVR (no names = all)"),
            "all known").set_defaults(func=lambda a: _set_managed(a, False))

    targets(sub.add_parser("on", help="power on")).set_defaults(
        func=lambda a: _run(a, actions.power_on, "power on"))
    targets(sub.add_parser("sleep", help="sleep (fully off)")).set_defaults(
        func=lambda a: _run(a, actions.sleep, "sleep"))
    targets(sub.add_parser("standby", help="standby (V2 only, faster wake)")).set_defaults(
        func=lambda a: _run(a, actions.standby, "standby"))
    targets(sub.add_parser("off", help="power down using the configured mode")).set_defaults(
        func=lambda a: _run(a, lambda d: actions.power_down(d, config.load().power_down_mode), "power down"))
    targets(sub.add_parser("identify", help="blink LED (V2 only)")).set_defaults(
        func=lambda a: _run(a, actions.identify, "identify"))
    targets(sub.add_parser("status", help="read power state (V2 only)")).set_defaults(func=cmd_status)

    sp = sub.add_parser("set-id", help="set the 8-char ID of a V1 base station")
    sp.add_argument("name")
    sp.add_argument("id")
    sp.set_defaults(func=cmd_set_id)

    sp = sub.add_parser("rename", help="set a custom display name (empty to reset)")
    sp.add_argument("name")
    sp.add_argument("new_name", nargs="?", default="")
    sp.set_defaults(func=cmd_rename)

    sp = sub.add_parser("forget", help="remove a base station from the list")
    sp.add_argument("name")
    sp.set_defaults(func=cmd_forget)

    sp = sub.add_parser("config", help="change settings")
    sp.add_argument("--power-management", type=_onoff, metavar="on|off")
    sp.add_argument("--power-down", choices=config.POWER_DOWN_MODES)
    sp.add_argument("--simultaneous", type=_onoff, metavar="on|off")
    sp.set_defaults(func=cmd_config)

    sub.add_parser("daemon", help="run the SteamVR watcher in the foreground").set_defaults(func=cmd_daemon)
    sub.add_parser("gui", help="open the graphical interface").set_defaults(func=cmd_gui)

    a = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if a.verbose else (logging.INFO if a.cmd in ("daemon", "gui") else logging.WARNING),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if not a.cmd:
        if os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
            return cmd_gui(a)
        p.print_help()
        return 0
    try:
        a.func(a)
    except ble.BleError as e:
        sys.exit(f"Bluetooth error: {e}")
    except KeyboardInterrupt:
        sys.exit(130)
