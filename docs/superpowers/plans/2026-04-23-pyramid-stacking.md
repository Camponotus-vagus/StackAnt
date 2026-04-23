# StackAnt v0.2 — Laplacian-pyramid stacking implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a pure-Python Laplacian-pyramid stacking method alongside
`focus-stack` in StackAnt, with a three-way method radio
(Pyramid / focus-stack / Auto), a Compare button that runs both
methods, and all supporting UI wiring.

**Architecture:** New `PyramidStacker` QObject running NumPy/OpenCV
work in a worker thread, invoked in parallel with the existing
`FocusStacker`. `stackant/stacking.py` holds the Auto heuristic as a
pure function. UI additions live in the existing `StackControls`
group box and the `PreviewPanel`.

**Tech Stack:** Python 3.10+, PyQt6, NumPy, OpenCV (swap to
`opencv-contrib-python-headless` for `cv2.ximgproc.guidedFilter`),
Pillow, existing project conventions.

**Reference spec:**
`docs/superpowers/specs/2026-04-23-pyramid-stacking-design.md`

---

## File map

**New:**
- `stackant/pyramid_stacker.py` — pyramid algorithm helpers + `PyramidStacker(QObject)` worker class
- `stackant/stacking.py` — `choose_method()` pure function (Auto heuristic)
- `tests/test_pyramid_stacker.py` — unit tests for pyramid math
- `tests/test_stacking_auto.py` — unit tests for `choose_method`

**Modified:**
- `requirements.txt` — swap to `opencv-contrib-python-headless`
- `stackant/settings.py` — four new keys
- `stackant/widgets/log_panel.py` — `append_tagged()` helper
- `stackant/widgets/stack_controls.py` — method radio, Compare button, Pyramid advanced sub-group
- `stackant/widgets/preview_panel.py` — Compare view toggle
- `stackant/mainwindow.py` — wire `PyramidStacker`, method dispatch, Compare flow
- `tests/test_headless_smoke.py` — extend with method picker + Compare tests
- `CHANGELOG.md` — v0.2.0 Unreleased entry
- `CLAUDE.md` — current-state block update

---

## Task 1 — Swap to `opencv-contrib-python-headless`

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Edit `requirements.txt`**

Replace the line `opencv-python-headless==4.13.0.92` with:
```
opencv-contrib-python-headless==4.13.0.92
```

The comment above it already explains the Qt-plugin reason; extend it to also mention the contrib reason. Final block:
```
# opencv-contrib-python-headless (not opencv-python): the non-headless
# wheel bundles outdated Qt5 plugins that shadow PyQt6's and break
# GUI launch; the contrib wheel adds cv2.ximgproc (guidedFilter)
# required by the Pyramid stacker.
opencv-contrib-python-headless==4.13.0.92
```

- [ ] **Step 2: Uninstall and reinstall inside the venv**

```bash
.venv/bin/pip uninstall -y opencv-python-headless opencv-python opencv-contrib-python
.venv/bin/pip install -r requirements.txt -q
.venv/bin/python -c "import cv2; from cv2 import ximgproc; print('ok', cv2.__version__)"
```

Expected: `ok 4.13.0.92` (or similar).

- [ ] **Step 3: Run existing suite to confirm nothing regressed**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/ -q
```

Expected: 76 passed.

- [ ] **Step 4: Commit**

```bash
git add requirements.txt
git -c user.email=fsmensa@gmail.com -c user.name=Francesco commit -m "deps: switch to opencv-contrib-python-headless for ximgproc.guidedFilter"
```

---

## Task 2 — `choose_method()` in `stackant/stacking.py` (TDD)

**Files:**
- Create: `stackant/stacking.py`
- Create: `tests/test_stacking_auto.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_stacking_auto.py`:
```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_stacking_auto.py -q
```

Expected: `ImportError: cannot import name 'choose_method' from 'stackant.stacking'` (module doesn't exist yet).

- [ ] **Step 3: Create `stackant/stacking.py`**

```python
"""Method-selection heuristic for the Auto stacker mode.

No published rule exists for selecting a focus-stacking method per
image (Helicon, Zerene, and the photomacrography community all
recommend trying both). This module exposes a documented heuristic
based on frame count and resolution — it is a reasonable default,
not a claim of correctness. For quality-critical work users should
reach for the Compare button.
"""
from __future__ import annotations

_MAX_FRAMES_FOR_PYRAMID = 50
_MAX_LONGEST_EDGE_FOR_PYRAMID = 2048


def choose_method(n_frames: int, width: int, height: int) -> str:
    """Return "pyramid" or "focus-stack" for the current input.

    Rule: pyramid when the stack is small (<=50 kept frames) AND the
    longest edge is <=2048 px. Otherwise focus-stack, whose GPU path
    scales better to deeper / higher-resolution stacks.
    """
    if n_frames <= 0:
        raise ValueError("n_frames must be positive")
    small_stack = n_frames <= _MAX_FRAMES_FOR_PYRAMID
    small_edge = max(width, height) <= _MAX_LONGEST_EDGE_FOR_PYRAMID
    return "pyramid" if (small_stack and small_edge) else "focus-stack"
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_stacking_auto.py -q
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add stackant/stacking.py tests/test_stacking_auto.py
git -c user.email=fsmensa@gmail.com -c user.name=Francesco commit -m "feat(stacking): add choose_method() auto heuristic"
```

---

## Task 3 — Laplacian pyramid build + collapse (TDD)

**Files:**
- Create: `stackant/pyramid_stacker.py`
- Create: `tests/test_pyramid_stacker.py`

- [ ] **Step 1: Write failing test for pyramid build/collapse round-trip**

Create `tests/test_pyramid_stacker.py`:
```python
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
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_pyramid_stacker.py -q
```

Expected: `ImportError` — the module doesn't exist.

- [ ] **Step 3: Create `stackant/pyramid_stacker.py` with the pyramid helpers**

```python
"""Laplacian-pyramid focus stacker.

Pure-Python implementation of the algorithm family used by Helicon
Focus Method C and Zerene Stacker PMax: Laplacian pyramid fusion with
guided-filter-smoothed sharpness weight maps. Addresses halos at hard
contrast edges that the wavelet-based focus-stack CLI (our default
backend) is prone to on macro entomology subjects.

Design tenets:
- All helpers operate on float32 arrays in [0, 1] for numerical
  stability during pyramid collapse.
- Input/output to/from disk is uint8 BGR (OpenCV convention) and the
  caller takes care of the conversion.
- Progress and cancellation are driven from the caller (see
  run_pyramid_stack + PyramidStacker below).
"""
from __future__ import annotations

import cv2
import numpy as np


def build_laplacian_pyramid(
    image: np.ndarray, levels: int
) -> list[np.ndarray]:
    """Return [L_0, L_1, ..., L_{levels-2}, G_{levels-1}].

    L_k = G_k - pyrUp(G_{k+1}) cropped to G_k's shape. The last
    entry is the coarsest Gaussian, which the collapse step seeds
    with.
    """
    gauss = [image.astype(np.float32)]
    for _ in range(levels - 1):
        gauss.append(cv2.pyrDown(gauss[-1]))
    pyramid: list[np.ndarray] = []
    for k in range(levels - 1):
        up = cv2.pyrUp(gauss[k + 1], dstsize=(gauss[k].shape[1], gauss[k].shape[0]))
        pyramid.append(gauss[k] - up)
    pyramid.append(gauss[-1])
    return pyramid


def collapse_laplacian_pyramid(pyramid: list[np.ndarray]) -> np.ndarray:
    """Collapse a Laplacian pyramid back to full resolution."""
    current = pyramid[-1]
    for k in range(len(pyramid) - 2, -1, -1):
        target = pyramid[k]
        up = cv2.pyrUp(current, dstsize=(target.shape[1], target.shape[0]))
        current = up + target
    return current
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_pyramid_stacker.py -q
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add stackant/pyramid_stacker.py tests/test_pyramid_stacker.py
git -c user.email=fsmensa@gmail.com -c user.name=Francesco commit -m "feat(pyramid): add Laplacian pyramid build + collapse"
```

---

## Task 4 — Sum-Modified-Laplacian sharpness metric (TDD)

**Files:**
- Modify: `stackant/pyramid_stacker.py` (add `compute_sml`)
- Modify: `tests/test_pyramid_stacker.py` (add tests)

- [ ] **Step 1: Write failing tests**

Append to `tests/test_pyramid_stacker.py`:
```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_pyramid_stacker.py -q
```

Expected: import errors on `compute_sml`.

- [ ] **Step 3: Implement `compute_sml`**

Append to `stackant/pyramid_stacker.py`:
```python
# SML kernels: second derivatives along x and y.
_SML_KERNEL_X = np.array([[-1.0, 2.0, -1.0]], dtype=np.float32)
_SML_KERNEL_Y = _SML_KERNEL_X.T
_SML_WINDOW = 7  # Summation window (odd).


