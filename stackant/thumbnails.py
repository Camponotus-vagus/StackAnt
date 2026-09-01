"""Thumbnail rendering for the filmstrip.

Uses Pillow draft mode or OpenCV C/C++ backends for fast thumbnail decoding and resizing.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QImage, QPainter, QPixmap

try:
    import cv2
except ImportError:
    cv2 = None


def make_thumbnail_data(path: str, max_edge: int = 120) -> tuple[bytes, int, int]:
    """Decode and downscale an image to raw RGB bytes and (width, height).

    Optimized for filmstrip thumbnails:
    - Uses Pillow JPEG draft mode (decodes directly at reduced resolution in libjpeg)
      for ~4x-6x faster decoding of JPEGs.
    - Uses OpenCV `cv2.INTER_AREA` for fast C/C++ area downsampling of TIFF/PNG frames.
    - Falls back to Pillow BOX resampling for maximum compatibility.
    """
    ext = Path(path).suffix.lower()
    if ext in (".jpg", ".jpeg"):
        try:
            with Image.open(path) as img:
                img.draft("RGB", (max_edge, max_edge))
                img = img.convert("RGB")
                img.thumbnail((max_edge, max_edge), Image.Resampling.BOX)
                return img.tobytes("raw", "RGB"), img.width, img.height
        except Exception:  # noqa: BLE001, S110
            pass

    # OpenCV fast C/C++ image decoding & area-downsampling for TIFF, PNG, etc.
    if cv2 is not None:
        bgr = cv2.imread(path, cv2.IMREAD_COLOR)
        if bgr is not None:
            h, w = bgr.shape[:2]
            scale = min(1.0, max_edge / max(h, w))
            nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
            resized = cv2.resize(bgr, (nw, nh), interpolation=cv2.INTER_AREA)
            rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
            return rgb.tobytes("C"), nw, nh

    # Fallback to standard Pillow loading with fast BOX resampling
    with Image.open(path) as img:
        img = img.convert("RGB")
        img.thumbnail((max_edge, max_edge), Image.Resampling.BOX)
        return img.tobytes("raw", "RGB"), img.width, img.height


def make_thumbnail(path: str, max_edge: int = 120) -> QPixmap:
    try:
        data, w, h = make_thumbnail_data(path, max_edge)
        qimg = QImage(data, w, h, w * 3, QImage.Format.Format_RGB888)
        return QPixmap.fromImage(qimg.copy())
    except Exception:  # noqa: BLE001
        return make_placeholder_pixmap(max_edge)


def make_placeholder_pixmap(size: int = 120) -> QPixmap:
    """Solid-gray square with a '?' — used when a frame fails to decode."""
    pm = QPixmap(size, size)
    pm.fill(QColor(70, 70, 70))
    painter = QPainter(pm)
    painter.setPen(QColor(200, 200, 200))
    font = QFont()
    font.setPointSize(max(8, size // 4))
    painter.setFont(font)
    painter.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, "?")
    painter.end()
    return pm


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
