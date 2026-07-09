# GnomePaper Engine

**Version 1.0** — Wallpaper Engine for GNOME.

Browse your Steam Wallpaper Engine library, search the Workshop, download wallpapers, and run them as live desktop backgrounds on GNOME (Wayland/X11 via XWayland).

> **Requires owning [Wallpaper Engine](https://store.steampowered.com/app/431960/) on Steam.** GnomePaper does not bypass ownership.

![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)
![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)
![GNOME](https://img.shields.io/badge/desktop-GNOME-purple.svg)

## Features

- **Installed library** with Steam workshop previews  
- **Workshop search & download** (SteamCMD direct download or Subscribe)  
- **Video wallpapers** — full-screen desktop surface (GStreamer)  
- **Scene wallpapers** — via [linux-wallpaperengine](https://github.com/Almamu/linux-wallpaperengine)  
- **Steam account link** (top-left) with profile avatar; password never stored  
- **Settings**: keep running in background, launch at login, restore last wallpaper  
- Native **GTK4 / libadwaita** UI  

## Requirements

### System (Fedora / Nobara)

```bash
sudo dnf install python3-gobject gtk4 libadwaita gtk3 \
  gstreamer1-plugins-base gstreamer1-plugins-good gstreamer1-plugins-bad-free \
  xprop wmctrl xdotool ffmpeg \
  libayatana-appindicator-gtk3   # optional tray
```

### Steam

1. Install [Steam](https://store.steampowered.com/)  
2. Own & install **Wallpaper Engine** (AppID `431960`)  
3. (Optional) Build [linux-wallpaperengine](https://github.com/Almamu/linux-wallpaperengine) for scenes — or use:

```bash
./scripts/install_linux_wallpaperengine.sh
```

## Install & run

```bash
git clone https://github.com/christianl/GnomePaper-Engine.git
cd GnomePaper-Engine
pip install --user -e .
gnomepaper-engine
```

Or without install:

```bash
python3 -m gnomepaper_engine
```

### Background / login

```bash
gnomepaper-engine --background   # start hidden, restore last wallpaper
```

In-app: **☰ menu → Settings**

| Setting | Effect |
|---------|--------|
| Keep running in background | Close hides the window; wallpaper keeps playing |
| Start minimized | Launch into background |
| Launch at login | XDG autostart desktop entry |
| Restore last wallpaper | Re-apply last wallpaper on start |

Optional **system tray** (AppIndicator) if your GNOME session has an indicator extension.

## Workshop downloads

1. Click **Link Steam** (top-left) once — account must own Wallpaper Engine  
2. **Workshop** tab → search → **Download**  
3. SteamCMD caches login (no password every time)  
4. Files go to `steamapps/workshop/content/431960/`  

**Open Subscribe page** remains as a fallback.

## Project layout

```
gnomepaper_engine/
  app.py                 # Adw.Application, background, restore
  config.py              # XDG config
  autostart.py           # Launch-at-login
  tray.py                # Optional AppIndicator
  steam/                 # Discovery, ownership, library scan
  workshop/              # Search, SteamCMD download, profile
  wallpaper/             # Video + scene backends
  ui/                    # Main window, settings, cards
data/
  io.github.gnomepaper.Engine.desktop
scripts/
  install_linux_wallpaperengine.sh
  install_steamcmd.sh
```

## Config

`~/.config/gnomepaper-engine/config.json`

## License

MIT — see [LICENSE](LICENSE).

Wallpaper Engine is © Kristjan Skutta / Wallpaper Engine. This project is unofficial and not affiliated with Valve or Wallpaper Engine.
