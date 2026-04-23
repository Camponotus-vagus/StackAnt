import pytest

from stackant.stacking import choose_method


def test_small_stack_small_resolution_picks_pyramid():
    assert choose_method(30, 1920, 1080) == "pyramid"


def test_threshold_frame_count_inclusive():
    assert choose_method(50, 1920, 1080) == "pyramid"
    assert choose_method(51, 1920, 1080) == "focus-stack"


def test_threshold_resolution_inclusive():
    assert choose_method(30, 2048, 2048) == "pyramid"
    assert choose_method(30, 2049, 1080) == "focus-stack"
    assert choose_method(30, 1080, 2049) == "focus-stack"


def test_deep_stack_forces_focus_stack():
    assert choose_method(200, 1920, 1080) == "focus-stack"


def test_zero_frames_raises():
    with pytest.raises(ValueError):
        choose_method(0, 1920, 1080)


def test_one_frame_is_pyramid():
    assert choose_method(1, 100, 100) == "pyramid"
