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
from gnomepaper_engine.steam.ownership import (  # noqa: E402
    ownership_status_message,
    wallpaper_engine_owned,
)
from gnomepaper_engine.steam.paths import discover_steam_installs  # noqa: E402
from gnomepaper_engine.tray import TrayIcon  # noqa: E402
from gnomepaper_engine.ui.main_window import MainWindow  # noqa: E402
from gnomepaper_engine.ui.settings import SettingsDialog  # noqa: E402
from gnomepaper_engine.wallpaper.manager import WallpaperManager  # noqa: E402

log = logging.getLogger(__name__)


class GnomePaperApplication(Adw.Application):
    def __init__(self, *, start_background: bool = False) -> None:
        super().__init__(
            application_id=__app_id__,
            flags=Gio.ApplicationFlags.FLAGS_NONE,
        )
        self.config = AppConfig.load()
        self.library = WallpaperLibrary()
        self.manager = WallpaperManager(self.config)
        self.window: MainWindow | None = None
        self._tray: TrayIcon | None = None
        self._start_background = start_background or self.config.start_minimized
        self._holding = False

    def do_startup(self) -> None:  # noqa: N802
        Adw.Application.do_startup(self)
        self._install_actions()
        self._setup_tray()

    def do_activate(self) -> None:  # noqa: N802
        if self.window is None:
            self.window = MainWindow(
                self,
                on_refresh=self.refresh_library,
                on_apply=self.apply_wallpaper,
                on_stop=self.stop_wallpaper,
                mute_audio=self.config.mute_audio,
                audio_volume=self.config.audio_volume,
                mouse_interaction=self.config.mouse_interaction,
                target_fps=self.config.target_fps,
                steam_username=self.config.steam_username,
                steam_linked=self.config.steam_linked,
                steam_persona_name=self.config.steam_persona_name,
                steam_avatar_path=self.config.steam_avatar_path,
                prefer_steamcmd_download=self.config.prefer_steamcmd_download,
                we_owned=wallpaper_engine_owned(self.config.steam_library_paths),
                on_mute_changed=self._on_mute_changed,
                on_volume_changed=self._on_volume_changed,
                on_mouse_changed=self._on_mouse_changed,
                on_fps_changed=self._on_fps_changed,
                on_steam_username_changed=self._on_steam_username_changed,
                on_steam_linked_changed=self._on_steam_linked_changed,
                on_steam_profile_changed=self._on_steam_profile_changed,
                on_prefer_steamcmd_changed=self._on_prefer_steamcmd_changed,
            )
            self.window.connect("close-request", self._on_close)

        if self._start_background:
            # First activation after launch with --background / start_minimized
            self._start_background = False
            self._enter_background()
        else:
            self._show_window()

        GLib.idle_add(self.refresh_library)
        GLib.idle_add(self._check_ownership)
        GLib.idle_add(self._maybe_restore_wallpaper)

    def _install_actions(self) -> None:
        quit_action = Gio.SimpleAction.new("quit", None)
        quit_action.connect("activate", lambda *_: self._quit_fully())
        self.add_action(quit_action)
        self.set_accels_for_action("app.quit", ["<primary>q"])

        about_action = Gio.SimpleAction.new("about", None)
        about_action.connect("activate", self._on_about)
        self.add_action(about_action)

        settings_action = Gio.SimpleAction.new("settings", None)
        settings_action.connect("activate", self._on_settings)
        self.add_action(settings_action)
        self.set_accels_for_action("app.settings", ["<primary>comma"])

        show_action = Gio.SimpleAction.new("show", None)
        show_action.connect("activate", lambda *_: self._show_window())
        self.add_action(show_action)

    def _setup_tray(self) -> None:
        if not self.config.close_to_background:
            return
        self._tray = TrayIcon(
            on_show=self._show_window,
            on_quit=self._quit_fully,
            on_stop_wallpaper=self.stop_wallpaper,
        )
        if self._tray.available:
            self._tray.set_visible(True)

    def _enter_background(self) -> None:
        """Hide UI but keep process + wallpaper alive."""
        if self.window is not None:
            self.window.set_visible(False)
        if not self._holding:
            self.hold()
            self._holding = True
        if self._tray is not None and self._tray.available:
            self._tray.set_visible(True)
        log.info("Running in background")

    def _show_window(self) -> None:
        if self.window is None:
            return
        self.window.set_visible(True)
        self.window.present()
        if self._holding:
            self.release()
            self._holding = False

    def _quit_fully(self) -> None:
        """Stop wallpaper and quit the process."""
        try:
            self.manager.stop()
        except Exception:
            pass
        if self._holding:
            self.release()
            self._holding = False
        self.quit()

    def _on_close(self, *_args: object) -> bool:
        """Window close: background or quit."""
        if self.config.close_to_background:
            self._enter_background()
            if self.window is not None:
                self.window.show_message(
                    "Still running in the background. Open from the app menu or tray."
                )
            return True  # block destroy
        self.manager.stop()
        return False

    def _on_settings(self, *_args: object) -> None:
        dialog = SettingsDialog(self.config, on_changed=self._on_settings_changed)
        if self.window is not None:
            dialog.present(self.window)
        else:
            dialog.present()

    def _on_settings_changed(self) -> None:
        # Re-sync manager config; recreate tray if background toggled on
        self.manager.config = self.config
        if self.config.close_to_background and self._tray is None:
            self._setup_tray()
        if self._tray is not None:
            self._tray.set_visible(self.config.close_to_background)

    def _maybe_restore_wallpaper(self) -> bool:
        if not self.config.restore_last_on_launch:
            return GLib.SOURCE_REMOVE
        wid = self.config.last_wallpaper_id
        if not wid:
            return GLib.SOURCE_REMOVE
        if self.manager.is_running:
            return GLib.SOURCE_REMOVE
        if not wallpaper_engine_owned(self.config.steam_library_paths):
            return GLib.SOURCE_REMOVE
        # Library may still be loading — try after scan via delayed call
        GLib.timeout_add_seconds(2, self._restore_last_wallpaper)
        return GLib.SOURCE_REMOVE

    def _restore_last_wallpaper(self) -> bool:
        wid = self.config.last_wallpaper_id
        if not wid or self.manager.is_running:
            return GLib.SOURCE_REMOVE
        item = self.library.by_id(wid)
        if item is None:
            # Rescan once more
            self.library = scan_library(self.config.steam_library_paths)
            item = self.library.by_id(wid)
        if item is None:
            log.info("Last wallpaper %s not found on disk", wid)
            return GLib.SOURCE_REMOVE
        log.info("Restoring last wallpaper: %s", item.title)
        self.apply_wallpaper(item)
        return GLib.SOURCE_REMOVE

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
            self.window.show_message(
                "No installed wallpapers yet — try the Workshop tab.",
                error=False,
            )
        else:
            self.window.show_message(
                f"Library ready · {len(self.library)} wallpaper(s)",
                error=False,
            )
            if self.config.last_wallpaper_id:
                last = self.library.by_id(self.config.last_wallpaper_id)
                if last is not None and self.manager.is_running:
                    self.window.set_active_wallpaper(last.title)
        return GLib.SOURCE_REMOVE

    def stop_wallpaper(self) -> None:
        self.manager.stop()
        if self.window is not None:
            self.window.show_message("Stopped wallpaper playback")
            self.window.set_active_wallpaper(None)
            n = len(self.library)
            self.window.set_status(
                f"Steam linked · {n} wallpaper(s)" if n else "Ready"
            )

    def apply_wallpaper(self, item: WallpaperItem) -> None:
        if not wallpaper_engine_owned(self.config.steam_library_paths):
            if self.window is not None:
                self.window.show_message(
                    "Wallpaper Engine must be installed (own it on Steam) to use GnomePaper.",
                    error=True,
                )
            return
        self.manager.config = self.config
        result = self.manager.apply(item)
        if self.window is not None:
            self.window.show_message(result.message, error=not result.ok)
            if result.ok:
                self.window.set_status(f"Active: {item.title}")
                self.window.set_active_wallpaper(item.title)
            elif "Preview set" in result.message:
                self.window.set_active_wallpaper(f"{item.title} (static preview)")

    def _on_mute_changed(self, muted: bool) -> None:
        self.config.mute_audio = muted
        self.config.save()
        if self.window is not None:
            self.window.show_message(
                f"Audio {'muted' if muted else 'unmuted'}. Re-apply to take effect."
            )

    def _on_volume_changed(self, volume: int) -> None:
        self.config.audio_volume = max(0, min(100, volume))
        self.config.save()

    def _on_mouse_changed(self, enabled: bool) -> None:
        self.config.mouse_interaction = enabled
        self.config.save()
        if self.window is not None:
            self.window.show_message(
                f"Mouse effects {'on' if enabled else 'off'}. Re-apply to take effect."
            )

    def _on_fps_changed(self, fps: int) -> None:
        self.config.target_fps = max(15, min(60, fps))
        self.config.save()

    def _on_steam_username_changed(self, username: str) -> None:
        self.config.steam_username = username.strip()
        if self.config.steam_linked:
            self.config.steam_linked = False
            self.config.steam_persona_name = ""
            self.config.steam_id64 = ""
            self.config.steam_avatar_path = ""
        self.config.save()

    def _on_steam_linked_changed(self, linked: bool) -> None:
        self.config.steam_linked = linked
        if not linked:
            self.config.steam_persona_name = ""
            self.config.steam_id64 = ""
            self.config.steam_avatar_path = ""
        self.config.save()

    def _on_steam_profile_changed(
        self, persona: str, steam_id64: str, avatar_path: str
    ) -> None:
        self.config.steam_persona_name = persona
        self.config.steam_id64 = steam_id64
        self.config.steam_avatar_path = avatar_path
        self.config.save()

    def _on_prefer_steamcmd_changed(self, prefer: bool) -> None:
        self.config.prefer_steamcmd_download = prefer
        self.config.save()

    def _check_ownership(self) -> bool:
        if not wallpaper_engine_owned(self.config.steam_library_paths):
            if self.window is not None and self.window.get_visible():
                self.window.show_message(
                    ownership_status_message(self.config.steam_library_paths),
                    error=True,
                )
        return GLib.SOURCE_REMOVE

    def _on_about(self, *_args: object) -> None:
        from gi.repository import Gtk

        about = Adw.AboutDialog(
            application_name=__app_name__,
            application_icon="preferences-desktop-wallpaper",
            developer_name="GnomePaper Engine contributors",
            version=__version__,
            comments=(
                "Bring Steam Wallpaper Engine wallpapers to GNOME desktops "
                "with a native Adwaita experience. Requires owning Wallpaper Engine on Steam."
            ),
            license_type=Gtk.License.MIT_X11,
            website="https://github.com/christianl/GnomePaper-Engine",
        )
        if self.window is not None:
            about.present(self.window)


def run(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    raw = list(sys.argv if argv is None else argv)
    # Support both full argv and args-only lists
    if raw and not raw[0].endswith("gnomepaper_engine") and "gnomepaper" not in raw[0]:
        # args only
        args = raw
        full = [sys.argv[0], *raw]
    else:
        full = raw if raw else [sys.argv[0]]
        args = full[1:]

    start_bg = "--background" in args or "-b" in args
    cleaned = [full[0]] + [a for a in args if a not in ("--background", "-b")]

    app = GnomePaperApplication(start_background=start_bg)
    return app.run(cleaned)
