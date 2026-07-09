"""Optional system tray (StatusNotifier) for background mode."""

from __future__ import annotations

import logging
from collections.abc import Callable

log = logging.getLogger(__name__)


class TrayIcon:
    """
    Best-effort AppIndicator tray.

    GNOME needs an AppIndicator extension for this to show; if unavailable,
    background mode still works via hide-window + app.hold().
    """

    def __init__(
        self,
        *,
        on_show: Callable[[], None],
        on_quit: Callable[[], None],
        on_stop_wallpaper: Callable[[], None] | None = None,
    ) -> None:
        self._on_show = on_show
        self._on_quit = on_quit
        self._on_stop = on_stop_wallpaper
        self._indicator = None
        self._available = False
        self._init_indicator()

    @property
    def available(self) -> bool:
        return self._available

    def _init_indicator(self) -> None:
        try:
            import gi

            try:
                gi.require_version("AyatanaAppIndicator3", "0.1")
                from gi.repository import AyatanaAppIndicator3 as AppIndicator  # type: ignore
            except (ValueError, ImportError):
                gi.require_version("AppIndicator3", "0.1")
                from gi.repository import AppIndicator3 as AppIndicator  # type: ignore

            gi.require_version("Gtk", "3.0")
            from gi.repository import Gtk as Gtk3  # type: ignore

            ind = AppIndicator.Indicator.new(
                "gnomepaper-engine",
                "preferences-desktop-wallpaper",
                AppIndicator.IndicatorCategory.APPLICATION_STATUS,
            )
            ind.set_status(AppIndicator.IndicatorStatus.ACTIVE)
            ind.set_title("GnomePaper Engine")

            menu = Gtk3.Menu()
            show_item = Gtk3.MenuItem(label="Show window")
            show_item.connect("activate", lambda *_: self._on_show())
            menu.append(show_item)

            if self._on_stop is not None:
                stop_item = Gtk3.MenuItem(label="Stop wallpaper")
                stop_item.connect("activate", lambda *_: self._on_stop())
                menu.append(stop_item)

            menu.append(Gtk3.SeparatorMenuItem())
            quit_item = Gtk3.MenuItem(label="Quit")
            quit_item.connect("activate", lambda *_: self._on_quit())
            menu.append(quit_item)
            menu.show_all()
            ind.set_menu(menu)
            self._indicator = ind
            self._available = True
            log.info("System tray indicator ready")
        except Exception as exc:
            log.info("System tray unavailable (%s) — using background hide only", exc)
            self._available = False

    def set_visible(self, visible: bool) -> None:
        if self._indicator is None:
            return
        try:
            from gi.repository import AyatanaAppIndicator3 as AppIndicator  # type: ignore
        except ImportError:
            try:
                from gi.repository import AppIndicator3 as AppIndicator  # type: ignore
            except ImportError:
                return
        status = (
            AppIndicator.IndicatorStatus.ACTIVE
            if visible
            else AppIndicator.IndicatorStatus.PASSIVE
        )
        self._indicator.set_status(status)
