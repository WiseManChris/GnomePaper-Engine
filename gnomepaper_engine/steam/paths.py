"""Locate Steam installs and Wallpaper Engine content roots."""

from __future__ import annotations

import re
from pathlib import Path

from gnomepaper_engine.steam.models import SteamInstall

# Wallpaper Engine on Steam
WALLPAPER_ENGINE_APP_ID = 431960

_VDF_PATH_RE = re.compile(r'"path"\s+"([^"]+)"')


def wallpaper_engine_app_id() -> int:
    return WALLPAPER_ENGINE_APP_ID


def _expand(path: str | Path) -> Path:
    return Path(path).expanduser().resolve()


def _candidate_steam_roots() -> list[tuple[Path, str]]:
    home = Path.home()
    return [
        (home / ".local/share/Steam", "native"),
        (home / ".steam/steam", "native"),
        (home / ".steam/root", "native"),
        (home / ".var/app/com.valvesoftware.Steam/.local/share/Steam", "flatpak"),
        (home / ".var/app/com.valvesoftware.Steam/data/Steam", "flatpak"),
        # Snap (less common)
        (home / "snap/steam/common/.local/share/Steam", "snap"),
    ]


def parse_libraryfolders_vdf(vdf_path: Path) -> list[Path]:
    """Best-effort parse of libraryfolders.vdf for extra library paths."""
    if not vdf_path.is_file():
        return []
    try:
        text = vdf_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    paths: list[Path] = []
    for match in _VDF_PATH_RE.finditer(text):
        raw = match.group(1).replace("\\\\", "/").replace("\\", "/")
        p = _expand(raw)
        if p.is_dir() and p not in paths:
            paths.append(p)
    return paths


def discover_steam_installs(
    extra_library_paths: list[str] | None = None,
) -> list[SteamInstall]:
    """Return unique Steam installs found on this system."""
    found: list[SteamInstall] = []
    seen_roots: set[Path] = set()

    for root, kind in _candidate_steam_roots():
        try:
            root = root.resolve()
        except OSError:
            continue
        if not root.is_dir() or root in seen_roots:
            continue
        # Require steamapps or steam.cfg-ish layout
        if not (root / "steamapps").is_dir() and not (root / "steam.sh").exists():
            # Flatpak sometimes only has steamapps under root
            if not any(root.iterdir()) if root.exists() else True:
                continue

        libraries = parse_libraryfolders_vdf(root / "steamapps" / "libraryfolders.vdf")
        if root not in libraries and (root / "steamapps").is_dir():
            libraries = [root, *libraries]

        found.append(
            SteamInstall(
                root=root,
                kind=kind,
                library_folders=tuple(libraries),
            )
        )
        seen_roots.add(root)

    for raw in extra_library_paths or []:
        lib = _expand(raw)
        if not lib.is_dir() or lib in seen_roots:
            continue
        steamapps = lib / "steamapps" if (lib / "steamapps").is_dir() else lib
        root = steamapps.parent if steamapps.name == "steamapps" else lib
        if root in seen_roots:
            continue
        found.append(
            SteamInstall(
                root=root,
                kind="custom",
                library_folders=(root,),
            )
        )
        seen_roots.add(root)

    return found


def workshop_content_dirs(install: SteamInstall) -> list[Path]:
    """Workshop content for Wallpaper Engine under each library folder."""
    dirs: list[Path] = []
    libraries = install.library_folders or (install.root,)
    for lib in libraries:
        candidate = lib / "steamapps" / "workshop" / "content" / str(WALLPAPER_ENGINE_APP_ID)
        if not candidate.is_dir():
            # lib might already be …/steamapps
            alt = lib / "workshop" / "content" / str(WALLPAPER_ENGINE_APP_ID)
            candidate = alt if alt.is_dir() else candidate
        if candidate.is_dir() and candidate not in dirs:
            dirs.append(candidate)
    return dirs


def wallpaper_engine_install_dirs(install: SteamInstall) -> list[Path]:
    """Directories where the Wallpaper Engine app itself may be installed."""
    dirs: list[Path] = []
    libraries = install.library_folders or (install.root,)
    for lib in libraries:
        for rel in (
            Path("steamapps") / "common" / "wallpaper_engine",
            Path("common") / "wallpaper_engine",
        ):
            candidate = lib / rel
            if candidate.is_dir() and candidate not in dirs:
                dirs.append(candidate)
    return dirs
