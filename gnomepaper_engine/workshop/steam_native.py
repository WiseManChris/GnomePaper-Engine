"""
Seamless Steam Workshop downloads via the Steam network (ValvePython steam).

This replaces SteamCMD for day-to-day use:

* One Link (password + optional Guard) stores a **login key**
* Later downloads re-auth silently with that key — no Subscribe click, no SteamCMD
* Runs Steam/gevent work in a **subprocess** so GTK stays healthy

Falls back with a clear error if the ``steam[client]`` package is missing.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from gnomepaper_engine.workshop.client import SteamCmdResult, primary_workshop_content_dir

log = logging.getLogger(__name__)

_APP_ID = "431960"


def native_steam_available() -> bool:
    try:
        import steam  # noqa: F401
        import gevent  # noqa: F401

        return True
    except ImportError:
        return False


def native_cred_dir() -> Path:
    from gnomepaper_engine.config import xdg_data_home

    path = xdg_data_home() / "gnomepaper-engine" / "steam_native"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _python_for_worker() -> str:
    # Prefer the same interpreter as the app (venv)
    return sys.executable


def _run_worker(
    args: list[str],
    *,
    env_extra: dict[str, str] | None = None,
    timeout: float = 600,
    progress: Callable[[str], None] | None = None,
) -> dict:
    if not native_steam_available():
        return {
            "ok": False,
            "message": (
                "Seamless Steam download needs the Python package steam[client]. "
                "Re-run ./install.sh to install it."
            ),
            "needs_password": True,
        }

    cmd = [
        _python_for_worker(),
        "-m",
        "gnomepaper_engine.workshop.steam_worker",
        "--cred-dir",
        str(native_cred_dir()),
        *args,
    ]
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    # Avoid leaking desktop Steam vars into the worker
    for key in list(env):
        if key.upper().startswith("STEAM"):
            env.pop(key, None)

    if progress:
        progress("Talking to Steam…")

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "message": "Steam operation timed out."}
    except OSError as exc:
        return {"ok": False, "message": f"Could not start Steam worker: {exc}"}

    # Parse last JSON line from stdout
    payload: dict | None = None
    for line in (proc.stdout or "").splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue

    if payload is None:
        err = (proc.stderr or proc.stdout or "").strip()[-800:]
        # Common: worker crashed before JSON (missing deps, gevent, etc.)
        hint = ""
        if "No module named" in err or "ModuleNotFoundError" in err:
            hint = " Re-run ./install.sh so steam[client] is installed."
        return {
            "ok": False,
            "message": f"Steam worker failed (exit {proc.returncode}).{hint} {err}",
            "needs_password": True,
        }
    # Always log eresult for debugging password/"InvalidPassword" cases
    if not payload.get("ok"):
        log.warning(
            "steam worker error: %s eresult=%s",
            payload.get("message"),
            payload.get("eresult"),
        )
    return payload


def _store_login_key(username: str, login_key: str) -> bool:
    if not username or not login_key:
        return False
    # Prefer keyring; also write a restricted file as backup
    try:
        from gnomepaper_engine.workshop.keyring import keyring_available

        if keyring_available():
            import subprocess as sp

            sp.run(
                [
                    "secret-tool",
                    "store",
                    "--label",
                    f"GnomePaper Steam login key ({username})",
                    "service",
                    "gnomepaper-engine",
                    "username",
                    username,
                    "kind",
                    "login_key",
                ],
                input=login_key + "\n",
                text=True,
                check=True,
                capture_output=True,
                timeout=30,
            )
    except Exception as exc:
        log.debug("keyring login_key store failed: %s", exc)

    key_path = native_cred_dir() / f"{username}.login_key"
    try:
        key_path.write_text(login_key, encoding="utf-8")
        key_path.chmod(0o600)
        return True
    except OSError as exc:
        log.warning("could not write login key file: %s", exc)
        return False


def lookup_login_key(username: str) -> str | None:
    username = (username or "").strip()
    if not username:
        return None
    try:
        import subprocess as sp

        out = sp.check_output(
            [
                "secret-tool",
                "lookup",
                "service",
                "gnomepaper-engine",
                "username",
                username,
                "kind",
                "login_key",
            ],
            text=True,
            timeout=15,
            stderr=subprocess.DEVNULL,
        )
        key = out.strip()
        if key:
            return key
    except Exception:
        pass
    key_path = native_cred_dir() / f"{username}.login_key"
    try:
        if key_path.is_file():
            return key_path.read_text(encoding="utf-8").strip() or None
    except OSError:
        pass
    return None


def clear_login_key(username: str) -> None:
    username = (username or "").strip()
    if not username:
        return
    try:
        import subprocess as sp

        sp.run(
            [
                "secret-tool",
                "clear",
                "service",
                "gnomepaper-engine",
                "username",
                username,
                "kind",
                "login_key",
            ],
            check=False,
            capture_output=True,
            timeout=15,
        )
    except Exception:
        pass
    key_path = native_cred_dir() / f"{username}.login_key"
    try:
        key_path.unlink(missing_ok=True)
    except OSError:
        pass


def _result_from_payload(payload: dict) -> SteamCmdResult:
    return SteamCmdResult(
        ok=bool(payload.get("ok")),
        message=str(payload.get("message") or ""),
        path=Path(payload["path"]) if payload.get("path") else None,
        needs_guard=bool(payload.get("needs_guard")),
        needs_password=bool(payload.get("needs_password")),
        rate_limited=bool(payload.get("rate_limited")),
        linked=bool(payload.get("linked") or payload.get("ok")),
        log_tail=str(payload.get("detail") or "")[-600:],
    )


def link_steam_native(
    *,
    username: str,
    password: str,
    guard_code: str = "",
    progress: Callable[[str], None] | None = None,
) -> SteamCmdResult:
    """One-time link: password (+ Guard) → persistent login key."""
    from gnomepaper_engine.workshop.keyring import store_steam_password

    if progress:
        progress("Linking Steam (seamless session)…")

    payload = _run_worker(
        [
            "link",
            "--username",
            username.strip(),
            "--guard",
            guard_code.strip(),
        ],
        env_extra={"GNOMEPAPER_STEAM_PASSWORD": password},
        timeout=180,
        progress=progress,
    )
    result = _result_from_payload(payload)
    if result.ok:
        store_steam_password(username, password)
        key = str(payload.get("login_key") or "")
        if key:
            _store_login_key(username, key)
            result.message = (
                f"Linked “{username}”. Downloads will work silently from now on."
            )
        else:
            result.message += " (Session key missing — you may need Guard again later.)"
    return result


def download_via_native(
    item_id: str,
    *,
    username: str,
    password: str = "",
    guard_code: str = "",
    progress: Callable[[str], None] | None = None,
) -> SteamCmdResult:
    """
    Seamless workshop download into the real Steam workshop folder.

    Auth order: QR tokens (access/refresh) → login key → keyring password.
    """
    from gnomepaper_engine.workshop.keyring import lookup_steam_password, store_steam_password
    from gnomepaper_engine.workshop.steam_qr_auth import load_tokens, refresh_access_token

    username = (username or "").strip()
    tokens = refresh_access_token() or load_tokens()
    access_token = ""
    if tokens:
        access_token = tokens.get("access_token") or ""
        if not username:
            username = tokens.get("account_name") or ""

    login_key = lookup_login_key(username) if username else ""
    if not password and username:
        password = lookup_steam_password(username) or ""

    if not access_token and not login_key and not password:
        return SteamCmdResult(
            False,
            "Link Steam once with the QR code (top-left) for seamless downloads.",
            needs_password=True,
        )

    dest_root = primary_workshop_content_dir()
    dest = dest_root / str(item_id)

    if progress:
        progress("Downloading from Steam…")

    env: dict[str, str] = {}
    if access_token:
        env["GNOMEPAPER_STEAM_ACCESS_TOKEN"] = access_token
    if login_key:
        env["GNOMEPAPER_STEAM_LOGIN_KEY"] = login_key
    if password:
        env["GNOMEPAPER_STEAM_PASSWORD"] = password

    # Download to a temp folder then move — avoids half-written workshop dirs
    tmp = native_cred_dir() / "download_tmp" / str(item_id)
    if tmp.exists():
        shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True, exist_ok=True)

    worker_args = [
        "download",
        "--username",
        username or "user",
        "--item-id",
        str(item_id),
        "--dest",
        str(tmp),
        "--guard",
        guard_code.strip(),
    ]
    if access_token:
        worker_args.extend(["--access-token", access_token])

    payload = _run_worker(
        worker_args,
        env_extra=env,
        timeout=900,
        progress=progress,
    )
    result = _result_from_payload(payload)

    # Persist refreshed login key
    new_key = str(payload.get("login_key") or "")
    if new_key:
        _store_login_key(username, new_key)
    if result.ok and password:
        store_steam_password(username, password)

    if not result.ok:
        shutil.rmtree(tmp, ignore_errors=True)
        return result

    # Move into Steam workshop content path
    try:
        if dest.exists():
            shutil.rmtree(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(tmp), str(dest))
    except OSError as exc:
        shutil.rmtree(tmp, ignore_errors=True)
        return SteamCmdResult(False, f"Downloaded but install failed: {exc}")

    return SteamCmdResult(
        True,
        f"Downloaded to {dest}",
        path=dest,
        linked=True,
    )


def reset_native_session(username: str = "") -> str:
    """Clear login keys / QR tokens / sentry so the next Link is clean."""
    from gnomepaper_engine.workshop.steam_qr_auth import clear_tokens

    clear_login_key(username)
    clear_tokens()
    if not username:
        try:
            for p in native_cred_dir().glob("*.login_key"):
                p.unlink(missing_ok=True)
        except OSError:
            pass
    wiped = 0
    for p in native_cred_dir().iterdir():
        if p.name.endswith(".login_key") or p.name == "download_tmp":
            continue
        try:
            if p.is_dir():
                shutil.rmtree(p)
            else:
                p.unlink()
            wiped += 1
        except OSError:
            pass
    return f"Cleared seamless Steam session ({wiped} files). Scan the QR again."


def has_seamless_session() -> bool:
    """True if QR tokens or a login key exist."""
    from gnomepaper_engine.workshop.steam_qr_auth import load_tokens

    tokens = load_tokens()
    if tokens and (tokens.get("access_token") or tokens.get("refresh_token")):
        return True
    # legacy login_key files
    try:
        if any(native_cred_dir().glob("*.login_key")):
            return True
    except OSError:
        pass
    return False
