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
    # Audio on by default (Windows WE plays wallpaper audio)
    mute_audio: bool = False
    # 0–100, used when not muted
    audio_volume: int = 70
    # Scene mouse / eye-follow / parallax (linux-wallpaperengine)
    mouse_interaction: bool = True
    target_fps: int = 30
    # "all" or a connector name later (multi-monitor)
    apply_to: str = "all"
    # Steam account for direct workshop downloads via SteamCMD (password never stored)
    steam_username: str = ""
    # True after a successful SteamCMD login (credentials cached by SteamCMD)
    steam_linked: bool = False
    # Public profile vanity / display cache
    steam_persona_name: str = ""
    steam_id64: str = ""
    steam_avatar_path: str = ""  # local cached avatar file
    # Prefer SteamCMD download over Subscribe-in-browser when credentials available
    prefer_steamcmd_download: bool = True
    # Desktop session (v1.0)
    close_to_background: bool = True
    start_minimized: bool = False
    launch_at_login: bool = False
    restore_last_on_launch: bool = True
    # Appearance (1.1.2)
    # system | light | dark | oled
    ui_theme: str = "system"
    # blue | teal | purple | orange
    accent_color: str = "blue"
    # Optional absolute path to linux-wallpaperengine (empty = auto-detect)
    lwe_binary_path: str = ""
    # Last auto-detected path + SHA-256 (checksum cache for faster, reliable re-detect)
    lwe_detected_path: str = ""
    lwe_binary_sha256: str = ""

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
