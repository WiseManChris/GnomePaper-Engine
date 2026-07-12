"""Discover, verify, and install Almamu/linux-wallpaperengine for scene support."""

from __future__ import annotations

import hashlib
import logging
import os
import shutil
import subprocess
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

BINARY_NAMES = ("linux-wallpaperengine", "wallengine")

# CLI strings that identify a real Almamu linux-wallpaperengine binary
_IDENTITY_MARKERS = (
    "--assets-dir",
    "--disable-parallax",
    "--screen-root",
    "--disable-mouse",
    "linux-wallpaperengine",
)


@dataclass(frozen=True)
class LWEDetection:
    """Result of locating / verifying linux-wallpaperengine."""

    found: bool
    path: Path | None
    sha256: str
    verified: bool
    message: str

    @property
    def short_sha(self) -> str:
        return self.sha256[:12] if self.sha256 else ""


def project_root() -> Path:
    """Package root (…/gnomepaper_engine)."""
    return Path(__file__).resolve().parents[2]


def _repo_root_candidates() -> list[Path]:
    """Possible source-tree roots (dev checkout or remembered install path)."""
    roots: list[Path] = []
    marker = Path.home() / ".local" / "share" / "gnomepaper-engine" / "source_path"
    if marker.is_file():
        try:
            p = Path(marker.read_text(encoding="utf-8").strip())
            if p.is_dir():
                roots.append(p)
        except OSError:
            pass
    try:
        dev = Path(__file__).resolve().parents[3]
        if (dev / "pyproject.toml").is_file() or (dev / "scripts").is_dir():
            roots.append(dev)
    except IndexError:
        pass
    # Deduplicate while preserving order
    seen: set[Path] = set()
    out: list[Path] = []
    for r in roots:
        key = r.resolve()
        if key not in seen:
            seen.add(key)
            out.append(key)
    return out


def file_sha256(path: Path, *, max_bytes: int | None = None) -> str:
    """SHA-256 of a file (hex). Empty string on failure."""
    try:
        h = hashlib.sha256()
        total = 0
        with path.open("rb") as fh:
            while True:
                chunk = fh.read(1 << 20)
                if not chunk:
                    break
                h.update(chunk)
                total += len(chunk)
                if max_bytes is not None and total >= max_bytes:
                    break
        return h.hexdigest()
    except OSError as exc:
        log.debug("sha256 failed for %s: %s", path, exc)
        return ""


def _is_executable_file(path: Path) -> bool:
    try:
        if not path.is_file() and not path.is_symlink():
            return False
        real = path.resolve()
        if not real.is_file():
            return False
        return os.access(real, os.X_OK)
    except OSError:
        return False


