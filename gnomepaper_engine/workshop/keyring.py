"""Store Steam password in the GNOME keyring (libsecret) — never in config.json."""

from __future__ import annotations

import logging
import shutil
import subprocess

log = logging.getLogger(__name__)

_SERVICE = "gnomepaper-engine"
_ATTR_USER = "username"


def keyring_available() -> bool:
    return shutil.which("secret-tool") is not None


def store_steam_password(username: str, password: str) -> bool:
    """Save password for username. Returns True on success."""
    username = (username or "").strip()
    if not username or not password or not keyring_available():
        return False
    try:
        subprocess.run(
            [
                "secret-tool",
                "store",
                "--label",
                f"GnomePaper Steam ({username})",
                "service",
                _SERVICE,
                _ATTR_USER,
                username,
            ],
            input=password + "\n",
            text=True,
            check=True,
            capture_output=True,
            timeout=30,
        )
        log.info("Stored Steam password in keyring for %s", username)
        return True
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        log.warning("keyring store failed: %s", exc)
        return False


def lookup_steam_password(username: str) -> str | None:
    username = (username or "").strip()
    if not username or not keyring_available():
        return None
    try:
        out = subprocess.check_output(
            [
                "secret-tool",
                "lookup",
                "service",
                _SERVICE,
                _ATTR_USER,
                username,
            ],
            text=True,
            timeout=15,
            stderr=subprocess.DEVNULL,
        )
        pw = out.strip()
        return pw or None
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None


def clear_steam_password(username: str) -> None:
    username = (username or "").strip()
    if not username or not keyring_available():
        return
    try:
        subprocess.run(
            [
                "secret-tool",
                "clear",
                "service",
                _SERVICE,
                _ATTR_USER,
                username,
            ],
            check=False,
            capture_output=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass
