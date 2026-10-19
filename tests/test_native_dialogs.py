"""Message boxes must avoid Qt's native NSAlert, which crashes on macOS 27."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QMessageBox

from stackant import dependency_checker


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_missing_deps_dialog_is_not_native(qapp):
    from stackant.app import missing_deps_dialog
    dlg = missing_deps_dialog("ffmpeg missing")
    assert dlg.testOption(QMessageBox.Option.DontUseNativeDialog)
    assert dlg.informativeText() == "ffmpeg missing"


def _click_when_shown(button):
    def click():
        box = QApplication.activeModalWidget()
        if isinstance(box, QMessageBox):
            assert box.testOption(QMessageBox.Option.DontUseNativeDialog)
            box.button(button).click()
        else:
            QTimer.singleShot(10, click)
    QTimer.singleShot(10, click)


@pytest.mark.parametrize("button,expected", [
    (QMessageBox.StandardButton.Yes, True),
    (QMessageBox.StandardButton.No, False),
])
def test_overwrite_confirmation_is_not_native(qapp, button, expected):
    from stackant.mainwindow import MainWindow
    w = MainWindow(tool_statuses=None)
    try:
        _click_when_shown(button)
        assert w._confirm_overwrite("a.tif") is expected
    finally:
        w.close()


def test_augment_path_appends_existing_tool_dirs(tmp_path, monkeypatch):
    local_bin = tmp_path / "home" / ".local" / "bin"
    local_bin.mkdir(parents=True)
    brew = tmp_path / "brew"
    brew.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setattr(dependency_checker, "_EXTRA_TOOL_DIRS",
                        ("~/.local/bin", str(brew), str(tmp_path / "missing")))
    env = {"PATH": f"/usr/bin{os.pathsep}{brew}"}
    added = dependency_checker.augment_path(env)
    if os.name == "nt":
        assert added == []
        return
    assert added == [str(local_bin)]
    assert env["PATH"].split(os.pathsep) == ["/usr/bin", str(brew), str(local_bin)]
    assert dependency_checker.augment_path(env) == []


def test_tool_in_local_bin_is_found_after_augment(tmp_path, monkeypatch):
    if os.name == "nt":
        pytest.skip("POSIX tool dirs")
    local_bin = tmp_path / ".local" / "bin"
    local_bin.mkdir(parents=True)
    tool = local_bin / "focus-stack"
    tool.write_text("#!/bin/sh\necho focus-stack 1.5\n")
    tool.chmod(0o755)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("PATH", "/usr/bin")
    dependency_checker.augment_path()
    status = {s.name: s for s in dependency_checker.check()}["focus-stack"]
    assert status.path == str(tool)
    assert status.version == "focus-stack 1.5"
