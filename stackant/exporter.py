"""TIFF and JPEG export helpers."""
from __future__ import annotations

import shutil
from pathlib import Path

from PIL import Image
from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDesktopServices


def export_tiff(src: str, dst: str) -> None:
    """Lossless copy of the source TIFF to `dst`."""
    src_p = Path(src)
    dst_p = Path(dst)
    dst_p.parent.mkdir(parents=True, exist_ok=True)
    if src_p.resolve() == dst_p.resolve():
        return
    shutil.copy2(src_p, dst_p)


def export_jpeg(src: str, dst: str, quality: int = 95) -> None:
    """Re-encode the source image as JPEG at the given quality (1-100)."""
    dst_p = Path(dst)
    dst_p.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(src) as img:
        img = img.convert("RGB")
        img.save(dst_p, format="JPEG", quality=int(quality), subsampling=0)


def reveal_in_file_manager(folder: str) -> bool:
    return QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(folder))))
