"""Application Settings dialog (background, autostart, downloads)."""

from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gtk  # noqa: E402

from gnomepaper_engine.autostart import is_autostart_enabled  # noqa: E402
from gnomepaper_engine.config import AppConfig  # noqa: E402


class SettingsDialog(Adw.PreferencesDialog):
    """Central settings for v1.0 desktop integration."""

    def __init__(
        self,
        config: AppConfig,
        *,
        on_changed: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(title="Settings")
        self._config = config
        self._on_changed = on_changed
        self._build()

    def _build(self) -> None:
        page = Adw.PreferencesPage(title="General", icon_name="preferences-system-symbolic")
        self.add(page)

        # Session
        session = Adw.PreferencesGroup(
            title="Session",
            description="Keep GnomePaper running with your wallpaper.",
        )
        page.add(session)

        self._bg_row = Adw.SwitchRow(
            title="Keep running in background",
            subtitle="Closing the window hides it instead of quitting (wallpaper keeps playing)",
            active=self._config.close_to_background,
        )
        self._bg_row.connect("notify::active", self._on_bg)
        session.add(self._bg_row)

        self._start_min_row = Adw.SwitchRow(
            title="Start minimized",
            subtitle="When launched, open in the background (e.g. at login)",
            active=self._config.start_minimized,
        )
        self._start_min_row.connect("notify::active", self._on_start_min)
        session.add(self._start_min_row)

        self._restore_row = Adw.SwitchRow(
            title="Restore last wallpaper on launch",
            subtitle="Re-apply the last wallpaper when the app starts",
            active=self._config.restore_last_on_launch,
        )
        self._restore_row.connect("notify::active", self._on_restore)
        session.add(self._restore_row)

        # Startup
        startup = Adw.PreferencesGroup(
            title="Startup",
            description="Launch GnomePaper when you log in to GNOME.",
        )
        page.add(startup)

        self._autostart_row = Adw.SwitchRow(
            title="Launch at login",
            subtitle="Creates an entry in ~/.config/autostart/",
            active=is_autostart_enabled() or self._config.launch_at_login,
        )
        self._autostart_row.connect("notify::active", self._on_autostart)
        startup.add(self._autostart_row)

        # Downloads
        dl = Adw.PreferencesGroup(
            title="Workshop downloads",
            description="SteamCMD direct download (account must own Wallpaper Engine).",
        )
        page.add(dl)

        self._steamcmd_row = Adw.SwitchRow(
            title="Prefer direct download (SteamCMD)",
            subtitle="Skip the Subscribe button when possible",
            active=self._config.prefer_steamcmd_download,
        )
        self._steamcmd_row.connect("notify::active", self._on_steamcmd)
        dl.add(self._steamcmd_row)

        # About note
        about = Adw.PreferencesGroup(title="About")
        page.add(about)
        note = Adw.ActionRow(
            title="GnomePaper Engine 1.0",
            subtitle="Wallpaper Engine for GNOME — requires owning WE on Steam",
        )
        about.add(note)

    def _persist(self) -> None:
        self._config.save()
        if self._on_changed is not None:
            self._on_changed()

    def _on_bg(self, row: Adw.SwitchRow, *_a: object) -> None:
        self._config.close_to_background = row.get_active()
        self._persist()

    def _on_start_min(self, row: Adw.SwitchRow, *_a: object) -> None:
        self._config.start_minimized = row.get_active()
        self._persist()

    def _on_restore(self, row: Adw.SwitchRow, *_a: object) -> None:
        self._config.restore_last_on_launch = row.get_active()
        self._persist()

    def _on_autostart(self, row: Adw.SwitchRow, *_a: object) -> None:
        from gnomepaper_engine.autostart import set_autostart

        enabled = row.get_active()
        self._config.launch_at_login = enabled
        set_autostart(enabled)
        self._persist()

    def _on_steamcmd(self, row: Adw.SwitchRow, *_a: object) -> None:
        self._config.prefer_steamcmd_download = row.get_active()
        self._persist()
