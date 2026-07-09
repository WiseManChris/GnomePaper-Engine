"""Main application window — library browser shell."""

from __future__ import annotations

import logging
from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gio, GLib, GObject, Gtk  # noqa: E402

from gnomepaper_engine.steam.models import WallpaperItem  # noqa: E402

log = logging.getLogger(__name__)


class WallpaperRow(Gtk.ListBoxRow):
    """One wallpaper entry in the library list."""

    def __init__(self, item: WallpaperItem) -> None:
        super().__init__()
        self.item = item

        title = Gtk.Label(
            label=item.title,
            xalign=0,
            hexpand=True,
            ellipsize=3,  # Pango.EllipsizeMode.END
        )
        title.add_css_class("heading")

        subtitle = Gtk.Label(
            label=f"{item.type_label} · {item.id}",
            xalign=0,
            hexpand=True,
            ellipsize=3,
        )
        subtitle.add_css_class("dim-label")
        subtitle.add_css_class("caption")

        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        text.append(title)
        text.append(subtitle)

        box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=12,
            margin_top=8,
            margin_bottom=8,
            margin_start=12,
            margin_end=12,
        )
        icon = Gtk.Image.new_from_icon_name("video-x-generic-symbolic")
        if item.wallpaper_type.value == "scene":
            icon.set_from_icon_name("applications-graphics-symbolic")
        elif item.wallpaper_type.value == "web":
            icon.set_from_icon_name("web-browser-symbolic")
        box.append(icon)
        box.append(text)
        self.set_child(box)


