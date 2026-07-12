# GnomePaper Engine

### Live wallpapers on GNOME. Your Steam library. Your desktop. Finally.

**Version 1.1** · by [WiseManChris](https://github.com/WiseManChris)

If you have ever stared at a beautiful Wallpaper Engine scene on Windows and thought *“why can’t GNOME feel like this?”* — this is the project for you.

GnomePaper Engine brings your **Steam Wallpaper Engine** library to **any GNOME-based Linux desktop**: browse previews, search the Workshop, download wallpapers, and run them as real live backgrounds — with an interface that feels like it belongs on your system.

> **You must own [Wallpaper Engine](https://store.steampowered.com/app/431960/) on Steam.**  
> No cracks. No ownership bypass. If you bought it, you’re welcome here.

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Version 1.1](https://img.shields.io/badge/version-1.1.0-brightgreen.svg)](https://github.com/WiseManChris/GnomePaper-Engine/releases)
[![GNOME](https://img.shields.io/badge/GNOME-any-purple.svg)](https://www.gnome.org/)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)

---

## Install in one shot

Works on **Ubuntu, Fedora, Arch, openSUSE, Pop!_OS, Zorin, elementary**, and other GNOME desktops.

```bash
git clone https://github.com/WiseManChris/GnomePaper-Engine.git
cd GnomePaper-Engine
./install.sh
gnomepaper-engine
```

That is the whole install story. The script:

1. Installs system libraries for **your** distro (apt / dnf / pacman / zypper)  
2. Sets up a clean user environment under `~/.local/share/gnomepaper-engine/`  
3. Puts `gnomepaper-engine` on your PATH  
4. Adds an app-menu entry  

```bash
./uninstall.sh    # when you want it gone
```

---

## What you need

| Requirement | Notes |
|-------------|--------|
| **GNOME** | Vanilla GNOME, or GNOME-based (libadwaita UI) |
| **Steam** | Native or Flatpak |
| **Wallpaper Engine** | Owned **and** installed on that Steam account |
| **Scene player** (optional) | `./scripts/install_linux_wallpaperengine.sh` for scene wallpapers |

---

## Features — the full tour

### Library that feels like home
- Grid of your installed workshop wallpapers with **real previews** (jpg/gif)  
- Search and filters: All · Video · Scene · Web  
- Detail pane with preview, metadata, tags  
- One-click **Apply** / **Stop**  

### Workshop without the Windows detour
- Search trending, popular, recent, or any query  
- **Three-column** browse grid for faster scrolling  
- **Direct download** via SteamCMD (no Subscribe click when linked)  
- Or open Steam’s Subscribe page as a fallback  
- Downloads land in the normal Steam workshop folder  

### Live wallpapers on the real desktop
- **Video** wallpapers: full-screen desktop surface (GStreamer), not a floating player  
- **Scene** wallpapers: powered by [linux-wallpaperengine](https://github.com/Almamu/linux-wallpaperengine)  
- Surfaces respect the **GNOME top bar** (clock & control center stay visible)  
- Audio, volume, FPS, mouse-effect toggles  

### Steam, linked like a native app
- **Link Steam** chip in the **top-left** of the window  
- After linking: **profile avatar + display name**  
- Password lives in your **GNOME Keyring** (not in a config file)  
- Sessions auto-renew so you are not re-linking every twenty minutes  

### Session & settings
- Keep running in the **background** when you close the window  
- **Launch at login**  
- **Restore last wallpaper** on start  
- `gnomepaper-engine --background` for silent start  

Open **☰ → Settings** anytime.

---

## Quick start after install

1. Own & install Wallpaper Engine on Steam  
2. Run `gnomepaper-engine`  
3. Click **Link Steam** (top-left) once — account that owns WE  
4. Browse **Installed** or **Workshop**  
5. **Apply** a wallpaper and enjoy  

For **scenes**:

```bash
./scripts/install_linux_wallpaperengine.sh
```

---

## How it works (for the curious)

| Piece | Role |
|-------|------|
| **GTK4 + libadwaita** | Native GNOME UI |
| **Steam paths** | Finds `steamapps/workshop/content/431960` (native & Flatpak) |
| **SteamCMD** | Direct workshop downloads for accounts that own WE |
| **GNOME Keyring** | Secure password storage for silent session renew |
| **GStreamer** | Video desktop surfaces |
| **linux-wallpaperengine** | Scene rendering |
| **X11 workarea** | Keeps wallpapers below the GNOME shell panel |

---

## Project layout

```
install.sh / uninstall.sh     ← one-command install for any GNOME distro
gnomepaper_engine/
  app.py · config.py · autostart.py · tray.py
  steam/       # discovery, ownership, library
  workshop/    # search, SteamCMD, keyring, profile
  wallpaper/   # video + scene backends (panel-safe geometry)
  ui/          # main window, settings, cards
scripts/
  install_linux_wallpaperengine.sh
  install_steamcmd.sh
```

---

## Changelog

### 1.1.0
- Permanent Steam link via **GNOME Keyring** (no re-auth every ~20 minutes)  
- Profile **avatar + persona name** on the top-left chip  
- Workshop grid defaults to **3 columns**  
- Scene/video surfaces use **workarea** so the GNOME top bar never disappears  
- Clearer multi-distro install story  

### 1.0.0
- First public release  

---

## License

MIT — see [LICENSE](LICENSE).

Copyright © 2026 **WiseManChris**.

Wallpaper Engine is © Kristjan Skutta / Wallpaper Engine.  
This project is **unofficial** and not affiliated with Valve or Wallpaper Engine.

---

Built with care for people who live on GNOME and refuse to give up their wallpapers.
EOF
