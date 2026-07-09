"""Scan Wallpaper Engine workshop (and local) packages into a library."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from gnomepaper_engine.steam.models import WallpaperItem, WallpaperType
from gnomepaper_engine.steam.paths import (
    discover_steam_installs,
    wallpaper_engine_install_dirs,
    workshop_content_dirs,
)

log = logging.getLogger(__name__)


class WallpaperLibrary:
    """In-memory collection of discovered wallpapers."""

    def __init__(self, items: list[WallpaperItem] | None = None) -> None:
        self.items: list[WallpaperItem] = items or []

    def __len__(self) -> int:
        return len(self.items)

    def search(self, query: str) -> list[WallpaperItem]:
        q = query.strip().lower()
        if not q:
            return list(self.items)
        return [
            item
            for item in self.items
            if q in item.title.lower()
            or q in item.id.lower()
            or q in item.type_label.lower()
            or any(q in t.lower() for t in item.tags)
        ]

    def by_id(self, wallpaper_id: str) -> WallpaperItem | None:
        for item in self.items:
            if item.id == wallpaper_id:
                return item
        return None


def _detect_type(folder: Path, meta: dict) -> WallpaperType:
    type_raw = str(meta.get("type", meta.get("general", {}).get("type", ""))).lower()
    mapping = {
        "video": WallpaperType.VIDEO,
        "scene": WallpaperType.SCENE,
        "web": WallpaperType.WEB,
        "application": WallpaperType.APPLICATION,
    }
    if type_raw in mapping:
        return mapping[type_raw]

    # Heuristics from files on disk
    names = {p.name.lower() for p in folder.iterdir()} if folder.is_dir() else set()
    if any(n.endswith((".mp4", ".webm", ".mkv", ".avi")) for n in names) or "video" in type_raw:
        return WallpaperType.VIDEO
    if "scene.json" in names or "scene.pkg" in names:
        return WallpaperType.SCENE
    if "index.html" in names:
        return WallpaperType.WEB
    return WallpaperType.UNKNOWN


def _load_project_meta(folder: Path) -> dict:
    for name in ("project.json", "project.json.json"):
        path = folder / name
        if not path.is_file():
            continue
        try:
            return json.loads(path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, json.JSONDecodeError) as exc:
            log.debug("Failed to parse %s: %s", path, exc)
    return {}


def _find_preview(folder: Path, meta: dict) -> Path | None:
    for key in ("preview", "preview_image", "thumbnail"):
        rel = meta.get(key)
        if isinstance(rel, str):
            candidate = folder / rel
            if candidate.is_file():
                return candidate
    for name in (
        "preview.gif",
        "preview.jpg",
        "preview.jpeg",
        "preview.png",
        "preview.webp",
    ):
        candidate = folder / name
        if candidate.is_file():
            return candidate
    return None


def _title_from_meta(folder: Path, meta: dict, fallback_id: str) -> str:
    for key in ("title", "name"):
        val = meta.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    general = meta.get("general")
    if isinstance(general, dict):
        for key in ("title", "name"):
            val = general.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
    return fallback_id


def _item_from_folder(folder: Path, *, workshop: bool) -> WallpaperItem | None:
    if not folder.is_dir():
        return None
    meta = _load_project_meta(folder)
    wallpaper_id = folder.name
    return WallpaperItem(
        id=wallpaper_id,
        title=_title_from_meta(folder, meta, wallpaper_id),
        path=folder,
        wallpaper_type=_detect_type(folder, meta),
        preview_path=_find_preview(folder, meta),
        workshop=workshop,
        meta=meta,
    )


def scan_library(extra_library_paths: list[str] | None = None) -> WallpaperLibrary:
    """Discover Steam + Wallpaper Engine workshop items."""
    installs = discover_steam_installs(extra_library_paths)
    items: list[WallpaperItem] = []
    seen_ids: set[str] = set()

    if not installs:
        log.info("No Steam installs found")
        return WallpaperLibrary()

    for install in installs:
        log.info("Steam install (%s): %s", install.kind, install.root)
        for we_dir in wallpaper_engine_install_dirs(install):
            log.info("Wallpaper Engine install: %s", we_dir)

        for workshop_dir in workshop_content_dirs(install):
            log.info("Scanning workshop: %s", workshop_dir)
            try:
                children = sorted(workshop_dir.iterdir(), key=lambda p: p.name)
            except OSError as exc:
                log.warning("Cannot list %s: %s", workshop_dir, exc)
                continue
            for child in children:
                if not child.is_dir() or child.name in seen_ids:
                    continue
                item = _item_from_folder(child, workshop=True)
                if item is None:
                    continue
                items.append(item)
                seen_ids.add(item.id)

    items.sort(key=lambda i: i.title.lower())
    log.info("Discovered %d wallpaper(s)", len(items))
    return WallpaperLibrary(items)
