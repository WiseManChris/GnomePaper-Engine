"""Adw.Application wiring: scan Steam, drive UI, apply wallpapers."""

from __future__ import annotations

import logging
import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gio, GLib  # noqa: E402

from gnomepaper_engine import __app_id__, __app_name__, __version__  # noqa: E402
from gnomepaper_engine.config import AppConfig  # noqa: E402
from gnomepaper_engine.steam.library import WallpaperLibrary, scan_library  # noqa: E402
from gnomepaper_engine.steam.models import WallpaperItem  # noqa: E402
from gnomepaper_engine.steam.paths import discover_steam_installs  # noqa: E402
from gnomepaper_engine.ui.main_window import MainWindow  # noqa: E402
from gnomepaper_engine.wallpaper.manager import WallpaperManager  # noqa: E402

log = logging.getLogger(__name__)


class GnomePaperApplication(Adw.Application):
    def __init__(self) -> None:
        super().__init__(
            application_id=__app_id__,
            flags=Gio.ApplicationFlags.FLAGS_NONE,
        )
        self.config = AppConfig.load()
        self.library = WallpaperLibrary()
        self.manager = WallpaperManager(self.config)
        self.window: MainWindow | None = None

    def do_activate(self) -> None:  # noqa: N802 — GObject override
        if self.window is None:
            self.window = MainWindow(
                self,
                on_refresh=self.refresh_library,
                on_apply=self.apply_wallpaper,
                on_stop=self.stop_wallpaper,
            )
            self.window.connect("close-request", self._on_close)
        self.window.present()
        # Initial scan on idle so the window appears immediately
        GLib.idle_add(self.refresh_library)

    def do_startup(self) -> None:  # noqa: N802
        Adw.Application.do_startup(self)
        self._install_actions()

    def _install_actions(self) -> None:
        quit_action = Gio.SimpleAction.new("quit", None)
        quit_action.connect("activate", lambda *_: self.quit())
        self.add_action(quit_action)
        self.set_accels_for_action("app.quit", ["<primary>q"])

        about_action = Gio.SimpleAction.new("about", None)
        about_action.connect("activate", self._on_about)
        self.add_action(about_action)

    def refresh_library(self) -> bool:
        assert self.window is not None
        installs = discover_steam_installs(self.config.steam_library_paths)
        if not installs:
            self.window.set_status("Steam not found")
            self.window.set_items([])
            self.window.show_message(
                "Could not find a Steam install. Install Steam or add a library path in config.",
                error=True,
            )
            return GLib.SOURCE_REMOVE

        kinds = ", ".join(sorted({i.kind for i in installs}))
        self.window.set_status(f"Scanning Steam ({kinds})…")

        self.library = scan_library(self.config.steam_library_paths)
        self.window.set_items(self.library.items)

        if len(self.library) == 0:
            self.window.set_status(
                f"Steam linked ({len(installs)} install(s)) · 0 wallpapers"
            )
            self.window.show_message(
                "Steam found, but no Wallpaper Engine workshop items yet.",
                error=False,
            )
        else:
            self.window.set_status(
                f"Steam linked · {len(self.library)} wallpaper(s)"
            )
        return GLib.SOURCE_REMOVE

    def apply_wallpaper(self, item: WallpaperItem) -> None:
        assert self.window is not None
        result = self.manager.apply(item)
        self.window.show_message(result.message, error=not result.ok)
        if result.ok:
            self.window.set_status(f"Active: {item.title}")

    def stop_wallpaper(self) -> None:
        assert self.window is not None
        self.manager.stop()
        self.window.show_message("Stopped wallpaper playback")
        n = len(self.library)
        self.window.set_status(f"Steam linked · {n} wallpaper(s)" if n else "Ready")

    def _on_about(self, *_args: object) -> None:
        from gi.repository import Gtk

        about = Adw.AboutDialog(
            application_name=__app_name__,
            application_icon="preferences-desktop-wallpaper",
            developer_name="GnomePaper Engine contributors",
            version=__version__,
            comments=(
                "Bring Steam Wallpaper Engine wallpapers to GNOME desktops "
                "with a native Adwaita experience."
            ),
            license_type=Gtk.License.MIT_X11,
        )
        if self.window is not None:
            about.present(self.window)

    def _on_close(self, *_args: object) -> bool:
        self.manager.stop()
        return False  # allow close


def run(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    app = GnomePaperApplication()
    return app.run(argv if argv is not None else sys.argv)
