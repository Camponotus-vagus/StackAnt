"""MainWindow state handling: errors, temp dirs, Compare view, persistence."""
from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import cv2
import numpy as np
import pytest
from PyQt6.QtCore import QRect
from PyQt6.QtWidgets import QApplication

from stackant import settings, tempfiles


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(qapp):
    from stackant.mainwindow import MainWindow
    w = MainWindow(tool_statuses=None)
    yield w
    w.close()


def _image(path, value, size=(120, 160)):
    cv2.imwrite(str(path), np.full((*size, 3), value, dtype=np.uint8))
    return str(path)


def test_excepthook_reports_instead_of_aborting(win, monkeypatch):
    from stackant.app import install_excepthook
    monkeypatch.setattr(sys, "excepthook", sys.excepthook)
    install_excepthook(win)
    try:
        raise ValueError("boom in a slot")
    except ValueError:
        sys.excepthook(*sys.exc_info())
    assert "ValueError: boom in a slot" in win.statusBar().currentMessage()
    assert "boom in a slot" in win.log_panel.view.toPlainText()


def test_new_input_deletes_previous_temp_dir(win, tmp_path):
    old = tempfiles.make_temp_dir()
    win._current_temp_dir = old
    win.controls._pick_video(str(tmp_path / "next.mp4"))
    assert not old.exists()
    assert win._current_temp_dir is None


def test_cycling_compare_view_changes_export_target(win, tmp_path):
    pyr = _image(tmp_path / "stacked_pyramid.tif", 50)
    fs = _image(tmp_path / "stacked_focus_stack.tif", 200)
    win.preview_panel.set_compare_outputs(pyramid_path=pyr, focus_stack_path=fs)
    assert win._stacked_output == pyr
    win.preview_panel._cycle_compare_view()
    assert win._stacked_output == fs


def test_single_stack_after_compare_leaves_compare_mode(win, tmp_path):
    pyr = _image(tmp_path / "p.tif", 50)
    fs = _image(tmp_path / "f.tif", 200)
    win.preview_panel.set_compare_outputs(pyramid_path=pyr, focus_stack_path=fs)
    new = _image(tmp_path / "new.tif", 120)
    win.preview_panel.show_stacked(new)
    assert win.preview_panel.btn_compare_view.isHidden()
    assert win.preview_panel._compare_view is None


def test_crop_survives_toggle_between_same_size_images(win, tmp_path):
    panel = win.preview_panel
    panel.show_stacked(_image(tmp_path / "s.tif", 90))
    panel.set_input_reference(_image(tmp_path / "in.tif", 30))
    panel._on_crop_drawn(QRect(10, 10, 40, 40))
    panel._toggle_mode()
    assert panel._current_mode == "input"
    assert panel.btn_reset_crop.isEnabled()
    assert panel._crop_rect == QRect(10, 10, 40, 40)


def test_prefilled_export_folder_is_not_saved_as_default(win, tmp_path):
    settings.save_export_defaults(folder="/my/chosen", quality=95, tiff=True, jpeg=True)
    ec = win.controls.export_controls
    ec.prefill_for_input(str(tmp_path / "clip.mp4"))
    win.close()
    assert settings.load_export_defaults()["folder"] == "/my/chosen"


def test_user_chosen_export_folder_is_saved(win, tmp_path):
    ec = win.controls.export_controls
    ec.prefill_for_input(str(tmp_path / "clip.mp4"))
    ec.txt_folder.setText(str(tmp_path / "exports"))
    win.close()
    assert settings.load_export_defaults()["folder"] == str(tmp_path / "exports")


def test_halo_value_survives_being_switched_off(qapp):
    from stackant.mainwindow import MainWindow
    w = MainWindow(tool_statuses=None)
    sc = w.controls.stack_controls
    sc.chk_halo.setChecked(False)
    sc.spn_halo.setValue(sc.spn_halo.maximum() - 1)
    expected = sc.spn_halo.value()
    w.close()
    w2 = MainWindow(tool_statuses=None)
    try:
        assert w2.controls.stack_controls.spn_halo.value() == expected
        assert not w2.controls.stack_controls.chk_halo.isChecked()
    finally:
        w2.close()


def test_forced_method_not_saved_without_pyramid_backend(qapp, monkeypatch):
    from stackant import mainwindow
    settings.save_method("auto")
    monkeypatch.setattr(mainwindow, "GUIDED_FILTER_AVAILABLE", False)
    w = mainwindow.MainWindow(tool_statuses=None)
    assert w.controls.stack_controls.method() == "focus-stack"
    w.close()
    assert settings.load_method() == "auto"


def test_internal_error_unlocks_idle_ui(win):
    win._lock_inputs(True)
    win.report_internal_error("Traceback...\nRuntimeError: x")
    assert win.controls.btn_open_video.isEnabled()
