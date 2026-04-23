"""Main application window — wires controls, filter, filmstrip, preview, subprocesses."""
from __future__ import annotations

from pathlib import Path
from typing import Sequence

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QIcon, QKeySequence
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QSplitter,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from . import config, settings, tempfiles
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
        self._build_menu()
        self._wire_signals()
        self._apply_saved_defaults()
        self._show_tool_statuses(tool_statuses)

        icon_path = Path(__file__).resolve().parent.parent / "assets" / "icon.png"
        if icon_path.is_file():
            self.setWindowIcon(QIcon(str(icon_path)))

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

    def _build_menu(self) -> None:
        mb = self.menuBar()
        m_file = mb.addMenu("&File")

        self.act_open_video = QAction("Open &Video…", self)
        self.act_open_video.setShortcut(QKeySequence.StandardKey.Open)
        self.act_open_video.setStatusTip("Open a manual-focus-pull video for frame extraction")
        self.act_open_video.triggered.connect(self.controls._pick_video)
        m_file.addAction(self.act_open_video)

        self.act_open_folder = QAction("Open Image &Folder…", self)
        self.act_open_folder.setShortcut("Ctrl+Shift+O")
        self.act_open_folder.setStatusTip("Load an existing folder of already-extracted frames")
        self.act_open_folder.triggered.connect(self.controls._pick_folder)
        m_file.addAction(self.act_open_folder)

        m_file.addSeparator()

        self.act_export = QAction("&Export stacked image…", self)
        self.act_export.setShortcut("Ctrl+E")
        self.act_export.setStatusTip("Export the stacked result to TIFF and/or JPEG")
        self.act_export.triggered.connect(self._on_export_requested)
        m_file.addAction(self.act_export)

        m_file.addSeparator()

        act_quit = QAction("&Quit", self)
        act_quit.setShortcut(QKeySequence.StandardKey.Quit)
        act_quit.triggered.connect(self.close)
        m_file.addAction(act_quit)

    def _set_busy(self, busy: bool) -> None:
        """Toggle controls + File menu together so there's one source of truth."""
        self.controls.set_busy(busy)
        self.act_open_video.setEnabled(not busy)
        self.act_open_folder.setEnabled(not busy)

    def _apply_saved_defaults(self) -> None:
        geom, state = settings.load_window_state()
        if geom:
            self.restoreGeometry(geom)
        if state:
            self.restoreState(state)

        exp = settings.load_export_defaults()
        ec = self.controls.export_controls
        if exp["folder"]:
            ec.txt_folder.setText(exp["folder"])
        ec.chk_tiff.setChecked(exp["tiff"])
        ec.chk_jpeg.setChecked(exp["jpeg"])
        ec.sld_quality.setValue(exp["quality"])

        sp = settings.load_stack_params()
        sc = self.controls.stack_controls
        sc.spn_consistency.setValue(sp["consistency"])
        sc.chk_denoise.setChecked(sp["denoise"])
        sc.spn_sharp.setValue(sp["sharp_strength"])
        if sp["halo_radius"] is not None:
            sc.chk_halo.setChecked(True)
            sc.spn_halo.setValue(sp["halo_radius"])
        sc.txt_extra.setText(sp["extra_cli"])
        sc.chk_no_opencl.setChecked(sp["no_opencl"])

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
        self._extractor.cancelled.connect(self._on_extraction_cancelled)

        self._stacker.progress.connect(self.progress.setValue)
        self._stacker.log.connect(self.log_panel.append)
        self._stacker.command_ready.connect(
            lambda cmd: self.log_panel.append(f"\n$ {cmd}\n")
        )
        self._stacker.finished_ok.connect(self._on_stack_done)
        self._stacker.failed.connect(self._on_stack_failed)
        self._stacker.cancelled.connect(self._on_stack_cancelled)

    # ---- input handling --------------------------------------------------

    def _reset_pipeline_state(self) -> None:
        """Drop everything that belongs to the previous input.

        Called on new video/folder load so stale stacked output doesn't
        linger behind a fresh input.
        """
        self.filmstrip.clear()
        self._filter_state = None
        self._stacked_output = None
        self._current_temp_dir = None
        self.preview_panel.clear()
        self.controls.filter_controls.setEnabled(False)
        self.controls.stack_controls.set_ready(False)
        self.controls.export_controls.setEnabled(False)

    def _on_video_selected(self, path: str) -> None:
        self._reset_pipeline_state()
        self.statusBar().showMessage(f"Loaded video: {Path(path).name}", 4000)

    def _on_folder_selected(self, path: str) -> None:
        self._reset_pipeline_state()
        frames = list_images(path)
        if not frames:
            self.statusBar().showMessage("No images found in folder.", 5000)
            return
        self.statusBar().showMessage(f"Loading {len(frames)} thumbnails…")
        self.progress.setVisible(True)
        self._drive_progress(0, 1)
        self.filmstrip.load_frames(frames, progress_callback=self._drive_progress)
        self._run_scoring(frames)
        self.progress.setVisible(False)

    def _on_extract_requested(self, decimation: int) -> None:
        video_path = self.controls.input_path
        if not video_path:
            return
        self._current_temp_dir = tempfiles.make_temp_dir()
        self.progress.setVisible(True)
        self.progress.setValue(0)
        self._set_busy(True)
        self.statusBar().showMessage("Extracting frames with ffmpeg…")
        self._extractor.extract(
            video_path, str(self._current_temp_dir), decimation=decimation
        )

    # ---- extraction pipeline ---------------------------------------------

    def _on_extraction_done(self, frames: list) -> None:
        self._set_busy(False)
        self.statusBar().showMessage(
            f"Extracted {len(frames)} frames. Loading thumbnails…"
        )
        self.progress.setVisible(True)
        self._drive_progress(0, 1)
        self.filmstrip.load_frames(frames, progress_callback=self._drive_progress)
        self._run_scoring(frames)
        self.progress.setVisible(False)

    def _on_extraction_failed(self, msg: str) -> None:
        self.progress.setVisible(False)
        self._set_busy(False)
        first_line = msg.splitlines()[0] if msg else "Extraction failed."
        self.log_panel.append(msg)
        self.statusBar().showMessage(
            f"Extraction failed: {first_line}  (See log panel for details.)"
        )

    def _on_extraction_cancelled(self) -> None:
        self.progress.setVisible(False)
        self._set_busy(False)
        self.statusBar().showMessage("Extraction cancelled.", 4000)

    # ---- filtering -------------------------------------------------------

    def _drive_progress(self, done: int, total: int) -> None:
        """Update the progress bar synchronously and keep the UI responsive.

        Used for in-thread workloads (thumbnail decode, Laplacian scoring)
        where the natural Qt signal loop can't drive the bar.
        """
        if total <= 0:
            self.progress.setValue(0)
        else:
            self.progress.setValue(min(100, int(done * 100 / total)))
        QApplication.processEvents()

    def _run_scoring(self, frames: list[str]) -> None:
        self.statusBar().showMessage(f"Scoring {len(frames)} frames…")
        self.progress.setVisible(True)
        self._drive_progress(0, 1)
        scored = score_frames(frames, progress_callback=self._drive_progress)
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
        fc.configure_range(min(scores, default=0.0), max(scores, default=1.0))
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
        # Lock input switching while the stack runs
        self.act_open_video.setEnabled(False)
        self.act_open_folder.setEnabled(False)
        self.statusBar().showMessage(f"Stacking {len(kept)} frames…")
        self._stacker.stack(kept, output, **self.controls.stack_controls.params())

    def _finish_stacking_ui(self) -> None:
        """Shared UI-reset after a stack completes, fails, or is cancelled."""
        self.progress.setVisible(False)
        self.controls.stack_controls.set_running(False)
        self.act_open_video.setEnabled(True)
        self.act_open_folder.setEnabled(True)

    def _on_stack_done(self, output_path: str) -> None:
        self._finish_stacking_ui()
        self.statusBar().showMessage(f"Stack complete: {Path(output_path).name}", 8000)
        self.preview_panel.show_stacked(output_path)
        self.controls.export_controls.setEnabled(True)
        if self.controls.input_path:
            self.controls.export_controls.prefill_for_input(self.controls.input_path)

    def _on_stack_failed(self, msg: str) -> None:
        self._finish_stacking_ui()
        first_line = msg.splitlines()[0] if msg else "Stack failed."
        hint = "  (See log panel for details.)"
        if "OpenCL" in msg or "CL_OUT_OF_RESOURCES" in msg:
            hint = "  (Try Advanced → Disable OpenCL and re-stack.)"
        self.statusBar().showMessage(f"Stack failed: {first_line}{hint}")
        self.log_panel.append(msg)

    def _on_stack_cancelled(self) -> None:
        self._finish_stacking_ui()
        self.statusBar().showMessage("Stacking cancelled.", 4000)

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

    # ---- close / persistence --------------------------------------------

    def closeEvent(self, event) -> None:
        # Cancel any running processes so they don't keep writing to temp
        self._extractor.cancel()
        self._stacker.cancel()
        # Persist settings
        settings.save_window_state(self.saveGeometry(), self.saveState())
        ec = self.controls.export_controls.settings()
        settings.save_export_defaults(
            folder=ec["folder"], quality=ec["quality"],
            tiff=ec["tiff"], jpeg=ec["jpeg"],
        )
        sc = self.controls.stack_controls
        settings.save_stack_params(
            consistency=sc.spn_consistency.value(),
            denoise=sc.chk_denoise.isChecked(),
            sharp_strength=sc.spn_sharp.value(),
            halo_radius=sc.spn_halo.value() if sc.chk_halo.isChecked() else None,
            extra_cli=sc.txt_extra.text().strip(),
            no_opencl=sc.chk_no_opencl.isChecked(),
        )
        # tempfiles.cleanup_all registered via atexit
        super().closeEvent(event)

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