def verify_lwe_identity(path: Path, *, timeout: float = 8.0) -> bool:
    """
    Confirm *path* is Almamu linux-wallpaperengine by probing ``--help``.

    Requires at least two distinctive CLI markers so a random binary named
    linux-wallpaperengine is rejected.
    """
    if not _is_executable_file(path):
        return False
    try:
        proc = subprocess.run(
            [str(path), "--help"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        log.debug("identity probe failed for %s: %s", path, exc)
        return False
    out = f"{proc.stdout or ''}{proc.stderr or ''}"
    hits = sum(1 for m in _IDENTITY_MARKERS if m in out)
    ok = hits >= 2
    if not ok:
        log.debug("identity probe weak for %s (hits=%s)", path, hits)
    return ok


def _candidate_paths() -> list[Path]:
    home = Path.home()
    candidates: list[Path] = [
        home / ".local" / "bin" / "linux-wallpaperengine",
        home / ".local" / "share" / "linux-wallpaperengine" / "linux-wallpaperengine",
        home / "bin" / "linux-wallpaperengine",
        home / "Applications" / "linux-wallpaperengine" / "linux-wallpaperengine",
        Path("/usr/local/bin/linux-wallpaperengine"),
        Path("/usr/bin/linux-wallpaperengine"),
        Path("/opt/linux-wallpaperengine/linux-wallpaperengine"),
        Path("/opt/linux-wallpaperengine/bin/linux-wallpaperengine"),
    ]
    for root in _repo_root_candidates():
        candidates.extend(
            [
                root
                / "third_party"
                / "linux-wallpaperengine"
                / "build"
                / "output"
                / "linux-wallpaperengine",
                root / "third_party" / "linux-wallpaperengine" / "output" / "linux-wallpaperengine",
                root / "third_party" / "linux-wallpaperengine" / "build" / "linux-wallpaperengine",
            ]
        )
    return candidates


def _probe_path(path: Path, *, skip_identity: bool = False) -> LWEDetection | None:
    """Return detection info if *path* looks like a usable LWE binary."""
    if not _is_executable_file(path):
        return None
    real = path.resolve()
    digest = file_sha256(real)
    verified = True if skip_identity else verify_lwe_identity(real)
    if not verified and not skip_identity:
        # Still allow executable named correctly if help probe fails (sandbox,
        # missing libs) but mark unverified — caller may accept with caution.
        name_ok = real.name in BINARY_NAMES or path.name in BINARY_NAMES
        if not name_ok:
            return None
    short = digest[:12] if digest else "unknown"
    if verified:
        msg = f"Found & verified · {real} · sha256:{short}…"
    else:
        msg = f"Found (checksum only) · {real} · sha256:{short}… · identity unconfirmed"
    return LWEDetection(
        found=True,
        path=real,
        sha256=digest,
        verified=verified,
        message=msg,
    )


def auto_detect_lwe(
    explicit: str | None = None,
    *,
    known_path: str | None = None,
    known_sha256: str | None = None,
) -> LWEDetection:
    """
    Locate linux-wallpaperengine with checksum + identity verification.

    Order:
      1. Explicit config path
      2. Cached path if its SHA-256 still matches (fast path)
      3. PATH (which)
      4. Well-known user / system / repo install locations
    """
    # 1. Explicit override
    if explicit:
        p = Path(explicit).expanduser()
        det = _probe_path(p)
        if det is not None:
            return det
        return LWEDetection(
            False,
            None,
            "",
            False,
            f"Custom path not usable: {p}",
        )

    # 2. Fast path: remembered path + matching checksum
    if known_path and known_sha256:
        kp = Path(known_path).expanduser()
        if _is_executable_file(kp):
            real = kp.resolve()
            digest = file_sha256(real)
            if digest and digest.lower() == known_sha256.lower():
                # Checksum match — skip slow identity probe
                short = digest[:12]
                return LWEDetection(
                    True,
                    real,
                    digest,
                    True,
                    f"Found (checksum match) · {real} · sha256:{short}…",
                )
            log.info(
                "Cached LWE checksum mismatch at %s — re-scanning",
                real,
            )

    # 3. PATH + 4. known locations (verified first, then any executable fallback)
    ordered: list[Path] = []
    for name in BINARY_NAMES:
        which = shutil.which(name)
        if which:
            ordered.append(Path(which))
    ordered.extend(_candidate_paths())

    seen: set[Path] = set()
    fallback_unverified: LWEDetection | None = None
    for path in ordered:
        try:
            key = path.resolve() if path.exists() else path
        except OSError:
            key = path
        if key in seen:
            continue
        seen.add(key)
        det = _probe_path(path)
        if det is None:
            continue
        if det.verified:
            log.info("Found linux-wallpaperengine at %s", det.path)
            return det
        if fallback_unverified is None:
            fallback_unverified = det

    if fallback_unverified is not None:
        log.warning(
            "linux-wallpaperengine at %s failed identity probe",
            fallback_unverified.path,
        )
        return fallback_unverified

    log.warning("linux-wallpaperengine not found on PATH or known locations")
    return LWEDetection(
        False,
        None,
        "",
        False,
        "Not found — install the scene engine or set a custom path",
    )


def find_lwe_binary(explicit: str | None = None) -> Path | None:
    """Locate linux-wallpaperengine (path only). Prefer :func:`auto_detect_lwe`."""
    det = auto_detect_lwe(explicit)
    return det.path if det.found else None


def lwe_status(
    explicit: str | None = None,
    *,
    known_path: str | None = None,
    known_sha256: str | None = None,
) -> LWEDetection:
    """Full detection result for Settings / diagnostics."""
    return auto_detect_lwe(
        explicit,
        known_path=known_path,
        known_sha256=known_sha256,
    )


def find_assets_dir(extra_steam_paths: list[str] | None = None) -> Path | None:
    """Locate Wallpaper Engine ``assets`` folder (required by LWE for many scenes)."""
    from gnomepaper_engine.steam.paths import (
        discover_steam_installs,
        wallpaper_engine_install_dirs,
    )

    installs = discover_steam_installs(extra_steam_paths)
    for install in installs:
        for we in wallpaper_engine_install_dirs(install):
            assets = we / "assets"
            if assets.is_dir():
                return assets
    return None


def find_install_script() -> Path | None:
    """Locate ``scripts/install_linux_wallpaperengine.sh`` if available."""
    for root in _repo_root_candidates():
        candidate = root / "scripts" / "install_linux_wallpaperengine.sh"
        if candidate.is_file():
            return candidate
    return None


def install_hint() -> str:
    script = find_install_script()
    lines = [
        "Scene wallpapers need linux-wallpaperengine (Almamu).",
        "Note: Steam’s “Wallpaper Engine” app is different — scenes need the Linux CLI binary.",
        "",
        "Install options:",
        "  • Settings → Scene engine → Install scene engine (recommended)",
    ]
    if script is not None:
        lines.append(f"  • Terminal: {script}")
    lines.extend(
        [
            "  • Build from https://github.com/Almamu/linux-wallpaperengine",
            "  • Put the binary on PATH, or at:",
            "      ~/.local/bin/linux-wallpaperengine",
            "      ~/.local/share/linux-wallpaperengine/linux-wallpaperengine",
            "  • Or set a custom path in Settings → Scene engine",
        ]
    )
    return "\n".join(lines)


def _terminal_launchers(script: Path) -> list[list[str]]:
    """Candidate commands that open a terminal running the install script."""
    quoted = str(script)
    # Keep the window open so the user can read errors / sudo prompts
    inner = f'bash "{quoted}"; echo; echo "Press Enter to close…"; read -r _'
    return [
        ["xdg-terminal-exec", "bash", "-lc", inner],
        ["gnome-terminal", "--", "bash", "-lc", inner],
        ["kgx", "-e", "bash", "-lc", inner],
        ["ptyxis", "--", "bash", "-lc", inner],
        ["konsole", "-e", "bash", "-lc", inner],
        ["xfce4-terminal", "-e", f"bash -lc {inner!r}"],
        ["xterm", "-e", "bash", "-lc", inner],
    ]


def launch_lwe_install(
    *,
    on_line: Callable[[str], None] | None = None,
    prefer_terminal: bool = True,
) -> tuple[bool, str, subprocess.Popen[str] | None]:
    """
    Start the linux-wallpaperengine install script.

    Prefers a terminal (sudo password prompts work). Falls back to a
    background subprocess. Returns ``(started, message, process_or_None)``.
    """
    script = find_install_script()
    if script is None:
        return (
            False,
            "Install script not found. Clone GnomePaper-Engine and run "
            "scripts/install_linux_wallpaperengine.sh, or set a custom binary path.",
            None,
        )

    if not os.access(script, os.X_OK):
        try:
            script.chmod(script.stat().st_mode | 0o111)
        except OSError:
            pass

    if prefer_terminal:
        for cmd in _terminal_launchers(script):
            exe = cmd[0]
            if shutil.which(exe) is None:
                continue
            try:
                proc = subprocess.Popen(
                    cmd,
                    start_new_session=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                log.info("Launched LWE install via terminal: %s", exe)
                return (
                    True,
                    f"Opened a terminal to run the installer.\n"
                    f"Approve any sudo prompts, wait for the build, then click "
                    f"Re-detect.\nScript: {script}",
                    proc,
                )
            except OSError as exc:
                log.debug("terminal launch failed (%s): %s", exe, exc)
                continue

    # Background subprocess (no interactive sudo)
    try:
        proc = subprocess.Popen(
            ["bash", str(script)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
    except OSError as exc:
        return False, f"Could not start installer: {exc}", None

    if on_line is not None and proc.stdout is not None:

        def _pump() -> None:
            assert proc.stdout is not None
            for line in proc.stdout:
                try:
                    on_line(line.rstrip("\n"))
                except Exception:
                    pass

        threading.Thread(target=_pump, name="lwe-install-log", daemon=True).start()

    log.info("Started LWE install in background: %s", script)
    return (
        True,
        f"Installer running in the background (no terminal found).\n"
        f"If dependency install needs sudo, re-run from a terminal:\n  {script}",
        proc,
    )


