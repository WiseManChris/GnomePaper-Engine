"""Application Settings dialog (session, appearance, downloads)."""

from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gtk  # noqa: E402

from gnomepaper_engine import __version__  # noqa: E402
from gnomepaper_engine.autostart import is_autostart_enabled  # noqa: E402
from gnomepaper_engine.config import AppConfig  # noqa: E402
from gnomepaper_engine.ui.theme import (  # noqa: E402
    ACCENT_OPTIONS,
    THEME_OPTIONS,
    apply_theme,
)


class SettingsDialog(Adw.PreferencesDialog):
    """Central settings: session, appearance, downloads."""

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

        # Appearance
        appearance = Adw.PreferencesGroup(
            title="Appearance",
            description="Theme and accent color for GnomePaper only.",
        )
        page.add(appearance)

        theme_row = Adw.ComboRow(title="Theme", subtitle="Light, dark, or pitch black OLED")
        theme_model = Gtk.StringList.new([label for _key, label in THEME_OPTIONS])
        theme_row.set_model(theme_model)
        theme_keys = [key for key, _label in THEME_OPTIONS]
        try:
            theme_row.set_selected(theme_keys.index(self._config.ui_theme))
        except ValueError:
            theme_row.set_selected(0)
        theme_row.connect("notify::selected", self._on_theme)
        appearance.add(theme_row)
        self._theme_keys = theme_keys

        accent_row = Adw.ActionRow(
            title="Accent color",
            subtitle="Highlights, switches, and primary buttons",
        )
        accent_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        accent_box.set_valign(Gtk.Align.CENTER)
        self._accent_buttons: dict[str, Gtk.CheckButton] = {}
        group_leader: Gtk.CheckButton | None = None
        for key, label, hex_color in ACCENT_OPTIONS:
            btn = Gtk.CheckButton(label=label)
            btn.add_css_class("accent-choice")
            # color swatch via tooltip
            btn.set_tooltip_text(f"{label} ({hex_color})")
            if group_leader is None:
                group_leader = btn
            else:
                btn.set_group(group_leader)
            if key == self._config.accent_color:
                btn.set_active(True)
            btn.connect("toggled", self._on_accent_toggled, key)
            self._accent_buttons[key] = btn
            accent_box.append(btn)
        accent_row.add_suffix(accent_box)
        appearance.add(accent_row)

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
            title=f"GnomePaper Engine {__version__}",
            subtitle="Any GNOME desktop · by WiseManChris · requires owning WE on Steam",
        )
        about.add(note)

    def _persist(self) -> None:
        self._config.save()
        if self._on_changed is not None:
            self._on_changed()

    def _on_theme(self, row: Adw.ComboRow, *_a: object) -> None:
        idx = row.get_selected()
        if idx < 0 or idx >= len(self._theme_keys):
            return
        self._config.ui_theme = self._theme_keys[idx]
        apply_theme(theme=self._config.ui_theme, accent=self._config.accent_color)
        self._persist()

    def _on_accent_toggled(self, button: Gtk.CheckButton, key: str) -> None:
        if not button.get_active():
            return
        self._config.accent_color = key
        apply_theme(theme=self._config.ui_theme, accent=self._config.accent_color)
        self._persist()

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
