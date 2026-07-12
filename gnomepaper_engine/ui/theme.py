"""Apply light / dark / OLED and accent color preferences to the app UI."""

from __future__ import annotations

import logging

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gdk, Gtk  # noqa: E402

log = logging.getLogger(__name__)

# Public options for Settings UI
THEME_OPTIONS: list[tuple[str, str]] = [
    ("system", "System"),
    ("light", "Light"),
    ("dark", "Dark"),
    ("oled", "Pitch black (OLED)"),
]

# id → (label, accent hex)
ACCENT_OPTIONS: list[tuple[str, str, str]] = [
    ("blue", "Blue", "#3584e4"),
    ("teal", "Teal", "#2190a4"),
    ("purple", "Purple", "#9141ac"),
    ("orange", "Orange", "#e66100"),
]

_provider: Gtk.CssProvider | None = None


def apply_theme(*, theme: str = "system", accent: str = "blue") -> None:
    """Apply color scheme + accent CSS. Safe to call repeatedly."""
    _apply_color_scheme(theme)
    _apply_css(theme=theme, accent=accent)


def _apply_color_scheme(theme: str) -> None:
    sm = Adw.StyleManager.get_default()
    if theme == "light":
        sm.set_color_scheme(Adw.ColorScheme.FORCE_LIGHT)
    elif theme in ("dark", "oled"):
        sm.set_color_scheme(Adw.ColorScheme.FORCE_DARK)
    else:
        sm.set_color_scheme(Adw.ColorScheme.DEFAULT)


def _accent_hex(accent: str) -> str:
    for key, _label, hex_color in ACCENT_OPTIONS:
        if key == accent:
            return hex_color
    return "#3584e4"


def _apply_css(*, theme: str, accent: str) -> None:
    global _provider
    accent_hex = _accent_hex(accent)
    # Slightly darker accent for hover/active
    oled_block = ""
    if theme == "oled":
        oled_block = """
        /* Pitch black OLED surfaces */
        window,
        .background,
        .view,
        .card,
        banner,
        toast,
        popover contents,
        .sidebar,
        headerbar,
        .top-bar,
        .bottom-bar,
        .toolbar,
        .navigation-sidebar {
          background-color: #000000;
          background: #000000;
        }
        list, listview, gridview, flowbox {
          background-color: #000000;
        }
        """

    css = f"""
    @define-color accent_color {accent_hex};
    @define-color accent_bg_color {accent_hex};
    @define-color accent_fg_color #ffffff;
    @define-color theme_selected_bg_color {accent_hex};
    @define-color theme_selected_fg_color #ffffff;

    button.suggested-action,
    .suggested-action {{
      background-color: {accent_hex};
      color: #ffffff;
    }}
    switch:checked {{
      background-color: {accent_hex};
    }}
    {oled_block}
    """

    display = Gdk.Display.get_default()
    if display is None:
        return

    if _provider is not None:
        try:
            Gtk.StyleContext.remove_provider_for_display(display, _provider)
        except Exception:
            pass
        _provider = None

    provider = Gtk.CssProvider()
    try:
        provider.load_from_string(css)
    except Exception:
        # Older PyGObject: load_from_data
        provider.load_from_data(css.encode("utf-8"))
    Gtk.StyleContext.add_provider_for_display(
        display,
        provider,
        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
    )
    _provider = provider
    log.info("Theme applied: theme=%s accent=%s", theme, accent)
