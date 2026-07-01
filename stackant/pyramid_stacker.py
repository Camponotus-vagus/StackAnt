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

import math
import concurrent.futures
import threading
from pathlib import Path
from typing import Callable, Iterable, Sequence

import cv2
import numpy as np
from PyQt6.QtCore import QObject, QThread, pyqtSignal

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
    ddx = np.abs(cv2.filter2D(gray, cv2.CV_32F, _SML_KERNEL_X))
    ddy = np.abs(cv2.filter2D(gray, cv2.CV_32F, _SML_KERNEL_Y))
    ml = ddx + ddy
    # Box-filter summation across the window.
    return cv2.boxFilter(ml, cv2.CV_32F, (_SML_WINDOW, _SML_WINDOW), normalize=False)


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
    images: Iterable[np.ndarray],
    levels: int,
    guided_radius: int = 8,
) -> np.ndarray:
    """Laplacian-pyramid fusion of N float32 RGB images in [0, 1].

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
        first_im = next(iterator)
    except StopIteration:
        raise ValueError("fuse_images needs at least one image")

    # Initialize fused levels and total weights based on the first image's pyramid.
    pyramid = build_laplacian_pyramid(first_im, levels)
    fused_levels = [np.zeros_like(band) for band in pyramid]
    total_weights = [np.zeros(band.shape[:2], dtype=np.float32) for band in pyramid]

    def process_pyramid(p: list[np.ndarray]) -> None:
        for lvl, band in enumerate(p):
            # Grayscale for sharpness scoring and as a guide for smoothing.
            if band.ndim == 3:
                gray = cv2.cvtColor(band, cv2.COLOR_RGB2GRAY)
            else:
                gray = band

            # Compute and smooth sharpness weights.
            w = compute_sml(gray)
            sw = smooth_weights(w, gray, radius=guided_radius)
            sw = np.maximum(sw, 0.0) + 1e-8

            total_weights[lvl] += sw
            if band.ndim == 3:
                fused_levels[lvl] += sw[..., np.newaxis] * band
            else:
                fused_levels[lvl] += sw * band

    process_pyramid(pyramid)

    for im in iterator:
        if im.shape != first_im.shape:
            raise ValueError("fuse_images: all images must share shape")
        pyramid = build_laplacian_pyramid(im, levels)
        process_pyramid(pyramid)

    # Normalise each level so weights sum to 1 per pixel.
    for lvl in range(levels):
        if fused_levels[lvl].ndim == 3:
            fused_levels[lvl] /= total_weights[lvl][..., np.newaxis]
        else:
            fused_levels[lvl] /= total_weights[lvl]

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

    # Alignment: use the middle frame as the reference.
    ref_idx = len(input_paths) // 2
    ref_image = _load_rgb_float(input_paths[ref_idx])
    ref_gray = cv2.cvtColor(ref_image, cv2.COLOR_RGB2GRAY)
    h, w = ref_gray.shape
    n = len(input_paths)

    def process_frame(idx: int) -> tuple[int, np.ndarray | None]:
        if cancel_check():
            return idx, None
        if idx == ref_idx:
            return idx, ref_image

        im = _load_rgb_float(input_paths[idx])
        if im.shape != ref_image.shape:
            raise ValueError(
                f"pyramid stacker requires same-shape inputs; {input_paths[idx]} differs"
            )

        gray = cv2.cvtColor(im, cv2.COLOR_RGB2GRAY)
        _, warp, ok = align_to_reference(ref_gray, gray)
        if ok:
            warped_rgb = cv2.warpAffine(
                im, warp, (w, h),
                flags=cv2.INTER_LINEAR + cv2.WARP_INVERSE_MAP,
            )
            return idx, warped_rgb
        return idx, None

    def aligned_stream() -> Iterable[np.ndarray]:
        dropped_count = 0
        processed_count = 0
        # Use ThreadPoolExecutor to parallelize loading and alignment.
        # Alignment is OpenCV-heavy (releasing GIL), so threads are effective.
        with concurrent.futures.ThreadPoolExecutor() as executor:
            # Maintain input order by using executor.map or similar.
            # Here we use executor.submit to handle potential cancellations better.
            futures = [executor.submit(process_frame, i) for i in range(n)]
            for future in futures:
                _check_cancel()
                _, aligned_im = future.result()
                processed_count += 1
                _progress(int(5 + 25 * processed_count / n), "Aligning frames")
                if aligned_im is not None:
                    yield aligned_im
                else:
                    dropped_count += 1
                    if not drop_misaligned and not cancel_check():
                        # idx is not easily available here without more bookkeeping,
                        # but we can raise a generic error or refactor.
                        raise RuntimeError(
                            "ECC alignment failed for a frame and drop_misaligned is False"
                        )

        if dropped_count == n:
            raise RuntimeError(
                f"All {n} frames failed ECC alignment. Subject may be moving."
            )
        if dropped_count > 0:
            _progress(30, f"Dropped {dropped_count} misaligned frame(s)")

    # Pyramid depth.
    depth = pyramid_depth if pyramid_depth and pyramid_depth > 0 else _auto_pyramid_depth(
        h, w
    )

    _progress(30, "Stacking frames")
    _check_cancel()
    # fuse_images now consumes the stream lazily.
    fused = fuse_images(aligned_stream(), levels=depth, guided_radius=guided_radius)
    _check_cancel()

    _progress(95, "Writing output")
    _save_rgb_float(output_path, fused)
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
