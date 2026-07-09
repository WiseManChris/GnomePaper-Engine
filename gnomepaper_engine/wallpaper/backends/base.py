"""Abstract wallpaper backend."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gnomepaper_engine.config import AppConfig
    from gnomepaper_engine.steam.models import WallpaperItem


@dataclass
class BackendResult:
    ok: bool
    message: str = ""


class WallpaperBackend(ABC):
    """Plays or applies one class of wallpaper content."""

    name: str = "base"

    @abstractmethod
    def supports(self, item: WallpaperItem) -> bool:
        raise NotImplementedError

    @abstractmethod
    def apply(self, item: WallpaperItem, config: AppConfig) -> BackendResult:
        raise NotImplementedError

    @abstractmethod
    def stop(self) -> None:
        raise NotImplementedError

    @property
    @abstractmethod
    def is_running(self) -> bool:
        raise NotImplementedError
