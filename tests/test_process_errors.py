"""QProcess failure modes of the ffmpeg and focus-stack wrappers."""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtCore import QEventLoop, QTimer
from PyQt6.QtWidgets import QApplication

from stackant.frame_extractor import FrameExtractor
from stackant.stacker import FocusStacker, is_opencl_failure

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


def test_focus_stack_bad_extra_cli_fails_cleanly(qapp, tmp_path):
    st = FocusStacker()
    events = _record(st)
    st.stack(["a.tif"], str(tmp_path / "out.tif"), extra_cli='--x="oops')
    assert events and events[0][0] == "failed"
    assert "extra" in events[0][1].lower()
    assert not st.is_running


def test_focus_stack_opencl_signature_survives_log_flood(qapp, tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _stub_tool(
        bin_dir, "focus-stack",
        "echo \"can't create cl_mem handle\"; "
        "i=0; while [ $i -lt 400 ]; do echo '[ 1/9] Grayscale aligned_frame_00023.tif padding padding padding'; "
        "i=$((i+1)); done; exit 1",
    )
    monkeypatch.setenv("PATH", str(bin_dir))
    st = FocusStacker()
    events = _record(st)
    st.stack(["a.tif"], str(tmp_path / "out.tif"))
    assert _wait_for(lambda: events)
    assert events[0][0] == "failed"
    assert is_opencl_failure(events[0][1])


def test_focus_stack_runs_in_frame_directory_with_bare_names(qapp, tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _stub_tool(bin_dir, "focus-stack", 'pwd > "$PWD/cwd.txt"; echo "$@" > "$PWD/args.txt"; exit 1')
    monkeypatch.setenv("PATH", str(bin_dir))
    frames_dir = tmp_path / "frames"
    frames_dir.mkdir()
    st = FocusStacker()
    events = _record(st)
    st.stack([str(frames_dir / "a.tif"), str(frames_dir / "b.tif")], str(tmp_path / "out.tif"))
    assert _wait_for(lambda: events)
    assert (frames_dir / "cwd.txt").read_text().strip() == str(frames_dir)
    args = (frames_dir / "args.txt").read_text()
    assert args.split()[-2:] == ["a.tif", "b.tif"]
    assert f"--output={tmp_path / 'out.tif'}" in args


def test_extractor_removes_stale_frames_and_handles_percent_dir(qapp, tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _stub_tool(bin_dir, "ffmpeg", "/usr/bin/touch frame_00000.tif frame_00001.tif")
    _stub_tool(bin_dir, "ffprobe", "echo '{\"streams\":[{\"nb_frames\":\"2\"}]}'")
    monkeypatch.setenv("PATH", str(bin_dir))
    frames = tmp_path / "100%frames"
    frames.mkdir()
    (frames / "frame_00099.tif").write_bytes(b"stale")
    ex = FrameExtractor()
    got = []
    ex.finished_ok.connect(got.append)
    ex.extract(str(tmp_path / "v.mp4"), str(frames))
    assert _wait_for(lambda: got)
    assert [Path(p).name for p in got[0]] == ["frame_00000.tif", "frame_00001.tif"]
    assert not ex.is_running
    assert ex._probe is None


def test_extractor_cancel_cleans_up_probe(qapp, tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _stub_tool(bin_dir, "ffmpeg", "sleep 30")
    _stub_tool(bin_dir, "ffprobe", "sleep 30")
    monkeypatch.setenv("PATH", str(bin_dir))
    ex = FrameExtractor()
    events = _record(ex)
    ex.extract(str(tmp_path / "v.mp4"), str(tmp_path / "frames"))
    assert ex._probe is not None
    ex.cancel()
    assert ex._probe is None
    assert _wait_for(lambda: events)
    assert events == ["cancelled"]


def test_shutdown_kills_and_waits_for_a_running_stack(qapp, tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _stub_tool(bin_dir, "focus-stack", "sleep 30")
    monkeypatch.setenv("PATH", str(bin_dir))
    st = FocusStacker()
    st.stack([str(tmp_path / "a.tif")], str(tmp_path / "out.tif"))
    assert _wait_for(lambda: st._proc is not None and st._proc.processId() > 0)
    assert st.shutdown(3000)
    assert not st.is_running
