"""Data models for Steam installs and Wallpaper Engine items."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class WallpaperType(str, Enum):
    """Wallpaper Engine content kinds we care about."""

    VIDEO = "video"
    SCENE = "scene"
    WEB = "web"
    APPLICATION = "application"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class SteamInstall:
    """A discovered Steam root (native, Flatpak, custom library, …)."""

    root: Path
    kind: str  # "native" | "flatpak" | "library" | "custom"
    library_folders: tuple[Path, ...] = ()

    @property
    def steamapps(self) -> Path:
        return self.root / "steamapps"


@dataclass
class WallpaperItem:
    """One workshop (or local) wallpaper package."""

    id: str
    title: str
    path: Path
    wallpaper_type: WallpaperType = WallpaperType.UNKNOWN
    preview_path: Path | None = None
    workshop: bool = True
    tags: tuple[str, ...] = ()
    # Raw project.json / package metadata when available
    meta: dict = field(default_factory=dict, repr=False)

    @property
    def type_label(self) -> str:
        return self.wallpaper_type.value.replace("_", " ").title()
