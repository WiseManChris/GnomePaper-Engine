"""Playback backends (video desktop surface + scene via LWE)."""

from gnomepaper_engine.wallpaper.backends.base import BackendResult, WallpaperBackend
from gnomepaper_engine.wallpaper.backends.scene import SceneBackend
from gnomepaper_engine.wallpaper.backends.video import VideoBackend

__all__ = ["BackendResult", "SceneBackend", "VideoBackend", "WallpaperBackend"]
