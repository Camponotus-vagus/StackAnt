import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import cv2
import numpy as np
from PIL import Image

from stackant.thumbnails import make_thumbnail_data


def _rgb(data, w, h):
    return np.frombuffer(data, np.uint8).reshape(h, w, 3)


def test_exif_orientation_applied_to_jpeg(tmp_path):
    img = Image.new("RGB", (200, 100), (255, 0, 0))
    exif = Image.Exif()
    exif[0x0112] = 6
    p = tmp_path / "a.jpg"
    img.save(p, exif=exif)
    _, w, h = make_thumbnail_data(str(p), 120)
    assert h > w


def test_16bit_tiff_scaled_not_wrapped(tmp_path):
    arr = np.full((40, 60, 3), 65535, np.uint16)
    p = tmp_path / "a.tif"
    cv2.imwrite(str(p), arr)
    data, w, h = make_thumbnail_data(str(p), 120)
    assert _rgb(data, w, h).min() >= 250


def test_pillow_fallback_16bit_gray(tmp_path, monkeypatch):
    import stackant.thumbnails as t

    monkeypatch.setattr(t, "cv2", None)
    p = tmp_path / "g.tif"
    cv2.imwrite(str(p), np.full((40, 60), 65535, np.uint16))
    data, w, h = make_thumbnail_data(str(p), 120)
    assert _rgb(data, w, h).min() >= 250


def test_pillow_fallback_float(tmp_path, monkeypatch):
    import stackant.thumbnails as t

    monkeypatch.setattr(t, "cv2", None)
    p = tmp_path / "f.tif"
    Image.fromarray(np.full((30, 30), 1.0, np.float32), "F").save(p)
    data, w, h = make_thumbnail_data(str(p), 120)
    assert _rgb(data, w, h).min() >= 250


def test_non_ascii_directory(tmp_path):
    d = tmp_path / "José"
    d.mkdir()
    _, buf = cv2.imencode(".png", np.full((20, 20, 3), 128, np.uint8))
    p = d / "x.png"
    buf.tofile(str(p))
    _, w, h = make_thumbnail_data(str(p), 120)
    assert (w, h) == (20, 20)
