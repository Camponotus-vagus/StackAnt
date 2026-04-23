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
