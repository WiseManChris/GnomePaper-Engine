"""Mark X11 windows as full-screen desktop backgrounds (below everything)."""

from __future__ import annotations

import logging
import shutil
import subprocess
import time

log = logging.getLogger(__name__)


def _run(cmd: list[str]) -> bool:
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        return True
    except (OSError, subprocess.CalledProcessError) as exc:
        log.debug("cmd failed %s: %s", cmd, exc)
        return False


def resize_xid(xid: int, x: int, y: int, w: int, h: int) -> None:
    """Force window geometry (gravity 0 = northwest)."""
    id_str = str(xid)
    if shutil.which("wmctrl"):
        # -e gravity,x,y,w,h
        _run(["wmctrl", "-i", "-r", id_str, "-e", f"0,{x},{y},{w},{h}"])
    if shutil.which("xdotool"):
        _run(["xdotool", "windowmove", id_str, str(x), str(y)])
        _run(["xdotool", "windowsize", id_str, str(w), str(h)])
    # Also try xprop-less path via xwininfo for verification
    log.info("Resized window %#x → %dx%d+%d+%d", xid, w, h, x, y)


def mark_xid_as_desktop(
    xid: int,
    *,
    geometry: tuple[int, int, int, int] | None = None,
) -> None:
    """
    Apply EWMH desktop + below + skip-taskbar hints, and optionally force size.

    Order matters on GNOME/XWayland: size first, then desktop type / below.
    """
    id_str = str(xid)

    if geometry is not None:
        x, y, w, h = geometry
        resize_xid(xid, x, y, w, h)

    if shutil.which("xprop"):
        _run(
            [
                "xprop",
                "-id",
                id_str,
                "-f",
                "_NET_WM_WINDOW_TYPE",
                "32a",
                "-set",
                "_NET_WM_WINDOW_TYPE",
                "_NET_WM_WINDOW_TYPE_DESKTOP",
            ]
        )
        _run(
            [
                "xprop",
                "-id",
                id_str,
                "-f",
                "_NET_WM_STATE",
                "32a",
                "-set",
                "_NET_WM_STATE",
                "_NET_WM_STATE_BELOW,_NET_WM_STATE_SKIP_TASKBAR,_NET_WM_STATE_SKIP_PAGER,_NET_WM_STATE_STICKY",
            ]
        )
        # Undecorated / no input focus hints
        _run(
            [
                "xprop",
                "-id",
                id_str,
                "-f",
                "_MOTIF_WM_HINTS",
                "32c",
                "-set",
                "_MOTIF_WM_HINTS",
                "0x2, 0x0, 0x0, 0x0, 0x0",
            ]
        )

    if shutil.which("wmctrl"):
        _run(
            [
                "wmctrl",
                "-i",
                "-r",
                id_str,
                "-b",
                "add,below,skip_taskbar,skip_pager,sticky",
            ]
        )
        # Re-apply size after state change (GNOME sometimes resets it)
        if geometry is not None:
            x, y, w, h = geometry
            _run(["wmctrl", "-i", "-r", id_str, "-e", f"0,{x},{y},{w},{h}"])
        _run(["wmctrl", "-i", "-r", id_str, "-b", "add,below"])

    # Lower stacking
    if shutil.which("xdotool"):
        _run(["xdotool", "windowlower", id_str])


def mark_window_by_pid(
    pid: int,
    *,
    geometry: tuple[int, int, int, int] | None = None,
    retries: int = 40,
    delay: float = 0.25,
) -> bool:
    """Find windows owned by pid (or title match) and make them full desktop surfaces."""
    if not shutil.which("wmctrl") and not shutil.which("xprop"):
        return False

    for attempt in range(retries):
        xids = _xids_for_pid(pid)
        if not xids:
            xids = _xids_for_wallpaper_titles()
        if xids:
            for xid in xids:
                mark_xid_as_desktop(xid, geometry=geometry)
            # Second pass a moment later — GLFW often resizes itself after map
            if geometry is not None and attempt == 0:
                time.sleep(0.4)
                for xid in _xids_for_pid(pid) or xids:
                    resize_xid(xid, *geometry)
                    mark_xid_as_desktop(xid, geometry=geometry)
            return True
        time.sleep(delay)
    log.warning("Could not find X11 windows for pid %s", pid)
    return False


def _xids_for_pid(pid: int) -> list[int]:
    """Parse `wmctrl -lp` for matching PIDs."""
    if not shutil.which("wmctrl"):
        return []
    try:
        out = subprocess.check_output(["wmctrl", "-lp"], text=True, errors="replace")
    except (OSError, subprocess.CalledProcessError):
        return []
    found: list[int] = []
    for line in out.splitlines():
        parts = line.split(None, 4)
        if len(parts) < 3:
            continue
        try:
            xid = int(parts[0], 16)
            wpid = int(parts[2])
        except ValueError:
            continue
        if wpid == pid:
            found.append(xid)
    return found


def _xids_for_wallpaper_titles() -> list[int]:
    """Fallback: match known wallpaper window titles."""
    if not shutil.which("wmctrl"):
        return []
    try:
        out = subprocess.check_output(["wmctrl", "-l"], text=True, errors="replace")
    except (OSError, subprocess.CalledProcessError):
        return []
    keys = ("wallpaperengine", "gnomepaper wallpaper", "linux-wallpaperengine")
    found: list[int] = []
    for line in out.splitlines():
        low = line.lower()
        if not any(k in low for k in keys):
            continue
        parts = line.split(None, 3)
        if not parts:
            continue
        try:
            found.append(int(parts[0], 16))
        except ValueError:
            continue
    return found


def lower_pid_windows(
    pid: int,
    *,
    geometry: tuple[int, int, int, int] | None = None,
) -> None:
    xids = _xids_for_pid(pid) or _xids_for_wallpaper_titles()
    for xid in xids:
        if geometry is not None:
            resize_xid(xid, *geometry)
        if shutil.which("wmctrl"):
            _run(["wmctrl", "-i", "-r", str(xid), "-b", "add,below"])
        if shutil.which("xdotool"):
            _run(["xdotool", "windowlower", str(xid)])
