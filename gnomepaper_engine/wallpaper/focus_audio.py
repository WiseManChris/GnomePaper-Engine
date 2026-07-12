"""Mute wallpaper audio when another app is in front (Windows-WE style).

On GNOME Wayland, prefer AT-SPI for focus. Invert keep-list: only shell /
GnomePaper / wallpaper itself may keep audio; everything else mutes.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
import threading
import time

from gnomepaper_engine.wallpaper.process_audio import set_wallpaper_volume

log = logging.getLogger(__name__)

# Only these may keep wallpaper audio while "focused"
_KEEP_AUDIO_APPS = (
    "gnomepaper",
    "linux-wallpaperengine",
    "wallpaperengine",
    "gnomepaper-wallpaper",
    "gnome-shell",
    "mutter-x11-frames",
)

_atspi_ready: bool | None = None


class FocusAudioGuard:
    """
    Mute wallpaper streams when another app is in front; restore user volume
    only on desktop / shell / GnomePaper.

    Does not touch window focus — audio only.
    """

    def __init__(self) -> None:
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._pids: list[int] = []
        self._volume = 70
        self._user_muted = False
        self._enabled = True
        self._lock = threading.Lock()
        self._last_obscured: bool | None = None
        # After a user volume change, force-apply volume for a short window
        # even if we also re-evaluate mute (so the slider always "sticks").
        self._force_until = 0.0

    def configure(
        self,
        *,
        pids: list[int],
        volume: int,
        user_muted: bool,
        enabled: bool = True,
    ) -> None:
        with self._lock:
            self._pids = list(pids)
            self._volume = max(0, min(100, int(volume)))
            self._user_muted = bool(user_muted)
            self._enabled = bool(enabled)

    def notify_user_volume_change(self) -> None:
        """Call when the user moves the volume slider / mute switch."""
        with self._lock:
            self._force_until = time.monotonic() + 3.0

    def start(self) -> None:
        self._stop.clear()
        if self._thread is not None and self._thread.is_alive():
            return
        self._thread = threading.Thread(
            target=self._loop, name="focus-audio-guard", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread = None
        self._last_obscured = None

    def apply_now(self) -> None:
        with self._lock:
            pids = list(self._pids)
            vol = self._volume
            user_muted = self._user_muted
            enabled = self._enabled
        self._push(pids, vol, user_muted, enabled)

    def _loop(self) -> None:
        while not self._stop.wait(0.5):
            with self._lock:
                pids = list(self._pids)
                vol = self._volume
                user_muted = self._user_muted
                enabled = self._enabled
            self._push(pids, vol, user_muted, enabled)

    def _push(
        self,
        pids: list[int],
        vol: int,
        user_muted: bool,
        enabled: bool,
    ) -> None:
        if user_muted or vol <= 0:
            set_wallpaper_volume(vol if vol > 0 else 0, muted=True, pids=pids)
            return
        if not enabled:
            set_wallpaper_volume(vol, muted=False, pids=pids)
            return

        obscured = _wallpaper_obscured(pids)
        if obscured != self._last_obscured:
            log.info("Wallpaper audio obscured=%s (focused=%s)", obscured, _describe_focus())
            self._last_obscured = obscured

        # Always write the volume level; mute only when something is in front
        set_wallpaper_volume(vol, muted=obscured, pids=pids)


def _wallpaper_obscured(wallpaper_pids: list[int]) -> bool:
    """True when any real application window is in front of the wallpaper."""
    # 1) AT-SPI focused app (Wayland-native)
    focused = _atspi_all_focused_apps()
    for app in focused:
        if _is_keep_audio_app(app):
            continue
        # Any other focused/active app ⇒ mute
        return True

    # If AT-SPI found only keep-apps (shell / gnomepaper), allow audio
    if focused:
        return False

    # 2) X11 active window (XWayland clients)
    active = _x11_active_window_info()
    if active is not None:
        pid, wm_class, title = active
        if pid is not None and wallpaper_pids and pid in wallpaper_pids:
            # Wallpaper itself focused — treat as not a real app in front
            # (focus should be released elsewhere); keep audio
            return False
        blob = f"{wm_class or ''} {title or ''}".lower()
        if _is_keep_audio_app(blob):
            return False
        if blob.strip():
            return True

    # 3) Any non-wallpaper X11 window that looks normal/mapped (extra net)
    if _x11_other_window_present(wallpaper_pids):
        # Only mute via this path if something has X11 focus that's not us
        # — already handled above. Don't mute just because windows exist
        # (user may want audio with windows open if they're not focused).
        # User asked for mute when window is "in front" = focused.
        pass

    # Unknown / empty desktop → allow audio
    return False


def _describe_focus() -> str:
    apps = _atspi_all_focused_apps()
    if apps:
        return ",".join(apps)
    active = _x11_active_window_info()
    if active:
        return f"x11:{active[1]} {active[2]}"
    return "none"


def _is_keep_audio_app(name: str) -> bool:
    low = (name or "").lower()
    if not low.strip():
        return True
    return any(k in low for k in _KEEP_AUDIO_APPS)


def _atspi_all_focused_apps() -> list[str]:
    """Return names of apps that currently have an ACTIVE or FOCUSED window."""
    global _atspi_ready
    found: list[str] = []
    try:
        import gi

        gi.require_version("Atspi", "2.0")
        from gi.repository import Atspi

        if _atspi_ready is not True:
            try:
                Atspi.init()
            except Exception:
                pass
            _atspi_ready = True

        desktop = Atspi.get_desktop(0)
        if desktop is None:
            return found

        for i in range(desktop.get_child_count()):
            app = desktop.get_child_at_index(i)
            if app is None:
                continue
            app_name = app.get_name() or ""
            try:
                # App-level ACTIVE (some toolkits)
                st = app.get_state_set()
                if st is not None and (
                    st.contains(Atspi.StateType.ACTIVE)
                    or st.contains(Atspi.StateType.FOCUSED)
                ):
                    if app_name and app_name not in found:
                        found.append(app_name)
            except Exception:
                pass

            try:
                n = app.get_child_count()
            except Exception:
                continue
            for j in range(n):
                try:
                    ch = app.get_child_at_index(j)
                except Exception:
                    continue
                if ch is None:
                    continue
                try:
                    st = ch.get_state_set()
                    if st is None:
                        continue
                    if st.contains(Atspi.StateType.ACTIVE) or st.contains(
                        Atspi.StateType.FOCUSED
                    ):
                        if app_name and app_name not in found:
                            found.append(app_name)
                        break
                except Exception:
                    continue
    except Exception as exc:
        log.debug("AT-SPI focus probe failed: %s", exc)
        _atspi_ready = False
    return found


def _x11_active_window_info() -> tuple[int | None, str, str] | None:
    if not shutil.which("xprop"):
        return None
    try:
        out = subprocess.check_output(
            ["xprop", "-root", "_NET_ACTIVE_WINDOW"],
            text=True,
            errors="replace",
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    m = re.search(r"window id # (0x[0-9a-fA-F]+)", out)
    if not m:
        return None
    xid = m.group(1)
    if xid in ("0x0", "0x00"):
        return None
    pid: int | None = None
    wm_class = ""
    title = ""
    try:
        props = subprocess.check_output(
            ["xprop", "-id", xid, "_NET_WM_PID", "WM_CLASS", "WM_NAME", "_NET_WM_NAME"],
            text=True,
            errors="replace",
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    for line in props.splitlines():
        if "_NET_WM_PID" in line and "=" in line:
            m2 = re.search(r"=\s*(\d+)", line)
            if m2:
                pid = int(m2.group(1))
        elif "WM_CLASS" in line and "=" in line:
            wm_class = line.split("=", 1)[1].strip()
        elif ("WM_NAME" in line or "_NET_WM_NAME" in line) and "=" in line:
            title = line.split("=", 1)[1].strip()
    return pid, wm_class, title


def _x11_other_window_present(wallpaper_pids: list[int]) -> bool:
    if not shutil.which("wmctrl"):
        return False
    try:
        out = subprocess.check_output(["wmctrl", "-lp"], text=True, errors="replace")
    except (OSError, subprocess.CalledProcessError):
        return False
    wp = set(wallpaper_pids)
    keys = ("gnomepaper wallpaper", "wallpaperengine", "gnomepaper-wallpaper")
    for line in out.splitlines():
        parts = line.split(None, 4)
        if len(parts) < 3:
            continue
        try:
            wpid = int(parts[2])
        except ValueError:
            continue
        if wpid in wp:
            continue
        title = parts[4].lower() if len(parts) > 4 else ""
        if any(k in title for k in keys):
            continue
        # desktop -1 sticky wallpaper-like; skip empty
        if not title.strip():
            continue
        return True
    return False
