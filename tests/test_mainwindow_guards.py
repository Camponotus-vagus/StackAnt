"""MainWindow must not take a new input or start a second job while one runs."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(qapp):
    from stackant.mainwindow import MainWindow
    w = MainWindow(tool_statuses=None)
    yield w
    w.close()


def test_inputs_locked_while_stacking(win, tmp_path):
    picked = []
    win.controls.video_selected.connect(picked.append)
    win.controls.folder_selected.connect(picked.append)
    win._set_stacking_ui(True)
    c = win.controls
    assert not c.btn_open_video.isEnabled()
    assert not c.btn_open_folder.isEnabled()
    assert not c.btn_extract.isEnabled()
    assert not win.act_open_video.isEnabled()
    assert not win.preview_panel.btn_restack.isEnabled()
    # Drag-and-drop and the File menu go through these directly.
    c._pick_video(str(tmp_path / "new.mp4"))
    c._pick_folder(str(tmp_path))
    assert picked == []

    win._set_stacking_ui(False)
    assert c.btn_open_video.isEnabled()
    c._pick_video(str(tmp_path / "new.mp4"))
    assert picked == [str(tmp_path / "new.mp4")]


def test_stack_request_ignored_while_a_job_runs(win, monkeypatch):
    launched = []
    monkeypatch.setattr(win._pyramid_stacker, "stack", lambda *a, **k: launched.append(a))
    monkeypatch.setattr(win._stacker, "stack", lambda *a, **k: launched.append(a))
    monkeypatch.setattr(win, "_kept_frame_paths", lambda: ["a.tif"])
    monkeypatch.setattr(type(win._pyramid_stacker), "is_running", property(lambda self: True))
    win._on_stack_requested()
    win._on_compare_requested()
    assert launched == []


def test_compare_second_stage_keeps_inputs_locked(win, monkeypatch, tmp_path):
    monkeypatch.setattr(win._stacker, "stack", lambda *a, **k: None)
    monkeypatch.setattr(win, "_kept_frame_paths", lambda: ["a.tif"])
    win._current_temp_dir = tmp_path
    win._compare_mode = True
    win._finish_stacking_ui()
    win._launch_focus_stack_compare()
    assert not win.controls.btn_open_video.isEnabled()
    assert not win.act_open_folder.isEnabled()
    assert not win.progress.isHidden()
