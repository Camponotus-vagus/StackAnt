"""Laplacian-pyramid focus stacker.

Pure-Python implementation of the algorithm family used by Helicon
Focus Method C and Zerene Stacker PMax: Laplacian pyramid fusion with
guided-filter-smoothed sharpness weight maps. Addresses halos at hard
contrast edges that the wavelet-based focus-stack CLI (our default
backend) is prone to on macro entomology subjects.

Design tenets:
- All helpers operate on float32 arrays in [0, 1] for numerical
  stability during pyramid collapse.
- Input/output to/from disk is uint8 or uint16 BGR (OpenCV convention);
  16-bit inputs produce a 16-bit output.
- Progress and cancellation are driven from the caller (see
  run_pyramid_stack + PyramidStacker below).
"""
from __future__ import annotations

import concurrent.futures
import math
import os
import threading
from collections import deque
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path

import cv2
import numpy as np
from PyQt6.QtCore import QObject, QThread, pyqtSignal

from .imread import imread

try:
    from cv2 import ximgproc as _ximgproc
    GUIDED_FILTER_AVAILABLE = True
except ImportError:
    _ximgproc = None
    GUIDED_FILTER_AVAILABLE = False


def build_laplacian_pyramid(
    image: np.ndarray, levels: int
) -> list[np.ndarray]:
    """Return [L_0, L_1, ..., L_{levels-2}, G_{levels-1}].

    L_k = G_k - pyrUp(G_{k+1}) cropped to G_k's shape. The last
    entry is the coarsest Gaussian, which the collapse step seeds
    with.
    """
    gauss = [image.astype(np.float32, copy=False)]
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
    # Compute second derivatives and take absolute values in-place to save allocations.
    ddx = cv2.filter2D(gray, cv2.CV_32F, _SML_KERNEL_X)
    np.abs(ddx, out=ddx)
    ddy = cv2.filter2D(gray, cv2.CV_32F, _SML_KERNEL_Y)
    np.abs(ddy, out=ddy)
    ddx += ddy
    # Box-filter summation across the window.
    return cv2.boxFilter(ddx, cv2.CV_32F, (_SML_WINDOW, _SML_WINDOW), normalize=False)


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
        guide=guide.astype(np.float32, copy=False),
        src=weights.astype(np.float32, copy=False),
        radius=int(radius),
        eps=float(eps),
    )


def fuse_images(
    images: Iterable[np.ndarray | tuple[np.ndarray, np.ndarray | None]],
    levels: int,
    guided_radius: int = 8,
) -> np.ndarray:
    """Laplacian-pyramid fusion of N float32 RGB images in [0, 1].

    Each item is an image, or an (image, valid_mask) pair where the uint8
    mask is 0 on pixels the image does not cover (the border an alignment
    warp exposes). Masked-out pixels get zero weight, so they cannot pull
    the result towards whatever fills them.

    Pipeline:
        - for each image, build L-level Laplacian pyramid
        - at each level, compute per-image SML on its grayscale
          component, smooth with guided filter, and accumulate
          weighted Laplacian coefficients
        - normalise across N so weights sum to 1 at every pixel
        - collapse to full resolution

    Input images must be pre-aligned and have identical shape.
    Iterating over images rather than pre-building all pyramids
    reduces memory usage from O(N * size) to O(size).
    """
    iterator = iter(images)
    try:
        first_im, first_mask = _split_masked(next(iterator))
    except StopIteration:
        raise ValueError("fuse_images needs at least one image")

    # Initialize fused levels and total weights based on the first image's pyramid.
    pyramid = build_laplacian_pyramid(first_im, levels)
    fused_levels = [np.zeros_like(band) for band in pyramid]
    total_weights = [np.zeros(band.shape[:2], dtype=np.float32) for band in pyramid]

    def process_pyramid(p: list[np.ndarray], mask: np.ndarray | None) -> None:
        mask_levels = _mask_pyramid(mask, levels) if mask is not None else None
        for lvl, band in enumerate(p):
            # Grayscale for sharpness scoring and as a guide for smoothing.
            if band.ndim == 3:
                gray = cv2.cvtColor(band, cv2.COLOR_RGB2GRAY)
            else:
                gray = band

            # Compute and smooth sharpness weights.
            w = compute_sml(gray)
            sw = smooth_weights(w, gray, radius=guided_radius)
            np.maximum(sw, 0.0, out=sw)
            sw += 1e-8
            if mask_levels is not None:
                sw *= mask_levels[lvl]

            total_weights[lvl] += sw
            if band.ndim == 3:
                fused_levels[lvl] += sw[..., np.newaxis] * band
            else:
                fused_levels[lvl] += sw * band

    process_pyramid(pyramid, first_mask)

    for item in iterator:
        im, mask = _split_masked(item)
        if im.shape != first_im.shape:
            raise ValueError("fuse_images: all images must share shape")
        pyramid = build_laplacian_pyramid(im, levels)
        process_pyramid(pyramid, mask)

    # Normalise each level so weights sum to 1 per pixel. The floor only
    # matters where every image was masked out.
    for lvl in range(levels):
        np.maximum(total_weights[lvl], 1e-12, out=total_weights[lvl])
        if fused_levels[lvl].ndim == 3:
            fused_levels[lvl] /= total_weights[lvl][..., np.newaxis]
        else:
            fused_levels[lvl] /= total_weights[lvl]

    return collapse_laplacian_pyramid(fused_levels)


