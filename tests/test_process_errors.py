"""QProcess failure modes of the ffmpeg and focus-stack wrappers."""
from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtCore import QEventLoop, QTimer
from PyQt6.QtWidgets import QApplication

from stackant.frame_extractor import FrameExtractor
from stackant.stacker import FocusStacker

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX shell stubs")


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _wait_for(condition, timeout_ms=5000):
    elapsed = 0
    while elapsed < timeout_ms and not condition():
        loop = QEventLoop()
        QTimer.singleShot(20, loop.quit)
        loop.exec()
        elapsed += 20
    return condition()


def _record(obj):
    events = []
    obj.finished_ok.connect(lambda *a: events.append("ok"))
    obj.failed.connect(lambda m: events.append(("failed", m)))
    obj.cancelled.connect(lambda: events.append("cancelled"))
    return events


def _stub_tool(bin_dir, name, body):
    path = bin_dir / name
    path.write_text(f"#!/bin/sh\n{body}\n")
    path.chmod(0o755)


def test_focus_stack_missing_binary_fails_and_frees_the_stacker(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path))
    st = FocusStacker()
    events = _record(st)
    st.stack(["a.tif"], str(tmp_path / "out.tif"))
    assert _wait_for(lambda: events)
    assert events[0][0] == "failed"
    assert not st.is_running, "a launch failure must not leave the stacker stuck"
    assert len(events) == 1


def test_ffmpeg_missing_binary_fails_and_frees_the_extractor(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path))
    ex = FrameExtractor()
    events = _record(ex)
    ex.extract(str(tmp_path / "v.mp4"), str(tmp_path / "frames"))
    assert _wait_for(lambda: events)
    assert events[0][0] == "failed"
    assert not ex.is_running


def test_focus_stack_crash_is_a_failure_not_a_stale_success(qapp, tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _stub_tool(bin_dir, "focus-stack", "kill -9 $$")
    monkeypatch.setenv("PATH", str(bin_dir))
    out = tmp_path / "out.tif"
    out.write_bytes(b"result of an earlier run")
    st = FocusStacker()
    events = _record(st)
    st.stack(["a.tif"], str(out))
    assert _wait_for(lambda: not st.is_running)
    _wait_for(lambda: False, timeout_ms=100)
    assert [e[0] if isinstance(e, tuple) else e for e in events] == ["failed"]
    assert "crashed" in events[0][1]
    assert not out.exists()


def test_ffmpeg_crash_is_a_failure(qapp, tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    frames = tmp_path / "frames"
    frames.mkdir()
    _stub_tool(bin_dir, "ffmpeg", f"touch '{frames}/frame_00001.tif'; kill -9 $$")
    monkeypatch.setenv("PATH", str(bin_dir))
    ex = FrameExtractor()
    events = _record(ex)
    ex.extract(str(tmp_path / "v.mp4"), str(frames))
    assert _wait_for(lambda: not ex.is_running)
    _wait_for(lambda: False, timeout_ms=100)
    assert [e[0] if isinstance(e, tuple) else e for e in events] == ["failed"]
