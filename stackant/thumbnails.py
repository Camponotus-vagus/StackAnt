"""Thumbnail rendering for the filmstrip.

Uses Pillow for decoding because Qt's built-in TIFF support varies by build.
"""
from __future__ import annotations

from PIL import Image
from PyQt6.QtGui import QImage, QPixmap


def make_thumbnail(path: str, max_edge: int = 120) -> QPixmap:
    with Image.open(path) as img:
        img = img.convert("RGB")
        img.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
        data = img.tobytes("raw", "RGB")
        qimg = QImage(
            data, img.width, img.height, img.width * 3, QImage.Format.Format_RGB888
        )
        return QPixmap.fromImage(qimg.copy())
