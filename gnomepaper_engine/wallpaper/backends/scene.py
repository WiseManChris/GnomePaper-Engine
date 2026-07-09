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
from gnomepaper_engine.wallpaper.gnome_bg import set_picture
from gnomepaper_engine.wallpaper.x11_desktop import lower_pid_windows, mark_window_by_pid

log = logging.getLogger(__name__)


class SceneBackend(WallpaperBackend):
    """
    Renders Wallpaper Engine scenes using linux-wallpaperengine.

    On GNOME (no wlr-layer-shell), LWE runs in window mode and we promote
    those windows to a full-screen desktop layer via X11/EWMH (XWayland).
    """

    name = "scene"

    def __init__(self) -> None:
        self._procs: list[subprocess.Popen[str]] = []
        self._geometries: list[tuple[int, int, int, int]] = []
        self._lower_stop = threading.Event()
        self._lower_thread: threading.Thread | None = None

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
        self._geometries = geos
        env = self._x11_env()

        bg_arg = str(item.path)
        common: list[str] = [str(binary)]
        if config.mute_audio:
            common.append("--silent")
        else:
            vol = max(0, min(100, int(config.audio_volume)))
            common.extend(["--volume", str(vol)])
            # Keep audio when other apps play sound (WE-like default)
            common.append("--noautomute")
        common.extend(["--fps", str(max(15, min(60, config.target_fps)))])
        # Mouse / eye-follow / parallax — do NOT pass --disable-mouse when enabled
        if not config.mouse_interaction:
            common.append("--disable-mouse")
            common.append("--disable-parallax")
        if assets is not None:
            common.extend(["--assets-dir", str(assets)])

        # One LWE process per monitor, full-screen geometry from xrandr
        started: list[subprocess.Popen[str]] = []
        for x, y, w, h in geos:
            # LWE --window is XxYxWxH (position + size)
            cmd = [
                *common,
                "--window",
                f"{x}x{y}x{w}x{h}",
                "--scaling",
                "fill",
                bg_arg,
            ]
            log.info("Starting LWE fullscreen: %s", " ".join(cmd))
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
        # Force full-screen + desktop layer (LWE often opens tiny until we resize)
        for idx, p in enumerate(self._procs):
            geo = geos[idx] if idx < len(geos) else geos[0]
            ok = mark_window_by_pid(p.pid, geometry=geo, retries=40, delay=0.25)
            log.info("Desktop-layer promote pid=%s geo=%s ok=%s", p.pid, geo, ok)
            # Extra delayed resize — GLFW sometimes reverts size once after map
            threading.Thread(
                target=self._delayed_fit,
                args=(p.pid, geo),
                daemon=True,
            ).start()

        self._start_lower_loop()
        return BackendResult(True, f"Scene wallpaper active: {item.title}")

    def _delayed_fit(self, pid: int, geo: tuple[int, int, int, int]) -> None:
        for wait in (1.0, 2.5, 5.0):
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
            while not self._lower_stop.wait(2.0):
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
        self._kill_all()
        self._procs = []
        self._geometries = []

    @property
    def is_running(self) -> bool:
        return any(p.poll() is None for p in self._procs)
