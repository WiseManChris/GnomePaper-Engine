# GnomePaper Engine

**Wallpaper Engine for GNOME** — any GNOME-based Linux desktop.

Browse your Steam Wallpaper Engine library, search the Workshop, download wallpapers, and run them as live desktop backgrounds.

> **You must own [Wallpaper Engine](https://store.steampowered.com/app/431960/) on Steam.** This app does not bypass ownership.

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![GNOME](https://img.shields.io/badge/desktop-GNOME-purple.svg)](https://www.gnome.org/)

**Author:** [WiseManChris](https://github.com/WiseManChris)

---

## Install (recommended)

One script. Works on **Ubuntu / Debian, Fedora, Arch, openSUSE**, and other GNOME desktops.

```bash
git clone https://github.com/WiseManChris/GnomePaper-Engine.git
cd GnomePaper-Engine
./install.sh
```

Then start it:

```bash
gnomepaper-engine
```

Or open **GnomePaper Engine** from your app menu.

The installer will:

1. Install system libraries (GTK4, libadwaita, GStreamer, …) via your package manager  
2. Create a private Python environment under `~/.local/share/gnomepaper-engine/`  
3. Put `gnomepaper-engine` on your PATH (`~/.local/bin`)  
4. Register a desktop entry for the app menu  

### Uninstall

```bash
./uninstall.sh
```

---

## Before you start

| Need | Why |
|------|-----|
| **GNOME** desktop | UI is GTK4 + libadwaita |
| **Steam** | Finds workshop content |
| **Wallpaper Engine** owned & installed | Required — no ownership bypass |
| **linux-wallpaperengine** (optional) | Needed for **scene** wallpapers |

Scene support (optional):

```bash
./scripts/install_linux_wallpaperengine.sh
```

---

## Features

- Installed library with workshop **previews**
- **Workshop** search & download (SteamCMD or Subscribe)
- **Video** wallpapers (desktop surface)
- **Scene** wallpapers (via linux-wallpaperengine)
- Steam **Link** (top-left) with profile avatar — password never stored by the app
- **Settings**: background mode, launch at login, restore last wallpaper

### Settings (☰ → Settings)

| Option | Effect |
|--------|--------|
| Keep running in background | Close hides the window; wallpaper keeps playing |
| Start minimized | Launch into the background |
| Launch at login | Starts with your session |
| Restore last wallpaper | Re-applies last wallpaper on start |

```bash
gnomepaper-engine --background   # start hidden
```

---

## Workshop downloads

1. **Link Steam** (top-left) — account that owns Wallpaper Engine  
2. **Workshop** tab → search → **Download**  
3. Later downloads reuse the linked session (no password every time)  

Files land in `steamapps/workshop/content/431960/`.

---

## Manual install (advanced)

Only if you prefer not to use `./install.sh`:

```bash
# 1) System packages — pick your distro
# Debian/Ubuntu:
sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adw-1 \
  gstreamer1.0-plugins-good ffmpeg xdotool wmctrl

# Fedora:
sudo dnf install python3-gobject gtk4 libadwaita gstreamer1-plugins-good ffmpeg xdotool wmctrl

# Arch:
sudo pacman -S python-gobject gtk4 libadwaita gst-plugins-good ffmpeg xdotool wmctrl

# 2) App (user install)
python3 -m venv --system-site-packages ~/.local/share/gnomepaper-engine/venv
~/.local/share/gnomepaper-engine/venv/bin/pip install .
# then wrap/link the console script into ~/.local/bin as install.sh does
```

---

## Config

`~/.config/gnomepaper-engine/config.json`

---

## License

MIT — see [LICENSE](LICENSE).

Copyright © 2026 WiseManChris.

Wallpaper Engine is © Kristjan Skutta / Wallpaper Engine. This project is unofficial and not affiliated with Valve or Wallpaper Engine.