def _split_masked(
    item: np.ndarray | tuple[np.ndarray, np.ndarray | None],
) -> tuple[np.ndarray, np.ndarray | None]:
    if isinstance(item, tuple):
        return item
    return item, None


def _mask_pyramid(mask: np.ndarray, levels: int) -> list[np.ndarray]:
    current = mask.astype(np.float32) * (1.0 / 255.0)
    out = [current]
    for _ in range(levels - 1):
        current = cv2.pyrDown(current)
        out.append(current)
    return out


_ECC_CRITERIA = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 100, 1e-4)

# ECC returns its final correlation even when it hit the iteration cap on a
# bad warp; fusing such a frame ghosts. Matching frames score ~0.95+, so this
# only rejects clearly unrelated or failed registrations.
MIN_ECC_CORRELATION = 0.5
# Focus-pull breathing changes scale by a few percent at most.
MIN_WARP_SCALE = 0.8
MAX_WARP_SCALE = 1.25
MAX_WARP_ROTATION_DEG = 10.0
MAX_WARP_ANISOTROPY = 1.15


def _warp_is_plausible(warp: np.ndarray) -> bool:
    a, b, c, d = (float(v) for v in warp[:, :2].ravel())
    det = a * d - b * c
    if det <= 0:
        return False
    if not MIN_WARP_SCALE <= math.sqrt(det) <= MAX_WARP_SCALE:
        return False
    if abs(math.degrees(math.atan2(c - b, a + d))) > MAX_WARP_ROTATION_DEG:
        return False
    # Singular-value ratio of the linear part: captures shear and
    # non-uniform stretch.
    trace_sq = a * a + b * b + c * c + d * d
    disc = math.sqrt(max(trace_sq * trace_sq - 4 * det * det, 0.0))
    s_max_sq = (trace_sq + disc) / 2
    s_min_sq = (trace_sq - disc) / 2
    if s_min_sq <= 0:
        return False
    return math.sqrt(s_max_sq / s_min_sq) <= MAX_WARP_ANISOTROPY


def estimate_affine(
    reference: np.ndarray,
    moving: np.ndarray,
    max_edge: int = 1024,
) -> tuple[np.ndarray, bool]:
    """Estimate the ECC affine warp aligning `moving` to `reference`.

    Both inputs must be 2-D float32 (grayscale). Returns the 2x3 warp
    (for cv2.WARP_INVERSE_MAP) and a success flag. On failure - ECC
    error, low correlation, or an implausible warp - returns the
    identity and ok=False.

    ECC runs coarse-to-fine on downscaled copies (from _ECC_COARSEST_EDGE
    up to max_edge), seeding each level with the previous estimate. A
    single ECC pass at ~1024 px settles in a wrong local optimum on sharp,
    finely textured frames (translation off by 10-30 px, compensated by a
    spurious shear); starting coarse fixes that and still preserves
    sub-pixel accuracy. Translation terms are rescaled between levels.
    """
    if reference.shape != moving.shape:
        raise ValueError("reference and moving must share shape")
    h, w = reference.shape
    longest = max(h, w)
    identity = np.eye(2, 3, dtype=np.float32)
    warp = identity.copy()
    correlation = 0.0
    prev_scale: float | None = None
    for edge in _ecc_level_edges(longest, max_edge):
        scale = min(1.0, edge / longest)
        if prev_scale is not None:
            warp[:, 2] *= scale / prev_scale
        if scale < 1.0:
            size = (max(1, int(w * scale)), max(1, int(h * scale)))
            ref_in = cv2.resize(reference, size, interpolation=cv2.INTER_AREA)
            mov_in = cv2.resize(moving, size, interpolation=cv2.INTER_AREA)
        else:
            ref_in, mov_in = reference, moving
        try:
            correlation, warp = cv2.findTransformECC(
                templateImage=ref_in,
                inputImage=mov_in,
                warpMatrix=warp,
                motionType=cv2.MOTION_AFFINE,
                criteria=_ECC_CRITERIA,
                inputMask=None,
                gaussFiltSize=5,
            )
        except cv2.error:
            return identity, False
        prev_scale = scale
    if not (correlation >= MIN_ECC_CORRELATION and np.isfinite(warp).all()):
        return identity, False
    if not _warp_is_plausible(warp):
        return identity, False
    warp[:, 2] /= prev_scale
    return warp, True


