"""Thumbnail card for the wallpaper library grid (WE-style)."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import Gtk  # noqa: E402

from gnomepaper_engine.steam.models import WallpaperItem  # noqa: E402
from gnomepaper_engine.ui.previews import THUMB_H, THUMB_W, PreviewCache  # noqa: E402


class WallpaperCard(Gtk.FlowBoxChild):
    """One wallpaper tile: preview image, type badge, title."""

    def __init__(self, item: WallpaperItem, cache: PreviewCache) -> None:
        super().__init__()
        self.item = item
        self.set_size_request(THUMB_W + 8, THUMB_H + 44)

        overlay = Gtk.Overlay()
        overlay.set_overflow(Gtk.Overflow.HIDDEN)
        overlay.add_css_class("card")

        texture = cache.get(item.preview_path, width=THUMB_W, height=THUMB_H)
        if texture is not None:
            picture = Gtk.Picture.new_for_paintable(texture)
            picture.set_content_fit(Gtk.ContentFit.COVER)
            picture.set_size_request(THUMB_W, THUMB_H)
            picture.set_can_shrink(False)
            overlay.set_child(picture)
        else:
            placeholder = Gtk.Box(
                orientation=Gtk.Orientation.VERTICAL,
                valign=Gtk.Align.CENTER,
                halign=Gtk.Align.CENTER,
                spacing=8,
            )
            placeholder.set_size_request(THUMB_W, THUMB_H)
            placeholder.add_css_class("view")
            icon = Gtk.Image.new_from_icon_name(self._icon_name(item))
            icon.set_pixel_size(48)
            icon.add_css_class("dim-label")
            placeholder.append(icon)
            lbl = Gtk.Label(label=item.type_label)
            lbl.add_css_class("dim-label")
            placeholder.append(lbl)
            overlay.set_child(placeholder)

        # Type badge
        badge = Gtk.Label(label=item.type_label)
        badge.add_css_class("caption-heading")
        badge_box = Gtk.Box(
            margin_top=8,
            margin_start=8,
            margin_end=4,
            margin_bottom=4,
            spacing=0,
        )
        badge_box.add_css_class("osd")
        badge_box.set_halign(Gtk.Align.START)
        badge_box.set_valign(Gtk.Align.START)
        badge.set_margin_start(6)
        badge.set_margin_end(6)
        badge.set_margin_top(2)
        badge.set_margin_bottom(2)
        badge_box.append(badge)
        overlay.add_overlay(badge_box)

        title = Gtk.Label(
            label=item.title,
            xalign=0,
            ellipsize=3,
            max_width_chars=32,
        )
        title.add_css_class("caption")
        title.set_margin_top(6)
        title.set_margin_start(4)
        title.set_margin_end(4)
        title.set_margin_bottom(4)

        column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        column.set_margin_top(6)
        column.set_margin_bottom(6)
        column.set_margin_start(6)
        column.set_margin_end(6)
        column.append(overlay)
        column.append(title)
        self.set_child(column)

    @staticmethod
    def _icon_name(item: WallpaperItem) -> str:
        t = item.wallpaper_type.value
        if t == "scene":
            return "applications-graphics-symbolic"
        if t == "web":
            return "web-browser-symbolic"
        if t == "video":
            return "video-x-generic-symbolic"
        return "image-x-generic-symbolic"
