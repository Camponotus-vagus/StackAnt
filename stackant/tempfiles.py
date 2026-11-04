"""Temp-dir management with automatic cleanup on exit."""
from __future__ import annotations

import atexit
import os
import shutil
import stat
import tempfile
import time
from pathlib import Path

_PREFIX = "stackant_"
_TRACKED: list[Path] = []


def make_temp_dir(prefix: str = _PREFIX) -> Path:
    d = Path(tempfile.mkdtemp(prefix=prefix))
    _TRACKED.append(d)
    return d


def cleanup_all() -> None:
    while _TRACKED:
        d = _TRACKED.pop()
        shutil.rmtree(d, ignore_errors=True)


atexit.register(cleanup_all)


def remove_temp_dir(path) -> None:
    """Delete one tracked temp dir now and stop tracking it.

    The batch processor cleans up after each video so disk use stays bounded
    to roughly one video's frames at a time.
    """
    p = Path(path)
    shutil.rmtree(p, ignore_errors=True)
    try:
        _TRACKED.remove(p)
    except ValueError:
        pass


def _owned_by_current_user(st: os.stat_result) -> bool:
    # The system temp dir is shared on POSIX: never delete a symlink or another
    # user's stackant_* dir (matters most when the app is run as root).
    getuid = getattr(os, "getuid", None)
    return getuid is None or st.st_uid == getuid()


def sweep_stale(max_age_hours: float = 24.0, root: str | None = None) -> int:
    """Delete untracked stackant_* dirs left by a crash or SIGKILL; return the count.

    atexit never runs after a hard kill, and on Windows open handles can make
    rmtree fail at exit, so multi-GB frame dirs would otherwise pile up in the
    temp folder. The age floor keeps a concurrently running instance safe.
    """
    base = Path(root or tempfile.gettempdir())
    cutoff = time.time() - max_age_hours * 3600
    removed = 0
    try:
        candidates = list(base.glob(f"{_PREFIX}*"))
    except OSError:
        return 0
    for d in candidates:
        try:
            st = d.lstat()
            if (
                not stat.S_ISDIR(st.st_mode)
                or not _owned_by_current_user(st)
                or d in _TRACKED
                or st.st_mtime > cutoff
            ):
                continue
        except OSError:
            continue
        shutil.rmtree(d, ignore_errors=True)
        if not d.exists():
            removed += 1
    return removed
