import cv2
import numpy as np

from stackant.pyramid_stacker import (
    build_laplacian_pyramid,
    collapse_laplacian_pyramid,
)


def _synth_image(size=(256, 256), seed=0):
    rng = np.random.default_rng(seed)
    # Textured image so pyramid detail is meaningful.
    return rng.integers(0, 255, size=(*size, 3), dtype=np.uint8).astype(np.float32) / 255.0


def test_build_returns_list_of_arrays_of_decreasing_size():
    img = _synth_image()
    pyramid = build_laplacian_pyramid(img, levels=4)
    # 4 levels = 3 Laplacian bands + 1 Gaussian base
    assert len(pyramid) == 4
    assert pyramid[0].shape[:2] == (256, 256)
    assert pyramid[1].shape[:2] == (128, 128)
    assert pyramid[2].shape[:2] == (64, 64)
    assert pyramid[3].shape[:2] == (32, 32)


def test_collapse_recovers_the_original_within_tolerance():
    img = _synth_image()
    pyramid = build_laplacian_pyramid(img, levels=5)
    recovered = collapse_laplacian_pyramid(pyramid)
    # Round-trip error is small but non-zero because pyrUp/pyrDown
    # are not exact inverses on odd dimensions.
    assert recovered.shape == img.shape
    assert np.abs(recovered - img).mean() < 0.01


from stackant.pyramid_stacker import compute_sml


def test_sml_is_zero_on_constant_image():
    img = np.full((64, 64), 0.5, dtype=np.float32)
    sml = compute_sml(img)
    assert np.allclose(sml, 0.0, atol=1e-6)


def test_sml_is_higher_on_noisy_than_smooth_image():
    rng = np.random.default_rng(0)
    noisy = rng.random((64, 64), dtype=np.float32)
    smooth = cv2.GaussianBlur(noisy, (11, 11), 3)
    sml_noisy = compute_sml(noisy).mean()
    sml_smooth = compute_sml(smooth).mean()
    assert sml_noisy > sml_smooth * 5  # order-of-magnitude separation


def test_sml_preserves_shape():
    img = np.zeros((37, 53), dtype=np.float32)
    assert compute_sml(img).shape == (37, 53)


from stackant.pyramid_stacker import smooth_weights


def test_smooth_weights_preserves_shape_and_range():
    rng = np.random.default_rng(0)
    weights = rng.random((64, 64), dtype=np.float32)
    guide = (rng.random((64, 64, 3), dtype=np.float32))
    smoothed = smooth_weights(weights, guide, radius=8)
    assert smoothed.shape == (64, 64)
    # Guided filter output is ~bounded by the input's range.
    assert smoothed.min() >= -0.01
    assert smoothed.max() <= 1.01


def test_smooth_weights_is_actually_smoothed():
    rng = np.random.default_rng(1)
    impulse = np.zeros((64, 64), dtype=np.float32)
    impulse[32, 32] = 1.0
    guide = np.full((64, 64, 3), 0.5, dtype=np.float32)
    smoothed = smooth_weights(impulse, guide, radius=8)
    # An isolated 1-pixel impulse must spread out.
    assert smoothed[32, 32] < 0.5
    assert smoothed[32:34, 32:34].sum() > 0.01  # mass spread into neighborhood
