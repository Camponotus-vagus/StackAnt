"""Main application window — wires Controls, Filmstrip, Preview, FrameExtractor."""
from __future__ import annotations

from pathlib import Path
from typing import Sequence

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame,
    QLabel,
    QMainWindow,
    QProgressBar,
    QSplitter,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from . import config, tempfiles
from .dependency_checker import ToolStatus
from .folder_loader import list_images
from .frame_extractor import FrameExtractor
from .widgets.controls import ControlsPanel
from .widgets.filmstrip import Filmstrip


class _PlaceholderPanel(QFrame):
    def __init__(self, title: str, subtitle: str = "", parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        header = QLabel(title)
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = header.font()
        font.setBold(True)
        header.setFont(font)
        layout.addWidget(header)
        if subtitle:
            sub = QLabel(subtitle)
            sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
            sub.setWordWrap(True)
            sub.setStyleSheet("color: gray;")
            layout.addWidget(sub)
        layout.addStretch(1)


class MainWindow(QMainWindow):
    def __init__(self, tool_statuses: Sequence[ToolStatus] | None = None):
        super().__init__()
        self.setWindowTitle(config.APP_NAME)
        self.resize(1240, 760)

        self._tool_statuses = tool_statuses
        self._extractor = FrameExtractor(self)
        self._current_temp_dir: Path | None = None

        self._build_ui()
        self._wire_signals()
        self._show_tool_statuses(tool_statuses)

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 4)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.controls = ControlsPanel()
        self.filmstrip = Filmstrip()
        self.preview_panel = _PlaceholderPanel(
            "Preview", "Stacked result and crop detail appear here after Session 5."
        )
        splitter.addWidget(self.controls)
        splitter.addWidget(self.filmstrip)
        splitter.addWidget(self.preview_panel)
        splitter.setSizes([300, 500, 440])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 1)
        root.addWidget(splitter, stretch=1)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setRange(0, 100)
        root.addWidget(self.progress)

        self.setStatusBar(QStatusBar())

    def _wire_signals(self) -> None:
        self.controls.video_selected.connect(self._on_video_selected)
        self.controls.folder_selected.connect(self._on_folder_selected)
        self.controls.extract_requested.connect(self._on_extract_requested)
        self.controls.cancel_requested.connect(self._extractor.cancel)

        self._extractor.progress.connect(self.progress.setValue)
        self._extractor.finished_ok.connect(self._on_extraction_done)
        self._extractor.failed.connect(self._on_extraction_failed)

    def _on_video_selected(self, path: str) -> None:
        self.filmstrip.clear()
        self.statusBar().showMessage(f"Loaded video: {Path(path).name}", 4000)

    def _on_folder_selected(self, path: str) -> None:
        frames = list_images(path)
        if not frames:
            self.statusBar().showMessage("No images found in folder.", 5000)
            self.filmstrip.clear()
            return
        self.statusBar().showMessage(f"Loading {len(frames)} thumbnails…")
        self.filmstrip.load_frames(frames)
        self.statusBar().showMessage(
            f"Loaded {len(frames)} frames from {Path(path).name}.", 4000
        )

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

    def _on_extraction_done(self, frames: list) -> None:
        self.progress.setVisible(False)
        self.controls.set_busy(False)
        self.statusBar().showMessage(f"Extracted {len(frames)} frames. Generating thumbnails…")
        self.filmstrip.load_frames(frames)
        self.statusBar().showMessage(f"Ready. {len(frames)} frames extracted.", 6000)

    def _on_extraction_failed(self, msg: str) -> None:
        self.progress.setVisible(False)
        self.controls.set_busy(False)
        # Keep the message persistent (no timeout) so the user can read it.
        first_line = msg.splitlines()[0] if msg else "Extraction failed."
        self.statusBar().showMessage(f"Extraction failed: {first_line}")

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
