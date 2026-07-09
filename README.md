# GnomePaper Engine

**Wallpaper Engine for GNOME** — browse your Steam Wallpaper Engine library and run wallpapers with a native Adwaita UI.

> Status: **pre-alpha scaffold**. Steam discovery and library UI work; desktop wallpaper integration is still a placeholder (video opens in an mpv preview window).

## Goals

- Link to Steam (native + Flatpak) and find Wallpaper Engine workshop content
- Ease of use close to the Windows Wallpaper Engine experience
- GNOME flavor: GTK4, libadwaita, desktop-friendly settings

## Requirements

### System (Fedora / Nobara)

```bash
sudo dnf install python3-gobject gtk4 libadwaita
# Optional — video wallpaper preview backend
sudo dnf install mpv
```

### Steam

1. Install [Steam](https://store.steampowered.com/)
2. Own / install **Wallpaper Engine** (AppID `431960`)
3. Subscribe to workshop wallpapers so they download under  
   `steamapps/workshop/content/431960/`

## Run from source

```bash
cd ~/Projects/GnomePaper-Engine
python3 -m gnomepaper_engine
```

Optional editable install:

```bash
pip install --user -e .
gnomepaper-engine
```

## Project layout

```
gnomepaper_engine/
  app.py                 # Adw.Application
  config.py              # XDG config (~/.config/gnomepaper-engine/)
  __main__.py
  steam/
    paths.py             # Find Steam / workshop dirs
    library.py           # Scan wallpapers
    models.py
  wallpaper/
    manager.py           # Backend orchestration
    backends/
      video.py           # mpv preview (desktop layer TBD)
  ui/
    main_window.py       # Library browser shell
data/
  io.github.gnomepaper.Engine.desktop
```

## Config

User config: `~/.config/gnomepaper-engine/config.json`

| Key | Meaning |
|-----|---------|
| `steam_library_paths` | Extra Steam library folders if auto-detect misses them |
| `mute_audio` | Mute wallpaper audio (default `true`) |
| `target_fps` | Reserved for future quality controls |
| `last_wallpaper_id` | Last applied wallpaper (restore-on-login later) |

## Roadmap (high level)

1. ~~Scaffold app + Steam library scan + UI shell~~
2. Real GNOME desktop integration (video behind desktop / multi-monitor)
3. Scene / web backends where feasible
4. Tray / autostart / per-monitor settings
5. Packaging (Flatpak)

## License

MIT (see `pyproject.toml`)
