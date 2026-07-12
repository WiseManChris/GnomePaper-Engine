"""Application Settings dialog (session, appearance, downloads, scene engine)."""

from __future__ import annotations

import logging
from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, GLib, Gtk  # noqa: E402

from gnomepaper_engine import __version__  # noqa: E402
from gnomepaper_engine.autostart import is_autostart_enabled  # noqa: E402
from gnomepaper_engine.config import AppConfig  # noqa: E402
from gnomepaper_engine.ui.theme import (  # noqa: E402
    ACCENT_OPTIONS,
    THEME_OPTIONS,
    apply_theme,
)
from gnomepaper_engine.wallpaper.backends.lwe import (  # noqa: E402
    LWEDetection,
    auto_detect_lwe,
    find_install_script,
    launch_lwe_install,
    lwe_status,
)

log = logging.getLogger(__name__)


class SettingsDialog(Adw.PreferencesDialog):
    """Central settings: session, appearance, scene engine, downloads."""

    def __init__(
        self,
        config: AppConfig,
        *,
        on_changed: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(title="Settings")
        self._config = config
        self._on_changed = on_changed
        self._lwe_icon: Gtk.Image | None = None
        self._install_poll_id: int | None = None
        self._install_polls = 0
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

        # Scene engine (linux-wallpaperengine)
        scenes = Adw.PreferencesGroup(
            title="Scene engine",
            description=(
                "Live scenes need Almamu’s linux-wallpaperengine CLI — not the Steam "
                "“Wallpaper Engine” app by itself. GnomePaper auto-detects it by path "
                "and SHA-256 checksum."
            ),
        )
        page.add(scenes)

        det = self._run_detect()
        self._lwe_status_row = Adw.ActionRow(
            title="Auto-detect",
            subtitle=det.message,
        )
        self._lwe_icon = Gtk.Image.new_from_icon_name(
            "emblem-ok-symbolic" if det.found else "dialog-warning-symbolic"
        )
        self._lwe_status_row.add_prefix(self._lwe_icon)
        scenes.add(self._lwe_status_row)

        actions_row = Adw.ActionRow(
            title="Setup",
            subtitle="Re-scan known locations, or install the engine automatically",
        )
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        btn_box.set_valign(Gtk.Align.CENTER)

        self._redetect_btn = Gtk.Button(label="Re-detect")
        self._redetect_btn.add_css_class("flat")
        self._redetect_btn.set_tooltip_text(
            "Scan PATH and known install locations; verify with SHA-256 + CLI identity"
        )
        self._redetect_btn.connect("clicked", self._on_redetect)
        btn_box.append(self._redetect_btn)

        self._install_btn = Gtk.Button(label="Install scene engine")
        self._install_btn.add_css_class("suggested-action")
        self._install_btn.set_tooltip_text(
            "Build and install linux-wallpaperengine into ~/.local "
            "(opens a terminal for sudo if needed)"
        )
        self._install_btn.connect("clicked", self._on_install_lwe)
        btn_box.append(self._install_btn)

        if find_install_script() is None:
            self._install_btn.set_sensitive(False)
            self._install_btn.set_tooltip_text(
                "Install script not found. Keep the GnomePaper-Engine source tree "
                "(or re-run install.sh) so scripts/install_linux_wallpaperengine.sh is available."
            )

        actions_row.add_suffix(btn_box)
        scenes.add(actions_row)

        path_row = Adw.EntryRow(
            title="Custom binary path (optional)",
            text=self._config.lwe_binary_path or "",
        )
        path_row.set_show_apply_button(True)
        path_row.connect("apply", self._on_lwe_path)
        scenes.add(path_row)
        self._lwe_path_row = path_row

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

    # --- Scene engine helpers -------------------------------------------------

    def _run_detect(self, *, use_custom: bool = True) -> LWEDetection:
        explicit = None
        if use_custom:
            explicit = (self._config.lwe_binary_path or "").strip() or None
        return lwe_status(
            explicit,
            known_path=self._config.lwe_detected_path or None,
            known_sha256=self._config.lwe_binary_sha256 or None,
        )

    def _apply_detection(self, det: LWEDetection, *, persist: bool = True) -> None:
        self._lwe_status_row.set_subtitle(det.message)
        if self._lwe_icon is not None:
            self._lwe_icon.set_from_icon_name(
                "emblem-ok-symbolic" if det.found else "dialog-warning-symbolic"
            )
        if det.found and det.path is not None:
            self._config.lwe_detected_path = str(det.path)
            if det.sha256:
                self._config.lwe_binary_sha256 = det.sha256
        if persist:
            self._persist()

    def _on_redetect(self, *_a: object) -> None:
        self._lwe_status_row.set_subtitle("Scanning…")
        # Full rescan: ignore stale checksum cache if custom path empty
        explicit = (self._config.lwe_binary_path or "").strip() or None
        if explicit:
            det = auto_detect_lwe(explicit)
            if not det.found:
                det = auto_detect_lwe(None)
        else:
            det = auto_detect_lwe(None)
        self._apply_detection(det)
        if det.found:
            self._toast("Scene engine detected")
        else:
            self._toast("Scene engine not found — try Install")

    def _on_install_lwe(self, *_a: object) -> None:
        self._install_btn.set_sensitive(False)
        self._lwe_status_row.set_subtitle("Starting installer…")
        ok, msg, _proc = launch_lwe_install(prefer_terminal=True)
        if not ok:
            self._lwe_status_row.set_subtitle(msg)
            if self._lwe_icon is not None:
                self._lwe_icon.set_from_icon_name("dialog-warning-symbolic")
            self._install_btn.set_sensitive(True)
            self._toast("Could not start installer")
            return

        self._lwe_status_row.set_subtitle(
            "Installer running — complete it in the terminal, then wait for auto-detect…"
        )
        self._toast("Installer started")
        self._start_install_poll()

    def _start_install_poll(self) -> None:
        self._stop_install_poll()
        self._install_polls = 0
        # Poll every 5s for up to ~15 minutes (build can be long)
        self._install_poll_id = GLib.timeout_add_seconds(5, self._poll_after_install)

    def _stop_install_poll(self) -> None:
        if self._install_poll_id is not None:
            GLib.source_remove(self._install_poll_id)
            self._install_poll_id = None

    def _poll_after_install(self) -> bool:
        self._install_polls += 1
        det = auto_detect_lwe(None)
        if det.found:
            self._apply_detection(det)
            self._install_btn.set_sensitive(True)
            self._install_poll_id = None
            self._toast("Scene engine installed and verified")
            return GLib.SOURCE_REMOVE
        if self._install_polls >= 180:  # 15 min
            self._lwe_status_row.set_subtitle(
                "Still not detected. Finish the terminal install, then click Re-detect."
            )
            if self._lwe_icon is not None:
                self._lwe_icon.set_from_icon_name("dialog-warning-symbolic")
            self._install_btn.set_sensitive(True)
            self._install_poll_id = None
            return GLib.SOURCE_REMOVE
        if self._install_polls % 6 == 0:
            mins = (self._install_polls * 5) // 60
            self._lwe_status_row.set_subtitle(
                f"Waiting for install… ({mins}m) — building can take a while"
            )
        return GLib.SOURCE_CONTINUE

    def _toast(self, message: str) -> None:
        try:
            toast = Adw.Toast.new(message)
            toast.set_timeout(3)
            self.add_toast(toast)
        except Exception:
            log.debug("toast unavailable: %s", message)

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

    def _on_lwe_path(self, row: Adw.EntryRow) -> None:
        self._config.lwe_binary_path = row.get_text().strip()
        det = self._run_detect(use_custom=True)
        # If custom path bad, still try auto so user sees a useful message
        if not det.found and self._config.lwe_binary_path:
            auto = auto_detect_lwe(None)
            if auto.found:
                det = LWEDetection(
                    found=False,
                    path=None,
                    sha256="",
                    verified=False,
                    message=(
                        f"Custom path invalid. Auto-detect would use: {auto.path} "
                        f"(sha256:{auto.short_sha}…)"
                    ),
                )
        self._apply_detection(det)
