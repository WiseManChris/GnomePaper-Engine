"""Select backends and apply/stop wallpapers."""

from __future__ import annotations

import logging

from gnomepaper_engine.config import AppConfig
from gnomepaper_engine.steam.models import WallpaperItem
from gnomepaper_engine.wallpaper.backends.base import BackendResult, WallpaperBackend
from gnomepaper_engine.wallpaper.backends.scene import SceneBackend
from gnomepaper_engine.wallpaper.backends.video import VideoBackend

log = logging.getLogger(__name__)


class WallpaperManager:
    """Facade over pluggable backends."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        # More specific backends first
        self._backends: list[WallpaperBackend] = [
            SceneBackend(),
            VideoBackend(),
        ]
        self._active: WallpaperBackend | None = None
        self._active_item: WallpaperItem | None = None

    @property
    def active_item(self) -> WallpaperItem | None:
        return self._active_item

    @property
    def is_running(self) -> bool:
        return self._active is not None and self._active.is_running

    def apply(self, item: WallpaperItem) -> BackendResult:
        backend = self._backend_for(item)
        if backend is None:
            return BackendResult(
                False,
                f"No backend for type “{item.type_label}” yet "
                "(video and scene are supported).",
            )

        self.stop()
        result = backend.apply(item, self.config)
        if result.ok:
            self._active = backend
            self._active_item = item
            self.config.last_wallpaper_id = item.id
            self.config.save()
        else:
            # Still remember selection if a static preview was applied
            self.config.last_wallpaper_id = item.id
            self.config.save()
        return result

    def stop(self) -> None:
        if self._active is not None:
            self._active.stop()
        for backend in self._backends:
            if backend is not self._active:
                backend.stop()
        self._active = None
        self._active_item = None

    def _backend_for(self, item: WallpaperItem) -> WallpaperBackend | None:
        for backend in self._backends:
            if backend.supports(item):
                return backend
        return None
