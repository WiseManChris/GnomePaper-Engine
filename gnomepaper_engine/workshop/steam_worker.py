"""
Isolated Steam network worker (subprocess only).

Uses ValvePython ``steam`` + gevent. Must NOT be imported by the GTK UI
process — gevent monkey-patching would break the desktop app.

Invoked as::

    python -m gnomepaper_engine.workshop.steam_worker link|download ...

Communicates via JSON on stdout (last line is the result object).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import traceback
from pathlib import Path

# Steam network chatter → stderr only (stdout is reserved for JSON result)
logging.basicConfig(level=logging.WARNING, stream=sys.stderr)


def _emit(payload: dict) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _fail(message: str, **extra: object) -> int:
    out = {"ok": False, "message": message}
    out.update(extra)
    _emit(out)
    return 1


def _ok(message: str, **extra: object) -> int:
    out = {"ok": True, "message": message}
    out.update(extra)
    _emit(out)
    return 0


def _patch_gevent() -> None:
    import gevent.monkey

    gevent.monkey.patch_socket()
    gevent.monkey.patch_select()
    gevent.monkey.patch_ssl()


def _make_client(cred_dir: Path):
    from steam.client import SteamClient
    from steam.enums import EPersonaState

    cred_dir.mkdir(parents=True, exist_ok=True)
    client = SteamClient()
    client.set_credential_location(str(cred_dir))
    client.persona_state = EPersonaState.Offline
    return client


def _password_from_env_or_args(args: argparse.Namespace) -> str:
    """
    Read password carefully — do NOT strip().

    Spaces at ends are rare but valid; stripping has broken real passwords.
    Only strip a single trailing newline if the env helper added one.
    """
    pw = os.environ.get("GNOMEPAPER_STEAM_PASSWORD")
    if pw is None or pw == "":
        pw = args.password or ""
    if pw.endswith("\n") and pw.count("\n") == 1:
        pw = pw[:-1]
    if pw.endswith("\r"):
        pw = pw[:-1]
    return pw


def _login_password(client, username: str, password: str, guard: str = ""):
    """
    Login with password (+ optional Guard).

    Important:
    * Do not send both two_factor_code and auth_code at once (Steam rejects that).
    * InvalidPassword is often NOT a wrong password — wrong account name, missing
      Guard, or rate limiting. Callers must interpret EResult carefully.
    """
    from steam.enums import EResult

    guard = (guard or "").strip()
    username = (username or "").strip()

    # Fresh connection sometimes needed after a failed attempt
    def _once(**kwargs):
        return client.login(username, password, **kwargs)

    if not guard:
        result = _once()
        # Steam sometimes wants 2FA but returns InvalidPassword on first hit
        if result == EResult.InvalidPassword:
            return result
        if result in (EResult.TryAnotherCM, EResult.ServiceUnavailable):
            client.disconnect()
            if client.connect(retry=5):
                result = _once()
        return result

    # Mobile authenticator (most common) — 5 alphanumeric chars
    result = _once(two_factor_code=guard)
    if result == EResult.OK:
        return result
    if result in (
        EResult.TwoFactorCodeMismatch,
        EResult.AccountLoginDeniedNeedTwoFactor,
    ):
        return result

    # Email Steam Guard code
    if result in (
        EResult.AccountLogonDenied,
        EResult.InvalidLoginAuthCode,
        EResult.ExpiredLoginAuthCode,
        EResult.InvalidPassword,  # sometimes email Guard mis-reported
    ):
        result2 = _once(auth_code=guard)
        if result2 == EResult.OK:
            return result2
        # Prefer the more specific second result
        return result2

    if result in (EResult.TryAnotherCM, EResult.ServiceUnavailable):
        client.disconnect()
        if client.connect(retry=5):
            return _once(two_factor_code=guard)

    return result


def _map_login_result(result, *, had_guard: bool) -> dict | None:
    """Return a _fail payload dict if login failed, else None for OK."""
    from steam.enums import EResult

    if result == EResult.OK:
        return None

    if result in (
        EResult.AccountLoginDeniedNeedTwoFactor,
        EResult.TwoFactorCodeMismatch,
    ):
        msg = (
            "Steam Mobile Guard code required."
            if result == EResult.AccountLoginDeniedNeedTwoFactor
            else "Steam Mobile Guard code was incorrect."
        )
        return {
            "message": msg + " Open Steam Mobile → Guard codes.",
            "needs_guard": True,
            "eresult": int(result),
        }

    if result in (
        EResult.AccountLogonDenied,
        EResult.InvalidLoginAuthCode,
        EResult.ExpiredLoginAuthCode,
    ):
        msg = (
            "Steam emailed a Guard code."
            if result == EResult.AccountLogonDenied
            else "Email Guard code was incorrect or expired."
        )
        return {
            "message": msg + " Check email and enter the code.",
            "needs_guard": True,
            "eresult": int(result),
        }

    if result == EResult.RateLimitExceeded:
        return {
            "message": "Steam is rate-limiting logins. Wait 10–15 minutes, then try again.",
            "rate_limited": True,
            "eresult": int(result),
        }

    if result == EResult.InvalidPassword:
        # Valve overuses this code — do not only blame the password
        if not had_guard:
            return {
                "message": (
                    "Steam rejected the login (code: InvalidPassword). "
                    "If you are sure the password is right:\n"
                    "• Use your Steam account name (login), not display name "
                    "(e.g. insanespider365 — not Wise_Man_Chris)\n"
                    "• Enter your Steam Mobile Guard code in the next step "
                    "(Steam often returns this error when Guard is required)\n"
                    "• Turn off CAPS LOCK / check keyboard layout"
                ),
                "needs_password": True,
                "needs_guard": True,  # offer Guard step
                "eresult": int(result),
            }
        return {
            "message": (
                "Steam still rejected the login. Double-check account name + password, "
                "and that the Guard code is the newest one from Steam Mobile."
            ),
            "needs_password": True,
            "needs_guard": True,
            "eresult": int(result),
        }

    if result in (EResult.TryAnotherCM, EResult.ServiceUnavailable):
        return {
            "message": "Steam network is busy/unavailable. Try again in a minute.",
            "eresult": int(result),
        }

    return {
        "message": f"Steam login failed: {EResult(result)!r}",
        "needs_password": True,
        "eresult": int(result),
    }


def cmd_link(args: argparse.Namespace) -> int:
    _patch_gevent()
    from steam.enums import EResult

    username = (args.username or "").strip()
    password = _password_from_env_or_args(args)
    guard = (args.guard or "").strip()

    if not username:
        return _fail(
            "Steam account name is required (login name, not profile display name).",
            needs_password=True,
        )
    if not password:
        return _fail("Password is required.", needs_password=True)

    # Log length only — never the secret
    sys.stderr.write(
        f"gnomepaper steam_worker link user={username!r} "
        f"password_len={len(password)} guard_len={len(guard)}\n"
    )

    client = _make_client(Path(args.cred_dir))
    try:
        if not client.connect(retry=5):
            return _fail("Could not connect to Steam network. Check internet / VPN.")

        result = _login_password(client, username, password, guard)

        mapped = _map_login_result(result, had_guard=bool(guard))
        if mapped is not None:
            return _fail(**mapped)

        # Wait for login key (enables seamless re-auth)
        if not client.login_key:
            client.wait_event(client.EVENT_NEW_LOGIN_KEY, timeout=15)

        login_key = client.login_key or ""
        return _ok(
            f"Linked Steam account “{username}” (seamless session).",
            login_key=login_key,
            linked=True,
            steam_id=str(getattr(client.steam_id, "as_64", "") or getattr(client, "steam_id", "") or ""),
        )
    except Exception as exc:
        return _fail(f"Steam link error: {exc}", detail=traceback.format_exc()[-800:])
    finally:
        try:
            client.logout()
        except Exception:
            pass
        try:
            client.disconnect()
        except Exception:
            pass


def _login_with_access_token(client, account_name: str, access_token: str):
    """Modern JWT logon (used after QR / refresh_token)."""
    from steam.core.crypto import sha1_hash
    from steam.core.msg import MsgProto
    from steam.enums import EOSType, EResult
    from steam.enums.emsg import EMsg
    from steam.steamid import SteamID
    import ipaddress

    eresult = client._pre_login()
    if eresult != EResult.OK:
        return eresult

    client.username = account_name
    message = MsgProto(EMsg.ClientLogon)
    message.header.steamid = SteamID(type="Individual", universe="Public")
    message.body.protocol_version = 65580
    message.body.client_package_version = 1561159470
    message.body.client_os_type = EOSType.LinuxUnknown
    message.body.client_language = "english"
    message.body.should_remember_password = True
    message.body.supports_rate_limit_response = True
    message.body.chat_mode = client.chat_mode
    try:
        message.body.obfuscated_private_ip.v4 = (
            int(ipaddress.IPv4Address(client.connection.local_address)) ^ 0xF00DBAAD
        )
    except Exception:
        pass
    message.body.account_name = account_name
    message.body.access_token = access_token

    sentry = client.get_sentry(account_name)
    if sentry is None:
        message.body.eresult_sentryfile = EResult.FileNotFound
    else:
        message.body.eresult_sentryfile = EResult.OK
        message.body.sha_sentryfile = sha1_hash(sentry)

    client.send(message)
    resp = client.wait_msg(EMsg.ClientLogOnResponse, timeout=30)
    if resp is None:
        return EResult.Fail
    return EResult(resp.body.eresult)


def cmd_download(args: argparse.Namespace) -> int:
    _patch_gevent()
    from steam.client.cdn import CDNClient
    from steam.enums import EResult
    from steam.exceptions import SteamError

    username = (args.username or "").strip()
    item_id = str(args.item_id).strip()
    dest = Path(args.dest)
    login_key = os.environ.get("GNOMEPAPER_STEAM_LOGIN_KEY", "") or (args.login_key or "")
    access_token = os.environ.get("GNOMEPAPER_STEAM_ACCESS_TOKEN", "") or (
        getattr(args, "access_token", "") or ""
    )
    password = _password_from_env_or_args(args)
    guard = (args.guard or "").strip()

    if not item_id.isdigit():
        return _fail(f"Invalid workshop id: {item_id}")
    if not access_token and not login_key and not password:
        return _fail(
            "No Steam session. Link Steam with QR (top-left).",
            needs_password=True,
        )
    if not username and not access_token:
        return _fail("Username required", needs_password=True)

    client = _make_client(Path(args.cred_dir))
    try:
        if not client.connect(retry=5):
            return _fail("Could not connect to Steam network")

        if access_token:
            # QR / modern token login — account_name may be empty for some tokens
            result = _login_with_access_token(
                client, username or "user", access_token
            )
            if result != EResult.OK:
                return _fail(
                    f"Steam token login failed: {EResult(result)!r}. "
                    "Scan the Link QR again.",
                    needs_password=True,
                    eresult=int(result),
                )
        elif login_key:
            result = client.login(username, login_key=login_key)
            if result != EResult.OK:
                if not password:
                    return _fail(
                        "Steam session expired. Link with QR again (top-left).",
                        needs_password=True,
                        eresult=int(result),
                    )
                result = _login_password(client, username, password, guard)
                mapped = _map_login_result(result, had_guard=bool(guard))
                if mapped is not None:
                    return _fail(**mapped)
        else:
            result = _login_password(client, username, password, guard)
            mapped = _map_login_result(result, had_guard=bool(guard))
            if mapped is not None:
                return _fail(**mapped)

        new_key = login_key
        if not access_token:
            if not client.login_key:
                client.wait_event(client.EVENT_NEW_LOGIN_KEY, timeout=10)
            new_key = client.login_key or login_key

        cdn = CDNClient(client)
        try:
            manifest = cdn.get_manifest_for_workshop_item(int(item_id))
        except SteamError as exc:
            return _fail(f"Could not fetch workshop manifest: {exc}")
        except Exception as exc:
            return _fail(f"Workshop lookup failed: {exc}")

        dest.mkdir(parents=True, exist_ok=True)
        for child in list(dest.iterdir()):
            try:
                if child.is_file():
                    child.unlink()
                else:
                    import shutil

                    shutil.rmtree(child)
            except OSError:
                pass

        files = 0
        for mfile in manifest:
            if not getattr(mfile, "is_file", True):
                continue
            try:
                mfile.download_to(str(dest))
                files += 1
            except Exception as exc:
                return _fail(f"Download failed for a file: {exc}")

        if files == 0:
            try:
                if not any(dest.iterdir()):
                    return _fail("Download produced no files")
            except OSError:
                return _fail("Download produced no files")

        return _ok(
            f"Downloaded workshop item {item_id} ({files} files)",
            path=str(dest),
            login_key=new_key or "",
            linked=True,
            files=files,
        )
    except Exception as exc:
        return _fail(f"Steam download error: {exc}", detail=traceback.format_exc()[-800:])
    finally:
        try:
            client.logout()
        except Exception:
            pass
        try:
            client.disconnect()
        except Exception:
            pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="steam_worker")
    parser.add_argument(
        "--cred-dir",
        default=str(Path.home() / ".local" / "share" / "gnomepaper-engine" / "steam_native"),
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_link = sub.add_parser("link")
    p_link.add_argument("--username", required=True)
    p_link.add_argument("--password", default="")
    p_link.add_argument("--guard", default="")
    p_link.set_defaults(func=cmd_link)

    p_dl = sub.add_parser("download")
    p_dl.add_argument("--username", default="")
    p_dl.add_argument("--item-id", required=True)
    p_dl.add_argument("--dest", required=True)
    p_dl.add_argument("--login-key", default="")
    p_dl.add_argument("--access-token", default="")
    p_dl.add_argument("--password", default="")
    p_dl.add_argument("--guard", default="")
    p_dl.set_defaults(func=cmd_download)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
