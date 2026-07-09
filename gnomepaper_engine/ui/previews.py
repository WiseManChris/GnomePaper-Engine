"""Load and cache wallpaper preview textures for the library grid."""

from __future__ import annotations

import logging
from pathlib import Path

import gi

gi.require_version("Gdk", "4.0")
gi.require_version("GdkPixbuf", "2.0")

from gi.repository import Gdk, GdkPixbuf  # noqa: E402

log = logging.getLogger(__name__)

# Grid cell target size (CSS-ish; scaled by loaders)
THUMB_W = 280
THUMB_H = 158
# Right-pane detail preview — compact so settings stay reachable
DETAIL_W = 300
DETAIL_H = 168


class PreviewCache:
    """In-memory cache of Gdk.Texture previews keyed by path + size."""

    def __init__(self) -> None:
        self._cache: dict[tuple[str, int, int], Gdk.Texture | None] = {}

    def get(
        self,
        path: Path | None,
        *,
        width: int = THUMB_W,
        height: int = THUMB_H,
    ) -> Gdk.Texture | None:
        if path is None or not path.is_file():
            return None
        key = (str(path.resolve()), width, height)
        if key in self._cache:
            return self._cache[key]
        texture = self._load(path, width, height)
        self._cache[key] = texture
        return texture

    def _load(self, path: Path, width: int, height: int) -> Gdk.Texture | None:
        try:
            # GIFs: Pixbuf loads first frame — good enough for library thumbs
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                str(path),
                width,
                height,
                True,  # preserve aspect
            )
            if pixbuf is None:
                return None
            return Gdk.Texture.new_for_pixbuf(pixbuf)
        except Exception as exc:
            log.debug("Preview load failed for %s: %s", path, exc)
            return None

    def clear(self) -> None:
        self._cache.clear()
