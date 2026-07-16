"""
Steam Mobile QR login via IAuthenticationService (no password).

Flow:
  1. BeginAuthSessionViaQR → challenge_url
  2. Show QR (user scans in Steam Guard app)
  3. PollAuthSessionStatus until access_token + refresh_token
  4. Persist tokens for seamless CM login / downloads
"""

from __future__ import annotations

import json
import logging
import time
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import requests

log = logging.getLogger(__name__)

_API = "https://api.steampowered.com/IAuthenticationService"
_BEGIN_QR = f"{_API}/BeginAuthSessionViaQR/v1/"
_POLL = f"{_API}/PollAuthSessionStatus/v1/"
_REFRESH = f"{_API}/GenerateAccessTokenForApp/v1/"


@dataclass
class QRSession:
    client_id: str
    request_id: str
    interval: float
    challenge_url: str
    version: int = 1
    allowed_confirmations: list = field(default_factory=list)


@dataclass
class QRAuthResult:
    ok: bool
    message: str
    account_name: str = ""
    steamid: str = ""
    access_token: str = ""
    refresh_token: str = ""


def session_file() -> Path:
    from gnomepaper_engine.config import xdg_data_home

    d = xdg_data_home() / "gnomepaper-engine" / "steam_native"
    d.mkdir(parents=True, exist_ok=True)
    return d / "qr_session.json"


def save_tokens(
    *,
    account_name: str,
    steamid: str,
    access_token: str,
    refresh_token: str,
) -> None:
    path = session_file()
    data = {
        "account_name": account_name,
        "steamid": steamid,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "updated": int(time.time()),
    }
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def load_tokens() -> dict[str, str] | None:
    path = session_file()
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not data.get("refresh_token") and not data.get("access_token"):
        return None
    return {k: str(v) for k, v in data.items()}


def clear_tokens() -> None:
    try:
        session_file().unlink(missing_ok=True)
    except OSError:
        pass


def begin_qr_session(device_name: str = "GnomePaper Engine") -> QRSession:
    payload = {
        "device_details": {
            "device_friendly_name": device_name,
            "platform_type": 2,  # SteamClient
            "os_type": 16,  # Windows 10 (Matches EOSType.Windows10 in steam_worker.py)
        },
        "website_id": "Client",
    }
    resp = requests.post(
        _BEGIN_QR,
        json=payload,
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json",
            "Origin": "https://steamcommunity.com",
            "Referer": "https://steamcommunity.com/login/home/?goto=",
            "User-Agent": "Mozilla/5.0 GnomePaper-Engine",
        },
        timeout=20,
    )
    resp.raise_for_status()
    body = resp.json().get("response") or resp.json()
    if "client_id" not in body or "challenge_url" not in body:
        raise RuntimeError(f"Unexpected QR start response: {body!r}")
    return QRSession(
        client_id=str(body["client_id"]),
        request_id=str(body["request_id"]),
        interval=float(body.get("interval") or 5.0),
        challenge_url=str(body["challenge_url"]),
        version=int(body.get("version") or 1),
        allowed_confirmations=list(body.get("allowed_confirmations") or []),
    )


def poll_qr_session(session: QRSession) -> dict[str, Any]:
    resp = requests.post(
        _POLL,
        data={
            "client_id": session.client_id,
            "request_id": session.request_id,
        },
        headers={
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Accept": "application/json",
            "Origin": "https://steamcommunity.com",
            "Referer": "https://steamcommunity.com/login/home/?goto=",
            "User-Agent": "Mozilla/5.0 GnomePaper-Engine",
        },
        timeout=20,
    )
    resp.raise_for_status()
    body = resp.json()
    if isinstance(body, dict) and "response" in body:
        return body["response"] or {}
    return body if isinstance(body, dict) else {}


def wait_for_qr_approval(
    session: QRSession,
    *,
    timeout: float = 300.0,
    should_cancel: Callable[[], bool] | None = None,
    on_poll: Callable[[dict], None] | None = None,
) -> QRAuthResult:
    """Block until mobile approves or timeout/cancel."""
    start = time.monotonic()
    interval = max(2.0, float(session.interval or 5.0))

    while time.monotonic() - start < timeout:
        if should_cancel is not None and should_cancel():
            return QRAuthResult(False, "Cancelled.")

        try:
            poll = poll_qr_session(session)
        except Exception as exc:
            log.warning("QR poll failed: %s", exc)
            time.sleep(interval)
            continue

        if on_poll:
            try:
                on_poll(poll)
            except Exception:
                pass

        access = str(poll.get("access_token") or "")
        refresh = str(poll.get("refresh_token") or "")
        if access and refresh:
            account = str(poll.get("account_name") or "")
            steamid = str(poll.get("steamid") or "")
            save_tokens(
                account_name=account,
                steamid=steamid,
                access_token=access,
                refresh_token=refresh,
            )
            return QRAuthResult(
                True,
                f"Linked via QR as “{account or steamid}”. Downloads are seamless now.",
                account_name=account,
                steamid=steamid,
                access_token=access,
                refresh_token=refresh,
            )

        time.sleep(interval)

    return QRAuthResult(False, "Timed out waiting for QR approval. Try again.")


def refresh_access_token() -> dict[str, str] | None:
    """Use stored refresh_token to mint a fresh access_token."""
    tokens = load_tokens()
    if not tokens or not tokens.get("refresh_token"):
        return None
    steamid = tokens.get("steamid") or ""
    refresh = tokens["refresh_token"]
    try:
        resp = requests.post(
            _REFRESH,
            data={
                "refresh_token": refresh,
                "steamid": steamid,
            },
            headers={
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "Accept": "application/json",
            },
            timeout=20,
        )
        resp.raise_for_status()
        body = resp.json().get("response") or resp.json()
        access = str(body.get("access_token") or "")
        # Some responses rotate refresh_token
        new_refresh = str(body.get("refresh_token") or refresh)
        if not access:
            log.warning("token refresh returned no access_token: %s", body)
            return tokens  # try old access
        save_tokens(
            account_name=tokens.get("account_name") or "",
            steamid=steamid,
            access_token=access,
            refresh_token=new_refresh,
        )
        return load_tokens()
    except Exception as exc:
        log.warning("token refresh failed: %s", exc)
        return tokens


def challenge_url_to_png_bytes(challenge_url: str, box_size: int = 8) -> bytes:
    """Render challenge_url as a PNG QR code (local, no third-party image host)."""
    import io

    import qrcode

    qr = qrcode.QRCode(version=None, box_size=box_size, border=2)
    qr.add_data(challenge_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def challenge_url_public_image(challenge_url: str) -> str:
    """Fallback online QR image URL if local qrcode is unavailable."""
    enc = urllib.parse.quote(challenge_url, safe="")
    return f"https://api.qrserver.com/v1/create-qr-code/?size=280x280&data={enc}"
