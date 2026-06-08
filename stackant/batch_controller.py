"""Sequential, unattended batch orchestration over a list of videos."""
from __future__ import annotations

from pathlib import Path

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
    def run(self, items, settings) -> None:
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

    def _start_extract(self, item) -> None:
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

    # ---- step handlers (filled in Tasks 7-8) ----
    def _on_extract_progress(self, pct: int) -> None:
        self.item_progress.emit(self._idx, int(pct * 0.40))

    def _on_extract_failed(self, msg: str) -> None:
        self._fail_item(msg)

    def _on_extract_done(self, frames) -> None:
        raise NotImplementedError  # Task 7

    def _on_stack_progress(self, pct: int) -> None:
        self.item_progress.emit(self._idx, 55 + int(pct * 0.35))

    def _on_stack_done(self, out_path: str) -> None:
        raise NotImplementedError  # Task 7

    def _on_stack_failed(self, msg: str) -> None:
        raise NotImplementedError  # Task 8

    def _fail_item(self, msg: str) -> None:
        item = self._items[self._idx]
        item.status = "failed"
        item.message = msg.splitlines()[0] if msg else "failed"
        self.log.emit(f"[batch] {Path(item.video_path).name} failed: {item.message}")
        self.item_finished.emit(self._idx, "failed", item.message)
        self._cleanup_temp()
        self._advance()
