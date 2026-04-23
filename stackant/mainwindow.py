"""Main application window — placeholder panels until Sessions 2-5 fill them in."""
from __future__ import annotations

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

from . import config
from .dependency_checker import ToolStatus


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
        self.resize(1200, 720)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 4)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.controls_panel = _PlaceholderPanel(
            "Controls", "Video/folder input, filter threshold, stack params, export."
        )
        self.filmstrip_panel = _PlaceholderPanel(
            "Filmstrip", "Extracted frames appear here after Session 2."
        )
        self.preview_panel = _PlaceholderPanel(
            "Preview", "Stacked result and crop detail appear here after Session 5."
        )
        splitter.addWidget(self.controls_panel)
        splitter.addWidget(self.filmstrip_panel)
        splitter.addWidget(self.preview_panel)
        splitter.setSizes([280, 500, 420])
        root.addWidget(splitter, stretch=1)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        root.addWidget(self.progress)

        self.setStatusBar(QStatusBar())
        self._show_tool_statuses(tool_statuses)

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
