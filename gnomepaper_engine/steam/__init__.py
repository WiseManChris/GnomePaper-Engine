"""Steam / Wallpaper Engine discovery and library scanning."""

from gnomepaper_engine.steam.library import WallpaperLibrary, scan_library
from gnomepaper_engine.steam.models import SteamInstall, WallpaperItem, WallpaperType
from gnomepaper_engine.steam.paths import discover_steam_installs, wallpaper_engine_app_id

__all__ = [
    "SteamInstall",
    "WallpaperItem",
    "WallpaperLibrary",
    "WallpaperType",
    "discover_steam_installs",
    "scan_library",
    "wallpaper_engine_app_id",
]
