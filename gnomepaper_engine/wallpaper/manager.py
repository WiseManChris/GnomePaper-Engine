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

    def set_audio(self, *, volume: int | None = None, muted: bool | None = None) -> None:
        """
        Apply live volume/mute to the running wallpaper (no re-apply needed).

        Updates config and pushes to the active backend (Pulse + player file).
        """
        if volume is not None:
            self.config.audio_volume = max(0, min(100, int(volume)))
        if muted is not None:
            self.config.mute_audio = bool(muted)
        self.config.save()

        vol = self.config.audio_volume
        mut = self.config.mute_audio
        active = self._active
        if active is None or not active.is_running:
            return
        setter = getattr(active, "set_audio", None)
        if callable(setter):
            try:
                setter(volume=vol, muted=mut)
            except Exception as exc:
                log.warning("Live audio update failed: %s", exc)

    def _backend_for(self, item: WallpaperItem) -> WallpaperBackend | None:
        for backend in self._backends:
            if backend.supports(item):
                return backend
        return None
