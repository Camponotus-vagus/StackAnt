"""Modal dialog for unattended batch processing of a folder of videos."""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from ..batch import BatchItem, discover_videos, is_already_done
from ..batch_controller import BatchController
from ..frame_extractor import FrameExtractor
from ..pyramid_stacker import PyramidStacker
from ..stacker import FocusStacker


class BatchDialog(QDialog):
    def __init__(self, controls, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Batch processing")
        self.resize(700, 480)
        self._controls = controls
        self._items: list[BatchItem] = []
        self._running = False

        self._controller = BatchController(
            FrameExtractor(self), FocusStacker(self), PyramidStacker(self), self
        )
        self._controller.item_started.connect(self._on_item_started)
        self._controller.item_progress.connect(self._on_item_progress)
        self._controller.item_status.connect(self._on_item_status)
        self._controller.item_finished.connect(self._on_item_finished)
        self._controller.batch_finished.connect(self._on_batch_finished)

        self._build_ui()
        self._refresh_summary()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        folder_row = QHBoxLayout()
        folder_row.addWidget(QLabel("Folder:"))
        self.txt_folder = QLineEdit()
        self.txt_folder.setReadOnly(True)
        self.btn_browse = QPushButton("Browse…")
        self.btn_browse.clicked.connect(self._browse)
        folder_row.addWidget(self.txt_folder, stretch=1)
        folder_row.addWidget(self.btn_browse)
        layout.addLayout(folder_row)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Video", "Status", "Detail"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table, stretch=1)

        self.btn_remove = QPushButton("Remove selected from queue")
        self.btn_remove.clicked.connect(self._remove_selected)
        layout.addWidget(self.btn_remove)

        self.lbl_summary = QLabel()
        self.lbl_summary.setWordWrap(True)
        self.lbl_summary.setStyleSheet("color: gray;")
        layout.addWidget(self.lbl_summary)

        self.lbl_overall = QLabel("Idle.")
        layout.addWidget(self.lbl_overall)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        layout.addWidget(self.progress)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self.btn_run = QPushButton("Run")
        self.btn_run.clicked.connect(self._run)
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self._controller.cancel)
        self.btn_cancel.setEnabled(False)
        self.btn_close = QPushButton("Close")
        self.btn_close.clicked.connect(self.reject)
        btn_row.addWidget(self.btn_run)
        btn_row.addWidget(self.btn_cancel)
        btn_row.addWidget(self.btn_close)
        layout.addLayout(btn_row)

        self._set_run_enabled()

    def _refresh_summary(self) -> None:
        s = self._controls.snapshot_for_batch()
        cap = s.cap if s.cap is not None else "auto"
        fmts = "+".join(
            name for name, on in (("TIFF", s.export["tiff"]), ("JPEG", s.export["jpeg"])) if on
        ) or "none"
        self.lbl_summary.setText(
            f"Method: {s.method} · extract every {s.extract_decimation} · cap {cap} · "
            f"export {fmts} (q{s.export['quality']}).  Read from the main panel — "
            "close to change."
        )

    def _browse(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select folder of videos")
        if path:
            self.txt_folder.setText(path)
            self._populate(path)

    def _populate(self, folder: str) -> None:
        export = self._controls.snapshot_for_batch().export
        self._items = [BatchItem(v) for v in discover_videos(folder)]
        self.table.setRowCount(len(self._items))
        for row, item in enumerate(self._items):
            done = is_already_done(item.video_path, export)
            if done:
                item.status = "skipped"
            self.table.setItem(row, 0, QTableWidgetItem(Path(item.video_path).name))
            self.table.setItem(row, 1, QTableWidgetItem("already done" if done else "pending"))
            self.table.setItem(row, 2, QTableWidgetItem(""))
        self.lbl_overall.setText(f"{len(self._items)} video(s) found.")
        self._refresh_summary()
        self._set_run_enabled()

    def _remove_selected(self) -> None:
        if self._running:
            return
        rows = sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True)
        for row in rows:
            self.table.removeRow(row)
            del self._items[row]
        self._set_run_enabled()

    def _set_run_enabled(self) -> None:
        self.btn_run.setEnabled(not self._running and bool(self._items))

    def _run(self) -> None:
        if not self._items:
            return
        self._running = True
        self.btn_run.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        for b in (self.btn_browse, self.btn_remove, self.btn_close):
            b.setEnabled(False)
        self._controller.run(self._items, self._controls.snapshot_for_batch())

    # ---- controller slots ----
    def _on_item_started(self, idx: int) -> None:
        self._set_row(idx, 1, "running")
        self.lbl_overall.setText(f"Video {idx + 1} / {len(self._items)}")

    def _on_item_progress(self, idx: int, pct: int) -> None:
        self.progress.setValue(pct)

    def _on_item_status(self, idx: int, label: str) -> None:
        self._set_row(idx, 2, label)

    def _on_item_finished(self, idx: int, status: str, message: str) -> None:
        self._set_row(idx, 1, status)
        self._set_row(idx, 2, message)

    def _on_batch_finished(self, summary: dict) -> None:
        self._running = False
        self.btn_cancel.setEnabled(False)
        for b in (self.btn_browse, self.btn_remove, self.btn_close):
            b.setEnabled(True)
        self.progress.setValue(0)
        tail = f" · cancelled: {summary['cancelled']}" if summary.get("cancelled") else ""
        self.lbl_overall.setText(
            f"Done: {summary['done']} · failed: {summary['failed']} · "
            f"skipped: {summary['skipped']}{tail}"
        )
        self._set_run_enabled()

    def _set_row(self, idx: int, col: int, text: str) -> None:
        if 0 <= idx < self.table.rowCount():
            self.table.setItem(idx, col, QTableWidgetItem(text))
