"""Video wallpaper backend — real desktop surface (not a media-player window)."""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

from gnomepaper_engine.config import AppConfig
from gnomepaper_engine.steam.models import WallpaperItem, WallpaperType
from gnomepaper_engine.wallpaper.backends.base import BackendResult, WallpaperBackend
from gnomepaper_engine.wallpaper.focus_audio import FocusAudioGuard
from gnomepaper_engine.wallpaper.gnome_bg import set_picture
from gnomepaper_engine.wallpaper.process_audio import set_wallpaper_volume

log = logging.getLogger(__name__)

_VIDEO_EXTS = {".mp4", ".webm", ".mkv", ".avi", ".mov"}


class VideoBackend(WallpaperBackend):
    """Plays a video on the desktop layer via the desktop_player process."""

    name = "video"

    def __init__(self) -> None:
        self._proc: subprocess.Popen[str] | None = None
        self._focus_guard = FocusAudioGuard()
        self._volume = 70
        self._muted = False
        self._volume_file: Path | None = None

    def supports(self, item: WallpaperItem) -> bool:
        if item.wallpaper_type == WallpaperType.VIDEO:
            return True
        return self._find_video(item) is not None

    def _find_video(self, item: WallpaperItem) -> Path | None:
        folder = item.path
        meta_file = item.meta.get("file")
        if isinstance(meta_file, str):
            candidate = folder / meta_file
            if candidate.is_file() and candidate.suffix.lower() in _VIDEO_EXTS:
                return candidate

        if not folder.is_dir():
            return None
        candidates: list[Path] = []
        for path in folder.rglob("*"):
            if path.is_file() and path.suffix.lower() in _VIDEO_EXTS:
                candidates.append(path)
        if not candidates:
            return None
        preferred_names = {"video.mp4", "video.webm", "mp4", "webm"}
        for c in candidates:
            if c.name.lower() in preferred_names or c.stem.lower() in preferred_names:
                return c
        return sorted(candidates, key=lambda p: p.stat().st_size, reverse=True)[0]

    def apply(self, item: WallpaperItem, config: AppConfig) -> BackendResult:
        video = self._find_video(item)
        if video is None:
            return BackendResult(False, "No video file found in wallpaper package")

        self.stop()

        if item.preview_path and item.preview_path.is_file():
            set_picture(item.preview_path)
        else:
            still = self._extract_still(video, config)
            if still is not None:
                set_picture(still)

        self._muted = bool(config.mute_audio)
        self._volume = max(0, min(100, int(config.audio_volume)))
        self._volume_file = config.cache_dir() / "desktop_player_volume"
        self._write_volume_file()

        env = os.environ.copy()
        if env.get("WAYLAND_DISPLAY") and not env.get("GNOMEPAPER_FORCE_WAYLAND"):
            env.pop("WAYLAND_DISPLAY", None)
            env.pop("WAYLAND_SOCKET", None)
            env.setdefault("DISPLAY", ":0")
            env["XDG_SESSION_TYPE"] = "x11"
            env["GDK_BACKEND"] = "x11"

        cmd = [
            sys.executable,
            "-m",
            "gnomepaper_engine.wallpaper.desktop_player",
            "--video",
            str(video),
            "--volume-file",
            str(self._volume_file),
        ]
        if self._muted or self._volume <= 0:
            cmd.append("--mute")
        else:
            vol = max(0.0, min(1.0, float(self._volume) / 100.0))
            cmd.extend(["--volume", f"{vol:.2f}"])

        log_path = config.cache_dir() / "desktop_player.log"
        log.info("Starting desktop video surface: %s (log %s)", video, log_path)
        try:
            log_f = open(log_path, "w", encoding="utf-8")  # noqa: SIM115
            self._proc = subprocess.Popen(
                cmd,
                env=env,
                stdout=log_f,
                stderr=subprocess.STDOUT,
                text=True,
                start_new_session=True,
            )
            log_f.close()
        except OSError as exc:
            return BackendResult(False, f"Failed to start desktop player: {exc}")

        try:
            code = self._proc.wait(timeout=0.6)
            err = ""
            try:
                err = log_path.read_text(encoding="utf-8", errors="replace")[-400:]
            except OSError:
                pass
            self._proc = None
            return BackendResult(
                False,
                f"Desktop player exited immediately ({code}). {err.strip()}",
            )
        except subprocess.TimeoutExpired:
            pass

        self._start_audio_guard()
        threading.Thread(target=self._deferred_volume, daemon=True).start()
        return BackendResult(True, f"Set desktop wallpaper: {item.title}")

    def set_audio(self, *, volume: int, muted: bool) -> None:
        self._volume = max(0, min(100, int(volume)))
        self._muted = bool(muted)
        self._write_volume_file()
        pids = self._running_pids()
        self._focus_guard.configure(
            pids=pids,
            volume=self._volume,
            user_muted=self._muted,
            enabled=True,
        )
        try:
            self._focus_guard.notify_user_volume_change()
        except Exception:
            pass
        n = set_wallpaper_volume(self._volume, muted=self._muted, pids=pids)
        log.info("Video set_audio volume=%s muted=%s updated=%s", self._volume, self._muted, n)
        self._focus_guard.apply_now()

    def _write_volume_file(self) -> None:
        if self._volume_file is None:
            return
        try:
            # format: "muted|volume" e.g. "0|70" or "1|0"
            self._volume_file.write_text(
                f"{1 if self._muted else 0}|{self._volume}\n",
                encoding="utf-8",
            )
        except OSError as exc:
            log.debug("volume file write failed: %s", exc)

    def _deferred_volume(self) -> None:
        for wait in (0.5, 1.5, 3.0, 5.0):
            time.sleep(wait)
            if not self.is_running:
                return
            pids = self._running_pids()
            set_wallpaper_volume(self._volume, muted=self._muted, pids=pids)

    def _running_pids(self) -> list[int]:
        if self._proc is None or self._proc.poll() is not None:
            return []
        return [self._proc.pid]

    def _start_audio_guard(self) -> None:
        pids = self._running_pids()
        self._focus_guard.configure(
            pids=pids,
            volume=self._volume,
            user_muted=self._muted,
            enabled=True,
        )
        self._focus_guard.start()

    def _extract_still(self, video: Path, config: AppConfig) -> Path | None:
        import shutil

        if not shutil.which("ffmpeg"):
            return None
        out = config.cache_dir() / f"still_{video.stem}.jpg"
        if out.is_file() and out.stat().st_mtime >= video.stat().st_mtime:
            return out
        try:
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-ss",
                    "1",
                    "-i",
                    str(video),
                    "-frames:v",
                    "1",
                    str(out),
                ],
                check=True,
                capture_output=True,
            )
            return out if out.is_file() else None
        except (OSError, subprocess.CalledProcessError) as exc:
            log.debug("still extract failed: %s", exc)
            return None

    def stop(self) -> None:
        self._focus_guard.stop()
        if self._proc is None:
            return
        if self._proc.poll() is None:
            try:
                os.killpg(self._proc.pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError, OSError):
                self._proc.terminate()
            try:
                self._proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(self._proc.pid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError, OSError):
                    self._proc.kill()
        self._proc = None

    @property
    def is_running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None
