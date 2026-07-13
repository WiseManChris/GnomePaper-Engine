"""Wallpaper Engine–style main window: installed library + Workshop browser."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")
gi.require_version("GdkPixbuf", "2.0")

from gi.repository import Adw, Gdk, GdkPixbuf, Gio, GLib, GObject, Gtk  # noqa: E402

from gnomepaper_engine.config import AppConfig  # noqa: E402
from gnomepaper_engine.steam.models import WallpaperItem  # noqa: E402
from gnomepaper_engine.ui.previews import DETAIL_H, DETAIL_W, PreviewCache  # noqa: E402
from gnomepaper_engine.ui.wallpaper_card import WallpaperCard  # noqa: E402
from gnomepaper_engine.ui.workshop_card import WorkshopCard  # noqa: E402
from gnomepaper_engine.workshop.client import (  # noqa: E402
    SORTS,
    WorkshopItem,
    cache_remote_preview,
    download_via_steamcmd,
    installed_ids,
    is_installed,
    link_steam_account,
    open_install,
    search_workshop,
    wait_for_install,
)
from gnomepaper_engine.workshop.steam_profile import (  # noqa: E402
    avatar_cache_path,
    cache_avatar,
    fetch_steam_profile,
)

log = logging.getLogger(__name__)


class MainWindow(Adw.ApplicationWindow):
    """Installed library + Steam Workshop browser (WE-like)."""

    def __init__(
        self,
        application: Adw.Application,
        *,
        on_refresh: Callable[[], None],
        on_apply: Callable[[WallpaperItem], None],
        on_stop: Callable[[], None],
        on_remove: Callable[[WallpaperItem], None] | None = None,
        mute_audio: bool = False,
        audio_volume: int = 70,
        mouse_interaction: bool = True,
        target_fps: int = 30,
        steam_username: str = "",
        steam_linked: bool = False,
        steam_persona_name: str = "",
        steam_id64: str = "",
        steam_avatar_path: str = "",
        prefer_steamcmd_download: bool = True,
        we_owned: bool = True,
        on_mute_changed: Callable[[bool], None] | None = None,
        on_volume_changed: Callable[[int], None] | None = None,
        on_mouse_changed: Callable[[bool], None] | None = None,
        on_fps_changed: Callable[[int], None] | None = None,
        on_steam_username_changed: Callable[[str], None] | None = None,
        on_steam_linked_changed: Callable[[bool], None] | None = None,
        on_steam_profile_changed: Callable[[str, str, str], None] | None = None,
        on_prefer_steamcmd_changed: Callable[[bool], None] | None = None,
    ) -> None:
        super().__init__(
            application=application,
            title="GnomePaper Engine",
            default_width=1220,
            default_height=780,
        )
        self._on_refresh = on_refresh
        self._on_apply = on_apply
        self._on_stop = on_stop
        self._on_remove = on_remove
        self._on_mute_changed = on_mute_changed
        self._on_volume_changed = on_volume_changed
        self._on_mouse_changed = on_mouse_changed
        self._on_fps_changed = on_fps_changed
        self._on_steam_username_changed = on_steam_username_changed
        self._on_steam_linked_changed = on_steam_linked_changed
        self._on_steam_profile_changed = on_steam_profile_changed
        self._on_prefer_steamcmd_changed = on_prefer_steamcmd_changed

        self._mute_audio = mute_audio
        self._audio_volume = audio_volume
        self._mouse_interaction = mouse_interaction
        self._target_fps = target_fps
        self._steam_username = steam_username
        self._steam_linked = steam_linked
        self._steam_persona = steam_persona_name
        self._steam_id64 = steam_id64
        self._steam_avatar_path = steam_avatar_path
        self._prefer_steamcmd = prefer_steamcmd_download
        self._we_owned = we_owned

        self._items: list[WallpaperItem] = []
        self._filter = ""
        self._type_filter = "all"
        self._selected: WallpaperItem | None = None
        self._ws_selected: WorkshopItem | None = None
        self._preview_cache = PreviewCache()
        self._ws_cache_dir = AppConfig.cache_dir() / "workshop_previews"
        self._ws_cache_dir.mkdir(parents=True, exist_ok=True)
        self._avatar_cache_dir = AppConfig.cache_dir() / "steam_avatar"
        self._avatar_cache_dir.mkdir(parents=True, exist_ok=True)
        self._ws_page = 1
        self._ws_sort = "trend"
        self._ws_query = ""
        self._ws_searching = False
        self._install_cancel = False

        self._build()
        GLib.idle_add(self._refresh_steam_chip)
        if self._steam_linked and self._steam_username:
            GLib.idle_add(self._load_steam_avatar_async)

    # ── construction ──────────────────────────────────────────────

    def _build(self) -> None:
        toolbar_view = Adw.ToolbarView()
        self.set_content(toolbar_view)

        header = Adw.HeaderBar()
        toolbar_view.add_top_bar(header)

        # Top-left: Steam account chip (link / avatar)
        header.pack_start(self._build_steam_chip())

        # View switcher: Installed | Workshop
        self._stack = Adw.ViewStack()
        switcher = Adw.ViewSwitcher(stack=self._stack, policy=Adw.ViewSwitcherPolicy.WIDE)
        header.set_title_widget(switcher)

        refresh_btn = Gtk.Button(
            icon_name="view-refresh-symbolic",
            tooltip_text="Rescan installed wallpapers",
        )
        refresh_btn.connect("clicked", lambda *_: self._on_refresh())
        header.pack_start(refresh_btn)

        menu_btn = Gtk.MenuButton(icon_name="open-menu-symbolic", tooltip_text="Menu")
        menu = Gio.Menu()
        menu.append("Settings", "app.settings")
        menu.append("About GnomePaper Engine", "app.about")
        menu.append("Quit", "app.quit")
        menu_btn.set_menu_model(menu)
        header.pack_end(menu_btn)

        stop_btn = Gtk.Button(label="Stop", tooltip_text="Stop active wallpaper")
        stop_btn.add_css_class("flat")
        stop_btn.connect("clicked", lambda *_: self._on_stop())
        header.pack_end(stop_btn)

        self._banner = Adw.Banner(title="")
        self._banner.set_revealed(False)

        # Pages
        self._stack.add_titled_with_icon(
            self._build_installed_page(),
            "installed",
            "Installed",
            "folder-pictures-symbolic",
        )
        self._stack.add_titled_with_icon(
            self._build_workshop_page(),
            "workshop",
            "Workshop",
            "emblem-downloads-symbolic",
        )
        self._stack.connect("notify::visible-child-name", self._on_view_changed)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        outer.append(self._banner)
        outer.append(self._stack)
        toolbar_view.set_content(outer)

        self._set_detail_placeholder()

    def _build_installed_page(self) -> Gtk.Widget:
        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL, wide_handle=True)
        paned.set_shrink_start_child(False)
        paned.set_shrink_end_child(False)
        paned.set_resize_start_child(True)
        paned.set_resize_end_child(False)
        paned.set_position(820)
        paned.set_vexpand(True)

        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        search = Gtk.SearchEntry(
            placeholder_text="Search installed wallpapers…",
            margin_top=10,
            margin_bottom=6,
            margin_start=12,
            margin_end=12,
        )
        search.connect("search-changed", self._on_search_changed)
        left.append(search)

        filter_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=6,
            margin_start=12,
            margin_end=12,
            margin_bottom=8,
        )
        first_btn: Gtk.ToggleButton | None = None
        for key, label in (
            ("all", "All"),
            ("video", "Video"),
            ("scene", "Scene"),
            ("web", "Web"),
        ):
            btn = Gtk.ToggleButton(label=label)
            btn.add_css_class("flat")
            if first_btn is None:
                first_btn = btn
                btn.set_active(True)
            else:
                btn.set_group(first_btn)
            btn.connect("toggled", self._on_type_toggled, key)
            filter_box.append(btn)
        left.append(filter_box)

        scrolled = Gtk.ScrolledWindow(vexpand=True, hexpand=True)
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self._flow = Gtk.FlowBox(
            selection_mode=Gtk.SelectionMode.SINGLE,
            homogeneous=True,
            max_children_per_line=6,
            min_children_per_line=3,
            row_spacing=8,
            column_spacing=8,
            margin_start=10,
            margin_end=10,
            margin_bottom=10,
            valign=Gtk.Align.START,
        )
        self._flow.set_activate_on_single_click(False)
        self._flow.connect("child-activated", self._on_card_activated)
        self._flow.connect("selected-children-changed", self._on_selection_changed)
        scrolled.set_child(self._flow)
        left.append(scrolled)

        self._empty = Adw.StatusPage(
            icon_name="folder-pictures-symbolic",
            title="No wallpapers installed",
            description="Open the Workshop tab to search and subscribe to new ones.",
            vexpand=True,
        )
        self._empty.set_visible(False)
        left.append(self._empty)

        paned.set_start_child(left)
        paned.set_end_child(self._build_detail_pane(installed_mode=True))
        return paned

    def _build_workshop_page(self) -> Gtk.Widget:
        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL, wide_handle=True)
        paned.set_shrink_start_child(False)
        paned.set_shrink_end_child(False)
        paned.set_resize_start_child(True)
        paned.set_resize_end_child(False)
        paned.set_position(820)
        paned.set_vexpand(True)

        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        # Search bar row
        row = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=8,
            margin_top=10,
            margin_bottom=6,
            margin_start=12,
            margin_end=12,
        )
        self._ws_search = Gtk.SearchEntry(
            placeholder_text="Search Steam Workshop…",
            hexpand=True,
        )
        self._ws_search.connect("activate", lambda *_: self._start_workshop_search(reset_page=True))
        row.append(self._ws_search)

        self._ws_sort = Gtk.DropDown.new_from_strings(list(SORTS.values()))
        self._ws_sort.set_selected(0)
        self._ws_sort.set_tooltip_text("Sort order")
        row.append(self._ws_sort)

        search_btn = Gtk.Button(label="Search")
        search_btn.add_css_class("suggested-action")
        search_btn.connect("clicked", lambda *_: self._start_workshop_search(reset_page=True))
        row.append(search_btn)
        left.append(row)

        hint = Gtk.Label(
            label="Subscribe with Steam (one click). Downloads land in your workshop folder automatically.",
            xalign=0,
            wrap=True,
            margin_start=14,
            margin_end=14,
            margin_bottom=6,
        )
        hint.add_css_class("dim-label")
        hint.add_css_class("caption")
        left.append(hint)

        self._ws_status = Gtk.Label(
            label="Search for wallpapers or browse trending.",
            xalign=0,
            margin_start=14,
            margin_end=14,
            margin_bottom=6,
        )
        self._ws_status.add_css_class("caption")
        left.append(self._ws_status)

        scrolled = Gtk.ScrolledWindow(vexpand=True, hexpand=True)
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self._ws_flow = Gtk.FlowBox(
            selection_mode=Gtk.SelectionMode.SINGLE,
            homogeneous=True,
            max_children_per_line=6,
            min_children_per_line=3,
            row_spacing=8,
            column_spacing=8,
            margin_start=10,
            margin_end=10,
            margin_bottom=10,
            valign=Gtk.Align.START,
        )
        self._ws_flow.connect("selected-children-changed", self._on_ws_selection_changed)
        scrolled.set_child(self._ws_flow)
        left.append(scrolled)

        # Pagination
        page_row = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=8,
            margin_start=12,
            margin_end=12,
            margin_bottom=10,
            halign=Gtk.Align.CENTER,
        )
        prev_btn = Gtk.Button(label="Previous")
        prev_btn.connect("clicked", self._on_ws_prev)
        next_btn = Gtk.Button(label="Next")
        next_btn.connect("clicked", self._on_ws_next)
        self._ws_page_lbl = Gtk.Label(label="Page 1")
        page_row.append(prev_btn)
        page_row.append(self._ws_page_lbl)
        page_row.append(next_btn)
        left.append(page_row)

        paned.set_start_child(left)
        paned.set_end_child(self._build_detail_pane(installed_mode=False))
        return paned

    def _build_detail_pane(self, *, installed_mode: bool) -> Gtk.Widget:
        """Build right-hand detail + settings (or install) pane."""
        right_scroll = Gtk.ScrolledWindow(vexpand=True, hexpand=False)
        right_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        right_scroll.set_size_request(320, -1)
        right_scroll.add_css_class("view")

        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        picture = Gtk.Picture()
        picture.set_content_fit(Gtk.ContentFit.COVER)
        picture.set_size_request(DETAIL_W, DETAIL_H)
        picture.set_can_shrink(True)
        picture.set_halign(Gtk.Align.CENTER)
        preview_frame = Gtk.Frame(
            margin_top=10,
            margin_start=12,
            margin_end=12,
            halign=Gtk.Align.CENTER,
        )
        preview_frame.set_size_request(DETAIL_W, DETAIL_H)
        preview_frame.set_child(picture)
        right.append(preview_frame)

        title = Gtk.Label(
            label="Select a wallpaper",
            xalign=0,
            wrap=True,
            margin_top=10,
            margin_start=16,
            margin_end=16,
        )
        title.add_css_class("heading")
        right.append(title)

        meta = Gtk.Label(
            label="Preview and actions appear here",
            xalign=0,
            wrap=True,
            margin_top=2,
            margin_start=16,
            margin_end=16,
        )
        meta.add_css_class("dim-label")
        meta.add_css_class("caption")
        right.append(meta)

        tags = Gtk.Label(
            label="",
            xalign=0,
            wrap=True,
            margin_top=2,
            margin_start=16,
            margin_end=16,
            margin_bottom=6,
        )
        tags.add_css_class("caption")
        tags.add_css_class("dim-label")
        right.append(tags)

        action_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=8,
            margin_start=16,
            margin_end=16,
            margin_bottom=8,
        )
        primary = Gtk.Button(hexpand=True)
        primary.add_css_class("suggested-action")
        primary.add_css_class("pill")
        primary.set_sensitive(False)
        action_box.append(primary)

        if installed_mode:
            remove_btn = Gtk.Button(label="Remove")
            remove_btn.add_css_class("destructive-action")
            remove_btn.add_css_class("pill")
            remove_btn.set_sensitive(False)
            remove_btn.set_tooltip_text("Delete this wallpaper from your library (local files)")
            remove_btn.connect("clicked", self._on_remove_clicked)
            action_box.append(remove_btn)
            self._remove_btn = remove_btn

        right.append(action_box)

        if installed_mode:
            self._detail_picture = picture
            self._detail_title = title
            self._detail_meta = meta
            self._detail_tags = tags
            self._apply_btn = primary
            self._apply_btn.set_label("OK · Apply")
            self._apply_btn.connect("clicked", self._on_apply_clicked)
            right.append(self._build_settings_block())
        else:
            self._ws_detail_picture = picture
            self._ws_detail_title = title
            self._ws_detail_meta = meta
            self._ws_detail_tags = tags
            self._ws_install_btn = primary
            self._ws_install_btn.set_label("Get via Steam")
            self._ws_install_btn.set_tooltip_text(
                "Opens the Workshop item in Steam — Subscribe and we pick it up "
                "(works with SteamTools / custom Steam)"
            )
            self._ws_install_btn.connect("clicked", self._on_ws_install_clicked)

            cmd_btn = Gtk.Button(label="SteamCMD download (advanced)")
            cmd_btn.add_css_class("flat")
            cmd_btn.set_margin_start(16)
            cmd_btn.set_margin_end(16)
            cmd_btn.set_tooltip_text(
                "Optional. Often breaks with SteamTools / Lua Tools. "
                "Needs Link Steam (top-left)."
            )
            cmd_btn.connect("clicked", self._on_ws_steamcmd_advanced)
            right.append(cmd_btn)

            tip = Gtk.Label(
                label=(
                    "Recommended: Get via Steam → click Subscribe in your Steam client. "
                    "Works with normal Steam, SteamTools, and custom clients. "
                    "SteamCMD is optional and often fails with injectors."
                ),
                wrap=True,
                xalign=0,
                margin_start=16,
                margin_end=16,
                margin_top=8,
            )
            tip.add_css_class("dim-label")
            tip.add_css_class("caption")
            right.append(tip)

            open_web = Gtk.Button(label="Open in browser")
            open_web.add_css_class("flat")
            open_web.set_margin_start(16)
            open_web.set_margin_end(16)
            open_web.connect("clicked", self._on_ws_open_browser)
            right.append(open_web)

        right_scroll.set_child(right)
        return right_scroll

    def _build_settings_block(self) -> Gtk.Widget:
        prefs = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=0,
            margin_start=12,
            margin_end=12,
            margin_bottom=16,
        )
        prefs.append(self._section_label("Playback"))
        play_group = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        play_group.add_css_class("boxed-list")
        play_group.append(
            self._switch_row(
                "Mute audio",
                "Live — silences active wallpaper immediately",
                self._mute_audio,
                self._on_mute_switch,
            )
        )
        vol_row = Adw.ActionRow(
            title="Volume",
            subtitle="Live — adjusts active wallpaper immediately",
        )
        self._volume_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        self._volume_scale.set_value(self._audio_volume)
        self._volume_scale.set_draw_value(True)
        self._volume_scale.set_value_pos(Gtk.PositionType.RIGHT)
        self._volume_scale.set_size_request(140, -1)
        self._volume_scale.set_hexpand(True)
        self._volume_scale.set_sensitive(not self._mute_audio)
        # Live while dragging (not only on release)
        self._volume_scale.connect("value-changed", self._on_volume_changed)
        vol_row.add_suffix(self._volume_scale)
        play_group.append(vol_row)
        fps_row = Adw.ActionRow(title="FPS limit", subtitle="Scene / engine frame rate")
        self._fps_spin = Gtk.SpinButton.new_with_range(15, 60, 1)
        self._fps_spin.set_value(self._target_fps)
        self._fps_spin.connect("value-changed", self._on_fps_changed)
        fps_row.add_suffix(self._fps_spin)
        play_group.append(fps_row)
        prefs.append(play_group)

        prefs.append(self._section_label("Interaction"))
        inter = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        inter.add_css_class("boxed-list")
        inter.append(
            self._switch_row(
                "Mouse effects",
                "Eye-follow, parallax (scenes)",
                self._mouse_interaction,
                self._on_mouse_switch,
            )
        )
        prefs.append(inter)

        prefs.append(self._section_label("Workshop"))
        steam_group = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        steam_group.add_css_class("boxed-list")
        steam_group.append(
            self._switch_row(
                "Prefer SteamCMD (advanced)",
                "Unreliable with SteamTools / custom Steam — leave off unless you need it",
                self._prefer_steamcmd,
                self._on_prefer_steamcmd_switch,
            )
        )
        prefs.append(steam_group)

        we_note = Gtk.Label(
            label=(
                "Wallpaper Engine ownership is required. "
                + (
                    "Install detected on this system."
                    if self._we_owned
                    else "Not detected — install WE from Steam first."
                )
            ),
            wrap=True,
            xalign=0,
            margin_top=8,
        )
        we_note.add_css_class("dim-label")
        we_note.add_css_class("caption")
        prefs.append(we_note)

        prefs.append(self._section_label("Status"))
        status = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        status.add_css_class("boxed-list")
        self._active_row = Adw.ActionRow(title="Active wallpaper", subtitle="None")
        status.append(self._active_row)
        prefs.append(status)

        hint = Gtk.Label(
            label="Change a toggle, then re-apply the wallpaper.",
            wrap=True,
            xalign=0,
            margin_top=10,
        )
        hint.add_css_class("dim-label")
        hint.add_css_class("caption")
        prefs.append(hint)
        return prefs

    def _section_label(self, text: str) -> Gtk.Label:
        lbl = Gtk.Label(label=text, xalign=0, margin_top=14, margin_bottom=6)
        lbl.add_css_class("heading")
        return lbl

    def _switch_row(
        self, title: str, subtitle: str, active: bool, callback: Callable
    ) -> Adw.ActionRow:
        row = Adw.ActionRow(title=title, subtitle=subtitle)
        switch = Gtk.Switch(valign=Gtk.Align.CENTER, active=active)
        switch.connect("notify::active", callback)
        row.add_suffix(switch)
        row.set_activatable_widget(switch)
        return row

    # ── public API ────────────────────────────────────────────────

    def set_status(self, text: str) -> None:
        # Status moved into banner/workshop label; keep for compatibility
        if hasattr(self, "_ws_status") and self._stack.get_visible_child_name() == "workshop":
            return
        log.debug("status: %s", text)

    def set_active_wallpaper(self, title: str | None) -> None:
        if hasattr(self, "_active_row"):
            self._active_row.set_subtitle(title or "None")

    def show_message(self, text: str, *, error: bool = False) -> None:
        self._banner.set_title(text)
        self._banner.set_revealed(True)
        if error:
            self._banner.add_css_class("error")
        else:
            self._banner.remove_css_class("error")
        if not error:
            GLib.timeout_add_seconds(6, self._hide_banner)

    def _hide_banner(self) -> bool:
        self._banner.set_revealed(False)
        return GLib.SOURCE_REMOVE

    def set_items(self, items: list[WallpaperItem]) -> None:
        self._items = list(items)
        self._rebuild_grid()

    # ── installed library ─────────────────────────────────────────

    def _filtered_items(self) -> list[WallpaperItem]:
        q = self._filter.strip().lower()
        out: list[WallpaperItem] = []
        for i in self._items:
            if self._type_filter != "all" and i.wallpaper_type.value != self._type_filter:
                continue
            if q and not (
                q in i.title.lower()
                or q in i.id.lower()
                or q in i.type_label.lower()
                or any(q in t.lower() for t in i.tags)
            ):
                continue
            out.append(i)
        return out

    def _rebuild_grid(self) -> None:
        while (child := self._flow.get_first_child()) is not None:
            self._flow.remove(child)
        filtered = self._filtered_items()
        for item in filtered:
            self._flow.append(WallpaperCard(item, self._preview_cache))
        has = len(filtered) > 0
        self._flow.set_visible(has)
        self._empty.set_visible(not has)
        if not has and self._filter:
            self._empty.set_title("No matches")
            self._empty.set_description("Try another search or filter.")
        elif not has:
            self._empty.set_title("No wallpapers installed")
            self._empty.set_description(
                "Open the Workshop tab to find and subscribe to wallpapers."
            )
        self._selected = None
        self._apply_btn.set_sensitive(False)
        if hasattr(self, "_remove_btn"):
            self._remove_btn.set_sensitive(False)
        self._set_detail_placeholder()

    def _on_search_changed(self, entry: Gtk.SearchEntry) -> None:
        self._filter = entry.get_text()
        self._rebuild_grid()

    def _on_type_toggled(self, button: Gtk.ToggleButton, key: str) -> None:
        if not button.get_active():
            return
        self._type_filter = key
        self._rebuild_grid()

    def _on_selection_changed(self, flow: Gtk.FlowBox) -> None:
        selected = flow.get_selected_children()
        if not selected:
            self._selected = None
            self._apply_btn.set_sensitive(False)
            if hasattr(self, "_remove_btn"):
                self._remove_btn.set_sensitive(False)
            self._set_detail_placeholder()
            return
        child = selected[0]
        if isinstance(child, WallpaperCard):
            self._show_detail(child.item)

    def _on_card_activated(self, _flow: Gtk.FlowBox, child: Gtk.FlowBoxChild) -> None:
        if isinstance(child, WallpaperCard):
            self._show_detail(child.item)
            self._on_apply(child.item)

    def _show_detail(self, item: WallpaperItem) -> None:
        self._selected = item
        self._apply_btn.set_sensitive(True)
        if hasattr(self, "_remove_btn"):
            self._remove_btn.set_sensitive(True)
        self._detail_title.set_label(item.title)
        self._detail_meta.set_label(f"{item.type_label}  ·  Workshop ID {item.id}")
        self._detail_tags.set_label(" · ".join(item.tags) if item.tags else str(item.path))
        texture = self._preview_cache.get(item.preview_path, width=DETAIL_W, height=DETAIL_H)
        self._detail_picture.set_paintable(texture)

    def _set_detail_placeholder(self) -> None:
        self._detail_picture.set_paintable(None)
        self._detail_title.set_label("Select a wallpaper")
        self._detail_meta.set_label("Double-click a tile or press Apply")
        self._detail_tags.set_label("")

    def _on_apply_clicked(self, *_args: GObject.Object) -> None:
        if self._selected is not None:
            self._on_apply(self._selected)

    def _on_remove_clicked(self, *_args: GObject.Object) -> None:
        item = self._selected
        if item is None:
            return
        dialog = Adw.AlertDialog(
            heading="Remove wallpaper?",
            body=(
                f"Delete “{item.title}” from your library?\n\n"
                "This removes the local workshop files from disk and cannot be undone. "
                "Steam may re-download it later if you are still subscribed."
            ),
        )
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("remove", "Remove")
        dialog.set_response_appearance("remove", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")

        def _on_response(_d: Adw.AlertDialog, response: str) -> None:
            if response != "remove":
                return
            if self._on_remove is not None:
                self._on_remove(item)

        dialog.connect("response", _on_response)
        dialog.present(self)

    # ── workshop ──────────────────────────────────────────────────

    def _on_view_changed(self, stack: Adw.ViewStack, *_args: object) -> None:
        if stack.get_visible_child_name() == "workshop":
            # Load trending on first open
            if self._ws_flow.get_first_child() is None and not self._ws_searching:
                self._start_workshop_search(reset_page=True)

    def _current_sort_key(self) -> str:
        keys = list(SORTS.keys())
        idx = int(self._ws_sort.get_selected())
        if 0 <= idx < len(keys):
            return keys[idx]
        return "trend"

    def _start_workshop_search(self, *, reset_page: bool) -> None:
        if self._ws_searching:
            return
        if reset_page:
            self._ws_page = 1
        self._ws_query = self._ws_search.get_text().strip()
        self._ws_searching = True
        self._ws_status.set_label("Searching Steam Workshop…")
        self._ws_page_lbl.set_label(f"Page {self._ws_page}")
        query = self._ws_query
        page = self._ws_page
        sort = self._current_sort_key()

        def worker() -> None:
            try:
                items = search_workshop(query, page=page, sort=sort, per_page=24)
                installed = installed_ids()
                GLib.idle_add(self._on_workshop_results, items, installed, None)
            except Exception as exc:
                GLib.idle_add(self._on_workshop_results, [], set(), str(exc))

        threading.Thread(target=worker, name="ws-search", daemon=True).start()

    def _on_workshop_results(
        self,
        items: list[WorkshopItem],
        installed: set[str],
        error: str | None,
    ) -> bool:
        self._ws_searching = False
        while (child := self._ws_flow.get_first_child()) is not None:
            self._ws_flow.remove(child)

        if error:
            self._ws_status.set_label(f"Search failed: {error}")
            self.show_message(error, error=True)
            return GLib.SOURCE_REMOVE

        for item in items:
            self._ws_flow.append(
                WorkshopCard(
                    item,
                    installed=item.id in installed,
                    cache_dir=self._ws_cache_dir,
                )
            )
        q = f"“{self._ws_query}”" if self._ws_query else "Trending"
        self._ws_status.set_label(f"{q} · {len(items)} results · page {self._ws_page}")
        self._ws_page_lbl.set_label(f"Page {self._ws_page}")
        self._ws_selected = None
        self._ws_install_btn.set_sensitive(False)
        self._ws_detail_title.set_label("Select a workshop item")
        self._ws_detail_meta.set_label("Subscribe to download via Steam")
        self._ws_detail_tags.set_label("")
        self._ws_detail_picture.set_paintable(None)
        return GLib.SOURCE_REMOVE

    def _on_ws_prev(self, *_args: object) -> None:
        if self._ws_page > 1 and not self._ws_searching:
            self._ws_page -= 1
            self._start_workshop_search(reset_page=False)

    def _on_ws_next(self, *_args: object) -> None:
        if not self._ws_searching:
            self._ws_page += 1
            self._start_workshop_search(reset_page=False)

    def _on_ws_selection_changed(self, flow: Gtk.FlowBox) -> None:
        selected = flow.get_selected_children()
        if not selected:
            self._ws_selected = None
            self._ws_install_btn.set_sensitive(False)
            return
        child = selected[0]
        if not isinstance(child, WorkshopCard):
            return
        item = child.item
        self._ws_selected = item
        installed = is_installed(item.id)
        self._ws_install_btn.set_sensitive(True)
        self._ws_install_btn.set_label("Open installed" if installed else "Download")
        self._ws_detail_title.set_label(item.title or item.id)
        bits = [b for b in (item.subs_label, item.size_label, f"ID {item.id}") if b]
        self._ws_detail_meta.set_label(" · ".join(bits))
        desc = (item.description or "").replace("\r\n", "\n").strip()
        if len(desc) > 280:
            desc = desc[:277] + "…"
        self._ws_detail_tags.set_label(desc)

        # Load detail preview
        def load() -> bool:
            url = item.preview_url
            if not url:
                return GLib.SOURCE_REMOVE
            dest = self._ws_cache_dir / f"ws_{item.id}_lg.jpg"
            path = dest if dest.is_file() else cache_remote_preview(url, dest)
            if path is None:
                return GLib.SOURCE_REMOVE
            try:
                pix = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                    str(path), DETAIL_W, DETAIL_H, True
                )
                if pix is not None:
                    self._ws_detail_picture.set_paintable(Gdk.Texture.new_for_pixbuf(pix))
            except Exception:
                pass
            return GLib.SOURCE_REMOVE

        GLib.idle_add(load)

    def _build_steam_chip(self) -> Gtk.Widget:
        """Top-left Steam account control: link button or avatar + name."""
        self._steam_chip_btn = Gtk.Button()
        self._steam_chip_btn.add_css_class("flat")
        self._steam_chip_btn.set_valign(Gtk.Align.CENTER)
        self._steam_chip_btn.connect("clicked", self._on_steam_chip_clicked)

        self._steam_chip_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=8,
            valign=Gtk.Align.CENTER,
        )
        self._steam_avatar = Gtk.Image.new_from_icon_name("avatar-default-symbolic")
        self._steam_avatar.set_pixel_size(28)
        self._steam_avatar.set_valign(Gtk.Align.CENTER)
        self._steam_chip_label = Gtk.Label(label="Link Steam", xalign=0)
        self._steam_chip_label.add_css_class("caption-heading")
        self._steam_chip_box.append(self._steam_avatar)
        self._steam_chip_box.append(self._steam_chip_label)
        self._steam_chip_btn.set_child(self._steam_chip_box)
        return self._steam_chip_btn

    def _on_steam_chip_clicked(self, *_args: object) -> None:
        # Always open link dialog (re-link / first link)
        self._prompt_link_steam()

    def _refresh_steam_chip(self) -> bool:
        if not hasattr(self, "_steam_chip_label"):
            return GLib.SOURCE_REMOVE
        if self._steam_linked and self._steam_username:
            name = self._steam_persona or self._steam_username
            self._steam_chip_label.set_label(name)
            self._steam_chip_btn.set_tooltip_text(
                f"Linked as {name}\nClick to re-link Steam account"
            )
            # Prefer cached avatar file
            if self._steam_avatar_path and Path(self._steam_avatar_path).is_file():
                self._set_avatar_from_file(Path(self._steam_avatar_path))
            else:
                self._steam_avatar.set_from_icon_name("avatar-default-symbolic")
        else:
            self._steam_chip_label.set_label("Link Steam")
            self._steam_chip_btn.set_tooltip_text(
                "Link the Steam account that owns Wallpaper Engine"
            )
            self._steam_avatar.set_from_icon_name("system-users-symbolic")
            self._steam_avatar.set_pixel_size(28)
        return GLib.SOURCE_REMOVE

    def _set_avatar_from_file(self, path: Path) -> None:
        try:
            pix = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(path), 56, 56, True)
            if pix is None:
                return
            # Round-ish: just use the image; GTK doesn't clip circles easily without CSS
            texture = Gdk.Texture.new_for_pixbuf(pix)
            self._steam_avatar.set_from_paintable(texture)
            self._steam_avatar.set_pixel_size(28)
        except Exception as exc:
            log.debug("avatar load failed: %s", exc)
            self._steam_avatar.set_from_icon_name("avatar-default-symbolic")

    def _load_steam_avatar_async(self) -> bool:
        username = self._steam_username
        sid = self._steam_id64
        if not username and not sid:
            return GLib.SOURCE_REMOVE

        def worker() -> None:
            profile = fetch_steam_profile(username, steam_id64=sid)
            if profile is None:
                log.info("Could not load Steam profile for %s / %s", username, sid)
                return
            key = profile.steam_id64 or username
            dest = avatar_cache_path(self._avatar_cache_dir, key)
            path = None
            if profile.avatar_url:
                path = cache_avatar(profile.avatar_url, dest)
            GLib.idle_add(
                self._on_profile_loaded,
                profile.persona_name,
                profile.steam_id64,
                str(path) if path else "",
            )

        threading.Thread(target=worker, name="steam-avatar", daemon=True).start()
        return GLib.SOURCE_REMOVE

    def _on_profile_loaded(
        self, persona: str, steam_id64: str, avatar_path: str
    ) -> bool:
        if persona:
            self._steam_persona = persona
        if steam_id64:
            self._steam_id64 = steam_id64
        if avatar_path:
            self._steam_avatar_path = avatar_path
        if self._on_steam_profile_changed is not None:
            self._on_steam_profile_changed(
                self._steam_persona,
                self._steam_id64,
                self._steam_avatar_path,
            )
        self._refresh_steam_chip()
        return GLib.SOURCE_REMOVE

    def _set_steam_linked(self, linked: bool) -> None:
        self._steam_linked = linked
        if self._on_steam_linked_changed is not None:
            self._on_steam_linked_changed(linked)
        self._refresh_steam_chip()
        if linked and self._steam_username:
            self._load_steam_avatar_async()

    def _on_ws_install_clicked(self, *_args: object) -> None:
        item = self._ws_selected
        if item is None:
            return
        if not self._we_owned:
            self.show_message(
                "Wallpaper Engine must be installed (owned on Steam) to download wallpapers.",
                error=True,
            )
            return
        if is_installed(item.id):
            self._stack.set_visible_child_name("installed")
            self._on_refresh()
            self.show_message(f"Already installed: {item.title}")
            return

        # Default: Steam client Subscribe (reliable with non-stock Steam).
        # SteamCMD only if the user explicitly prefers it (advanced).
        if self._prefer_steamcmd:
            if self._steam_linked and self._steam_username:
                self._run_steamcmd_download(
                    item, self._steam_username, password="", guard=""
                )
                return
            self._prompt_steamcmd_download(item)
            return

        self._start_subscribe_watch(item)

    def _on_ws_steamcmd_advanced(self, *_args: object) -> None:
        """Manual SteamCMD path — optional, often broken with injectors."""
        item = self._ws_selected
        if item is None:
            return
        if not self._we_owned:
            self.show_message(
                "Wallpaper Engine must be installed (owned on Steam) to download wallpapers.",
                error=True,
            )
            return
        if is_installed(item.id):
            self.show_message(f"Already installed: {item.title}")
            return
        if self._steam_linked and self._steam_username:
            self._run_steamcmd_download(
                item, self._steam_username, password="", guard=""
            )
            return
        self._prompt_steamcmd_download(item)

    def _on_ws_subscribe_fallback(self, *_args: object) -> None:
        item = self._ws_selected
        if item is None:
            return
        self._start_subscribe_watch(item)

    def _start_subscribe_watch(self, item: WorkshopItem) -> None:
        msg = open_install(item.id)
        self.show_message(msg)
        self._ws_install_btn.set_sensitive(False)
        self._ws_install_btn.set_label("Waiting for Steam…")
        self._install_cancel = False
        item_id = item.id
        title = item.title

        def worker() -> None:
            path = wait_for_install(
                item_id,
                timeout=420.0,
                interval=2.5,
                should_cancel=lambda: self._install_cancel,
            )
            GLib.idle_add(self._on_install_finished, item_id, title, path, False)

        threading.Thread(target=worker, name="ws-install", daemon=True).start()

    def _steam_login_form(
        self,
        *,
        include_password: bool = True,
        include_guard: bool = False,
        prefill_user: str = "",
    ) -> tuple[Gtk.Box, Gtk.Entry, Gtk.PasswordEntry | None, Gtk.Entry | None]:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_margin_top(8)

        user_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        user_row.append(Gtk.Label(label="Username", xalign=0, width_chars=12))
        user_entry = Gtk.Entry(
            text=prefill_user or self._steam_username,
            hexpand=True,
        )
        user_entry.set_placeholder_text("Steam account name (not display name)")
        user_row.append(user_entry)
        box.append(user_row)

        pass_entry: Gtk.PasswordEntry | None = None
        if include_password:
            pass_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            pass_row.append(Gtk.Label(label="Password", xalign=0, width_chars=12))
            pass_entry = Gtk.PasswordEntry(hexpand=True, show_peek_icon=True)
            pass_row.append(pass_entry)
            box.append(pass_row)

        guard_entry: Gtk.Entry | None = None
        if include_guard:
            guard_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            guard_row.append(Gtk.Label(label="Guard code", xalign=0, width_chars=12))
            guard_entry = Gtk.Entry(
                hexpand=True,
                placeholder_text="5-digit code from Steam Mobile",
            )
            guard_entry.set_input_purpose(Gtk.InputPurpose.DIGITS)
            guard_row.append(guard_entry)
            box.append(guard_row)

        note = Gtk.Label(
            label=(
                "Password is saved only in your GNOME Keyring. "
                "GnomePaper uses an isolated SteamCMD session — it does not "
                "share login tokens with the desktop Steam client. "
                "Disable SteamTools / Lua Tools if login keeps failing."
            ),
            wrap=True,
            xalign=0,
        )
        note.add_css_class("dim-label")
        note.add_css_class("caption")
        box.append(note)
        return box, user_entry, pass_entry, guard_entry

    def _prompt_link_steam(self) -> None:
        """Simple one-time link: auto-detect Steam username, password, optional Guard."""
        from gnomepaper_engine.workshop.keyring import lookup_steam_password
        from gnomepaper_engine.workshop.steam_account import (
            detect_desktop_steam_account,
            steam_injector_warning,
        )

        desktop = detect_desktop_steam_account()
        prefill = self._steam_username
        persona_hint = ""
        if desktop is not None:
            prefill = prefill or desktop.account_name
            if desktop.persona_name and desktop.persona_name != desktop.account_name:
                persona_hint = f" (Steam is signed in as “{desktop.persona_name}”)"
            if not self._steam_id64 and desktop.steam_id64:
                self._steam_id64 = desktop.steam_id64

        injector = steam_injector_warning()
        body = (
            f"Sign in once with the account that owns Wallpaper Engine{persona_hint}.\n"
            "Username is pre-filled from desktop Steam when possible — "
            "you usually only need your password."
        )
        if injector:
            body += f"\n\n⚠ {injector}"

        dialog = Adw.AlertDialog(heading="Link Steam", body=body)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("reset", "Reset session")
        dialog.add_response("link", "Link")
        dialog.set_response_appearance("link", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_response_appearance("reset", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("link")
        dialog.set_close_response("cancel")

        box, user_entry, pass_entry, _guard = self._steam_login_form(
            include_password=True,
            include_guard=False,
            prefill_user=prefill,
        )
        # Hint if keyring already has a password for this user
        if pass_entry is not None and prefill and lookup_steam_password(prefill):
            pass_entry.set_placeholder_text("Saved in keyring — re-enter to refresh")
        dialog.set_extra_child(box)

        def on_response(_dlg: Adw.AlertDialog, response: str) -> None:
            if response == "reset":
                from gnomepaper_engine.workshop.client import reset_steamcmd_session

                msg = reset_steamcmd_session()
                self.show_message(msg)
                # Open a fresh link dialog after reset
                GLib.idle_add(self._prompt_link_steam)
                return
            if response != "link" or pass_entry is None:
                return
            username = user_entry.get_text().strip()
            password = pass_entry.get_text()
            if username and username != self._steam_username:
                self._steam_username = username
                if self._on_steam_username_changed:
                    self._on_steam_username_changed(username)
            if not username or not password:
                self.show_message("Username and password required to link.", error=True)
                return
            # Keep password for a possible Guard follow-up (memory only)
            self._pending_link_user = username
            self._pending_link_pass = password
            self.show_message("Linking Steam…")

            def worker() -> None:
                result = link_steam_account(
                    username=username, password=password, guard_code=""
                )
                GLib.idle_add(self._on_link_finished, result)

            threading.Thread(target=worker, name="steam-link", daemon=True).start()

        dialog.connect("response", on_response)
        dialog.present(self)

    def _prompt_steam_guard_only(self) -> None:
        """Second step: only the Guard code, using password kept in memory."""
        user = getattr(self, "_pending_link_user", "") or self._steam_username
        password = getattr(self, "_pending_link_pass", "") or ""
        if not user or not password:
            self._prompt_link_steam()
            return

        dialog = Adw.AlertDialog(
            heading="Steam Guard",
            body=(
                f"Steam needs a one-time code for “{user}”.\n"
                "Open Steam Mobile (or email) and enter the code below."
            ),
        )
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("link", "Continue")
        dialog.set_response_appearance("link", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("link")

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_top(8)
        guard_entry = Gtk.Entry(
            placeholder_text="5-digit Steam Guard code",
            hexpand=True,
        )
        guard_entry.set_input_purpose(Gtk.InputPurpose.DIGITS)
        box.append(guard_entry)
        dialog.set_extra_child(box)

        def on_response(_d: Adw.AlertDialog, response: str) -> None:
            if response != "link":
                return
            code = guard_entry.get_text().strip()
            if not code:
                self.show_message("Enter the Steam Guard code.", error=True)
                return
            self.show_message("Confirming Steam Guard…")

            def worker() -> None:
                result = link_steam_account(
                    username=user, password=password, guard_code=code
                )
                GLib.idle_add(self._on_link_finished, result)

            threading.Thread(target=worker, name="steam-guard", daemon=True).start()

        dialog.connect("response", on_response)
        dialog.present(self)

    def _on_link_finished(self, result: object, had_guard: bool = False) -> bool:
        from gnomepaper_engine.workshop.client import SteamCmdResult

        assert isinstance(result, SteamCmdResult)
        if result.ok or result.linked:
            self._set_steam_linked(True)
            self._pending_link_pass = ""
            # Force fresh profile (avatar + display name) after every successful link
            self._steam_persona = ""
            self._steam_avatar_path = ""
            self._load_steam_avatar_async()
            self.show_message(result.message)
        else:
            # Keep previous linked state unless auth is clearly invalid —
            # rate limits / concurrent SteamCMD must not wipe a good link.
            if result.needs_password and not result.rate_limited and not result.needs_guard:
                self._set_steam_linked(False)
            self.show_message(result.message, error=True)
            # Guard-only follow-up — do not re-open full password form
            if result.needs_guard:
                self._prompt_steam_guard_only()
            elif getattr(result, "rate_limited", False):
                pass  # user must wait
        return GLib.SOURCE_REMOVE

    def _prompt_steamcmd_download(
        self, item: WorkshopItem, *, guard_only: bool = False
    ) -> None:
        """Ask for Steam password / Guard when keyring is empty or Guard is required."""
        from gnomepaper_engine.workshop.keyring import lookup_steam_password

        saved = lookup_steam_password(self._steam_username) if self._steam_username else None

        if guard_only and self._steam_username and saved:
            # Simple Guard-only dialog — easier approval flow
            dialog = Adw.AlertDialog(
                heading="Steam Guard code",
                body=(
                    f"Steam needs a one-time code to download “{item.title}”.\n"
                    "Open your Steam Mobile Authenticator (or email) and enter the code."
                ),
            )
            dialog.add_response("cancel", "Cancel")
            dialog.add_response("download", "Continue")
            dialog.set_response_appearance("download", Adw.ResponseAppearance.SUGGESTED)
            dialog.set_default_response("download")
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            box.set_margin_top(8)
            guard_entry = Gtk.Entry(
                placeholder_text="5-digit code from Steam Guard",
                hexpand=True,
            )
            guard_entry.set_input_purpose(Gtk.InputPurpose.DIGITS)
            box.append(guard_entry)
            dialog.set_extra_child(box)

            def on_guard(_d: Adw.AlertDialog, response: str) -> None:
                if response != "download":
                    return
                self._run_steamcmd_download(
                    item,
                    self._steam_username,
                    saved or "",
                    guard_entry.get_text().strip(),
                )

            dialog.connect("response", on_guard)
            dialog.present(self)
            return

        dialog = Adw.AlertDialog(
            heading="Link Steam to download",
            body=(
                f"Download “{item.title}”.\n"
                "Account must own Wallpaper Engine.\n"
                "Password is saved in your GNOME Keyring (not in a text file) "
                "so you won't re-type it every time."
            ),
        )
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("download", "Save & download")
        dialog.set_response_appearance("download", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("download")
        dialog.set_close_response("cancel")
        box, user_entry, pass_entry, guard_entry = self._steam_login_form(
            include_password=True,
            include_guard=True,
        )
        if saved and pass_entry is not None:
            pass_entry.set_placeholder_text("Saved in keyring — leave blank to reuse")
        dialog.set_extra_child(box)

        def on_response(_dlg: Adw.AlertDialog, response: str) -> None:
            if response != "download" or pass_entry is None:
                return
            username = user_entry.get_text().strip()
            password = pass_entry.get_text() or (saved or "")
            guard = guard_entry.get_text().strip() if guard_entry is not None else ""
            if username and username != self._steam_username:
                self._steam_username = username
                if self._on_steam_username_changed:
                    self._on_steam_username_changed(username)
            if not username or not password:
                self.show_message(
                    "Username and password required (or Link Steam first).",
                    error=True,
                )
                return
            self._run_steamcmd_download(item, username, password, guard)

        dialog.connect("response", on_response)
        dialog.present(self)

    def _run_steamcmd_download(
        self,
        item: WorkshopItem,
        username: str,
        password: str,
        guard: str,
    ) -> None:
        self._ws_install_btn.set_sensitive(False)
        self._ws_install_btn.set_label("Downloading…")
        self.show_message(f"Downloading {item.title}…")

        def worker() -> None:
            def prog(msg: str) -> None:
                GLib.idle_add(self.show_message, msg)

            result = download_via_steamcmd(
                item.id,
                username=username,
                password=password,
                guard_code=guard,
                # Always try the local SteamCMD session first, then keyring password.
                # Re-sending the password every time fights multi-PC / multi-window use.
                use_cached_login=True,
                progress=prog,
            )
            GLib.idle_add(self._on_steamcmd_finished, item.id, item.title, result)

        threading.Thread(target=worker, name="steamcmd-dl", daemon=True).start()

    def _on_steamcmd_finished(
        self, item_id: str, title: str, result: object
    ) -> bool:
        from gnomepaper_engine.workshop.client import SteamCmdResult

        assert isinstance(result, SteamCmdResult)
        self._ws_install_btn.set_sensitive(True)
        if result.linked:
            self._set_steam_linked(True)
        if getattr(result, "rate_limited", False):
            self._ws_install_btn.set_label("Get via Steam")
            self.show_message(result.message, error=True)
            return GLib.SOURCE_REMOVE
        if result.needs_guard:
            self._ws_install_btn.set_label("Get via Steam")
            self.show_message(result.message, error=True)
            item = self._ws_selected
            if item is not None and item.id == item_id:
                self._prompt_steamcmd_download(item, guard_only=True)
            return GLib.SOURCE_REMOVE
        if result.needs_password:
            self._ws_install_btn.set_label("Get via Steam")
            self.show_message(result.message, error=True)
            item = self._ws_selected
            # Only open password dialog if keyring is empty — avoid re-auth loops
            from gnomepaper_engine.workshop.keyring import lookup_steam_password

            has_saved = bool(
                self._steam_username and lookup_steam_password(self._steam_username)
            )
            if item is not None and item.id == item_id and not has_saved:
                self._prompt_steamcmd_download(item, guard_only=False)
            elif has_saved:
                self.show_message(
                    result.message
                    + " If this keeps happening, close other GnomePaper windows "
                    "and re-link once (top-left).",
                    error=True,
                )
            return GLib.SOURCE_REMOVE

        if not result.ok:
            self._ws_install_btn.set_label("Get via Steam")
            self.show_message(result.message, error=True)
            return GLib.SOURCE_REMOVE

        return self._on_install_finished(item_id, title, result.path, True)

    def _on_install_finished(
        self,
        item_id: str,
        title: str,
        path: Path | None,
        via_steamcmd: bool,
    ) -> bool:
        self._ws_install_btn.set_sensitive(True)
        if path is None:
            self._ws_install_btn.set_label("Get via Steam")
            self.show_message(
                "Download not found yet — try Direct download or Subscribe page.",
                error=True,
            )
            return GLib.SOURCE_REMOVE

        self._ws_install_btn.set_label("Installed")
        how = "SteamCMD" if via_steamcmd else "Steam"
        self.show_message(f"Ready ({how}): {title}")
        child = self._ws_flow.get_first_child()
        while child is not None:
            if isinstance(child, WorkshopCard) and child.item.id == item_id:
                child.set_installed(True)
            child = child.get_next_sibling()
        self._on_refresh()
        self._stack.set_visible_child_name("installed")
        return GLib.SOURCE_REMOVE

    def _on_ws_open_browser(self, *_args: object) -> None:
        item = self._ws_selected
        if item is None:
            return
        url = f"https://steamcommunity.com/sharedfiles/filedetails/?id={item.id}"
        Gtk.show_uri(self, url, Gdk.CURRENT_TIME)

    # ── settings ──────────────────────────────────────────────────

    def _on_mute_switch(self, switch: Gtk.Switch, *_args: object) -> None:
        self._mute_audio = switch.get_active()
        self._volume_scale.set_sensitive(not self._mute_audio)
        if self._on_mute_changed is not None:
            self._on_mute_changed(self._mute_audio)

    def _on_volume_changed(self, scale: Gtk.Scale) -> None:
        self._audio_volume = int(scale.get_value())
        if self._on_volume_changed is not None:
            self._on_volume_changed(self._audio_volume)

    def _on_mouse_switch(self, switch: Gtk.Switch, *_args: object) -> None:
        self._mouse_interaction = switch.get_active()
        if self._on_mouse_changed is not None:
            self._on_mouse_changed(self._mouse_interaction)

    def _on_fps_changed(self, spin: Gtk.SpinButton) -> None:
        self._target_fps = int(spin.get_value())
        if self._on_fps_changed is not None:
            self._on_fps_changed(self._target_fps)

    def _on_prefer_steamcmd_switch(self, switch: Gtk.Switch, *_args: object) -> None:
        self._prefer_steamcmd = switch.get_active()
        if self._on_prefer_steamcmd_changed is not None:
            self._on_prefer_steamcmd_changed(self._prefer_steamcmd)
