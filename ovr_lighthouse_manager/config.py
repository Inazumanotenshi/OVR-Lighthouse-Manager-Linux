from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "ovr-lighthouse-manager"
CONFIG_FILE = CONFIG_DIR / "settings.json"

POWER_DOWN_MODES = ("standby", "sleep")


@dataclass
class Device:
    name: str
    address: str
    custom_name: str | None = None
    id: str | None = None  # only needed for V1 (HTC BS) stations
    managed: bool = False

    @property
    def version(self) -> int:
        if self.name.startswith("HTC BS"):
            return 1
        if self.name.startswith("LHB-"):
            return 2
        return 0

    @property
    def display_name(self) -> str:
        return self.custom_name or self.name


@dataclass
class Settings:
    power_management: bool = True
    power_down_mode: str = "standby"
    send_simultaneously: bool = False
    devices: list[Device] = field(default_factory=list)

    def find(self, key: str) -> Device | None:
        k = key.lower()
        for d in self.devices:
            if k in (d.address.lower(), d.name.lower(), (d.custom_name or "").lower()):
                return d
        return None

    def upsert(self, name: str, address: str) -> Device:
        address = address.upper()
        for d in self.devices:
            if d.address == address:
                d.name = name
                return d
        d = Device(name=name, address=address)
        self.devices.append(d)
        return d

    @property
    def managed(self) -> list[Device]:
        return [d for d in self.devices if d.managed]


def load() -> Settings:
    try:
        raw = json.loads(CONFIG_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return Settings()
    devices = [Device(**{k: v for k, v in d.items() if k in Device.__dataclass_fields__})
               for d in raw.get("devices", [])]
    mode = raw.get("power_down_mode", "standby")
    return Settings(
        power_management=bool(raw.get("power_management", True)),
        power_down_mode=mode if mode in POWER_DOWN_MODES else "standby",
        send_simultaneously=bool(raw.get("send_simultaneously", False)),
        devices=devices,
    )


def save(settings: Settings):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    data = asdict(settings)
    fd, tmp = tempfile.mkstemp(dir=CONFIG_DIR, prefix=".settings-", suffix=".json")
    with os.fdopen(fd, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, CONFIG_FILE)
