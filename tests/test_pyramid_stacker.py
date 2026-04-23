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


from stackant.pyramid_stacker import fuse_images


def test_fuse_prefers_sharp_over_blurred():
    """Given two frames, one sharp and one blurred, the fused image
    should be at least as sharp as the sharp source — not averaged."""
    rng = np.random.default_rng(42)
    sharp = rng.random((128, 128, 3), dtype=np.float32)
    blurred = cv2.GaussianBlur(sharp, (15, 15), 5.0)
    fused = fuse_images([sharp, blurred], levels=4, guided_radius=8)
    assert fused.shape == sharp.shape
    # Fused sharpness should be closer to the sharp source's sharpness
    # than to the blurred one's.
    gray = lambda im: cv2.cvtColor((im * 255).astype(np.uint8), cv2.COLOR_RGB2GRAY).astype(np.float32) / 255.0
    sml_sharp = compute_sml(gray(sharp)).mean()
    sml_blurred = compute_sml(gray(blurred)).mean()
    sml_fused = compute_sml(gray(fused)).mean()
    midpoint = (sml_sharp + sml_blurred) / 2
    assert sml_fused > midpoint, \
        f"Fused sharpness {sml_fused:.4f} should be above midpoint {midpoint:.4f}"


from stackant.pyramid_stacker import align_to_reference


def test_align_to_reference_identity_is_near_identity():
    rng = np.random.default_rng(0)
    ref = rng.random((64, 64), dtype=np.float32)
    aligned, warp, ok = align_to_reference(ref, ref.copy())
    assert ok
    assert warp.shape == (2, 3)
    assert np.allclose(aligned, ref, atol=1e-3)


def test_align_to_reference_recovers_small_translation():
    rng = np.random.default_rng(1)
    ref = rng.random((128, 128), dtype=np.float32)
    # Shift by (2, 3) pixels.
    M = np.float32([[1, 0, 2], [0, 1, 3]])
    shifted = cv2.warpAffine(ref, M, (128, 128))
    aligned, warp, ok = align_to_reference(ref, shifted)
    assert ok
    # Central region should match the reference closely after alignment.
    err = np.abs(aligned[10:-10, 10:-10] - ref[10:-10, 10:-10]).mean()
    assert err < 0.1


import tempfile
from pathlib import Path

from PIL import Image

from stackant.pyramid_stacker import run_pyramid_stack


def _write_synth_frame(path: Path, blur_sigma: float, seed: int = 42):
    rng = np.random.default_rng(seed)
    arr = rng.integers(0, 255, size=(128, 128, 3), dtype=np.uint8)
    if blur_sigma > 0:
        ksize = max(3, int(blur_sigma * 4) | 1)
        arr = cv2.GaussianBlur(arr, (ksize, ksize), blur_sigma)
    Image.fromarray(arr).save(path, format="TIFF")


def test_run_pyramid_stack_produces_readable_tiff(tmp_path):
    paths = []
    for i, sigma in enumerate([0.0, 2.0, 4.0]):
        p = tmp_path / f"frame_{i:02d}.tif"
        _write_synth_frame(p, sigma, seed=42 + i)
        paths.append(str(p))
    out = tmp_path / "stacked.tif"
    result = run_pyramid_stack(
        input_paths=paths,
        output_path=str(out),
        pyramid_depth=None,       # auto
        guided_radius=8,
        drop_misaligned=True,
        progress_callback=None,
        cancel_check=lambda: False,
    )
    assert result == str(out)
    assert out.is_file()
    # Output is a TIFF whose size matches the inputs.
    with Image.open(out) as img:
        assert img.size == (128, 128)
