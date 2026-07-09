"""Discover and run Almamu/linux-wallpaperengine for scene (and optional video) support."""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path

log = logging.getLogger(__name__)

BINARY_NAMES = ("linux-wallpaperengine", "wallengine")


def project_root() -> Path:
    # gnomepaper_engine/wallpaper/backends/lwe.py → repo root
    return Path(__file__).resolve().parents[3]


def find_lwe_binary() -> Path | None:
    """Locate linux-wallpaperengine on PATH or known install locations."""
    for name in BINARY_NAMES:
        which = shutil.which(name)
        if which:
            return Path(which)

    home = Path.home()
    candidates = [
        home / ".local" / "bin" / "linux-wallpaperengine",
        home / ".local" / "share" / "linux-wallpaperengine" / "linux-wallpaperengine",
        home / "bin" / "linux-wallpaperengine",
        project_root() / "third_party" / "linux-wallpaperengine" / "build" / "output" / "linux-wallpaperengine",
        project_root() / "third_party" / "linux-wallpaperengine" / "output" / "linux-wallpaperengine",
        project_root() / "third_party" / "linux-wallpaperengine" / "build" / "linux-wallpaperengine",
    ]
    for path in candidates:
        if path.is_file() and os.access(path, os.X_OK):
            return path
    return None


def find_assets_dir(extra_steam_paths: list[str] | None = None) -> Path | None:
    """Locate Wallpaper Engine `assets` folder (required by LWE for many scenes)."""
    from gnomepaper_engine.steam.paths import (
        discover_steam_installs,
        wallpaper_engine_install_dirs,
    )

    installs = discover_steam_installs(extra_steam_paths)
    for install in installs:
        for we in wallpaper_engine_install_dirs(install):
            assets = we / "assets"
            if assets.is_dir():
                return assets
    return None


def install_hint() -> str:
    root = project_root()
    return (
        "Scene wallpapers need linux-wallpaperengine.\n"
        "Install it, then Rescan / Apply again:\n"
        f"  {root}/scripts/install_linux_wallpaperengine.sh\n"
        "Or build from https://github.com/Almamu/linux-wallpaperengine "
        "and put the binary on your PATH / ~/.local/bin"
    )
