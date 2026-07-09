"""Playback backends (video first; scene/web later)."""

from gnomepaper_engine.wallpaper.backends.base import BackendResult, WallpaperBackend
from gnomepaper_engine.wallpaper.backends.video import VideoBackend

__all__ = ["BackendResult", "VideoBackend", "WallpaperBackend"]
