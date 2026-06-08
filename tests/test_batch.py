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
