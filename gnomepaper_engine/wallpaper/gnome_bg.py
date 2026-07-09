"""GNOME desktop background helpers (still image via gsettings)."""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path
from urllib.parse import quote

log = logging.getLogger(__name__)

_SCHEMA = "org.gnome.desktop.background"
_KEYS = ("picture-uri", "picture-uri-dark")


def _gsettings_available() -> bool:
    return shutil.which("gsettings") is not None


def path_to_file_uri(path: Path) -> str:
    resolved = path.expanduser().resolve()
    # gsettings expects file:///… with percent-encoding for spaces
    return "file://" + quote(str(resolved))


def set_picture(path: Path, *, options: str = "zoom") -> bool:
    """Set GNOME still background to an image (light + dark)."""
    if not _gsettings_available() or not path.is_file():
        return False
    uri = path_to_file_uri(path)
    ok = True
    for key in _KEYS:
        try:
            subprocess.run(
                ["gsettings", "set", _SCHEMA, key, uri],
                check=True,
                capture_output=True,
                text=True,
            )
        except (OSError, subprocess.CalledProcessError) as exc:
            log.warning("gsettings set %s failed: %s", key, exc)
            ok = False
    try:
        subprocess.run(
            ["gsettings", "set", _SCHEMA, "picture-options", options],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        pass
    return ok


def get_picture_uri() -> str | None:
    if not _gsettings_available():
        return None
    try:
        r = subprocess.run(
            ["gsettings", "get", _SCHEMA, "picture-uri"],
            check=True,
            capture_output=True,
            text=True,
        )
        return r.stdout.strip().strip("'")
    except (OSError, subprocess.CalledProcessError):
        return None
