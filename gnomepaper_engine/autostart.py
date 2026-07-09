"""XDG autostart (.desktop) helpers for launch-at-login."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from gnomepaper_engine import __app_id__, __app_name__
from gnomepaper_engine.config import xdg_config_home

log = logging.getLogger(__name__)

_DESKTOP_NAME = f"{__app_id__}.desktop"


def autostart_path() -> Path:
    return xdg_config_home() / "autostart" / _DESKTOP_NAME


def is_autostart_enabled() -> bool:
    return autostart_path().is_file()


def _resolve_exec() -> str:
    """Prefer installed console script, else python -m."""
    which = shutil.which("gnomepaper-engine")
    if which:
        return f"{which} --background"
    # Fallback: module launch
    return "python3 -m gnomepaper_engine --background"


def set_autostart(enabled: bool) -> None:
    path = autostart_path()
    if not enabled:
        try:
            if path.is_file():
                path.unlink()
                log.info("Removed autostart entry %s", path)
        except OSError as exc:
            log.warning("Could not remove autostart: %s", exc)
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    content = f"""[Desktop Entry]
Type=Application
Name={__app_name__}
Comment=Restore Wallpaper Engine wallpapers on GNOME
Exec={_resolve_exec()}
Icon=preferences-desktop-wallpaper
Terminal=false
Categories=Utility;GTK;GNOME;
X-GNOME-Autostart-enabled=true
StartupNotify=false
"""
    path.write_text(content, encoding="utf-8")
    log.info("Wrote autostart entry %s", path)
