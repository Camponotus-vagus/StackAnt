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
