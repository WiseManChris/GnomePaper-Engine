"""Search Steam Workshop and install wallpapers via the Steam client."""

from __future__ import annotations

import html
import json
import logging
import os
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from gnomepaper_engine.steam.paths import (
    WALLPAPER_ENGINE_APP_ID,
    discover_steam_installs,
    workshop_content_dirs,
)

log = logging.getLogger(__name__)

_USER_AGENT = "GnomePaper-Engine/0.1 (+https://github.com/; Steam Workshop browser)"
_APP_ID = str(WALLPAPER_ENGINE_APP_ID)

# Browse sorts that work on steamcommunity workshop browse
SORTS = {
    "trend": "Trending",
    "mostrecent": "Most recent",
    "totaluniquesubscribers": "Most popular",
    "lastupdated": "Last updated",
}


@dataclass
class WorkshopItem:
    id: str
    title: str
    preview_url: str = ""
    description: str = ""
    file_size: int = 0
    subscriptions: int = 0
    time_created: int = 0
    creator: str = ""

    @property
    def size_label(self) -> str:
        if self.file_size <= 0:
            return ""
        mb = self.file_size / (1024 * 1024)
        if mb >= 100:
            return f"{mb:.0f} MB"
        if mb >= 1:
            return f"{mb:.1f} MB"
        return f"{self.file_size / 1024:.0f} KB"

    @property
    def subs_label(self) -> str:
        if self.subscriptions <= 0:
            return ""
        if self.subscriptions >= 1_000_000:
            return f"{self.subscriptions / 1_000_000:.1f}M subs"
        if self.subscriptions >= 1_000:
            return f"{self.subscriptions / 1_000:.1f}K subs"
        return f"{self.subscriptions} subs"


def _http_get(url: str, timeout: float = 30.0) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _http_post_form(url: str, data: dict, timeout: float = 30.0) -> dict:
    body = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "User-Agent": _USER_AGENT,
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def search_workshop(
    query: str = "",
    *,
    page: int = 1,
    sort: str = "trend",
    per_page: int = 24,
) -> list[WorkshopItem]:
    """
    Search Wallpaper Engine workshop items.

    Uses the public Steam Community browse page (no API key), then hydrates
    metadata via ISteamRemoteStorage/GetPublishedFileDetails.
    """
    query = (query or "").strip()
    page = max(1, int(page))
    per_page = max(9, min(30, int(per_page)))
    sort_key = sort if sort in SORTS else "trend"
    if query:
        sort_key = "textsearch"

    params: dict[str, str] = {
        "appid": _APP_ID,
        "browsesort": sort_key,
        "section": "readytouseitems",
        "actualsort": sort_key,
        "p": str(page),
        "numperpage": str(per_page),
    }
    if query:
        params["searchtext"] = query

    url = "https://steamcommunity.com/workshop/browse/?" + urllib.parse.urlencode(params)
    log.info("Workshop search: %s", url)
    try:
        html_text = _http_get(url)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        log.warning("Workshop browse failed: %s", exc)
        raise RuntimeError(f"Could not reach Steam Workshop: {exc}") from exc

    # id + preview + title from modern Steam workshop cards
    pattern = re.compile(
        r'filedetails/\?id=(\d+)"[^>]*>\s*<img\s+src="([^"]+)"\s+alt="([^"]*)"',
        re.IGNORECASE | re.DOTALL,
    )
    raw: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for match in pattern.finditer(html_text):
        wid, preview, title = match.group(1), match.group(2), match.group(3)
        if wid in seen:
            continue
        seen.add(wid)
        raw.append(
            (
                wid,
                html.unescape(preview.replace("&amp;", "&")),
                html.unescape(title),
            )
        )

    if not raw:
        # Fallback: IDs only
        for wid in dict.fromkeys(re.findall(r"filedetails/\?id=(\d+)", html_text)):
            raw.append((wid, "", ""))

    if not raw:
        return []

    details = get_published_details([r[0] for r in raw])
    by_id = {d.id: d for d in details}

    items: list[WorkshopItem] = []
    for wid, preview, title in raw:
        if wid in by_id:
            item = by_id[wid]
            if not item.preview_url and preview:
                item.preview_url = preview
            if not item.title and title:
                item.title = title
            items.append(item)
        else:
            items.append(WorkshopItem(id=wid, title=title or wid, preview_url=preview))
    return items


