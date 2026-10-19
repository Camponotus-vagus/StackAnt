import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import cv2
import numpy as np
import pytest
from PyQt6.QtWidgets import QApplication

from stackant.widgets import filmstrip as fs


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _frames(tmp_path, n=3):
    paths = []
    for i in range(n):
        p = tmp_path / f"{i}.png"
        cv2.imwrite(str(p), np.full((20, 20, 3), 100, np.uint8))
        paths.append(str(p))
    return paths


def test_apply_mask_only_updates_changed_items(app, tmp_path, monkeypatch):
    strip = fs.Filmstrip()
    strip.load_frames(_frames(tmp_path))
    calls = []
    for i in range(strip.count()):
        item = strip.item(i)
        orig = item.setIcon
        monkeypatch.setattr(item, "setIcon", lambda ic, i=i, o=orig: (calls.append(i), o(ic)))
    strip.apply_mask([True, False, True])
    assert calls == [1]
    strip.apply_mask([True, False, True])
    assert calls == [1]
    strip.apply_mask([True, True, True])
    assert calls == [1, 1]


def test_worker_cap_for_large_frames(tmp_path, monkeypatch):
    paths = _frames(tmp_path)
    assert fs._thumbnail_workers(paths, 100) == 16
    monkeypatch.setattr(fs.os.path, "getsize", lambda p: 60 * 1024 * 1024)
    assert fs._thumbnail_workers(paths, 100) == 4
    monkeypatch.setattr(fs.os.path, "getsize", lambda p: 300 * 1024 * 1024)
    assert fs._thumbnail_workers(paths, 100) == 2
    assert fs._thumbnail_workers(paths, 1) == 1
