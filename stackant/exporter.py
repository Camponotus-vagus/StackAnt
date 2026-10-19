"""TIFF and JPEG export helpers."""
from __future__ import annotations

import os
import shutil
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDesktopServices

from .imread import imread


def _part_path(dst: Path) -> Path:
    # Keeps the real suffix so encoders pick the right format from the name.
    return dst.with_name(f"{dst.stem}.part{dst.suffix}")


def _write_atomically(dst: Path, write) -> None:
    """Run write(tmp) then rename into place; a failure never leaves `dst` truncated.

    Any non-OSError from a decoder/encoder is re-raised as OSError.
    """
    tmp = _part_path(dst)
    try:
        write(tmp)
        os.replace(tmp, dst)
    except BaseException as exc:
        tmp.unlink(missing_ok=True)
        if isinstance(exc, Exception) and not isinstance(exc, OSError):
            raise OSError(f"Could not write {dst.name}: {exc}") from exc
        raise


def export_tiff(src: str, dst: str) -> None:
    """Lossless copy of the source TIFF to `dst`."""
    src_p = Path(src)
    dst_p = Path(dst)
    dst_p.parent.mkdir(parents=True, exist_ok=True)
    if src_p.resolve() == dst_p.resolve():
        return
    _write_atomically(dst_p, lambda tmp: shutil.copy2(src_p, tmp))


def _load_rgb8(src: str) -> Image.Image:
    # Pillow clips I;16 to 8 bits and misreads RGB48 TIFFs, so 16-bit goes via cv2.
    arr = imread(src, cv2.IMREAD_ANYDEPTH | cv2.IMREAD_ANYCOLOR)
    if arr is not None and arr.dtype == np.uint16:
        arr8 = ((arr.astype(np.uint32) + 128) // 257).astype(np.uint8)
        if arr8.ndim == 2:
            return Image.fromarray(arr8).convert("RGB")
        if arr8.shape[2] == 4:
            arr8 = arr8[:, :, :3]
        return Image.fromarray(cv2.cvtColor(arr8, cv2.COLOR_BGR2RGB))
    with Image.open(src) as img:
        return img.convert("RGB")


def export_jpeg(src: str, dst: str, quality: int = 95) -> None:
    """Re-encode the source image as JPEG at the given quality (1-100)."""
    dst_p = Path(dst)
    dst_p.parent.mkdir(parents=True, exist_ok=True)

    def write(tmp: Path) -> None:
        img = _load_rgb8(src)
        img.save(tmp, format="JPEG", quality=int(quality), subsampling=0)

    _write_atomically(dst_p, write)


def reveal_in_file_manager(folder: str) -> bool:
    return QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(folder))))
