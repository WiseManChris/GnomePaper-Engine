"""
Place wallpaper windows behind apps without covering the GNOME top bar,
without appearing in the dock, and without stealing keyboard/mouse focus.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import time

log = logging.getLogger(__name__)

_WALLPAPER_CLASS = "gnomepaper-wallpaper"
_WALLPAPER_TITLE = "GnomePaper Wallpaper Surface"


def _run(cmd: list[str]) -> bool:
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        return True
    except (OSError, subprocess.CalledProcessError) as exc:
        log.debug("cmd failed %s: %s", cmd, exc)
        return False


def resize_xid(xid: int, x: int, y: int, w: int, h: int) -> None:
    id_str = str(xid)
    if shutil.which("wmctrl"):
        _run(["wmctrl", "-i", "-r", id_str, "-e", f"0,{x},{y},{w},{h}"])
    if shutil.which("xdotool"):
        _run(["xdotool", "windowmove", id_str, str(x), str(y)])
        _run(["xdotool", "windowsize", id_str, str(w), str(h)])


def _hide_from_dock(xid: int) -> None:
    id_str = str(xid)
    if shutil.which("xdotool"):
        _run(
            [
                "xdotool",
                "set_window",
                "--name",
                _WALLPAPER_TITLE,
                "--classname",
                _WALLPAPER_CLASS,
                "--class",
                _WALLPAPER_CLASS,
                id_str,
            ]
        )
    if shutil.which("xprop"):
        _run(
            [
                "xprop",
                "-id",
                id_str,
                "-f",
                "WM_NAME",
                "8s",
                "-set",
                "WM_NAME",
                _WALLPAPER_TITLE,
            ]
        )
        _run(
            [
                "xprop",
                "-id",
                id_str,
                "-f",
                "_NET_WM_NAME",
                "8u",
                "-set",
                "_NET_WM_NAME",
                _WALLPAPER_TITLE,
            ]
        )
        _run(
            [
                "xprop",
                "-id",
                id_str,
                "-f",
                "_GTK_APPLICATION_ID",
                "8u",
                "-set",
                "_GTK_APPLICATION_ID",
                "io.github.gnomepaper.WallpaperSurface",
            ]
        )
        _run(["xprop", "-id", id_str, "-remove", "BAMF_DESKTOP_FILE_HINT"])


def _set_no_input_hints(xid: int) -> None:
    """Ask the WM not to give this window keyboard focus."""
    id_str = str(xid)
    if not shutil.which("xprop"):
        return
    # WM_HINTS: flags=InputHint(1), input=0 → does not want keyboard input
    # format: flags, input, initial_state, icon_pixmap, icon_window, icon_x, icon_y, icon_mask, window_group
    _run(
        [
            "xprop",
            "-id",
            id_str,
            "-f",
            "WM_HINTS",
            "32i",
            "-set",
            "WM_HINTS",
            "1, 0, 1, 0, 0, 0, 0, 0, 0",
        ]
    )
    # Motif: undecorated, functions=0
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
            "0x3, 0x0, 0x0, 0x0, 0x0",
        ]
    )


def _apply_layer_state(xid: int) -> None:
    """Below + skip taskbar/pager. Never touches input focus."""
    id_str = str(xid)

    if shutil.which("wmctrl"):
        _run(
            [
                "wmctrl",
                "-i",
                "-r",
                id_str,
                "-b",
                "remove,fullscreen,maximized_vert,maximized_horz,above",
            ]
        )
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
                "_NET_WM_WINDOW_TYPE_NORMAL",
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
        _run(
            [
                "xprop",
                "-id",
                id_str,
                "-f",
                "_NET_WM_STRUT",
                "32c",
                "-set",
                "_NET_WM_STRUT",
                "0, 0, 0, 0",
            ]
        )

    if shutil.which("xdotool"):
        for state in ("FULLSCREEN", "MAXIMIZED_VERT", "MAXIMIZED_HORZ", "ABOVE"):
            _run(["xdotool", "windowstate", "--remove", state, id_str])
        for state in ("BELOW", "SKIP_TASKBAR", "SKIP_PAGER", "STICKY"):
            _run(["xdotool", "windowstate", "--add", state, id_str])
        # Lower only — NEVER windowfocus (that steals the keyboard from the user)
        _run(["xdotool", "windowlower", id_str])


def mark_xid_as_desktop(
    xid: int,
    *,
    geometry: tuple[int, int, int, int] | None = None,
    full: bool = True,
) -> None:
    """
    Wallpaper layer: below apps, workarea geometry, hidden from dock.

    full=True  → also rebrand class/title and no-input hints (startup)
    full=False → light reassert only (periodic loop — must not steal focus)
    """
    _apply_layer_state(xid)
    if full:
        _hide_from_dock(xid)
        _set_no_input_hints(xid)

    if geometry is not None:
        x, y, w, h = geometry
        if y < 1:
            y = 32
            h = max(1, h - 32)
        resize_xid(xid, x, y, w, h)
        _apply_layer_state(xid)

    if full and shutil.which("xdotool"):
        # One-time: if wallpaper grabbed focus at map, release it once.
        # Do NOT do this on the periodic loop.
        _run(["xdotool", "windowlower", str(xid)])


def mark_window_by_pid(
    pid: int,
    *,
    geometry: tuple[int, int, int, int] | None = None,
    retries: int = 40,
    delay: float = 0.25,
) -> bool:
    if not shutil.which("wmctrl") and not shutil.which("xprop"):
        return False

    for _attempt in range(retries):
        xids = _xids_for_pid(pid)
        if not xids:
            xids = _xids_for_wallpaper_titles()
        if xids:
            for xid in xids:
                mark_xid_as_desktop(xid, geometry=geometry, full=True)
            time.sleep(0.35)
            for xid in _xids_for_pid(pid) or xids:
                mark_xid_as_desktop(xid, geometry=geometry, full=True)
            return True
        time.sleep(delay)
    log.warning("Could not find X11 windows for pid %s", pid)
    return False


def _xids_for_pid(pid: int) -> list[int]:
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
    if not shutil.which("wmctrl"):
        return []
    try:
        out = subprocess.check_output(["wmctrl", "-l"], text=True, errors="replace")
    except (OSError, subprocess.CalledProcessError):
        return []
    keys = (
        "wallpaperengine",
        "gnomepaper wallpaper",
        "linux-wallpaperengine",
        "gnomepaper-wallpaper",
        "wallpaper surface",
    )
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
    """Periodic light reassert — must never steal keyboard focus."""
    xids = _xids_for_pid(pid) or _xids_for_wallpaper_titles()
    for xid in xids:
        mark_xid_as_desktop(xid, geometry=geometry, full=False)
        _release_focus_if_wallpaper_active(xid)


def _release_focus_if_wallpaper_active(xid: int) -> None:
    """
    If the wallpaper is the X11 active window it will eat keyboard input.
    Release focus only in that case — never on every tick unconditionally.
    """
    if not shutil.which("xprop"):
        return
    try:
        out = subprocess.check_output(
            ["xprop", "-root", "_NET_ACTIVE_WINDOW"],
            text=True,
            errors="replace",
        )
    except (OSError, subprocess.CalledProcessError):
        return
    import re

    m = re.search(r"window id # (0x[0-9a-fA-F]+)", out)
    if not m:
        return
    active = m.group(1).lower()
    mine = hex(xid) if not str(xid).startswith("0x") else str(xid)
    # normalize
    try:
        active_i = int(active, 16)
    except ValueError:
        return
    if active_i != xid:
        return
    # Wallpaper stole focus — lower and drop X11 focus once
    id_str = str(xid)
    if shutil.which("xdotool"):
        _run(["xdotool", "windowlower", id_str])
        # Focus the root so Wayland apps can receive keys again
        _run(["xdotool", "windowfocus", "root"])
    log.debug("Released keyboard focus stolen by wallpaper %#x", xid)
