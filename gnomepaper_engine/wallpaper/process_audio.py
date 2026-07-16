"""Live volume / mute for wallpaper streams via PulseAudio / PipeWire."""

from __future__ import annotations

import logging
import re
import shutil
import subprocess

log = logging.getLogger(__name__)

DEFAULT_NAME_PATTERNS = (
    "linux-wallpaperengine",
    "wallpaperengine",
    "gnomepaper",
    "GnomePaper",
    "playbin",
    "GstPipeline",
    "gstreamer",
    "desktop_player",
)


def set_wallpaper_volume(
    volume_pct: int,
    *,
    muted: bool = False,
    pids: list[int] | None = None,
    name_patterns: tuple[str, ...] | list[str] | None = None,
) -> int:
    """
    Set volume and mute on all wallpaper sink-inputs.

    Matches by application/media name (LWE often has no process.id) and PID.
    volume_pct is 0–100. Returns number of sink-inputs updated.
    """
    vol = max(0, min(100, int(volume_pct)))
    patterns = tuple(name_patterns) if name_patterns is not None else DEFAULT_NAME_PATTERNS
    inputs = find_wallpaper_sink_inputs(pids=pids, name_patterns=patterns)
    if not inputs:
        log.info(
            "Audio: no sink-inputs matched (pids=%s patterns=%s)",
            pids,
            patterns,
        )
        return 0

    updated = 0
    for sid in inputs:
        ok = True
        # Always write the volume level, then set mute separately so the
        # user's slider value is stored even while focus-muted.
        if not _run(["pactl", "set-sink-input-volume", str(sid), f"{vol}%"]):
            ok = False
        want_mute = "1" if (muted or vol == 0) else "0"
        if not _run(["pactl", "set-sink-input-mute", str(sid), want_mute]):
            ok = False
        if ok:
            updated += 1

    log.info(
        "Audio: volume=%s muted=%s updated=%s ids=%s",
        vol,
        muted or vol == 0,
        updated,
        inputs,
    )
    return updated


def set_pids_volume(pids: list[int], volume_pct: int, *, muted: bool = False) -> int:
    return set_wallpaper_volume(volume_pct, muted=muted, pids=pids)


def mute_pids(pids: list[int], muted: bool = True) -> int:
    return set_wallpaper_volume(0 if muted else 100, muted=muted, pids=pids)


def find_wallpaper_sink_inputs(
    *,
    pids: list[int] | None = None,
    name_patterns: tuple[str, ...] | list[str] = DEFAULT_NAME_PATTERNS,
) -> list[int]:
    if not shutil.which("pactl"):
        return []
    try:
        out = subprocess.check_output(
            ["pactl", "list", "sink-inputs"],
            text=True,
            errors="replace",
        )
    except (OSError, subprocess.CalledProcessError):
        return []

    want_pids: set[int] = set(int(p) for p in (pids or []))
    if want_pids:
        want_pids |= _child_pids(want_pids)

    patterns_l = [p.lower() for p in name_patterns]
    found: list[int] = []
    current_index: int | None = None
    current_pid: int | None = None
    current_blob = ""

    def _commit() -> None:
        nonlocal current_index, current_pid, current_blob
        if current_index is None:
            return
        match = False
        if current_pid is not None and current_pid in want_pids:
            match = True
        blob = current_blob.lower()
        if not match and any(p in blob for p in patterns_l):
            match = True
        if match:
            found.append(current_index)
        current_index = None
        current_pid = None
        current_blob = ""

    for line in out.splitlines():
        m = re.match(r"^Sink Input #(\d+)", line)
        if m:
            _commit()
            current_index = int(m.group(1))
            current_pid = None
            current_blob = ""
            continue
        if current_index is None:
            continue
        current_blob += line + "\n"
        if "application.process.id" in line:
            m2 = re.search(r'=\s*"?(\d+)"?', line)
            if m2:
                current_pid = int(m2.group(1))

    _commit()
    seen: set[int] = set()
    uniq: list[int] = []
    for sid in found:
        if sid not in seen:
            seen.add(sid)
            uniq.append(sid)
    return uniq


def _run(cmd: list[str]) -> bool:
    if not shutil.which(cmd[0]):
        return False
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        return True
    except (OSError, subprocess.CalledProcessError) as exc:
        log.debug("audio cmd failed %s: %s", cmd, exc)
        return False


def _child_pids(roots: set[int]) -> set[int]:
    kids: set[int] = set()
    if not shutil.which("pgrep"):
        return kids
    for root in list(roots):
        try:
            out = subprocess.check_output(
                ["pgrep", "-P", str(root)],
                text=True,
                errors="replace",
            )
        except (OSError, subprocess.CalledProcessError):
            continue
        for line in out.splitlines():
            line = line.strip()
            if line.isdigit():
                kids.add(int(line))
    return kids
