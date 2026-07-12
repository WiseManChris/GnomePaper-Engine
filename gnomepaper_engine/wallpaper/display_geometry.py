"""Monitor geometries for wallpaper surfaces — respect GNOME panel (workarea)."""

from __future__ import annotations

import logging
import re
import shutil
import subprocess

log = logging.getLogger(__name__)

# eDP-1 connected primary 3072x1728+0+0
_XRANDR_RE = re.compile(
    r"^(?P<name>\S+)\s+connected(?:\s+primary)?\s+"
    r"(?P<w>\d+)x(?P<h>\d+)\+(?P<x>\d+)\+(?P<y>\d+)",
    re.MULTILINE,
)


def monitor_geometries() -> list[tuple[int, int, int, int]]:
    """
    Usable wallpaper rectangles [(x, y, width, height), ...].

    Uses the X11/XWayland workarea when available so the GNOME top bar
    (clock / control center) is never covered by scene/video surfaces.
    Always enforces a minimum top inset — never returns y=0 full-height.
    """
    full = _from_xrandr()
    work = _from_net_workarea()

    geos: list[tuple[int, int, int, int]] = []
    if full and work:
        geos = _intersect_monitors_with_workarea(full, work)
        if geos:
            log.info("Wallpaper geometry (workarea-safe): %s", geos)
    if not geos and work:
        geos = work
        log.info("Wallpaper geometry (workarea only): %s", geos)
    if not geos and full:
        geos = _heuristic_panel_inset(full)
        log.info("Wallpaper geometry (xrandr + panel inset): %s", geos)
    if not geos:
        geos = _from_gdk()
        if geos:
            log.info("Wallpaper geometry (Gdk): %s", geos)
    if not geos:
        log.warning("Falling back to default geometry")
        geos = [(0, 32, 1920, 1048)]

    # Final hard clamp — never cover the top panel band
    return [_ensure_panel_gap(g, full) for g in geos]


def _ensure_panel_gap(
    geo: tuple[int, int, int, int],
    full_monitors: list[tuple[int, int, int, int]] | None = None,
) -> tuple[int, int, int, int]:
    """Guarantee wallpaper does not start under the GNOME top bar."""
    x, y, w, h = geo
    min_top = 32
    # If this rect matches a full monitor height from y=0, force inset
    if full_monitors:
        for fx, fy, fw, fh in full_monitors:
            if abs(x - fx) < 4 and abs(w - fw) < 4 and abs(h - fh) < 8 and y <= fy + 4:
                y = fy + min_top
                h = max(1, fh - min_top)
                return (x, y, w, h)
    if y < min_top:
        delta = min_top - y
        y = min_top
        h = max(1, h - delta)
    return (x, y, w, h)


def primary_geometry() -> tuple[int, int, int, int]:
    return monitor_geometries()[0]


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


def _from_net_workarea() -> list[tuple[int, int, int, int]]:
    """Parse _NET_WORKAREA from the root window (x,y,w,h repeating)."""
    if not shutil.which("xprop"):
        return []
    try:
        out = subprocess.check_output(
            ["xprop", "-root", "_NET_WORKAREA"],
            text=True,
            errors="replace",
        )
    except (OSError, subprocess.CalledProcessError):
        return []

    # _NET_WORKAREA(CARDINAL) = 0, 64, 3072, 1664, 0, 64, 3072, 1664
    m = re.search(r"=\s*([0-9,\s]+)", out)
    if not m:
        return []
    nums = [int(x.strip()) for x in m.group(1).split(",") if x.strip().isdigit()]
    rects: list[tuple[int, int, int, int]] = []
    for i in range(0, len(nums) - 3, 4):
        x, y, w, h = nums[i], nums[i + 1], nums[i + 2], nums[i + 3]
        if w > 0 and h > 0:
            rects.append((x, y, w, h))
    # De-dupe identical desktop copies
    unique: list[tuple[int, int, int, int]] = []
    for r in rects:
        if r not in unique:
            unique.append(r)
    return unique


def _intersect(
    a: tuple[int, int, int, int], b: tuple[int, int, int, int]
) -> tuple[int, int, int, int] | None:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    x1 = max(ax, bx)
    y1 = max(ay, by)
    x2 = min(ax + aw, bx + bw)
    y2 = min(ay + ah, by + bh)
    if x2 <= x1 or y2 <= y1:
        return None
    return (x1, y1, x2 - x1, y2 - y1)


def _intersect_monitors_with_workarea(
    monitors: list[tuple[int, int, int, int]],
    workareas: list[tuple[int, int, int, int]],
) -> list[tuple[int, int, int, int]]:
    """Clamp each monitor rect to the union of usable workarea."""
    # Combine workareas into one bounding usable region (typical single desktop)
    if not workareas:
        return monitors
    # Prefer intersecting each monitor with every workarea and keep largest
    result: list[tuple[int, int, int, int]] = []
    for mon in monitors:
        best: tuple[int, int, int, int] | None = None
        best_area = 0
        for wa in workareas:
            inter = _intersect(mon, wa)
            if inter is None:
                continue
            area = inter[2] * inter[3]
            if area > best_area:
                best = inter
                best_area = area
        if best is not None:
            result.append(best)
        else:
            # No intersection (rare) — apply top inset from first workarea
            top = workareas[0][1]
            x, y, w, h = mon
            result.append((x, y + top, w, max(1, h - top)))
    return result


def _heuristic_panel_inset(
    monitors: list[tuple[int, int, int, int]],
) -> list[tuple[int, int, int, int]]:
    """Fallback ~top panel only when workarea is missing."""
    out: list[tuple[int, int, int, int]] = []
    for x, y, w, h in monitors:
        # ~32 CSS px; on 200% scale XWayland often reports ~64 already in workarea
        top = max(28, min(80, h // 40))
        out.append((x, y + top, w, max(1, h - top)))
    return out


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
            geos.append((g.x, g.y, g.width, g.height))
        return geos
    except Exception as exc:
        log.debug("Gdk geometry failed: %s", exc)
        return []
