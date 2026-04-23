"""Image loading helpers for the preview panel."""
from __future__ import annotations

from PIL import Image
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage, QPixmap


def load_pixmap(path: str) -> QPixmap:
    with Image.open(path) as img:
        img = img.convert("RGB")
        data = img.tobytes("raw", "RGB")
        qimg = QImage(
            data, img.width, img.height, img.width * 3, QImage.Format.Format_RGB888
        )
        return QPixmap.fromImage(qimg.copy())


def scaled_for_preview(pixmap: QPixmap, max_edge: int) -> tuple[QPixmap, float]:
    """Return (scaled_pixmap, scale_factor) so longest edge <= max_edge."""
    longest = max(pixmap.width(), pixmap.height())
    if longest <= max_edge:
        return pixmap, 1.0
    scale = max_edge / longest
    scaled = pixmap.scaled(
        int(pixmap.width() * scale),
        int(pixmap.height() * scale),
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    return scaled, scale