def get_published_details(ids: list[str]) -> list[WorkshopItem]:
    """Batch-fetch public metadata for workshop file IDs."""
    if not ids:
        return []
    # Steam allows reasonably sized batches; keep under 50
    ids = ids[:50]
    data: dict[str, str | int] = {"itemcount": len(ids)}
    for i, wid in enumerate(ids):
        data[f"publishedfileids[{i}]"] = wid
    try:
        payload = _http_post_form(
            "https://api.steampowered.com/ISteamRemoteStorage/GetPublishedFileDetails/v1/",
            data,  # type: ignore[arg-type]
        )
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        log.warning("GetPublishedFileDetails failed: %s", exc)
        return []

    items: list[WorkshopItem] = []
    for entry in payload.get("response", {}).get("publishedfiledetails", []):
        if int(entry.get("result", 0)) != 1:
            continue
        try:
            size = int(entry.get("file_size") or 0)
        except (TypeError, ValueError):
            size = 0
        try:
            subs = int(entry.get("subscriptions") or 0)
        except (TypeError, ValueError):
            subs = 0
        items.append(
            WorkshopItem(
                id=str(entry.get("publishedfileid", "")),
                title=str(entry.get("title") or entry.get("publishedfileid") or ""),
                preview_url=str(entry.get("preview_url") or ""),
                description=str(entry.get("description") or ""),
                file_size=size,
                subscriptions=subs,
                time_created=int(entry.get("time_created") or 0),
                creator=str(entry.get("creator") or ""),
            )
        )
    return items


def installed_ids() -> set[str]:
    """Workshop IDs already present under Steam workshop content."""
    found: set[str] = set()
    for install in discover_steam_installs():
        for wdir in workshop_content_dirs(install):
            try:
                for child in wdir.iterdir():
                    if child.is_dir() and child.name.isdigit():
                        found.add(child.name)
            except OSError:
                continue
    return found


def is_installed(item_id: str) -> bool:
    return item_id in installed_ids()


def workshop_item_path(item_id: str) -> Path | None:
    for install in discover_steam_installs():
        for wdir in workshop_content_dirs(install):
            path = wdir / item_id
            if path.is_dir() and any(path.iterdir()):
                return path
    return None


