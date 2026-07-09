"""Thumbnail card for Workshop browse results."""

from __future__ import annotations

from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")

from gi.repository import Gdk, GdkPixbuf, GLib, Gtk  # noqa: E402

from gnomepaper_engine.ui.previews import THUMB_H, THUMB_W  # noqa: E402
from gnomepaper_engine.workshop.client import WorkshopItem, cache_remote_preview  # noqa: E402


class WorkshopCard(Gtk.FlowBoxChild):
    """Workshop result tile with remote preview + install state."""

    def __init__(
        self,
        item: WorkshopItem,
        *,
        installed: bool,
        cache_dir: Path,
    ) -> None:
        super().__init__()
        self.item = item
        self._installed = installed
        self._cache_dir = cache_dir
        self.set_size_request(THUMB_W + 8, THUMB_H + 56)

        overlay = Gtk.Overlay()
        overlay.set_overflow(Gtk.Overflow.HIDDEN)
        overlay.add_css_class("card")

        self._picture = Gtk.Picture()
        self._picture.set_content_fit(Gtk.ContentFit.COVER)
        self._picture.set_size_request(THUMB_W, THUMB_H)
        self._picture.set_can_shrink(False)

        placeholder = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            valign=Gtk.Align.CENTER,
            halign=Gtk.Align.CENTER,
            spacing=6,
        )
        placeholder.set_size_request(THUMB_W, THUMB_H)
        placeholder.add_css_class("view")
        icon = Gtk.Image.new_from_icon_name("folder-download-symbolic")
        icon.set_pixel_size(40)
        icon.add_css_class("dim-label")
        placeholder.append(icon)
        overlay.set_child(self._picture)
        # show placeholder until image loads by using empty paintable + overlay icon
        self._ph = placeholder

        # Badges
        badge_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        badge_box.set_halign(Gtk.Align.START)
        badge_box.set_valign(Gtk.Align.START)
        badge_box.set_margin_top(8)
        badge_box.set_margin_start(8)

        if item.subs_label:
            sub = self._pill(item.subs_label)
            badge_box.append(sub)
        if item.size_label:
            badge_box.append(self._pill(item.size_label))
        overlay.add_overlay(badge_box)

        self._status_badge = self._pill("Installed" if installed else "Workshop")
        self._status_badge.set_halign(Gtk.Align.END)
        self._status_badge.set_valign(Gtk.Align.START)
        self._status_badge.set_margin_top(8)
        self._status_badge.set_margin_end(8)
        overlay.add_overlay(self._status_badge)

        title = Gtk.Label(
            label=item.title or item.id,
            xalign=0,
            ellipsize=3,
            max_width_chars=32,
        )
        title.add_css_class("caption")
        title.set_margin_top(6)
        title.set_margin_start(4)
        title.set_margin_end(4)

        meta = Gtk.Label(
            label=self._meta_line(),
            xalign=0,
            ellipsize=3,
        )
        meta.add_css_class("caption")
        meta.add_css_class("dim-label")
        meta.set_margin_start(4)
        meta.set_margin_end(4)
        meta.set_margin_bottom(4)

        column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        column.set_margin_top(6)
        column.set_margin_bottom(6)
        column.set_margin_start(6)
        column.set_margin_end(6)
        column.append(overlay)
        column.append(title)
        column.append(meta)
        self.set_child(column)

        GLib.idle_add(self._load_preview)

    def set_installed(self, installed: bool) -> None:
        self._installed = installed
        # refresh badge label
        child = self._status_badge.get_first_child()
        if isinstance(child, Gtk.Label):
            child.set_label("Installed" if installed else "Workshop")

    def _meta_line(self) -> str:
        parts = [p for p in (self.item.subs_label, self.item.size_label) if p]
        return " · ".join(parts) if parts else f"ID {self.item.id}"

    @staticmethod
    def _pill(text: str) -> Gtk.Box:
        box = Gtk.Box()
        box.add_css_class("osd")
        lbl = Gtk.Label(label=text)
        lbl.add_css_class("caption-heading")
        lbl.set_margin_start(6)
        lbl.set_margin_end(6)
        lbl.set_margin_top(2)
        lbl.set_margin_bottom(2)
        box.append(lbl)
        return box

    def _load_preview(self) -> bool:
        url = self.item.preview_url
        if not url:
            return GLib.SOURCE_REMOVE
        dest = self._cache_dir / f"ws_{self.item.id}.jpg"
        path = dest if dest.is_file() else cache_remote_preview(url, dest)
        if path is None:
            return GLib.SOURCE_REMOVE
        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                str(path), THUMB_W, THUMB_H, True
            )
            if pixbuf is not None:
                self._picture.set_paintable(Gdk.Texture.new_for_pixbuf(pixbuf))
        except Exception:
            pass
        return GLib.SOURCE_REMOVE
