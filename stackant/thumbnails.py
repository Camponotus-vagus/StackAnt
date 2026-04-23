"""Thumbnail rendering for the filmstrip.

Uses Pillow for decoding because Qt's built-in TIFF support varies by build.
"""
from __future__ import annotations

from PIL import Image
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QImage, QPainter, QPixmap


def make_thumbnail(path: str, max_edge: int = 120) -> QPixmap:
    with Image.open(path) as img:
        img = img.convert("RGB")
        img.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
        data = img.tobytes("raw", "RGB")
        qimg = QImage(
            data, img.width, img.height, img.width * 3, QImage.Format.Format_RGB888
        )
        return QPixmap.fromImage(qimg.copy())


def make_rejected_pixmap(base: QPixmap) -> QPixmap:
    """Return a copy of `base` dimmed and tinted red to signal rejection."""
    out = QPixmap(base.size())
    out.fill(Qt.GlobalColor.transparent)
    painter = QPainter(out)
    painter.setOpacity(0.55)
    painter.drawPixmap(0, 0, base)
    painter.setOpacity(0.45)
    painter.fillRect(out.rect(), QColor(200, 40, 40))
    painter.end()
    return out
