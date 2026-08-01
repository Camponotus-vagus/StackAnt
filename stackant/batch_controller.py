"""Sequential, unattended batch orchestration over a list of videos."""
from __future__ import annotations

from pathlib import Path

from PIL import Image
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QApplication

from . import tempfiles
from .batch import BatchItem, BatchSettings, is_already_done, output_targets
from .exporter import export_jpeg, export_tiff
from .frame_filter import (
    FilterState,
    auto_threshold,
    score_frames,
    suggested_decimation_target,
)
from .stacker import should_retry_without_opencl
from .stacking import choose_method


class BatchController(QObject):
    item_started = pyqtSignal(int)             # index
    item_progress = pyqtSignal(int, int)       # index, percent 0..100
    item_status = pyqtSignal(int, str)         # index, step label
    item_finished = pyqtSignal(int, str, str)  # index, status, message
    batch_finished = pyqtSignal(dict)
    log = pyqtSignal(str)

    def __init__(self, extractor, focus_stacker, pyramid_stacker, parent=None):
        super().__init__(parent)
        self._extractor = extractor
        self._focus = focus_stacker
        self._pyramid = pyramid_stacker

        self._items: list[BatchItem] = []
        self._settings: BatchSettings | None = None
        self._idx: int = -1
        self._temp_dir: Path | None = None
        self._kept: list[str] = []
        self._stack_out: str | None = None
        self._stack_method: str = "focus-stack"
        self._item_retried: bool = False
        self._cancelled: bool = False

        self._extractor.finished_ok.connect(self._on_extract_done)
        self._extractor.failed.connect(self._on_extract_failed)
        self._extractor.cancelled.connect(self._on_worker_cancelled)
        self._extractor.progress.connect(self._on_extract_progress)
        for st in (self._focus, self._pyramid):
            st.finished_ok.connect(self._on_stack_done)
            st.failed.connect(self._on_stack_failed)
            st.cancelled.connect(self._on_worker_cancelled)
            st.progress.connect(self._on_stack_progress)

    # ---- public API ----
    def run(self, items: list[BatchItem], settings: BatchSettings) -> None:
        self._items = list(items)
        self._settings = settings
        self._idx = -1
        self._cancelled = False
        self._advance()

    def cancel(self) -> None:
        self._cancelled = True
        if self._extractor.is_running:
            self._extractor.cancel()
        elif self._focus.is_running:
            self._focus.cancel()
        elif self._pyramid.is_running:
            self._pyramid.cancel()

    # ---- state machine ----
    def _advance(self) -> None:
        self._idx += 1
        self._item_retried = False
        if self._cancelled or self._idx >= len(self._items):
            self._finish()
            return
        item = self._items[self._idx]
        if is_already_done(item.video_path, self._settings.export):
            item.status = "skipped"
            item.message = "outputs already exist"
            self.item_finished.emit(self._idx, "skipped", item.message)
            self._advance()
            return
        self._start_extract(item)

    def _start_extract(self, item: BatchItem) -> None:
        item.status = "running"
        item.step = "extract"
        self._temp_dir = tempfiles.make_temp_dir()
        self.item_started.emit(self._idx)
        self.item_status.emit(self._idx, "extracting")
        self._extractor.extract(
            item.video_path, str(self._temp_dir),
            decimation=self._settings.extract_decimation,
        )

    def _on_worker_cancelled(self) -> None:
        if 0 <= self._idx < len(self._items):
            self._items[self._idx].status = "cancelled"
            self.item_finished.emit(self._idx, "cancelled", "cancelled")
        self._cleanup_temp()
        self._finish()

    def _cleanup_temp(self) -> None:
        if self._temp_dir is not None:
            tempfiles.remove_temp_dir(self._temp_dir)
            self._temp_dir = None

    def _finish(self) -> None:
        summary = {"done": 0, "failed": 0, "skipped": 0, "cancelled": 0,
                   "total": len(self._items)}
        for it in self._items:
            if it.status in summary:
                summary[it.status] += 1
        self.batch_finished.emit(summary)

    # ---- worker signal handlers ----
    def _on_extract_progress(self, pct: int) -> None:
        self.item_progress.emit(self._idx, int(pct * 0.40))

    def _on_extract_failed(self, msg: str) -> None:
        self._fail_item(msg)

    def _on_extract_done(self, frames: list[str]) -> None:
        if self._cancelled:
            self._on_worker_cancelled()
            return
        self.item_status.emit(self._idx, "scoring")
        scores = [
            s.laplacian_var
            for s in score_frames(frames, progress_callback=self._scoring_progress)
        ]
        threshold = auto_threshold(scores)
        target = self._settings.cap or suggested_decimation_target(len(scores))
        mask = FilterState(
            scores=scores, threshold=threshold, decimation_target=target
        ).kept_mask()
        kept = [p for p, keep in zip(frames, mask) if keep]
        # A Cancel during scoring's processEvents() pump lands here (no worker was
        # running to emit `cancelled`), so finalize the run before launching a stack.
        if self._cancelled:
            self._on_worker_cancelled()
            return
        if not kept:  # defense-in-depth: auto_threshold makes this unreachable
            self._fail_item("no frames kept after filtering")
            return
        self._kept = kept
        self._start_stack()

    def _scoring_progress(self, done: int, total: int) -> None:
        self.item_progress.emit(self._idx, 40 + int(15 * done / max(1, total)))
        QApplication.processEvents()

    def _start_stack(self) -> None:
        item = self._items[self._idx]
        item.step = "stack"
        assert self._temp_dir is not None
        self._stack_out = str(self._temp_dir / "stacked.tif")
        method = self._settings.method
        if method == "auto":
            w, h = _first_frame_size(self._kept[0])
            method = choose_method(len(self._kept), w, h)
            self.log.emit(f"[auto] {method} for {len(self._kept)} frames at {w}x{h}")
        self.item_status.emit(self._idx, f"stacking ({method})")
        self._stack_method = method
        if method == "pyramid":
            self._pyramid.stack(self._kept, self._stack_out, **self._settings.pyramid_params)
        else:
            self._focus.stack(self._kept, self._stack_out, **self._settings.focus_params)

    def _on_stack_progress(self, pct: int) -> None:
        self.item_progress.emit(self._idx, 55 + int(pct * 0.35))

    def _on_stack_done(self, out_path: str) -> None:
        if self._cancelled:
            return
        self._export(out_path)

    def _export(self, stacked: str) -> None:
        item = self._items[self._idx]
        item.step = "export"
        self.item_status.emit(self._idx, "exporting")
        written: list[str] = []
        try:
            for target in output_targets(item.video_path, self._settings.export):
                if target.exists():
                    continue
                if target.suffix == ".tif":
                    export_tiff(stacked, str(target))
                else:
                    export_jpeg(stacked, str(target), quality=self._settings.export["quality"])
                written.append(str(target))
        except OSError as exc:
            self._fail_item(f"export failed: {exc}")
            return
        item.status = "done"
        item.output_paths = written
        item.message = ", ".join(Path(w).name for w in written) or "already present"
        self.item_progress.emit(self._idx, 100)
        self.item_finished.emit(self._idx, "done", item.message)
        self._cleanup_temp()
        self._advance()

    def _on_stack_failed(self, msg: str) -> None:
        if self._cancelled:
            return
        params = self._settings.focus_params
        if self._stack_method != "pyramid" and should_retry_without_opencl(
            msg, compare_mode=False, already_retried=self._item_retried,
            extra_cli=params.get("extra_cli", ""),
        ):
            self._item_retried = True
            retry = {**params,
                     "extra_cli": ("--no-opencl " + params.get("extra_cli", "")).strip()}
            self.log.emit("[auto] OpenCL failure; retrying on CPU with --no-opencl")
            self._focus.stack(self._kept, self._stack_out, **retry)
            return
        self._fail_item(msg)

    def _fail_item(self, msg: str) -> None:
        item = self._items[self._idx]
        item.status = "failed"
        item.message = msg.splitlines()[0] if msg else "failed"
        self.log.emit(f"[batch] {Path(item.video_path).name} failed: {item.message}")
        self.item_finished.emit(self._idx, "failed", item.message)
        self._cleanup_temp()
        self._advance()


def _first_frame_size(path: str) -> tuple[int, int]:
    try:
        with Image.open(path) as im:
            return im.size
    except Exception:  # noqa: BLE001
        return 1920, 1080
