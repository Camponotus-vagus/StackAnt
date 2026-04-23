import numpy as np
import pytest

from stackant.frame_filter import (
    FilterState,
    auto_threshold,
    even_subsample,
    laplacian_variance,
    suggested_decimation_target,
)


def test_laplacian_variance_is_higher_for_sharper_image():
    noisy = np.random.default_rng(0).integers(0, 255, size=(100, 100), dtype=np.uint8)
    blurred = np.full((100, 100), 128, dtype=np.uint8)
    assert laplacian_variance(noisy) > laplacian_variance(blurred)


def test_auto_threshold_is_mean_minus_one_std():
    scores = [1.0, 2.0, 3.0, 4.0, 5.0]
    mean = 3.0
    std = float(np.asarray(scores).std())
    assert auto_threshold(scores) == pytest.approx(mean - std)


def test_even_subsample_keeps_endpoints_and_spacing():
    result = even_subsample(list(range(10)), 3)
    assert len(result) == 3
    assert result[0] == 0
    assert result[-1] == 9


def test_even_subsample_returns_all_when_under_target():
    assert even_subsample([2, 4, 6], 10) == [2, 4, 6]


def test_suggested_decimation_target_below_hi_keeps_all():
    assert suggested_decimation_target(40) == 40
    assert suggested_decimation_target(90) == 90


def test_suggested_decimation_target_above_hi_returns_middle():
    assert suggested_decimation_target(500) == 75


def test_filter_threshold_flags_low_score_frames():
    state = FilterState(scores=[10.0, 1.0, 20.0, 2.0], threshold=5.0)
    assert state.kept_mask() == [True, False, True, False]
    assert state.counts() == (2, 4)


def test_filter_manual_override_forces_include_and_exclude():
    state = FilterState(
        scores=[10.0, 10.0, 10.0],
        threshold=5.0,
        manual_overrides={0: False, 1: True},
    )
    mask = state.kept_mask()
    assert mask[0] is False  # forced exclude beats threshold
    assert mask[1] is True
    assert mask[2] is True


def test_filter_decimation_reduces_to_target():
    state = FilterState(
        scores=[10.0] * 10,
        threshold=5.0,
        decimation_target=3,
    )
    mask = state.kept_mask()
    assert sum(mask) == 3


def test_decimation_preserves_forced_include_even_over_budget():
    state = FilterState(
        scores=[10.0] * 10,
        threshold=5.0,
        decimation_target=2,
        manual_overrides={7: True},
    )
    mask = state.kept_mask()
    assert mask[7] is True
    # 2 total: 1 forced + up to 1 auto
    assert sum(mask) <= 2


def test_decimation_disabled_when_none():
    state = FilterState(scores=[10.0] * 10, threshold=5.0, decimation_target=None)
    assert sum(state.kept_mask()) == 10
