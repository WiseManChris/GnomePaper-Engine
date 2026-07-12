"""Scene wallpaper backend via linux-wallpaperengine."""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import threading
import time

from gnomepaper_engine.config import AppConfig
from gnomepaper_engine.steam.models import WallpaperItem, WallpaperType
from gnomepaper_engine.wallpaper.backends.base import BackendResult, WallpaperBackend
from gnomepaper_engine.wallpaper.backends.lwe import (
    find_assets_dir,
    find_lwe_binary,
    install_hint,
)
from gnomepaper_engine.wallpaper.display_geometry import monitor_geometries
from gnomepaper_engine.wallpaper.focus_audio import FocusAudioGuard
from gnomepaper_engine.wallpaper.gnome_bg import set_picture
from gnomepaper_engine.wallpaper.process_audio import set_wallpaper_volume
from gnomepaper_engine.wallpaper.x11_desktop import lower_pid_windows, mark_window_by_pid

log = logging.getLogger(__name__)


class SceneBackend(WallpaperBackend):
    """
    Renders Wallpaper Engine scenes using linux-wallpaperengine.

    On GNOME (no wlr-layer-shell), LWE runs in window mode and we keep
    those windows below apps, sized strictly to the workarea so the top
    bar (clock / control center) stays visible.
    """

    name = "scene"

    def __init__(self) -> None:
        self._procs: list[subprocess.Popen[str]] = []
        self._geometries: list[tuple[int, int, int, int]] = []
        self._lower_stop = threading.Event()
        self._lower_thread: threading.Thread | None = None
        self._focus_guard = FocusAudioGuard()
        self._volume = 70
        self._muted = False

    def supports(self, item: WallpaperItem) -> bool:
        if item.wallpaper_type == WallpaperType.SCENE:
            return True
        if (item.path / "scene.pkg").is_file() or (item.path / "scene.json").is_file():
            return True
        return False

    def apply(self, item: WallpaperItem, config: AppConfig) -> BackendResult:
        binary = find_lwe_binary()
        if binary is None:
            if item.preview_path and item.preview_path.is_file():
                set_picture(item.preview_path)
                return BackendResult(
                    False,
                    f"Preview set as static wallpaper. Live scenes need "
                    f"linux-wallpaperengine.\n{install_hint()}",
                )
            return BackendResult(False, install_hint())

        self.stop()

        if item.preview_path and item.preview_path.is_file():
            set_picture(item.preview_path)

        assets = find_assets_dir(config.steam_library_paths)
        geos = monitor_geometries()
        # Hard safety: never start at y=0 full height (covers GNOME panel)
        geos = [_safe_workarea_geo(g) for g in geos]
        self._geometries = geos
        env = self._x11_env()

        self._muted = bool(config.mute_audio)
        self._volume = max(0, min(100, int(config.audio_volume)))

        bg_arg = str(item.path)
        common: list[str] = [str(binary)]
        if self._muted or self._volume <= 0:
            common.append("--silent")
        else:
            # Engine volume = user volume (0–100). Live slider also drives Pulse.
            common.extend(["--volume", str(self._volume)])
        common.extend(["--fps", str(max(15, min(60, config.target_fps)))])
        # Always disable mouse grab for wallpaper layer — LWE must never take
        # keyboard/mouse control away from normal apps (typing, clicking).
        common.append("--disable-mouse")
        common.append("--disable-parallax")
        if assets is not None:
            common.extend(["--assets-dir", str(assets)])

        started: list[subprocess.Popen[str]] = []
        for x, y, w, h in geos:
            # LWE --window is XxYxWxH (position + size) — MUST be workarea only
            cmd = [
                *common,
                "--window",
                f"{x}x{y}x{w}x{h}",
                "--scaling",
                "fill",
                bg_arg,
            ]
            log.info("Starting LWE (workarea %dx%d+%d+%d): %s", w, h, x, y, " ".join(cmd))
            log_path = config.cache_dir() / f"lwe_{x}_{y}.log"
            try:
                log_f = open(log_path, "w", encoding="utf-8")  # noqa: SIM115
                proc = subprocess.Popen(
                    cmd,
                    env=env,
                    stdout=log_f,
                    stderr=subprocess.STDOUT,
                    text=True,
                    start_new_session=True,
                )
                log_f.close()
            except OSError as exc:
                self._kill_all(started)
                return BackendResult(False, f"Failed to start linux-wallpaperengine: {exc}")
            started.append(proc)

        time.sleep(0.8)
        alive = [p for p in started if p.poll() is None]
        if not alive:
            return BackendResult(
                False,
                "linux-wallpaperengine exited immediately — see "
                f"{config.cache_dir()}/lwe_*.log",
            )

        self._procs = alive
        for idx, p in enumerate(self._procs):
            geo = geos[idx] if idx < len(geos) else geos[0]
            ok = mark_window_by_pid(p.pid, geometry=geo, retries=40, delay=0.25)
            log.info("Wallpaper-layer promote pid=%s geo=%s ok=%s", p.pid, geo, ok)
            threading.Thread(
                target=self._delayed_fit,
                args=(p.pid, geo),
                daemon=True,
            ).start()

        self._start_lower_loop()
        self._start_audio_guard()
        # Apply live volume after audio stream appears
        threading.Thread(target=self._deferred_volume, daemon=True).start()
        return BackendResult(True, f"Scene wallpaper active: {item.title}")

    def set_audio(self, *, volume: int, muted: bool) -> None:
        """Live volume/mute while scene is running (Pulse + focus guard)."""
        self._volume = max(0, min(100, int(volume)))
        self._muted = bool(muted)
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
        # Match LWE by stream name (PipeWire often omits process.id)
        n = set_wallpaper_volume(self._volume, muted=self._muted, pids=pids)
        log.info("Scene set_audio volume=%s muted=%s updated=%s", self._volume, self._muted, n)
        # Apply immediately; focus guard only toggles mute, keeps volume level
        self._focus_guard.apply_now()
        # If Pulse has not registered the stream yet, keep retrying briefly
        if n == 0:
            threading.Thread(target=self._retry_volume, args=(8,), daemon=True).start()

    def _retry_volume(self, attempts: int) -> None:
        for i in range(attempts):
            time.sleep(0.4)
            if not self.is_running:
                return
            n = set_wallpaper_volume(
                self._volume, muted=self._muted, pids=self._running_pids()
            )
            if n > 0:
                log.info("Scene volume applied after retry %s", i + 1)
                self._focus_guard.apply_now()
                return

    def _deferred_volume(self) -> None:
        for wait in (0.4, 1.0, 2.0, 4.0, 7.0, 12.0):
            time.sleep(wait)
            if not self.is_running:
                return
            pids = self._running_pids()
            n = set_wallpaper_volume(self._volume, muted=self._muted, pids=pids)
            if n > 0:
                self._focus_guard.apply_now()

    def _running_pids(self) -> list[int]:
        return [p.pid for p in self._procs if p.poll() is None]

    def _start_audio_guard(self) -> None:
        pids = self._running_pids()
        self._focus_guard.configure(
            pids=pids,
            volume=self._volume,
            user_muted=self._muted,
            enabled=True,
        )
        self._focus_guard.start()

    def _delayed_fit(self, pid: int, geo: tuple[int, int, int, int]) -> None:
        for wait in (0.8, 1.5, 2.5, 4.0, 7.0):
            time.sleep(wait)
            if not any(p.pid == pid and p.poll() is None for p in self._procs):
                return
            mark_window_by_pid(pid, geometry=geo, retries=3, delay=0.1)

    def _x11_env(self) -> dict[str, str]:
        env = os.environ.copy()
        if env.get("WAYLAND_DISPLAY") and not env.get("GNOMEPAPER_FORCE_WAYLAND"):
            env.pop("WAYLAND_DISPLAY", None)
            env.pop("WAYLAND_SOCKET", None)
            env.setdefault("DISPLAY", ":0")
            env["XDG_SESSION_TYPE"] = "x11"
            env["GDK_BACKEND"] = "x11"
            env["SDL_VIDEODRIVER"] = "x11"
            env["GLFW_PLATFORM"] = "x11"
            env["QT_QPA_PLATFORM"] = "xcb"
            env.setdefault("__GL_THREADED_OPTIMIZATIONS", "0")
        return env

    def _start_lower_loop(self) -> None:
        self._lower_stop.clear()

        def _loop() -> None:
            # Light reassert only — never steals keyboard focus
            while not self._lower_stop.wait(1.0):
                for idx, p in enumerate(list(self._procs)):
                    if p.poll() is None:
                        geo = (
                            self._geometries[idx]
                            if idx < len(self._geometries)
                            else (self._geometries[0] if self._geometries else None)
                        )
                        lower_pid_windows(p.pid, geometry=geo)

        self._lower_thread = threading.Thread(target=_loop, name="lwe-lower", daemon=True)
        self._lower_thread.start()

    def _kill_all(self, procs: list[subprocess.Popen[str]] | None = None) -> None:
        targets = procs if procs is not None else self._procs
        for p in targets:
            if p.poll() is not None:
                continue
            try:
                os.killpg(p.pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError, OSError):
                p.terminate()
            try:
                p.wait(timeout=3)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(p.pid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError, OSError):
                    p.kill()

    def stop(self) -> None:
        self._lower_stop.set()
        self._focus_guard.stop()
        self._kill_all()
        self._procs = []
        self._geometries = []

    @property
    def is_running(self) -> bool:
        return any(p.poll() is None for p in self._procs)


def _safe_workarea_geo(geo: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    """
    Never allow a wallpaper rect that starts at y=0 with full display height.
    GNOME top bar is typically 32–64 physical px on HiDPI.
    """
    x, y, w, h = geo
    if y < 28:
        # Force top inset so panel cannot be covered even if workarea failed
        inset = max(32, 64 - y) if y == 0 else 32
        y = inset
        h = max(1, h - inset)
    return (x, y, w, h)
