#!/usr/bin/env bash
# Install Valve SteamCMD into ~/.local/share/gnomepaper-engine/steamcmd
set -euo pipefail
DEST="${XDG_DATA_HOME:-$HOME/.local/share}/gnomepaper-engine/steamcmd"
mkdir -p "$DEST"
cd "$DEST"
if [[ ! -x ./steamcmd.sh ]]; then
  echo "==> Downloading SteamCMD…"
  curl -fL "https://steamcdn-a.akamaihd.net/client/installer/steamcmd_linux.tar.gz" -o steamcmd_linux.tar.gz
  tar -xzf steamcmd_linux.tar.gz
  rm -f steamcmd_linux.tar.gz
fi
echo "==> First-run update…"
./steamcmd.sh +quit || true
echo "==> SteamCMD ready at $DEST/steamcmd.sh"
