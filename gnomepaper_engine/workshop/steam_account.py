"""Detect the desktop Steam account and common Steam injectors (SteamTools / Lua Tools)."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class DesktopSteamAccount:
    """Account currently marked MostRecent in the desktop Steam client."""

    account_name: str  # login name (what SteamCMD wants)
    persona_name: str = ""
    steam_id64: str = ""


def _loginusers_candidates() -> list[Path]:
    home = Path.home()
    return [
        home / ".local" / "share" / "Steam" / "config" / "loginusers.vdf",
        home / ".steam" / "steam" / "config" / "loginusers.vdf",
        home / ".steam" / "root" / "config" / "loginusers.vdf",
        home / ".var" / "app" / "com.valvesoftware.Steam" / ".local" / "share" / "Steam" / "config" / "loginusers.vdf",
    ]


def detect_desktop_steam_account() -> DesktopSteamAccount | None:
    """
    Read desktop Steam's loginusers.vdf for the most recent account.

    This is the account already signed into the Steam client — we pre-fill
    the Link dialog so users only type a password (and Guard if asked).
    """
    for path in _loginusers_candidates():
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            log.debug("read loginusers failed %s: %s", path, exc)
            continue
        acct = _parse_loginusers(text)
        if acct is not None:
            log.info(
                "Detected desktop Steam account %s (%s) from %s",
                acct.account_name,
                acct.persona_name,
                path,
            )
            return acct
    return None


def _parse_loginusers(text: str) -> DesktopSteamAccount | None:
    # Split into "7656…" { body } blocks
    parts = re.split(r'"(\d{17})"\s*\{', text)
    # parts: preamble, id, body, id, body, ...
    best: DesktopSteamAccount | None = None
    for i in range(1, len(parts) - 1, 2):
        sid = parts[i]
        body = parts[i + 1]
        account = _vdf_str(body, "AccountName")
        persona = _vdf_str(body, "PersonaName")
        if not account:
            continue
        recent = _vdf_str(body, "MostRecent") == "1"
        cand = DesktopSteamAccount(
            account_name=account,
            persona_name=persona or account,
            steam_id64=sid,
        )
        if recent:
            return cand
        best = cand
    return best


def _vdf_str(body: str, key: str) -> str:
    # "Key"\t\t"value"  or "Key""value"
    m = re.search(rf'"{re.escape(key)}"\s*"([^"]*)"', body)
    return (m.group(1) if m else "").strip()


def steam_injector_warning() -> str | None:
    """
    Detect SteamTools / “Lua Tools” style injectors that break SteamCMD auth.

    These tools patch the Steam client and frequently cause endless Guard /
    login failures when another process (SteamCMD) tries to sign in.
    """
    home = Path.home()
    markers: list[Path] = []
    roots = [
        home / ".local" / "share" / "Steam",
        home / ".steam" / "steam",
        home / ".steam" / "root",
    ]
    names = (
        "SteamTools",
        "steamtools",
        "stplug-in",
        "hid.dll",  # common injector name on Windows layers / wine
        "version.dll",
        "GreenLuma",
        "greenluma",
        "CreamAPI",
        "steam_api_emu",
        "LuaTools",
        "luatools",
    )
    for root in roots:
        if not root.is_dir():
            continue
        for name in names:
            # Shallow checks — full recursive walk is slow
            for p in (
                root / name,
                root / "config" / name,
                root / "bin" / name,
                root / "package" / name,
            ):
                if p.exists():
                    markers.append(p)
        # Look for .lua unlock scripts that SteamTools uses
        try:
            for p in root.glob("*.lua"):
                markers.append(p)
                break
            st = root / "config" / "stplug-in"
            if st.exists():
                markers.append(st)
        except OSError:
            pass

    # Process names (best-effort)
    try:
        proc = Path("/proc")
        for entry in proc.iterdir():
            if not entry.name.isdigit():
                continue
            try:
                cmd = (entry / "cmdline").read_bytes().replace(b"\x00", b" ").decode(
                    "utf-8", errors="replace"
                ).lower()
            except OSError:
                continue
            if "steamtools" in cmd or "luatools" in cmd or "greenluma" in cmd:
                return (
                    "SteamTools / Lua Tools (or similar) appears to be running. "
                    "These injectors often break SteamCMD login used by GnomePaper. "
                    "Quit them and use a normal Steam client, then Link again."
                )
    except OSError:
        pass

    if markers:
        return (
            "SteamTools / Lua Tools files were found under your Steam install. "
            "They commonly break Workshop downloads via SteamCMD (endless Guard / "
            "login loops). Disable or remove the injector, restart Steam, then Link."
        )
    return None
