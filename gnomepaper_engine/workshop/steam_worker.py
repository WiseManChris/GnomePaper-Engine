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
import os
import sys
import traceback
from pathlib import Path


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


def cmd_link(args: argparse.Namespace) -> int:
    _patch_gevent()
    from steam.enums import EResult

    username = (args.username or "").strip()
    password = os.environ.get("GNOMEPAPER_STEAM_PASSWORD", "") or (args.password or "")
    guard = (args.guard or "").strip()
    if not username or not password:
        return _fail("Username and password required", needs_password=True)

    client = _make_client(Path(args.cred_dir))
    try:
        if not client.connect(retry=3):
            return _fail("Could not connect to Steam network")

        result = client.login(
            username,
            password,
            two_factor_code=guard or None,
            auth_code=guard or None,
        )
        # Wait for login key (enables seamless re-auth)
        if result == EResult.OK and not client.login_key:
            client.wait_event(client.EVENT_NEW_LOGIN_KEY, timeout=12)

        if result == EResult.AccountLogonDenied or result == EResult.AccountLoginDeniedNeedTwoFactor:
            return _fail(
                "Steam Guard code required — open Steam Mobile and enter the code.",
                needs_guard=True,
                eresult=int(result),
            )
        if result == EResult.TwoFactorCodeMismatch or result == EResult.InvalidLoginAuthCode:
            return _fail(
                "Steam Guard code incorrect — try again.",
                needs_guard=True,
                eresult=int(result),
            )
        if result == EResult.InvalidPassword:
            return _fail("Wrong Steam password.", needs_password=True, eresult=int(result))
        if result == EResult.RateLimitExceeded:
            return _fail(
                "Steam rate-limited logins. Wait a few minutes.",
                rate_limited=True,
                eresult=int(result),
            )
        if result != EResult.OK:
            return _fail(
                f"Steam login failed: {EResult(result)!r}",
                needs_password=True,
                eresult=int(result),
            )

        login_key = client.login_key or ""
        return _ok(
            f"Linked Steam account “{username}” (seamless session).",
            login_key=login_key,
            linked=True,
            steam_id=str(getattr(client, "steam_id", "") or ""),
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


def cmd_download(args: argparse.Namespace) -> int:
    _patch_gevent()
    from steam.client.cdn import CDNClient
    from steam.enums import EResult
    from steam.exceptions import SteamError

    username = (args.username or "").strip()
    item_id = str(args.item_id).strip()
    dest = Path(args.dest)
    login_key = os.environ.get("GNOMEPAPER_STEAM_LOGIN_KEY", "") or (args.login_key or "")
    password = os.environ.get("GNOMEPAPER_STEAM_PASSWORD", "") or (args.password or "")
    guard = (args.guard or "").strip()

    if not username:
        return _fail("Username required", needs_password=True)
    if not item_id.isdigit():
        return _fail(f"Invalid workshop id: {item_id}")
    if not login_key and not password:
        return _fail(
            "No Steam session. Link Steam once (top-left).",
            needs_password=True,
        )

    client = _make_client(Path(args.cred_dir))
    try:
        if not client.connect(retry=3):
            return _fail("Could not connect to Steam network")

        if login_key:
            result = client.login(username, login_key=login_key)
            if result == EResult.InvalidPassword:
                # Expired session key — need password again
                if not password:
                    return _fail(
                        "Steam session expired. Link Steam again (top-left).",
                        needs_password=True,
                        eresult=int(result),
                    )
                result = client.login(
                    username,
                    password,
                    two_factor_code=guard or None,
                    auth_code=guard or None,
                )
        else:
            result = client.login(
                username,
                password,
                two_factor_code=guard or None,
                auth_code=guard or None,
            )

        if result in (
            EResult.AccountLogonDenied,
            EResult.AccountLoginDeniedNeedTwoFactor,
        ):
            return _fail(
                "Steam Guard code required.",
                needs_guard=True,
                eresult=int(result),
            )
        if result in (EResult.TwoFactorCodeMismatch, EResult.InvalidLoginAuthCode):
            return _fail("Steam Guard code incorrect.", needs_guard=True, eresult=int(result))
        if result == EResult.RateLimitExceeded:
            return _fail("Steam rate-limited logins. Wait a few minutes.", rate_limited=True)
        if result != EResult.OK:
            return _fail(
                f"Steam login failed: {EResult(result)!r}",
                needs_password=True,
                eresult=int(result),
            )

        # Refresh login key for next time
        if not client.login_key:
            client.wait_event(client.EVENT_NEW_LOGIN_KEY, timeout=8)
        new_key = client.login_key or login_key

        cdn = CDNClient(client)
        try:
            manifest = cdn.get_manifest_for_workshop_item(int(item_id))
        except SteamError as exc:
            return _fail(f"Could not fetch workshop manifest: {exc}")
        except Exception as exc:
            return _fail(f"Workshop lookup failed: {exc}")

        dest.mkdir(parents=True, exist_ok=True)
        # Clear previous partial download
        for child in dest.iterdir():
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

        if files == 0 and not any(dest.iterdir()):
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
    p_dl.add_argument("--username", required=True)
    p_dl.add_argument("--item-id", required=True)
    p_dl.add_argument("--dest", required=True)
    p_dl.add_argument("--login-key", default="")
    p_dl.add_argument("--password", default="")
    p_dl.add_argument("--guard", default="")
    p_dl.set_defaults(func=cmd_download)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
