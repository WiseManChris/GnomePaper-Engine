"""Fetch public Steam profile metadata (avatar) for the linked account chip."""

from __future__ import annotations

import logging
import re
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

_USER_AGENT = "GnomePaper-Engine/0.1 (Steam profile avatar)"


@dataclass
class SteamProfile:
    username: str
    steam_id64: str = ""
    persona_name: str = ""
    avatar_url: str = ""  # preferably medium or full


def fetch_steam_profile(username: str) -> SteamProfile | None:
    """
    Load public profile via Steam Community XML.

    Tries /id/<username> first (vanity), then treats username as steamid64
    if numeric.
    """
    username = (username or "").strip()
    if not username:
        return None

    urls = [f"https://steamcommunity.com/id/{username}/?xml=1"]
    if username.isdigit():
        urls.insert(0, f"https://steamcommunity.com/profiles/{username}/?xml=1")

    for url in urls:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = resp.read()
            profile = _parse_profile_xml(data, username)
            if profile is not None and (profile.avatar_url or profile.steam_id64):
                return profile
        except (urllib.error.URLError, TimeoutError, OSError, ET.ParseError) as exc:
            log.debug("profile fetch failed for %s: %s", url, exc)
            continue
    return None


def _parse_profile_xml(data: bytes, fallback_user: str) -> SteamProfile | None:
    root = ET.fromstring(data)
    # Error response: <response><error>…</error></response>
    err = root.findtext("error")
    if err:
        log.debug("steam profile error: %s", err)
        return None

    steam_id = (root.findtext("steamID64") or "").strip()
    persona = (root.findtext("steamID") or "").strip()  # display name in XML
    avatar = (
        (root.findtext("avatarFull") or "").strip()
        or (root.findtext("avatarMedium") or "").strip()
        or (root.findtext("avatarIcon") or "").strip()
    )
    if not steam_id and not avatar:
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


def avatar_cache_path(cache_dir: Path, username: str) -> Path:
    safe = re.sub(r"[^a-zA-Z0-9_.-]+", "_", username.strip()) or "user"
    return cache_dir / f"steam_avatar_{safe}.jpg"
