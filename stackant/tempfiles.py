"""Temp-dir management with automatic cleanup on exit."""
from __future__ import annotations

import atexit
import shutil
import tempfile
from pathlib import Path

_TRACKED: list[Path] = []


def make_temp_dir(prefix: str = "stackant_") -> Path:
    d = Path(tempfile.mkdtemp(prefix=prefix))
    _TRACKED.append(d)
    return d


def cleanup_all() -> None:
    while _TRACKED:
        d = _TRACKED.pop()
        shutil.rmtree(d, ignore_errors=True)


atexit.register(cleanup_all)
