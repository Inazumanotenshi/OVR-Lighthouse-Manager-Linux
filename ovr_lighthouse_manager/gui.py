"""GTK4 user interface, styled after SteamVR / the Steam gamepad UI."""

from __future__ import annotations

import logging
import subprocess
import sys
import threading
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GLib, Gtk, Pango  # noqa: E402

from . import __version__, actions, ble, config, watcher  # noqa: E402

log = logging.getLogger(__name__)

APP_ID = "io.github.kurotu.OVRLighthouseManager.Linux"
SERVICE = "ovr-lighthouse-manager.service"
ASSETS = Path(__file__).parent / "assets"

# Palette from Steam's own gamepad UI / SteamVR web interface CSS
CSS = """
@define-color sv_darkest  #0e141b;
@define-color sv_darkish  #171d25;
@define-color sv_darker   #23262e;
@define-color sv_dark     #3d4450;
@define-color sv_grey     #67707b;
@define-color sv_light    #8b929a;
@define-color sv_lighter  #b8bcbf;
@define-color sv_lightest #dcdedf;
@define-color sv_blue     #1a9fff;
@define-color sv_blue_hi  #47bfff;
@define-color sv_green    #9dc112;
@define-color sv_amber    #e6be42;
@define-color sv_red      #d94453;

window, window.background, .sv-root {
  background-color: @sv_darkest;
  color: @sv_lightest;
  font-family: "Motiva Sans", "Adwaita Sans", "Noto Sans", sans-serif;
  font-size: 11pt;
}
label { color: @sv_lightest; }

/* ---- header ---- */
headerbar.sv-header {
  background: @sv_darkest;
  box-shadow: none;
  border-bottom: 1px solid alpha(@sv_dark, 0.6);
  min-height: 52px;
  padding: 0 8px;
}
.sv-apptitle { font-weight: 800; letter-spacing: 2px; font-size: 12pt; color: white; }
.sv-apptitle-dim { font-weight: 400; letter-spacing: 2px; font-size: 12pt; color: @sv_light; }

.sv-pill {
  background: @sv_darker; border-radius: 999px; padding: 5px 14px 5px 10px;
  border: 1px solid alpha(@sv_dark, 0.8);
}
.sv-pill label { font-size: 9.5pt; font-weight: 600; letter-spacing: 0.5px; }

/* ---- sidebar ---- */
.sv-sidebar { background: @sv_darkish; border-right: 1px solid alpha(@sv_dark, 0.5); }
.sv-sidebar list { background: transparent; }
.sv-sidebar row {
  padding: 12px 18px; margin: 2px 8px; border-radius: 6px; color: @sv_lighter;
  border-left: 3px solid transparent;
}
.sv-sidebar row:hover { background: alpha(@sv_dark, 0.55); }
.sv-sidebar row:selected { background: @sv_dark; border-left: 3px solid @sv_blue; }
.sv-sidebar row:selected label { color: white; }
.sv-sidebar row label { font-weight: 600; }
.sv-sidebar row image { color: @sv_light; }
.sv-sidebar row:selected image { color: @sv_blue_hi; }
.sv-sidefoot { padding: 14px 18px; }
.sv-sidefoot label { font-size: 9pt; color: @sv_light; }

/* ---- content ---- */
.sv-page { padding: 24px 28px; }
.sv-h1 { font-size: 18pt; font-weight: 700; color: white; }
.sv-section {
  font-size: 9pt; font-weight: 700; letter-spacing: 1.5px; color: @sv_light; margin-top: 8px;
}
.sv-dim { color: @sv_light; }
.sv-small { font-size: 9pt; }

.sv-card {
  background: @sv_darker; border-radius: 10px; padding: 16px;
  border: 1px solid alpha(@sv_dark, 0.55);
}
.sv-card.managed { border-color: alpha(@sv_blue, 0.45); }
.sv-card-title { font-weight: 700; font-size: 12.5pt; color: white; }
.sv-card-sub { font-size: 9pt; color: @sv_light; }
.sv-mono { font-family: "Adwaita Mono", "Hack", monospace; font-size: 8.5pt; color: @sv_grey; }

flowbox > flowboxchild { padding: 0; background: transparent; }
flowbox > flowboxchild:focus { outline: none; }

.sv-state { font-size: 9pt; font-weight: 700; letter-spacing: 1.2px; }
.state-on      { color: @sv_green; }
.state-standby { color: @sv_amber; }
.state-sleep   { color: @sv_grey; }
.state-booting { color: @sv_blue_hi; }
.state-unknown { color: @sv_grey; }
.state-error   { color: @sv_red; }

/* ---- buttons ---- */
.sv-content button {
  background-image: none; background-color: @sv_dark; color: @sv_lightest;
  border: none; border-radius: 4px; box-shadow: none; text-shadow: none;
  padding: 7px 14px; min-height: 22px; font-weight: 600;
}
.sv-content button:hover { background-color: #4b5361; color: white; }
.sv-content button:active { background-color: @sv_grey; }
.sv-content button:disabled { background-color: alpha(@sv_dark, 0.45); color: @sv_grey; }
.sv-content button.sv-primary { background-color: @sv_blue; color: white; }
.sv-content button.sv-primary:hover { background-color: @sv_blue_hi; }
.sv-content button.sv-flat { background: transparent; color: @sv_light; padding: 6px; }
.sv-content button.sv-flat:hover { background: @sv_dark; color: white; }
.sv-content button.sv-danger:hover { background-color: @sv_red; color: white; }

.sv-content .sv-seg { background: @sv_darkest; border-radius: 6px; padding: 3px; }
.sv-content .sv-seg button { background: transparent; border-radius: 4px; color: @sv_lighter; padding: 6px 4px; }
.sv-content .sv-seg button:hover { background: @sv_dark; color: white; }
.sv-content .sv-seg button.active { background: @sv_dark; color: white; box-shadow: inset 0 -2px @sv_blue; }
.sv-content .sv-seg button.active.on { box-shadow: inset 0 -2px @sv_green; }
.sv-content .sv-seg button.active.standby { box-shadow: inset 0 -2px @sv_amber; }
.sv-content .sv-seg button.active.sleep { box-shadow: inset 0 -2px @sv_grey; }
.sv-content .sv-seg button:disabled { background: transparent; color: alpha(@sv_grey, 0.6); }

/* ---- switches ---- */
.sv-content switch {
  background: @sv_dark; border: none; border-radius: 999px; box-shadow: none; outline: none;
  min-width: 46px; min-height: 24px; padding: 2px;
}
.sv-content switch:checked { background: @sv_blue; }
.sv-content switch > slider {
  background: @sv_lightest; border: none; border-radius: 999px; box-shadow: none;
  min-width: 20px; min-height: 20px; margin: 0;
}
.sv-content switch:checked > slider { background: white; }
.sv-content switch image { color: transparent; }

/* ---- settings rows ---- */
.sv-group { background: @sv_darker; border-radius: 10px; border: 1px solid alpha(@sv_dark, 0.55); }
.sv-row { padding: 14px 18px; border-bottom: 1px solid alpha(@sv_dark, 0.5); }
.sv-row.last { border-bottom: none; }
.sv-row-title { font-weight: 600; color: white; }
.sv-row-desc { font-size: 9pt; color: @sv_light; }

/* ---- misc ---- */
scrollbar { background: transparent; }
scrollbar slider { background: @sv_dark; border-radius: 999px; min-width: 6px; }
popover > contents { background: @sv_darker; border: 1px solid @sv_dark; border-radius: 8px; padding: 6px; }
popover > arrow { background: @sv_darker; border: 1px solid @sv_dark; }
popover button { background: transparent; padding: 8px 14px; }
.sv-content menubutton.sv-flat > button { background: transparent; color: @sv_light; padding: 6px; }
.sv-content menubutton.sv-flat > button:hover, .sv-content menubutton.sv-flat > button:checked {
  background: @sv_dark; color: white; }
popover button:hover { background: @sv_dark; }
entry {
  background: @sv_darkest; color: white; border: 1px solid @sv_dark; border-radius: 4px;
  box-shadow: none; padding: 6px 10px; caret-color: @sv_blue;
}
entry:focus-within { border-color: @sv_blue; outline: none; }
.sv-toast {
  background: @sv_dark; color: white; border-radius: 6px; padding: 10px 18px;
  margin-bottom: 18px; border-left: 3px solid @sv_blue;
  box-shadow: 0 6px 18px rgba(0,0,0,0.5);
}
.sv-toast.error { border-left-color: @sv_red; }
.sv-empty { padding: 60px; }
.sv-empty label { color: @sv_light; }
"""

