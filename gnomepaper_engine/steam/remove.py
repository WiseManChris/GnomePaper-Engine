"""Safely remove installed workshop wallpapers from disk."""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from pathlib import Path

from gnomepaper_engine.steam.models import WallpaperItem

log = logging.getLogger(__name__)

_APP_ID = "431960"


@dataclass
class RemoveResult:
    ok: bool
    message: str


def is_safe_workshop_path(path: Path) -> bool:
    """
    Only allow deletion under steamapps/workshop/content/431960/<id>.

    Prevents wiping unrelated folders if metadata is wrong.
    """
    try:
        resolved = path.resolve()
    except OSError:
        return False
    if not resolved.is_dir():
        return False
    parts = resolved.parts
    try:
        w = parts.index("workshop")
        c = parts.index("content", w)
        app = parts.index(_APP_ID, c)
    except ValueError:
        return False
    # .../workshop/content/431960/<folder>
    if app + 1 >= len(parts):
        return False
    # folder name should look like a workshop id (digits) or at least be one segment
    folder = parts[app + 1]
    if not folder or folder in (".", ".."):
        return False
    # Must not be the 431960 root itself
    if resolved.name == _APP_ID and (len(parts) <= app + 1):
        return False
    return True


def remove_wallpaper(item: WallpaperItem) -> RemoveResult:
    """
    Delete a wallpaper package from the local Steam workshop folder.

    Does not unsubscribe on Steam — only removes local files. Steam may
    re-download if still subscribed and you open Steam Workshop later.
    """
    path = item.path
    if not is_safe_workshop_path(path):
        return RemoveResult(
            False,
            f"Refusing to remove “{item.title}”: path is not a safe workshop folder.",
        )
    try:
        shutil.rmtree(path)
    except OSError as exc:
        log.exception("Failed to remove wallpaper %s", path)
        return RemoveResult(False, f"Could not remove “{item.title}”: {exc}")
    log.info("Removed wallpaper %s at %s", item.id, path)
    return RemoveResult(True, f"Removed “{item.title}” from your library.")
