"""List image files in a folder (used when the user picks a folder instead of a video)."""
from __future__ import annotations

from pathlib import Path

_EXTS = {".tif", ".tiff", ".jpg", ".jpeg", ".png", ".bmp"}


def list_images(folder: str) -> list[str]:
    p = Path(folder)
    if not p.is_dir():
        return []
    files = [f for f in p.iterdir() if f.is_file() and f.suffix.lower() in _EXTS]
    files.sort(key=lambda f: f.name)
    return [str(f) for f in files]
