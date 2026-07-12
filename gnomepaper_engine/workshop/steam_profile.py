"""Fetch public Steam profile metadata (avatar + display name)."""

from __future__ import annotations

import logging
import re
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

_USER_AGENT = "GnomePaper-Engine/1.1 (Steam profile)"


@dataclass
class SteamProfile:
    username: str
    steam_id64: str = ""
    persona_name: str = ""
    avatar_url: str = ""


def fetch_steam_profile(
    username: str = "",
    *,
    steam_id64: str = "",
) -> SteamProfile | None:
    """
    Load public profile via Steam Community XML.

    Prefer steam_id64 (stable). Fall back to vanity /id/<username>.
    """
    urls: list[str] = []
    sid = (steam_id64 or "").strip()
    user = (username or "").strip()

    if sid.isdigit():
        urls.append(f"https://steamcommunity.com/profiles/{sid}/?xml=1")
    if user:
        if user.isdigit() and user not in urls:
            urls.append(f"https://steamcommunity.com/profiles/{user}/?xml=1")
        urls.append(f"https://steamcommunity.com/id/{user}/?xml=1")

    # Also try steamcmd-resolved id from local config
    if not sid:
        local_id = read_steamcmd_steamid64()
        if local_id:
            urls.insert(0, f"https://steamcommunity.com/profiles/{local_id}/?xml=1")

    seen: set[str] = set()
    for url in urls:
        if url in seen:
            continue
        seen.add(url)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = resp.read()
            profile = _parse_profile_xml(data, user or sid)
            if profile is not None and (profile.avatar_url or profile.persona_name):
                return profile
        except (urllib.error.URLError, TimeoutError, OSError, ET.ParseError) as exc:
            log.debug("profile fetch failed for %s: %s", url, exc)
            continue
    return None


def read_steamcmd_steamid64() -> str | None:
    """Best-effort: read most recent SteamID from SteamCMD loginusers.vdf."""
    from gnomepaper_engine.workshop.client import steamcmd_dir

    candidates = [
        steamcmd_dir() / "config" / "loginusers.vdf",
        steamcmd_dir() / "config" / "config.vdf",
        Path.home() / ".steam" / "steam" / "config" / "loginusers.vdf",
        Path.home() / ".local" / "share" / "Steam" / "config" / "loginusers.vdf",
    ]
    id_re = re.compile(r'"(\d{17})"')
    for path in candidates:
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        # Prefer MostRecent "1" block if present
        blocks = re.split(r'"(\d{17})"\s*\{', text)
        # blocks: preamble, id1, body1, id2, body2, ...
        best: str | None = None
        for i in range(1, len(blocks) - 1, 2):
            sid = blocks[i]
            body = blocks[i + 1]
            if '"MostRecent"' in body and '"1"' in body.split("MostRecent", 1)[-1][:40]:
                return sid
            best = sid
        ids = id_re.findall(text)
        if ids:
            return best or ids[-1]
    return None


def _parse_profile_xml(data: bytes, fallback_user: str) -> SteamProfile | None:
    root = ET.fromstring(data)
    err = root.findtext("error")
    if err:
        log.debug("steam profile error: %s", err)
        return None

    steam_id = (root.findtext("steamID64") or "").strip()
    persona = (root.findtext("steamID") or "").strip()
    avatar = (
        (root.findtext("avatarFull") or "").strip()
        or (root.findtext("avatarMedium") or "").strip()
        or (root.findtext("avatarIcon") or "").strip()
    )
    if not steam_id and not avatar and not persona:
        return None
    return SteamProfile(
        username=fallback_user,
        steam_id64=steam_id,
        persona_name=persona or fallback_user,
        avatar_url=avatar,
    )


def cache_avatar(url: str, dest: Path) -> Path | None:
    if not url:
        return None
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
        with urllib.request.urlopen(req, timeout=15) as resp:
            dest.write_bytes(resp.read())
        return dest if dest.is_file() and dest.stat().st_size > 0 else None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        log.debug("avatar cache failed: %s", exc)
        return None


def avatar_cache_path(cache_dir: Path, key: str) -> Path:
    safe = re.sub(r"[^a-zA-Z0-9_.-]+", "_", (key or "user").strip()) or "user"
    return cache_dir / f"steam_avatar_{safe}.jpg"
