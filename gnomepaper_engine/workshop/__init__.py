"""Steam Workshop search and install helpers for Wallpaper Engine."""

from gnomepaper_engine.workshop.client import (
    SteamCmdResult,
    WorkshopItem,
    download_via_steamcmd,
    ensure_steamcmd,
    is_installed,
    link_steam_account,
    open_install,
    reset_steamcmd_session,
    search_workshop,
    steamcmd_binary,
    wait_for_install,
)

__all__ = [
    "SteamCmdResult",
    "WorkshopItem",
    "download_via_steamcmd",
    "ensure_steamcmd",
    "is_installed",
    "link_steam_account",
    "open_install",
    "reset_steamcmd_session",
    "search_workshop",
    "steamcmd_binary",
    "wait_for_install",
]
