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