STATE_COLORS = {
    "on": "#9dc112", "standby": "#e6be42", "sleep": "#4b5361",
    "booting": "#47bfff", "unknown": "#3d4450", "error": "#d94453",
}
STATE_TEXT = {
    "on": "ON", "standby": "STANDBY", "sleep": "SLEEP", "booting": "STARTING",
    "unknown": "UNKNOWN", "error": "NOT REACHABLE",
}


def station_svg(led: str) -> bytes:
    glow = "" if led in ("#4b5361", "#3d4450") else \
        f'<circle cx="64" cy="22" r="11" fill="{led}" opacity="0.35"/>'
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128" viewBox="0 0 128 128">
<defs>
 <linearGradient id="b" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#4a525e"/>
  <stop offset="0.15" stop-color="#2c323b"/><stop offset="1" stop-color="#11161c"/></linearGradient>
 <linearGradient id="l" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#1e252e"/>
  <stop offset="1" stop-color="#05080b"/></linearGradient>
 <linearGradient id="g" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff" stop-opacity="0.2"/>
  <stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>
</defs>
<rect x="52" y="104" width="24" height="14" rx="4" fill="#0b0f14"/>
<rect x="38" y="114" width="52" height="9" rx="4.5" fill="#1b212a"/>
<rect x="14" y="8" width="100" height="102" rx="26" fill="url(#b)"/>
<rect x="14.5" y="8.5" width="99" height="101" rx="25.5" fill="none" stroke="#fff" stroke-opacity="0.1"/>
<rect x="25" y="32" width="78" height="68" rx="17" fill="url(#l)"/>
<path d="M42 32 H86 A17 17 0 0 1 103 49 V54 Q64 45 25 57 V49 A17 17 0 0 1 42 32 Z" fill="url(#g)"/>
{glow}<circle cx="64" cy="22" r="4.2" fill="{led}"/>
</svg>""".encode()


def station_texture(state: str) -> Gdk.Texture:
    return Gdk.Texture.new_from_bytes(GLib.Bytes.new(station_svg(STATE_COLORS.get(state, "#3d4450"))))


def _systemctl(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["systemctl", "--user", *args, SERVICE], capture_output=True, text=True)


def service_installed() -> bool:
    return _systemctl("cat").returncode == 0


def service_enabled() -> bool:
    return _systemctl("is-enabled").stdout.strip() == "enabled"


def service_active() -> bool:
    return _systemctl("is-active").stdout.strip() == "active"


def dot(color: str, size: int = 10) -> Gtk.DrawingArea:
    area = Gtk.DrawingArea(content_width=size, content_height=size, valign=Gtk.Align.CENTER)
    area._color = color

    def draw(_a, cr, w, h):
        rgba = Gdk.RGBA()
        rgba.parse(area._color)
        cr.set_source_rgba(rgba.red, rgba.green, rgba.blue, rgba.alpha)
        cr.arc(w / 2, h / 2, min(w, h) / 2, 0, 6.2832)
        cr.fill()

    area.set_draw_func(draw)

    def set_color(c):
        area._color = c
        area.queue_draw()

    area.set_color = set_color
    return area


# ---------------------------------------------------------------- station card

class StationCard(Gtk.Box):
    def __init__(self, win: "MainWindow", dev: config.Device):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        self.win = win
        self.dev = dev
        self.busy = False
        self.add_css_class("sv-card")
        self.set_size_request(300, -1)
        v1 = dev.version == 1

        # top: picture + name + menu
        top = Gtk.Box(spacing=14)
        stack = Gtk.Overlay()
        self.picture = Gtk.Image(pixel_size=68, valign=Gtk.Align.CENTER)
        stack.set_child(self.picture)
        self.spinner = Gtk.Spinner(halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER, width_request=22,
                                   height_request=22)
        stack.add_overlay(self.spinner)
        top.append(stack)

        names = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3, valign=Gtk.Align.CENTER, hexpand=True)
        self.title = Gtk.Label(xalign=0, ellipsize=Pango.EllipsizeMode.END)
        self.title.add_css_class("sv-card-title")
        self.sub = Gtk.Label(xalign=0, ellipsize=Pango.EllipsizeMode.END)
        self.sub.add_css_class("sv-card-sub")
        self.addr = Gtk.Label(xalign=0, ellipsize=Pango.EllipsizeMode.END, selectable=True)
        self.addr.add_css_class("sv-card-sub")
        self.addr.add_css_class("sv-mono")
        staterow = Gtk.Box(spacing=7, margin_top=4)
        self.state_dot = dot(STATE_COLORS["unknown"], 8)
        self.state_lbl = Gtk.Label(xalign=0)
        self.state_lbl.add_css_class("sv-state")
        staterow.append(self.state_dot)
        staterow.append(self.state_lbl)
        names.append(self.title)
        names.append(self.sub)
        names.append(self.addr)
        names.append(staterow)
        top.append(names)

        menu_btn = Gtk.MenuButton(icon_name="view-more-symbolic", valign=Gtk.Align.START, tooltip_text="More")
        menu_btn.add_css_class("sv-flat")
        pop = Gtk.Popover()
        pbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        def item(label, cb, sensitive=True):
            b = Gtk.Button(label=label, sensitive=sensitive)
            b.get_child().set_xalign(0)
            b.connect("clicked", lambda *_: (pop.popdown(), cb()))
            pbox.append(b)

        item("Identify (blink LED)", lambda: self._do(actions.identify, "identify", None), not v1)
        item("Refresh state", self.refresh_state, not v1)
        item("Set ID / rename…" if v1 else "Rename…", self._edit)
        item("Forget", lambda: self.win.forget(self.dev))
        pop.set_child(pbox)
        menu_btn.set_popover(pop)
        top.append(menu_btn)
        self.append(top)

        # power segmented control
        seg = Gtk.Box(homogeneous=True, spacing=3)
        seg.add_css_class("sv-seg")
        self.seg_buttons = {}
        for key, label, fn, ok in (("on", "On", actions.power_on, True),
                                   ("standby", "Standby", actions.standby, not v1),
                                   ("sleep", "Sleep", actions.sleep, True)):
            b = Gtk.Button(label=label, sensitive=ok)
            b.add_css_class(key)
            b.connect("clicked", lambda _b, f=fn, k=key: self._do(f, k, k))
            b._ok = ok
            seg.append(b)
            self.seg_buttons[key] = b
        self.append(seg)

        # managed toggle
        auto = Gtk.Box(spacing=10)
        lbl = Gtk.Label(label="Control with SteamVR", xalign=0, hexpand=True)
        lbl.add_css_class("sv-dim")
        self.managed = Gtk.Switch(active=dev.managed, valign=Gtk.Align.CENTER)
        self.managed.connect("notify::active", self._on_managed)
        auto.append(lbl)
        auto.append(self.managed)
        self.append(auto)

        self.update_labels()
        self.set_state(win.states.get(dev.address, "unknown"))

    # ---- presentation
    def update_labels(self):
        d = self.dev
        self.title.set_text(d.display_name)
        sub = f"Base Station {'1.0' if d.version == 1 else '2.0'}"
        if d.custom_name:
            sub += f"  ·  {d.name}"
        if d.version == 1 and not d.id:
            sub += "  ·  ID missing"
        self.sub.set_text(sub)
        self.sub.set_tooltip_text(sub)
        self.addr.set_text(d.address)
        if d.managed:
            self.add_css_class("managed")
        else:
            self.remove_css_class("managed")

    def set_state(self, state: str):
        self.state = state
        self.win.states[self.dev.address] = state
        self.picture.set_from_paintable(station_texture(state))
        self.state_dot.set_color(STATE_COLORS.get(state, STATE_COLORS["unknown"]))
        self.state_lbl.set_text(STATE_TEXT.get(state, state.upper()))
        for k in STATE_TEXT:
            self.state_lbl.remove_css_class(f"state-{k}")
        self.state_lbl.add_css_class(f"state-{state if state in STATE_TEXT else 'unknown'}")
        for k, b in self.seg_buttons.items():
            if k == state or (k == "on" and state == "booting"):
                b.add_css_class("active")
            else:
                b.remove_css_class("active")

    def set_busy(self, busy: bool):
        self.busy = busy
        if busy:
            self.spinner.start()
        else:
            self.spinner.stop()
        for b in self.seg_buttons.values():
            b.set_sensitive(b._ok and not busy)

    # ---- actions
    def _on_managed(self, sw, _p):
        self.dev.managed = sw.get_active()
        self.update_labels()
        self.win.save()

    def _do(self, fn, verb, new_state):
        if self.busy:
            return
        self.set_busy(True)
        name = self.dev.display_name

        def work():
            try:
                fn(self.dev)
                GLib.idle_add(self._done, new_state, f"{name}: {verb} ✓", False)
            except Exception as e:  # noqa: BLE001
                log.error("%s: %s", name, e)
                GLib.idle_add(self._done, None, f"{name}: {verb} failed", True)

        threading.Thread(target=work, daemon=True).start()

    def _done(self, new_state, msg, error):
        self.set_busy(False)
        if new_state:
            self.set_state(new_state)
        self.win.toast(msg, error)

    def refresh_state(self, quiet=False):
        if self.busy or self.dev.version != 2:
            return
        self.set_busy(True)

        def work():
            try:
                st = actions.status(self.dev)
            except Exception as e:  # noqa: BLE001
                log.warning("%s: %s", self.dev.display_name, e)
                st = "error"
            GLib.idle_add(self._state_read, st)

        threading.Thread(target=work, daemon=True).start()

    def _state_read(self, st):
        self.set_busy(False)
        self.set_state(st if st in STATE_TEXT else "unknown")

    def _edit(self):
        dlg = Gtk.Window(transient_for=self.win, modal=True, title="Edit base station", default_width=380,
                         resizable=False)
        dlg.add_css_class("sv-root")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=20, margin_bottom=20,
                      margin_start=20, margin_end=20)
        box.add_css_class("sv-content")
        sec = Gtk.Label(label="DISPLAY NAME", xalign=0)
        sec.add_css_class("sv-section")
        box.append(sec)
        name = Gtk.Entry(text=self.dev.custom_name or "", placeholder_text=self.dev.name)
        box.append(name)
        idfield = None
        if self.dev.version == 1:
            sec = Gtk.Label(label="ID  (8 CHARACTERS ON THE BACK LABEL)", xalign=0)
            sec.add_css_class("sv-section")
            box.append(sec)
            idfield = Gtk.Entry(text=self.dev.id or "", max_length=8)
            box.append(idfield)
        err = Gtk.Label(xalign=0)
        err.add_css_class("state-error")
        box.append(err)
        btns = Gtk.Box(spacing=8, halign=Gtk.Align.END, margin_top=8)
        cancel = Gtk.Button(label="Cancel")
        ok = Gtk.Button(label="Save")
        ok.add_css_class("sv-primary")
        btns.append(cancel)
        btns.append(ok)
        box.append(btns)
        dlg.set_child(box)

        def save(*_):
            if idfield is not None:
                v = idfield.get_text().strip().upper()
                if v:
                    try:
                        bytes.fromhex(v)
                        assert len(v) == 8
                    except (ValueError, AssertionError):
                        err.set_text("ID must be 8 hex characters")
                        return
                self.dev.id = v or None
            self.dev.custom_name = name.get_text().strip() or None
            self.update_labels()
            self.win.save()
            dlg.close()

        ok.connect("clicked", save)
        name.connect("activate", save)
        cancel.connect("clicked", lambda *_: dlg.close())
        dlg.present()


# ---------------------------------------------------------------- main window

class MainWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="OVR Lighthouse Manager", default_width=1000, default_height=680)
        self.add_css_class("sv-root")
        self.settings = config.load()
        self.states: dict[str, str] = {}
        self.cards: list[StationCard] = []
        self._scanning = False
        self._toast_id = 0

        # ---- header
        header = Gtk.HeaderBar(show_title_buttons=True)
        header.add_css_class("sv-header")
        header.set_decoration_layout(":minimize,maximize,close")
        brand = Gtk.Box(spacing=10, valign=Gtk.Align.CENTER, margin_start=6)
        logo = Gtk.Image(icon_name=APP_ID, pixel_size=28)
        t1 = Gtk.Label(label="LIGHTHOUSE")
        t1.add_css_class("sv-apptitle")
        t2 = Gtk.Label(label="MANAGER")
        t2.add_css_class("sv-apptitle-dim")
        for w in (logo, t1, t2):
            brand.append(w)
        header.pack_start(brand)
        header.set_title_widget(Gtk.Box())

        pill = Gtk.Box(spacing=8, valign=Gtk.Align.CENTER, margin_end=8)
        pill.add_css_class("sv-pill")
        self.vr_dot = dot("#67707b", 9)
        self.vr_lbl = Gtk.Label()
        pill.append(self.vr_dot)
        pill.append(self.vr_lbl)
        header.pack_end(pill)
        self.set_titlebar(header)

        # ---- body: sidebar + stack
        body = Gtk.Box()
        body.add_css_class("sv-content")
        side = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, width_request=220)
        side.add_css_class("sv-sidebar")
        nav = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE, margin_top=12)
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, hexpand=True, vexpand=True)
        self._pages = []
        for key, label, icon, builder in (("stations", "Base Stations", "network-wireless-symbolic", self._page_stations),
                                          ("settings", "Settings", "emblem-system-symbolic", self._page_settings),
                                          ("about", "About", "help-about-symbolic", self._page_about)):
            row = Gtk.ListBoxRow()
            rb = Gtk.Box(spacing=12)
            rb.append(Gtk.Image(icon_name=icon))
            rb.append(Gtk.Label(label=label, xalign=0))
            row.set_child(rb)
            nav.append(row)
            self.stack.add_named(builder(), key)
            self._pages.append(key)
        nav.connect("row-selected", lambda _l, r: r and self.stack.set_visible_child_name(self._pages[r.get_index()]))
        nav.select_row(nav.get_row_at_index(0))
        side.append(nav)
        side.append(Gtk.Box(vexpand=True))
        foot = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        foot.add_css_class("sv-sidefoot")
        fl = Gtk.Box(spacing=8)
        self.svc_dot = dot("#67707b", 8)
        self.svc_foot = Gtk.Label(xalign=0, wrap=True)
        fl.append(self.svc_dot)
        fl.append(self.svc_foot)
        foot.append(fl)
        side.append(foot)
        body.append(side)

        overlay = Gtk.Overlay()
        overlay.set_child(self.stack)
        self.toast_rev = Gtk.Revealer(transition_type=Gtk.RevealerTransitionType.SLIDE_UP,
                                      halign=Gtk.Align.CENTER, valign=Gtk.Align.END)
        self.toast_lbl = Gtk.Label(wrap=True, max_width_chars=70)
        self.toast_lbl.add_css_class("sv-toast")
        self.toast_rev.set_child(self.toast_lbl)
        overlay.add_overlay(self.toast_rev)
        body.append(overlay)
        self.set_child(body)

        self.rebuild()
        self._tick()
        GLib.timeout_add_seconds(3, self._tick)

        if not ble.adapter_available():
            self.toast("No powered Bluetooth adapter found", True)
            self.scan_btn.set_sensitive(False)
        elif not self.settings.devices:
            GLib.idle_add(self.scan)
        else:
            GLib.timeout_add(400, self.refresh_all)

    # ---------------- pages
    def _page_scroller(self, child):
        sc = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True)
        sc.set_child(child)
        return sc

    def _page_stations(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        page.add_css_class("sv-page")
        head = Gtk.Box(spacing=10)
        titles = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
        h = Gtk.Label(label="Base Stations", xalign=0)
        h.add_css_class("sv-h1")
        self.count_lbl = Gtk.Label(xalign=0)
        self.count_lbl.add_css_class("sv-dim")
        titles.append(h)
        titles.append(self.count_lbl)
        head.append(titles)

        refresh = Gtk.Button(icon_name="view-refresh-symbolic", tooltip_text="Refresh states", valign=Gtk.Align.CENTER)
        refresh.connect("clicked", lambda *_: self.refresh_all())
        on_all = Gtk.Button(label="All on", valign=Gtk.Align.CENTER, tooltip_text="Power on all SteamVR-controlled stations")
        off_all = Gtk.Button(label="All off", valign=Gtk.Align.CENTER, tooltip_text="Power down all SteamVR-controlled stations")
        on_all.connect("clicked", lambda *_: self.run_managed(True))
        off_all.connect("clicked", lambda *_: self.run_managed(False))
        self.scan_btn = Gtk.Button(valign=Gtk.Align.CENTER)
        sb = Gtk.Box(spacing=8)
        self.scan_spin = Gtk.Spinner(visible=False)
        sb.append(self.scan_spin)
        self.scan_lbl = Gtk.Label(label="Scan")
        sb.append(self.scan_lbl)
        self.scan_btn.set_child(sb)
        self.scan_btn.add_css_class("sv-primary")
        self.scan_btn.connect("clicked", lambda *_: self.scan())
        for w in (refresh, on_all, off_all, self.scan_btn):
            head.append(w)
        page.append(head)

        self.flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, homogeneous=True,
                                column_spacing=14, row_spacing=14, min_children_per_line=2,
                                max_children_per_line=3, valign=Gtk.Align.START)
        self.empty = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, halign=Gtk.Align.CENTER)
        self.empty.add_css_class("sv-empty")
        img = Gtk.Picture(paintable=station_texture("unknown"), can_shrink=True)
        img.set_size_request(96, 96)
        self.empty.append(img)
        self.empty.append(Gtk.Label(label="No base stations yet. Make sure they are plugged in, then press Scan."))
        page.append(self.flow)
        page.append(self.empty)
        return self._page_scroller(page)

    def _row(self, group, title, desc, widget, last=False):
        row = Gtk.Box(spacing=16)
        row.add_css_class("sv-row")
        if last:
            row.add_css_class("last")
        texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3, hexpand=True, valign=Gtk.Align.CENTER)
        t = Gtk.Label(label=title, xalign=0, wrap=True)
        t.add_css_class("sv-row-title")
        texts.append(t)
        if desc:
            d = Gtk.Label(label=desc, xalign=0, wrap=True)
            d.add_css_class("sv-row-desc")
            texts.append(d)
            row._desc = d
        row.append(texts)
        widget.set_valign(Gtk.Align.CENTER)
        row.append(widget)
        group.append(row)
        return row

    def _page_settings(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        page.add_css_class("sv-page")
        h = Gtk.Label(label="Settings", xalign=0)
        h.add_css_class("sv-h1")
        page.append(h)

        sec = Gtk.Label(label="STEAMVR INTEGRATION", xalign=0)
        sec.add_css_class("sv-section")
        page.append(sec)
        g = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        g.add_css_class("sv-group")
        self.pm_switch = Gtk.Switch(active=self.settings.power_management)
        self.pm_switch.connect("notify::active", self._on_pm)
        self._row(g, "Control base stations automatically",
                  "Power on the selected base stations when SteamVR starts and power them down when it exits.",
                  self.pm_switch)

        self.mode_seg = Gtk.Box(homogeneous=True, spacing=3, width_request=220)
        self.mode_seg.add_css_class("sv-seg")
        self.mode_buttons = {}
        for key, label in (("standby", "Standby"), ("sleep", "Sleep")):
            b = Gtk.Button(label=label)
            b.add_css_class(key)
            b.connect("clicked", lambda _b, k=key: self._set_mode(k))
            self.mode_seg.append(b)
            self.mode_buttons[key] = b
        self._set_mode(self.settings.power_down_mode, save=False)
        self._row(g, "When SteamVR exits",
                  "Standby stops the motor and wakes up faster. Sleep switches the station off completely. "
                  "1.0 base stations always sleep.", self.mode_seg)

        self.sim_switch = Gtk.Switch(active=self.settings.send_simultaneously)
        self.sim_switch.connect("notify::active", self._on_sim)
        self._row(g, "Send commands simultaneously",
                  "Faster with many stations, but a little less reliable over Bluetooth.", self.sim_switch, last=True)
        page.append(g)

        sec = Gtk.Label(label="BACKGROUND SERVICE", xalign=0)
        sec.add_css_class("sv-section")
        page.append(sec)
        g2 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        g2.add_css_class("sv-group")
        self.svc_switch = Gtk.Switch()
        self._svc_updating = False
        self.svc_row = self._row(g2, "Watch for SteamVR in the background",
                                 "", self.svc_switch, last=True)
        self.svc_switch.connect("notify::active", self._on_service)
        page.append(g2)
        return self._page_scroller(page)

    def _page_about(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, halign=Gtk.Align.CENTER,
                       valign=Gtk.Align.CENTER)
        page.add_css_class("sv-page")
        page.append(Gtk.Image(icon_name=APP_ID, pixel_size=128))
        t = Gtk.Label(label="OVR Lighthouse Manager")
        t.add_css_class("sv-h1")
        page.append(t)
        v = Gtk.Label(label=f"Linux port  ·  version {__version__}")
        v.add_css_class("sv-dim")
        page.append(v)
        d = Gtk.Label(label="Power management for SteamVR base stations over Bluetooth LE.\n"
                            "Based on the original Windows app by kurotu.  ·  GPLv3",
                      justify=Gtk.Justification.CENTER, margin_top=8)
        d.add_css_class("sv-dim")
        page.append(d)
        link = Gtk.Button(label="github.com/kurotu/OVR-Lighthouse-Manager", halign=Gtk.Align.CENTER, margin_top=10)
        link.add_css_class("sv-flat")
        link.connect("clicked", lambda *_: Gtk.UriLauncher.new(
            "https://github.com/kurotu/OVR-Lighthouse-Manager").launch(self, None, None))
        page.append(link)
        return page

    # ---------------- helpers
    def toast(self, msg: str, error: bool = False):
        log.info(msg)
        self.toast_lbl.set_text(msg)
        if error:
            self.toast_lbl.add_css_class("error")
        else:
            self.toast_lbl.remove_css_class("error")
        self.toast_rev.set_reveal_child(True)
        self._toast_id += 1
        tid = self._toast_id

        def hide():
            if tid == self._toast_id:
                self.toast_rev.set_reveal_child(False)
            return False

        GLib.timeout_add(3500 if not error else 6000, hide)

    def save(self):
        config.save(self.settings)

    def rebuild(self):
        while (child := self.flow.get_first_child()) is not None:
            self.flow.remove(child)
        self.cards = [StationCard(self, d) for d in self.settings.devices]
        for c in self.cards:
            self.flow.append(c)
        n = len(self.cards)
        m = len(self.settings.managed)
        self.count_lbl.set_text(f"{n} found  ·  {m} controlled with SteamVR" if n else "")
        self.flow.set_visible(n > 0)
        self.empty.set_visible(n == 0)

    def forget(self, dev):
        self.settings.devices.remove(dev)
        self.states.pop(dev.address, None)
        self.save()
        self.rebuild()
        self.toast(f"Forgot {dev.display_name}")

    def _tick(self):
        running = watcher.steamvr_running()
        self.vr_dot.set_color("#9dc112" if running else "#67707b")
        self.vr_lbl.set_text("SteamVR running" if running else "SteamVR not running")
        self._refresh_service()
        m = len(self.settings.managed)
        n = len(self.settings.devices)
        if n:
            self.count_lbl.set_text(f"{n} found  ·  {m} controlled with SteamVR")
        return True

    # ---------------- settings callbacks
    def _on_pm(self, sw, _p):
        self.settings.power_management = sw.get_active()
        self.save()

    def _set_mode(self, key, save=True):
        for k, b in self.mode_buttons.items():
            if k == key:
                b.add_css_class("active")
            else:
                b.remove_css_class("active")
        if save:
            self.settings.power_down_mode = key
            self.save()

    def _on_sim(self, sw, _p):
        self.settings.send_simultaneously = sw.get_active()
        self.save()

    def _refresh_service(self):
        self._svc_updating = True
        desc = getattr(self.svc_row, "_desc", None)
        if not service_installed():
            text = "Not installed – run install.sh"
            self.svc_switch.set_sensitive(False)
            self.svc_switch.set_active(False)
            foot, on = "Background service not installed", False
        else:
            active = service_active()
            self.svc_switch.set_sensitive(True)
            self.svc_switch.set_active(service_enabled())
            text = ("Starts at login, also in Game Mode. Currently " + ("running." if active else "stopped."))
            on = active and self.settings.power_management
            foot = "Auto control active" if on else "Auto control inactive"
        if desc is None:
            d = Gtk.Label(xalign=0, wrap=True)
            d.add_css_class("sv-row-desc")
            self.svc_row.get_first_child().append(d)
            self.svc_row._desc = desc = d
        desc.set_text(text)
        self.svc_foot.set_text(foot)
        self.svc_dot.set_color("#9dc112" if on else "#67707b")
        self._svc_updating = False

    def _on_service(self, sw, _p):
        if self._svc_updating:
            return
        res = _systemctl("enable" if sw.get_active() else "disable", "--now")
        if res.returncode != 0:
            self.toast(f"systemctl failed: {res.stderr.strip()}", True)
        self._refresh_service()

    # ---------------- actions
    def refresh_all(self):
        """Read the power state of every V2 station, one after another."""
        cards = [c for c in self.cards if c.dev.version == 2 and not c.busy]
        if not cards:
            return False
        for c in cards:
            c.set_busy(True)

        def work():
            for c in cards:
                try:
                    st = actions.status(c.dev)
                except Exception as e:  # noqa: BLE001
                    log.warning("%s: %s", c.dev.display_name, e)
                    st = "error"
                GLib.idle_add(c._state_read, st)

        threading.Thread(target=work, daemon=True).start()
        return False

    def scan(self):
        if self._scanning:
            return False
        self._scanning = True
        self.scan_btn.set_sensitive(False)
        self.scan_spin.set_visible(True)
        self.scan_spin.start()
        self.scan_lbl.set_text("Scanning…")

        def found(name, addr):
            GLib.idle_add(self._found, name, addr)

        def work():
            err = None
            try:
                ble.scan(10.0, on_found=found)
            except Exception as e:  # noqa: BLE001
                err = e
            GLib.idle_add(self._scan_done, err)

        threading.Thread(target=work, daemon=True).start()
        return False

    def _found(self, name, addr):
        known = any(d.address == addr.upper() for d in self.settings.devices)
        self.settings.upsert(name, addr)
        self.save()
        if not known:
            self.rebuild()
            self.toast(f"Found {name}")

    def _scan_done(self, err):
        self._scanning = False
        self.scan_btn.set_sensitive(True)
        self.scan_spin.stop()
        self.scan_spin.set_visible(False)
        self.scan_lbl.set_text("Scan")
        if err:
            self.toast(f"Scan failed: {err}", True)
        else:
            self.toast(f"Scan finished – {len(self.settings.devices)} base station(s)")

    def run_managed(self, on: bool):
        cards = [c for c in self.cards if c.dev.managed and not c.busy]
        if not cards:
            self.toast("No stations are controlled with SteamVR – enable the switch on a card first.", True)
            return
        mode = self.settings.power_down_mode
        fn = actions.power_on if on else (lambda d: actions.power_down(d, mode))
        by_addr = {c.dev.address: c for c in cards}
        for c in cards:
            c.set_busy(True)

        def res(d, e):
            card = by_addr[d.address]
            new = ("on" if on else ("sleep" if mode == "sleep" or d.version == 1 else "standby"))
            GLib.idle_add(card._done, new if e is None else None,
                          f"{d.display_name}: " + ("✓" if e is None else "failed"), e is not None)

        def work():
            actions.run_all([c.dev for c in cards], fn, self.settings.send_simultaneously, res)

        threading.Thread(target=work, daemon=True).start()


class App(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID)

    def do_startup(self):
        Gtk.Application.do_startup(self)
        display = Gdk.Display.get_default()
        Gtk.Settings.get_default().set_property("gtk-application-prefer-dark-theme", True)
        Gtk.IconTheme.get_for_display(display).add_search_path(str(ASSETS))
        Gtk.Window.set_default_icon_name(APP_ID)
        provider = Gtk.CssProvider()
        provider.load_from_string(CSS)
        Gtk.StyleContext.add_provider_for_display(display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def do_activate(self):
        win = self.get_active_window() or MainWindow(self)
        win.present()


def main() -> int:
    GLib.set_prgname(APP_ID)
    GLib.set_application_name("OVR Lighthouse Manager")
    return App().run([sys.argv[0]])
