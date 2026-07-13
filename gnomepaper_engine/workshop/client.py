"""Search Steam Workshop and install wallpapers via the Steam client."""

from __future__ import annotations

import fcntl
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
from collections.abc import Callable, Iterator
from contextlib import contextmanager
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
    Open the Steam Workshop page so the user can Subscribe.

    This is the **reliable** install path for non-stock Steam (SteamTools,
    Lua Tools, custom clients): your Steam client downloads the item into
    the normal workshop folder and GnomePaper picks it up.

    Returns a short human message describing what happened.
    """
    steam_uri = f"steam://url/CommunityFilePage/{item_id}"
    web_url = f"https://steamcommunity.com/sharedfiles/filedetails/?id={item_id}"

    def _spawn(cmd: list[str]) -> bool:
        try:
            subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            return True
        except OSError as exc:
            log.warning("launch failed %s: %s", cmd, exc)
            return False

    # 1) steam:// via xdg-open — works with custom/SteamTools clients registered
    #    as the steam protocol handler (often better than PATH "steam")
    xdg = shutil.which("xdg-open")
    if xdg and _spawn([xdg, steam_uri]):
        return (
            "Opened in Steam — click Subscribe. "
            "GnomePaper will detect it when the download finishes."
        )

    # 2) steam binary on PATH
    steam_bin = shutil.which("steam")
    if steam_bin and _spawn([steam_bin, steam_uri]):
        return (
            "Opened in Steam — click Subscribe. "
            "GnomePaper will detect it when the download finishes."
        )

    # 3) Flatpak Steam
    flatpak = shutil.which("flatpak")
    if flatpak and _spawn(
        ["flatpak", "run", "com.valvesoftware.Steam", steam_uri]
    ):
        return (
            "Opened Flatpak Steam — click Subscribe. "
            "GnomePaper will detect it when the download finishes."
        )

    # 4) Browser — Subscribe still works if Steam is running in the background
    if xdg and _spawn([xdg, web_url]):
        return (
            "Opened Workshop in your browser — click Subscribe. "
            "Keep Steam running so the wallpaper downloads."
        )

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
    rate_limited: bool = False
    linked: bool = False
    log_tail: str = ""


def steamcmd_home() -> Path:
    """Isolated HOME for SteamCMD (never the real user home / desktop Steam)."""
    return steamcmd_dir() / "home"


def steamcmd_steam_root() -> Path:
    """Isolated Steam library root for force_install_dir + credentials."""
    return steamcmd_home() / ".local" / "share" / "Steam"


def _steamcmd_env() -> dict[str, str]:
    """
    Fully isolate SteamCMD from the desktop Steam client.

    Desktop Steam, SteamTools, and “Lua Tools” injectors live under the real
    ~/.local/share/Steam tree. Sharing that tree causes endless Guard / re-auth
    loops. Force HOME + XDG dirs into our private tree instead.
    """
    home = steamcmd_home()
    data = home / ".local" / "share"
    config = home / ".config"
    cache = home / ".cache"
    state = home / ".local" / "state"
    steam_root = steamcmd_steam_root()
    for p in (home, data, config, cache, state, steam_root):
        p.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env.pop("DISPLAY", None)
    env.pop("WAYLAND_DISPLAY", None)
    env.pop("WAYLAND_SOCKET", None)
    for key in list(env):
        ku = key.upper()
        if ku.startswith("STEAM") or key in (
            "SteamAppId",
            "SteamGameId",
            "SteamOverlayGameId",
        ):
            env.pop(key, None)

    env["HOME"] = str(home)
    env["XDG_DATA_HOME"] = str(data)
    env["XDG_CONFIG_HOME"] = str(config)
    env["XDG_CACHE_HOME"] = str(cache)
    env["XDG_STATE_HOME"] = str(state)
    env["STEAM_DIR"] = str(steam_root)
    env["STEAMROOT"] = str(steam_root)
    return env


def reset_steamcmd_session() -> str:
    """
    Wipe isolated SteamCMD login tokens so the next Link is a clean sign-in.
    Does not touch the desktop Steam client or the GNOME Keyring password.
    """
    wiped = 0
    for path in (
        steamcmd_steam_root() / "config",
        steamcmd_dir() / "config",
        steamcmd_home() / ".steam",
        steamcmd_home() / "Steam",
    ):
        if not path.exists():
            continue
        try:
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
            wiped += 1
        except OSError as exc:
            log.warning("reset session could not remove %s: %s", path, exc)
    try:
        for p in steamcmd_home().rglob("ssfn*"):
            try:
                p.unlink()
                wiped += 1
            except OSError:
                pass
    except OSError:
        pass
    if wiped:
        return f"Cleared SteamCMD session ({wiped} paths). Link Steam again."
    return "No SteamCMD session files found — try Link Steam again."


@contextmanager
def _steamcmd_lock(timeout: float = 180.0) -> Iterator[None]:
    """
    Serialize SteamCMD across concurrent GnomePaper instances.

    Two processes writing the same steamcmd home corrupt the login token and
    cause endless “sign in again” loops.
    """
    lock_path = steamcmd_dir() / ".gnomepaper-steamcmd.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fh = open(lock_path, "a+", encoding="utf-8")  # noqa: SIM115
    deadline = time.monotonic() + timeout
    locked = False
    try:
        while True:
            try:
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked = True
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError(
                        "Another GnomePaper / SteamCMD operation is still running. "
                        "Close the other window or wait a minute, then try again."
                    ) from None
                time.sleep(0.4)
        fh.seek(0)
        fh.truncate()
        fh.write(f"pid={os.getpid()} time={time.time():.0f}\n")
        fh.flush()
        yield
    finally:
        if locked:
            try:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
        try:
            fh.close()
        except OSError:
            pass


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


def _login_ok(output: str, returncode: int) -> bool:
    lower = output.lower()
    if _login_failure(output) is not None:
        return False
    # Be strict — bare "ok" appears in too many non-login lines
    return (
        "logged in ok" in lower
        or ("logging in user" in lower and "ok" in lower)
        or "waiting for user info" in lower
        or (returncode == 0 and "logging in" in lower and "failed" not in lower)
    )


def _login_failure(output: str) -> SteamCmdResult | None:
    """Return a failure result if the SteamCMD log indicates login problems."""
    lower = output.lower()
    if (
        "rate limit" in lower
        or "too many logon" in lower
        or "try again later" in lower
        or "limit exceeded" in lower
    ):
        return SteamCmdResult(
            False,
            "Steam is rate-limiting logins. Wait 5–15 minutes, use only one "
            "GnomePaper window, then Link again.",
            rate_limited=True,
            log_tail=output[-600:],
        )
    if (
        "two-factor" in lower
        or "steam guard" in lower
        or "guard code" in lower
        or "mobile authenticator" in lower
        or "account logon denied" in lower
        or "invalid login auth code" in lower
        or "invalid auth code" in lower
        or ("enter" in lower and "code" in lower and ("guard" in lower or "email" in lower))
    ):
        return SteamCmdResult(
            False,
            "Steam Guard code needed — open your Steam Mobile app and enter the code.",
            needs_guard=True,
            log_tail=output[-600:],
        )
    if (
        "cached credentials not found" in lower
        or "no cached credentials" in lower
        or ("password" in lower and "not set" in lower)
    ):
        return SteamCmdResult(
            False,
            "No saved Steam session on this PC yet.",
            needs_password=True,
            log_tail=output[-400:],
        )
    if "invalid password" in lower:
        return SteamCmdResult(
            False,
            "Wrong Steam password. Check CAPS LOCK and try again.",
            needs_password=True,
            log_tail=output[-600:],
        )
    if (
        "logged in elsewhere" in lower
        or "another computer" in lower
        or "already logged" in lower
        or "logon session replaced" in lower
    ):
        return SteamCmdResult(
            False,
            "Steam signed this session out (another PC/app logged in). "
            "Close other GnomePaper windows, wait 30s, then Link once here.",
            needs_password=True,
            log_tail=output[-600:],
        )
    if "login failure" in lower or "failed to log" in lower or "failed with result code" in lower:
        # SteamTools / injectors often surface as generic login failure
        hint = ""
        try:
            from gnomepaper_engine.workshop.steam_account import steam_injector_warning

            w = steam_injector_warning()
            if w:
                hint = " " + w
        except Exception:
            pass
        return SteamCmdResult(
            False,
            "Steam login failed." + hint
            + " Tip: use stock Steam (disable SteamTools/Lua Tools), then Link again.",
            needs_password=True,
            log_tail=output[-600:],
        )
    if "no subscription" in lower:
        return SteamCmdResult(
            False,
            "This Steam account must own Wallpaper Engine.",
            log_tail=output[-600:],
        )
    return None


def _login_args(username: str, password: str = "", guard_code: str = "") -> list[str]:
    """
    Build SteamCMD +login arguments.

    SteamCMD accepts: login <user> [<password>] [<steam guard code>]
    Putting the Guard code as the third login argument is more reliable than
    +set_steam_guard_code alone on modern SteamCMD builds.
    """
    user = username.strip()
    pw = password or ""
    code = guard_code.strip()
    if pw and code:
        return ["+login", user, pw, code]
    if pw:
        return ["+login", user, pw]
    return ["+login", user]


def link_steam_account(
    *,
    username: str,
    password: str,
    guard_code: str = "",
    progress: Callable[[str], None] | None = None,
    store_password: bool = True,
) -> SteamCmdResult:
    """
    Log into isolated SteamCMD and keep credentials for Workshop downloads.

    - Session tokens live only under GnomePaper's steamcmd home (not desktop Steam).
    - Password is stored in the **GNOME Keyring** for silent renew on this PC.
    - Prefer linking once; downloads then use the cached session first.
    """
    username = username.strip()
    if not username or not password:
        return SteamCmdResult(
            False,
            "Steam username and password are required to link.",
            needs_password=True,
        )

    # Warn early about injectors (non-fatal)
    try:
        from gnomepaper_engine.workshop.steam_account import steam_injector_warning

        warn = steam_injector_warning()
        if warn and progress:
            progress(warn)
    except Exception:
        pass

    try:
        cmd_bin = ensure_steamcmd()
    except Exception as exc:
        return SteamCmdResult(False, f"Could not install SteamCMD: {exc}")

    from gnomepaper_engine.config import AppConfig
    from gnomepaper_engine.workshop.keyring import store_steam_password

    log_path = AppConfig.cache_dir() / "steamcmd_link.log"
    if progress:
        progress("Linking Steam (isolated SteamCMD session)…")

    args: list[str] = [
        str(cmd_bin),
        "+@ShutdownOnFailedCommand",
        "1",
        "+@NoPromptForPassword",
        "1",
        *(_login_args(username, password, guard_code)),
        "+quit",
    ]

    try:
        with _steamcmd_lock():
            _code, output = _run_steamcmd(
                args, cwd=cmd_bin.parent, timeout=180, log_path=log_path
            )
    except TimeoutError as exc:
        return SteamCmdResult(False, str(exc))

    fail = _login_failure(output)
    if fail is not None:
        return fail

    if not _login_ok(output, _code):
        return SteamCmdResult(
            False,
            "Could not confirm Steam login. Check password / Steam Guard. "
            "If SteamTools or Lua Tools is installed, disable it first.",
            needs_password=True,
            needs_guard="guard" in output.lower() or "auth code" in output.lower(),
            log_tail=output[-600:],
        )

    stored = False
    if store_password:
        stored = store_steam_password(username, password)

    msg = f"Linked “{username}” on this PC."
    if stored:
        msg += " Password saved in GNOME Keyring — downloads reuse this session."
    else:
        msg += " (Keyring unavailable — you may need to re-enter the password later.)"

    return SteamCmdResult(True, msg, linked=True, log_tail=output[-400:])


def _find_workshop_download(dl_root: Path, item_id: str) -> Path | None:
    candidates = [
        dl_root / "steamapps" / "workshop" / "content" / _APP_ID / item_id,
        dl_root / "workshop" / "content" / _APP_ID / item_id,
        steamcmd_dir()
        / "home"
        / ".local"
        / "share"
        / "Steam"
        / "steamapps"
        / "workshop"
        / "content"
        / _APP_ID
        / item_id,
        steamcmd_dir() / "steamapps" / "workshop" / "content" / _APP_ID / item_id,
    ]
    for c in candidates:
        try:
            if c.is_dir() and any(c.iterdir()):
                return c
        except OSError:
            continue
    try:
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
                if (p / "project.json").exists():
                    return p
                return p
    except OSError:
        pass
    return None


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

    Auth order (avoids multi-session / Guard loops):
      1. SteamCMD cached session (``+login username``) — no password spam
      2. Password from argument or GNOME Keyring (``+login user pass``)
      3. Fail with needs_guard / needs_password for the UI
    """
    username = username.strip()
    if not username:
        return SteamCmdResult(
            False,
            "Steam username is required. Link your account (top-left).",
            needs_password=True,
        )

    from gnomepaper_engine.config import AppConfig
    from gnomepaper_engine.workshop.keyring import lookup_steam_password, store_steam_password

    if not password:
        password = lookup_steam_password(username) or ""

    try:
        cmd_bin = ensure_steamcmd()
    except Exception as exc:
        return SteamCmdResult(False, f"Could not install SteamCMD: {exc}")

    # Always use the isolated Steam root (never desktop ~/.local/share/Steam)
    dl_root = steamcmd_steam_root()
    dl_root.mkdir(parents=True, exist_ok=True)
    log_path = AppConfig.cache_dir() / "steamcmd_last.log"

    def _attempt(login_parts: list[str], label: str) -> tuple[int, str]:
        if progress:
            progress(label)
        args: list[str] = [
            str(cmd_bin),
            "+@ShutdownOnFailedCommand",
            "1",
            "+@NoPromptForPassword",
            "1",
            "+force_install_dir",
            str(dl_root),
            *login_parts,
            "+workshop_download_item",
            _APP_ID,
            str(item_id),
            "validate",
            "+quit",
        ]
        return _run_steamcmd(
            args, cwd=cmd_bin.parent, timeout=900, log_path=log_path
        )

    def _finish(output: str) -> SteamCmdResult:
        lower = output.lower()
        found = _find_workshop_download(dl_root, item_id)
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
            linked=True,
            log_tail=output[-400:],
        )

    try:
        with _steamcmd_lock():
            # 1) Prefer cached SteamCMD session — avoids re-sending the password
            #    (password login is what re-triggers Guard and kicks other sessions).
            if use_cached_login and not guard_code.strip():
                _code, output = _attempt(
                    _login_args(username),
                    "Using saved Steam session…",
                )
                fail = _login_failure(output)
                if fail is None:
                    result = _finish(output)
                    if result.ok:
                        return result
                    if "downloaded item" in output.lower() and "success" in output.lower():
                        return result
                else:
                    if fail.rate_limited:
                        return fail
                    if fail.needs_guard and not password:
                        return fail
                    if fail.needs_guard and not guard_code.strip():
                        return fail
                    # needs_password / expired cache → keyring password below

            if not password:
                return SteamCmdResult(
                    False,
                    "No saved Steam password on this PC. Click Link Steam (top-left) once — "
                    "password is saved in GNOME Keyring. Each computer needs its own one-time link.",
                    needs_password=True,
                )

            _code, output = _attempt(
                _login_args(username, password, guard_code),
                "Signing in to Steam…",
            )
            fail = _login_failure(output)
            if fail is not None:
                return fail

            store_steam_password(username, password)
            return _finish(output)
    except TimeoutError as exc:
        return SteamCmdResult(False, str(exc))


