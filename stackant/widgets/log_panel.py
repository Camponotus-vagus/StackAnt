"""Collapsible subprocess-output log panel."""
from __future__ import annotations

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QClipboard, QFontDatabase, QGuiApplication
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class LogPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
        self._copy_timer = QTimer(self)
        self._copy_timer.setSingleShot(True)
        self._copy_timer.timeout.connect(self._reset_copy_label)
        self._visible = False
        self._update_visibility()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        btn_row = QHBoxLayout()
        self.btn_toggle = QPushButton("Show log ▾")
        self.btn_toggle.setToolTip("Show or hide the detailed processing log")
        self.btn_toggle.setAccessibleName("Toggle log visibility")
        self.btn_toggle.clicked.connect(self._toggle)
        btn_row.addWidget(self.btn_toggle)

        self.btn_copy = QPushButton("Copy log")
        self.btn_copy.setToolTip("Copy the entire log to the clipboard")
        self.btn_copy.setAccessibleName("Copy log to clipboard")
        self.btn_copy.clicked.connect(self._copy)
        btn_row.addWidget(self.btn_copy)

        self.btn_clear = QPushButton("Clear")
        self.btn_clear.setToolTip("Clear all text from the log")
        self.btn_clear.setAccessibleName("Clear log content")
        self.btn_clear.clicked.connect(self._clear)
        btn_row.addWidget(self.btn_clear)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        self.view = QPlainTextEdit()
        self.view.setAccessibleName("Processing log")
        self.view.setReadOnly(True)
        self.view.setMaximumBlockCount(5000)
        self.view.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self.view.setFixedHeight(160)
        layout.addWidget(self.view)

    def _toggle(self) -> None:
        self._visible = not self._visible
        self._update_visibility()

    def _update_visibility(self) -> None:
        self.view.setVisible(self._visible)
        self.btn_copy.setVisible(self._visible)
        self.btn_clear.setVisible(self._visible)
        self.btn_toggle.setText("Hide log ▴" if self._visible else "Show log ▾")

    def append(self, text: str) -> None:
        text = text.rstrip("\n")
        if text:
            self.view.appendPlainText(text)

    def append_tagged(self, tag: str, text: str) -> None:
        """Like append(), but prepends '[tag] ' to every line."""
        prefix = f"[{tag}] "
        for line in text.rstrip("\n").splitlines() or [""]:
            if line:
                self.view.appendPlainText(prefix + line)

    def _copy(self) -> None:
        clip = QGuiApplication.clipboard()
        if clip is not None:
            clip.setText(self.view.toPlainText(), QClipboard.Mode.Clipboard)
            self.btn_copy.setText("Copied!")
            self._copy_timer.start(2000)

    def _reset_copy_label(self) -> None:
        self.btn_copy.setText("Copy log")

    def _clear(self) -> None:
        self.view.clear()
