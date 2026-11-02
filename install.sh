#!/usr/bin/env bash
# Installs OVR Lighthouse Manager (Linux) for the current user. No root needed.
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PREFIX="${XDG_DATA_HOME:-$HOME/.local/share}/ovr-lighthouse-manager"
BIN="$HOME/.local/bin"
APPS="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
UNITS="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
ICONS="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor"
APP_ID="io.github.kurotu.OVRLighthouseManager.Linux"

# Use the system python: it ships dbus-python and PyGObject on SteamOS.
PY=/usr/bin/python3
"$PY" -c "import dbus" || { echo "error: python dbus module missing (install python-dbus)"; exit 1; }
"$PY" -c "import gi; gi.require_version('Gtk','4.0')" 2>/dev/null || echo "warning: GTK4 for python not found, GUI won't work (CLI + service still do)"

echo "Installing to $PREFIX"
rm -rf "$PREFIX"
mkdir -p "$PREFIX" "$BIN" "$APPS" "$UNITS" "$ICONS/scalable/apps"
cp -r "$SRC/ovr_lighthouse_manager" "$PREFIX/"
cp "$SRC/LICENSE" "$PREFIX/"
find "$PREFIX" -name __pycache__ -prune -exec rm -rf {} +

cat > "$BIN/ovr-lighthouse-manager" <<EOF
#!/bin/sh
PYTHONPATH="$PREFIX\${PYTHONPATH:+:\$PYTHONPATH}" exec $PY -P -m ovr_lighthouse_manager "\$@"
EOF
chmod +x "$BIN/ovr-lighthouse-manager"

# app icon (SVG + PNG sizes for launchers that don't do SVG, e.g. some Steam views)
cp "$SRC/ovr_lighthouse_manager/assets/$APP_ID.svg" "$ICONS/scalable/apps/$APP_ID.svg"
if command -v rsvg-convert >/dev/null; then
  for s in 48 64 128 256; do
    mkdir -p "$ICONS/${s}x${s}/apps"
    rsvg-convert -w $s -h $s "$ICONS/scalable/apps/$APP_ID.svg" -o "$ICONS/${s}x${s}/apps/$APP_ID.png"
  done
fi
gtk-update-icon-cache -q -t "$ICONS" 2>/dev/null || true

rm -f "$APPS/ovr-lighthouse-manager.desktop"   # old name
cat > "$APPS/$APP_ID.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=OVR Lighthouse Manager
Comment=SteamVR base station power management
Exec=$BIN/ovr-lighthouse-manager gui
Icon=$APP_ID
StartupWMClass=$APP_ID
Terminal=false
StartupNotify=true
Categories=Utility;Game;
Keywords=SteamVR;Lighthouse;Base Station;VR;
EOF

cat > "$UNITS/ovr-lighthouse-manager.service" <<EOF
[Unit]
Description=OVR Lighthouse Manager - power base stations with SteamVR
After=bluetooth.target

[Service]
Type=simple
ExecStart=$BIN/ovr-lighthouse-manager daemon
Restart=on-failure
RestartSec=10

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable ovr-lighthouse-manager.service
systemctl --user restart ovr-lighthouse-manager.service

echo
echo "Done."
echo "  GUI:      'OVR Lighthouse Manager' in the app menu, or: ovr-lighthouse-manager gui"
echo "  CLI:      ovr-lighthouse-manager --help"
echo "  Service:  systemctl --user status ovr-lighthouse-manager"
echo "  Logs:     journalctl --user -u ovr-lighthouse-manager -f"
case ":$PATH:" in *":$BIN:"*) ;; *) echo "  note: $BIN is not in your PATH";; esac
