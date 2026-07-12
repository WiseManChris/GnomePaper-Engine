#!/usr/bin/env bash
# Remove a user-local GnomePaper Engine install created by install.sh
set -euo pipefail

APP_ID="io.github.gnomepaper.Engine"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
BIN_DIR="${HOME}/.local/bin"
PREFIX="${DATA_HOME}/gnomepaper-engine"

bold() { printf '\033[1m%s\033[0m\n' "$*"; }
green(){ printf '\033[1;32m%s\033[0m\n' "$*"; }

bold "==> Uninstalling GnomePaper Engine…"

rm -f "${BIN_DIR}/gnomepaper-engine"
rm -f "${DATA_HOME}/applications/${APP_ID}.desktop"
rm -f "${CONFIG_HOME}/autostart/${APP_ID}.desktop"
rm -rf "${PREFIX}"

if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "${DATA_HOME}/applications" 2>/dev/null || true
fi

green "✓ App files removed."
echo
echo "Left in place (your data):"
echo "  ${CONFIG_HOME}/gnomepaper-engine/   # settings"
echo "  ${XDG_CACHE_HOME:-$HOME/.cache}/gnomepaper-engine/"
echo
echo "Remove those manually if you want a full wipe:"
echo "  rm -rf ${CONFIG_HOME}/gnomepaper-engine"
echo "  rm -rf ${XDG_CACHE_HOME:-$HOME/.cache}/gnomepaper-engine"
