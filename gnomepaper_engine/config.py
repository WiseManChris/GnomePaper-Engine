"""Application configuration and XDG paths."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path


def xdg_config_home() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))


def xdg_data_home() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))


def xdg_cache_home() -> Path:
    return Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))


@dataclass
class AppConfig:
    """User preferences persisted as JSON under XDG config."""

    # Empty = auto-discover Steam library folders
    steam_library_paths: list[str] = field(default_factory=list)
    last_wallpaper_id: str | None = None
    mute_audio: bool = True
    target_fps: int = 30
    # "all" or a connector name later (multi-monitor)
    apply_to: str = "all"

    @classmethod
    def config_dir(cls) -> Path:
        return xdg_config_home() / "gnomepaper-engine"

    @classmethod
    def config_path(cls) -> Path:
        return cls.config_dir() / "config.json"

    @classmethod
    def cache_dir(cls) -> Path:
        path = xdg_cache_home() / "gnomepaper-engine"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @classmethod
    def load(cls) -> AppConfig:
        path = cls.config_path()
        if not path.is_file():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
            return cls(**{k: v for k, v in data.items() if k in known})
        except (OSError, json.JSONDecodeError, TypeError):
            return cls()

    def save(self) -> None:
        path = self.config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(asdict(self), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
