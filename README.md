# GnomePaper Engine

### Live wallpapers on GNOME. Your Steam library. Your desktop. Finally.

**Version 1.1.3** · by [WiseManChris](https://github.com/WiseManChris)

If you have ever stared at a beautiful Wallpaper Engine scene on Windows and thought *“why can’t GNOME feel like this?”* — this is the project for you.

GnomePaper Engine brings your **Steam Wallpaper Engine** library to **any GNOME-based Linux desktop**: browse previews, search the Workshop, download wallpapers, and run them as real live backgrounds — with an interface that feels like it belongs on your system.

> **You must own [Wallpaper Engine](https://store.steampowered.com/app/431960/) on Steam.**  
> No cracks. No ownership bypass. If you bought it, you’re welcome here.

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Version 1.1.3](https://img.shields.io/badge/version-1.1.3-brightgreen.svg)](https://github.com/WiseManChris/GnomePaper-Engine/releases)
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

That is the whole app install story. The script:

1. Installs system libraries for **your** distro (apt / dnf / pacman / zypper)  
2. Sets up a clean user environment under `~/.local/share/gnomepaper-engine/`  
3. Puts `gnomepaper-engine` on your PATH  
4. Adds an app-menu entry  
5. Remembers the source path so **Settings → Install scene engine** can find the LWE build script  

For **live scene** wallpapers, do one more step after first launch:  
**☰ → Settings → Scene engine → Install scene engine**  
(see [Scene engine](#scene-engine-linux-wallpaperengine) below).

```bash
./uninstall.sh    # when you want it gone
```

---

## Manual install (no scripts)

Prefer to install everything yourself? Same result — no `install.sh` required.

### 1. System packages

Pick your distro. You need **Python 3.11+**, **PyGObject**, **GTK4**, **libadwaita**, **GStreamer**, plus helpers for wallpaper surfaces (`xprop`, `wmctrl`, `xdotool`) and downloads (`ffmpeg`, `curl`).

**Debian / Ubuntu / Pop!_OS / Zorin / elementary**

```bash
sudo apt update
sudo apt install -y \
  python3 python3-pip python3-venv python3-gi python3-gi-cairo \
  gir1.2-gtk-4.0 gir1.2-adw-1 gir1.2-gtk-3.0 \
  libgtk-4-1 libadwaita-1-0 \
  gstreamer1.0-plugins-base gstreamer1.0-plugins-good \
  gstreamer1.0-plugins-bad gstreamer1.0-libav \
  x11-utils wmctrl xdotool ffmpeg curl tar \
  libsecret-tools gir1.2-ayatanaappindicator3-0.1
```

**Fedora / Nobara / RHEL-like**

```bash
sudo dnf install -y \
  python3 python3-pip python3-gobject \
  gtk4 libadwaita gtk3 \
  gstreamer1-plugins-base gstreamer1-plugins-good \
  gstreamer1-plugins-bad-free \
  xprop wmctrl xdotool ffmpeg curl tar \
  libsecret libayatana-appindicator-gtk3
```

**Arch / Endeavour / Manjaro**

```bash
sudo pacman -S --needed \
  python python-pip python-gobject \
  gtk4 libadwaita gtk3 \
  gst-plugins-base gst-plugins-good gst-plugins-bad \
  xorg-xprop wmctrl xdotool ffmpeg curl tar \
  libsecret libayatana-appindicator
```

**openSUSE**

```bash
sudo zypper install \
  python3 python3-pip python3-gobject \
  gtk4 libadwaita-1-0 typelib-1_0-Gtk-4_0 typelib-1_0-Adw-1 \
  gstreamer-plugins-base gstreamer-plugins-good \
  xprop wmctrl xdotool ffmpeg curl tar libsecret-tools
```

### 2. Install the app (user-local)

GTK bindings come from the system packages above — use a venv with **`--system-site-packages`** so Python can import them.

```bash
git clone https://github.com/WiseManChris/GnomePaper-Engine.git
cd GnomePaper-Engine

python3 -m venv --system-site-packages ~/.local/share/gnomepaper-engine/venv
source ~/.local/share/gnomepaper-engine/venv/bin/activate
pip install --upgrade pip setuptools wheel
pip install .

# Launcher on PATH
mkdir -p ~/.local/bin
cat > ~/.local/bin/gnomepaper-engine <<'EOF'
#!/usr/bin/env bash
exec "$HOME/.local/share/gnomepaper-engine/venv/bin/gnomepaper-engine" "$@"
EOF
chmod +x ~/.local/bin/gnomepaper-engine
```

Ensure `~/.local/bin` is on your `PATH` (log out/in or add it in your shell config), then run:

```bash
gnomepaper-engine
```

Optional app menu entry:

```bash
mkdir -p ~/.local/share/applications
cp data/io.github.gnomepaper.Engine.desktop ~/.local/share/applications/
# Point Exec at your launcher if needed:
#   sed -i "s|^Exec=.*|Exec=$HOME/.local/bin/gnomepaper-engine|" \
#     ~/.local/share/applications/io.github.gnomepaper.Engine.desktop
update-desktop-database ~/.local/share/applications 2>/dev/null || true
```

### Manual uninstall

```bash
rm -f ~/.local/bin/gnomepaper-engine
rm -rf ~/.local/share/gnomepaper-engine
rm -f ~/.local/share/applications/io.github.gnomepaper.Engine.desktop
# optional config/cache:
# rm -rf ~/.config/gnomepaper-engine ~/.cache/gnomepaper-engine
```

---

## Scene engine (linux-wallpaperengine)

**Video** wallpapers work out of the box. **Scene** wallpapers need Almamu’s [linux-wallpaperengine](https://github.com/Almamu/linux-wallpaperengine) CLI — that is **not** the Steam “Wallpaper Engine” app by itself.

### Install from Settings (recommended)

After GnomePaper is installed:

1. Open **☰ → Settings**
2. Scroll to **Scene engine**
3. Click **Install scene engine**

That opens a terminal running the built-in installer (`scripts/install_linux_wallpaperengine.sh`). Approve any **sudo** prompts for build dependencies, wait for the compile (it can take several minutes), then either:

- Wait — GnomePaper **polls and auto-detects** when the binary appears, or  
- Click **Re-detect** when the terminal says it’s done  

The installer installs to:

| Path | Role |
|------|------|
| `~/.local/share/linux-wallpaperengine/` | Binary + runtime files |
| `~/.local/bin/linux-wallpaperengine` | Symlink on your PATH |
| `…/linux-wallpaperengine.sha256` | Side-car checksum written by the installer |

### Auto-detect & checksum

GnomePaper does not only look for a filename. It:

1. Scans **PATH**, `~/.local/bin`, `~/.local/share/linux-wallpaperengine`, common system paths, and a local repo build tree  
2. Computes a **SHA-256** of the binary  
3. Runs a quick **CLI identity probe** (`--help` markers) so a random file with the same name is rejected  
4. Caches the last good **path + checksum** in config for faster, reliable re-checks  

Settings shows status like:

- **Found & verified** · path · `sha256:649866e96fda…`  
- **Not found** — use **Install scene engine** or set a custom path  

**Re-detect** forces a full rescan (ignores a stale cache).  
**Custom binary path** lets you point at a hand-built binary; if that path breaks, GnomePaper falls back to auto-detect.

### Install from a terminal

If you prefer the shell (or Settings can’t find the script):

```bash
cd GnomePaper-Engine   # your clone
./scripts/install_linux_wallpaperengine.sh
```

What the script does:

1. Installs **build dependencies** for your distro (apt / dnf / pacman / zypper)  
2. Clones or updates [Almamu/linux-wallpaperengine](https://github.com/Almamu/linux-wallpaperengine) under `third_party/`  
3. Configures **CMake** (Release) and builds  
4. Installs the output into `~/.local/share/linux-wallpaperengine/` and links `~/.local/bin/linux-wallpaperengine`  
5. Prints the **SHA-256** and writes `linux-wallpaperengine.sha256` next to the binary  

Then open GnomePaper → **Settings → Scene engine → Re-detect** (or apply a scene and it will detect on its own).

### Already built it yourself?

Put the binary somewhere GnomePaper looks:

- `~/.local/bin/linux-wallpaperengine`  
- `~/.local/share/linux-wallpaperengine/linux-wallpaperengine`  
- anywhere on your `PATH`  
- or set **Custom binary path** in Settings  

Then **Re-detect**.

---

## What you need

| Requirement | Notes |
|-------------|--------|
| **GNOME** | Vanilla GNOME, or GNOME-based (libadwaita UI) |
| **Steam** | Native or Flatpak |
| **Wallpaper Engine** | Owned **and** installed on that Steam account |
| **Scene player** (optional) | **Settings → Install scene engine**, or `./scripts/install_linux_wallpaperengine.sh` |

---

## Features — the full tour

### Library that feels like home
- Grid of your installed workshop wallpapers with **real previews** (jpg/gif)  
- Search and filters: All · Video · Scene · Web  
- Detail pane with preview, metadata, tags  
- One-click **Apply** / **Stop** / **Remove** (delete local workshop files)  

### Workshop without the Windows detour
- Search trending, popular, recent, or any query  
- **Three-column** browse grid for faster scrolling  
- **Direct download** via SteamCMD + GNOME Keyring (password once)  
- Or open Steam’s Subscribe page as a fallback  
- Downloads land in the normal Steam workshop folder  

### Live wallpapers on the real desktop
- **Video** wallpapers: full-screen desktop surface (GStreamer), not a floating player  
- **Scene** wallpapers: powered by [linux-wallpaperengine](https://github.com/Almamu/linux-wallpaperengine)  
- Surfaces stay in the **workarea** — GNOME top bar (clock & control center) stays visible  
- Audio, volume, FPS, mouse-effect toggles  

### Scene engine installer (built into the app)
- **Settings → Scene engine → Install scene engine** — one-click path for new users  
- **Re-detect** after a manual or terminal install  
- **SHA-256 checksum** + CLI identity verification  
- Cached detection so the app doesn’t “lose” a working binary between launches  
- Optional **custom binary path** when you install LWE yourself  
- Terminal installer script still available: `./scripts/install_linux_wallpaperengine.sh`  
- Installer **hard-requires** freeglut (**GLUT**), **MPV/libmpv**, and **FFmpeg** (the three deps that most often break CMake on Nobara/Fedora)  

### Workshop downloads (seamless)
- **Link Steam with QR** (top-left) — scan with **Steam Mobile → Steam Guard → Scan QR** (no password)  
- GnomePaper stores Steam **access/refresh tokens** privately  
- Click **Download** — files go straight into your workshop folder  
- **No password typing**, no Subscribe click, no SteamCMD for the normal path  
- Password link remains as a fallback; SteamCMD is optional in Settings only  

Also fix the typo PressURE if any...

### Steam, linked like a native app
- **Link Steam** chip in the **top-left** of the window  
- After linking: **profile avatar + display name**  
- Password in **GNOME Keyring** — auto sign-in for downloads (no 20‑minute re-link loop)  
- Simple **Steam Guard code** dialog when Steam asks  

### Session & settings
- Keep running in the **background** when you close the window  
- **Launch at login**  
- **Restore last wallpaper** on start  
- **Appearance**: System / Light / Dark / Pitch black (OLED)  
- **Accent colors**: Blue · Teal · Purple · Orange  
- **Scene engine** group: status, install, re-detect, custom path  
- `gnomepaper-engine --background` for silent start  

Open **☰ → Settings** anytime.

---

## Quick start after install

1. Own & install Wallpaper Engine on Steam  
2. Run `gnomepaper-engine`  
3. Click **Link Steam** (top-left) once — account that owns WE  
4. For **scene** wallpapers: **☰ → Settings → Scene engine → Install scene engine** (one time)  
5. Browse **Installed** or **Workshop**  
6. **Apply** a wallpaper and enjoy  

Terminal alternative for step 4:

```bash
./scripts/install_linux_wallpaperengine.sh
```

Then **Re-detect** in Settings if the status still says not found.

---

## How it works (for the curious)

| Piece | Role |
|-------|------|
| **GTK4 + libadwaita** | Native GNOME UI |
| **Steam paths** | Finds `steamapps/workshop/content/431960` (native & Flatpak) |
| **SteamCMD + Keyring** | Direct workshop downloads for accounts that own WE |
| **GStreamer** | Video desktop surfaces |
| **linux-wallpaperengine** | Scene rendering (Almamu CLI) |
| **Scene engine detect** | PATH / known paths + SHA-256 + CLI identity; config cache |
| **In-app installer** | Settings launches `scripts/install_linux_wallpaperengine.sh` in a terminal |
| **X11 workarea + below** | Wallpapers under apps, never covering the shell panel |

---

## Changelog

### 1.1.3
- **Settings → Scene engine**: status, **Re-detect**, and **Install scene engine**  
- **Auto-detect** linux-wallpaperengine across PATH and known install locations  
- **SHA-256 checksum** cache so detection stays reliable between launches  
- **CLI identity probe** so a random binary with the same name is rejected  
- **Custom binary path** with fallback to full auto-detect if the path is broken  
- Installer writes **`linux-wallpaperengine.sha256`** and prints the checksum  
- In-app install opens a terminal (so sudo prompts work) and polls until the binary is found  

### 1.1.2
- **Remove wallpapers** from your installed library (local workshop folder, with confirm)  
- **Appearance settings**: System / Light / Dark / Pitch black OLED  
- **Accent color**: Blue, Teal, Purple, or Orange  
- Earlier focus/volume/panel fixes remain on `main`  

### 1.1.1 — apology release
We are sorry. **1.1.0** shipped two painful bugs:

1. **Scenes hid the GNOME top bar** (clock / control center). Fixed by abandoning desktop/fullscreen window types and locking geometry to the **workarea**, re-asserted every second.  
2. **Steam link felt worse** — SteamCMD “cached login” fought the desktop client and Guard. Fixed by isolating SteamCMD’s home, **always signing in with your GNOME Keyring password**, and a **Guard-only** dialog when Steam wants a code.

**After updating, click Link Steam once** so the keyring is filled. Downloads should stay automatic after that.

### 1.1.0
- Steam link + keyring foundation, profile chip, 3-column workshop, first workarea pass  
- [Release notes](https://github.com/WiseManChris/GnomePaper-Engine/releases/tag/v1.1.0)

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
