# 🐧 GnomePaper Engine

**Version 1.0** — Your Steam Wallpaper Engine collection, brought to GNOME.

Hey everyone! 👋 I built GnomePaper Engine because I really wanted a seamless way to use my Steam Wallpaper Engine collection right on my GNOME desktop. This app lets you browse your Steam library, search the Workshop, download new wallpapers, and run them as awesome live backgrounds. It works flawlessly whether you're using Wayland or X11 (via XWayland).

> **Just a quick heads-up:** You absolutely **need to own [Wallpaper Engine](https://store.steampowered.com/app/431960/) on Steam** for this to work. I wanted to respect the original developers, so this app does not bypass Steam ownership checks.

![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)
![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)
![GNOME](https://img.shields.io/badge/desktop-GNOME-purple.svg)

## ✨ What makes it cool

- **Browse your collection:** See all the wallpapers you've already installed, complete with Workshop preview images.
- **Find new favorites:** Search the Workshop and download new wallpapers straight from the app.
- **Video & Scene Wallpapers:** Play video backgrounds smoothly (using GStreamer), and run full interactive scene wallpapers (powered by [linux-wallpaperengine](https://github.com/Almamu/linux-wallpaperengine)).
- **Easy Steam Login:** Link your account with one click. And don't worry—your password is never stored or seen by the app.
- **Set it and forget it:** You can set it to run silently in the background, launch automatically when you log in, and remember your last used wallpaper.
- **Looks right at home:** Built from the ground up with native GTK4 and libadwaita so it matches your beautiful GNOME desktop perfectly.

---

## 🚀 Getting Started

GnomePaper Engine works on practically any GNOME setup, provided your system has a few under-the-hood tools installed to handle the video and window management.

### 1. Install the required tools

**For Fedora / Nobara users:**
```bash
sudo dnf install python3-gobject gtk4 libadwaita gtk3 \
  gstreamer1-plugins-base gstreamer1-plugins-good gstreamer1-plugins-bad-free \
  xprop wmctrl xdotool ffmpeg \
  libayatana-appindicator-gtk3   # optional (gives you a system tray icon)
```

**For Ubuntu / Debian-based distros:**
```bash
sudo apt update && sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 \
  gstreamer1.0-plugins-base gstreamer1.0-plugins-good gstreamer1.0-plugins-bad \
  x11-utils wmctrl xdotool ffmpeg \
  gir1.2-ayatanaappindicator3-0.1   # optional (gives you a system tray icon)
```

**For Arch Linux users:**
```bash
sudo pacman -S python-gobject gtk4 libadwaita gtk3 \
  gst-plugins-base gst-plugins-good gst-plugins-bad \
  xorg-xprop wmctrl xdotool ffmpeg \
  libayatana-appindicator           # optional (gives you a system tray icon)
```

### 2. Set Up Steam

1. Make sure you have the regular Linux [Steam](https://store.steampowered.com/) client installed.
2. Make sure you actually own and install **Wallpaper Engine** (AppID `431960`) through Steam.
3. *(Optional but highly recommended)* If you want to use the complex "scene" wallpapers, you can run my included helper script to set that up automatically:

```bash
./scripts/install_linux_wallpaperengine.sh
```

### 3. Install and Run!

Just clone the code and install it locally using pip:

```bash
git clone https://github.com/WiseManChris/GnomePaper-Engine.git
cd GnomePaper-Engine
pip install --user -e .
gnomepaper-engine
```

If you just want to test it out without officially installing it, you can run it directly from the folder:

```bash
python3 -m gnomepaper_engine
```

---

## ⚙️ Background Mode & Startup

Want your wallpaper to keep playing while the app window is closed? Just run it in background mode:

```bash
gnomepaper-engine --background
```

You can easily tweak how the app behaves by opening the **☰ menu → Settings** inside the app:

| Setting | What it does |
|---------|--------|
| **Keep running in background** | Closes the main window, but your wallpaper keeps playing seamlessly. |
| **Start minimized** | Launches straight to the background without popping up a window. |
| **Launch at login** | Automatically fires up the app as soon as you boot your PC. |
| **Restore last wallpaper** | Remembers what you were using last and reapplies it on startup. |

*Tip: If you use an AppIndicator extension on GNOME, you'll also get a neat little system tray icon to control things quickly.*

---

## 🖼️ Finding and Installing Wallpapers

1. Click **Link Steam** in the top-left of the app.
2. Jump over to the **Workshop** tab and search for whatever fits your current vibe.
3. Hit **Download**. The app uses SteamCMD to handle the heavy lifting and will remember your login for next time.
4. Your new wallpapers are safely downloaded to your default Steam folder at `steamapps/workshop/content/431960/`.

*If the native download acts up for any reason, you can always use the **Subscribe** fallback button.*

---

## 🏗️ How It's Built

Curious about how I put this together? For the fellow developers out there, here is a quick look at how the project is organized:

```text
gnomepaper_engine/
  app.py                 # The main app, background mode, and restore logic
  config.py              # Handles saving your user settings
  autostart.py           # The magic that makes it launch at login
  tray.py                # System tray icon stuff (optional)
  steam/                 # Talks to Steam to check your library and ownership
  workshop/              # Handles Workshop searches and downloads
  wallpaper/             # The engine for video and scene playback
  ui/                    # All the GTK4 user interface code
data/
  io.github.gnomepaper.Engine.desktop
scripts/
  install_linux_wallpaperengine.sh
  install_steamcmd.sh
```

**Where are my settings?**
Everything you change in the app is safely saved to a simple JSON file right here: `~/.config/gnomepaper-engine/config.json`

---

## 📝 License & Disclaimer

Released under the MIT License — see the [LICENSE](LICENSE) file for the legal stuff.

*Wallpaper Engine is © Kristjan Skutta / Wallpaper Engine. This project is entirely unofficial, made by a fan for the Linux community, and is not affiliated with Valve or Wallpaper Engine in any way.*