def compute_sml(gray: np.ndarray) -> np.ndarray:
    """Sum-Modified-Laplacian sharpness map on a grayscale float image.

    Returns an array of the same shape as `gray` where each pixel is
    the sum (over a 7x7 window) of the absolute second derivative in
    x plus the absolute second derivative in y.
    """
    if gray.ndim != 2:
        raise ValueError("compute_sml expects a 2-D grayscale array")
    ddx = np.abs(cv2.filter2D(gray, cv2.CV_32F, _SML_KERNEL_X))
    ddy = np.abs(cv2.filter2D(gray, cv2.CV_32F, _SML_KERNEL_Y))
    ml = ddx + ddy
    # Box-filter summation across the window.
    return cv2.boxFilter(ml, cv2.CV_32F, (_SML_WINDOW, _SML_WINDOW), normalize=False)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_pyramid_stacker.py -q
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add stackant/pyramid_stacker.py tests/test_pyramid_stacker.py
git -c user.email=fsmensa@gmail.com -c user.name=Francesco commit -m "feat(pyramid): add Sum-Modified-Laplacian sharpness metric"
```

---

## Task 5 — Guided-filter-smoothed weight map (TDD)

**Files:**
- Modify: `stackant/pyramid_stacker.py` (add `smooth_weights`)
- Modify: `tests/test_pyramid_stacker.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_pyramid_stacker.py`:
```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_pyramid_stacker.py -q
```

Expected: import errors on `smooth_weights`.

- [ ] **Step 3: Implement `smooth_weights`**

Append to `stackant/pyramid_stacker.py`:
```python
try:
    from cv2 import ximgproc as _ximgproc
    GUIDED_FILTER_AVAILABLE = True
except ImportError:  # opencv-python (non-contrib) was installed
    _ximgproc = None
    GUIDED_FILTER_AVAILABLE = False


