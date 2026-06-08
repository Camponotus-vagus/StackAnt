"""Tests for batch processing: pure helpers, controller, dialog."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from stackant import tempfiles


def test_remove_temp_dir_deletes_and_untracks():
    d = tempfiles.make_temp_dir()
    assert d.exists()
    tempfiles.remove_temp_dir(d)
    assert not d.exists()
    assert d not in tempfiles._TRACKED


def test_remove_temp_dir_is_safe_on_unknown_path():
    # Removing a path that was never tracked must not raise.
    d = tempfiles.make_temp_dir()
    tempfiles.remove_temp_dir(d)
    tempfiles.remove_temp_dir(d)  # second call: already gone, still no error


from pathlib import Path

from stackant.batch import (
    VIDEO_EXTENSIONS,
    BatchItem,
    BatchSettings,
    discover_videos,
    is_already_done,
    output_targets,
)


def _make_mixed_folder(root: Path) -> None:
    # Mirrors the user's Leica capture folder: videos + stills + sidecars.
    for name in ("Vid_b.mp4", "Vid_a.mp4", "clip.MOV", "movie.mkv", "old.avi"):
        (root / name).write_bytes(b"x")
    for name in ("still.tiff", "shot.jpg", "Vid_a.mp4.metadata", "notes.txt"):
        (root / name).write_bytes(b"x")
    (root / "subdir").mkdir()
    (root / "subdir" / "nested.mp4").write_bytes(b"x")


def test_discover_videos_filters_sorts_and_is_non_recursive(tmp_path):
    _make_mixed_folder(tmp_path)
    found = discover_videos(str(tmp_path))
    names = [Path(p).name for p in found]
    assert names == ["Vid_a.mp4", "Vid_b.mp4", "clip.MOV", "movie.mkv", "old.avi"]
    assert all(Path(p).is_absolute() for p in found)
    assert not any("nested" in p for p in found)


def test_discover_videos_missing_folder_returns_empty():
    assert discover_videos("/no/such/folder") == []


def test_output_targets_next_to_source_for_selected_formats(tmp_path):
    v = str(tmp_path / "Vid_x.mp4")
    both = output_targets(v, {"tiff": True, "jpeg": True})
    assert [t.name for t in both] == ["Vid_x_stacked.tif", "Vid_x_stacked.jpg"]
    assert all(t.parent == tmp_path for t in both)
    tiff_only = output_targets(v, {"tiff": True, "jpeg": False})
    assert [t.name for t in tiff_only] == ["Vid_x_stacked.tif"]


def test_is_already_done_requires_all_selected_targets(tmp_path):
    v = str(tmp_path / "Vid_x.mp4")
    export = {"tiff": True, "jpeg": True}
    assert not is_already_done(v, export)
    (tmp_path / "Vid_x_stacked.tif").write_bytes(b"x")
    assert not is_already_done(v, export)  # jpeg still missing
    (tmp_path / "Vid_x_stacked.jpg").write_bytes(b"x")
    assert is_already_done(v, export)


def test_is_already_done_false_when_no_formats_selected(tmp_path):
    v = str(tmp_path / "Vid_x.mp4")
    assert not is_already_done(v, {"tiff": False, "jpeg": False})


def test_batchsettings_and_item_defaults():
    s = BatchSettings(
        method="focus-stack", extract_decimation=1, cap=None,
        focus_params={"extra_cli": ""}, pyramid_params={},
        export={"tiff": True, "jpeg": False, "quality": 95},
    )
    assert s.method == "focus-stack"
    item = BatchItem("/v.mp4")
    assert item.status == "pending" and item.output_paths == []


import pytest
from PyQt6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


def test_snapshot_for_batch_composes_panel_values(qapp):
    from stackant.batch import BatchSettings
    from stackant.widgets.controls import ControlsPanel

    panel = ControlsPanel()
    panel.stack_controls.set_method("focus-stack")
    panel.spn_decimation.setValue(3)
    panel.filter_controls.chk_decimate.setChecked(True)
    panel.filter_controls.spn_decimation_target.setValue(60)
    panel.export_controls.chk_tiff.setChecked(True)
    panel.export_controls.chk_jpeg.setChecked(False)
    panel.export_controls.sld_quality.setValue(88)

    s = panel.snapshot_for_batch()
    assert isinstance(s, BatchSettings)
    assert s.method == "focus-stack"
    assert s.extract_decimation == 3
    assert s.cap == 60
    assert s.export == {"tiff": True, "jpeg": False, "quality": 88}
    assert "extra_cli" in s.focus_params
    assert "guided_radius" in s.pyramid_params


def test_snapshot_cap_none_when_decimate_unchecked(qapp):
    from stackant.widgets.controls import ControlsPanel
    panel = ControlsPanel()
    panel.filter_controls.chk_decimate.setChecked(False)
    assert panel.snapshot_for_batch().cap is None


from PyQt6.QtCore import QObject, pyqtSignal


class _FakeExtractor(QObject):
    progress = pyqtSignal(int)
    log = pyqtSignal(str)
    finished_ok = pyqtSignal(list)
    failed = pyqtSignal(str)
    cancelled = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.calls = []
        self._running = False

    @property
    def is_running(self):
        return self._running

    def extract(self, video, out_dir, decimation=1):
        self.calls.append((video, out_dir, decimation))
        self._running = True

    def finish(self, frames):
        self._running = False
        self.finished_ok.emit(frames)

    def fail(self, msg):
        self._running = False
        self.failed.emit(msg)

    def cancel(self):
        self._running = False
        self.cancelled.emit()


class _FakeStacker(QObject):
    progress = pyqtSignal(int)
    log = pyqtSignal(str)
    finished_ok = pyqtSignal(str)
    failed = pyqtSignal(str)
    cancelled = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.calls = []
        self._running = False

    @property
    def is_running(self):
        return self._running

    def stack(self, frames, out, **kw):
        self.calls.append((list(frames), out, kw))
        self._running = True

    def finish(self, out):
        self._running = False
        self.finished_ok.emit(out)

    def fail(self, msg):
        self._running = False
        self.failed.emit(msg)

    def cancel(self):
        self._running = False
        self.cancelled.emit()


def _make_controller():
    from stackant.batch_controller import BatchController
    ext, foc, pyr = _FakeExtractor(), _FakeStacker(), _FakeStacker()
    return BatchController(ext, foc, pyr), ext, foc, pyr


def _settings(export):
    from stackant.batch import BatchSettings
    return BatchSettings(
        method="focus-stack", extract_decimation=1, cap=None,
        focus_params={"consistency": 2, "denoise": True, "sharp_strength": 1,
                      "halo_radius": None, "extra_cli": ""},
        pyramid_params={"pyramid_depth": None, "guided_radius": 8, "drop_misaligned": True},
        export=export,
    )


def test_skip_already_done_items(qapp, tmp_path):
    from stackant.batch import BatchItem
    v1 = str(tmp_path / "a.mp4"); (tmp_path / "a.mp4").write_bytes(b"x")
    v2 = str(tmp_path / "b.mp4"); (tmp_path / "b.mp4").write_bytes(b"x")
    (tmp_path / "a_stacked.tif").write_bytes(b"x")
    export = {"tiff": True, "jpeg": False, "quality": 95}

    ctrl, ext, foc, pyr = _make_controller()
    finished = {}
    ctrl.batch_finished.connect(lambda s: finished.update(s))
    statuses = []
    ctrl.item_finished.connect(lambda i, st, m: statuses.append((i, st)))

    ctrl.run([BatchItem(v1), BatchItem(v2)], _settings(export))
    assert (0, "skipped") in statuses
    assert ext.calls == [(v2, ext.calls[0][1], 1)]


def test_run_starts_extraction_for_first_item(qapp, tmp_path):
    from stackant.batch import BatchItem
    v = str(tmp_path / "a.mp4"); (tmp_path / "a.mp4").write_bytes(b"x")
    export = {"tiff": True, "jpeg": False, "quality": 95}
    ctrl, ext, foc, pyr = _make_controller()
    started = []
    ctrl.item_started.connect(started.append)
    ctrl.run([BatchItem(v)], _settings(export))
    assert started == [0]
    assert ext.calls and ext.calls[0][0] == v and ext.calls[0][2] == 1


def test_happy_path_single_video(qapp, tmp_path, monkeypatch):
    from stackant import batch_controller as bc
    from stackant.batch import BatchItem
    from stackant.frame_filter import FrameScore

    monkeypatch.setattr(
        bc, "score_frames",
        lambda frames, progress_callback=None: [FrameScore(i, p, 100.0)
                                                for i, p in enumerate(frames)],
    )
    tiff_calls, jpeg_calls = [], []
    monkeypatch.setattr(bc, "export_tiff", lambda s, d: tiff_calls.append((s, d)))
    monkeypatch.setattr(bc, "export_jpeg",
                        lambda s, d, quality=95: jpeg_calls.append((s, d, quality)))
    removed = []
    monkeypatch.setattr(bc.tempfiles, "remove_temp_dir", lambda p: removed.append(p))

    v = str(tmp_path / "a.mp4"); (tmp_path / "a.mp4").write_bytes(b"x")
    export = {"tiff": True, "jpeg": True, "quality": 90}
    ctrl, ext, foc, pyr = _make_controller()
    summary = {}
    ctrl.batch_finished.connect(lambda s: summary.update(s))
    item = BatchItem(v)
    ctrl.run([item], _settings(export))

    ext.finish(["f0.tif", "f1.tif", "f2.tif"])
    assert foc.calls, "focus stacker should have been launched"
    kept, out, kw = foc.calls[0]
    assert kept == ["f0.tif", "f1.tif", "f2.tif"]

    foc.finish(out)
    assert item.status == "done"
    assert [d for _, d in tiff_calls] == [str(tmp_path / "a_stacked.tif")]
    assert [d for _, d, _ in jpeg_calls] == [str(tmp_path / "a_stacked.jpg")]
    assert removed, "per-video temp dir must be cleaned up"
    assert summary["done"] == 1 and summary["total"] == 1
