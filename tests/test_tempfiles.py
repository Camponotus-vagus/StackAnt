import os
import time

from stackant import tempfiles


def _age(path, hours):
    t = time.time() - hours * 3600
    os.utime(path, (t, t))


def test_sweep_removes_only_old_untracked_stackant_dirs(tmp_path):
    old = tmp_path / "stackant_old"
    old.mkdir()
    (old / "frame_00001.tif").write_bytes(b"x")
    _age(old, 48)
    fresh = tmp_path / "stackant_fresh"
    fresh.mkdir()
    other = tmp_path / "someone_else"
    other.mkdir()
    _age(other, 48)

    assert tempfiles.sweep_stale(max_age_hours=24, root=str(tmp_path)) == 1
    assert not old.exists()
    assert fresh.exists()
    assert other.exists()


def test_sweep_keeps_dirs_tracked_by_this_process(tmp_path, monkeypatch):
    tracked = tmp_path / "stackant_live"
    tracked.mkdir()
    _age(tracked, 48)
    monkeypatch.setattr(tempfiles, "_TRACKED", [tracked])
    assert tempfiles.sweep_stale(max_age_hours=24, root=str(tmp_path)) == 0
    assert tracked.exists()
