# GnomePaper Engine

**Version 1.0** — Wallpaper Engine for GNOME.

Bring your Steam Wallpaper Engine collection to life on your GNOME desktop. Browse your library, explore the Workshop, download new wallpapers, and enjoy them as stunning live backgrounds on GNOME (Wayland and X11 via XWayland).

> **You'll need to own [Wallpaper Engine](https://store.steampowered.com/app/431960/) on Steam.** GnomePaper respects that ownership and doesn't bypass it.

![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)
![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)
![GNOME](https://img.shields.io/badge/desktop-GNOME-purple.svg)

## What you can do

- **Browse your library** — see all your installed wallpapers with Workshop previews  
- **Search and download** — explore the Workshop and grab new wallpapers directly  
- **Enjoy video wallpapers** — full-screen, beautifully rendered with GStreamer  
- **Use scene wallpapers** — powered by [linux-wallpaperengine](https://github.com/Almamu/linux-wallpaperengine)  
- **Link your Steam account** — one-click login (your password is never stored)  
- **Smart settings** — keep running in the background, launch at startup, and restore your last wallpaper  
- **Beautiful interface** — built with native GTK4 and libadwaita

## Getting Started

### Install Dependencies

GnomePaper Engine works with any version of GNOME, as long as you have the right dependencies installed.

**On Fedora / Nobara:**

```bash
sudo dnf install python3-gobject gtk4 libadwaita gtk3 \
  gstreamer1-plugins-base gstreamer1-plugins-good gstreamer1-plugins-bad-free \
  xprop wmctrl xdotool ffmpeg \
  libayatana-appindicator-gtk3   # optional for system tray
```

### Set Up Steam

1. Install [Steam](https://store.steampowered.com/)  
2. Own and install **Wallpaper Engine** (AppID `431960`)  
3. (Optional) Set up scene wallpapers — build [linux-wallpaperengine](https://github.com/Almamu/linux-wallpaperengine), or use our helper script:

```bash
./scripts/install_linux_wallpaperengine.sh
```

### Install and Run

```bash
git clone https://github.com/WiseManChris/GnomePaper-Engine.git
cd GnomePaper-Engine
pip install --user -e .
gnomepaper-engine
```

Or skip the installation and run directly:

```bash
python3 -m gnomepaper_engine
```

## Background and Startup

Run in the background to keep your wallpaper playing while the app is closed:

```bash
gnomepaper-engine --background
```

**Configure in the app:** Open the **☰ menu → Settings**

| Setting | What it does |
|---------|--------|
| Keep running in background | Closes the window while your wallpaper keeps playing |
| Start minimized | Launch straight into the background |
| Launch at login | Automatically start when you log in |
| Restore last wallpaper | Reapply your wallpaper on startup |

If your GNOME has an indicator extension, you'll also get a handy system tray icon.

## Finding and Installing Wallpapers

1. Click **Link Steam** in the top-left — make sure your account owns Wallpaper Engine  
2. Go to the **Workshop** tab and search for what you like  
3. Hit **Download** — SteamCMD handles the rest and remembers your login  
4. Your wallpapers go to `steamapps/workshop/content/431960/`

You can also use the **Subscribe** fallback if needed.

## How It's Built

```
gnomepaper_engine/
  app.py                 # Main app, background mode, restore
  config.py              # User settings
  autostart.py           # Startup automation
  tray.py                # System tray (optional)
  steam/                 # Steam library and ownership checks
  workshop/              # Workshop search and downloads
  wallpaper/             # Video and scene playback
  ui/                    # User interface
data/
  io.github.gnomepaper.Engine.desktop
scripts/
  install_linux_wallpaperengine.sh
  install_steamcmd.sh
```

## Configuration

Settings are saved to `~/.config/gnomepaper-engine/config.json`

## License

MIT — see [LICENSE](LICENSE).

Wallpaper Engine is © Kristjan Skutta / Wallpaper Engine. This project is unofficial and not affiliated with Valve or Wallpaper Engine.
