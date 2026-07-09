"""Video wallpaper backend (mpv-based; desktop layer TBD)."""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

from gnomepaper_engine.config import AppConfig
from gnomepaper_engine.steam.models import WallpaperItem, WallpaperType
from gnomepaper_engine.wallpaper.backends.base import BackendResult, WallpaperBackend

log = logging.getLogger(__name__)

_VIDEO_EXTS = {".mp4", ".webm", ".mkv", ".avi", ".mov"}


class VideoBackend(WallpaperBackend):
    """
    Scaffold backend: finds the video file and (when mpv is present) can
    launch a looped windowed player for development.

    Full GNOME desktop integration (draw behind icons / set as background)
    will replace the placeholder launch path.
    """

    name = "video"

    def __init__(self) -> None:
        self._proc: subprocess.Popen[str] | None = None

    def supports(self, item: WallpaperItem) -> bool:
        if item.wallpaper_type == WallpaperType.VIDEO:
            return True
        return self._find_video(item.path) is not None

    def _find_video(self, folder: Path) -> Path | None:
        if not folder.is_dir():
            return None
        candidates: list[Path] = []
        for path in folder.rglob("*"):
            if path.is_file() and path.suffix.lower() in _VIDEO_EXTS:
                candidates.append(path)
        if not candidates:
            return None
        # Prefer common Wallpaper Engine names
        preferred = ("video.mp4", "video.webm", "mp4", "webm")
        for name in preferred:
            for c in candidates:
                if c.name.lower() == name or c.stem.lower() == name:
                    return c
        return sorted(candidates, key=lambda p: p.stat().st_size, reverse=True)[0]

    def apply(self, item: WallpaperItem, config: AppConfig) -> BackendResult:
        video = self._find_video(item.path)
        if video is None:
            return BackendResult(False, "No video file found in wallpaper package")

        mpv = shutil.which("mpv")
        if mpv is None:
            return BackendResult(
                False,
                f"Found video ({video.name}) but mpv is not installed. "
                "Install with: sudo dnf install mpv",
            )

        self.stop()
        # Placeholder: looped borderless window. Desktop-as-wallpaper comes next.
        cmd = [
            mpv,
            "--loop-file=inf",
            "--no-border",
            "--force-window=yes",
            f"--volume={0 if config.mute_audio else 50}",
            f"--autofit=80%",
            str(video),
        ]
        log.info("Starting video backend: %s", " ".join(cmd))
        try:
            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
            )
        except OSError as exc:
            return BackendResult(False, f"Failed to start mpv: {exc}")

        return BackendResult(
            True,
            f"Playing {video.name} in a preview window (desktop integration pending)",
        )

    def stop(self) -> None:
        if self._proc is None:
            return
        if self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        self._proc = None

    @property
    def is_running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None
