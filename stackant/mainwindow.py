"""Main application window — wires controls, filter, filmstrip, preview, subprocesses."""
from __future__ import annotations

from pathlib import Path
from typing import Sequence

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QSplitter,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from . import config, tempfiles
from .dependency_checker import ToolStatus
from .exporter import export_jpeg, export_tiff, reveal_in_file_manager
from .folder_loader import list_images
from .frame_extractor import FrameExtractor
from .frame_filter import (
    FilterState,
    auto_threshold,
    score_frames,
    suggested_decimation_target,
)
from .stacker import FocusStacker
from .widgets.controls import ControlsPanel
from .widgets.filmstrip import Filmstrip
from .widgets.log_panel import LogPanel
from .widgets.preview_panel import PreviewPanel

STACKED_FILENAME = "stacked_preview.tif"


class MainWindow(QMainWindow):
    def __init__(self, tool_statuses: Sequence[ToolStatus] | None = None):
        super().__init__()
        self.setWindowTitle(config.APP_NAME)
        self.resize(1280, 820)

        self._tool_statuses = tool_statuses
        self._extractor = FrameExtractor(self)
        self._stacker = FocusStacker(self)
        self._current_temp_dir: Path | None = None
        self._filter_state: FilterState | None = None
        self._stacked_output: str | None = None

        self._build_ui()
        self._wire_signals()
        self._show_tool_statuses(tool_statuses)

    # ---- UI construction -------------------------------------------------

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 4)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.controls = ControlsPanel()
        self.filmstrip = Filmstrip()
        self.preview_panel = PreviewPanel()
        splitter.addWidget(self.controls)
        splitter.addWidget(self.filmstrip)
        splitter.addWidget(self.preview_panel)
        splitter.setSizes([320, 500, 460])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 1)
        root.addWidget(splitter, stretch=1)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setRange(0, 100)
        root.addWidget(self.progress)

        self.log_panel = LogPanel()
        root.addWidget(self.log_panel)

        self.setStatusBar(QStatusBar())

    def _wire_signals(self) -> None:
        self.controls.video_selected.connect(self._on_video_selected)
        self.controls.folder_selected.connect(self._on_folder_selected)
        self.controls.extract_requested.connect(self._on_extract_requested)
        self.controls.cancel_requested.connect(self._extractor.cancel)

        fc = self.controls.filter_controls
        fc.threshold_changed.connect(self._on_threshold_changed)
        fc.decimation_changed.connect(self._on_decimation_changed)
        fc.auto_threshold_requested.connect(self._on_auto_threshold)

        sc = self.controls.stack_controls
        sc.stack_requested.connect(self._on_stack_requested)
        sc.cancel_requested.connect(self._stacker.cancel)

        self.filmstrip.toggle_requested.connect(self._on_frame_toggled)
        self.filmstrip.currentItemChanged.connect(self._on_filmstrip_selection_changed)

        self.preview_panel.restack_requested.connect(self._on_stack_requested)

        self.controls.export_controls.export_requested.connect(self._on_export_requested)

        self._extractor.progress.connect(self.progress.setValue)
        self._extractor.log.connect(self.log_panel.append)
        self._extractor.finished_ok.connect(self._on_extraction_done)
        self._extractor.failed.connect(self._on_extraction_failed)

        self._stacker.progress.connect(self.progress.setValue)
        self._stacker.log.connect(self.log_panel.append)
        self._stacker.command_ready.connect(
            lambda cmd: self.log_panel.append(f"\n$ {cmd}\n")
        )
        self._stacker.finished_ok.connect(self._on_stack_done)
        self._stacker.failed.connect(self._on_stack_failed)

    # ---- input handling --------------------------------------------------

    def _on_video_selected(self, path: str) -> None:
        self.filmstrip.clear()
        self._filter_state = None
        self.preview_panel.clear()
        self.controls.filter_controls.setEnabled(False)
        self.controls.stack_controls.set_ready(False)
        self.statusBar().showMessage(f"Loaded video: {Path(path).name}", 4000)

    def _on_folder_selected(self, path: str) -> None:
        self.preview_panel.clear()
        frames = list_images(path)
        if not frames:
            self.statusBar().showMessage("No images found in folder.", 5000)
            self.filmstrip.clear()
            return
        self.statusBar().showMessage(f"Loading {len(frames)} thumbnails…")
        self.filmstrip.load_frames(frames)
        self.statusBar().showMessage(f"Loaded {len(frames)} frames. Scoring…")
        self._run_scoring(frames)

    def _on_extract_requested(self, decimation: int) -> None:
        video_path = self.controls.input_path
        if not video_path:
            return
        self._current_temp_dir = tempfiles.make_temp_dir()
        self.progress.setVisible(True)
        self.progress.setValue(0)
        self.controls.set_busy(True)
        self.statusBar().showMessage("Extracting frames with ffmpeg…")
        self._extractor.extract(
            video_path, str(self._current_temp_dir), decimation=decimation
        )

    # ---- extraction pipeline ---------------------------------------------

    def _on_extraction_done(self, frames: list) -> None:
        self.progress.setVisible(False)
        self.controls.set_busy(False)
        self.statusBar().showMessage(
            f"Extracted {len(frames)} frames. Generating thumbnails…"
        )
        self.filmstrip.load_frames(frames)
        self.statusBar().showMessage(f"Scoring {len(frames)} frames…")
        self._run_scoring(frames)

    def _on_extraction_failed(self, msg: str) -> None:
        self.progress.setVisible(False)
        self.controls.set_busy(False)
        first_line = msg.splitlines()[0] if msg else "Extraction failed."
        self.statusBar().showMessage(f"Extraction failed: {first_line}")

    # ---- filtering -------------------------------------------------------

    def _run_scoring(self, frames: list[str]) -> None:
        scored = score_frames(frames)
        scores = [s.laplacian_var for s in scored]
        target = suggested_decimation_target(len(scores))
        threshold = auto_threshold(scores)
        self._filter_state = FilterState(
            scores=scores,
            threshold=threshold,
            decimation_target=target if target < len(scores) else None,
        )

        fc = self.controls.filter_controls
        fc.setEnabled(True)
        fc.configure_range(min(scores), max(scores) if scores else 1.0)
        fc.set_threshold(threshold)
        if self._filter_state.decimation_target:
            fc.chk_decimate.setChecked(True)
            fc.spn_decimation_target.setValue(self._filter_state.decimation_target)
        else:
            fc.chk_decimate.setChecked(False)

        self._refresh_filter_view()

    def _refresh_filter_view(self) -> None:
        if self._filter_state is None:
            return
        mask = self._filter_state.kept_mask()
        self.filmstrip.apply_mask(mask)
        kept, total = self._filter_state.counts()
        self.controls.filter_controls.set_counts(kept, total)
        self.controls.stack_controls.set_ready(kept > 0)
        self.statusBar().showMessage(f"{kept} / {total} frames kept.", 4000)

    def _on_threshold_changed(self, value: float) -> None:
        if self._filter_state is None:
            return
        self._filter_state.threshold = value
        self._refresh_filter_view()

    def _on_decimation_changed(self, target: int) -> None:
        if self._filter_state is None:
            return
        self._filter_state.decimation_target = target if target > 0 else None
        self._refresh_filter_view()

    def _on_auto_threshold(self) -> None:
        if self._filter_state is None:
            return
        value = auto_threshold(self._filter_state.scores)
        self._filter_state.threshold = value
        self.controls.filter_controls.set_threshold(value)
        self._refresh_filter_view()

    def _on_filmstrip_selection_changed(self, current, _previous) -> None:
        if current is None:
            self.preview_panel.set_input_reference(None)
            return
        path = current.data(Qt.ItemDataRole.UserRole)
        self.preview_panel.set_input_reference(path)

    def _on_frame_toggled(self, index: int) -> None:
        if self._filter_state is None:
            return
        current_mask = self._filter_state.kept_mask()
        if 0 <= index < len(current_mask):
            self._filter_state.manual_overrides[index] = not current_mask[index]
            self._refresh_filter_view()

    # ---- stacking --------------------------------------------------------

    def _kept_frame_paths(self) -> list[str]:
        if self._filter_state is None:
            return []
        mask = self._filter_state.kept_mask()
        paths = self.filmstrip.frame_paths()
        return [p for p, m in zip(paths, mask) if m]

    def _on_stack_requested(self) -> None:
        kept = self._kept_frame_paths()
        if not kept:
            self.statusBar().showMessage("No frames selected for stacking.")
            return
        if self._current_temp_dir is None:
            self._current_temp_dir = tempfiles.make_temp_dir()
        output = str(self._current_temp_dir / STACKED_FILENAME)
        self._stacked_output = output
        self.progress.setVisible(True)
        self.progress.setValue(0)
        self.controls.stack_controls.set_running(True)
        self.statusBar().showMessage(f"Stacking {len(kept)} frames…")
        self._stacker.stack(kept, output, **self.controls.stack_controls.params())

    def _on_stack_done(self, output_path: str) -> None:
        self.progress.setVisible(False)
        self.controls.stack_controls.set_running(False)
        self.statusBar().showMessage(f"Stack complete: {Path(output_path).name}", 8000)
        self.preview_panel.show_stacked(output_path)
        self.controls.export_controls.setEnabled(True)
        if self.controls.input_path:
            self.controls.export_controls.prefill_for_input(self.controls.input_path)

    def _on_stack_failed(self, msg: str) -> None:
        self.progress.setVisible(False)
        self.controls.stack_controls.set_running(False)
        first_line = msg.splitlines()[0] if msg else "Stack failed."
        self.statusBar().showMessage(f"Stack failed: {first_line}")
        self.log_panel.append(msg)

    # ---- export ----------------------------------------------------------

    def _on_export_requested(self) -> None:
        stacked = self._stacked_output
        if not stacked or not Path(stacked).is_file():
            self.statusBar().showMessage("Nothing to export — stack a result first.")
            return
        s = self.controls.export_controls.settings()
        if not s["folder"]:
            self.statusBar().showMessage("Please pick an output folder.")
            return
        if not (s["tiff"] or s["jpeg"]):
            self.statusBar().showMessage("Select at least one output format (TIFF or JPEG).")
            return

        folder = Path(s["folder"])
        targets: list[Path] = []
        if s["tiff"]:
            targets.append(folder / f"{s['name']}.tif")
        if s["jpeg"]:
            targets.append(folder / f"{s['name']}.jpg")

        existing = [t for t in targets if t.exists()]
        if existing:
            names = "\n  ".join(str(t.name) for t in existing)
            reply = QMessageBox.question(
                self,
                "Overwrite?",
                f"The following file(s) already exist in the output folder:\n  {names}\n\n"
                "Overwrite them?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                self.statusBar().showMessage("Export cancelled.")
                return

        try:
            if s["tiff"]:
                export_tiff(stacked, str(folder / f"{s['name']}.tif"))
            if s["jpeg"]:
                export_jpeg(stacked, str(folder / f"{s['name']}.jpg"), quality=s["quality"])
        except OSError as exc:
            self.statusBar().showMessage(f"Export failed: {exc}")
            return

        written = ", ".join(t.name for t in targets)
        self.statusBar().showMessage(f"Exported: {written}", 8000)
        reveal_in_file_manager(str(folder))

    # ---- status bar ------------------------------------------------------

    def _show_tool_statuses(self, statuses: Sequence[ToolStatus] | None) -> None:
        if not statuses:
            self.statusBar().showMessage("Ready.")
            return
        parts = []
        for s in statuses:
            if s.version:
                v = s.version if len(s.version) <= 60 else s.version[:57] + "…"
                parts.append(f"{s.name}: {v}")
            else:
                parts.append(f"{s.name}: missing")
        self.statusBar().showMessage("  |  ".join(parts))