class MainWindow(Adw.ApplicationWindow):
    """Primary UI: status, search, library list, apply/stop."""

    def __init__(
        self,
        application: Adw.Application,
        *,
        on_refresh: Callable[[], None],
        on_apply: Callable[[WallpaperItem], None],
        on_stop: Callable[[], None],
    ) -> None:
        super().__init__(
            application=application,
            title="GnomePaper Engine",
            default_width=920,
            default_height=640,
        )
        self._on_refresh = on_refresh
        self._on_apply = on_apply
        self._on_stop = on_stop
        self._items: list[WallpaperItem] = []
        self._filter = ""

        self._build()

    def _build(self) -> None:
        toolbar_view = Adw.ToolbarView()
        self.set_content(toolbar_view)

        header = Adw.HeaderBar()
        toolbar_view.add_top_bar(header)

        self._status = Gtk.Label(label="Not linked to Steam yet", xalign=0)
        self._status.add_css_class("dim-label")
        header.set_title_widget(self._status)

        refresh_btn = Gtk.Button(icon_name="view-refresh-symbolic", tooltip_text="Rescan Steam")
        refresh_btn.connect("clicked", lambda *_: self._on_refresh())
        header.pack_start(refresh_btn)

        menu_btn = Gtk.MenuButton(icon_name="open-menu-symbolic", tooltip_text="Menu")
        menu = Gio.Menu()
        menu.append("Keyboard Shortcuts", "win.show-help-overlay")
        menu.append("About GnomePaper Engine", "app.about")
        menu.append("Quit", "app.quit")
        menu_btn.set_menu_model(menu)
        header.pack_end(menu_btn)

        stop_btn = Gtk.Button(label="Stop", tooltip_text="Stop active wallpaper")
        stop_btn.add_css_class("flat")
        stop_btn.connect("clicked", lambda *_: self._on_stop())
        header.pack_end(stop_btn)

        # Body
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        search = Gtk.SearchEntry(
            placeholder_text="Search wallpapers…",
            margin_top=12,
            margin_bottom=6,
            margin_start=12,
            margin_end=12,
        )
        search.connect("search-changed", self._on_search_changed)
        outer.append(search)

        self._banner = Adw.Banner(title="")
        self._banner.set_revealed(False)
        outer.append(self._banner)

        scrolled = Gtk.ScrolledWindow(vexpand=True, hexpand=True)
        self._list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self._list.add_css_class("boxed-list")
        self._list.set_margin_start(12)
        self._list.set_margin_end(12)
        self._list.set_margin_bottom(12)
        self._list.connect("row-activated", self._on_row_activated)
        scrolled.set_child(self._list)

        clamp = Adw.Clamp(maximum_size=800, tightening_threshold=600, child=scrolled)
        clamp.set_vexpand(True)
        outer.append(clamp)

        # Empty state
        self._empty = Adw.StatusPage(
            icon_name="folder-pictures-symbolic",
            title="No wallpapers found",
            description=(
                "Install Wallpaper Engine on Steam and subscribe to workshop items, "
                "then click Rescan."
            ),
        )
        self._empty.set_visible(False)
        outer.append(self._empty)

        action_bar = Gtk.ActionBar()
        self._selection_label = Gtk.Label(label="Select a wallpaper", xalign=0, hexpand=True)
        self._selection_label.add_css_class("dim-label")
        action_bar.pack_start(self._selection_label)

        self._apply_btn = Gtk.Button(label="Apply")
        self._apply_btn.add_css_class("suggested-action")
        self._apply_btn.set_sensitive(False)
        self._apply_btn.connect("clicked", self._on_apply_clicked)
        action_bar.pack_end(self._apply_btn)
        outer.append(action_bar)

        toolbar_view.set_content(outer)

        self._list.connect("row-selected", self._on_row_selected)

    def set_status(self, text: str) -> None:
        self._status.set_label(text)

    def show_message(self, text: str, *, error: bool = False) -> None:
        self._banner.set_title(text)
        self._banner.set_revealed(True)
        if error:
            self._banner.add_css_class("error")
        else:
            self._banner.remove_css_class("error")
        # Auto-hide informational banners
        if not error:
            GLib.timeout_add_seconds(5, self._hide_banner)

    def _hide_banner(self) -> bool:
        self._banner.set_revealed(False)
        return GLib.SOURCE_REMOVE

    def set_items(self, items: list[WallpaperItem]) -> None:
        self._items = list(items)
        self._rebuild_list()

    def _filtered_items(self) -> list[WallpaperItem]:
        q = self._filter.strip().lower()
        if not q:
            return list(self._items)
        return [
            i
            for i in self._items
            if q in i.title.lower() or q in i.id.lower() or q in i.type_label.lower()
        ]

    def _rebuild_list(self) -> None:
        while (child := self._list.get_first_child()) is not None:
            self._list.remove(child)

        filtered = self._filtered_items()
        for item in filtered:
            self._list.append(WallpaperRow(item))

        has = len(filtered) > 0
        self._list.set_visible(has)
        self._empty.set_visible(not has and not self._filter)
        if not has and self._filter:
            self._empty.set_visible(True)
            self._empty.set_title("No matches")
            self._empty.set_description("Try a different search.")
        elif not has:
            self._empty.set_title("No wallpapers found")
            self._empty.set_description(
                "Install Wallpaper Engine on Steam and subscribe to workshop items, "
                "then click Rescan."
            )

        self._apply_btn.set_sensitive(False)
        self._selection_label.set_label("Select a wallpaper")

    def _on_search_changed(self, entry: Gtk.SearchEntry) -> None:
        self._filter = entry.get_text()
        self._rebuild_list()

    def _selected_item(self) -> WallpaperItem | None:
        row = self._list.get_selected_row()
        if isinstance(row, WallpaperRow):
            return row.item
        return None

    def _on_row_selected(self, _list: Gtk.ListBox, row: Gtk.ListBoxRow | None) -> None:
        item = row.item if isinstance(row, WallpaperRow) else None
        if item is None:
            self._apply_btn.set_sensitive(False)
            self._selection_label.set_label("Select a wallpaper")
            return
        self._apply_btn.set_sensitive(True)
        self._selection_label.set_label(f"{item.title} ({item.type_label})")

    def _on_row_activated(self, _list: Gtk.ListBox, row: Gtk.ListBoxRow) -> None:
        if isinstance(row, WallpaperRow):
            self._on_apply(row.item)

    def _on_apply_clicked(self, *_args: GObject.Object) -> None:
        item = self._selected_item()
        if item is not None:
            self._on_apply(item)
