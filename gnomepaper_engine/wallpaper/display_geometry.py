"""Monitor geometries for wallpaper surfaces (prefer xrandr for X11/XWayland)."""

from __future__ import annotations

import logging
import re
import shutil
import subprocess

log = logging.getLogger(__name__)

# name, x, y, w, h  —  eDP-1 connected primary 3072x1728+0+0
_XRANDR_RE = re.compile(
    r"^(?P<name>\S+)\s+connected(?:\s+primary)?\s+"
    r"(?P<w>\d+)x(?P<h>\d+)\+(?P<x>\d+)\+(?P<y>\d+)",
    re.MULTILINE,
)


def monitor_geometries() -> list[tuple[int, int, int, int]]:
    """
    Return [(x, y, width, height), ...] for each connected monitor.

    Prefers ``xrandr`` (matches XWayland root coordinates used by LWE / GTK-X11).
    Falls back to Gdk, then a single 1920×1080 rect.
    """
    geos = _from_xrandr()
    if geos:
        log.info("Monitor geometry (xrandr): %s", geos)
        return geos

    geos = _from_gdk()
    if geos:
        log.info("Monitor geometry (Gdk): %s", geos)
        return geos

    log.warning("Falling back to default 1920x1080 geometry")
    return [(0, 0, 1920, 1080)]


def primary_geometry() -> tuple[int, int, int, int]:
    geos = monitor_geometries()
    return geos[0]


def _from_xrandr() -> list[tuple[int, int, int, int]]:
    if not shutil.which("xrandr"):
        return []
    try:
        out = subprocess.check_output(["xrandr", "--current"], text=True, errors="replace")
    except (OSError, subprocess.CalledProcessError) as exc:
        log.debug("xrandr failed: %s", exc)
        return []

    geos: list[tuple[int, int, int, int]] = []
    for m in _XRANDR_RE.finditer(out):
        geos.append(
            (
                int(m.group("x")),
                int(m.group("y")),
                int(m.group("w")),
                int(m.group("h")),
            )
        )
    return geos


def _from_gdk() -> list[tuple[int, int, int, int]]:
    try:
        import gi

        gi.require_version("Gdk", "4.0")
        from gi.repository import Gdk

        display = Gdk.Display.get_default()
        if display is None:
            return []
        monitors = display.get_monitors()
        geos: list[tuple[int, int, int, int]] = []
        for i in range(monitors.get_n_items()):
            mon = monitors.get_item(i)
            g = mon.get_geometry()
            scale = max(1, int(mon.get_scale_factor()))
            # On X11/XWayland wallpaper windows, physical/root coords usually
            # already match xrandr; keep Gdk logical size as last resort.
            geos.append((g.x, g.y, g.width * scale // scale, g.height))  # logical
            # Prefer unscaled logical — xrandr path is preferred above
            geos[-1] = (g.x, g.y, g.width, g.height)
        return geos
    except Exception as exc:
        log.debug("Gdk geometry failed: %s", exc)
        return []
