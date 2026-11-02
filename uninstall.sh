#!/usr/bin/env bash
# Removes OVR Lighthouse Manager (Linux). Your settings in ~/.config/ovr-lighthouse-manager are kept.
set -uo pipefail
systemctl --user disable --now ovr-lighthouse-manager.service 2>/dev/null
rm -f "${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user/ovr-lighthouse-manager.service"
systemctl --user daemon-reload
rm -f "$HOME/.local/bin/ovr-lighthouse-manager"
APP_ID="io.github.kurotu.OVRLighthouseManager.Linux"
rm -f "${XDG_DATA_HOME:-$HOME/.local/share}/applications/ovr-lighthouse-manager.desktop" \
      "${XDG_DATA_HOME:-$HOME/.local/share}/applications/$APP_ID.desktop"
find "${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor" -name "$APP_ID.*" -delete 2>/dev/null
rm -rf "${XDG_DATA_HOME:-$HOME/.local/share}/ovr-lighthouse-manager"
echo "Uninstalled. Settings kept in ${XDG_CONFIG_HOME:-$HOME/.config}/ovr-lighthouse-manager"
