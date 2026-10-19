"""List image files in a folder (used when the user picks a folder instead of a video)."""
from __future__ import annotations

import re
from pathlib import Path

_EXTS = {".tif", ".tiff", ".jpg", ".jpeg", ".png", ".bmp"}
_DIGITS_RE = re.compile(r"(\d+)")


def _natural_key(name: str) -> list[tuple[int, int, str]]:
    return [
        (0, int(part), "") if part.isdigit() else (1, 0, part.casefold())
        for part in _DIGITS_RE.split(name)
        if part
    ]


def list_images(folder: str) -> list[str]:
    p = Path(folder)
    if not p.is_dir():
        return []
    files = [
        f for f in p.iterdir()
        # Dot-files include macOS AppleDouble "._IMG.jpg" sidecars, which are not images.
        if f.is_file() and not f.name.startswith(".") and f.suffix.lower() in _EXTS
    ]
    files.sort(key=lambda f: (_natural_key(f.name), f.name))
    return [str(f) for f in files]