def open_install(item_id: str) -> str:
    """
    Open the Steam Workshop page so the user can Subscribe (Steam downloads it).

    Returns a short human message describing what happened.
    """
    steam_uri = f"steam://url/CommunityFilePage/{item_id}"
    web_url = f"https://steamcommunity.com/sharedfiles/filedetails/?id={item_id}"

    steam_bin = shutil.which("steam")
    if steam_bin:
        try:
            subprocess.Popen(
                [steam_bin, steam_uri],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            return (
                "Opened in Steam — click Subscribe. "
                "GnomePaper will add it when the download finishes."
            )
        except OSError as exc:
            log.warning("steam launch failed: %s", exc)

    # Fallback: system browser (Subscribe still works if Steam is running)
    xdg = shutil.which("xdg-open")
    if xdg:
        try:
            subprocess.Popen(
                [xdg, web_url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            return (
                "Opened Workshop in your browser — click Subscribe. "
                "Keep Steam running so the wallpaper downloads."
            )
        except OSError as exc:
            log.warning("xdg-open failed: %s", exc)

    return f"Open this URL and click Subscribe:\n{web_url}"


def wait_for_install(
    item_id: str,
    *,
    timeout: float = 300.0,
    interval: float = 2.0,
    should_cancel: Callable[[], bool] | None = None,
) -> Path | None:
    """Poll until workshop content appears on disk (or timeout)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if should_cancel is not None and should_cancel():
            return None
        path = workshop_item_path(item_id)
        if path is not None:
            # Wait until folder is non-empty / has project or media
            try:
                if any(path.iterdir()):
                    return path
            except OSError:
                pass
        time.sleep(interval)
    return None


def cache_remote_preview(url: str, dest: Path) -> Path | None:
    """Download a remote preview image into dest (for UI cache)."""
    if not url:
        return None
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
        with urllib.request.urlopen(req, timeout=20) as resp:
            dest.write_bytes(resp.read())
        return dest if dest.is_file() else None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        log.debug("preview download failed: %s", exc)
        return None


# ── SteamCMD direct download (no Subscribe click) ─────────────────


def steamcmd_dir() -> Path:
    from gnomepaper_engine.config import xdg_data_home

    return xdg_data_home() / "gnomepaper-engine" / "steamcmd"


def steamcmd_binary() -> Path | None:
    """Locate steamcmd.sh (bundled under data home or on PATH)."""
    candidate = steamcmd_dir() / "steamcmd.sh"
    if candidate.is_file() and os.access(candidate, os.X_OK):
        return candidate
    which = shutil.which("steamcmd") or shutil.which("steamcmd.sh")
    return Path(which) if which else None


def ensure_steamcmd() -> Path:
    """
    Ensure SteamCMD is installed under ~/.local/share/gnomepaper-engine/steamcmd.
    Downloads Valve's official Linux package if missing.
    """
    binary = steamcmd_binary()
    if binary is not None:
        return binary

    dest = steamcmd_dir()
    dest.mkdir(parents=True, exist_ok=True)
    tarball = dest / "steamcmd_linux.tar.gz"
    url = "https://steamcdn-a.akamaihd.net/client/installer/steamcmd_linux.tar.gz"
    log.info("Downloading SteamCMD from %s", url)
    urllib.request.urlretrieve(url, tarball)  # noqa: S310 — official Valve CDN
    subprocess.run(
        ["tar", "-xzf", str(tarball), "-C", str(dest)],
        check=True,
        capture_output=True,
    )
    tarball.unlink(missing_ok=True)
    script = dest / "steamcmd.sh"
    if not script.is_file():
        raise RuntimeError("SteamCMD extract failed — steamcmd.sh missing")
    script.chmod(script.stat().st_mode | 0o111)
    # First run self-update (ignore non-zero)
    subprocess.run(
        [str(script), "+quit"],
        cwd=str(dest),
        capture_output=True,
        text=True,
        timeout=180,
    )
    return script


def primary_workshop_content_dir() -> Path:
    """Best target directory for new workshop downloads."""
    installs = discover_steam_installs()
    for install in installs:
        dirs = workshop_content_dirs(install)
        if dirs:
            return dirs[0]
        # Create standard path under first steam root
        candidate = install.root / "steamapps" / "workshop" / "content" / _APP_ID
        candidate.mkdir(parents=True, exist_ok=True)
        return candidate
    # Fallback under home Steam
    fallback = (
        Path.home()
        / ".local"
        / "share"
        / "Steam"
        / "steamapps"
        / "workshop"
        / "content"
        / _APP_ID
    )
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


@dataclass
class SteamCmdResult:
    ok: bool
    message: str
    path: Path | None = None
    needs_guard: bool = False
    needs_password: bool = False
    linked: bool = False
    log_tail: str = ""


def _steamcmd_env() -> dict[str, str]:
    env = os.environ.copy()
    env.pop("DISPLAY", None)
    env.pop("WAYLAND_DISPLAY", None)
    return env


def _run_steamcmd(
    args: list[str],
    *,
    cwd: Path,
    timeout: float = 900,
    log_path: Path | None = None,
) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            args,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            env=_steamcmd_env(),
        )
    except subprocess.TimeoutExpired:
        return 124, "SteamCMD timed out."
    except OSError as exc:
        return 1, f"Failed to run SteamCMD: {exc}"
    output = (proc.stdout or "") + "\n" + (proc.stderr or "")
    if log_path is not None:
        try:
            log_path.write_text(output, encoding="utf-8", errors="replace")
        except OSError:
            pass
    return proc.returncode, output


def _login_failure(output: str) -> SteamCmdResult | None:
    """Return a failure result if the SteamCMD log indicates login problems."""
    lower = output.lower()
    if "two-factor" in lower or "steam guard" in lower or (
        "guard" in lower and "code" in lower
    ):
        return SteamCmdResult(
            False,
            "Steam Guard code required. Enter the code from your authenticator/email.",
            needs_guard=True,
            log_tail=output[-600:],
        )
    if "invalid password" in lower:
        return SteamCmdResult(
            False,
            "Steam login failed — check username/password.",
            needs_password=True,
            log_tail=output[-600:],
        )
    if "login failure" in lower or "failed to log" in lower:
        return SteamCmdResult(
            False,
            "Steam login failed — re-link your account (password may be required).",
            needs_password=True,
            log_tail=output[-600:],
        )
    if "no subscription" in lower:
        return SteamCmdResult(
            False,
            "Steam reports no subscription — this account must own Wallpaper Engine.",
            log_tail=output[-600:],
        )
    return None


def link_steam_account(
    *,
    username: str,
    password: str,
    guard_code: str = "",
    progress: Callable[[str], None] | None = None,
) -> SteamCmdResult:
    """
    Log into SteamCMD once so credentials are cached for future downloads.

    Password is not stored by GnomePaper — SteamCMD keeps its own encrypted
    login token under the steamcmd data directory.
    """
    username = username.strip()
    if not username or not password:
        return SteamCmdResult(
            False,
            "Steam username and password are required to link.",
            needs_password=True,
        )

    try:
        cmd_bin = ensure_steamcmd()
    except Exception as exc:
        return SteamCmdResult(False, f"Could not install SteamCMD: {exc}")

    from gnomepaper_engine.config import AppConfig

    log_path = AppConfig.cache_dir() / "steamcmd_link.log"
    if progress:
        progress("Linking Steam account via SteamCMD…")

    args: list[str] = [
        str(cmd_bin),
        "+@ShutdownOnFailedCommand",
        "1",
        "+@NoPromptForPassword",
        "1",
    ]
    if guard_code.strip():
        args += ["+set_steam_guard_code", guard_code.strip()]
    args += ["+login", username, password, "+quit"]

    _code, output = _run_steamcmd(
        args, cwd=cmd_bin.parent, timeout=180, log_path=log_path
    )
    fail = _login_failure(output)
    if fail is not None:
        return fail

    # SteamCMD prints "OK" / "Waiting for client config" on success
    lower = output.lower()
    if "logged in" in lower or "ok" in lower or "waiting for user" in lower:
        return SteamCmdResult(
            True,
            f"Linked Steam account “{username}”. Future downloads won’t need a password.",
            linked=True,
            log_tail=output[-400:],
        )
    # Some builds are quiet on success
    if _code == 0 and "failed" not in lower:
        return SteamCmdResult(
            True,
            f"Linked Steam account “{username}”.",
            linked=True,
            log_tail=output[-400:],
        )
    return SteamCmdResult(
        False,
        "Could not confirm Steam login. Check credentials / Steam Guard.",
        needs_password=True,
        log_tail=output[-600:],
    )


def download_via_steamcmd(
    item_id: str,
    *,
    username: str,
    password: str = "",
    guard_code: str = "",
    use_cached_login: bool = True,
    progress: Callable[[str], None] | None = None,
) -> SteamCmdResult:
    """
    Download a workshop item with SteamCMD (account that owns Wallpaper Engine).

    If ``use_cached_login`` and no password is given, SteamCMD uses its cached
    login for ``username`` (from a previous successful link/download).

    Note: Steam allows one login at a time — the desktop Steam client may
    disconnect briefly while SteamCMD is logged in.
    """
    username = username.strip()
    if not username:
        return SteamCmdResult(
            False,
            "Steam username is required. Link your account in settings.",
            needs_password=True,
        )
    if not password and not use_cached_login:
        return SteamCmdResult(
            False,
            "Steam password required (or link your account first).",
            needs_password=True,
        )

    try:
        cmd_bin = ensure_steamcmd()
    except Exception as exc:
        return SteamCmdResult(False, f"Could not install SteamCMD: {exc}")

    # Isolated download root (avoid touching live Steam install while running)
    from gnomepaper_engine.config import AppConfig

    dl_root = AppConfig.cache_dir() / "steamcmd_dl"
    dl_root.mkdir(parents=True, exist_ok=True)
    log_path = AppConfig.cache_dir() / "steamcmd_last.log"

    if progress:
        if password:
            progress("Logging into SteamCMD…")
        else:
            progress("Using linked Steam account…")

    args: list[str] = [
        str(cmd_bin),
        "+@ShutdownOnFailedCommand",
        "1",
        "+@NoPromptForPassword",
        "1",
        "+force_install_dir",
        str(dl_root),
    ]
    if guard_code.strip():
        args += ["+set_steam_guard_code", guard_code.strip()]
    # Cached login: +login username   |  Fresh login: +login username password
    if password:
        args += ["+login", username, password]
    else:
        args += ["+login", username]
    args += [
        "+workshop_download_item",
        _APP_ID,
        str(item_id),
        "validate",
        "+quit",
    ]

    _code, output = _run_steamcmd(
        args, cwd=cmd_bin.parent, timeout=900, log_path=log_path
    )

    fail = _login_failure(output)
    if fail is not None:
        return fail

    lower = output.lower()

    # Locate downloaded item
    candidates = [
        dl_root / "steamapps" / "workshop" / "content" / _APP_ID / item_id,
        dl_root / "workshop" / "content" / _APP_ID / item_id,
    ]
    # Also search under dl_root
    found: Path | None = None
    for c in candidates:
        if c.is_dir() and any(c.iterdir()):
            found = c
            break
    if found is None:
        for p in dl_root.rglob(item_id):
            if not p.is_dir():
                continue
            try:
                has_files = any(p.iterdir())
            except OSError:
                continue
            if not has_files:
                continue
            if (p / "project.json").exists() or "workshop" in p.parts:
                found = p
                if (p / "project.json").exists():
                    break

    if found is None:
        if "success" in lower and "downloaded item" in lower:
            return SteamCmdResult(
                False,
                "SteamCMD reported success but files were not found. See log.",
                log_tail=output[-800:],
            )
        return SteamCmdResult(
            False,
            "Download failed. Check Steam Guard / ownership, or use Subscribe.",
            log_tail=output[-800:],
        )

    if progress:
        progress("Copying into Steam workshop folder…")

    dest_root = primary_workshop_content_dir()
    dest = dest_root / item_id
    try:
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(found, dest)
    except OSError as exc:
        return SteamCmdResult(False, f"Downloaded but copy failed: {exc}", path=found)

    return SteamCmdResult(
        True,
        f"Downloaded to {dest}",
        path=dest,
        linked=True,  # successful login implies cache is usable
        log_tail=output[-400:],
    )


