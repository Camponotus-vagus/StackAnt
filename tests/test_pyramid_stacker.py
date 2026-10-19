import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys
from pathlib import Path

import cv2
import numpy as np
import pytest
from PIL import Image
from PyQt6.QtCore import QEventLoop, QTimer
from PyQt6.QtWidgets import QApplication

from stackant.pyramid_stacker import (
    PyramidStacker,
    align_to_reference,
    build_laplacian_pyramid,
    collapse_laplacian_pyramid,
    compute_sml,
    estimate_affine,
    fuse_images,
    run_pyramid_stack,
    smooth_weights,
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
    impulse = np.zeros((64, 64), dtype=np.float32)
    impulse[32, 32] = 1.0
    guide = np.full((64, 64, 3), 0.5, dtype=np.float32)
    smoothed = smooth_weights(impulse, guide, radius=8)
    # An isolated 1-pixel impulse must spread out.
    assert smoothed[32, 32] < 0.5
    assert smoothed[32:34, 32:34].sum() > 0.01  # mass spread into neighborhood


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
    def gray(im):
        return cv2.cvtColor((im * 255).astype(np.uint8), cv2.COLOR_RGB2GRAY).astype(np.float32) / 255.0
    sml_sharp = compute_sml(gray(sharp)).mean()
    sml_blurred = compute_sml(gray(blurred)).mean()
    sml_fused = compute_sml(gray(fused)).mean()
    midpoint = (sml_sharp + sml_blurred) / 2
    assert sml_fused > midpoint, \
        f"Fused sharpness {sml_fused:.4f} should be above midpoint {midpoint:.4f}"


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
    aligned, _warp, ok = align_to_reference(ref, shifted)
    assert ok
    # Central region should match the reference closely after alignment.
    err = np.abs(aligned[10:-10, 10:-10] - ref[10:-10, 10:-10]).mean()
    assert err < 0.1


def _write_synth_frame(path: Path, blur_sigma: float, seed: int = 42, size=(128, 128)):
    rng = np.random.default_rng(seed)
    arr = rng.integers(0, 255, size=(*size, 3), dtype=np.uint8)
    if blur_sigma > 0:
        ksize = max(3, int(blur_sigma * 4) | 1)
        arr = cv2.GaussianBlur(arr, (ksize, ksize), blur_sigma)
    Image.fromarray(arr).save(path, format="TIFF")


def test_run_pyramid_stack_produces_readable_tiff(tmp_path):
    paths = []
    for i, sigma in enumerate([0.0, 2.0, 4.0]):
        p = tmp_path / f"frame_{i:02d}.tif"
        _write_synth_frame(p, sigma, seed=42)
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


def _make_app():
    return QApplication.instance() or QApplication(sys.argv)


def test_pyramid_stacker_runs_to_completion(tmp_path):
    app = _make_app()  # noqa: F841 — keep a reference so the QApplication isn't gc'd mid-test
    paths = []
    for i, sigma in enumerate([0.0, 2.0, 4.0]):
        p = tmp_path / f"frame_{i:02d}.tif"
        _write_synth_frame(p, sigma, seed=42)
        paths.append(str(p))

    stacker = PyramidStacker()
    out = str(tmp_path / "stacked.tif")

    loop = QEventLoop()
    result: dict = {}
    stacker.finished_ok.connect(lambda p: (result.update(path=p), loop.quit()))
    stacker.failed.connect(lambda m: (result.update(err=m), loop.quit()))
    QTimer.singleShot(30000, loop.quit)  # safety timeout
    stacker.stack(
        input_paths=paths,
        output_path=out,
        pyramid_depth=None,
        guided_radius=8,
        drop_misaligned=True,
    )
    loop.exec()
    assert result.get("path") == out
    assert Path(out).is_file()


def test_pyramid_stacker_cancellation_returns_cancelled_signal(tmp_path):
    app = _make_app()  # noqa: F841 — keep a reference so the QApplication isn't gc'd mid-test
    paths = []
    for i in range(8):
        p = tmp_path / f"frame_{i:02d}.tif"
        # Larger frames so the worker is guaranteed to still be mid-pipeline
        # when we fire the cancel signal — tiny inputs can race us to DONE.
        _write_synth_frame(p, float(i), seed=7 + i, size=(512, 512))
        paths.append(str(p))

    stacker = PyramidStacker()
    out = str(tmp_path / "stacked.tif")
    loop = QEventLoop()
    result: dict = {}
    stacker.cancelled.connect(lambda: (result.update(cancelled=True), loop.quit()))
    stacker.finished_ok.connect(lambda _: loop.quit())
    stacker.failed.connect(lambda _: loop.quit())
    QTimer.singleShot(15000, loop.quit)
    stacker.stack(
        input_paths=paths,
        output_path=out,
        pyramid_depth=None,
        guided_radius=8,
        drop_misaligned=True,
    )
    # Cancel as soon as the event loop spins so we're guaranteed to hit a
    # worker checkpoint before the pipeline finishes.
    QTimer.singleShot(0, stacker.cancel)
    loop.exec()
    assert result.get("cancelled") is True


def test_shifted_frames_leave_no_dark_border(tmp_path):
    rng = np.random.default_rng(0)
    # Wide blur gives ECC a basin big enough to converge from ~10 px offsets.
    big = cv2.GaussianBlur(rng.random((260, 300, 3)).astype(np.float32), (0, 0), 6)
    big = (big - big.min()) / (big.max() - big.min()) * 0.5 + 0.4
    paths = []
    for i, (dx, dy) in enumerate([(0, 0), (8, 5), (-6, 7), (4, -6), (-9, -4)]):
        crop = big[30 + dy:230 + dy, 30 + dx:270 + dx]
        p = str(tmp_path / f"f{i}.png")
        cv2.imwrite(p, (crop * 255).astype(np.uint8))
        paths.append(p)
    out = str(tmp_path / "out.png")
    run_pyramid_stack(
        paths, out, pyramid_depth=None, guided_radius=8, drop_misaligned=True,
        progress_callback=None, cancel_check=lambda: False,
    )
    fused = cv2.imread(out).astype(np.float32) / 255.0
    ref = cv2.imread(paths[len(paths) // 2]).astype(np.float32) / 255.0
    for edge in (fused[:, :12], fused[:, -12:], fused[:12], fused[-12:]):
        assert edge.min() > 0.3, "zero-filled warp border leaked into the stack"
    assert abs(fused[:, :12].mean() - ref[:, :12].mean()) < 0.02


def test_fuse_images_ignores_masked_out_pixels():
    good = _synth_image((64, 64), seed=1)
    junk = np.zeros_like(good)
    junk[:, :, :] = 1.0
    mask = np.zeros((64, 64), dtype=np.uint8)
    fused = fuse_images([good, (junk, mask)], levels=3)
    assert np.abs(fused - good).max() < 1e-4


def test_alignment_keeps_only_a_small_window_of_frames_in_memory(tmp_path, monkeypatch):
    import threading
    import time

    from stackant import pyramid_stacker as ps

    n = 30
    paths = []
    for i in range(n):
        p = str(tmp_path / f"f{i:02d}.png")
        cv2.imwrite(p, (_synth_image((48, 48), seed=0) * 255).astype(np.uint8))
        paths.append(p)

    lock = threading.Lock()
    loaded = 0
    consumed = 0
    peak_in_flight = 0
    real_load = ps._load_rgb

    def counting_load(path):
        nonlocal loaded, peak_in_flight
        im = real_load(path)
        with lock:
            loaded += 1
            peak_in_flight = max(peak_in_flight, loaded - consumed)
        return im

    def slow_consumer(pct, stage):
        nonlocal consumed
        if stage == "Aligning + fusing frames":
            with lock:
                consumed += 1
            time.sleep(0.01)

    monkeypatch.setattr(ps, "_load_rgb", counting_load)
    run_pyramid_stack(
        paths, str(tmp_path / "out.png"), pyramid_depth=3, guided_radius=4,
        drop_misaligned=True, progress_callback=slow_consumer,
        cancel_check=lambda: False,
    )
    assert loaded == n
    assert peak_in_flight <= 8, f"{peak_in_flight} frames held at once"


def _noise_gray(seed, size=(128, 128)):
    return np.random.default_rng(seed).random(size, dtype=np.float32)


def test_estimate_affine_rejects_unrelated_content():
    warp, ok = estimate_affine(_noise_gray(1), _noise_gray(2))
    assert not ok
    assert np.allclose(warp, np.eye(2, 3))


def test_estimate_affine_rejects_heavy_distortion():
    ref = cv2.GaussianBlur(_noise_gray(3, (200, 200)), (0, 0), 6)
    M = np.float32([[1.6, 0.0, 0.0], [0.0, 1.6, 0.0]])
    zoomed = cv2.warpAffine(ref, M, (200, 200))
    _warp, ok = estimate_affine(ref, zoomed)
    assert not ok


def test_estimate_affine_accepts_small_translation():
    ref = cv2.GaussianBlur(_noise_gray(4, (200, 200)), (0, 0), 6)
    ref = (ref - ref.min()) / (ref.max() - ref.min())
    shifted = cv2.warpAffine(
        ref, np.float32([[1, 0, 3], [0, 1, 2]]), (200, 200),
        borderMode=cv2.BORDER_REPLICATE,
    )
    warp, ok = estimate_affine(ref, shifted)
    assert ok
    assert abs(warp[0, 2] - 3) < 0.5
    assert abs(warp[1, 2] - 2) < 0.5


def _write_noise_png(path, seed):
    rng = np.random.default_rng(seed)
    cv2.imwrite(str(path), rng.integers(0, 255, (96, 96, 3), dtype=np.uint8))
    return str(path)


def _stack(paths, out, drop):
    return run_pyramid_stack(
        paths, str(out), pyramid_depth=3, guided_radius=4, drop_misaligned=drop,
        progress_callback=None, cancel_check=lambda: False,
    )


def test_all_non_reference_frames_failing_raises(tmp_path):
    paths = [_write_noise_png(tmp_path / f"f{i}.png", i) for i in range(3)]
    with pytest.raises(RuntimeError, match="failed ECC alignment"):
        _stack(paths, tmp_path / "out.png", drop=True)


def test_strict_mode_error_names_failed_frame(tmp_path):
    paths = [_write_noise_png(tmp_path / f"f{i}.png", i) for i in range(3)]
    with pytest.raises(RuntimeError) as exc:
        _stack(paths, tmp_path / "out.png", drop=False)
    assert any(p in str(exc.value) for p in (paths[0], paths[2]))


def test_16bit_input_gives_16bit_output(tmp_path):
    rng = np.random.default_rng(5)
    base = cv2.GaussianBlur(rng.random((96, 96, 3)).astype(np.float32), (0, 0), 2)
    paths = []
    for i in range(3):
        p = str(tmp_path / f"f{i}.tif")
        cv2.imwrite(p, (base * 60000 + 100).astype(np.uint16))
        paths.append(p)
    out = tmp_path / "out.tif"
    _stack(paths, out, drop=True)
    result = cv2.imread(str(out), cv2.IMREAD_ANYDEPTH | cv2.IMREAD_COLOR)
    assert result.dtype == np.uint16
    assert (result % 257 != 0).any(), "values were quantised to 8 bits"


def test_8bit_input_gives_8bit_output(tmp_path):
    paths = [_write_noise_png(tmp_path / "a.png", 1)]
    out = tmp_path / "out.png"
    _stack(paths, out, drop=True)
    assert cv2.imread(str(out), cv2.IMREAD_ANYDEPTH | cv2.IMREAD_COLOR).dtype == np.uint8


def test_progress_spans_alignment_and_fusion(tmp_path):
    paths = [_write_noise_png(tmp_path / "a.png", 1)] * 4
    seen = []
    run_pyramid_stack(
        paths, str(tmp_path / "o.png"), pyramid_depth=3, guided_radius=4,
        drop_misaligned=True, progress_callback=lambda p, s: seen.append((p, s)),
        cancel_check=lambda: False,
    )
    fusing = [p for p, s in seen if s == "Aligning + fusing frames"]
    assert max(fusing) == 90
    assert fusing == sorted(fusing)


def test_cleanup_keeps_thread_that_did_not_stop():
    _make_app()

    class StuckThread:
        deleted = False

        def quit(self):
            pass

        def wait(self, _ms):
            return False

        def deleteLater(self):
            self.deleted = True

    stacker = PyramidStacker()
    stuck = StuckThread()
    stacker._thread = stuck
    stacker._cleanup_thread()
    assert stacker._thread is stuck
    assert not stuck.deleted
    stacker._thread = None


def test_shutdown_cancels_and_waits_for_thread(tmp_path):
    _make_app()
    paths = []
    for i in range(8):
        p = tmp_path / f"frame_{i:02d}.tif"
        _write_synth_frame(p, float(i), seed=7 + i, size=(512, 512))
        paths.append(str(p))
    stacker = PyramidStacker()
    stacker.stack(
        input_paths=paths, output_path=str(tmp_path / "o.tif"),
        pyramid_depth=None, guided_radius=8, drop_misaligned=True,
    )
    assert stacker.shutdown(20000)
    assert not stacker.is_running


def test_estimate_affine_is_accurate_on_sharp_fine_texture():
    # A single ECC pass at ~1024 px used to settle ~10-30 px off on sharp,
    # finely textured frames (wrong translation offset by a fake shear).
    from stackant.pyramid_stacker import estimate_affine
    rng = np.random.default_rng(1)
    h, w = 720, 1280
    img = np.full((h, w), 0.8, np.float32)
    cv2.ellipse(img, (640, 360), (260, 110), 15, 0, 360, 0.25, -1)
    cv2.circle(img, (930, 300), 70, 0.2, -1)
    tex = cv2.GaussianBlur(rng.random((h, w)).astype(np.float32), (0, 0), 1.2)
    img = np.clip(img + (img < 0.5) * (tex - 0.5) * 0.3, 0, 1)
    true_warp = np.float32([[1.02, 0, 6], [0, 1.02, 3]])
    moving = cv2.warpAffine(img, true_warp, (w, h), borderMode=cv2.BORDER_REPLICATE)
    warp, ok = estimate_affine(img, moving)
    assert ok
    pts = np.array([[640, 360, 1], [400, 300, 1], [900, 300, 1], [640, 550, 1]],
                   np.float32).T
    assert np.abs(warp @ pts - true_warp @ pts).max() < 0.5
