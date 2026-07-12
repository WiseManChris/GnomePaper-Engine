"""
Desktop video player process — full-screen wallpaper surface(s).

Uses GTK3 DESKTOP hints + X11 resize so the video covers each monitor
(not a small floating player window).
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys

log = logging.getLogger(__name__)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="GnomePaper desktop video surface")
    p.add_argument("--video", required=True, help="Path to video file")
    p.add_argument("--mute", action="store_true", default=False)
    p.add_argument("--volume", type=float, default=0.0, help="0.0–1.0")
    return p


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = _build_parser().parse_args(argv)

    video = os.path.abspath(args.video)
    if not os.path.isfile(video):
        log.error("Video not found: %s", video)
        return 1

    # Force X11/XWayland for DESKTOP window type under GNOME
    if os.environ.get("WAYLAND_DISPLAY") or os.environ.get("XDG_SESSION_TYPE") == "wayland":
        os.environ.pop("WAYLAND_DISPLAY", None)
        os.environ.pop("WAYLAND_SOCKET", None)
        os.environ.setdefault("DISPLAY", ":0")
        os.environ["XDG_SESSION_TYPE"] = "x11"
        os.environ["GDK_BACKEND"] = "x11"

    import gi

    gi.require_version("Gtk", "3.0")
    gi.require_version("Gdk", "3.0")
    gi.require_version("Gst", "1.0")
    gi.require_version("GstVideo", "1.0")

    from gi.repository import Gdk, GLib, Gst, Gtk

    from gnomepaper_engine.wallpaper.display_geometry import monitor_geometries
    from gnomepaper_engine.wallpaper.x11_desktop import mark_xid_as_desktop

    Gst.init(None)

    volume = 0.0 if args.mute else max(0.0, min(1.0, args.volume if args.volume > 0 else 0.5))
    geos = monitor_geometries()
    log.info("Using geometries: %s", geos)

    class MonitorWallpaper(Gtk.Window):
        def __init__(
            self,
            app: Gtk.Application,
            rect: tuple[int, int, int, int],
            path: str,
        ) -> None:
            super().__init__(type=Gtk.WindowType.TOPLEVEL)
            self.set_application(app)
            self.set_title("GnomePaper Wallpaper")
            self.set_decorated(False)
            self.set_resizable(True)
            self.set_keep_below(True)
            self.set_skip_taskbar_hint(True)
            self.set_skip_pager_hint(True)
            self.set_accept_focus(False)
            self.set_focus_on_map(False)
            self.stick()
            # NORMAL (not DESKTOP): GNOME hides the top bar for DESKTOP/fullscreen
            self.set_type_hint(Gdk.WindowTypeHint.NORMAL)
            self.set_decorated(False)

            # rect is X11/root pixels from xrandr. GTK may use a scale factor on
            # XWayland, so we convert to logical units for GTK APIs and keep the
            # physical rect only for wmctrl/xdotool.
            self._geo = rect  # physical (xrandr)
            x, y, w, h = rect
            self._scale = max(1, int(self.get_scale_factor()))
            lw, lh = max(1, w // self._scale), max(1, h // self._scale)
            lx, ly = x // self._scale, y // self._scale
            self._w = lw
            self._h = lh
            self.move(lx, ly)
            self.set_default_size(lw, lh)
            self.resize(lw, lh)
            # Exact full-screen coverage is enforced via X11 below.

            self._player = Gst.ElementFactory.make("playbin", None)
            if self._player is None:
                raise RuntimeError("GStreamer playbin unavailable")

            uri = Gst.filename_to_uri(path)
            self._player.set_property("uri", uri)
            self._player.set_property("volume", volume)

            sink = Gst.ElementFactory.make("gtksink", None)
            if sink is None:
                raise RuntimeError("GStreamer gtksink unavailable")
            try:
                sink.set_property("force-aspect-ratio", False)
            except Exception:
                pass
            self._player.set_property("video-sink", sink)

            widget = sink.get_property("widget")
            widget.set_hexpand(True)
            widget.set_vexpand(True)
            widget.set_size_request(lw, lh)
            self.add(widget)

            bus = self._player.get_bus()
            bus.add_signal_watch()
            bus.connect("message", self._on_bus)

            self.connect("realize", self._on_realize)
            self.connect("map-event", self._on_map)
            self.connect("delete-event", lambda *_: True)

            GLib.timeout_add_seconds(1, self._reassert_layer)
            GLib.timeout_add(500, self._fit_once)
            log.info("Video wallpaper surface %dx%d+%d+%d", w, h, x, y)

        def start(self) -> None:
            self.show_all()
            self._player.set_state(Gst.State.PLAYING)

        def stop(self) -> None:
            self._player.set_state(Gst.State.NULL)

        def _fit_x11(self) -> None:
            gdk_win = self.get_window()
            if gdk_win is None:
                return
            try:
                xid = int(gdk_win.get_xid())
                # Physical pixels only — do not call GTK resize with xrandr sizes
                # (HiDPI would double them again).
                mark_xid_as_desktop(xid, geometry=self._geo)
                gdk_win.lower()
            except Exception as exc:
                log.debug("fit_x11 failed: %s", exc)

        def _on_realize(self, *_args: object) -> None:
            self._fit_x11()
            gdk_win = self.get_window()
            if gdk_win is not None:
                try:
                    gdk_win.set_decorations(0)
                    gdk_win.set_functions(0)
                    gdk_win.lower()
                except Exception:
                    pass

        def _on_map(self, *_args: object) -> bool:
            self._fit_x11()
            return False

        def _fit_once(self) -> bool:
            self._fit_x11()
            return False  # one-shot

        def _reassert_layer(self) -> bool:
            self._fit_x11()
            return True

        def _on_bus(self, _bus: Gst.Bus, message: Gst.Message) -> None:
            t = message.type
            if t == Gst.MessageType.EOS:
                self._player.seek_simple(
                    Gst.Format.TIME,
                    Gst.SeekFlags.FLUSH | Gst.SeekFlags.KEY_UNIT,
                    0,
                )
            elif t == Gst.MessageType.ERROR:
                err, debug = message.parse_error()
                log.error("GStreamer error: %s (%s)", err, debug)
                self._player.set_state(Gst.State.NULL)

    class DesktopApp(Gtk.Application):
        def __init__(self, path: str) -> None:
            super().__init__(application_id="io.github.gnomepaper.DesktopPlayer")
            self._path = path
            self._windows: list[MonitorWallpaper] = []

        def do_activate(self) -> None:  # noqa: N802
            if self._windows:
                for w in self._windows:
                    w.present()
                return

            for rect in geos:
                win = MonitorWallpaper(self, rect, self._path)
                self._windows.append(win)
                win.start()

        def do_shutdown(self) -> None:  # noqa: N802
            for w in self._windows:
                w.stop()
            Gtk.Application.do_shutdown(self)

    app = DesktopApp(video)

    def _handle_signal(signum: int, _frame: object) -> None:
        log.info("Signal %s — stopping desktop player", signum)
        app.quit()

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    return app.run([sys.argv[0]])


if __name__ == "__main__":
    raise SystemExit(main())
