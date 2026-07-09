"""Detect Wallpaper Engine ownership / install (required to use GnomePaper)."""

from __future__ import annotations

import logging
from pathlib import Path

from gnomepaper_engine.steam.paths import (
    WALLPAPER_ENGINE_APP_ID,
    discover_steam_installs,
    wallpaper_engine_install_dirs,
)

log = logging.getLogger(__name__)


def wallpaper_engine_manifest_paths(
    extra_library_paths: list[str] | None = None,
) -> list[Path]:
    """Return existing appmanifest_431960.acf paths."""
    found: list[Path] = []
    for install in discover_steam_installs(extra_library_paths):
        libraries = list(install.library_folders) or [install.root]
        for lib in libraries:
            for rel in (
                Path("steamapps") / f"appmanifest_{WALLPAPER_ENGINE_APP_ID}.acf",
                Path(f"appmanifest_{WALLPAPER_ENGINE_APP_ID}.acf"),
            ):
                p = lib / rel
                if p.is_file() and p not in found:
                    found.append(p)
        # Also next to steamapps under root
        p = install.root / "steamapps" / f"appmanifest_{WALLPAPER_ENGINE_APP_ID}.acf"
        if p.is_file() and p not in found:
            found.append(p)
    return found


def wallpaper_engine_owned(extra_library_paths: list[str] | None = None) -> bool:
    """
    True if Wallpaper Engine appears installed for this user.

    Uses Steam appmanifest and/or the wallpaper_engine install folder.
    Owning the app on Steam is required — we only detect a local install.
    """
    if wallpaper_engine_manifest_paths(extra_library_paths):
        return True
    for install in discover_steam_installs(extra_library_paths):
        if wallpaper_engine_install_dirs(install):
            return True
    return False


def ownership_status_message(extra_library_paths: list[str] | None = None) -> str:
    if wallpaper_engine_owned(extra_library_paths):
        return "Wallpaper Engine detected on this system."
    return (
        "Wallpaper Engine not found. Install it from Steam (you must own the app) "
        "before using GnomePaper Engine."
    )