_ECC_COARSEST_EDGE = 256


def _ecc_level_edges(longest: int, max_edge: int) -> list[int]:
    """Longest-edge sizes for the coarse-to-fine ECC levels, coarsest first."""
    top = min(longest, max_edge)
    edges = [top]
    while edges[-1] // 2 >= _ECC_COARSEST_EDGE:
        edges.append(edges[-1] // 2)
    return edges[::-1]


def align_to_reference(
    reference: np.ndarray,
    moving: np.ndarray,
    max_edge: int = 1024,
) -> tuple[np.ndarray, np.ndarray, bool]:
    """Align `moving` to `reference` using ECC with affine motion.

    Returns the warped moving image, the 2x3 affine warp matrix, and a
    success flag. On failure the original moving image is returned with
    the identity warp and ok=False. See `estimate_affine`.
    """
    warp, ok = estimate_affine(reference, moving, max_edge)
    if not ok:
        return moving, warp, False
    h, w = reference.shape
    aligned = cv2.warpAffine(
        moving, warp, (w, h), flags=cv2.INTER_LINEAR + cv2.WARP_INVERSE_MAP
    )
    return aligned, warp, True


def _auto_pyramid_depth(height: int, width: int) -> int:
    return max(3, math.floor(math.log2(min(height, width))) - 3)


def _load_rgb(path: str) -> tuple[np.ndarray, bool]:
    """Read an image as float32 RGB in [0, 1]; also report whether it was 16-bit."""
    bgr = imread(path, cv2.IMREAD_ANYDEPTH | cv2.IMREAD_COLOR)
    if bgr is None:
        raise OSError(f"could not read image: {path}")
    if bgr.dtype == np.uint8:
        max_value, is_16bit = 255.0, False
    elif bgr.dtype == np.uint16:
        max_value, is_16bit = 65535.0, True
    else:
        raise OSError(f"unsupported pixel type {bgr.dtype}: {path}")
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    # Perform in-place float scaling to reduce temporary array memory allocations by 50%.
    arr = rgb.astype(np.float32)
    arr *= 1.0 / max_value
    return arr, is_16bit


def _load_rgb_float(path: str) -> np.ndarray:
    return _load_rgb(path)[0]


def _save_rgb_float(path: str, image: np.ndarray, *, sixteen_bit: bool = False) -> None:
    # Streamline clipping and integer scale to avoid multiple intermediate float arrays.
    if sixteen_bit:
        rgb = np.clip(image * 65535.0 + 0.5, 0, 65535).astype(np.uint16)
    else:
        rgb = np.clip(image * 255.0 + 0.5, 0, 255).astype(np.uint8)
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

    # Alignment: use the middle frame as the reference.
    ref_idx = len(input_paths) // 2
    ref_image, sixteen_bit = _load_rgb(input_paths[ref_idx])
    ref_gray = cv2.cvtColor(ref_image, cv2.COLOR_RGB2GRAY)
    h, w = ref_gray.shape
    n = len(input_paths)

    abort = threading.Event()
    full_mask = np.full((h, w), 255, dtype=np.uint8)

    def process_frame(idx: int) -> tuple[int, tuple[np.ndarray, np.ndarray | None] | None]:
        if abort.is_set() or cancel_check():
            return idx, None
        if idx == ref_idx:
            return idx, (ref_image, None)

        im = _load_rgb_float(input_paths[idx])
        if im.shape != ref_image.shape:
            raise ValueError(
                f"pyramid stacker requires same-shape inputs; {input_paths[idx]} differs"
            )

        gray = cv2.cvtColor(im, cv2.COLOR_RGB2GRAY)
        warp, ok = estimate_affine(ref_gray, gray)
        if ok:
            # Replicate rather than zero-fill the exposed border: black fill
            # creates a hard edge whose high sharpness wins the fusion and
            # leaves dark wedges along the frame edges.
            warped_rgb = cv2.warpAffine(
                im, warp, (w, h),
                flags=cv2.INTER_LINEAR + cv2.WARP_INVERSE_MAP,
                borderMode=cv2.BORDER_REPLICATE,
            )
            valid = cv2.warpAffine(
                full_mask, warp, (w, h),
                flags=cv2.INTER_NEAREST + cv2.WARP_INVERSE_MAP,
                borderMode=cv2.BORDER_CONSTANT, borderValue=0,
            )
            return idx, (warped_rgb, valid)
        return idx, None

    def aligned_stream() -> Iterable[tuple[np.ndarray, np.ndarray | None]]:
        dropped_count = 0
        processed_count = 0
        # Alignment is OpenCV-heavy (releases the GIL), so threads help. Only
        # a small window of frames is in flight: each aligned 4K frame is
        # ~100 MB of float32, and submitting them all at once kept every one
        # of them in memory until the end of the run.
        workers = min(4, os.cpu_count() or 1)
        window = workers + 2
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            pending: deque[concurrent.futures.Future] = deque()
            next_idx = 0

            def top_up() -> None:
                nonlocal next_idx
                while next_idx < n and len(pending) < window:
                    pending.append(executor.submit(process_frame, next_idx))
                    next_idx += 1

            try:
                top_up()
                while pending:
                    _check_cancel()
                    idx, aligned = pending.popleft().result()
                    top_up()
                    processed_count += 1
                    _progress(
                        int(5 + 85 * processed_count / n), "Aligning + fusing frames"
                    )
                    if aligned is not None:
                        yield aligned
                        continue
                    if cancel_check():
                        continue
                    dropped_count += 1
                    if not drop_misaligned:
                        raise RuntimeError(
                            f"ECC alignment failed for {input_paths[idx]} "
                            "and drop_misaligned is False"
                        )
            finally:
                # Fusion raised or the generator was closed: let queued frames
                # return at once instead of being loaded and aligned for nothing.
                abort.set()

        if n > 1 and dropped_count == n - 1:
            raise RuntimeError(
                f"All {n - 1} non-reference frames failed ECC alignment. "
                "Subject may be moving."
            )
        if dropped_count > 0:
            _progress(90, f"Dropped {dropped_count} misaligned frame(s)")

    # Pyramid depth.
    depth = pyramid_depth if pyramid_depth and pyramid_depth > 0 else _auto_pyramid_depth(
        h, w
    )

    _progress(5, "Aligning + fusing frames")
    _check_cancel()
    # fuse_images now consumes the stream lazily.
    fused = fuse_images(aligned_stream(), levels=depth, guided_radius=guided_radius)
    _check_cancel()

    _progress(95, "Writing output")
    _save_rgb_float(output_path, fused, sixteen_bit=sixteen_bit)
    _progress(100, "Done")
    return output_path


class Cancelled(Exception):
    """Raised inside run_pyramid_stack when the caller requests cancellation."""


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
        if self._thread is None:
            return
        self._thread.quit()
        # Deleting a QThread that is still running aborts the process, so
        # keep the references (and is_running) until it has really stopped.
        if not self._thread.wait(3000):
            return
        self._thread.deleteLater()
        if self._worker is not None:
            self._worker.deleteLater()
        self._thread = None
        self._worker = None

    def shutdown(self, timeout_ms: int = 5000) -> bool:
        """Cancel any run and wait for the thread to stop; True if stopped."""
        self.cancel()
        if self._thread is None:
            return True
        self._cancel.set()
        self._thread.quit()
        if not self._thread.wait(timeout_ms):
            return False
        self._cleanup_thread()
        return True

    def _on_worker_done(self, path: str) -> None:
        self._cleanup_thread()
        self.finished_ok.emit(path)

    def _on_worker_failed(self, msg: str) -> None:
        self._cleanup_thread()
        self.failed.emit(msg)

    def _on_worker_cancelled(self) -> None:
        self._cleanup_thread()
        self.cancelled.emit()