def smooth_weights(
    weights: np.ndarray,
    guide: np.ndarray,
    radius: int = 8,
    eps: float = 1e-4,
) -> np.ndarray:
    """Edge-preserving smoothing of a sharpness/weight map.

    This is the step that distinguishes Helicon C / Zerene PMax
    quality from a naive max-pixel pyramid — without guided-filter
    smoothing the raw sharpness map creates speckle and blocking.

    Raises ImportError if opencv-contrib is not installed — caller
    should gate on `GUIDED_FILTER_AVAILABLE` before calling.
    """
    if _ximgproc is None:
        raise ImportError(
            "cv2.ximgproc not available — install opencv-contrib-python-headless"
        )
    return _ximgproc.guidedFilter(
        guide=guide.astype(np.float32),
        src=weights.astype(np.float32),
        radius=int(radius),
        eps=float(eps),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_pyramid_stacker.py -q
```

Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add stackant/pyramid_stacker.py tests/test_pyramid_stacker.py
git -c user.email=fsmensa@gmail.com -c user.name=Francesco commit -m "feat(pyramid): add guided-filter weight-map smoothing"
```

---

## Task 6 — 2-frame fusion rule (TDD)

**Files:**
- Modify: `stackant/pyramid_stacker.py`
- Modify: `tests/test_pyramid_stacker.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_pyramid_stacker.py`:
```python
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
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_pyramid_stacker.py -q
```

Expected: import error on `fuse_images`.

- [ ] **Step 3: Implement `fuse_images`**

Append to `stackant/pyramid_stacker.py`:
```python
def fuse_images(
    images: list[np.ndarray],
    levels: int,
    guided_radius: int = 8,
) -> np.ndarray:
    """Laplacian-pyramid fusion of N float32 RGB images in [0, 1].

    Pipeline:
        - build L-level Laplacian pyramid per image
        - at each level, compute per-image SML on its grayscale
          component, smooth with guided filter, normalise across N
          so weights sum to 1 at every pixel
        - weighted-sum Laplacian coefficients per level
        - collapse to full resolution

    Input images must be pre-aligned and have identical shape.
    """
    if not images:
        raise ValueError("fuse_images needs at least one image")
    shape = images[0].shape
    for im in images[1:]:
        if im.shape != shape:
            raise ValueError("fuse_images: all images must share shape")

    pyramids = [build_laplacian_pyramid(im, levels) for im in images]
    fused_levels: list[np.ndarray] = []

    for lvl in range(levels):
        level_bands = [p[lvl] for p in pyramids]
        # Per-image sharpness on grayscale version of the band's
        # corresponding Gaussian (we use the band itself as a proxy
        # — Laplacian bands are already high-frequency for lvl<last;
        # for the base Gaussian we use the band directly).
        grays = [
            cv2.cvtColor(np.clip(b, -1, 1).astype(np.float32), cv2.COLOR_RGB2GRAY)
            if b.ndim == 3 else b
            for b in level_bands
        ]
        weights = [compute_sml(g) for g in grays]
        # Smooth each weight map with the source band as guide.
        smoothed = [
            smooth_weights(w, b if b.ndim == 3 else np.stack([b]*3, axis=-1),
                           radius=guided_radius)
            for w, b in zip(weights, level_bands)
        ]
        # Normalise across images so weights sum to 1 per pixel.
        stacked = np.stack(smoothed, axis=0)
        stacked = np.maximum(stacked, 0.0) + 1e-8
        norms = stacked / stacked.sum(axis=0, keepdims=True)
        # Weighted sum of Laplacian coefficients. For 3-channel bands
        # broadcast the per-pixel weight across channels.
        fused = np.zeros_like(level_bands[0])
        for i, band in enumerate(level_bands):
            w = norms[i]
            if band.ndim == 3:
                w = w[..., np.newaxis]
            fused += w * band
        fused_levels.append(fused)

    return collapse_laplacian_pyramid(fused_levels)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_pyramid_stacker.py -q
```

Expected: 8 passed. (Test is tolerant — midpoint threshold gives headroom for numerics.)

- [ ] **Step 5: Commit**

```bash
git add stackant/pyramid_stacker.py tests/test_pyramid_stacker.py
git -c user.email=fsmensa@gmail.com -c user.name=Francesco commit -m "feat(pyramid): fusion rule with per-level weighted blending"
```

---

## Task 7 — ECC alignment with drop-misaligned handling (TDD)

**Files:**
- Modify: `stackant/pyramid_stacker.py`
- Modify: `tests/test_pyramid_stacker.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_pyramid_stacker.py`:
```python
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
    assert err < 0.05
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_pyramid_stacker.py -q
```

Expected: import error on `align_to_reference`.

- [ ] **Step 3: Implement `align_to_reference`**

Append to `stackant/pyramid_stacker.py`:
```python
_ECC_CRITERIA = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 100, 1e-4)


def align_to_reference(
    reference: np.ndarray,
    moving: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, bool]:
    """Align `moving` to `reference` using ECC with affine motion.

    Both inputs must be 2-D float32 (grayscale). Returns the
    warped moving image, the 2x3 affine warp matrix, and a success
    flag. On ECC failure the original moving image is returned with
    the identity warp and ok=False.
    """
    if reference.shape != moving.shape:
        raise ValueError("reference and moving must share shape")
    warp = np.eye(2, 3, dtype=np.float32)
    try:
        _, warp = cv2.findTransformECC(
            templateImage=reference,
            inputImage=moving,
            warpMatrix=warp,
            motionType=cv2.MOTION_AFFINE,
            criteria=_ECC_CRITERIA,
            inputMask=None,
            gaussFiltSize=5,
        )
    except cv2.error:
        return moving, np.eye(2, 3, dtype=np.float32), False
    h, w = reference.shape
    aligned = cv2.warpAffine(
        moving, warp, (w, h), flags=cv2.INTER_LINEAR + cv2.WARP_INVERSE_MAP
    )
    return aligned, warp, True
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_pyramid_stacker.py -q
```

Expected: 10 passed.

- [ ] **Step 5: Commit**

```bash
git add stackant/pyramid_stacker.py tests/test_pyramid_stacker.py
git -c user.email=fsmensa@gmail.com -c user.name=Francesco commit -m "feat(pyramid): add ECC-based alignment helper"
```

---

## Task 8 — Top-level `run_pyramid_stack` orchestration (TDD)

**Files:**
- Modify: `stackant/pyramid_stacker.py`
- Modify: `tests/test_pyramid_stacker.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_pyramid_stacker.py`:
```python
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
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_pyramid_stacker.py -q
```

Expected: import error on `run_pyramid_stack`.

- [ ] **Step 3: Implement `run_pyramid_stack`**

Append to `stackant/pyramid_stacker.py`:
```python
import math
from pathlib import Path
from typing import Callable, Sequence


def _auto_pyramid_depth(height: int, width: int) -> int:
    return max(3, int(math.floor(math.log2(min(height, width)))) - 3)


def _load_rgb_float(path: str) -> np.ndarray:
    """Read an image from disk as float32 RGB in [0, 1]."""
    bgr = cv2.imread(path, cv2.IMREAD_COLOR)
    if bgr is None:
        raise OSError(f"could not read image: {path}")
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    return rgb.astype(np.float32) / 255.0


def _save_rgb_float(path: str, image: np.ndarray) -> None:
    arr = np.clip(image, 0.0, 1.0)
    rgb = (arr * 255.0 + 0.5).astype(np.uint8)
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(path, bgr):
        raise OSError(f"could not write image: {path}")


def run_pyramid_stack(
    input_paths: Sequence[str],
    output_path: str,
    *,
    pyramid_depth: int | None,
    guided_radius: int,
    drop_misaligned: bool,
    progress_callback: Callable[[int, str], None] | None,
    cancel_check: Callable[[], bool],
) -> str:
    """Run the full pyramid pipeline and write the result to `output_path`.

    Arguments:
        input_paths: ordered TIFF paths from the filmstrip.
        output_path: destination TIFF.
        pyramid_depth: override pyramid levels (None = auto).
        guided_radius: guided-filter radius for weight smoothing.
        drop_misaligned: if True, frames whose ECC alignment fails
            are dropped with a log line rather than aborting.
        progress_callback: called as (pct: int, stage: str).
        cancel_check: returns True if the run was cancelled; the
            function raises `Cancelled` at the next checkpoint.

    Returns the output path on success.
    """
    if not input_paths:
        raise ValueError("run_pyramid_stack: at least one input required")

    def _progress(pct: int, stage: str) -> None:
        if progress_callback is not None:
            progress_callback(pct, stage)

    def _check_cancel() -> None:
        if cancel_check():
            raise Cancelled()

    _progress(0, "Loading frames")
    images = [_load_rgb_float(p) for p in input_paths]
    _check_cancel()

    shape = images[0].shape
    for p, im in zip(input_paths, images):
        if im.shape != shape:
            raise ValueError(
                f"pyramid stacker requires same-shape inputs; {p} differs"
            )

    # Alignment: use the middle frame as the reference.
    ref_idx = len(images) // 2
    ref_gray = cv2.cvtColor(images[ref_idx], cv2.COLOR_RGB2GRAY)
    aligned: list[np.ndarray] = []
    dropped: list[int] = []
    n = len(images)
    h, w = ref_gray.shape
    for i, im in enumerate(images):
        _check_cancel()
        if i == ref_idx:
            aligned.append(im)
        else:
            gray = cv2.cvtColor(im, cv2.COLOR_RGB2GRAY)
            _, warp, ok = align_to_reference(ref_gray, gray)
            if ok:
                warped_rgb = cv2.warpAffine(
                    im, warp, (w, h),
                    flags=cv2.INTER_LINEAR + cv2.WARP_INVERSE_MAP,
                )
                aligned.append(warped_rgb)
            elif drop_misaligned:
                dropped.append(i)
            else:
                raise RuntimeError(
                    f"ECC alignment failed for frame {i} and drop_misaligned is False"
                )
        _progress(int(5 + 20 * (i + 1) / n), "Aligning frames")

    if not aligned:
        raise RuntimeError(
            f"All {n} frames failed ECC alignment. Subject may be moving."
        )
    if dropped:
        _progress(25, f"Dropped {len(dropped)} misaligned frame(s)")

    # Pyramid depth.
    depth = pyramid_depth if pyramid_depth and pyramid_depth > 0 else _auto_pyramid_depth(
        shape[0], shape[1]
    )

    _progress(30, "Building pyramids")
    _check_cancel()
    fused = fuse_images(aligned, levels=depth, guided_radius=guided_radius)
    _check_cancel()

    _progress(95, "Writing output")
    _save_rgb_float(output_path, fused)
    _progress(100, "Done")
    return output_path


class Cancelled(Exception):
    """Raised inside run_pyramid_stack when the caller requests cancellation."""
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_pyramid_stacker.py -q
```

Expected: 11 passed.

- [ ] **Step 5: Commit**

```bash
git add stackant/pyramid_stacker.py tests/test_pyramid_stacker.py
git -c user.email=fsmensa@gmail.com -c user.name=Francesco commit -m "feat(pyramid): add run_pyramid_stack orchestrator"
```

---

## Task 9 — `PyramidStacker(QObject)` worker wrapper

**Files:**
- Modify: `stackant/pyramid_stacker.py`
- Modify: `tests/test_pyramid_stacker.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_pyramid_stacker.py`:
```python
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys
from PyQt6.QtCore import QEventLoop, QTimer
from PyQt6.QtWidgets import QApplication

from stackant.pyramid_stacker import PyramidStacker


def _make_app():
    return QApplication.instance() or QApplication(sys.argv)


def test_pyramid_stacker_runs_to_completion(tmp_path):
    _make_app()
    paths = []
    for i, sigma in enumerate([0.0, 2.0, 4.0]):
        p = tmp_path / f"frame_{i:02d}.tif"
        _write_synth_frame(p, sigma, seed=42 + i)
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
    _make_app()
    paths = []
    for i in range(6):
        p = tmp_path / f"frame_{i:02d}.tif"
        _write_synth_frame(p, float(i), seed=7 + i)
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
    # Cancel shortly after it starts.
    QTimer.singleShot(100, stacker.cancel)
    loop.exec()
    assert result.get("cancelled") is True
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_pyramid_stacker.py -q
```

Expected: import error on `PyramidStacker`.

- [ ] **Step 3: Implement `PyramidStacker`**

Append to `stackant/pyramid_stacker.py`:
```python
import threading

from PyQt6.QtCore import QObject, QThread, pyqtSignal


class _PyramidWorker(QObject):
    progress = pyqtSignal(int)
    stage = pyqtSignal(str)
    finished_ok = pyqtSignal(str)
    failed = pyqtSignal(str)
    cancelled = pyqtSignal()

    def __init__(self, params: dict, cancel_event: threading.Event):
        super().__init__()
        self._params = params
        self._cancel = cancel_event

    def run(self) -> None:
        def on_progress(pct: int, stage: str) -> None:
            self.progress.emit(int(pct))
            self.stage.emit(stage)

        try:
            out = run_pyramid_stack(
                input_paths=self._params["input_paths"],
                output_path=self._params["output_path"],
                pyramid_depth=self._params["pyramid_depth"],
                guided_radius=self._params["guided_radius"],
                drop_misaligned=self._params["drop_misaligned"],
                progress_callback=on_progress,
                cancel_check=self._cancel.is_set,
            )
        except Cancelled:
            self.cancelled.emit()
            return
        except Exception as exc:  # noqa: BLE001 — we must surface any failure
            self.failed.emit(f"{type(exc).__name__}: {exc}")
            return
        self.finished_ok.emit(out)


class PyramidStacker(QObject):
    """Qt-side wrapper around run_pyramid_stack.

    Shape mirrors FocusStacker: progress / log / finished_ok / failed /
    cancelled signals, with a log channel synthesised from the
    worker's per-stage progress messages so the MainWindow's existing
    log-panel wiring works unchanged.
    """
    progress = pyqtSignal(int)
    log = pyqtSignal(str)
    command_ready = pyqtSignal(str)
    finished_ok = pyqtSignal(str)
    failed = pyqtSignal(str)
    cancelled = pyqtSignal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._thread: QThread | None = None
        self._worker: _PyramidWorker | None = None
        self._cancel = threading.Event()

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.isRunning()

    def stack(
        self,
        input_paths,
        output_path: str,
        *,
        pyramid_depth: int | None,
        guided_radius: int,
        drop_misaligned: bool,
    ) -> None:
        if self.is_running:
            self.failed.emit("Pyramid stacker already running.")
            return
        if not GUIDED_FILTER_AVAILABLE:
            self.failed.emit(
                "opencv-contrib-python-headless is required for the pyramid stacker "
                "(cv2.ximgproc.guidedFilter is missing)."
            )
            return

        self.command_ready.emit(
            f"python -m stackant.pyramid_stacker --depth={pyramid_depth or 'auto'} "
            f"--radius={guided_radius} --drop_misaligned={drop_misaligned} "
            f"-> {output_path}"
        )

        self._cancel.clear()
        params = {
            "input_paths": list(input_paths),
            "output_path": output_path,
            "pyramid_depth": pyramid_depth,
            "guided_radius": guided_radius,
            "drop_misaligned": drop_misaligned,
        }
        self._thread = QThread(self)
        self._worker = _PyramidWorker(params, self._cancel)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self.progress.emit)
        self._worker.stage.connect(lambda s: self.log.emit(f"{s}"))
        self._worker.finished_ok.connect(self._on_worker_done)
        self._worker.failed.connect(self._on_worker_failed)
        self._worker.cancelled.connect(self._on_worker_cancelled)
        self._thread.start()

    def cancel(self) -> None:
        if self.is_running:
            self._cancel.set()

    def _cleanup_thread(self) -> None:
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait(3000)
            self._thread.deleteLater()
            self._thread = None
            self._worker = None

    def _on_worker_done(self, path: str) -> None:
        self._cleanup_thread()
        self.finished_ok.emit(path)

    def _on_worker_failed(self, msg: str) -> None:
        self._cleanup_thread()
        self.failed.emit(msg)

    def _on_worker_cancelled(self) -> None:
        self._cleanup_thread()
        self.cancelled.emit()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_pyramid_stacker.py -q
```

Expected: 13 passed.

- [ ] **Step 5: Commit**

```bash
git add stackant/pyramid_stacker.py tests/test_pyramid_stacker.py
git -c user.email=fsmensa@gmail.com -c user.name=Francesco commit -m "feat(pyramid): PyramidStacker QObject wrapper with worker thread"
```

---

## Task 10 — Settings keys for pyramid params

**Files:**
- Modify: `stackant/settings.py`
- Modify: `tests/test_headless_smoke.py` (extend the Settings class)

- [ ] **Step 1: Write failing test**

In `tests/test_headless_smoke.py`, append to `class TestSettings`:
```python
    def test_save_load_pyramid_params_roundtrip(self, win):
        from stackant import settings
        settings.save_pyramid_params(
            depth=5,
            guided_radius=12,
            drop_misaligned=False,
        )
        loaded = settings.load_pyramid_params()
        assert loaded["depth"] == 5
        assert loaded["guided_radius"] == 12
        assert loaded["drop_misaligned"] is False

    def test_save_load_method_roundtrip(self, win):
        from stackant import settings
        settings.save_method("focus-stack")
        assert settings.load_method() == "focus-stack"
        settings.save_method("pyramid")
        assert settings.load_method() == "pyramid"
        settings.save_method("auto")
        assert settings.load_method() == "auto"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_headless_smoke.py::TestSettings -q
```

Expected: attribute errors on `save_pyramid_params` / `save_method` / `load_method`.

- [ ] **Step 3: Extend `stackant/settings.py`**

Append at the end:
```python
# ---- stacker method selection (v0.2) ----------------------------------

_VALID_METHODS = {"pyramid", "focus-stack", "auto"}
_DEFAULT_METHOD = "pyramid"


def save_method(method: str) -> None:
    if method not in _VALID_METHODS:
        raise ValueError(f"invalid method: {method}")
    _s().setValue("stack/method", method)


def load_method() -> str:
    m = _s().value("stack/method", _DEFAULT_METHOD, type=str)
    return m if m in _VALID_METHODS else _DEFAULT_METHOD


# ---- pyramid advanced params (v0.2) -----------------------------------

_DEFAULT_PYRAMID_DEPTH = -1  # -1 = auto
_DEFAULT_GUIDED_RADIUS = 8
_MIN_GUIDED_RADIUS = 4
_MAX_GUIDED_RADIUS = 32


def save_pyramid_params(
    depth: int,
    guided_radius: int,
    drop_misaligned: bool,
) -> None:
    s = _s()
    s.setValue("stack/pyramid/depth", int(depth))
    s.setValue(
        "stack/pyramid/guided_radius",
        max(_MIN_GUIDED_RADIUS, min(_MAX_GUIDED_RADIUS, int(guided_radius))),
    )
    s.setValue("stack/pyramid/drop_misaligned", bool(drop_misaligned))


def load_pyramid_params() -> dict:
    s = _s()
    depth = s.value("stack/pyramid/depth", _DEFAULT_PYRAMID_DEPTH, type=int)
    raw_radius = s.value("stack/pyramid/guided_radius", _DEFAULT_GUIDED_RADIUS, type=int)
    clamped = max(_MIN_GUIDED_RADIUS, min(_MAX_GUIDED_RADIUS, raw_radius))
    return {
        "depth": depth,
        "guided_radius": clamped,
        "drop_misaligned": s.value("stack/pyramid/drop_misaligned", True, type=bool),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_headless_smoke.py::TestSettings -q
```

Expected: all Settings tests pass (previous 2 + new 2 = 4).

- [ ] **Step 5: Commit**

```bash
git add stackant/settings.py tests/test_headless_smoke.py
git -c user.email=fsmensa@gmail.com -c user.name=Francesco commit -m "feat(settings): persist method + pyramid advanced params"
```

---

## Task 11 — `LogPanel.append_tagged`

**Files:**
- Modify: `stackant/widgets/log_panel.py`
- Modify: `tests/test_headless_smoke.py`

- [ ] **Step 1: Write failing test**

Append a new class to `tests/test_headless_smoke.py`:
```python
class TestLogPanel:
    def test_append_tagged_prefixes_each_line(self, win):
        panel = win.log_panel
        panel._clear()   # use the internal clear to avoid toggling UI state
        panel.append_tagged("pyramid", "first line\nsecond line")
        text = panel.view.toPlainText()
        assert "[pyramid] first line" in text
        assert "[pyramid] second line" in text

    def test_append_without_tag_is_unchanged(self, win):
        panel = win.log_panel
        panel._clear()
        panel.append("plain line")
        text = panel.view.toPlainText()
        assert text.strip() == "plain line"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_headless_smoke.py::TestLogPanel -q
```

Expected: `AttributeError: LogPanel ... append_tagged`.

- [ ] **Step 3: Implement `append_tagged`**

Edit `stackant/widgets/log_panel.py`. Find the `append` method and add below it:
```python
    def append_tagged(self, tag: str, text: str) -> None:
        """Like append(), but prepends '[tag] ' to every line."""
        prefix = f"[{tag}] "
        for line in text.rstrip("\n").splitlines() or [""]:
            if line:
                self.view.appendPlainText(prefix + line)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_headless_smoke.py::TestLogPanel -q
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add stackant/widgets/log_panel.py tests/test_headless_smoke.py
git -c user.email=fsmensa@gmail.com -c user.name=Francesco commit -m "feat(log): add LogPanel.append_tagged for Compare-mode prefixing"
```

---

## Task 12 — StackControls: method radio

**Files:**
- Modify: `stackant/widgets/stack_controls.py`

- [ ] **Step 1: Add the radio UI to `StackControls`**

Edit `stackant/widgets/stack_controls.py`. At the top of `_build_ui`, before the buttons row, insert:
```python
        from PyQt6.QtWidgets import QButtonGroup, QRadioButton

        method_row = QVBoxLayout()
        method_row.addWidget(QLabel("Method:"))
        self._method_group = QButtonGroup(self)
        self.rb_pyramid = QRadioButton("Pyramid")
        self.rb_pyramid.setToolTip(
            "Laplacian-pyramid fusion with guided-filter smoothing.\n"
            "Slower, better edges (cleaner on legs/antennae).\n"
            "Same family as Helicon Method C and Zerene PMax."
        )
        self.rb_focus_stack = QRadioButton("focus-stack")
        self.rb_focus_stack.setToolTip(
            "Complex-wavelet fusion via the focus-stack CLI.\n"
            "Faster, GPU-accelerated when available.\n"
            "Slightly more halo-prone at hard contrast edges."
        )
        self.rb_auto = QRadioButton("Auto")
        self.rb_auto.setToolTip(
            "Picks per image: Pyramid for small stacks (≤50 frames at ≤2K),\n"
            "focus-stack otherwise. For quality-critical work, use Compare."
        )
        self._method_group.addButton(self.rb_pyramid, 0)
        self._method_group.addButton(self.rb_focus_stack, 1)
        self._method_group.addButton(self.rb_auto, 2)
        self.rb_pyramid.setChecked(True)
        method_row.addWidget(self.rb_pyramid)
        method_row.addWidget(self.rb_focus_stack)
        method_row.addWidget(self.rb_auto)
        layout.addLayout(method_row)
```

- [ ] **Step 2: Add a `method()` accessor**

In the same file, just before `set_ready`, add:
```python
    def method(self) -> str:
        if self.rb_focus_stack.isChecked():
            return "focus-stack"
        if self.rb_auto.isChecked():
            return "auto"
        return "pyramid"

    def set_method(self, method: str) -> None:
        if method == "focus-stack":
            self.rb_focus_stack.setChecked(True)
        elif method == "auto":
            self.rb_auto.setChecked(True)
        else:
            self.rb_pyramid.setChecked(True)
```

- [ ] **Step 3: Verify the app still launches**

```bash
QT_QPA_PLATFORM=offscreen timeout 5 .venv/bin/python -c "
import sys
from PyQt6.QtWidgets import QApplication
from stackant.mainwindow import MainWindow
app = QApplication(sys.argv)
w = MainWindow()
assert w.controls.stack_controls.method() == 'pyramid'
print('ok')
"
```

Expected: `ok`.

- [ ] **Step 4: Commit**

```bash
git add stackant/widgets/stack_controls.py
git -c user.email=fsmensa@gmail.com -c user.name=Francesco commit -m "feat(stack_controls): add method radio (Pyramid/focus-stack/Auto)"
```

---

## Task 13 — StackControls: Compare button

**Files:**
- Modify: `stackant/widgets/stack_controls.py`

- [ ] **Step 1: Add the Compare button and a signal**

At the top of `stack_controls.py`, find the class `StackControls` and add the signal:
```python
    compare_requested = pyqtSignal()
```

In `_build_ui`, after the Cancel-button row, insert:
```python
        self.btn_compare = QPushButton("Compare methods")
        self.btn_compare.setToolTip(
            "Runs both stackers on the current frames and shows them\n"
            "side-by-side in the preview. Takes roughly twice as long."
        )
        self.btn_compare.setEnabled(False)
        self.btn_compare.clicked.connect(self.compare_requested.emit)
        layout.addWidget(self.btn_compare)
```

- [ ] **Step 2: Wire the Compare button's enabled state to `_ready`**

In `set_ready`, after the existing `self.btn_stack.setEnabled(...)` line, add:
```python
        self.btn_compare.setEnabled(ready and not self._running)
```

And in `set_running`, after the `self.btn_stack.setEnabled(...)` line, add:
```python
        self.btn_compare.setEnabled(self._ready and not running)
```

- [ ] **Step 3: Verify the app still launches**

```bash
QT_QPA_PLATFORM=offscreen timeout 5 .venv/bin/python -c "
import sys
from PyQt6.QtWidgets import QApplication
from stackant.mainwindow import MainWindow
app = QApplication(sys.argv)
w = MainWindow()
assert not w.controls.stack_controls.btn_compare.isEnabled()
w.controls.stack_controls.set_ready(True)
assert w.controls.stack_controls.btn_compare.isEnabled()
print('ok')
"
```

Expected: `ok`.

- [ ] **Step 4: Commit**

```bash
git add stackant/widgets/stack_controls.py
git -c user.email=fsmensa@gmail.com -c user.name=Francesco commit -m "feat(stack_controls): add Compare methods button"
```

---

## Task 14 — StackControls: Pyramid advanced sub-group

**Files:**
- Modify: `stackant/widgets/stack_controls.py`

- [ ] **Step 1: Wrap the existing focus-stack advanced fields in a named sub-group**

Edit `stack_controls.py` `_build_ui`. Find the section that begins with the consistency row (the first `QHBoxLayout` inside `self.advanced_box`). Wrap all of it — from consistency through `txt_extra` — in a new `QGroupBox`:

Locate the `ab = QVBoxLayout(self.advanced_box)` line. Immediately after it, insert:
```python
        _fs_group = QGroupBox("focus-stack")
        fs = QVBoxLayout(_fs_group)
```

Then in the existing lines, replace every `ab.addLayout(row)` / `ab.addWidget(self.<fs-widget>)` / `ab.addWidget(QLabel(...))` call **that relates to focus-stack options (consistency, denoise, sharp, halo, chk_no_opencl, txt_extra, and the "Extra CLI flags" label)** with the same call against `fs` instead of `ab`.

After those are all reassigned, add:
```python
        ab.addWidget(_fs_group)
```

- [ ] **Step 2: Add the Pyramid sub-group below it**

Append inside `_build_ui`, just before the `self.advanced_box.setVisible(False)` line:
```python
        py_group = QGroupBox("Pyramid")
        py = QVBoxLayout(py_group)

        row = QHBoxLayout()
        row.addWidget(QLabel("Pyramid depth:"))
        self.spn_pyramid_depth = QSpinBox()
        self.spn_pyramid_depth.setRange(0, 12)
        self.spn_pyramid_depth.setSpecialValueText("auto")
        self.spn_pyramid_depth.setValue(0)
        self.spn_pyramid_depth.setToolTip(
            "Number of Laplacian pyramid levels.\n"
            "0 = auto (chosen from image dimensions)."
        )
        row.addWidget(self.spn_pyramid_depth)
        row.addStretch(1)
        py.addLayout(row)

        row = QHBoxLayout()
        row.addWidget(QLabel("Guided-filter radius:"))
        self.spn_guided_radius = QSpinBox()
        self.spn_guided_radius.setRange(4, 32)
        self.spn_guided_radius.setValue(8)
        self.spn_guided_radius.setToolTip(
            "Smoothing window for the sharpness weight map.\n"
            "Higher = smoother transitions, fewer speckle artifacts,\n"
            "slight risk of losing fine detail."
        )
        row.addWidget(self.spn_guided_radius)
        row.addStretch(1)
        py.addLayout(row)

        self.chk_drop_misaligned = QCheckBox("Drop frames whose alignment fails")
        self.chk_drop_misaligned.setChecked(True)
        self.chk_drop_misaligned.setToolTip(
            "On: misaligned frames are skipped with a log warning.\n"
            "Off: any alignment failure aborts the whole run."
        )
        py.addWidget(self.chk_drop_misaligned)

        ab.addWidget(py_group)
```

- [ ] **Step 3: Add a `pyramid_params()` accessor**

In the same file, just before `params(self)`, add:
```python
    def pyramid_params(self) -> dict:
        depth = self.spn_pyramid_depth.value()
        return {
            "pyramid_depth": None if depth == 0 else depth,
            "guided_radius": self.spn_guided_radius.value(),
            "drop_misaligned": self.chk_drop_misaligned.isChecked(),
        }
```

- [ ] **Step 4: Verify the app still launches**

```bash
QT_QPA_PLATFORM=offscreen timeout 5 .venv/bin/python -c "
import sys
from PyQt6.QtWidgets import QApplication
from stackant.mainwindow import MainWindow
app = QApplication(sys.argv)
w = MainWindow()
p = w.controls.stack_controls.pyramid_params()
assert p == {'pyramid_depth': None, 'guided_radius': 8, 'drop_misaligned': True}
print('ok')
"
```

Expected: `ok`.

- [ ] **Step 5: Commit**

```bash
git add stackant/widgets/stack_controls.py
git -c user.email=fsmensa@gmail.com -c user.name=Francesco commit -m "feat(stack_controls): reorganize Advanced into focus-stack + Pyramid sub-groups"
```

---

## Task 15 — PreviewPanel: Compare view toggle

**Files:**
- Modify: `stackant/widgets/preview_panel.py`

- [ ] **Step 1: Add the compare-mode state and button**

Edit `stackant/widgets/preview_panel.py`. In `PreviewPanel.__init__`, after the existing `self._stacked_path: str | None = None` line, add:
```python
        self._stacked_paths: dict[str, str | None] = {
            "pyramid": None, "focus-stack": None,
        }
        self._compare_view: str | None = None  # "pyramid" or "focus-stack" while comparing
```

In `_build_ui`, just after the `header_row` (the row with `Show input frame`), add:
```python
        self.btn_compare_view = QPushButton()
        self.btn_compare_view.setVisible(False)
        self.btn_compare_view.clicked.connect(self._cycle_compare_view)
        self.btn_compare_view.setToolTip(
            "Cycle between the two stacked outputs from Compare mode."
        )
        header_row.addWidget(self.btn_compare_view)
```

- [ ] **Step 2: Add `set_compare_outputs` + `_cycle_compare_view`**

Append to the class:
```python
    def set_compare_outputs(
        self,
        pyramid_path: str | None,
        focus_stack_path: str | None,
    ) -> None:
        """Enter compare mode with one or both stacked outputs."""
        self._stacked_paths["pyramid"] = pyramid_path
        self._stacked_paths["focus-stack"] = focus_stack_path
        first = "pyramid" if pyramid_path else "focus-stack"
        self._compare_view = first
        self._show_compare(first)
        has_both = bool(pyramid_path and focus_stack_path)
        self.btn_compare_view.setVisible(has_both)
        self._update_compare_button_label()

    def _show_compare(self, which: str) -> None:
        path = self._stacked_paths[which]
        if path:
            self.show_stacked(path)

    def _cycle_compare_view(self) -> None:
        if self._compare_view == "pyramid":
            self._compare_view = "focus-stack"
        else:
            self._compare_view = "pyramid"
        self._show_compare(self._compare_view)
        self._update_compare_button_label()

    def _update_compare_button_label(self) -> None:
        if self._compare_view is None:
            return
        current = "Pyramid" if self._compare_view == "pyramid" else "focus-stack"
        self.btn_compare_view.setText(f"View: {current} ↻")
```

- [ ] **Step 3: Clear compare state in `clear()`**

In the existing `clear` method, after `self._stacked_path = None` add:
```python
        self._stacked_paths = {"pyramid": None, "focus-stack": None}
        self._compare_view = None
        self.btn_compare_view.setVisible(False)
```

- [ ] **Step 4: Verify the app still launches**

```bash
QT_QPA_PLATFORM=offscreen timeout 5 .venv/bin/python -c "
import sys
from PyQt6.QtWidgets import QApplication
from stackant.mainwindow import MainWindow
app = QApplication(sys.argv)
w = MainWindow()
assert not w.preview_panel.btn_compare_view.isVisible()
print('ok')
"
```

Expected: `ok`.

- [ ] **Step 5: Commit**

```bash
git add stackant/widgets/preview_panel.py
git -c user.email=fsmensa@gmail.com -c user.name=Francesco commit -m "feat(preview): add Compare view toggle"
```

---

## Task 16 — MainWindow: instantiate PyramidStacker and wire signals

**Files:**
- Modify: `stackant/mainwindow.py`

- [ ] **Step 1: Import and instantiate the pyramid stacker**

Edit `stackant/mainwindow.py`. Add to imports:
```python
from .pyramid_stacker import PyramidStacker
from .stacking import choose_method
```

In `MainWindow.__init__`, immediately after `self._stacker = FocusStacker(self)`, add:
```python
        self._pyramid_stacker = PyramidStacker(self)
```

Also add two more instance attrs:
```python
        self._compare_mode: bool = False
        self._compare_outputs: dict[str, str | None] = {
            "pyramid": None, "focus-stack": None,
        }
```

- [ ] **Step 2: Wire the PyramidStacker signals**

In `_wire_signals`, after the existing `self._stacker.cancelled.connect(...)` line, add:
```python
        self._pyramid_stacker.progress.connect(self.progress.setValue)
        self._pyramid_stacker.log.connect(self._on_pyramid_log)
        self._pyramid_stacker.command_ready.connect(
            lambda cmd: self.log_panel.append(f"\n$ {cmd}\n")
        )
        self._pyramid_stacker.finished_ok.connect(self._on_pyramid_done)
        self._pyramid_stacker.failed.connect(self._on_pyramid_failed)
        self._pyramid_stacker.cancelled.connect(self._on_pyramid_cancelled)

        sc = self.controls.stack_controls
        sc.compare_requested.connect(self._on_compare_requested)
```

- [ ] **Step 3: Add the pyramid signal handlers**

In `MainWindow`, before `_on_stack_done`, add:
```python
    def _on_pyramid_log(self, line: str) -> None:
        if self._compare_mode:
            self.log_panel.append_tagged("pyramid", line)
        else:
            self.log_panel.append(line)

    def _on_pyramid_done(self, output_path: str) -> None:
        self._finish_stacking_ui()
        self.statusBar().showMessage(
            f"Pyramid stack complete: {Path(output_path).name}", 8000
        )
        if self._compare_mode:
            self._compare_outputs["pyramid"] = output_path
            self._maybe_finish_compare()
        else:
            self._stacked_output = output_path
            self.preview_panel.show_stacked(output_path)
            self.controls.export_controls.setEnabled(True)
            if self.controls.input_path:
                self.controls.export_controls.prefill_for_input(self.controls.input_path)

    def _on_pyramid_failed(self, msg: str) -> None:
        self._finish_stacking_ui()
        first_line = msg.splitlines()[0] if msg else "Pyramid stack failed."
        self.statusBar().showMessage(
            f"Pyramid failed: {first_line}  (See log panel for details.)"
        )
        self.log_panel.append(msg)
        if self._compare_mode:
            self._compare_outputs["pyramid"] = None
            self._maybe_finish_compare()

    def _on_pyramid_cancelled(self) -> None:
        self._finish_stacking_ui()
        self.statusBar().showMessage("Pyramid stacking cancelled.", 4000)
        if self._compare_mode:
            # User cancelled during the first half of Compare — abort the
            # whole compare run without starting focus-stack.
            self._compare_mode = False
            self._compare_outputs = {"pyramid": None, "focus-stack": None}
```

- [ ] **Step 4: Verify the app launches**

```bash
QT_QPA_PLATFORM=offscreen timeout 5 .venv/bin/python -c "
import sys
from PyQt6.QtWidgets import QApplication
from stackant.mainwindow import MainWindow
app = QApplication(sys.argv)
w = MainWindow()
print('ok', w._pyramid_stacker is not None)
"
```

Expected: `ok True`.

- [ ] **Step 5: Commit**

```bash
git add stackant/mainwindow.py
git -c user.email=fsmensa@gmail.com -c user.name=Francesco commit -m "feat(mainwindow): instantiate PyramidStacker + wire signals"
```

---

## Task 17 — MainWindow: route Stack Frames to the correct stacker

**Files:**
- Modify: `stackant/mainwindow.py`

- [ ] **Step 1: Replace `_on_stack_requested` with method-aware routing**

Edit `_on_stack_requested` in `mainwindow.py`. Replace its body with:
```python
    def _on_stack_requested(self) -> None:
        kept = self._kept_frame_paths()
        if not kept:
            self.statusBar().showMessage("No frames selected for stacking.")
            return
        if self._current_temp_dir is None:
            self._current_temp_dir = tempfiles.make_temp_dir()

        method_choice = self.controls.stack_controls.method()
        if method_choice == "auto":
            first = Path(kept[0])
            # Use the first kept frame's dimensions as representative.
            try:
                from PIL import Image as _PIL
                with _PIL.open(first) as _im:
                    w, h = _im.size
            except Exception:
                w, h = 1920, 1080
            method = choose_method(len(kept), w, h)
            self.log_panel.append(
                f"[auto] chose {method} for {len(kept)} frames at {w}x{h}"
            )
        else:
            method = method_choice

        self.progress.setVisible(True)
        self.progress.setValue(0)
        self.controls.stack_controls.set_running(True)
        self.act_open_video.setEnabled(False)
        self.act_open_folder.setEnabled(False)

        if method == "pyramid":
            output = str(self._current_temp_dir / "stacked_pyramid.tif")
            self._stacked_output = output
            self.statusBar().showMessage(f"Stacking {len(kept)} frames (Pyramid)…")
            self._pyramid_stacker.stack(
                kept, output, **self.controls.stack_controls.pyramid_params()
            )
        else:
            output = str(self._current_temp_dir / "stacked_focus_stack.tif")
            self._stacked_output = output
            self.statusBar().showMessage(f"Stacking {len(kept)} frames (focus-stack)…")
            self._stacker.stack(kept, output, **self.controls.stack_controls.params())
```

- [ ] **Step 2: Load/save the method in settings**

In `_apply_saved_defaults`, after the `sc.chk_no_opencl.setChecked(sp["no_opencl"])` line, add:
```python
        sc.set_method(settings.load_method())
        pp = settings.load_pyramid_params()
        sc.spn_pyramid_depth.setValue(pp["depth"] if pp["depth"] > 0 else 0)
        sc.spn_guided_radius.setValue(pp["guided_radius"])
        sc.chk_drop_misaligned.setChecked(pp["drop_misaligned"])
```

In `closeEvent`, after the existing `settings.save_stack_params(...)` call, add:
```python
        settings.save_method(sc.method())
        pp = sc.pyramid_params()
        settings.save_pyramid_params(
            depth=pp["pyramid_depth"] if pp["pyramid_depth"] else -1,
            guided_radius=pp["guided_radius"],
            drop_misaligned=pp["drop_misaligned"],
        )
```

- [ ] **Step 3: Verify the routing works on a tiny synthetic stack**

```bash
QT_QPA_PLATFORM=offscreen timeout 60 .venv/bin/python - <<'PY'
import sys, tempfile
from pathlib import Path
import numpy as np
from PIL import Image
import cv2
from PyQt6.QtCore import QEventLoop, QTimer
from PyQt6.QtWidgets import QApplication

from stackant.mainwindow import MainWindow

app = QApplication(sys.argv)

# Synthetic 3-frame stack
d = Path(tempfile.mkdtemp())
rng = np.random.default_rng(0)
base = rng.integers(0, 255, size=(128, 128, 3), dtype=np.uint8)
for i, sigma in enumerate([0.0, 2.0, 4.0]):
    arr = cv2.GaussianBlur(base, (9, 9), sigma) if sigma > 0 else base
    Image.fromarray(arr).save(d / f"f{i:02d}.tif", format="TIFF")

w = MainWindow()
w.controls._set_input(str(d), is_folder=True)
w.controls.folder_selected.emit(str(d))

loop = QEventLoop()
QTimer.singleShot(30000, loop.quit)

def done(p):
    print(f"[pyramid] OK {p} exists={Path(p).is_file()}")
    loop.quit()

w._pyramid_stacker.finished_ok.connect(done)
w._pyramid_stacker.failed.connect(lambda m: (print("FAIL", m), loop.quit()))
QTimer.singleShot(200, lambda: w.controls.stack_controls.stack_requested.emit())
loop.exec()
PY
```

Expected: `[pyramid] OK /tmp/.../stacked_pyramid.tif exists=True`.

- [ ] **Step 4: Commit**

```bash
git add stackant/mainwindow.py
git -c user.email=fsmensa@gmail.com -c user.name=Francesco commit -m "feat(mainwindow): method-aware stack routing + Auto + settings"
```

---

## Task 18 — MainWindow: Compare flow

**Files:**
- Modify: `stackant/mainwindow.py`

- [ ] **Step 1: Add the Compare orchestration handlers**

In `MainWindow`, just below `_on_pyramid_cancelled`, add:
```python
    def _on_compare_requested(self) -> None:
        kept = self._kept_frame_paths()
        if not kept:
            self.statusBar().showMessage("No frames selected for Compare.")
            return
        if self._current_temp_dir is None:
            self._current_temp_dir = tempfiles.make_temp_dir()

        self._compare_mode = True
        self._compare_outputs = {"pyramid": None, "focus-stack": None}

        self.progress.setVisible(True)
        self.progress.setValue(0)
        self.controls.stack_controls.set_running(True)
        self.act_open_video.setEnabled(False)
        self.act_open_folder.setEnabled(False)

        self.statusBar().showMessage(
            f"Compare: running Pyramid on {len(kept)} frames…"
        )
        out = str(self._current_temp_dir / "stacked_pyramid.tif")
        self._pyramid_stacker.stack(
            kept, out, **self.controls.stack_controls.pyramid_params()
        )

    def _maybe_finish_compare(self) -> None:
        """Called after pyramid completes during a Compare run.

        If pyramid was the only step left, finalise; otherwise launch
        focus-stack as the second stage.
        """
        if not self._compare_mode:
            return
        if self._compare_outputs["pyramid"] is None and self._compare_outputs["focus-stack"] is None:
            # Pyramid failed; launch focus-stack anyway.
            self._launch_focus_stack_compare()
        elif self._compare_outputs["pyramid"] is not None and self._compare_outputs["focus-stack"] is None:
            self._launch_focus_stack_compare()
        else:
            self._finalise_compare()

    def _launch_focus_stack_compare(self) -> None:
        kept = self._kept_frame_paths()
        assert self._current_temp_dir is not None
        out = str(self._current_temp_dir / "stacked_focus_stack.tif")
        self.statusBar().showMessage(
            f"Compare: running focus-stack on {len(kept)} frames…"
        )
        self.progress.setValue(0)
        self.controls.stack_controls.set_running(True)
        self._stacker.stack(kept, out, **self.controls.stack_controls.params())
```

- [ ] **Step 2: Adapt the focus-stack handlers to recognise Compare mode**

Edit `_on_stack_done`, `_on_stack_failed`, `_on_stack_cancelled` in mainwindow.py. Wrap each's body so that in Compare mode they update `_compare_outputs` and call `_finalise_compare`:

Replace `_on_stack_done` body with:
```python
    def _on_stack_done(self, output_path: str) -> None:
        self._finish_stacking_ui()
        self.statusBar().showMessage(f"Stack complete: {Path(output_path).name}", 8000)
        if self._compare_mode:
            self._compare_outputs["focus-stack"] = output_path
            self._finalise_compare()
            return
        self._stacked_output = output_path
        self.preview_panel.show_stacked(output_path)
        self.controls.export_controls.setEnabled(True)
        if self.controls.input_path:
            self.controls.export_controls.prefill_for_input(self.controls.input_path)
```

Replace `_on_stack_failed` body with:
```python
    def _on_stack_failed(self, msg: str) -> None:
        self._finish_stacking_ui()
        first_line = msg.splitlines()[0] if msg else "Stack failed."
        hint = "  (See log panel for details.)"
        if "OpenCL" in msg or "CL_OUT_OF_RESOURCES" in msg:
            hint = "  (Try Advanced → Disable OpenCL and re-stack.)"
        self.statusBar().showMessage(f"Stack failed: {first_line}{hint}")
        if self._compare_mode:
            self.log_panel.append_tagged("focus-stack", msg)
            self._compare_outputs["focus-stack"] = None
            self._finalise_compare()
        else:
            self.log_panel.append(msg)
```

Replace `_on_stack_cancelled` body with:
```python
    def _on_stack_cancelled(self) -> None:
        self._finish_stacking_ui()
        self.statusBar().showMessage("Stacking cancelled.", 4000)
        if self._compare_mode:
            self._compare_mode = False
            self._compare_outputs = {"pyramid": None, "focus-stack": None}
```

Also: in the same `_on_stack_done`, tag the focus-stack log during compare. In `_wire_signals` where the existing `self._stacker.log.connect(self.log_panel.append)` line is, replace it with:
```python
        self._stacker.log.connect(self._on_focus_stack_log)
```

Then add a new method to MainWindow:
```python
    def _on_focus_stack_log(self, line: str) -> None:
        if self._compare_mode:
            self.log_panel.append_tagged("focus-stack", line)
        else:
            self.log_panel.append(line)
```

- [ ] **Step 3: Add `_finalise_compare`**

Just below `_on_stack_cancelled`, add:
```python
    def _finalise_compare(self) -> None:
        """Called when Compare has results (one or both stackers done)."""
        pyramid_ok = self._compare_outputs["pyramid"] is not None
        fs_ok = self._compare_outputs["focus-stack"] is not None
        self._compare_mode = False

        self.preview_panel.set_compare_outputs(
            pyramid_path=self._compare_outputs["pyramid"],
            focus_stack_path=self._compare_outputs["focus-stack"],
        )

        # Pick a default export target — prefer pyramid if we have it.
        target = self._compare_outputs["pyramid"] or self._compare_outputs["focus-stack"]
        if target:
            self._stacked_output = target
            self.controls.export_controls.setEnabled(True)
            if self.controls.input_path:
                self.controls.export_controls.prefill_for_input(self.controls.input_path)

        if pyramid_ok and fs_ok:
            status = "Compare complete. Use the view toggle to inspect either output."
        elif pyramid_ok:
            status = "Compare: Pyramid succeeded, focus-stack failed (see log)."
        elif fs_ok:
            status = "Compare: focus-stack succeeded, Pyramid failed (see log)."
        else:
            status = "Compare: both methods failed (see log)."
        self.statusBar().showMessage(status, 10000)
```

- [ ] **Step 4: Verify Compare end-to-end on the tiny synthetic stack**

```bash
QT_QPA_PLATFORM=offscreen timeout 120 .venv/bin/python - <<'PY'
import sys, tempfile
from pathlib import Path
import numpy as np
from PIL import Image
import cv2
from PyQt6.QtCore import QEventLoop, QTimer
from PyQt6.QtWidgets import QApplication

from stackant.mainwindow import MainWindow

app = QApplication(sys.argv)
d = Path(tempfile.mkdtemp())
rng = np.random.default_rng(0)
base = rng.integers(0, 255, size=(128, 128, 3), dtype=np.uint8)
for i, sigma in enumerate([0.0, 2.0, 4.0]):
    arr = cv2.GaussianBlur(base, (9, 9), sigma) if sigma > 0 else base
    Image.fromarray(arr).save(d / f"f{i:02d}.tif", format="TIFF")

w = MainWindow()
w.controls._set_input(str(d), is_folder=True)
w.controls.folder_selected.emit(str(d))

loop = QEventLoop()
QTimer.singleShot(90000, loop.quit)
def check_done():
    if w.preview_panel.btn_compare_view.isVisible() or not w._compare_mode:
        print(f"compare done, outputs={w._compare_outputs}")
        loop.quit()
    else:
        QTimer.singleShot(500, check_done)

QTimer.singleShot(200, lambda: w.controls.stack_controls.compare_requested.emit())
QTimer.singleShot(1000, check_done)
loop.exec()
PY
```

Expected: `compare done, outputs={'pyramid': '/tmp/.../stacked_pyramid.tif', 'focus-stack': ...}` with both paths non-None (assuming focus-stack is installed locally).

- [ ] **Step 5: Commit**

```bash
git add stackant/mainwindow.py
git -c user.email=fsmensa@gmail.com -c user.name=Francesco commit -m "feat(mainwindow): Compare flow chaining both stackers with log tagging"
```

---

## Task 19 — MainWindow: graceful degradation when opencv-contrib is missing

**Files:**
- Modify: `stackant/mainwindow.py`

- [ ] **Step 1: Detect the missing dependency at app bootstrap**

At the top of `mainwindow.py`, after the existing `from .pyramid_stacker import PyramidStacker` line, add:
```python
from .pyramid_stacker import GUIDED_FILTER_AVAILABLE
```

- [ ] **Step 2: Disable pyramid paths if unavailable**

At the end of `_apply_saved_defaults` (just before the closing `def _wire_signals(...)`), add:
```python
        if not GUIDED_FILTER_AVAILABLE:
            sc = self.controls.stack_controls
            sc.rb_pyramid.setEnabled(False)
            sc.rb_auto.setEnabled(False)
            sc.btn_compare.setEnabled(False)
            sc.set_method("focus-stack")
            tip = (
                "opencv-contrib-python-headless is required for the Pyramid stacker."
            )
            sc.rb_pyramid.setToolTip(tip)
            sc.rb_auto.setToolTip(tip)
            sc.btn_compare.setToolTip(tip)
            self.statusBar().showMessage(
                "Pyramid stacker disabled: install opencv-contrib-python-headless."
            )
```

- [ ] **Step 3: Verify**

```bash
QT_QPA_PLATFORM=offscreen timeout 5 .venv/bin/python -c "
import sys
# Simulate missing guided filter.
import stackant.pyramid_stacker as ps
ps.GUIDED_FILTER_AVAILABLE = False
from stackant.mainwindow import GUIDED_FILTER_AVAILABLE
print('import-time flag:', GUIDED_FILTER_AVAILABLE)
"
```

This just checks the import path; the real test is whether a local install without contrib shows the disabled UI — the disabled-branch logic is simple and dry-readable.

- [ ] **Step 4: Commit**

```bash
git add stackant/mainwindow.py
git -c user.email=fsmensa@gmail.com -c user.name=Francesco commit -m "feat(mainwindow): disable Pyramid UI when opencv-contrib missing"
```

---

## Task 20 — Headless-smoke tests for method picker and Compare flow

**Files:**
- Modify: `tests/test_headless_smoke.py`

- [ ] **Step 1: Add a new test class**

Append to `tests/test_headless_smoke.py`:
```python
class TestMethodPicker:
    def test_default_method_is_pyramid(self, win):
        assert win.controls.stack_controls.method() == "pyramid"

    def test_set_method_switches_radio(self, win):
        win.controls.stack_controls.set_method("focus-stack")
        assert win.controls.stack_controls.method() == "focus-stack"
        win.controls.stack_controls.set_method("auto")
        assert win.controls.stack_controls.method() == "auto"
        win.controls.stack_controls.set_method("pyramid")
        assert win.controls.stack_controls.method() == "pyramid"

    def test_compare_button_enabled_follows_ready(self, win):
        sc = win.controls.stack_controls
        sc.set_ready(False)
        assert not sc.btn_compare.isEnabled()
        sc.set_ready(True)
        assert sc.btn_compare.isEnabled()
```

- [ ] **Step 2: Run it**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_headless_smoke.py::TestMethodPicker -q
```

Expected: 3 passed.

- [ ] **Step 3: Commit**

```bash
git add tests/test_headless_smoke.py
git -c user.email=fsmensa@gmail.com -c user.name=Francesco commit -m "test: headless-smoke tests for method picker + Compare enablement"
```

---

## Task 21 — Full-suite sanity + ruff

- [ ] **Step 1: Run every test**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/ -q
```

Expected: all green. If anything failed, go back and fix before committing docs.

- [ ] **Step 2: Lint**

```bash
.venv/bin/ruff check stackant/ tests/
```

Expected: `All checks passed!`. Fix any new lints in place (prefer in-file `# noqa` only for BLE001 on the worker's broad exception, which is intentional).

- [ ] **Step 3: No commit here** — tests/lint just gate the next step.

---

## Task 22 — Docs: CHANGELOG + CLAUDE + design doc cross-link

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Add the v0.2.0 entry at the top of CHANGELOG.md**

Edit `CHANGELOG.md`. After the title block (after line `this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).`), and before the `## [0.1.0] — 2026-04-23` line, insert:
```markdown
## [0.2.0] — Unreleased

### Added

- **Laplacian-pyramid stacking method** alongside `focus-stack`,
  using guided-filter-smoothed sharpness weight maps per pyramid
  level. Same algorithm family as Helicon Focus Method C and Zerene
  PMax. Produces cleaner edges than `focus-stack`'s wavelet path on
  hard contrast boundaries (legs, antennae against bright
  backgrounds). Pure Python/NumPy/OpenCV, CPU-only.
- **Method radio** (Pyramid / focus-stack / Auto) with Pyramid as
  the default. Auto picks by stack size and resolution (≤50 frames
  and longest edge ≤2048 → Pyramid, else focus-stack).
- **Compare methods** button that runs both stackers on the current
  frames and shows both outputs in the preview with a view toggle.
- **Advanced panel** reorganised into method-specific sub-groups;
  three new Pyramid tunables (depth, guided-filter radius, drop
  misaligned frames).
- Log panel prefixes lines with `[pyramid]` / `[focus-stack]`
  during Compare runs.
- Settings persist method + pyramid params across launches.

### Changed

- Dependency: `opencv-python-headless` →
  `opencv-contrib-python-headless` (needed for
  `cv2.ximgproc.guidedFilter`).
```

- [ ] **Step 2: Update CLAUDE.md current-state block**

Edit `CLAUDE.md`. Replace the "Current state" section with:
```markdown
## Current state

- v0.1.0 shipped; v0.2.0 in progress on main.
- Two stacking backends: `focus-stack` CLI (existing) and an
  in-process Laplacian-pyramid implementation in
  `stackant/pyramid_stacker.py` with a worker `QThread` and
  guided-filter-smoothed sharpness weights.
- Method radio in StackControls (Pyramid / focus-stack / Auto),
  Compare button, Pyramid-specific Advanced sub-group, compare
  view toggle in the preview panel. See
  `docs/superpowers/specs/2026-04-23-pyramid-stacking-design.md`
  for the full design and
  `docs/superpowers/plans/2026-04-23-pyramid-stacking.md` for the
  task-by-task plan.
```

- [ ] **Step 3: Verify CLAUDE.md is still under 200 lines**

```bash
wc -l CLAUDE.md
```

Expected: a line count under 200.

- [ ] **Step 4: Commit**

```bash
git add CHANGELOG.md CLAUDE.md
git -c user.email=fsmensa@gmail.com -c user.name=Francesco commit -m "docs: v0.2.0 Unreleased CHANGELOG + CLAUDE.md state refresh"
```

---

## Task 23 — Manual end-to-end verification on the Uganda video

This is not a committed step, but it IS a merge gate.

- [ ] **Step 1: Run Pyramid on the real video**

Launch the app manually:
```bash
source .venv/bin/activate
python main.py
```

- Open `/home/francesco/Scaricati/Formiche Uganda/Vid_26-04-22 150856.mp4`
- Decimation 30 → extract
- Leave method on Pyramid → Stack Frames
- Wait for completion; note wall-clock runtime and peak memory
- Screenshot a known halo region (leg against bright background)

- [ ] **Step 2: Run focus-stack on the same frames**

- Flip the method radio to `focus-stack`
- Click Stack Frames
- Screenshot the same region

- [ ] **Step 3: Run Compare**

- Click Compare methods
- Wait for both stackers to finish
- Verify the preview toggle appears and flips cleanly
- Verify the log panel shows `[pyramid]` and `[focus-stack]` prefixes

- [ ] **Step 4: Run CI locally or push a branch to trigger CI**

```bash
.venv/bin/ruff check stackant/ tests/
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/ -q
```

Expected: all green on Python 3.10 and 3.12 (CI matrix).

- [ ] **Step 5: Tag and release (manual, post-review)**

After merging:
```bash
git -c user.email=fsmensa@gmail.com -c user.name=Francesco tag -a v0.2.0 -m "StackAnt v0.2.0 — Laplacian-pyramid stacking + Compare"
git push origin main
git push origin v0.2.0
```

Then cut a GitHub release via `gh release create v0.2.0 --notes-file <(sed -n '/^## \[0.2.0\]/,/^## \[/p' CHANGELOG.md | sed '$d')`.

---

## Post-plan checklist

After all tasks are done:

- [ ] All 23 tasks completed, each committed.
- [ ] CI green on 3.10 and 3.12.
- [ ] README / CHANGELOG / PLAN / CLAUDE.md consistent.
- [ ] Manual Uganda-video comparison screenshots attached to the PR
      description (if going via PR) or to a release note on GitHub.
- [ ] Tag `v0.2.0` pushed and release created.
- [ ] Roadmap `docs/PLAN.md` ticks the v0.2 box; next up is v0.3 (batch).
